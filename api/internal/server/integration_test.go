package server_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/cookiejar"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/internal/config"
	"github.com/agentplayground/api/internal/handler"
	"github.com/agentplayground/api/internal/middleware"
	"github.com/agentplayground/api/internal/server"
	"github.com/agentplayground/api/pkg/migrate"
	apredis "github.com/agentplayground/api/pkg/redis"
)

// TestIntegration_FullFlow exercises the entire Plan 01-01 substrate end to
// end against real-ish infra: embedded-postgres + miniredis + the real Echo
// router. It proves that a single call to server.New yields a binary that:
//
//   - boots, runs migrations, and serves /healthz
//   - issues + validates session cookies via the dev auth flow
//   - rejects unauthenticated /api/me, accepts authenticated /api/me
//   - destroys sessions on /api/dev/logout
//
// It also exercises server.New with WithDevAuth, demonstrating that the
// functional-options pattern composes correctly. Plan 01-05 will add a sister
// test that calls server.New with both WithDevAuth and WithWorkers to prove
// the pattern still composes.
func TestIntegration_FullFlow(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping integration test in -short mode")
	}

	// ----- Embedded Postgres ------------------------------------------------
	port := uint32(47000 + time.Now().UnixNano()%1000)
	tmpDir, err := os.MkdirTemp("", "ap-integration-*")
	require.NoError(t, err)
	t.Cleanup(func() { _ = os.RemoveAll(tmpDir) })

	pg := embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Username("postgres").
			Password("postgres").
			Database("ap_int").
			Port(port).
			RuntimePath(filepath.Join(tmpDir, "runtime")).
			DataPath(filepath.Join(tmpDir, "data")).
			BinariesPath(filepath.Join(tmpDir, "bin")).
			StartTimeout(60*time.Second),
	)
	require.NoError(t, pg.Start())
	t.Cleanup(func() { _ = pg.Stop() })

	dsn := fmt.Sprintf("postgres://postgres:postgres@localhost:%d/ap_int?sslmode=disable", port)

	// ----- Miniredis --------------------------------------------------------
	mr := miniredis.RunT(t)
	redisURL := "redis://" + mr.Addr()

	// ----- Config -- dev mode on so /api/dev/login is mounted ---------------
	cfg := &config.Config{
		APIPort:           "0",
		DatabaseURL:       dsn,
		RedisURL:          redisURL,
		LogLevel:          "info",
		DevMode:           true,
		SessionSecret:     "test-secret-that-is-at-least-32-characters-long",
		TemporalHost:      "localhost:7233",
		TemporalNamespace: "default",
	}

	logger := zerolog.Nop()
	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	// ----- Pool + Migrations ------------------------------------------------
	pool, err := pgxpool.New(ctx, dsn)
	require.NoError(t, err)
	require.NoError(t, pool.Ping(ctx))
	t.Cleanup(pool.Close)

	require.NoError(t, migrate.New(pool, logger, migrate.EmbeddedMigrations()).Run(ctx))

	// ----- Redis client (real go-redis against miniredis) -------------------
	rdb, err := apredis.New(ctx, redisURL, logger)
	require.NoError(t, err)
	t.Cleanup(func() { _ = rdb.Close() })

	// ----- Health checker -- same wiring path as cmd/server/main.go --------
	checker := handler.NewInfraChecker(&pgPinger{pool: pool}, rdb)

	// ----- Dev auth wiring --------------------------------------------------
	store := handler.NewDevSessionStore(pool)
	devAuth := handler.NewDevAuthHandler(pool, store, []byte(cfg.SessionSecret), cfg.DevMode)

	// ----- Server with WithDevAuth -- proves functional options compose ----
	srv := server.New(cfg, logger, checker, server.WithDevAuth(devAuth, store))

	// ----- httptest harness wraps the Echo handler -------------------------
	ts := httptest.NewServer(srv.Echo)
	t.Cleanup(ts.Close)

	jar, err := cookiejar.New(nil)
	require.NoError(t, err)
	client := ts.Client()
	client.Jar = jar

	tsURL, err := url.Parse(ts.URL)
	require.NoError(t, err)

	// ====== /healthz returns 200 healthy ====================================
	resp, err := client.Get(ts.URL + "/healthz")
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var health map[string]any
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&health))
	_ = resp.Body.Close()
	require.Equal(t, "healthy", health["status"])
	checks, ok := health["checks"].(map[string]any)
	require.True(t, ok)
	require.Equal(t, "healthy", checks["database"])
	require.Equal(t, "healthy", checks["redis"])

	// ====== /api/me without cookie -> 401 ===================================
	resp, err = client.Get(ts.URL + "/api/me")
	require.NoError(t, err)
	require.Equal(t, http.StatusUnauthorized, resp.StatusCode)
	_ = resp.Body.Close()

	// ====== /api/dev/login sets cookie ======================================
	resp, err = client.Post(ts.URL+"/api/dev/login", "application/json",
		strings.NewReader(`{"email":"int@test","display_name":"Integration"}`))
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	_ = resp.Body.Close()

	// Confirm the cookie made it into the jar.
	var session *http.Cookie
	for _, c := range jar.Cookies(tsURL) {
		if c.Name == middleware.CookieName {
			session = c
		}
	}
	require.NotNil(t, session, "session cookie %q must be set after login", middleware.CookieName)

	// ====== /api/me with cookie -> 200 + user payload =======================
	resp, err = client.Get(ts.URL + "/api/me")
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	var me map[string]any
	require.NoError(t, json.NewDecoder(resp.Body).Decode(&me))
	_ = resp.Body.Close()
	require.NotEmpty(t, me["id"])
	require.Equal(t, "Integration", me["display_name"])

	// ====== /api/dev/logout destroys session, /api/me back to 401 ==========
	req, err := http.NewRequest(http.MethodPost, ts.URL+"/api/dev/logout", nil)
	require.NoError(t, err)
	resp, err = client.Do(req)
	require.NoError(t, err)
	require.Equal(t, http.StatusOK, resp.StatusCode)
	_ = resp.Body.Close()

	resp, err = client.Get(ts.URL + "/api/me")
	require.NoError(t, err)
	require.Equal(t, http.StatusUnauthorized, resp.StatusCode)
	_ = resp.Body.Close()

	// ====== Schema verification: all four tables exist =====================
	var count int
	err = pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM information_schema.tables
		WHERE table_schema = 'public'
		  AND table_name IN ('users', 'user_sessions', 'agents', 'schema_migrations')
	`).Scan(&count)
	require.NoError(t, err)
	require.Equal(t, 4, count, "all baseline tables must exist after migrations")
}

// TestIntegration_NoOptionsWiring proves server.New(cfg, logger, checker) with
// zero options still compiles and yields a working /healthz responder. This is
// the functional-options backward-compatibility guarantee documented on
// server.New: future plans add options without breaking older callers.
func TestIntegration_NoOptionsWiring(t *testing.T) {
	cfg := &config.Config{
		APIPort:           "0",
		DatabaseURL:       "postgres://unused",
		RedisURL:          "redis://unused",
		LogLevel:          "info",
		DevMode:           false,
		TemporalHost:      "localhost:7233",
		TemporalNamespace: "default",
	}
	logger := zerolog.Nop()

	// Stub checker -- we're proving wiring, not infra.
	srv := server.New(cfg, logger, stubChecker{})
	require.NotNil(t, srv)
	require.NotNil(t, srv.Echo)

	ts := httptest.NewServer(srv.Echo)
	defer ts.Close()

	resp, err := http.Get(ts.URL + "/healthz")
	require.NoError(t, err)
	defer resp.Body.Close()
	require.Equal(t, http.StatusOK, resp.StatusCode)

	// /api/me must NOT exist when WithDevAuth was not supplied.
	resp2, err := http.Get(ts.URL + "/api/me")
	require.NoError(t, err)
	defer resp2.Body.Close()
	require.Equal(t, http.StatusNotFound, resp2.StatusCode)
}

// pgPinger adapts a *pgxpool.Pool to the handler.DBPinger interface used by
// InfraChecker. We use a thin wrapper here to avoid pulling pkg/database into
// the test (the test would then need its own DB struct just to ping).
type pgPinger struct{ pool *pgxpool.Pool }

func (p *pgPinger) Ping(ctx context.Context) error { return p.pool.Ping(ctx) }

// stubChecker is the world's smallest healthy infra: both pings always succeed.
// Used only by TestIntegration_NoOptionsWiring.
type stubChecker struct{}

func (stubChecker) PingDB(_ context.Context) error    { return nil }
func (stubChecker) PingRedis(_ context.Context) error { return nil }

// Compile-time assertion that DevSessionStore satisfies the SessionProvider
// interface. If this ever stops compiling, we have a Phase 3 swap problem.
var _ middleware.SessionProvider = (*handler.DevSessionStore)(nil)
