package session_test

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/agentplayground/api/internal/session"
	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newTestWriter(t *testing.T, src session.SecretSource) *session.SecretWriter {
	t.Helper()
	base := filepath.Join(t.TempDir(), "secrets")
	w := session.NewSecretWriter(src)
	w.BaseDir = base
	return w
}

func TestSecretWriter_WritesFile(t *testing.T) {
	src := &session.DevEnvSource{AnthropicKey: "sk-ant-test-123"}
	w := newTestWriter(t, src)
	id := uuid.New()

	dir, err := w.Provision(id, []string{"anthropic_key"})
	require.NoError(t, err)
	assert.Equal(t, filepath.Join(w.BaseDir, id.String()), dir)

	// Directory mode 0700 (Pitfall 6: only owner — uid remapped host user —
	// can traverse into the secrets dir). Mask off type bits before compare.
	st, err := os.Stat(dir)
	require.NoError(t, err)
	assert.True(t, st.IsDir())
	assert.Equal(t, os.FileMode(0o700), st.Mode().Perm(), "secrets dir must be 0700")

	keyPath := filepath.Join(dir, "anthropic_key")
	fi, err := os.Stat(keyPath)
	require.NoError(t, err)
	assert.Equal(t, os.FileMode(0o644), fi.Mode().Perm(), "secret file must be 0644 (Pitfall 6)")

	data, err := os.ReadFile(keyPath)
	require.NoError(t, err)
	assert.Equal(t, "sk-ant-test-123", string(data))
}

func TestSecretWriter_Cleanup(t *testing.T) {
	src := &session.DevEnvSource{AnthropicKey: "sk-ant-test"}
	w := newTestWriter(t, src)
	id := uuid.New()

	_, err := w.Provision(id, []string{"anthropic_key"})
	require.NoError(t, err)

	require.NoError(t, w.Cleanup(id))
	_, err = os.Stat(filepath.Join(w.BaseDir, id.String()))
	assert.True(t, os.IsNotExist(err), "secret dir must be removed")
}

func TestSecretSource_DevEnv_NotSet(t *testing.T) {
	src := &session.DevEnvSource{AnthropicKey: ""}
	_, err := src.Get("anthropic_key")
	assert.True(t, errors.Is(err, session.ErrSecretMissing))
}

func TestSecretSource_DevEnv_Set(t *testing.T) {
	src := &session.DevEnvSource{AnthropicKey: "sk-ant-XYZ"}
	v, err := src.Get("anthropic_key")
	require.NoError(t, err)
	assert.Equal(t, "sk-ant-XYZ", v)

	_, err = src.Get("openai_key")
	assert.True(t, errors.Is(err, session.ErrSecretMissing),
		"dev source only knows anthropic_key")
}

func TestSecretWriter_BindMountSpec(t *testing.T) {
	src := &session.DevEnvSource{AnthropicKey: "k"}
	w := session.NewSecretWriter(src) // default BaseDir = /tmp/ap/secrets
	id := uuid.MustParse("11111111-2222-3333-4444-555555555555")
	spec := w.BindMountSpec(id)
	assert.Equal(t, "/tmp/ap/secrets/11111111-2222-3333-4444-555555555555:/run/secrets:ro", spec)
}

func TestNewDevEnvSource_ReadsEnv(t *testing.T) {
	t.Setenv("AP_DEV_BYOK_KEY", "sk-ant-from-env")
	src := session.NewDevEnvSource()
	require.NotNil(t, src)
	assert.Equal(t, "sk-ant-from-env", src.AnthropicKey)
}

// --- Phase 02.5 Plan 05: Resolve + OpenRouter + extras ---

func TestResolve_LiteralPassthrough(t *testing.T) {
	src := &session.DevEnvSecretSource{}
	v, err := src.Resolve("vim")
	require.NoError(t, err)
	assert.Equal(t, "vim", v)
}

func TestResolve_SecretPrefix_Anthropic(t *testing.T) {
	t.Setenv("AP_DEV_BYOK_KEY", "sk-ant-plan05")
	t.Setenv("AP_DEV_OPENROUTER_KEY", "")
	src := session.NewDevEnvSecretSource()
	v, err := src.Resolve("secret:anthropic-api-key")
	require.NoError(t, err)
	assert.Equal(t, "sk-ant-plan05", v)
}

func TestResolve_SecretPrefix_OpenRouter(t *testing.T) {
	t.Setenv("AP_DEV_BYOK_KEY", "")
	t.Setenv("AP_DEV_OPENROUTER_KEY", "sk-or-v1-plan05")
	src := session.NewDevEnvSecretSource()
	v, err := src.Resolve("secret:openrouter-api-key")
	require.NoError(t, err)
	assert.Equal(t, "sk-or-v1-plan05", v)
}

func TestResolve_ExtrasKey(t *testing.T) {
	t.Setenv("AP_DEV_FOO_KEY", "bar")
	t.Setenv("AP_DEV_MY_CUSTOM_KEY", "baz")
	src := session.NewDevEnvSecretSource()
	v, err := src.Resolve("secret:foo")
	require.NoError(t, err)
	assert.Equal(t, "bar", v)
	v, err = src.Resolve("secret:my-custom")
	require.NoError(t, err)
	assert.Equal(t, "baz", v)
}

func TestResolve_Missing(t *testing.T) {
	t.Setenv("AP_DEV_BYOK_KEY", "")
	t.Setenv("AP_DEV_OPENROUTER_KEY", "")
	src := session.NewDevEnvSecretSource()
	_, err := src.Resolve("secret:nosuch")
	assert.True(t, errors.Is(err, session.ErrSecretMissing))
}

func TestResolve_GetParity(t *testing.T) {
	t.Setenv("AP_DEV_BYOK_KEY", "sk-ant-parity")
	src := session.NewDevEnvSecretSource()
	getV, err := src.Get("anthropic_key")
	require.NoError(t, err)
	resolveV, err := src.Resolve("secret:anthropic-api-key")
	require.NoError(t, err)
	assert.Equal(t, getV, resolveV)
}
