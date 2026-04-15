package docker

// runner_lifecycle.go — the Dev Containers 6-hook sequencer.
//
// Phase 02.5 Plan 03 adds RunWithLifecycle as a NEW method on the
// existing *Runner type. Phase 2's Runner.Run / Runner.Exec / Runner.Stop
// / Runner.Remove are untouched; this file only orchestrates them plus
// the host-side initializeCommand step.
//
// Hook execution order (D-25, Dev Containers spec):
//
//	1. initializeCommand    — on HOST, before container create (os/exec)
//	2. (container create)   — via Runner.Run
//	3. onCreateCommand      — in-container, skipped if ap.already-created label
//	4. updateContentCommand — in-container
//	5. postCreateCommand    — in-container; default waitFor target
//	6. postStartCommand     — in-container
//	7. postAttachCommand    — in-container
//
// waitFor gating (D-25): once the hook named by recipe.Lifecycle.WaitFor
// completes successfully, LifecycleSession.ReadyCh is closed so callers
// can unblock user-visible session-ready logic without waiting for
// postAttach. The default target is "postCreateCommand" (matches the
// Dev Containers spec and what both 02.5 reference recipes expect).
//
// Parallel groups (D-26, D-27): a hook with multiple outer entries runs
// under errgroup.WithContext — each group becomes one goroutine calling
// exec(gctx, cid, argv). The first non-zero exit cancels sibling goroutines
// via the shared context, and errgroup.Wait returns that first error.
//
// Per-hook timeout (D-30): every hook runs under context.WithTimeout
// with recipes.HookTimeout(recipe, name) — default 10 minutes, override
// via recipe.Lifecycle.<hook>TimeoutSec. The timeout applies to the
// entire group including all parallel dispatches.
//
// Teardown on failure: any non-nil hook error (including a
// context-deadline-exceeded error from the timeout path) triggers a
// best-effort Stop + Remove on the container, and the returned error
// wraps both the hook error and any teardown error via errors.Join.
//
// Test seam (lifecycleDeps): the container-create, in-container-exec,
// and teardown steps are injected via an unexported lifecycleDeps
// struct so runner_lifecycle_test.go can exercise the full sequencer
// without a live Docker daemon. Production wires the real Runner.Run /
// Runner.Exec / teardown implementations; tests wire fakes that record
// call sequences, simulate errors, and sleep to test timeouts.

import (
	"context"
	"errors"
	"fmt"
	"os/exec"
	"time"

	"golang.org/x/sync/errgroup"

	"github.com/agentplayground/api/internal/recipes"
)

// LifecycleSession is the handle RunWithLifecycle returns on success.
// ContainerID is the started container's ID. Recipe is the pointer the
// caller passed in — the runner does not copy it. ReadyCh is closed
// exactly once, when the hook named by recipe.Lifecycle.WaitFor
// completes successfully; callers can <-ReadyCh to block until the
// session is user-visible-ready without waiting for postAttachCommand.
type LifecycleSession struct {
	ContainerID string
	Recipe      *recipes.Recipe
	ReadyCh     chan struct{}
}

// execFunc is the minimal in-container exec contract used by the
// sequencer. Production passes Runner.Exec; tests pass a fake that
// records call sequence and simulates errors/sleeps.
type execFunc func(ctx context.Context, containerID string, cmd []string) ([]byte, error)

// createFunc is the container-create contract used by the sequencer.
// Production passes Runner.Run; tests pass a fake that returns a
// canned container ID without touching Docker.
type createFunc func(ctx context.Context, opts RunOptions) (string, error)

// teardownFunc is the failure-path cleanup contract used by the
// sequencer. Production passes the runner's real teardown (Stop +
// Remove with a bounded context); tests pass a fake that either
// succeeds or returns a recorded error.
type teardownFunc func(ctx context.Context, cid string) error

