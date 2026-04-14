package temporal

import (
	"time"

	"go.temporal.io/sdk/workflow"
)

// PingPong is a trivial workflow proving Temporal wiring end-to-end.
// Submit to the SessionQueue task queue with any workflow ID; the workflow
// executes PingActivity and returns "pong:<input>". Used by the worker_test.go
// suite and by the Plan 01-05 manual verification via `temporal workflow
// execute --type PingPong --task-queue session --input '"hello"'`.
func PingPong(ctx workflow.Context, input string) (string, error) {
	ao := workflow.ActivityOptions{
		StartToCloseTimeout: 10 * time.Second,
	}
	ctx = workflow.WithActivityOptions(ctx, ao)

	var result string
	err := workflow.ExecuteActivity(ctx, PingActivity, input).Get(ctx, &result)
	return result, err
}

// --- Stub workflows for future phases ---------------------------------------
//
// Each stub returns nil after logging "not implemented". Tests in this package
// assert they run to completion, which proves the registration path works.
// Phase 4 / Phase 5 will replace the bodies with real logic; the signatures
// are fixed now so the server/worker wiring does not churn.

// SessionSpawn creates a container, installs a recipe, and transitions the
// session to running. Phase 5 implements the real logic.
func SessionSpawn(ctx workflow.Context, sessionID string) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("SessionSpawn stub: not implemented", "sessionID", sessionID)
	return nil
}

// SessionDestroy stops and removes the session's container and releases
// resources. Phase 5 implements the real logic.
func SessionDestroy(ctx workflow.Context, sessionID string) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("SessionDestroy stub: not implemented", "sessionID", sessionID)
	return nil
}

// RecipeInstall installs a named recipe into a running container. Phase 4
// implements the real logic.
func RecipeInstall(ctx workflow.Context, containerID string, recipeName string) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("RecipeInstall stub: not implemented", "containerID", containerID, "recipe", recipeName)
	return nil
}

// ReconcileContainers compares running Docker containers against the DB
// sessions table and heals divergence. Runs on the reconciliation task queue.
func ReconcileContainers(ctx workflow.Context) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("ReconcileContainers stub: not implemented")
	return nil
}

// ReconcileBilling diffs the local credit ledger against Stripe webhook events
// and heals divergence. Runs on the billing task queue.
func ReconcileBilling(ctx workflow.Context) error {
	logger := workflow.GetLogger(ctx)
	logger.Info("ReconcileBilling stub: not implemented")
	return nil
}
