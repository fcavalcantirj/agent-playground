// Package temporal wires the Temporal SDK into the Go API: a client, three
// workers (session, billing, reconciliation task queues), and a set of stub
// workflows that Phase 4 and Phase 5 will fill in.
//
// Plan 01-05 creates this package. Phase 1's only functional workflow is
// PingPong, which proves end-to-end wiring from a workflow submission through
// an activity back to a result. Every other workflow here is a stub that logs
// "not implemented" and returns nil (or returns an explicit error for
// activities, so a stray caller sees the gap loudly).
package temporal

import (
	"context"
	"fmt"
)

// PingActivity is a trivial activity that returns "pong:<input>".
// It exists purely to prove Temporal's activity-execution path is wired up
// end-to-end in Phase 1. Remove in a later phase if no tests reference it.
func PingActivity(ctx context.Context, input string) (string, error) {
	return fmt.Sprintf("pong:%s", input), nil
}

// --- Stub activities for future phases --------------------------------------

// SpawnContainerActivity will wrap pkg/docker/runner.Run in Phase 5.
// The stub returns an explicit error so any accidental caller in Phase 1 fails
// loudly instead of silently succeeding with empty data.
func SpawnContainerActivity(ctx context.Context, sessionID string) (string, error) {
	return "", fmt.Errorf("SpawnContainerActivity not implemented (Phase 5)")
}

// DestroyContainerActivity will wrap pkg/docker/runner.Stop + Remove in Phase 5.
func DestroyContainerActivity(ctx context.Context, containerID string) error {
	return fmt.Errorf("DestroyContainerActivity not implemented (Phase 5)")
}

// InstallRecipeActivity will install a recipe into a running container in Phase 4.
func InstallRecipeActivity(ctx context.Context, containerID string, recipeName string) error {
	return fmt.Errorf("InstallRecipeActivity not implemented (Phase 4)")
}
