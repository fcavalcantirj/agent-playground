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
	"github.com/agentplayground/api/internal/recipes"
	"github.com/agentplayground/api/internal/session"
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

	// sessionHandler is set by WithSessionHandler and mounts the three
	// Plan 02-05 /api/sessions* routes on the authed group. nil means
	// session routes are skipped (Phase 1 tests, etc.).
	sessionHandler *session.Handler

	// Phase 02.5 Plan 05 wiring — injected via functional options and
	// consumed by the session handler (Plan 09 wires the handler call).
	// Plan 01-01 callers that omit these options get nil, which matches
	// the "missing-infra degrades gracefully" contract.
	recipeLoader     *recipes.Loader
	templateRegistry session.TemplateRenderer
	secretSource     session.SecretSource
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
		if len(s.Config.SessionSecret) < 32 {
			panic("WithDevAuth requires AP_SESSION_SECRET of at least 32 bytes")
		}
		s.devAuth = h
		s.sessionProvider = provider
	}
}

// WithSessionHandler mounts the Plan 02-05 session routes
// (POST /api/sessions, POST /api/sessions/:id/message, DELETE
// /api/sessions/:id) behind the existing auth middleware. Following
// the same functional-options shape as WithDevAuth / WithWorkers so
// Phase 1 callers that omit it continue to work unchanged.
//
// The handler is only wired if WithDevAuth (or its Phase 3 successor)
// is ALSO supplied — session routes require an authenticated group.
func WithSessionHandler(h *session.Handler) Option {
	return func(s *Server) { s.sessionHandler = h }
}

// WithRecipeLoader attaches the Phase 02.5 Plan 01 recipe loader to
// the Server. The session handler consumes this via Server.RecipeLoader
// when Plan 09 swaps the hardcoded catalog for the YAML-backed one.
// Plan 01-01 callers that omit this option get a nil loader and the
// handler falls back to its Phase 2 defaults.
func WithRecipeLoader(l *recipes.Loader) Option {
	return func(s *Server) { s.recipeLoader = l }
}

// WithTemplateRegistry attaches the Phase 02.5 Plan 02 template
// registry to the Server. The session handler consumes this via
// Server.TemplateRegistry in Plan 09's Materialize call. The option
// takes the TemplateRenderer interface (not *recipes.TemplateRegistry
// directly) so the session package can unit-test Materialize without
// the recipes package depending on session, and so Plan 02's concrete
// type lands in parallel without a merge conflict on this file.
func WithTemplateRegistry(t session.TemplateRenderer) Option {
	return func(s *Server) { s.templateRegistry = t }
}

// WithSecretSource attaches the Phase 02.5 Plan 05 SecretSource to
// the Server. The session handler uses this to resolve every
// `secret:<name>` reference in a recipe's auth block before launching
// the container. Phase 02.5 ships session.DevEnvSecretSource; Phase 3
// will replace it with a pgcrypto-backed source without touching
// server.go.
func WithSecretSource(src session.SecretSource) Option {
	return func(s *Server) { s.secretSource = src }
}

// RecipeLoader exposes the injected recipe loader for downstream
// handlers. Returns nil if WithRecipeLoader was not supplied.
func (s *Server) RecipeLoader() *recipes.Loader { return s.recipeLoader }

// TemplateRegistry exposes the injected template renderer for
// downstream handlers. Returns nil if WithTemplateRegistry was not
// supplied.
func (s *Server) TemplateRegistry() session.TemplateRenderer { return s.templateRegistry }

// SecretSource exposes the injected SecretSource for downstream
// handlers. Returns nil if WithSecretSource was not supplied.
func (s *Server) SecretSource() session.SecretSource { return s.secretSource }

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

		// Phase 02.5 Plan 09: public recipe catalog endpoints behind
		// the authed group. RegisterRecipesRoutes short-circuits if
		// s.recipeLoader is nil, so callers that omit WithRecipeLoader
		// (Phase 1 integration tests) are unaffected.
		handler.RegisterRecipesRoutes(authed, s.recipeLoader)

		// Plan 02-05: session routes behind the same authed group.
		// Skipped if WithSessionHandler was not passed.
		if s.sessionHandler != nil {
			s.sessionHandler.Register(authed)
		}
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

// Shutdown gracefully stops the HTTP listener. The caller is responsible for
// supplying a context with an appropriate deadline (main.go uses 15s). Keeping
// the policy in the caller avoids the misleading double-timeout that occurred
// when this function created its own 10s child context.
func (s *Server) Shutdown(ctx context.Context) error {
	s.Logger.Info().Msg("shutting down server")
	return s.Echo.Shutdown(ctx)
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
