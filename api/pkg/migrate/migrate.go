// Package migrate is a tiny embedded SQL migrator for the Agent Playground API.
//
// Ports MSV's `pkg/migrate/migrate.go` pattern:
//   - Migrations live in `sql/NNN_name.sql` and are embedded at build time.
//   - A `schema_migrations` table records applied versions.
//   - Run() is idempotent: previously-applied versions are skipped.
//
// We intentionally do NOT use github.com/golang-migrate/migrate -- the embedded
// approach keeps the binary single-file and matches the MSV operational model.
//
// # Migration authoring rules
//
// Every SQL migration file MUST be written to be idempotent. If a migration
// fails after partial execution and is retried on the next startup, the retry
// must succeed without producing duplicate data or errors. Use:
//
//   - CREATE TABLE IF NOT EXISTS
//   - CREATE INDEX IF NOT EXISTS
//   - ALTER TABLE ... ADD COLUMN IF NOT EXISTS  (Postgres 9.6+)
//   - DO $$ BEGIN ... EXCEPTION WHEN duplicate_* THEN NULL; END $$
//
// Avoid bare ALTER TABLE ADD COLUMN, CREATE INDEX, or INSERT without conflict
// handling — these will error on retry if the first attempt succeeded partially.
//
// The migrator wraps each migration's SQL execution and schema_migrations INSERT
// in a single transaction, so a process crash between the two leaves neither
// committed. The advisory lock prevents concurrent API instances from running
// the same migration simultaneously.
package migrate

import (
	"context"
	"embed"
	"fmt"
	"io/fs"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/rs/zerolog"
)

//go:embed sql/*.sql
var embeddedFS embed.FS

// EmbeddedMigrations returns the embedded SQL migrations filesystem, rooted at
// the `sql/` directory inside the package.
func EmbeddedMigrations() fs.FS {
	sub, err := fs.Sub(embeddedFS, "sql")
	if err != nil {
		panic(fmt.Sprintf("embedded migrations: %v", err))
	}
	return sub
}

// DB defines the database operations needed by the migrator. Both
// *pgxpool.Pool and *pgx.Conn satisfy this interface, which makes the migrator
// trivially testable against an embedded postgres in tests.
//
// Begin is required to wrap each migration's apply+record steps in a single
// transaction and to acquire a session-level advisory lock that serializes
// concurrent migrators (preventing TOCTOU races on startup).
type DB interface {
	Exec(ctx context.Context, sql string, arguments ...any) (pgconn.CommandTag, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
	Begin(ctx context.Context) (pgx.Tx, error)
}

// Migration represents a single parsed SQL migration file.
type Migration struct {
	Version  int
	Name     string
	Filename string
	SQL      string
}

// Migrator runs database migrations against a DB.
type Migrator struct {
	db     DB
	logger zerolog.Logger
	fsys   fs.FS
}

// New creates a Migrator. Use EmbeddedMigrations() for the production path
// or pass an in-memory fs.FS in tests.
func New(db DB, logger zerolog.Logger, fsys fs.FS) *Migrator {
	return &Migrator{db: db, logger: logger, fsys: fsys}
}

// ParseMigrations reads and parses migration files from the filesystem.
// Filenames must follow the `NNN_name.sql` convention; entries are returned
// sorted by version ascending.
func ParseMigrations(fsys fs.FS) ([]Migration, error) {
	entries, err := fs.ReadDir(fsys, ".")
	if err != nil {
		return nil, fmt.Errorf("read migrations directory: %w", err)
	}

	var migrations []Migration
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".sql" {
			continue
		}

		name := entry.Name()
		parts := strings.SplitN(strings.TrimSuffix(name, ".sql"), "_", 2)
		if len(parts) != 2 {
			return nil, fmt.Errorf("invalid migration filename: %s (expected NNN_name.sql)", name)
		}

		version, err := strconv.Atoi(parts[0])
		if err != nil {
			return nil, fmt.Errorf("invalid migration filename: %s (version must be numeric)", name)
		}

		data, err := fs.ReadFile(fsys, name)
		if err != nil {
			return nil, fmt.Errorf("read migration %s: %w", name, err)
		}

		migrations = append(migrations, Migration{
			Version:  version,
			Name:     parts[1],
			Filename: name,
			SQL:      string(data),
		})
	}

	sort.Slice(migrations, func(i, j int) bool {
		return migrations[i].Version < migrations[j].Version
	})

	return migrations, nil
}

