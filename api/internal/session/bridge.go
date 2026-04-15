// Package session's bridge.go is the Phase 2 facade that delegates
// into the new ChatBridge substrate under api/internal/session/bridge/.
// Plan 02.5-04 promoted the fifoMode / execMode bodies into the
// subpackage so Phase 4 can plug new chat-io modes in without touching
// the session handler.
//
// The Phase 2 public surface (session.Bridge, session.NewBridge,
// session.ErrTimeout, session.RunnerExec, the *recipes.LegacyRecipe
// signature on SendMessage) is preserved byte-for-byte so handler.go
// and the Phase 2 integration tests keep compiling and passing. Plan
// 02.5-09 will cut handlers over to the YAML-backed Recipe type and
// delete this shim entirely.
package session

import (
	"context"
	"time"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/agentplayground/api/internal/session/bridge"
	"github.com/rs/zerolog"
)

// ErrTimeout is re-exported from the bridge subpackage so Phase 2
// callers that do `errors.Is(err, session.ErrTimeout)` keep working.
// The value and identity are preserved across the indirection.
var ErrTimeout = bridge.ErrTimeout

// RunnerExec is an alias for the bridge subpackage's narrow docker
// exec interface. Keeping the Phase 2 name via `type ... =` (alias,
// not new type) means *docker.Runner continues to satisfy both
// session.RunnerExec and bridge.RunnerExec without adapter code.
type RunnerExec = bridge.RunnerExec

// Bridge is the Phase 2 facade. Its public shape is unchanged:
// NewBridge(runner) → *Bridge → SendMessage(*LegacyRecipe). Internally
// every call goes through a BridgeRegistry that routes on the new
// chat_io.mode enum after a tiny legacy→YAML recipe adapter.
//
// Adapter responsibility is isolated in synthRecipeFromLegacy below —
// when Plan 02.5-09 rewrites handler.go to use *recipes.Recipe
// directly, this shim (and the adapter) can be deleted in one commit.
type Bridge struct {
	registry *bridge.BridgeRegistry
}

// NewBridge constructs a Bridge backed by the given runner. Phase 2
// callers (cmd/server/main.go, handler_test.go, bridge_test.go) pass
// a single runner argument; the shim silently wires a zerolog.Nop()
// logger into the underlying subpackage so no existing call site
// needs to change.
func NewBridge(r RunnerExec) *Bridge {
	return &Bridge{registry: bridge.NewBridgeRegistry(r, zerolog.Nop())}
}

// SendMessage delivers the user's text to the agent process running
// inside containerID and returns the agent's reply. The dispatch path
// is determined by recipe.ChatIO.Mode (the Phase 2 ChatIOMode values
// "stdin_fifo" / "exec_per_message") — this shim translates those
// into the new Plan 02.5 enum ("fifo" / "exec_per_message") and hands
// off to the BridgeRegistry.
//
// Behavior preserved byte-for-byte from Phase 2:
//   - ErrTimeout is returned on ctx deadline in either mode.
//   - Recipe is cloned, not mutated (the underlying exec bridge uses
//     slices.Clone on its cmd template).
//   - ANSI is stripped from replies.
//   - Text with shell metacharacters is safe: FIFO pipes through
//     stdin, Exec sends argv.
func (b *Bridge) SendMessage(ctx context.Context, containerID string, recipe *recipes.LegacyRecipe, modelID, text string) (string, error) {
	if recipe == nil {
		return "", errNilRecipe
	}

	// Apply the Phase 2 response timeout at the shim layer using the
	// raw time.Duration so sub-second values (e.g. 50ms in
	// TestBridge_Timeout) survive the round-trip through the new
	// Recipe type, whose ResponseTimeoutSec field is int-seconds and
	// would truncate anything below 1s to zero. The synthetic recipe
	// below leaves ResponseTimeoutSec at zero so the downstream
	// FIFOBridge / ExecBridge do not redundantly wrap the context.
	if recipe.ChatIO.ResponseTimeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, recipe.ChatIO.ResponseTimeout)
		defer cancel()
	}

	syn := synthRecipeFromLegacy(recipe)
	modeKey, err := mapLegacyChatIOMode(recipe.ChatIO.Mode)
	if err != nil {
		return "", err
	}

	impl, err := b.registry.Dispatch(modeKey)
	if err != nil {
		return "", err
	}
	return impl.SendMessage(ctx, containerID, syn, modelID, text)
}

// errNilRecipe preserves the Phase 2 error text verbatim. Callers
// like integration_test.go may match on this string; the format is
// kept identical to what Phase 2 bridge.go returned.
var errNilRecipe = &recipeError{msg: "session bridge: nil recipe"}

type recipeError struct{ msg string }

func (e *recipeError) Error() string { return e.msg }

// mapLegacyChatIOMode converts the Phase 2 ChatIOMode constant values
// into the v0.1 YAML-level chat_io.mode strings the BridgeRegistry
// understands. The mapping is static: ChatIOFIFO → "fifo" and
// ChatIOExec → "exec_per_message". Anything else becomes an
// ErrUnsupportedMode wrap so the shim cannot silently misroute.
func mapLegacyChatIOMode(m recipes.ChatIOMode) (string, error) {
	switch m {
	case recipes.ChatIOFIFO:
		return "fifo", nil
	case recipes.ChatIOExec:
		return "exec_per_message", nil
	default:
		return "", bridge.ErrUnsupportedMode
	}
}

// synthRecipeFromLegacy projects a Phase 2 *LegacyRecipe onto a
// minimally populated *recipes.Recipe so the new ChatBridge
// implementations can consume it without a dedicated adapter. Only
// the fields the bridges actually read are filled in: ID, Name,
// ModelFlag, and the ChatIO sub-structs. Everything else stays zero.
//
// This function is intentionally narrow — Plan 02.5-09 deletes both
// this shim and the LegacyRecipe type; there is no value in making
// the translation exhaustive.
func synthRecipeFromLegacy(r *recipes.LegacyRecipe) *recipes.Recipe {
	syn := &recipes.Recipe{
		ID:        r.Name,
		Name:      r.Name,
		ModelFlag: r.ModelFlag,
		ChatIO: recipes.RecipeChatIO{
			ResponseTimeoutSec: int(r.ChatIO.ResponseTimeout / time.Second),
		},
	}
	switch r.ChatIO.Mode {
	case recipes.ChatIOFIFO:
		syn.ChatIO.Mode = "fifo"
		syn.ChatIO.FIFO = &recipes.RecipeChatIOFIFO{
			FIFOIn:    "/run/ap/chat.in",
			FIFOOut:   "/run/ap/chat.out",
			StripANSI: true,
		}
	case recipes.ChatIOExec:
		syn.ChatIO.Mode = "exec_per_message"
		syn.ChatIO.ExecPerMessage = &recipes.RecipeChatIOExec{
			CmdTemplate: r.ChatIO.ExecCmd,
		}
	}
	return syn
}

var _ = context.Background // keep the context import grounded even
// if a future edit drops the SendMessage delegation body.
