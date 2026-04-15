package logging_test

import (
	"bytes"
	"strings"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/internal/logging"
)

func TestRedact_AnthropicKey(t *testing.T) {
	var buf bytes.Buffer
	w := logging.InstallRedactionHook(&buf)
	logger := zerolog.New(w)
	fakeKey := "sk-ant-" + strings.Repeat("a", 60)
	logger.Info().Str("key", fakeKey).Msg("test")
	out := buf.String()
	require.NotContains(t, out, fakeKey, "Anthropic key must not appear in log output")
	assert.Contains(t, out, "<REDACTED>")
}

func TestRedact_OpenRouterKey(t *testing.T) {
	var buf bytes.Buffer
	w := logging.InstallRedactionHook(&buf)
	logger := zerolog.New(w)
	fakeKey := "sk-or-v1-" + strings.Repeat("a", 64)
	logger.Info().Str("key", fakeKey).Msg("test")
	out := buf.String()
	require.NotContains(t, out, fakeKey, "OpenRouter key must not appear in log output")
	assert.Contains(t, out, "<REDACTED>")
}

func TestRedact_SessionCookie(t *testing.T) {
	var buf bytes.Buffer
	w := logging.InstallRedactionHook(&buf)
	logger := zerolog.New(w)
	logger.Info().Str("cookie", "ap_session=abc123XYZ_+/=").Msg("test")
	out := buf.String()
	require.NotContains(t, out, "ap_session=abc123XYZ", "session cookie value must not appear")
	assert.Contains(t, out, "<REDACTED>")
}

func TestRedact_Passthrough(t *testing.T) {
	var buf bytes.Buffer
	w := logging.InstallRedactionHook(&buf)
	logger := zerolog.New(w)
	logger.Info().Str("msg", "hello world").Msg("ok")
	out := buf.String()
	assert.Contains(t, out, "hello world")
	assert.NotContains(t, out, "<REDACTED>")
}

// TestRedact_ReportsOriginalLength protects the zerolog integration:
// Write MUST return len(p) on success, not the post-redaction output
// length, otherwise zerolog flags the sink as broken.
func TestRedact_ReportsOriginalLength(t *testing.T) {
	var buf bytes.Buffer
	w := logging.InstallRedactionHook(&buf)
	payload := []byte("prefix sk-ant-" + strings.Repeat("a", 60) + " suffix")
	n, err := w.Write(payload)
	require.NoError(t, err)
	assert.Equal(t, len(payload), n, "Write must report original length")
	assert.Contains(t, buf.String(), "<REDACTED>")
	assert.NotContains(t, buf.String(), strings.Repeat("a", 60))
}
