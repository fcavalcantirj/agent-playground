// Package bridge hosts the ChatBridge interface and its two v0.1
// implementations (FIFOBridge, ExecBridge) plus the BridgeRegistry
// that maps recipe.ChatIO.Mode values onto a concrete bridge. Phase 2
// shipped the bridge logic as inline methods on session.Bridge; Plan
// 02.5-04 promotes those bodies into this package verbatim so Phase 4
// can plug new modes in by adding one struct + one registry entry.
//
// LIFT-DON'T-INVENT RULE. The FIFO and exec bodies are byte-equivalent
// ports of Phase 2's session/bridge.go fifoMode / execMode functions.
// The THREAT NOTES T-02-04 / T-02-04b (shell-safety invariants) must
// be preserved verbatim — any "cleanup" is strictly out of scope and
// is deferred to Plan 09 of Phase 02.5.
package bridge

import (
	"context"
	"errors"
	"io"
	"strings"

	"github.com/agentplayground/api/internal/recipes"
)

// ErrTimeout signals that the agent did not respond within the
// recipe's ChatIO.ResponseTimeoutSec window. The session handler maps
// this to HTTP 504 Gateway Timeout. Value preserved byte-for-byte from
// Phase 2's session.ErrTimeout — the session package re-exports this
// symbol via the shim so Plan 02 callers keep working unchanged.
var ErrTimeout = errors.New("agent response timeout")

// ErrUnsupportedMode is the defense-in-depth error the BridgeRegistry
// returns when asked to dispatch a chat_io.mode value that does not
// map to a concrete ChatBridge. Plan 01's JSON Schema enforces the
// closed enum {fifo, exec_per_message}; this error path should be
// unreachable under normal flow but protects against future flavor
// files that bypass the validator.
var ErrUnsupportedMode = errors.New("unsupported chat_io.mode")

// RunnerExec is the narrow subset of *docker.Runner the chat bridge
// depends on. Defined here so bridge_test.go can inject a mock without
// touching the Docker daemon; production code passes a *docker.Runner
// which satisfies the interface structurally.
//
// Signature lifted unchanged from Phase 2 session.RunnerExec — Exec
// returns ([]byte, error) and ExecWithStdin takes an io.Reader for the
// stdin stream.
type RunnerExec interface {
	Exec(ctx context.Context, containerID string, cmd []string) ([]byte, error)
	ExecWithStdin(ctx context.Context, containerID string, cmd []string, stdin io.Reader) ([]byte, error)
}

// ChatBridge is the single-method contract every chat-io mode
// implements. Callers pass the full Recipe pointer so implementations
// can read mode-specific sub-structs (RecipeChatIOFIFO /
// RecipeChatIOExec) without the dispatcher needing to know the shape.
//
// The contract is deliberately minimal: "given a container, a recipe,
// an optional modelID, and user text, return the agent's reply or an
// error". Timeouts are honored via ctx; ErrTimeout is the sentinel the
// session handler maps to 504.
type ChatBridge interface {
	SendMessage(ctx context.Context, containerID string, recipe *recipes.Recipe, modelID, text string) (string, error)
}

// StripANSI removes simple CSI escape sequences (e.g. `\x1b[31m`) from
// a string. Hermes prints colored output by default; picoclaw emits
// reset sequences around its prompts; the API layer returns plain
// text to the client so we normalize here.
//
// This is intentionally not a full ECMA-48 parser — it handles the
// common `\x1b[<params><letter>` form which is what the upstream
// agents emit. If a future recipe emits OSC or DCS sequences, add a
// more sophisticated stripper; for Phase 2 / 02.5 this covers the
// shipped recipes. Body lifted byte-for-byte from Phase 2
// session/bridge.go#stripANSI.
func StripANSI(s string) string {
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
