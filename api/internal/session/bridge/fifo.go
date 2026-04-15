package bridge

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/rs/zerolog"
)

// Phase 2 hardcoded the FIFO paths at /run/ap/chat.in and
// /run/ap/chat.out. The YAML-backed Recipe type lets a recipe override
// them, so this package honors RecipeChatIOFIFO.FIFOIn /.FIFOOut when
// set and falls back to the Phase 2 defaults otherwise. This keeps the
// legacy shim (see api/internal/session/bridge.go) byte-equivalent to
// Phase 2 behavior for the picoclaw + hermes catalog entries.
const (
	defaultFIFOIn  = "/run/ap/chat.in"
	defaultFIFOOut = "/run/ap/chat.out"
)

// FIFOBridge is the ChatBridge implementation for recipes whose agent
// runs long-lived inside the container with stdin/stdout plumbed into
// a pair of named pipes. Picoclaw is the canonical consumer: its agent
// process reads user turns from /run/ap/chat.in and appends replies to
// /run/ap/chat.out.
//
// Phase 2 shipped the logic as session.(*Bridge).fifoMode; this struct
// wraps the same body verbatim so Phase 4's additional modes
// (one_shot_task, http_gateway) plug in as siblings without touching
// the FIFO code path.
type FIFOBridge struct {
	runner RunnerExec
	logger zerolog.Logger
}

// NewFIFOBridge constructs a FIFOBridge backed by the given runner.
// The logger is currently unused by the lifted body but is held for
// Plan 09's observability pass (structured message logs).
func NewFIFOBridge(r RunnerExec, logger zerolog.Logger) *FIFOBridge {
	return &FIFOBridge{runner: r, logger: logger}
}

// SendMessage writes the user text to the recipe's FIFO-in pipe via
// stdin-pipe'd `cat` and then polls the FIFO-out pipe for a reply.
//
// THREAT NOTE (T-02-04 / T-02.5-05): the user text NEVER becomes
// shell arguments. Bytes on stdin are not interpreted by `sh` — they
// are handed verbatim to `cat` which copies them to the FIFO. The
// argv the shell sees is the constant `["sh","-c","cat >> <fifo_in>"]`
// where `<fifo_in>` is taken from the recipe (or the Phase 2 default)
// — never from user-controlled input.
//
// Body lifted byte-for-byte from Phase 2 session/bridge.go#fifoMode.
// Deviations from the literal port:
//   - FIFO paths are pulled from recipe.ChatIO.FIFO (with Phase 2
//     defaults) instead of the hardcoded constants Phase 2 used —
//     this is a zero-behavior change when the recipe is empty.
//   - ResponseTimeout is derived from recipe.ChatIO.ResponseTimeoutSec
//     (int seconds) rather than the Phase 2 time.Duration field;
//     zero/absent means "use the caller's ctx unchanged".
func (b *FIFOBridge) SendMessage(ctx context.Context, containerID string, recipe *recipes.Recipe, modelID, text string) (string, error) {
	if recipe == nil {
		return "", fmt.Errorf("fifo bridge: nil recipe")
	}

	fifoIn := defaultFIFOIn
	fifoOut := defaultFIFOOut
	if recipe.ChatIO.FIFO != nil {
		if recipe.ChatIO.FIFO.FIFOIn != "" {
			fifoIn = recipe.ChatIO.FIFO.FIFOIn
		}
		if recipe.ChatIO.FIFO.FIFOOut != "" {
			fifoOut = recipe.ChatIO.FIFO.FIFOOut
		}
	}

	if recipe.ChatIO.ResponseTimeoutSec > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, time.Duration(recipe.ChatIO.ResponseTimeoutSec)*time.Second)
		defer cancel()
	}

	payload := bytes.NewReader([]byte(text + "\n"))
	if _, err := b.runner.ExecWithStdin(
		ctx, containerID,
		[]string{"sh", "-c", "cat >> " + fifoIn},
		payload,
	); err != nil {
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return "", ErrTimeout
		}
		return "", fmt.Errorf("fifo bridge: write: %w", err)
	}

	// Poll FIFO-out until non-empty or context expires. Each probe
	// runs `timeout 5 head -n 1 <fifo_out>` so a dead agent cannot
	// block the docker exec indefinitely; the outer context still
	// caps total wall time. Lifted verbatim from Phase 2.
	for {
		if err := ctx.Err(); err != nil {
			return "", ErrTimeout
		}
		out, err := b.runner.Exec(
			ctx, containerID,
			[]string{"timeout", "5", "head", "-n", "1", fifoOut},
		)
		if err == nil && len(bytes.TrimSpace(out)) > 0 {
			// Phase 2 unconditionally stripped ANSI; lift unchanged.
			// RecipeChatIOFIFO.StripANSI is intentionally not consulted
			// because the lift-don't-invent rule forbids behavior
			// changes mid-refactor. Plan 09 may flip this once
			// handlers are cut over.
			return StripANSI(strings.TrimSpace(string(out))), nil
		}
		select {
		case <-ctx.Done():
			return "", ErrTimeout
		case <-time.After(25 * time.Millisecond):
		}
	}
}

