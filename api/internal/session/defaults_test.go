package session_test

import (
	"testing"

	"github.com/agentplayground/api/internal/session"
	"github.com/stretchr/testify/assert"
)

func TestDefaultSandbox_Hardened(t *testing.T) {
	s := session.DefaultSandbox()
	assert.Contains(t, s.CapDrop, "ALL", "CapDrop must include ALL")
	assert.True(t, s.NoNewPrivs, "NoNewPrivs must be true")
	assert.True(t, s.ReadOnlyRootfs, "ReadOnlyRootfs must be true")
	assert.Equal(t, int64(256), s.PidsLimit)
	assert.Equal(t, int64(1<<30), s.Memory, "Memory must be 1 GiB")
	assert.Equal(t, int64(1_000_000_000), s.CPUs, "CPUs must be 1 vCPU in nanoCPUs")
	assert.Contains(t, s.Tmpfs, "/tmp", "Tmpfs must include /tmp")
	assert.Contains(t, s.Tmpfs, "/run", "Tmpfs must include /run")
	assert.Equal(t, "bridge", s.Network)
	assert.True(t, s.Remove, "Remove must be true (--rm semantics)")
	assert.Equal(t, "", s.SeccompProfile, "SeccompProfile empty = Docker default (Phase 7.5 overrides)")
	assert.Equal(t, "", s.Runtime, "Runtime empty = runc default")
}

func TestDefaultSandbox_InitCapsOnly(t *testing.T) {
	s := session.DefaultSandbox()
	// Phase 2 init-only caps: needed by ap-base entrypoint for the root→agent
	// gosu drop + /run/ap chown. NoNewPrivs locks privs after init.
	assert.ElementsMatch(t,
		[]string{"CHOWN", "SETUID", "SETGID", "SETPCAP"},
		s.CapAdd,
		"CapAdd must be exactly the ap-base init caps")
	// Caps that must NEVER appear (privilege-escalation / network-tampering):
	for _, forbidden := range []string{"SYS_ADMIN", "NET_ADMIN", "NET_RAW", "SYS_PTRACE", "SYS_MODULE", "DAC_READ_SEARCH", "SYS_RAWIO"} {
		assert.NotContains(t, s.CapAdd, forbidden,
			"CapAdd must not include %s", forbidden)
	}
}
