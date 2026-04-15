package recipes_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/stretchr/testify/require"
)

// TestSchemaCompiles constructs the SchemaValidator and verifies the embedded
// Draft 2019-09 schema compiles cleanly. The validator is the entry point for
// every YAML-backed recipe file; if it can't be built at startup, the Go API
// can never load recipes.
func TestSchemaCompiles(t *testing.T) {
	v, err := recipes.NewSchemaValidator()
	require.NoError(t, err, "schema must compile cleanly")
	require.NotNil(t, v)
}

// TestValidateYAML_Valid_Minimal asserts that the smallest possible valid
// recipe (every required field supplied, nothing extra) passes validation.
func TestValidateYAML_Valid_Minimal(t *testing.T) {
	v := mustValidator(t)
	raw := mustRead(t, filepath.Join("testdata", "valid", "minimal.yaml"))
	require.NoError(t, v.ValidateYAML(raw))
}

// TestValidateYAML_Rejects_MissingRequired asserts the schema surfaces the
// name of the first missing required field in its error output — here, the
// fixture omits runtime entirely.
func TestValidateYAML_Rejects_MissingRequired(t *testing.T) {
	v := mustValidator(t)
	raw := mustRead(t, filepath.Join("testdata", "invalid", "missing_required.yaml"))
	err := v.ValidateYAML(raw)
	require.Error(t, err)
	require.True(t, strings.Contains(err.Error(), "runtime") || strings.Contains(err.Error(), "required"),
		"expected error to mention missing required field 'runtime', got: %v", err)
}

// TestValidateYAML_Rejects_UnknownChatMode asserts chat_io.mode is a closed
// enum: http_gateway was cut per D-10 and must be rejected by the schema
// (not a runtime-only check).
func TestValidateYAML_Rejects_UnknownChatMode(t *testing.T) {
	v := mustValidator(t)
	raw := mustRead(t, filepath.Join("testdata", "invalid", "unknown_chat_mode.yaml"))
	err := v.ValidateYAML(raw)
	require.Error(t, err)
	// Detailed output must mention the offending value or the chat_io.mode path.
	msg := err.Error()
	require.True(t,
		strings.Contains(msg, "http_gateway") || strings.Contains(msg, "mode") || strings.Contains(msg, "enum"),
		"expected error to mention http_gateway / mode / enum, got: %v", err)
}

// TestValidateYAML_Rejects_OnCreateSecret asserts the hook-no-secrets $def
// catches secret: references inside onCreateCommand (D-29 schema-level
// enforcement — semantic check is belt-and-suspenders).
func TestValidateYAML_Rejects_OnCreateSecret(t *testing.T) {
	v := mustValidator(t)
	raw := mustRead(t, filepath.Join("testdata", "invalid", "onCreate_uses_secret.yaml"))
	err := v.ValidateYAML(raw)
	require.Error(t, err)
	// The error should either flag the 'secret:' pattern or the onCreateCommand field.
	msg := err.Error()
	require.True(t,
		strings.Contains(msg, "secret") || strings.Contains(msg, "onCreateCommand") || strings.Contains(msg, "hook-no-secrets"),
		"expected error to mention secret/onCreateCommand/hook-no-secrets, got: %v", err)
}

// --- helpers ---

func mustValidator(t *testing.T) *recipes.SchemaValidator {
	t.Helper()
	v, err := recipes.NewSchemaValidator()
	require.NoError(t, err)
	return v
}

func mustRead(t *testing.T, path string) []byte {
	t.Helper()
	raw, err := os.ReadFile(path)
	require.NoError(t, err, "read fixture %s", path)
	return raw
}
