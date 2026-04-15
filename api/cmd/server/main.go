// Command server is the Agent Playground API entry point.
//
// Plan 01-01 Task 1 wiring:
//   - Load config from environment
//   - Init zerolog
//   - Open Postgres pool via pkg/database
//   - Open Redis client via pkg/redis
//   - Run embedded migrations via pkg/migrate
//   - Build server via internal/server.New (functional options pattern)
//   - Start Echo, wait for SIGINT/SIGTERM, shut down gracefully
//
// Plan 01-01 Task 2 wires DevAuthHandler + SessionProvider through
// server.WithDevAuth(...) without changing the Task 1 wiring shape.
//
// Plan 01-05 Task 2 wires Temporal workers via server.WithWorkers(...) --
// still no change to the server.New signature. When TEMPORAL_HOST is empty
// the Temporal block is skipped entirely so `go run` against a laptop with
// no Temporal server keeps working.
package main

import (
	"context"
	"io"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/rs/zerolog"

	"github.com/agentplayground/api/internal/config"
	"github.com/agentplayground/api/internal/handler"
	"github.com/agentplayground/api/internal/logging"
	"github.com/agentplayground/api/internal/recipes"
	"github.com/agentplayground/api/internal/server"
	"github.com/agentplayground/api/internal/session"
	"github.com/agentplayground/api/internal/session/bridge"
	apitemporal "github.com/agentplayground/api/internal/temporal"
	"github.com/agentplayground/api/pkg/database"
	"github.com/agentplayground/api/pkg/docker"
	"github.com/agentplayground/api/pkg/migrate"
	apredis "github.com/agentplayground/api/pkg/redis"
)

