// Package redis wraps a go-redis client with structured logging.
//
// Mirrors MSV's `pkg/redis/client.go`: parse URL, ping, expose Ping/Close.
package redis

import (
	"context"
	"fmt"

	goredis "github.com/redis/go-redis/v9"
	"github.com/rs/zerolog"
)

// Client wraps a go-redis client with structured logging.
type Client struct {
	RDB    *goredis.Client
	Logger zerolog.Logger
}

// New parses a Redis URL, opens a connection, and pings to verify connectivity.
func New(ctx context.Context, redisURL string, logger zerolog.Logger) (*Client, error) {
	opts, err := goredis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis URL: %w", err)
	}

	rdb := goredis.NewClient(opts)

	if err := rdb.Ping(ctx).Err(); err != nil {
		_ = rdb.Close()
		return nil, fmt.Errorf("ping redis: %w", err)
	}

	logger.Info().Msg("redis connected")

	return &Client{
		RDB:    rdb,
		Logger: logger,
	}, nil
}

// Ping verifies the Redis server is reachable.
func (c *Client) Ping(ctx context.Context) error {
	return c.RDB.Ping(ctx).Err()
}

// Close releases the underlying Redis connection pool.
func (c *Client) Close() error {
	c.Logger.Info().Msg("redis connection closed")
	return c.RDB.Close()
}
