package handler_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/labstack/echo/v4"
	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/internal/handler"
)

// fakeChecker is a stub HealthChecker that returns whatever errors the test
// configures. No real infra dependency.
type fakeChecker struct {
	dbErr    error
	redisErr error
}

func (f fakeChecker) PingDB(_ context.Context) error    { return f.dbErr }
func (f fakeChecker) PingRedis(_ context.Context) error { return f.redisErr }

func newRequest(t *testing.T, h *handler.HealthHandler) (*httptest.ResponseRecorder, handler.HealthResponse) {
	t.Helper()
	e := echo.New()
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	rec := httptest.NewRecorder()
	c := e.NewContext(req, rec)

	require.NoError(t, h.Health(c))

	var body handler.HealthResponse
	require.NoError(t, json.NewDecoder(rec.Body).Decode(&body))
	return rec, body
}

func TestHealth_AllHealthy(t *testing.T) {
	h := handler.NewHealthHandler(fakeChecker{})
	rec, body := newRequest(t, h)

	require.Equal(t, http.StatusOK, rec.Code)
	require.Equal(t, "healthy", body.Status)
	require.Equal(t, "healthy", body.Checks["database"])
	require.Equal(t, "healthy", body.Checks["redis"])
	require.NotEmpty(t, body.Uptime)
}

func TestHealth_DBDown(t *testing.T) {
	h := handler.NewHealthHandler(fakeChecker{dbErr: errors.New("connection refused")})
	rec, body := newRequest(t, h)

	require.Equal(t, http.StatusServiceUnavailable, rec.Code)
	require.Equal(t, "unhealthy", body.Status)
	require.True(t, strings.HasPrefix(body.Checks["database"], "unhealthy"))
	require.Equal(t, "healthy", body.Checks["redis"])
}

func TestHealth_RedisDown(t *testing.T) {
	h := handler.NewHealthHandler(fakeChecker{redisErr: errors.New("EOF")})
	rec, body := newRequest(t, h)

	require.Equal(t, http.StatusServiceUnavailable, rec.Code)
	require.Equal(t, "unhealthy", body.Status)
	require.Equal(t, "healthy", body.Checks["database"])
	require.True(t, strings.HasPrefix(body.Checks["redis"], "unhealthy"))
}
