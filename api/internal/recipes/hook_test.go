package recipes

import (
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNormalize_Nil(t *testing.T) {
	h, err := NormalizeHook(nil)
	require.NoError(t, err)
	assert.Nil(t, h)
}

func TestNormalize_EmptyString(t *testing.T) {
	h, err := NormalizeHook("")
	require.NoError(t, err)
	assert.Nil(t, h)
}

func TestNormalize_String(t *testing.T) {
	h, err := NormalizeHook("echo hello")
	require.NoError(t, err)
	require.Equal(t, Hook{{"sh", "-c", "echo hello"}}, h)
}

func TestNormalize_ArrayOfStrings(t *testing.T) {
	// Aider's postCreateCommand example from Plan 03 <behavior>.
	h, err := NormalizeHook([]any{"uv", "pip", "install", "--system", "aider-chat"})
	require.NoError(t, err)
	require.Equal(t, Hook{{"uv", "pip", "install", "--system", "aider-chat"}}, h)
}

func TestNormalize_ArrayOfArrays(t *testing.T) {
	// Parallel groups example from Plan 03 <behavior>.
	h, err := NormalizeHook([]any{
		[]any{"apt-get", "install", "git"},
		[]any{"uv", "pip", "install", "aider-chat"},
	})
	require.NoError(t, err)
	require.Len(t, h, 2)
	require.Equal(t, []string{"apt-get", "install", "git"}, h[0])
	require.Equal(t, []string{"uv", "pip", "install", "aider-chat"}, h[1])
}

func TestNormalize_EmptyArray(t *testing.T) {
	h, err := NormalizeHook([]any{})
	require.NoError(t, err)
	assert.Nil(t, h)
}

func TestNormalize_Mixed_Error(t *testing.T) {
	// Mixing string and []any at the outer level is rejected.
	_, err := NormalizeHook([]any{"echo", []any{"hi"}})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "mixed")
}

func TestNormalize_NonStringInInnerArgv(t *testing.T) {
	_, err := NormalizeHook([]any{
		[]any{"apt-get", 42},
	})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "non-string")
}

func TestNormalize_EmptyInnerArgv(t *testing.T) {
	_, err := NormalizeHook([]any{
		[]any{"ok"},
		[]any{},
	})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "empty argv")
}

func TestNormalize_GoSliceOfString(t *testing.T) {
	// Convenience path for tests that pre-build hooks in native Go.
	h, err := NormalizeHook([]string{"bin", "--flag"})
	require.NoError(t, err)
	require.Equal(t, Hook{{"bin", "--flag"}}, h)
}

func TestNormalize_UnsupportedRootType(t *testing.T) {
	_, err := NormalizeHook(42)
	require.Error(t, err)
	assert.True(t, strings.Contains(err.Error(), "unsupported root type"))
}

func TestNormalize_UnsupportedInnerType(t *testing.T) {
	// First element is a map — neither string nor []any.
	_, err := NormalizeHook([]any{map[string]any{"foo": "bar"}})
	require.Error(t, err)
	assert.Contains(t, err.Error(), "unsupported first element type")
}

func TestHookTimeout_Default(t *testing.T) {
	r := &Recipe{}
	// Every named hook returns the default when the corresponding
	// per-hook sec field is zero.
	for _, name := range []string{
		"initializeCommand",
		"onCreateCommand",
		"updateContentCommand",
		"postCreateCommand",
		"postStartCommand",
		"postAttachCommand",
	} {
		assert.Equal(t, DefaultHookTimeout, HookTimeout(r, name), name)
	}
}

func TestHookTimeout_NilRecipe(t *testing.T) {
	assert.Equal(t, DefaultHookTimeout, HookTimeout(nil, "postCreateCommand"))
}

func TestHookTimeout_Override(t *testing.T) {
	r := &Recipe{
		Lifecycle: RecipeLifecycle{
			InitializeTimeoutSec:    1,
			OnCreateTimeoutSec:      2,
			UpdateContentTimeoutSec: 3,
			PostCreateTimeoutSec:    4,
			PostStartTimeoutSec:     5,
			PostAttachTimeoutSec:    6,
		},
	}
	assert.Equal(t, 1*time.Second, HookTimeout(r, "initializeCommand"))
	assert.Equal(t, 2*time.Second, HookTimeout(r, "onCreateCommand"))
	assert.Equal(t, 3*time.Second, HookTimeout(r, "updateContentCommand"))
	assert.Equal(t, 4*time.Second, HookTimeout(r, "postCreateCommand"))
	assert.Equal(t, 5*time.Second, HookTimeout(r, "postStartCommand"))
	assert.Equal(t, 6*time.Second, HookTimeout(r, "postAttachCommand"))
}

func TestHookTimeout_UnknownName(t *testing.T) {
	r := &Recipe{Lifecycle: RecipeLifecycle{PostCreateTimeoutSec: 99}}
	// Unknown hook names fall through to the default.
	assert.Equal(t, DefaultHookTimeout, HookTimeout(r, "bogusCommand"))
}
