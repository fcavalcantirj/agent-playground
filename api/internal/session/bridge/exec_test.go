package bridge_test

import (
	"context"
	"testing"
	"time"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/agentplayground/api/internal/session/bridge"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// Ported from Phase 2 session/bridge_test.go#TestBridge_ExecMode.
// Verbatim assertions: argv is cloned from the recipe template, user
// text is appended as the final argv element, output is trimmed.
func TestExecBridge_SendMessage(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("ok: got your message\n"),
	}
	b := bridge.NewExecBridge(m, zerolog.Nop())

	rec := &recipes.Recipe{
		ID:   "hermes",
		Name: "hermes",
		ChatIO: recipes.RecipeChatIO{
			Mode:               "exec_per_message",
			ResponseTimeoutSec: 5,
			ExecPerMessage: &recipes.RecipeChatIOExec{
				CmdTemplate: []string{"hermes", "chat", "-q"},
			},
		},
	}

	resp, err := b.SendMessage(context.Background(), "cid", rec, "", "hi there")
	require.NoError(t, err)
	assert.Equal(t, "ok: got your message", resp)

	require.Len(t, m.execCalls, 1)
	call := m.execCalls[0]
	assert.Equal(t, "cid", call.containerID)
	require.Len(t, call.cmd, 4)
	assert.Equal(t, []string{"hermes", "chat", "-q", "hi there"}, call.cmd)

	// The bridge must clone the cmd template, not mutate the recipe.
	assert.Equal(t, []string{"hermes", "chat", "-q"}, rec.ChatIO.ExecPerMessage.CmdTemplate,
		"bridge must not mutate recipe.ChatIO.ExecPerMessage.CmdTemplate")
}

// Ported from Phase 2 session/bridge_test.go#TestBridge_TextWithShellMetacharacters.
// THREAT NOTE (T-02-04b / T-02.5-05a) — user text is a single argv
// element, never shell-interpreted.
func TestExecBridge_TextWithShellMetacharacters(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("ok\n"),
	}
	b := bridge.NewExecBridge(m, zerolog.Nop())

	rec := &recipes.Recipe{
		ID:   "hermes",
		Name: "hermes",
		ChatIO: recipes.RecipeChatIO{
			Mode:               "exec_per_message",
			ResponseTimeoutSec: 5,
			ExecPerMessage: &recipes.RecipeChatIOExec{
				CmdTemplate: []string{"hermes", "chat", "-q"},
			},
		},
	}

	malicious := "; rm -rf / $(whoami) `id`"
	_, err := b.SendMessage(context.Background(), "cid", rec, "", malicious)
	require.NoError(t, err)

	require.Len(t, m.execCalls, 1)
	call := m.execCalls[0]
	require.Len(t, call.cmd, 4)
	assert.Equal(t, malicious, call.cmd[3],
		"user text must be a single argv element, not shell-expanded")
}

// Ported from Phase 2 session/bridge_test.go#TestBridge_StripsANSI.
// Exec mode must strip CSI escape sequences before returning.
func TestExecBridge_StripsANSI(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("\x1b[31mERR\x1b[0m\n"),
	}
	b := bridge.NewExecBridge(m, zerolog.Nop())

	rec := &recipes.Recipe{
		ID:   "hermes",
		Name: "hermes",
		ChatIO: recipes.RecipeChatIO{
			Mode:               "exec_per_message",
			ResponseTimeoutSec: 5,
			ExecPerMessage: &recipes.RecipeChatIOExec{
				CmdTemplate: []string{"hermes", "chat", "-q"},
			},
		},
	}

	resp, err := b.SendMessage(context.Background(), "cid", rec, "", "err")
	require.NoError(t, err)
	assert.Equal(t, "ERR", resp)
}

// Exec mode honors recipe.ModelFlag + modelID: the flag and the model
// id are appended before the user text. Phase 2 behavior preserved.
func TestExecBridge_AppendsModelFlag(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("ok\n"),
	}
	b := bridge.NewExecBridge(m, zerolog.Nop())

	rec := &recipes.Recipe{
		ID:        "hermes",
		Name:      "hermes",
		ModelFlag: "--model",
		ChatIO: recipes.RecipeChatIO{
			Mode:               "exec_per_message",
			ResponseTimeoutSec: 5,
			ExecPerMessage: &recipes.RecipeChatIOExec{
				CmdTemplate: []string{"hermes", "chat", "-q"},
			},
		},
	}

	_, err := b.SendMessage(context.Background(), "cid", rec, "claude-sonnet-4.6", "hi")
	require.NoError(t, err)

	require.Len(t, m.execCalls, 1)
	assert.Equal(t,
		[]string{"hermes", "chat", "-q", "--model", "claude-sonnet-4.6", "hi"},
		m.execCalls[0].cmd)
}

// Exec mode with an impossible response time (negative context deadline)
// still returns cleanly — guards against hangs if upstream passes a
// cancelled context.
func TestExecBridge_CancelledContext(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("ok\n"),
	}
	b := bridge.NewExecBridge(m, zerolog.Nop())

	rec := &recipes.Recipe{
		ID:   "hermes",
		Name: "hermes",
		ChatIO: recipes.RecipeChatIO{
			Mode: "exec_per_message",
			ExecPerMessage: &recipes.RecipeChatIOExec{
				CmdTemplate: []string{"hermes", "chat", "-q"},
			},
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Millisecond)
	defer cancel()
	time.Sleep(5 * time.Millisecond)

	// Runner returns ok — the bridge's context is cancelled but because
	// the fake runner ignores ctx, it still returns. This test mainly
	// ensures the bridge does not panic when ctx.Err() != nil.
	_, _ = b.SendMessage(ctx, "cid", rec, "", "hi")
}
