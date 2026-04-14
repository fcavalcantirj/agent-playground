package handler_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/labstack/echo/v4"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/internal/handler"
	"github.com/agentplayground/api/internal/middleware"
	"github.com/agentplayground/api/pkg/migrate"
)

// startTestPostgres boots embedded-postgres, applies migrations, and returns
// a ready-to-use pool. Cleanup is registered with t.Cleanup.
func startTestPostgres(t *testing.T) *pgxpool.Pool {
	t.Helper()

	port := uint32(46500 + time.Now().UnixNano()%1000)
	tmpDir, err := os.MkdirTemp("", "ap-devauth-test-*")
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
	require.NoError(t, pg.Start())
	t.Cleanup(func() { _ = pg.Stop() })

	dsn := fmt.Sprintf("postgres://postgres:postgres@localhost:%d/ap_test?sslmode=disable", port)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	pool, err := pgxpool.New(ctx, dsn)
	require.NoError(t, pool.Ping(ctx))
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	logger := zerolog.Nop()
	require.NoError(t, migrate.New(pool, logger, migrate.EmbeddedMigrations()).Run(ctx))
	return pool
}

func newTestHandler(t *testing.T, devMode bool) (*handler.DevAuthHandler, *pgxpool.Pool, []byte) {
	t.Helper()
	pool := startTestPostgres(t)
	store := handler.NewDevSessionStore(pool)
	secret := []byte("test-secret-needs-32-characters!!")
	h := handler.NewDevAuthHandler(pool, store, secret, devMode)
	return h, pool, secret
}

func doRequest(t *testing.T, e *echo.Echo, method, path, body string, cookie *http.Cookie) *httptest.ResponseRecorder {
	t.Helper()
	var bodyReader *strings.Reader
	if body != "" {
		bodyReader = strings.NewReader(body)
	} else {
		bodyReader = strings.NewReader("")
	}
	req := httptest.NewRequest(method, path, bodyReader)
	req.Header.Set("Content-Type", "application/json")
	if cookie != nil {
		req.AddCookie(cookie)
	}
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)
	return rec
}

func TestDevAuth_LoginCreatesUserAndSession(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping embedded-postgres test in -short mode")
	}

	h, pool, secret := newTestHandler(t, true)
	e := echo.New()
	e.POST("/api/dev/login", h.Login)

	rec := doRequest(t, e, http.MethodPost, "/api/dev/login", `{"email":"alice@dev","display_name":"Alice"}`, nil)
	require.Equal(t, http.StatusOK, rec.Code)

	var resp map[string]string
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &resp))
	require.NotEmpty(t, resp["user_id"])
	require.Equal(t, "Alice", resp["display_name"])

	// Cookie present + signed.
	var sessionCookie *http.Cookie
	for _, c := range rec.Result().Cookies() {
		if c.Name == middleware.CookieName {
			sessionCookie = c
		}
	}
	require.NotNil(t, sessionCookie, "cookie %q must be set", middleware.CookieName)
	require.True(t, sessionCookie.HttpOnly)
	require.Contains(t, sessionCookie.Value, ".") // hmac.token format

	// User row exists.
	var count int
	require.NoError(t, pool.QueryRow(context.Background(),
		"SELECT COUNT(*) FROM users WHERE email = $1", "alice@dev").Scan(&count))
	require.Equal(t, 1, count)

	// Session row exists.
	var sessions int
	require.NoError(t, pool.QueryRow(context.Background(),
		"SELECT COUNT(*) FROM user_sessions").Scan(&sessions))
	require.Equal(t, 1, sessions)

	_ = secret // captured for follow-up tests
}

func TestDevAuth_LoginUpsertsExistingUser(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping embedded-postgres test in -short mode")
	}

	h, pool, _ := newTestHandler(t, true)
	e := echo.New()
	e.POST("/api/dev/login", h.Login)

	rec1 := doRequest(t, e, http.MethodPost, "/api/dev/login", `{"email":"a@b","display_name":"Bob"}`, nil)
	require.Equal(t, http.StatusOK, rec1.Code)
	rec2 := doRequest(t, e, http.MethodPost, "/api/dev/login", `{"email":"a@b","display_name":"Robert"}`, nil)
	require.Equal(t, http.StatusOK, rec2.Code)

	var users int
	require.NoError(t, pool.QueryRow(context.Background(),
		"SELECT COUNT(*) FROM users").Scan(&users))
	require.Equal(t, 1, users, "second login must upsert, not duplicate")

	// display_name should now be Robert (the upsert path updates it).
	var name string
	require.NoError(t, pool.QueryRow(context.Background(),
		"SELECT display_name FROM users LIMIT 1").Scan(&name))
	require.Equal(t, "Robert", name)
}

func TestDevAuth_LoginRejectedWhenDevModeOff(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping embedded-postgres test in -short mode")
	}

	h, _, _ := newTestHandler(t, false)
	e := echo.New()
	e.POST("/api/dev/login", h.Login)

	rec := doRequest(t, e, http.MethodPost, "/api/dev/login", "", nil)
	require.Equal(t, http.StatusNotFound, rec.Code)
}

func TestDevAuth_LogoutDestroysSession(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping embedded-postgres test in -short mode")
	}

	h, pool, _ := newTestHandler(t, true)
	e := echo.New()
	e.POST("/api/dev/login", h.Login)
	e.POST("/api/dev/logout", h.Logout)

	rec := doRequest(t, e, http.MethodPost, "/api/dev/login", "", nil)
	require.Equal(t, http.StatusOK, rec.Code)

	var sessionCookie *http.Cookie
	for _, c := range rec.Result().Cookies() {
		if c.Name == middleware.CookieName {
			sessionCookie = c
		}
	}
	require.NotNil(t, sessionCookie)

	// Logout with the cookie -> session row should be removed.
	rec2 := doRequest(t, e, http.MethodPost, "/api/dev/logout", "", sessionCookie)
	require.Equal(t, http.StatusOK, rec2.Code)

	var sessions int
	require.NoError(t, pool.QueryRow(context.Background(),
		"SELECT COUNT(*) FROM user_sessions").Scan(&sessions))
	require.Equal(t, 0, sessions)
}
