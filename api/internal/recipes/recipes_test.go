package recipes_test

import (
	"testing"
	"time"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// These tests exercise the Phase 2 legacy hardcoded catalog. The types
// were renamed to Legacy* in Phase 02.5 Plan 01 to make room for the
// YAML-backed Recipe. Plan 02.5-09 will delete this whole file.

func TestRecipes_HasPicoclaw(t *testing.T) {
	r := recipes.LegacyAllRecipes["picoclaw"]
	require.NotNil(t, r, "picoclaw recipe must exist")
	assert.Equal(t, "ap-picoclaw:v0.1.0-c7461f9", r.Image)
	assert.Equal(t, recipes.ChatIOFIFO, r.ChatIO.Mode)
	require.NotEmpty(t, r.RequiredSecrets)
	assert.Contains(t, r.RequiredSecrets, "anthropic_key")
	require.NotEmpty(t, r.ChatIO.LaunchCmd)
	assert.Equal(t, "picoclaw", r.ChatIO.LaunchCmd[0])
	assert.Contains(t, r.SupportedProviders, "anthropic")
	assert.Equal(t, "anthropic", r.EnvOverrides["PICOCLAW_PROVIDER"])
	assert.Equal(t, 60*time.Second, r.ChatIO.ResponseTimeout)
}

func TestRecipes_HasHermes(t *testing.T) {
	r := recipes.LegacyAllRecipes["hermes"]
	require.NotNil(t, r, "hermes recipe must exist")
	assert.Equal(t, "ap-hermes:v0.1.0-5621fc4", r.Image)
	assert.Equal(t, recipes.ChatIOExec, r.ChatIO.Mode)
	require.GreaterOrEqual(t, len(r.ChatIO.ExecCmd), 3)
	assert.Equal(t, []string{"hermes", "chat", "-q"}, r.ChatIO.ExecCmd[:3])
	assert.Contains(t, r.RequiredSecrets, "anthropic_key")
	assert.Contains(t, r.SupportedProviders, "anthropic")
	assert.Equal(t, "anthropic", r.EnvOverrides["HERMES_INFERENCE_PROVIDER"])
	assert.Equal(t, "1", r.EnvOverrides["HERMES_QUIET"])
	assert.Equal(t, int64(2<<30), r.ResourceOverrides.Memory)
	assert.Equal(t, 120*time.Second, r.ChatIO.ResponseTimeout)
}

func TestRecipes_AllRequireAnthropicKey(t *testing.T) {
	require.NotEmpty(t, recipes.LegacyAllRecipes)
	for name, r := range recipes.LegacyAllRecipes {
		assert.Contains(t, r.RequiredSecrets, "anthropic_key",
			"recipe %q must require anthropic_key in Phase 2", name)
	}
}

func TestRecipes_Get_Lookup(t *testing.T) {
	assert.NotNil(t, recipes.GetLegacy("picoclaw"))
	assert.NotNil(t, recipes.GetLegacy("hermes"))
	assert.Nil(t, recipes.GetLegacy("nope"))
}
