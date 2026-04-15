package recipes_test

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func newTestLoader(t *testing.T, root string) *recipes.Loader {
	t.Helper()
	v, err := recipes.NewSchemaValidator()
	require.NoError(t, err)
	return recipes.NewLoader(root, v, zerolog.Nop())
}

// TestLoaderLoadAll points Loader at a fixture root with exactly two
// valid recipes (aider + picoclaw) and asserts both load cleanly.
func TestLoaderLoadAll(t *testing.T) {
	l := newTestLoader(t, filepath.Join("testdata", "fixtures", "set_a"))
	require.NoError(t, l.LoadAll(context.Background()))

	all := l.All()
	require.Len(t, all, 2, "expected exactly 2 recipes in set_a")

	aider, ok := l.Get("aider")
	require.True(t, ok)
	assert.Equal(t, "Aider", aider.Name)
	assert.Equal(t, "python", aider.Runtime.Family)
	assert.Equal(t, "exec_per_message", aider.ChatIO.Mode)

	picoclaw, ok := l.Get("picoclaw")
	require.True(t, ok)
	assert.Equal(t, "node", picoclaw.Runtime.Family)
	assert.Equal(t, "fifo", picoclaw.ChatIO.Mode)
	require.NotNil(t, picoclaw.Install.Git)
	assert.Equal(t, "c7461f9e963496c4471336642ac6a8d91a456978", picoclaw.Install.Git.Rev)
}

// TestLoaderRejects_Semantic_InstallRuntimeMismatch ensures the semantic
// check for install.type↔runtime.family coherence catches a pip package
// paired with a node runtime.
func TestLoaderRejects_Semantic_InstallRuntimeMismatch(t *testing.T) {
	l := newTestLoader(t, filepath.Join("testdata", "fixtures", "install_mismatch"))
	err := l.LoadAll(context.Background())
	require.Error(t, err)
	require.True(t, errors.Is(err, recipes.ErrInstallRuntimeMismatch) || strings.Contains(err.Error(), "install.type"),
		"expected ErrInstallRuntimeMismatch, got: %v", err)
}

// TestLoaderRejects_FlavorChain asserts the loader rejects a recipe that
// points at a parent which itself points at another parent (flavor of
// flavor not allowed).
func TestLoaderRejects_FlavorChain(t *testing.T) {
	l := newTestLoader(t, filepath.Join("testdata", "fixtures", "flavor_chain"))
	err := l.LoadAll(context.Background())
	require.Error(t, err)
	require.True(t, errors.Is(err, recipes.ErrFlavorChain) || strings.Contains(err.Error(), "flavor"),
		"expected ErrFlavorChain, got: %v", err)
}

// TestLoaderRejects_FlavorRedeclaresInstall asserts a flavor (one with
// config_flavor_of set) cannot carry its own install block — install
// must inherit from the parent.
func TestLoaderRejects_FlavorRedeclaresInstall(t *testing.T) {
	l := newTestLoader(t, filepath.Join("testdata", "fixtures", "flavor_redeclare"))
	err := l.LoadAll(context.Background())
	require.Error(t, err)
	require.True(t, errors.Is(err, recipes.ErrFlavorRedeclaresInstall) || strings.Contains(err.Error(), "redeclare"),
		"expected ErrFlavorRedeclaresInstall, got: %v", err)
}

// TestReload mutates a recipe file on disk, calls Reload, and asserts
// the cache reflects the new name — confirming atomic swap works.
func TestReload(t *testing.T) {
	// Copy the static fixture into a temp dir so we can mutate without
	// polluting the committed testdata.
	src := filepath.Join("testdata", "fixtures", "reload", "rel", "recipe.yaml")
	body, err := os.ReadFile(src)
	require.NoError(t, err)

	tmp := t.TempDir()
	relDir := filepath.Join(tmp, "rel")
	require.NoError(t, os.Mkdir(relDir, 0o755))
	recPath := filepath.Join(relDir, "recipe.yaml")
	require.NoError(t, os.WriteFile(recPath, body, 0o644))

	l := newTestLoader(t, tmp)
	require.NoError(t, l.LoadAll(context.Background()))

	rel, ok := l.Get("rel")
	require.True(t, ok)
	assert.Equal(t, "Reloadable v1", rel.Name)

	// Rewrite with a bumped Name.
	mutated := strings.ReplaceAll(string(body), "Reloadable v1", "Reloadable v2")
	require.NoError(t, os.WriteFile(recPath, []byte(mutated), 0o644))

	require.NoError(t, l.Reload(context.Background()))

	rel2, ok := l.Get("rel")
	require.True(t, ok)
	assert.Equal(t, "Reloadable v2", rel2.Name)
}

// TestLoader_DirectoryIDMismatch ensures a recipe whose file-id differs
// from its directory name is rejected (prevents copy-paste drift).
func TestLoader_DirectoryIDMismatch(t *testing.T) {
	// Create a fixture on the fly in a temp dir so we can force the
	// directory name to diverge from the recipe.id field.
	tmp := t.TempDir()
	dir := filepath.Join(tmp, "mismatched")
	require.NoError(t, os.Mkdir(dir, 0o755))
	body := []byte(`id: something-else
name: Mismatched
runtime:
  family: python
install:
  type: pip
  package: pkg
launch:
  cmd: ["pkg", "--help"]
chat_io:
  mode: exec_per_message
  exec_per_message:
    cmd_template: ["pkg", "chat"]
isolation:
  tier: strict
`)
	require.NoError(t, os.WriteFile(filepath.Join(dir, "recipe.yaml"), body, 0o644))

	l := newTestLoader(t, tmp)
	err := l.LoadAll(context.Background())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "directory")
}
