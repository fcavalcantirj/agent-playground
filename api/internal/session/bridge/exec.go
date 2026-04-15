package bridge

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/rs/zerolog"
)

// ExecBridge is the ChatBridge implementation for recipes whose agent
// binary is invoked fresh per user turn via `docker exec`. Hermes is
// the canonical consumer: its CLI runs `hermes chat -q "<msg>"` once
// and prints the reply to stdout, then exits.
//
// Phase 2 shipped this logic as session.(*Bridge).execMode. This
// struct holds the exact same body so Phase 4's additional modes can
// plug in as siblings without touching exec path.
type ExecBridge struct {
	runner RunnerExec
	logger zerolog.Logger
}

// NewExecBridge constructs an ExecBridge backed by the given runner.
// The logger is reserved for Plan 09's structured message logs.
func NewExecBridge(r RunnerExec, logger zerolog.Logger) *ExecBridge {
	return &ExecBridge{runner: r, logger: logger}
}

// SendMessage clones the recipe's cmd template, appends the optional
// modelFlag+modelID pair, appends the user text as the final argv
// element, and exec's it via RunnerExec.Exec.
//
// THREAT NOTE (T-02-04b / T-02.5-05a): the Docker SDK passes cmd as
// []string directly to dockerd over the daemon HTTP API — there is NO
// shell between Go and the container's exec layer. The user text
// therefore cannot be interpreted as shell metacharacters even if it
// contains `;`, `$()`, or backticks. The lift-don't-invent rule
// requires this invariant to hold byte-for-byte: the user text MUST
// land in its own argv slice element, never concatenated into a
// pre-formed command string.
//
// Body lifted byte-for-byte from Phase 2 session/bridge.go#execMode.
// Deviations from the literal port:
//   - Template is read from recipe.ChatIO.ExecPerMessage.CmdTemplate
//     instead of recipe.ChatIO.ExecCmd — same shape, new home.
//   - ResponseTimeout is derived from ResponseTimeoutSec (int seconds)
//     rather than a time.Duration field; zero means "use caller's ctx".
func (b *ExecBridge) SendMessage(ctx context.Context, containerID string, recipe *recipes.Recipe, modelID, text string) (string, error) {
	if recipe == nil {
		return "", fmt.Errorf("exec bridge: nil recipe")
	}
	if recipe.ChatIO.ExecPerMessage == nil {
		return "", fmt.Errorf("exec bridge: recipe %q has chat_io.mode=exec_per_message but no chat_io.exec_per_message block", recipe.ID)
	}

	if recipe.ChatIO.ResponseTimeoutSec > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, time.Duration(recipe.ChatIO.ResponseTimeoutSec)*time.Second)
		defer cancel()
	}

	// Build the exec argv. We support two shapes for cmd_template:
	//
	//   (a) Positional append — the original Phase 2 shape. Recipe
	//       just lists the base cmd; the bridge appends `<model-flag>
	//       <model-id> <text>` at the end. Works for Hermes where text
	//       is the last positional arg and model flag comes last.
	//
	//   (b) Placeholder substitution — if the template contains the
	//       literal "{text}" and/or "{model}" elements, they are
	//       replaced in-place by the user text / model id. This is
	//       required for recipes like aider where --message VALUE must
	//       sit next to its flag and --model VALUE must sit next to
	//       its flag — the Phase 2 "append at end" order produces a
	//       malformed argv otherwise.
	//
	// The argv-invariant (T-02-04b / T-02.5-05a) still holds: the
	// user text is replaced into its own argv slice element, never
	// concatenated into a pre-formed command string.
	tmpl := slices.Clone(recipe.ChatIO.ExecPerMessage.CmdTemplate)
	hasTextPH := false
	hasModelPH := false
	for _, el := range tmpl {
		if el == "{text}" {
			hasTextPH = true
		}
		if el == "{model}" {
			hasModelPH = true
		}
	}

	cmd := make([]string, 0, len(tmpl)+4)
	for _, el := range tmpl {
		switch el {
		case "{text}":
			cmd = append(cmd, text)
		case "{model}":
			cmd = append(cmd, modelID)
		default:
			cmd = append(cmd, el)
		}
	}

	if !hasModelPH && recipe.ModelFlag != "" && modelID != "" {
		cmd = append(cmd, recipe.ModelFlag, modelID)
	}
	if !hasTextPH {
		cmd = append(cmd, text)
	}

	out, err := b.runner.Exec(ctx, containerID, cmd)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return "", ErrTimeout
		}
		return "", fmt.Errorf("exec bridge: %w", err)
	}
	return StripANSI(strings.TrimSpace(string(out))), nil
}
