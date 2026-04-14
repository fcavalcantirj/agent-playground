// Package database wraps a pgxpool.Pool with structured logging.
//
// Mirrors MSV's `pkg/database/postgres.go` -- one connection pool, one Ping,
// one Close. Higher-level query helpers live in their respective handlers.
package database

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/rs/zerolog"
)

// DB is the shared Postgres handle used by every package in the API.
type DB struct {
	Pool   *pgxpool.Pool
	Logger zerolog.Logger
}

// New parses the URL, opens a pgxpool with reasonable defaults, and verifies
// connectivity with a Ping. The returned *DB is safe for concurrent use.
func New(ctx context.Context, databaseURL string, logger zerolog.Logger) (*DB, error) {
	poolCfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("parse database URL: %w", err)
	}

	poolCfg.MaxConns = 20
	poolCfg.MinConns = 2

	pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		return nil, fmt.Errorf("create connection pool: %w", err)
	}

	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping database: %w", err)
	}

	logger.Info().Msg("database connected")

	return &DB{
		Pool:   pool,
		Logger: logger,
	}, nil
}

// Ping verifies the pool can still reach the database.
func (db *DB) Ping(ctx context.Context) error {
	return db.Pool.Ping(ctx)
}

// Close drains and closes the underlying pool.
func (db *DB) Close() {
	db.Pool.Close()
	db.Logger.Info().Msg("database connection closed")
}
