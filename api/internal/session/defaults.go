// Package session hosts the Phase 2 session lifecycle primitives:
//
//   - DefaultSandbox: the hardened docker.RunOptions baseline applied to
//     every playground container.
//   - SecretWriter / SecretSource: the dev BYOK env-var → host tmpfs file
//     → container bind-mount injection chain.
//   - Store: the pgxpool-backed CRUD layer for the sessions table.
//
// Plan 05 composes these primitives into the HTTP handler + bridge layer.
// This package intentionally has ZERO HTTP dependencies so it is trivially
// unit-testable with only the stdlib + pgxpool.
package session

import (
	"github.com/agentplayground/api/pkg/docker"
)

// DefaultSandbox returns the Phase 2 hardened docker.RunOptions baseline.
// Every session-spawned container starts from this posture; recipe-level
// ResourceOverrides (Memory / CPUs / PidsLimit) are layered on top by the
// Plan 05 session-create handler. Security knobs (CapDrop, NoNewPrivs,
// ReadOnlyRootfs) are NOT overridable per recipe.
//
// References:
//   - CONTEXT D-13 "Default sandbox posture"
//   - RESEARCH §Default sandbox posture
//   - Phase 7.5 will swap SeccompProfile for a custom JSON; Plan 04 leaves
//     it empty so Docker's default profile applies.
func DefaultSandbox() docker.RunOptions {
	return docker.RunOptions{
		// SeccompProfile empty → Docker default. Phase 7.5 overrides.
		ReadOnlyRootfs: true,
		Tmpfs: map[string]string{
			"/tmp": "rw,noexec,nosuid,size=128m",
			"/run": "rw,noexec,nosuid,size=16m",
		},
		CapDrop:    []string{"ALL"},
		CapAdd:     nil,
		NoNewPrivs: true,
		Runtime:    "", // runc
		Network:    "bridge",
		Memory:     1 << 30,       // 1 GiB
		CPUs:       1_000_000_000, // 1 vCPU in nanoCPUs
		PidsLimit:  256,
		Remove:     true,
	}
}
