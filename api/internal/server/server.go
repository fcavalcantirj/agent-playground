// Package server wires the Echo HTTP server, middleware, and route table.
//
// Mirrors MSV's `internal/server/server.go` but adds a functional-options
// constructor so later plans (Plan 01-05's Temporal workers, Plan 02's recipe
// service, etc.) can extend the Server without breaking existing callers.
package server

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/labstack/echo/v4"
	echomw "github.com/labstack/echo/v4/middleware"
	"github.com/rs/zerolog"

	"github.com/agentplayground/api/internal/config"
	"github.com/agentplayground/api/internal/handler"
	"github.com/agentplayground/api/internal/middleware"
)

// Workers is the minimal interface that Plan 01-05 (Temporal worker) and any
// other long-lived background subsystem must satisfy if it wants to be hung
// off the Server. Defined here to keep this package free of a Temporal import.
type Workers interface {
	Start() error
	Stop()
}

// Option configures the Server. Use functional options to extend server.New
// without breaking existing callers -- Plan 01-05 will add WithWorkers, future
// plans can add more without touching Plan 01-01 callers.
type Option func(*Server)

// Server bundles the Echo instance with its dependencies. Fields are exported
// so options can mutate them without ceremony.
type Server struct {
	Echo    *echo.Echo
	Config  *config.Config
	Logger  zerolog.Logger
	Workers Workers // nil until Plan 01-05 wires Temporal via WithWorkers

	// devAuth is set by WithDevAuth and consumed during route registration.
	// nil means no dev auth routes are mounted (e.g. tests that only exercise
	// /healthz).
	devAuth         *handler.DevAuthHandler
	sessionProvider middleware.SessionProvider
}

// WithWorkers attaches a background worker subsystem to the Server. Plan 01-05
// will pass a Temporal worker bundle here. Plan 01-01 callers ignore it.
func WithWorkers(w Workers) Option {
	return func(s *Server) { s.Workers = w }
}

// WithDevAuth mounts the dev cookie auth routes (/api/dev/login,
// /api/dev/logout, /api/me) and applies AuthMiddleware to the protected /api
// group. The provider is what AuthMiddleware uses to validate session cookies;
// the handler is what serves the routes. Plan 01-01 Task 2 wires this option.
//
// Phase 3 will replace the option with WithGoth(...) backed by the same
// SessionProvider interface -- callers stay unchanged.
func WithDevAuth(h *handler.DevAuthHandler, provider middleware.SessionProvider) Option {
	return func(s *Server) {
		s.devAuth = h
		s.sessionProvider = provider
	}
}

// New constructs the Server. Required arguments cover what every Phase 1
// caller needs: config, logger, and the health checker. Anything else
// (auth, workers, future subsystems) flows through `opts ...Option`.
//
// Task 2 of Plan 01-01 extends this constructor with WithDevAuth(...), which
// mounts /api/dev/login, /api/dev/logout, and /api/me. Test callers that only
// exercise /healthz can still call server.New(cfg, logger, checker) with zero
// options -- proving the functional-options pattern is backward-compatible.
func New(
	cfg *config.Config,
	logger zerolog.Logger,
	checker handler.HealthChecker,
	opts ...Option,
) *Server {
	e := echo.New()
	e.HideBanner = true
	e.HidePort = true

	e.Use(echomw.Recover())
	e.Use(echomw.RequestID())
	e.Use(zerologRequestLogger(logger))

	// Health endpoint -- unauthenticated by design (load balancers must hit it).
	healthHandler := handler.NewHealthHandler(checker)
	e.GET("/healthz", healthHandler.Health)

	s := &Server{
		Echo:   e,
		Config: cfg,
		Logger: logger,
	}
	for _, opt := range opts {
		opt(s)
	}

	// /api group hosts JSON endpoints. Dev auth routes mount unprotected;
	// /api/me sits behind AuthMiddleware. Both are gated on WithDevAuth being
	// supplied -- Task 1 callers (zero options) skip this entire block.
	api := e.Group("/api")
	if s.devAuth != nil && s.sessionProvider != nil {
		api.POST("/dev/login", s.devAuth.Login)
		api.POST("/dev/logout", s.devAuth.Logout)

		authed := api.Group("",
			middleware.AuthMiddleware(s.sessionProvider, []byte(cfg.SessionSecret)),
		)
		authed.GET("/me", s.devAuth.Me)
	}

	return s
}

// Start binds the HTTP listener. It blocks until the server stops.
func (s *Server) Start() error {
	addr := fmt.Sprintf(":%s", s.Config.APIPort)
	s.Logger.Info().Str("addr", addr).Msg("starting server")
	if err := s.Echo.Start(addr); err != nil && err != http.ErrServerClosed {
		return err
	}
	return nil
}

// Shutdown gracefully stops the HTTP listener within 10s.
func (s *Server) Shutdown(ctx context.Context) error {
	s.Logger.Info().Msg("shutting down server")
	shutdownCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	return s.Echo.Shutdown(shutdownCtx)
}

// zerologRequestLogger emits one structured log line per HTTP request. Mirrors
// the request logging shape MSV uses so log pipelines can be shared.
func zerologRequestLogger(logger zerolog.Logger) echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			start := time.Now()
			err := next(c)
			req := c.Request()
			res := c.Response()
			logger.Info().
				Str("method", req.Method).
				Str("path", req.URL.Path).
				Int("status", res.Status).
				Dur("dur", time.Since(start)).
				Str("request_id", res.Header().Get(echo.HeaderXRequestID)).
				Msg("http request")
			return err
		}
	}
}