// lifecycleDeps bundles the injectable collaborators for the
// sequencer. It is intentionally unexported — only tests in the same
// package construct one directly. Production callers go through
// RunWithLifecycle which wires the real implementations.
type lifecycleDeps struct {
	createStartContainer createFunc
	exec                 execFunc
	teardown             teardownFunc
	// now returns the current time; injectable for deterministic tests.
	now func() time.Time
}

// RunWithLifecycle executes the full Dev Containers lifecycle against
// a new container created from opts. On success it returns a
// LifecycleSession; on any hook failure it tears the container down
// and returns the wrapped error.
//
// Secrets policy note: schema validation in Plan 01 guarantees that
// neither onCreateCommand nor updateContentCommand can reference
// `secret:` values — this runner trusts that invariant. If a future
// change relaxes the schema, the runner must be updated to scrub
// secrets from the environment passed to those two hooks.
//
// FIFO bridge note (Pitfall 4): postStartCommand / postAttachCommand
// for FIFO-mode recipes (picoclaw) MUST NOT recreate or consume the
// chat FIFOs that Phase 2's entrypoint has already mknod'd —
// recreating them races the bridge, and `cat < fifo` silently eats
// bytes the bridge is supposed to receive. The runner does not
// enforce this; the recipe author does. Code review is the gate.
func (r *Runner) RunWithLifecycle(
	ctx context.Context,
	recipe *recipes.Recipe,
	opts RunOptions,
) (*LifecycleSession, error) {
	return r.runWithLifecycleWithDeps(ctx, recipe, opts, lifecycleDeps{
		createStartContainer: r.Run,
		exec:                 r.Exec,
		teardown:             r.lifecycleTeardown,
		now:                  time.Now,
	})
}

// runWithLifecycleWithDeps is the testable core. It takes injected
// collaborators so unit tests can exercise every branch of the
// sequencer without a live Docker daemon.
func (r *Runner) runWithLifecycleWithDeps(
	ctx context.Context,
	recipe *recipes.Recipe,
	opts RunOptions,
	deps lifecycleDeps,
) (*LifecycleSession, error) {
	if recipe == nil {
		return nil, fmt.Errorf("lifecycle: nil recipe")
	}
	if deps.now == nil {
		deps.now = time.Now
	}

	// 1. initializeCommand runs on the HOST before the container exists.
	// No teardown path here because no container has been created yet.
	if err := runHostInitialize(ctx, recipe); err != nil {
		return nil, fmt.Errorf("initializeCommand: %w", err)
	}

	// 2. Create + start container via existing Phase 2 Runner.Run.
	cid, err := deps.createStartContainer(ctx, opts)
	if err != nil {
		return nil, fmt.Errorf("container create: %w", err)
	}

	session := &LifecycleSession{
		ContainerID: cid,
		Recipe:      recipe,
		ReadyCh:     make(chan struct{}),
	}

	waitFor := recipe.Lifecycle.WaitFor
	if waitFor == "" {
		waitFor = "postCreateCommand"
	}
	// readySignalled guards against close-twice if the recipe names a
	// hook that somehow matches multiple pipeline entries. With the
	// current hook table this cannot happen, but the guard is cheap.
	readySignalled := false
	signalReady := func() {
		if !readySignalled {
			close(session.ReadyCh)
			readySignalled = true
		}
	}

	// 3-7. In-container hooks, in strict spec order.
	alreadyCreated := opts.Labels["ap.already-created"] == "true"
	type hookSpec struct {
		name string
		skip bool
	}
	hooks := []hookSpec{
		{name: "onCreateCommand", skip: alreadyCreated},
		{name: "updateContentCommand", skip: false},
		{name: "postCreateCommand", skip: false},
		{name: "postStartCommand", skip: false},
		{name: "postAttachCommand", skip: false},
	}

	for _, h := range hooks {
		if !h.skip {
			if err := runHookByName(ctx, cid, recipe, h.name, deps.exec); err != nil {
				// Hook failed → teardown + return wrapped error.
				teardownErr := deps.teardown(context.Background(), cid)
				hookErr := fmt.Errorf("%s: %w", h.name, err)
				if teardownErr != nil {
					return nil, errors.Join(hookErr, fmt.Errorf("teardown: %w", teardownErr))
				}
				return nil, hookErr
			}
		}
		if h.name == waitFor {
			signalReady()
		}
	}

	// Defense-in-depth: if the recipe named a waitFor hook that matches
	// none of the pipeline entries (should be schema-caught, but still)
	// we signal ready at the end rather than leaving ReadyCh dangling.
	signalReady()

	return session, nil
}

