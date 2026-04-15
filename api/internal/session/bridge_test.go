package session_test

// bridge_test.go — smoke tests against the bridge subpackage through
// the session package's re-exported symbols. Plan 02.5-09 deleted the
// legacy session.Bridge shim and the LegacyRecipe translation that
// used to live here; the authoritative per-mode tests now live in
// api/internal/session/bridge/ alongside the implementations.
//
// This file keeps the re-exports covered by compile-time assertions
// so any future rename surfaces at build time.

import (
	"testing"

	"github.com/agentplayground/api/internal/session"
	"github.com/agentplayground/api/internal/session/bridge"
	"github.com/stretchr/testify/assert"
)

// Compile-time assertion: session.RunnerExec is an alias of the
// bridge subpackage interface. `type X = Y` aliases satisfy each
// other's method sets, so a var declared as session.RunnerExec can
// hold a bridge.RunnerExec value only if the alias is intact.
var _ session.RunnerExec = (bridge.RunnerExec)(nil)

// TestSession_ErrTimeoutReexport pins session.ErrTimeout to the
// bridge subpackage value so handler code that does
// `errors.Is(err, session.ErrTimeout)` continues to match bridge
// returns after the re-export path.
func TestSession_ErrTimeoutReexport(t *testing.T) {
	assert.NotNil(t, session.ErrTimeout, "session.ErrTimeout must resolve")
	assert.Same(t, session.ErrTimeout, bridge.ErrTimeout,
		"session.ErrTimeout must point at bridge.ErrTimeout after re-export")
}
