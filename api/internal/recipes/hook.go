// hook.go — lifecycle hook normalizer + per-hook timeout helper.
//
// Phase 02.5 Plan 03 introduces the normalized Hook type that
// pkg/docker/runner_lifecycle.go uses when dispatching the 6 Dev
// Containers lifecycle commands. The normalizer is kept in the
// recipes package (and NOT in pkg/docker) so the dependency graph
// stays docker → recipes, never the other way around. Plan 03's
// acceptance gate checks `go list -deps ./internal/recipes/...`
// returns zero hits for pkg/docker.
//
// Authoring contract (D-27):
//
//	hook: "echo hi"                  → one group, one argv, sh -c wrapped
//	hook: ["bin","--flag","arg"]     → one group, one argv, literal exec form
//	hook: [["a"], ["b"]]             → TWO PARALLEL groups (errgroup dispatches)
//	hook: [["a","arg"],["b","arg"]]  → TWO PARALLEL groups, each multi-arg
//
// To run multiple commands sequentially inside a single group, wrap
// them in sh -c: ["sh","-c","cmd1 && cmd2"]. Dev Containers object-
// syntax parallel groups ({"label": "cmd"}) are rejected at schema
// validation time (Plan 01's hook $def has not:{type:object}).
package recipes

import (
	"fmt"
	"time"
)

// Hook is the normalized representation of any lifecycle hook.
//
// Each outer element is one parallel group. Each inner element is the
// argv of a single `docker exec` call. An empty Hook (len == 0) means
// "nothing to run" and is treated as a no-op by the runner.
type Hook [][]string

// DefaultHookTimeout is the per-hook wall-clock budget used when a
// recipe does not override the per-hook timeout field (D-30).
const DefaultHookTimeout = 10 * time.Minute

// NormalizeHook converts an untyped lifecycle field value (as
// deserialized from YAML via sigs.k8s.io/yaml → JSON) into a Hook.
//
// The input type is `any` because RecipeLifecycle.<hook> fields are
// typed `any` at the struct level to accept all three v0.1 shapes.
// NormalizeHook is the one place that collapses that any-shape into
// the [][]string canonical form the runner consumes.
func NormalizeHook(v any) (Hook, error) {
	switch x := v.(type) {
	case nil:
		return nil, nil
	case string:
		if x == "" {
			return nil, nil
		}
		return Hook{{"sh", "-c", x}}, nil
	case []any:
		if len(x) == 0 {
			return nil, nil
		}
		// Peek at first element to decide the shape:
		//   - all strings → single argv, literal exec form (one group)
		//   - all []any   → array-of-arrays, each inner is an argv in a
		//                   parallel group
		switch x[0].(type) {
		case string:
			argv := make([]string, 0, len(x))
			for _, item := range x {
				s, ok := item.(string)
				if !ok {
					return nil, fmt.Errorf("hook: mixed type in []string form: got %T", item)
				}
				argv = append(argv, s)
			}
			return Hook{argv}, nil
		case []any:
			out := make(Hook, 0, len(x))
			for _, item := range x {
				inner, ok := item.([]any)
				if !ok {
					return nil, fmt.Errorf("hook: mixed-type array-of-arrays: got %T", item)
				}
				if len(inner) == 0 {
					return nil, fmt.Errorf("hook: empty argv in array-of-arrays")
				}
				argv := make([]string, 0, len(inner))
				for _, s := range inner {
					str, ok := s.(string)
					if !ok {
						return nil, fmt.Errorf("hook: non-string in inner argv: got %T", s)
					}
					argv = append(argv, str)
				}
				out = append(out, argv)
			}
			return out, nil
		default:
			return nil, fmt.Errorf("hook: unsupported first element type %T", x[0])
		}
	// []string is rarely produced by sigs.k8s.io/yaml (it emits []any),
	// but accept it for callers that pre-build hooks in Go tests.
	case []string:
		if len(x) == 0 {
			return nil, nil
		}
		argv := make([]string, len(x))
		copy(argv, x)
		return Hook{argv}, nil
	default:
		return nil, fmt.Errorf("hook: unsupported root type %T", v)
	}
}

// HookTimeout returns the effective wall-clock timeout for the named
// lifecycle hook on the given recipe, falling back to
// DefaultHookTimeout when the recipe omits the per-hook override.
//
// Hook names follow the Dev Containers casing (initializeCommand,
// onCreateCommand, updateContentCommand, postCreateCommand,
// postStartCommand, postAttachCommand). Unknown hook names return
// DefaultHookTimeout — the runner only calls this helper with
// known names so this branch is defense-in-depth, not a contract.
func HookTimeout(r *Recipe, name string) time.Duration {
	if r == nil {
		return DefaultHookTimeout
	}
	var sec int
	switch name {
	case "initializeCommand":
		sec = r.Lifecycle.InitializeTimeoutSec
	case "onCreateCommand":
		sec = r.Lifecycle.OnCreateTimeoutSec
	case "updateContentCommand":
		sec = r.Lifecycle.UpdateContentTimeoutSec
	case "postCreateCommand":
		sec = r.Lifecycle.PostCreateTimeoutSec
	case "postStartCommand":
		sec = r.Lifecycle.PostStartTimeoutSec
	case "postAttachCommand":
		sec = r.Lifecycle.PostAttachTimeoutSec
	}
	if sec <= 0 {
		return DefaultHookTimeout
	}
	return time.Duration(sec) * time.Second
}
