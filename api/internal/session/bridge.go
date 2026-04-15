package session

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"slices"
	"strings"
	"time"

	"github.com/agentplayground/api/internal/recipes"
)

// ErrTimeout means the agent did not respond within the recipe's
// ChatIO.ResponseTimeout. Plan 05's message handler maps this to
// HTTP 504 Gateway Timeout.
var ErrTimeout = errors.New("agent response timeout")

// RunnerExec is the minimal subset of *docker.Runner the chat bridge
// needs. It exists so bridge_test.go can inject a mock without touching
// the real Docker daemon; production wiring passes a *docker.Runner.
//
// Signature MUST match the real Runner methods exactly (see
// api/pkg/docker/runner.go) — Exec returns ([]byte, error), and
// ExecWithStdin takes an io.Reader for the stdin stream.
type RunnerExec interface {
	Exec(ctx context.Context, containerID string, cmd []string) ([]byte, error)
	ExecWithStdin(ctx context.Context, containerID string, cmd []string, stdin io.Reader) ([]byte, error)
}

// Bridge dispatches chat messages into a running container, choosing
// between the FIFO path (picoclaw — long-lived agent reading from
// /run/ap/chat.in) and the exec-per-message path (Hermes — one docker
// exec invocation per message) based on the recipe's ChatIO.Mode.
//
// The struct is tiny by design: it owns no state other than the
// injected runner, so multiple concurrent Bridge calls against the same
// container are safe as long as the underlying runner is.
type Bridge struct {
	runner RunnerExec
}

// NewBridge constructs a Bridge backed by the given runner.
func NewBridge(r RunnerExec) *Bridge {
	return &Bridge{runner: r}
}

// SendMessage delivers the user's text to the agent process running
// inside containerID and returns the agent's reply. The dispatch path
// is determined by recipe.ChatIO.Mode:
//
//   - ChatIOFIFO  — write text to /run/ap/chat.in via ExecWithStdin
//     using `sh -c 'cat >> /run/ap/chat.in'`, then poll
//     /run/ap/chat.out until a reply arrives or the context expires.
//   - ChatIOExec — clone recipe.ChatIO.ExecCmd, append the user text
//     as a single final argv element, and exec it via Runner.Exec.
//
// The context is wrapped with recipe.ChatIO.ResponseTimeout so callers
// that pass a longer-lived context still honor the per-recipe cap.
// Timeouts surface as ErrTimeout (HTTP 504 at the handler layer).
func (b *Bridge) SendMessage(ctx context.Context, containerID string, recipe *recipes.LegacyRecipe, modelID, text string) (string, error) {
	if recipe == nil {
		return "", fmt.Errorf("session bridge: nil recipe")
	}
	if recipe.ChatIO.ResponseTimeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, recipe.ChatIO.ResponseTimeout)
		defer cancel()
	}

	switch recipe.ChatIO.Mode {
	case recipes.ChatIOExec:
		return b.execMode(ctx, containerID, recipe, modelID, text)
	case recipes.ChatIOFIFO:
		return b.fifoMode(ctx, containerID, recipe, text)
	default:
		return "", fmt.Errorf("session bridge: unknown chat io mode: %q", recipe.ChatIO.Mode)
	}
}

// execMode runs the recipe's ExecCmd with the user text appended as a
// single final argv element. slices.Clone prevents accidental mutation
// of the recipe's shared ExecCmd slice.
//
// THREAT NOTE (T-02-04b): the Docker SDK passes cmd as []string
// directly to dockerd over the daemon HTTP API — there is NO shell
// between Go and the container's exec layer. The user text therefore
// cannot be interpreted as shell metacharacters even if it contains
// `;`, `$()`, or backticks.
func (b *Bridge) execMode(ctx context.Context, containerID string, recipe *recipes.LegacyRecipe, modelID, text string) (string, error) {
	cmd := slices.Clone(recipe.ChatIO.ExecCmd)
	if recipe.ModelFlag != "" && modelID != "" {
		cmd = append(cmd, recipe.ModelFlag, modelID)
	}
	cmd = append(cmd, text)
	out, err := b.runner.Exec(ctx, containerID, cmd)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return "", ErrTimeout
		}
		return "", fmt.Errorf("session bridge: exec: %w", err)
	}
	return stripANSI(strings.TrimSpace(string(out))), nil
}

// fifoMode writes the user text to /run/ap/chat.in via stdin-pipe'd
// `cat` and then polls /run/ap/chat.out for a reply. The `cat` shell
// invocation is SAFE because the user text flows over stdin — the
// shell only sees the literal string `cat >> /run/ap/chat.in`.
//
// THREAT NOTE (T-02-04): the user text NEVER becomes shell arguments.
// Bytes on stdin are not interpreted by `sh` — they are handed verbatim
// to `cat` which copies them to the FIFO.
func (b *Bridge) fifoMode(ctx context.Context, containerID string, recipe *recipes.LegacyRecipe, text string) (string, error) {
	payload := bytes.NewReader([]byte(text + "\n"))
	if _, err := b.runner.ExecWithStdin(
		ctx, containerID,
		[]string{"sh", "-c", "cat >> /run/ap/chat.in"},
		payload,
	); err != nil {
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return "", ErrTimeout
		}
		return "", fmt.Errorf("session bridge: fifo write: %w", err)
	}

	// Poll chat.out until non-empty or context expires. Each probe runs
	// `timeout 5 head -n 1 /run/ap/chat.out` so a dead agent cannot
	// block the docker exec indefinitely; the outer context still caps
	// total wall time.
	for {
		if err := ctx.Err(); err != nil {
			return "", ErrTimeout
		}
		out, err := b.runner.Exec(
			ctx, containerID,
			[]string{"timeout", "5", "head", "-n", "1", "/run/ap/chat.out"},
		)
		if err == nil && len(bytes.TrimSpace(out)) > 0 {
			return stripANSI(strings.TrimSpace(string(out))), nil
		}
		select {
		case <-ctx.Done():
			return "", ErrTimeout
		case <-time.After(25 * time.Millisecond):
		}
	}
}

// stripANSI removes simple CSI escape sequences (e.g. `\x1b[31m`) from
// a string. Hermes prints colored output by default; the API layer
// returns plain text to the client so we normalize here.
//
// This is intentionally not a full ECMA-48 parser — it handles the
// common `\x1b[<params><letter>` form which is what the upstream
// agents emit. If a future recipe emits OSC or DCS sequences, add a
// more sophisticated stripper; for Phase 2 this covers the two
// shipped recipes.
func stripANSI(s string) string {
	var out strings.Builder
	out.Grow(len(s))
	inEscape := false
	for _, r := range s {
		if r == '\x1b' {
			inEscape = true
			continue
		}
		if inEscape {
			// CSI params are digits, `;`, `[`, etc. Terminates on
			// any ASCII letter (e.g. 'm', 'A', 'K').
			if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') {
				inEscape = false
			}
			continue
		}
		out.WriteRune(r)
	}
	return out.String()
}
