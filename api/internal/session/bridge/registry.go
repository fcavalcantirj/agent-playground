package bridge

import (
	"fmt"

	"github.com/rs/zerolog"
)

// BridgeRegistry maps a recipe's chat_io.mode string onto the
// concrete ChatBridge implementation that handles that mode. The keys
// are the v0.1 closed-enum values D-10 locked down: "fifo" and
// "exec_per_message". Plan 01's JSON Schema rejects any other value
// at load time, but BridgeRegistry.Dispatch also returns
// ErrUnsupportedMode as defense in depth.
//
// Phase 4 extends this by adding a new struct (e.g. HTTPGatewayBridge)
// and a single line in NewBridgeRegistry — no session handler code
// needs to move.
type BridgeRegistry struct {
	bridges map[string]ChatBridge
}

// NewBridgeRegistry wires the v0.1 chat-io modes to their concrete
// implementations. The runner is shared — every bridge calls the
// same *docker.Runner in production.
func NewBridgeRegistry(runner RunnerExec, logger zerolog.Logger) *BridgeRegistry {
	return &BridgeRegistry{
		bridges: map[string]ChatBridge{
			"fifo":             NewFIFOBridge(runner, logger),
			"exec_per_message": NewExecBridge(runner, logger),
		},
	}
}

// Dispatch returns the ChatBridge registered for the given
// chat_io.mode value, or ErrUnsupportedMode wrapped with the rejected
// mode string. Callers should surface a chat_bridge_unsupported_mode
// error envelope at the HTTP layer (Plan 09).
func (r *BridgeRegistry) Dispatch(mode string) (ChatBridge, error) {
	b, ok := r.bridges[mode]
	if !ok {
		return nil, fmt.Errorf("%w: %q", ErrUnsupportedMode, mode)
	}
	return b, nil
}
