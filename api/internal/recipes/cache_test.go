package recipes_test

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/require"
)

// TestSIGHUPSignal wires StartSIGHUPWatcher to a Loader pointing at a
// temp dir, mutates the underlying file, self-sends SIGHUP, and polls
// the cache for the reloaded value. This proves signal.Notify is
// wired and Reload runs atomically on signal delivery.
func TestSIGHUPSignal(t *testing.T) {
	// Set up a mutable on-disk fixture.
	src := filepath.Join("testdata", "fixtures", "reload", "rel", "recipe.yaml")
	body, err := os.ReadFile(src)
	require.NoError(t, err)

	tmp := t.TempDir()
	relDir := filepath.Join(tmp, "rel")
	require.NoError(t, os.Mkdir(relDir, 0o755))
	recPath := filepath.Join(relDir, "recipe.yaml")
	require.NoError(t, os.WriteFile(recPath, body, 0o644))

	v, err := recipes.NewSchemaValidator()
	require.NoError(t, err)
	l := recipes.NewLoader(tmp, v, zerolog.Nop())
	require.NoError(t, l.LoadAll(context.Background()))

	before, ok := l.Get("rel")
	require.True(t, ok)
	require.Equal(t, "Reloadable v1", before.Name)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	recipes.StartSIGHUPWatcher(ctx, l, zerolog.Nop())

	// Give signal.Notify time to install the handler before we fire.
	time.Sleep(20 * time.Millisecond)

	// Mutate file + deliver SIGHUP to ourselves.
	mutated := strings.ReplaceAll(string(body), "Reloadable v1", "Reloadable via SIGHUP")
	require.NoError(t, os.WriteFile(recPath, []byte(mutated), 0o644))

	proc, err := os.FindProcess(os.Getpid())
	require.NoError(t, err)
	require.NoError(t, proc.Signal(syscall.SIGHUP))

	// Poll up to 1s for the reload to land.
	deadline := time.Now().Add(1 * time.Second)
	for time.Now().Before(deadline) {
		after, ok := l.Get("rel")
		if ok && after.Name == "Reloadable via SIGHUP" {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("SIGHUP did not trigger reload within 1s; cache still shows old value")
}
