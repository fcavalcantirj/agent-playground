package migrate_test

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/pkg/migrate"
)

// startEmbeddedPostgres boots an embedded-postgres on a free port for the
// duration of the test. The returned pool is ready for queries; the cleanup
// closes the pool and stops postgres.
func startEmbeddedPostgres(t *testing.T) *pgxpool.Pool {
	t.Helper()

	port := uint32(45433 + time.Now().UnixNano()%1000)
	tmpDir, err := os.MkdirTemp("", "ap-migrate-test-*")
	require.NoError(t, err)
	t.Cleanup(func() { _ = os.RemoveAll(tmpDir) })

	pg := embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Username("postgres").
			Password("postgres").
			Database("ap_test").
			Port(port).
			RuntimePath(filepath.Join(tmpDir, "runtime")).
			DataPath(filepath.Join(tmpDir, "data")).
			BinariesPath(filepath.Join(tmpDir, "bin")).
			StartTimeout(60*time.Second),
	)
	require.NoError(t, pg.Start(), "embedded postgres start")
	t.Cleanup(func() { _ = pg.Stop() })

	dsn := fmt.Sprintf("postgres://postgres:postgres@localhost:%d/ap_test?sslmode=disable", port)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	pool, err := pgxpool.New(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	require.NoError(t, pool.Ping(ctx))
	return pool
}

func TestMigrator_AppliesBaseline(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping embedded-postgres test in -short mode")
	}

	pool := startEmbeddedPostgres(t)
	ctx := context.Background()
	logger := zerolog.Nop()

	m := migrate.New(pool, logger, migrate.EmbeddedMigrations())
	require.NoError(t, m.Run(ctx), "first run should apply baseline")

	// All three tables should exist.
	for _, table := range []string{"users", "user_sessions", "agents", "schema_migrations"} {
		var exists bool
		err := pool.QueryRow(ctx, `
			SELECT EXISTS (
				SELECT 1 FROM information_schema.tables
				WHERE table_schema = 'public' AND table_name = $1
			)
		`, table).Scan(&exists)
		require.NoError(t, err, "query for %s", table)
		require.True(t, exists, "table %s should exist after migration", table)
	}

	// The partial unique index on agents must exist (D-17).
	var indexExists bool
	err := pool.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM pg_indexes
			WHERE schemaname = 'public' AND indexname = 'idx_agents_one_active_per_user'
		)
	`).Scan(&indexExists)
	require.NoError(t, err)
	require.True(t, indexExists, "partial unique index on agents must exist")
}

func TestMigrator_Idempotent(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping embedded-postgres test in -short mode")
	}

	pool := startEmbeddedPostgres(t)
	ctx := context.Background()
	logger := zerolog.Nop()

	m := migrate.New(pool, logger, migrate.EmbeddedMigrations())
	require.NoError(t, m.Run(ctx))
	require.NoError(t, m.Run(ctx), "second run must be a no-op")
	require.NoError(t, m.Run(ctx), "third run must be a no-op")

	var count int
	require.NoError(t, pool.QueryRow(ctx, "SELECT COUNT(*) FROM schema_migrations").Scan(&count))
	require.Equal(t, 1, count, "exactly one migration row should be recorded")
}
