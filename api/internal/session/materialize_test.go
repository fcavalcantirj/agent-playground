package session_test

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"text/template"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/agentplayground/api/internal/session"
)

// --- helpers ---

// fakeSecrets is a SecretSource mock that returns values from a map.
// It implements both Get and Resolve per the Phase 02.5 interface.
type fakeSecrets struct {
	vals map[string]string
}

func (f *fakeSecrets) Get(name string) (string, error) {
	if v, ok := f.vals[name]; ok {
		return v, nil
	}
	return "", session.ErrSecretMissing
}

func (f *fakeSecrets) Resolve(ref string) (string, error) {
	if !strings.HasPrefix(ref, "secret:") {
		return ref, nil
	}
	return f.Get(strings.TrimPrefix(ref, "secret:"))
}

// fakeRenderer is a TemplateRenderer mock that compiles and runs a
// text/template body stored under (recipeID, templateName). Mirrors
// the real registry's Render signature without the filesystem and
// cache machinery so these tests can focus on Materialize semantics.
type fakeRenderer struct {
	bodies map[string]string // key = recipeID/templateName
	// returnErr forces Render to return a canned error regardless of input.
	returnErr error
}

func (r *fakeRenderer) Render(ctx context.Context, recipeID, name string, data any) (string, error) {
	if r.returnErr != nil {
		return "", r.returnErr
	}
	body, ok := r.bodies[recipeID+"/"+name]
	if !ok {
		return "", fmt.Errorf("fake renderer: unknown template %s/%s", recipeID, name)
	}
	t, err := template.New(name).
		Option("missingkey=error").
		Parse(body)
	if err != nil {
		return "", fmt.Errorf("fake renderer: parse %s: %w", name, err)
	}
	var buf bytes.Buffer
	if err := t.Execute(&buf, data); err != nil {
		return "", fmt.Errorf("fake renderer: execute %s: %w", name, err)
	}
	return buf.String(), nil
}

// --- tests ---

func TestMaterialize_LiteralEnv(t *testing.T) {
	recipe := &recipes.Recipe{
		ID: "literal",
		Auth: recipes.RecipeAuth{
			Env: map[string]string{"EDITOR": "vim"},
		},
	}
	src := &fakeSecrets{vals: map[string]string{}}
	r := &fakeRenderer{}
	m, err := session.Materialize(context.Background(), recipe, "", "", src, r)
	require.NoError(t, err)
	assert.Equal(t, "vim", m.Env["EDITOR"])
	assert.Empty(t, m.Files)
}

func TestMaterialize_SecretEnv(t *testing.T) {
	recipe := &recipes.Recipe{
		ID: "secret-env",
		Auth: recipes.RecipeAuth{
			Env: map[string]string{
				"ANTHROPIC_API_KEY": "secret:anthropic-api-key",
			},
		},
	}
	src := &fakeSecrets{vals: map[string]string{"anthropic-api-key": "sk-ant-test"}}
	r := &fakeRenderer{}
	m, err := session.Materialize(context.Background(), recipe, "", "", src, r)
	require.NoError(t, err)
	assert.Equal(t, "sk-ant-test", m.Env["ANTHROPIC_API_KEY"])
}

func TestMaterialize_AuthFile_RendersTemplate(t *testing.T) {
	recipe := &recipes.Recipe{
		ID: "picoclaw",
		Auth: recipes.RecipeAuth{
			Files: []recipes.RecipeAuthFileDecl{
				{
					Secret:   "anthropic-api-key",
					Target:   "/home/agent/.picoclaw/.security.yml",
					Mode:     "0600",
					Template: "security.yml",
				},
			},
		},
	}
	src := &fakeSecrets{vals: map[string]string{"anthropic-api-key": "sk-ant-test"}}
	r := &fakeRenderer{
		bodies: map[string]string{
			"picoclaw/security.yml": `key: "{{ .secrets.anthropic_api_key }}"`,
		},
	}
	m, err := session.Materialize(context.Background(), recipe, "", "", src, r)
	require.NoError(t, err)
	require.Len(t, m.Files, 1)
	assert.Equal(t, "/home/agent/.picoclaw/.security.yml", m.Files[0].Target)
	assert.Equal(t, "0600", m.Files[0].Mode)
	assert.Contains(t, m.Files[0].Body, "sk-ant-test")
}