func main() {
	logger := newLogger("info")

	cfg, err := config.Load()
	if err != nil {
		logger.Fatal().Err(err).Msg("config load failed")
	}
	logger = newLogger(cfg.LogLevel)

	// Phase 02.5 Plan 05: wrap stdout with the secret-redaction writer
	// BEFORE any subsystem that may accidentally log a BYOK key logs
	// a single byte. This is defence in depth — the handler code path
	// is still required to never log resolved secrets, but the writer
	// wrap guarantees that accidental logs are scrubbed.
	redactedStdout := logging.InstallRedactionHook(os.Stdout)
	logger = newLoggerTo(cfg.LogLevel, redactedStdout)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Postgres
	db, err := database.New(ctx, cfg.DatabaseURL, logger)
	if err != nil {
		logger.Fatal().Err(err).Msg("database open failed")
	}
	defer db.Close()

	// Redis
	rdb, err := apredis.New(ctx, cfg.RedisURL, logger)
	if err != nil {
		logger.Fatal().Err(err).Msg("redis open failed")
	}
	defer func() { _ = rdb.Close() }()

	// Migrations -- idempotent on every boot.
	if err := migrate.Run(ctx, db.Pool, logger); err != nil {
		logger.Fatal().Err(err).Msg("migrate run failed")
	}

	// Temporal workers (optional). When TEMPORAL_HOST is empty we skip the
	// dial entirely so `go run ./cmd/server` against a laptop without a
	// Temporal server still starts and serves /healthz. When set, we build
	// three workers (session/billing/reconciliation), start their pollers,
	// and hand them to the server via the WithWorkers functional option so
	// Shutdown can Stop them. The Server.Workers field stays nil when the
	// option is not supplied, matching Plan 01-01's TestIntegration_NoOptionsWiring
	// contract.
	var workerOpt server.Option
	var temporalWorkers *apitemporal.Workers
	if cfg.TemporalHost != "" {
		w, err := apitemporal.NewWorkers(cfg.TemporalHost, cfg.TemporalNamespace, logger)
		if err != nil {
			logger.Fatal().Err(err).Msg("failed to create temporal workers")
		}
		if err := w.Start(); err != nil {
			logger.Fatal().Err(err).Msg("failed to start temporal workers")
		}
		logger.Info().
			Str("host", cfg.TemporalHost).
			Str("namespace", cfg.TemporalNamespace).
			Msg("temporal workers started")
		temporalWorkers = w
		workerOpt = server.WithWorkers(w)
	} else {
		logger.Warn().Msg("TEMPORAL_HOST empty, skipping temporal worker startup")
	}

	// Server -- functional options pattern. Task 1 booted with zero options;
	// Plan 01-01 Task 2 wires the dev cookie auth via WithDevAuth(...). Plan
	// 01-05 adds WithWorkers(...) for Temporal. Plan 01-01's
	// TestIntegration_NoOptionsWiring contract still holds: any of these
	// options can be omitted and server.New continues to compile and run.
	checker := handler.NewInfraChecker(db, rdb)
	sessionCookieStore := handler.NewDevSessionStore(db.Pool)
	devAuth := handler.NewDevAuthHandler(db.Pool, sessionCookieStore, []byte(cfg.SessionSecret), cfg.DevMode)
	opts := []server.Option{server.WithDevAuth(devAuth, sessionCookieStore)}
	if workerOpt != nil {
		opts = append(opts, workerOpt)
	}

	// Phase 02.5 Plan 01/05: wire the YAML-backed recipe loader and the
	// dev secret source onto the server via functional options. The
	// loader scans agents/ at startup, validates each recipe against
	// the embedded schema, and starts a SIGHUP watcher so operators
	// can reload recipes without a restart. The template registry
	// (Plan 02) is injected as an interface so Plan 05 tests compile
	// without a hard dependency on the parallel wave-2 deliverable.
	validator, vErr := recipes.NewSchemaValidator()
	if vErr != nil {
		logger.Fatal().Err(vErr).Msg("recipe schema compile failed")
	}
	recipeLoader := recipes.NewLoader("agents/", validator, logger)
	if lErr := recipeLoader.LoadAll(ctx); lErr != nil {
		logger.Warn().Err(lErr).Msg("recipe LoadAll failed; continuing with empty catalog")
	}
	recipes.StartSIGHUPWatcher(ctx, recipeLoader, logger)
	templateRegistry := recipes.NewTemplateRegistry("agents/")
	secretSource := session.NewDevEnvSecretSource()
	opts = append(opts,
		server.WithRecipeLoader(recipeLoader),
		server.WithTemplateRegistry(templateRegistry),
		server.WithSecretSource(secretSource),
	)

	// Plan 02-05: wire the session HTTP handler. The Docker runner is
	// optional — if NewRunner fails (no Docker daemon available, e.g.
	// CI or a dev box without Docker) we skip session wiring and log a
	// warning, matching the same "missing-infra degrades gracefully"
	// pattern the Temporal block uses above.
	runner, runnerErr := docker.NewRunner(logger)
	if runnerErr != nil {
		logger.Warn().Err(runnerErr).Msg("docker runner unavailable, session routes disabled")
	} else {
		sessStore := session.NewStore(db.Pool)
		// Phase 02.5 Plan 09: BridgeRegistry replaces the legacy
		// session.Bridge shim. The session handler dispatches on
		// recipe.ChatIO.Mode through this registry directly.
		bridgeReg := bridge.NewBridgeRegistry(runner, logger)
		sessHandler := session.NewHandler(
			sessStore,
			runner,
			recipeLoader,
			secretSource,
			templateRegistry,
			bridgeReg,
			logger,
		)
		opts = append(opts, server.WithSessionHandler(sessHandler))
	}

	srv := server.New(cfg, logger, checker, opts...)

	// Run Echo in a goroutine so we can listen for shutdown signals.
	go func() {
		if err := srv.Start(); err != nil {
			logger.Fatal().Err(err).Msg("server start failed")
		}
	}()

	// Wait for SIGINT/SIGTERM, then drain.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
	<-sigCh
	logger.Info().Msg("shutdown signal received")

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer shutdownCancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		logger.Error().Err(err).Msg("server shutdown error")
	}

	// Drain Temporal workers after Echo has stopped accepting new requests.
	// Stopping before Echo.Shutdown could kill in-flight workflow callers;
	// stopping after is the safer order. We use the concrete type (not
	// srv.Workers) so Stop is deterministic even if the server struct is
	// garbage-collected out from under us.
	if temporalWorkers != nil {
		temporalWorkers.Stop()
	}
}

// newLogger configures a JSON zerolog writer at the requested level. Defaults
// to info when the level is unrecognized.
func newLogger(level string) zerolog.Logger {
	return newLoggerTo(level, os.Stdout)
}

// newLoggerTo is the same as newLogger but writes to an explicit
// io.Writer sink. Phase 02.5 Plan 05 uses this to install the
// secret-redaction writer wrap around os.Stdout before any subsystem
// emits a single log line.
func newLoggerTo(level string, w io.Writer) zerolog.Logger {
	lvl, err := zerolog.ParseLevel(level)
	if err != nil || level == "" {
		lvl = zerolog.InfoLevel
	}
	return zerolog.New(w).
		Level(lvl).
		With().
		Timestamp().
		Str("svc", "ap-api").
		Logger()
}