// runHookByName reads the named hook off the recipe, normalizes it,
// applies the per-hook timeout, and dispatches each parallel group
// via errgroup. Returns nil for empty/absent hooks.
func runHookByName(
	ctx context.Context,
	cid string,
	recipe *recipes.Recipe,
	name string,
	exec execFunc,
) error {
	var raw any
	switch name {
	case "onCreateCommand":
		raw = recipe.Lifecycle.OnCreateCommand
	case "updateContentCommand":
		raw = recipe.Lifecycle.UpdateContentCommand
	case "postCreateCommand":
		raw = recipe.Lifecycle.PostCreateCommand
	case "postStartCommand":
		raw = recipe.Lifecycle.PostStartCommand
	case "postAttachCommand":
		raw = recipe.Lifecycle.PostAttachCommand
	default:
		return fmt.Errorf("unknown hook %q", name)
	}
	hook, err := recipes.NormalizeHook(raw)
	if err != nil {
		return fmt.Errorf("normalize: %w", err)
	}
	if len(hook) == 0 {
		return nil
	}
	timeout := recipes.HookTimeout(recipe, name)
	hctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	g, gctx := errgroup.WithContext(hctx)
	for _, argv := range hook {
		argv := argv
		g.Go(func() error {
			out, err := exec(gctx, cid, argv)
			if err != nil {
				return fmt.Errorf("exec %v: %w (output=%q)", argv, err, string(out))
			}
			return nil
		})
	}
	return g.Wait()
}

// runHostInitialize runs recipe.Lifecycle.InitializeCommand on the
// host via os/exec.CommandContext. This is the only hook that does
// NOT touch the container. v0.1 reference recipes leave this empty;
// future recipes that declare a host-side initialize must pass code
// review (T-02.5-04a mitigation).
//
// Parallel groups within initializeCommand follow the same errgroup
// semantics as in-container hooks: each group runs as its own host
// process; first non-zero exit cancels siblings.
func runHostInitialize(ctx context.Context, recipe *recipes.Recipe) error {
	hook, err := recipes.NormalizeHook(recipe.Lifecycle.InitializeCommand)
	if err != nil {
		return fmt.Errorf("normalize: %w", err)
	}
	if len(hook) == 0 {
		return nil
	}
	timeout := recipes.HookTimeout(recipe, "initializeCommand")
	hctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	g, gctx := errgroup.WithContext(hctx)
	for _, argv := range hook {
		argv := argv
		if len(argv) == 0 {
			continue
		}
		g.Go(func() error {
			cmd := exec.CommandContext(gctx, argv[0], argv[1:]...)
			out, err := cmd.CombinedOutput()
			if err != nil {
				return fmt.Errorf("host exec %v: %w (%s)", argv, err, string(out))
			}
			return nil
		})
	}
	return g.Wait()
}

// lifecycleTeardown is the production teardown implementation wired
// into deps.teardown by RunWithLifecycle. It attempts Stop (graceful)
// then Remove with a short bounded context that is NOT derived from
// the caller's ctx — teardown must still run when the parent context
// is already cancelled (e.g. the hook hit its timeout).
func (r *Runner) lifecycleTeardown(_ context.Context, cid string) error {
	tctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	// Best-effort Stop; ignore error because Remove below is the
	// authoritative cleanup. If Stop fails (container already exited)
	// Remove will still succeed.
	_ = r.Stop(tctx, cid)
	return r.Remove(tctx, cid)
}
