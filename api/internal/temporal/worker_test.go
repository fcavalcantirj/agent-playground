package temporal

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.temporal.io/sdk/testsuite"
)

// TestPingPong proves the full Temporal wiring: a workflow invokes an
// activity, the activity returns, and the workflow returns the result. This
// is the Phase 1 liveness proof -- if this passes, Plan 01-05 has done its
// job of getting Temporal actually executing code, not just compiling.
//
// The test uses go.temporal.io/sdk/testsuite, which runs workflows in an
// in-memory environment with no real Temporal server required. We still have
// to explicitly register the activity; the SDK does not auto-discover them in
// the test environment.
func TestPingPong(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()
	env.RegisterActivity(PingActivity)

	env.ExecuteWorkflow(PingPong, "hello")

	require.True(t, env.IsWorkflowCompleted(), "PingPong workflow did not complete")
	require.NoError(t, env.GetWorkflowError(), "PingPong workflow returned an error")

	var result string
	require.NoError(t, env.GetWorkflowResult(&result))
	assert.Equal(t, "pong:hello", result)
}

// TestSessionSpawnStub asserts the SessionSpawn stub workflow is registrable
// and runs to completion. Phase 5 will replace the body; the registration path
// must stay green.
func TestSessionSpawnStub(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	env.ExecuteWorkflow(SessionSpawn, "test-session-id")

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())
}

// TestSessionDestroyStub mirrors TestSessionSpawnStub for SessionDestroy.
func TestSessionDestroyStub(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	env.ExecuteWorkflow(SessionDestroy, "test-session-id")

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())
}

// TestRecipeInstallStub covers the RecipeInstall stub workflow. It will be
// replaced in Phase 4 but the registration path must not regress.
func TestRecipeInstallStub(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	env.ExecuteWorkflow(RecipeInstall, "container-abc", "claude-code")

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())
}

// TestReconcileContainersStub covers the reconciliation-queue workflow.
func TestReconcileContainersStub(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	env.ExecuteWorkflow(ReconcileContainers)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())
}

// TestReconcileBillingStub covers the billing-queue workflow.
func TestReconcileBillingStub(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	env.ExecuteWorkflow(ReconcileBilling)

	require.True(t, env.IsWorkflowCompleted())
	require.NoError(t, env.GetWorkflowError())
}

// TestQueueConstants locks in the task-queue string values so nothing silently
// renames them. Other services (Phase 5 session handlers, tctl verification
// scripts) encode these strings.
func TestQueueConstants(t *testing.T) {
	assert.Equal(t, "session", SessionQueue)
	assert.Equal(t, "billing", BillingQueue)
	assert.Equal(t, "reconciliation", ReconciliationQueue)
}
