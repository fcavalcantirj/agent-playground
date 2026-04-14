//go:build integration

// Integration tests for session.Store against a real Postgres (embedded).
//
// These tests verify the one-active-session-per-user invariant that Plan 04
// encodes via the partial unique index `idx_sessions_one_active_per_user`
// on (user_id) WHERE status IN ('pending', 'provisioning', 'running').
//
// Gated behind the `integration` build tag so the default `go test ./...`
// run in CI/dev does not spin up embedded-postgres. Run with:
//
//	cd api && go test -tags=integration ./internal/session/ -count=1 -run TestSessionLifecycle
//
// The embedded-postgres helper mirrors api/pkg/migrate/migrate_test.go —
// OS-assigned port, tmpfs runtime/data/binaries dirs, cleanup on test exit.

package session_test

import (
	"context"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/internal/session"
	"github.com/agentplayground/api/pkg/migrate"
)

// startEmbeddedPostgres spins up an embedded-postgres on a free ephemeral
// port, applies the embedded SQL migrations, and returns a ready pgxpool.
// The t.Cleanup chain tears the postgres down at test end.
//
// Ported from pkg/migrate/migrate_test.go — keep in sync if that helper
// changes. Intentionally NOT extracted into a shared testutil package yet
// because Phase 2 only has one integration-test file; extraction belongs
// in Phase 5 when reconciliation + workflow tests also need it.
func startEmbeddedPostgres(t *testing.T) *pgxpool.Pool {
	t.Helper()

	// Grab a free port, close the listener, then hand the number to
	// embedded-postgres before anything else can claim it. Matches
	// migrate_test.go's approach to avoid parallel-test port collisions.
	l, err := net.Listen("tcp", "127.0.0.1:0")
	require.NoError(t, err)
	port := uint32(l.Addr().(*net.TCPAddr).Port)
	require.NoError(t, l.Close())

	tmpDir, err := os.MkdirTemp("", "ap-session-integration-*")
	require.NoError(t, err)
	t.Cleanup(func() { _ = os.RemoveAll(tmpDir) })

	pg := embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Username("postgres").
			Password("postgres").
			Database("ap_session_test").
			Port(port).
			RuntimePath(filepath.Join(tmpDir, "runtime")).
			DataPath(filepath.Join(tmpDir, "data")).
			BinariesPath(filepath.Join(tmpDir, "bin")).
			StartTimeout(60 * time.Second),
	)
	require.NoError(t, pg.Start(), "embedded postgres start")
	t.Cleanup(func() { _ = pg.Stop() })

	dsn := fmt.Sprintf("postgres://postgres:postgres@localhost:%d/ap_session_test?sslmode=disable", port)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	pool, err := pgxpool.New(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)
	require.NoError(t, pool.Ping(ctx))

	// Run the embedded migrations so sessions + users tables exist.
	logger := zerolog.Nop()
	require.NoError(t, migrate.Run(ctx, pool, logger), "migrate.Run")

	return pool
}

// mustCreateUser inserts a row into users so the sessions.user_id FK is
// satisfied. 001_baseline.sql declares provider / provider_sub / email as
// nullable, so we pass a minimal shape keyed by a fresh UUID. Returning
// the uuid lets the caller use it as Store.Create's userID.
func mustCreateUser(t *testing.T, pool *pgxpool.Pool) uuid.UUID {
	t.Helper()
	id := uuid.New()
	_, err := pool.Exec(
		context.Background(),
		`INSERT INTO users (id, provider, provider_sub, email)
		 VALUES ($1, 'integration-test', $2, $3)`,
		id, id.String(), id.String()+"@example.test",
	)
	require.NoError(t, err)
	return id
}

// TestSessionLifecycle_OneActivePerUser verifies that a second Create
// against the same user returns session.ErrConflictActive while the
// first session's status is still in the "active" set (pending by
// default). This exercises the partial unique index from 002_sessions.sql.
func TestSessionLifecycle_OneActivePerUser(t *testing.T) {
	pool := startEmbeddedPostgres(t)
	store := session.NewStore(pool)
	ctx := context.Background()

	user := mustCreateUser(t, pool)

	s1, err := store.Create(ctx, user, "picoclaw", "anthropic", "claude-sonnet-4-5")
	require.NoError(t, err, "first Create must succeed")
	require.NotNil(t, s1)
	require.Equal(t, session.StatusPending, s1.Status)

	_, err = store.Create(ctx, user, "picoclaw", "anthropic", "claude-sonnet-4-5")
	require.Error(t, err, "second Create must fail while the first is active")
	require.ErrorIs(t, err, session.ErrConflictActive,
		"partial unique index should translate to ErrConflictActive")
}

// TestSessionLifecycle_AfterStopAllowsNew verifies that transitioning the
// first session to 'stopped' clears the partial unique index and allows
// a subsequent Create for the same user to succeed.
func TestSessionLifecycle_AfterStopAllowsNew(t *testing.T) {
	pool := startEmbeddedPostgres(t)
	store := session.NewStore(pool)
	ctx := context.Background()

	user := mustCreateUser(t, pool)

	s1, err := store.Create(ctx, user, "picoclaw", "anthropic", "claude-sonnet-4-5")
	require.NoError(t, err)

	require.NoError(t, store.UpdateStatus(ctx, s1.ID, session.StatusStopped),
		"transition to stopped must succeed")

	s2, err := store.Create(ctx, user, "hermes", "anthropic", "claude-sonnet-4-5")
	require.NoError(t, err,
		"after the first session is stopped, a new Create must succeed")
	require.NotEqual(t, s1.ID, s2.ID, "second session gets a fresh id")
	require.Equal(t, "hermes", s2.RecipeName)
}

// TestSessionLifecycle_DistinctUsersConcurrent verifies the partial
// unique index is keyed on user_id and does NOT fire across distinct
// users. Two users each get one active session simultaneously.
func TestSessionLifecycle_DistinctUsersConcurrent(t *testing.T) {
	pool := startEmbeddedPostgres(t)
	store := session.NewStore(pool)
	ctx := context.Background()

	u1 := mustCreateUser(t, pool)
	u2 := mustCreateUser(t, pool)

	_, err := store.Create(ctx, u1, "picoclaw", "anthropic", "claude-sonnet-4-5")
	require.NoError(t, err, "user 1 first Create")

	_, err = store.Create(ctx, u2, "picoclaw", "anthropic", "claude-sonnet-4-5")
	if errors.Is(err, session.ErrConflictActive) {
		t.Fatal("partial unique index incorrectly fired across distinct users")
	}
	require.NoError(t, err, "user 2 first Create must succeed independently")
}
