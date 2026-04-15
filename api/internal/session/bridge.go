// Package session's bridge.go hosts the Phase 02.5 Plan 09 bridge
// wiring helpers. Plan 02.5-04 moved the actual ChatBridge
// implementations into api/internal/session/bridge/ as a subpackage;
// this file re-exports the handful of symbols callers still reference
// by their Phase 2 / session-level names.
//
// The Phase 2 LegacyRecipe translation shim that previously lived
// here was deleted by Plan 02.5-09 — the session handler now calls
// bridge.BridgeRegistry.Dispatch directly with the YAML-backed
// *recipes.Recipe. Keeping the re-exports below lets tests that
// already live in the session package reach the subpackage without
// a second import.
package session

import (
	"github.com/agentplayground/api/internal/session/bridge"
)

// ErrTimeout is re-exported from the bridge subpackage so callers
// that do `errors.Is(err, session.ErrTimeout)` keep working. The
// value and identity are preserved across the indirection.
var ErrTimeout = bridge.ErrTimeout

// RunnerExec is an alias for the bridge subpackage's narrow docker
// exec interface. Keeping the Phase 2 name via `type ... =` (alias,
// not new type) means *docker.Runner continues to satisfy both
// session.RunnerExec and bridge.RunnerExec without adapter code.
type RunnerExec = bridge.RunnerExec
