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
// Plan 01-01 Task 2 will wire DevAuthHandler + SessionProvider through
// server.WithDevAuth(...) without changing the Task 1 wiring shape.
package main

import (
	"context"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/rs/zerolog"

	"github.com/agentplayground/api/internal/config"
	"github.com/agentplayground/api/internal/handler"
	"github.com/agentplayground/api/internal/server"
	"github.com/agentplayground/api/pkg/database"
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

	// Server -- functional options pattern. Task 1 booted with zero options;
	// Task 2 wires the dev cookie auth via WithDevAuth(...). Plan 01-05 will
	// add WithWorkers(...) for Temporal without touching this call.
	checker := handler.NewInfraChecker(db, rdb)
	sessionStore := handler.NewDevSessionStore(db.Pool)
	devAuth := handler.NewDevAuthHandler(db.Pool, sessionStore, []byte(cfg.SessionSecret), cfg.DevMode)
	srv := server.New(cfg, logger, checker,
		server.WithDevAuth(devAuth, sessionStore),
	)

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
}

// newLogger configures a JSON zerolog writer at the requested level. Defaults
// to info when the level is unrecognized.
func newLogger(level string) zerolog.Logger {
	lvl, err := zerolog.ParseLevel(level)
	if err != nil || level == "" {
		lvl = zerolog.InfoLevel
	}
	return zerolog.New(os.Stdout).
		Level(lvl).
		With().
		Timestamp().
		Str("svc", "ap-api").
		Logger()
}
