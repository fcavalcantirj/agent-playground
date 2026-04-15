package bridge_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/agentplayground/api/internal/session/bridge"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Ported from Phase 2 session/bridge_test.go#TestBridge_FIFOMode.
// Assertions preserved byte-for-byte: the FIFO write must use
// ExecWithStdin against `sh -c 'cat >> /run/ap/chat.in'`, and the
// poll must target /run/ap/chat.out.
func TestFIFOBridge_SendMessage(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("hello back\n"),
	}
	b := bridge.NewFIFOBridge(m, zerolog.Nop())

	rec := &recipes.Recipe{
		ID:   "picoclaw",
		Name: "picoclaw",
		ChatIO: recipes.RecipeChatIO{
			Mode:               "fifo",
			ResponseTimeoutSec: 5,
			FIFO: &recipes.RecipeChatIOFIFO{
				FIFOIn:    "/run/ap/chat.in",
				FIFOOut:   "/run/ap/chat.out",
				StripANSI: true,
			},
		},
	}

	resp, err := b.SendMessage(context.Background(), "abc123", rec, "", "hello")
	require.NoError(t, err)
	assert.Equal(t, "hello back", resp)

	require.Len(t, m.stdinCalls, 1, "FIFO mode should write once via ExecWithStdin")
	call := m.stdinCalls[0]
	assert.Equal(t, "abc123", call.containerID)
	assert.Equal(t, []string{"sh", "-c", "cat >> /run/ap/chat.in"}, call.cmd)
	assert.Contains(t, string(call.stdin), "hello")

	require.GreaterOrEqual(t, len(m.execCalls), 1, "FIFO mode should poll chat.out")
	found := false
	for _, ec := range m.execCalls {
		for _, a := range ec.cmd {
			if strings.Contains(a, "/run/ap/chat.out") {
				found = true
			}
		}
	}
	assert.True(t, found, "Exec should read /run/ap/chat.out")
}

// Ported from Phase 2 session/bridge_test.go#TestBridge_Timeout.
// FIFO poll with zero-length response must honor the response timeout
// and surface ErrTimeout.
func TestFIFOBridge_Timeout(t *testing.T) {
	m := &mockRunner{
		execResp:  []byte(""),
		stdinResp: []byte(""),
	}
	b := bridge.NewFIFOBridge(m, zerolog.Nop())

	rec := &recipes.Recipe{
		ID:   "picoclaw",
		Name: "picoclaw",
		ChatIO: recipes.RecipeChatIO{
			Mode:               "fifo",
			ResponseTimeoutSec: 0, // below use a short ctx deadline instead
			FIFO: &recipes.RecipeChatIOFIFO{
				FIFOIn:  "/run/ap/chat.in",
				FIFOOut: "/run/ap/chat.out",
			},
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	_, err := b.SendMessage(ctx, "cid", rec, "", "hi")
	require.Error(t, err)
	assert.True(t, errors.Is(err, bridge.ErrTimeout),
		"expected ErrTimeout, got %v", err)
}

// FIFOIn/FIFOOut defaulting: when the recipe leaves them empty, the
// Phase 2 hardcoded defaults (/run/ap/chat.in, /run/ap/chat.out) MUST
// be used so the legacy shim keeps working.
func TestFIFOBridge_DefaultPaths(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("ok\n"),
	}
	b := bridge.NewFIFOBridge(m, zerolog.Nop())

	rec := &recipes.Recipe{
		ID:   "picoclaw",
		Name: "picoclaw",
		ChatIO: recipes.RecipeChatIO{
			Mode:               "fifo",
			ResponseTimeoutSec: 5,
			// FIFO block nil on purpose — the bridge must default.
		},
	}

	_, err := b.SendMessage(context.Background(), "cid", rec, "", "hi")
	require.NoError(t, err)
	require.Len(t, m.stdinCalls, 1)
	assert.Equal(t, []string{"sh", "-c", "cat >> /run/ap/chat.in"}, m.stdinCalls[0].cmd)
}

// Shell-metacharacter safety: the FIFO bridge writes user text to
// stdin; the shell only sees the literal `cat >> /run/ap/chat.in`.
// THREAT NOTE (T-02-04 / T-02.5-05) preserved from Phase 2.
func TestFIFOBridge_TextOnStdin_NotArgv(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("ok\n"),
	}
	b := bridge.NewFIFOBridge(m, zerolog.Nop())

	rec := &recipes.Recipe{
		ID:   "picoclaw",
		Name: "picoclaw",
		ChatIO: recipes.RecipeChatIO{
			Mode:               "fifo",
			ResponseTimeoutSec: 5,
			FIFO: &recipes.RecipeChatIOFIFO{
				FIFOIn:  "/run/ap/chat.in",
				FIFOOut: "/run/ap/chat.out",
			},
		},
	}

	malicious := "; rm -rf / $(whoami) `id`"
	_, err := b.SendMessage(context.Background(), "cid", rec, "", malicious)
	require.NoError(t, err)

	require.Len(t, m.stdinCalls, 1)
	// The cmd itself is constant — the user text is NEVER an argv element.
	assert.Equal(t, []string{"sh", "-c", "cat >> /run/ap/chat.in"}, m.stdinCalls[0].cmd)
	assert.Contains(t, string(m.stdinCalls[0].stdin), malicious,
		"malicious bytes must travel through stdin, not the argv")
}
