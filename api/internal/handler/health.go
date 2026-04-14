package handler

import (
	"net/http"
	"time"

	"github.com/labstack/echo/v4"
)

// HealthHandler serves the /healthz endpoint. It depends on a HealthChecker so
// real infra (Postgres + Redis) can be swapped for a test double.
type HealthHandler struct {
	checker HealthChecker
}

// NewHealthHandler wires a HealthChecker into a HealthHandler.
func NewHealthHandler(checker HealthChecker) *HealthHandler {
	return &HealthHandler{checker: checker}
}

// HealthResponse is the JSON body returned by /healthz.
type HealthResponse struct {
	Status string            `json:"status"`
	Checks map[string]string `json:"checks"`
	Uptime string            `json:"uptime"`
}

// startTime records the boot moment so /healthz can report uptime.
var startTime = time.Now()

// Health pings the database and Redis, returning 200 when both succeed and
// 503 otherwise. The response body always lists per-component status, so a
// load balancer or human operator can see exactly what failed.
func (h *HealthHandler) Health(c echo.Context) error {
	ctx := c.Request().Context()

	checks := map[string]string{}
	allOK := true

	if err := h.checker.PingDB(ctx); err != nil {
		checks["database"] = "unhealthy: " + err.Error()
		allOK = false
	} else {
		checks["database"] = "healthy"
	}

	if err := h.checker.PingRedis(ctx); err != nil {
		checks["redis"] = "unhealthy: " + err.Error()
		allOK = false
	} else {
		checks["redis"] = "healthy"
	}

	status := "healthy"
	httpStatus := http.StatusOK
	if !allOK {
		status = "unhealthy"
		httpStatus = http.StatusServiceUnavailable
	}

	return c.JSON(httpStatus, HealthResponse{
		Status: status,
		Checks: checks,
		Uptime: time.Since(startTime).Truncate(time.Second).String(),
	})
}
