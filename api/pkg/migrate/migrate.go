// Package migrate is a tiny embedded SQL migrator for the Agent Playground API.
//
// Ports MSV's `pkg/migrate/migrate.go` pattern:
//   - Migrations live in `sql/NNN_name.sql` and are embedded at build time.
//   - A `schema_migrations` table records applied versions.
//   - Run() is idempotent: previously-applied versions are skipped.
//
// We intentionally do NOT use github.com/golang-migrate/migrate -- the embedded
// approach keeps the binary single-file and matches the MSV operational model.
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
type DB interface {
	Exec(ctx context.Context, sql string, arguments ...any) (pgconn.CommandTag, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
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

// Run executes all pending migrations in version order. It is safe to call
// multiple times -- migrations already recorded in `schema_migrations` are
// skipped.
func (m *Migrator) Run(ctx context.Context) error {
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

		if _, err = m.db.Exec(ctx, migration.SQL); err != nil {
			return fmt.Errorf("migration %s failed: %w", migration.Filename, err)
		}

		if _, err = m.db.Exec(ctx,
			"INSERT INTO schema_migrations (version, filename) VALUES ($1, $2)",
			migration.Version, migration.Filename,
		); err != nil {
			return fmt.Errorf("record migration %s: %w", migration.Filename, err)
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
