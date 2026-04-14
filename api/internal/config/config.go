// Package config loads the API configuration from environment variables.
//
// The pattern mirrors MSV's `internal/config/config.go`: required vars fail
// loudly, optional vars get sane defaults, and dev-mode toggles unlock the
// dev cookie auth path used by Phase 1.
package config

import (
	"fmt"
	"os"
	"strings"
)

// Config is the validated runtime configuration for the API binary.
type Config struct {
	// APIPort is the TCP port the HTTP server binds to. Defaults to "8080".
	APIPort string

	// DatabaseURL is the Postgres connection string. Required; empty -> Load() errors.
	DatabaseURL string

	// RedisURL is the Redis connection URL. Defaults to "redis://localhost:6379".
	RedisURL string

	// LogLevel is a zerolog level string ("debug", "info", "warn", "error"). Default "info".
	LogLevel string

	// DevMode enables the dev-cookie auth stub at POST /api/dev/login.
	// Phase 3 swaps goth in behind the same SessionProvider interface.
	DevMode bool

	// SessionSecret is the HMAC key used to sign session cookies. Required when DevMode=true.
	// Must be at least 32 bytes for HMAC-SHA256.
	SessionSecret string

	// TemporalHost is the Temporal frontend address. Empty means "no Temporal"
	// and cmd/server/main.go skips the worker dial entirely. Set TEMPORAL_HOST
	// explicitly to connect (e.g. "localhost:7233" in local dev).
	TemporalHost string

	// TemporalNamespace is the Temporal namespace this binary uses. Defaults to "default".
	TemporalNamespace string
}

// Load reads the process environment and returns a populated, validated Config.
// Returns an error if any required variable is missing or invalid.
func Load() (*Config, error) {
	cfg := &Config{
		APIPort:           getEnvDefault("API_PORT", "8080"),
		DatabaseURL:       os.Getenv("DATABASE_URL"),
		RedisURL:          getEnvDefault("REDIS_URL", "redis://localhost:6379"),
		LogLevel:          getEnvDefault("LOG_LEVEL", "info"),
		DevMode:           strings.EqualFold(os.Getenv("AP_DEV_MODE"), "true"),
		SessionSecret:     os.Getenv("AP_SESSION_SECRET"),
		TemporalHost:      os.Getenv("TEMPORAL_HOST"),
		TemporalNamespace: getEnvDefault("TEMPORAL_NAMESPACE", "default"),
	}

	if cfg.DatabaseURL == "" {
		return nil, fmt.Errorf("DATABASE_URL is required")
	}

	// Validate length whenever a secret is provided, regardless of DevMode.
	// A short HMAC key is cryptographically weak; a zero-length key makes every
	// token produce the same signature.
	if cfg.SessionSecret != "" && len(cfg.SessionSecret) < 32 {
		return nil, fmt.Errorf("AP_SESSION_SECRET must be at least 32 bytes (got %d)", len(cfg.SessionSecret))
	}

	// In dev mode the secret is required (the dev cookie auth path always uses it).
	if cfg.DevMode && cfg.SessionSecret == "" {
		return nil, fmt.Errorf("AP_SESSION_SECRET is required when AP_DEV_MODE=true")
	}

	return cfg, nil
}

func getEnvDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
