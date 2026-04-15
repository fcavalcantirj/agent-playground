package recipes

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

// newTestRegistry returns a registry rooted at a fresh temp dir layout that
// matches agents/<id>/templates/. It copies the two valid fixture templates
// under picoclaw so the happy path works without touching the committed
// testdata tree.
func newTestRegistry(t *testing.T) (*TemplateRegistry, string) {
	t.Helper()
	root := t.TempDir()
	recipeDir := filepath.Join(root, "picoclaw", "templates")
	require.NoError(t, os.MkdirAll(recipeDir, 0o755))

	// Copy the committed valid fixtures into the temp tree.
	for _, name := range []string{"security.yml.tmpl", "ok.yml.tmpl"} {
		src := filepath.Join("testdata", "templates", "valid", name)
		data, err := os.ReadFile(src)
		require.NoError(t, err)
		require.NoError(t, os.WriteFile(filepath.Join(recipeDir, name), data, 0o644))
	}
	return NewTemplateRegistry(root), root
}

func TestRender_Valid(t *testing.T) {
	reg, _ := newTestRegistry(t)
	out, err := reg.Render(context.Background(), "picoclaw", "security.yml", map[string]any{
		"secrets": map[string]any{
			"anthropic_key": "sk-ant-foo",
		},
	})
	require.NoError(t, err)
	require.Equal(t, "api_key: \"sk-ant-foo\"\n", out)
}

func TestRender_RejectsUppercase(t *testing.T) {
	root := t.TempDir()
	recipeDir := filepath.Join(root, "picoclaw", "templates")
	require.NoError(t, os.MkdirAll(recipeDir, 0o755))
	require.NoError(t, os.WriteFile(filepath.Join(recipeDir, "UPPERCASE.tmpl"), []byte("hello"), 0o644))
	reg := NewTemplateRegistry(root)
	_, err := reg.Render(context.Background(), "picoclaw", "UPPERCASE", nil)
	require.Error(t, err)
	require.ErrorIs(t, err, ErrTemplatePath)
}

func TestRender_RejectsSymlink(t *testing.T) {
	root := t.TempDir()
	recipeDir := filepath.Join(root, "picoclaw", "templates")
	require.NoError(t, os.MkdirAll(recipeDir, 0o755))
	// Target lives outside the templates dir.
	outside := filepath.Join(root, "outside.tmpl")
	require.NoError(t, os.WriteFile(outside, []byte("evil"), 0o644))
	require.NoError(t, os.Symlink(outside, filepath.Join(recipeDir, "link.tmpl")))
	reg := NewTemplateRegistry(root)
	_, err := reg.Render(context.Background(), "picoclaw", "link", nil)
	require.Error(t, err)
	require.ErrorIs(t, err, ErrTemplatePath)
}

func TestRender_RejectsPathEscape(t *testing.T) {
	reg, _ := newTestRegistry(t)
	// The regex catches traversal attempts before the Lstat check.
	_, err := reg.Render(context.Background(), "picoclaw", "../../../etc/passwd", nil)
	require.Error(t, err)
	require.ErrorIs(t, err, ErrTemplatePath)

	// Also try a backslash to ensure the allowlist is tight.
	_, err = reg.Render(context.Background(), "picoclaw", "bad/name", nil)
	require.Error(t, err)
	require.ErrorIs(t, err, ErrTemplatePath)
}

func TestRender_MissingKeyError(t *testing.T) {
	root := t.TempDir()
	recipeDir := filepath.Join(root, "picoclaw", "templates")
	require.NoError(t, os.MkdirAll(recipeDir, 0o755))
	require.NoError(t, os.WriteFile(
		filepath.Join(recipeDir, "missing.yml.tmpl"),
		[]byte("api_key: {{ .secrets.missing }}\n"),
		0o644,
	))
	reg := NewTemplateRegistry(root)
	_, err := reg.Render(context.Background(), "picoclaw", "missing.yml", map[string]any{
		"secrets": map[string]any{},
	})
	require.Error(t, err)
	require.Contains(t, err.Error(), "map has no entry")
}

func TestRender_OversizedOutput(t *testing.T) {
	root := t.TempDir()
	recipeDir := filepath.Join(root, "picoclaw", "templates")
	require.NoError(t, os.MkdirAll(recipeDir, 0o755))
	// `range .` over a 100000-element slice renders X each — hits 64 KiB cap.
	require.NoError(t, os.WriteFile(
		filepath.Join(recipeDir, "huge.tmpl"),
		[]byte("{{ range . }}X{{ end }}"),
		0o644,
	))
	reg := NewTemplateRegistry(root)
	data := make([]struct{}, 100000)
	_, err := reg.Render(context.Background(), "picoclaw", "huge", data)
	require.Error(t, err)
	require.ErrorIs(t, err, ErrTemplateSize)
}