// migrationAdvisoryLock is a stable, arbitrary integer used as the key for the
// Postgres session-level advisory lock that serializes concurrent migrators.
// Any two-process race on startup will block on this lock rather than racing
// through the TOCTOU check-then-insert gap.
const migrationAdvisoryLock = 8675309

// Run executes all pending migrations in version order. It is safe to call
// multiple times -- migrations already recorded in `schema_migrations` are
// skipped.
//
// Correctness guarantees:
//   - A session-level advisory lock (pg_advisory_lock) prevents two processes
//     from running migrations concurrently.
//   - Each migration's SQL execution and schema_migrations INSERT are wrapped
//     in a single transaction so that a crash between the two steps cannot
//     leave the migration half-recorded.
func (m *Migrator) Run(ctx context.Context) error {
	// Acquire session-level advisory lock. This blocks until no other session
	// holds the lock, serialising concurrent API instances on rolling deploys.
	if _, err := m.db.Exec(ctx, "SELECT pg_advisory_lock($1)", migrationAdvisoryLock); err != nil {
		return fmt.Errorf("acquire migration lock: %w", err)
	}
	// Release the lock when Run returns, even on error.
	defer m.db.Exec(ctx, "SELECT pg_advisory_unlock($1)", migrationAdvisoryLock) //nolint:errcheck

	if _, err := m.db.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version INTEGER PRIMARY KEY,
			filename VARCHAR(255) NOT NULL,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
		)
	`); err != nil {
		return fmt.Errorf("create schema_migrations table: %w", err)
	}

	migrations, err := ParseMigrations(m.fsys)
	if err != nil {
		return err
	}

	for _, migration := range migrations {
		var v int
		err := m.db.QueryRow(ctx,
			"SELECT version FROM schema_migrations WHERE version = $1",
			migration.Version,
		).Scan(&v)

		if err == nil {
			m.logger.Debug().
				Int("version", migration.Version).
				Str("name", migration.Name).
				Msg("migration already applied, skipping")
			continue
		}

		if err != pgx.ErrNoRows {
			return fmt.Errorf("check migration %s: %w", migration.Filename, err)
		}

		m.logger.Info().
			Int("version", migration.Version).
			Str("name", migration.Name).
			Msg("applying migration")

		// Wrap apply + record in a single transaction so a crash between the
		// two steps cannot leave schema_migrations inconsistent with the schema.
		tx, err := m.db.Begin(ctx)
		if err != nil {
			return fmt.Errorf("begin transaction for migration %s: %w", migration.Filename, err)
		}

		if _, err = tx.Exec(ctx, migration.SQL); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("migration %s failed: %w", migration.Filename, err)
		}

		if _, err = tx.Exec(ctx,
			"INSERT INTO schema_migrations (version, filename) VALUES ($1, $2)",
			migration.Version, migration.Filename,
		); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("record migration %s: %w", migration.Filename, err)
		}

		if err = tx.Commit(ctx); err != nil {
			return fmt.Errorf("commit migration %s: %w", migration.Filename, err)
		}

		m.logger.Info().
			Int("version", migration.Version).
			Str("name", migration.Name).
			Msg("migration applied successfully")
	}

	return nil
}

// Run is a convenience for callers that already have a *pgxpool.Pool and want
// the embedded migrations applied with default logging. It mirrors the call
// signature most cmd/server entry points want: `migrate.Run(ctx, pool)`.
func Run(ctx context.Context, db DB, logger zerolog.Logger) error {
	return New(db, logger, EmbeddedMigrations()).Run(ctx)
}
