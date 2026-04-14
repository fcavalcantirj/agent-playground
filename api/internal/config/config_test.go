package config_test

import (
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/internal/config"
)

// resetEnv unsets all env vars the Config touches so tests start from a clean slate.
func resetEnv(t *testing.T) {
	t.Helper()
	for _, k := range []string{
		"DATABASE_URL", "REDIS_URL", "API_PORT", "LOG_LEVEL",
		"AP_DEV_MODE", "AP_SESSION_SECRET",
		"TEMPORAL_HOST", "TEMPORAL_NAMESPACE",
	} {
		t.Setenv(k, "")
	}
}

func TestLoad_RequiresDatabaseURL(t *testing.T) {
	resetEnv(t)
	_, err := config.Load()
	require.Error(t, err, "missing DATABASE_URL must error")
	require.Contains(t, err.Error(), "DATABASE_URL")
}

func TestLoad_RedisURLDefault(t *testing.T) {
	resetEnv(t)
	t.Setenv("DATABASE_URL", "postgres://localhost/test")
	cfg, err := config.Load()
	require.NoError(t, err)
	require.Equal(t, "redis://localhost:6379", cfg.RedisURL)
}

func TestLoad_DevModeDefaultFalse(t *testing.T) {
	resetEnv(t)
	t.Setenv("DATABASE_URL", "postgres://localhost/test")
	cfg, err := config.Load()
	require.NoError(t, err)
	require.False(t, cfg.DevMode)
}

func TestLoad_SessionSecretRequiredInDevMode(t *testing.T) {
	resetEnv(t)
	t.Setenv("DATABASE_URL", "postgres://localhost/test")
	t.Setenv("AP_DEV_MODE", "true")
	_, err := config.Load()
	require.Error(t, err, "AP_DEV_MODE=true without secret must error")
	require.Contains(t, err.Error(), "AP_SESSION_SECRET")

	t.Setenv("AP_SESSION_SECRET", "too-short")
	_, err = config.Load()
	require.Error(t, err, "secret shorter than 32 chars must error")

	t.Setenv("AP_SESSION_SECRET", "this-is-a-32-character-secret-okay!")
	cfg, err := config.Load()
	require.NoError(t, err)
	require.True(t, cfg.DevMode)
	require.GreaterOrEqual(t, len(cfg.SessionSecret), 32)
}

func TestLoad_APIPortDefault(t *testing.T) {
	resetEnv(t)
	t.Setenv("DATABASE_URL", "postgres://localhost/test")
	cfg, err := config.Load()
	require.NoError(t, err)
	require.Equal(t, "8080", cfg.APIPort)
}

func TestLoad_APIPortOverride(t *testing.T) {
	resetEnv(t)
	t.Setenv("DATABASE_URL", "postgres://localhost/test")
	t.Setenv("API_PORT", "9090")
	cfg, err := config.Load()
	require.NoError(t, err)
	require.Equal(t, "9090", cfg.APIPort)
}

func TestLoad_TemporalDefaults(t *testing.T) {
	resetEnv(t)
	t.Setenv("DATABASE_URL", "postgres://localhost/test")
	cfg, err := config.Load()
	require.NoError(t, err)
	require.Equal(t, "localhost:7233", cfg.TemporalHost)
	require.Equal(t, "default", cfg.TemporalNamespace)
}