func TestMaterialize_MissingSecret(t *testing.T) {
	recipe := &recipes.Recipe{
		ID: "missing",
		Auth: recipes.RecipeAuth{
			Env: map[string]string{
				"ANTHROPIC_API_KEY": "secret:anthropic-api-key",
			},
		},
	}
	src := &fakeSecrets{vals: map[string]string{}}
	r := &fakeRenderer{}
	_, err := session.Materialize(context.Background(), recipe, "", "", src, r)
	require.Error(t, err)
	assert.True(t, errors.Is(err, session.ErrSecretMissing))
	// Must not contain the key name-value — only the field ref.
	assert.Contains(t, err.Error(), "ANTHROPIC_API_KEY")
}

func TestMaterialize_TemplateRenderFailure(t *testing.T) {
	recipe := &recipes.Recipe{
		ID: "bad-tmpl",
		Auth: recipes.RecipeAuth{
			Files: []recipes.RecipeAuthFileDecl{
				{
					Secret:   "anthropic-api-key",
					Target:   "/path",
					Mode:     "0600",
					Template: "security.yml",
				},
			},
		},
	}
	src := &fakeSecrets{vals: map[string]string{"anthropic-api-key": "sk-ant-test"}}
	r := &fakeRenderer{
		bodies: map[string]string{
			// Undefined key: template engine with missingkey=error fails.
			"bad-tmpl/security.yml": `{{ .nosuchkey }}`,
		},
	}
	_, err := session.Materialize(context.Background(), recipe, "", "", src, r)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "render")
	assert.Contains(t, err.Error(), "security.yml")
}

func TestMaterialize_ContextKeyNormalization(t *testing.T) {
	recipe := &recipes.Recipe{
		ID: "norm",
		Auth: recipes.RecipeAuth{
			Files: []recipes.RecipeAuthFileDecl{
				{
					Secret:   "anthropic-api-key",
					Target:   "/path",
					Mode:     "0600",
					Template: "t1",
				},
			},
		},
	}
	src := &fakeSecrets{vals: map[string]string{"anthropic-api-key": "sk-ant-norm"}}
	// Underscore form must work (the canonical template style).
	r := &fakeRenderer{
		bodies: map[string]string{
			"norm/t1": `{{ .secrets.anthropic_api_key }}`,
		},
	}
	m, err := session.Materialize(context.Background(), recipe, "", "", src, r)
	require.NoError(t, err)
	assert.Equal(t, "sk-ant-norm", m.Files[0].Body)

	// Hyphen form via index must also work.
	r2 := &fakeRenderer{
		bodies: map[string]string{
			"norm/t1": `{{ index .secrets "anthropic-api-key" }}`,
		},
	}
	m2, err := session.Materialize(context.Background(), recipe, "", "", src, r2)
	require.NoError(t, err)
	assert.Equal(t, "sk-ant-norm", m2.Files[0].Body)
}

func TestMaterialize_ProviderValidation(t *testing.T) {
	recipe := &recipes.Recipe{
		ID: "prov",
		Providers: []recipes.RecipeProvider{
			{ID: "anthropic"},
		},
	}
	src := &fakeSecrets{}
	r := &fakeRenderer{}
	// Declared provider succeeds.
	_, err := session.Materialize(context.Background(), recipe, "anthropic", "claude-4.6", src, r)
	require.NoError(t, err)
	// Undeclared provider fails.
	_, err = session.Materialize(context.Background(), recipe, "openrouter", "x", src, r)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "provider")
	assert.Contains(t, err.Error(), "not declared")
}

func TestMaterialize_NilRecipe(t *testing.T) {
	src := &fakeSecrets{}
	r := &fakeRenderer{}
	_, err := session.Materialize(context.Background(), nil, "", "", src, r)
	require.Error(t, err)
}