func TestRender_Timeout(t *testing.T) {
	reg, _ := newTestRegistry(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel() // immediately cancelled → the select fires the ctx.Done branch
	_, err := reg.Render(ctx, "picoclaw", "security.yml", map[string]any{
		"secrets": map[string]any{"anthropic_key": "sk"},
	})
	require.Error(t, err)
	require.ErrorIs(t, err, ErrTemplateTimeout)
}

func TestRender_DefaultFunc(t *testing.T) {
	root := t.TempDir()
	recipeDir := filepath.Join(root, "picoclaw", "templates")
	require.NoError(t, os.MkdirAll(recipeDir, 0o755))
	require.NoError(t, os.WriteFile(
		filepath.Join(recipeDir, "default.tmpl"),
		[]byte(`{{ default "fallback" .value }}`),
		0o644,
	))
	reg := NewTemplateRegistry(root)
	// nil value → default
	out, err := reg.Render(context.Background(), "picoclaw", "default", map[string]any{
		"value": nil,
	})
	require.NoError(t, err)
	require.Equal(t, "fallback", out)

	// empty string → default
	out, err = reg.Render(context.Background(), "picoclaw", "default", map[string]any{
		"value": "",
	})
	require.NoError(t, err)
	require.Equal(t, "fallback", out)

	// real value → passthrough
	out, err = reg.Render(context.Background(), "picoclaw", "default", map[string]any{
		"value": "real",
	})
	require.NoError(t, err)
	require.Equal(t, "real", out)
}

func TestRender_StringFuncs(t *testing.T) {
	root := t.TempDir()
	recipeDir := filepath.Join(root, "picoclaw", "templates")
	require.NoError(t, os.MkdirAll(recipeDir, 0o755))
	require.NoError(t, os.WriteFile(
		filepath.Join(recipeDir, "funcs.tmpl"),
		[]byte(`{{ lower .a }}|{{ upper .b }}|{{ trim .c }}`),
		0o644,
	))
	reg := NewTemplateRegistry(root)
	out, err := reg.Render(context.Background(), "picoclaw", "funcs", map[string]any{
		"a": "HELLO",
		"b": "world",
		"c": "  spaced  ",
	})
	require.NoError(t, err)
	require.Equal(t, "hello|WORLD|spaced", out)
}

func TestCache_MtimeInvalidates(t *testing.T) {
	root := t.TempDir()
	recipeDir := filepath.Join(root, "picoclaw", "templates")
	require.NoError(t, os.MkdirAll(recipeDir, 0o755))
	path := filepath.Join(recipeDir, "cache.tmpl")
	require.NoError(t, os.WriteFile(path, []byte("v1"), 0o644))
	reg := NewTemplateRegistry(root)

	out, err := reg.Render(context.Background(), "picoclaw", "cache", nil)
	require.NoError(t, err)
	require.Equal(t, "v1", out)
	require.Equal(t, 1, reg.ParseCountForTest())

	// Second render hits the cache — parse count unchanged.
	out, err = reg.Render(context.Background(), "picoclaw", "cache", nil)
	require.NoError(t, err)
	require.Equal(t, "v1", out)
	require.Equal(t, 1, reg.ParseCountForTest())

	// Rewrite with a NEW mtime. Sleep past filesystem mtime resolution,
	// then Chtimes to a deterministic future time.
	require.NoError(t, os.WriteFile(path, []byte("v2"), 0o644))
	future := time.Now().Add(2 * time.Second)
	require.NoError(t, os.Chtimes(path, future, future))

	out, err = reg.Render(context.Background(), "picoclaw", "cache", nil)
	require.NoError(t, err)
	require.Equal(t, "v2", out)
	require.Equal(t, 2, reg.ParseCountForTest())
}

// Sanity check: errors use sentinels so callers can type-assert.
func TestSentinelErrors_AreDistinct(t *testing.T) {
	require.True(t, errors.Is(ErrTemplatePath, ErrTemplatePath))
	require.True(t, errors.Is(ErrTemplateSize, ErrTemplateSize))
	require.True(t, errors.Is(ErrTemplateTimeout, ErrTemplateTimeout))
	require.False(t, errors.Is(ErrTemplatePath, ErrTemplateSize))
	// quick strings.Contains check just to keep the strings import live.
	require.True(t, strings.Contains(ErrTemplatePath.Error(), "template"))
}
