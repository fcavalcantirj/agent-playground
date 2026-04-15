package session_test

import (
	"bytes"
	"context"
	"errors"
	"io"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/agentplayground/api/internal/session"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockRunner captures Exec / ExecWithStdin calls for assertion.
type mockRunner struct {
	mu sync.Mutex

	execCalls []mockExecCall
	stdinCalls []mockStdinCall

	// execFn overrides the default "return execResp, execErr" behavior
	// when set. Useful for timeout / polling simulations.
	execFn func(ctx context.Context, containerID string, cmd []string) ([]byte, error)
	execResp []byte
	execErr  error

	stdinResp []byte
	stdinErr  error
}

type mockExecCall struct {
	containerID string
	cmd         []string
}

type mockStdinCall struct {
	containerID string
	cmd         []string
	stdin       []byte
}

func (m *mockRunner) Exec(ctx context.Context, containerID string, cmd []string) ([]byte, error) {
	m.mu.Lock()
	m.execCalls = append(m.execCalls, mockExecCall{containerID: containerID, cmd: append([]string(nil), cmd...)})
	fn := m.execFn
	resp := m.execResp
	err := m.execErr
	m.mu.Unlock()
	if fn != nil {
		return fn(ctx, containerID, cmd)
	}
	return resp, err
}

func (m *mockRunner) ExecWithStdin(ctx context.Context, containerID string, cmd []string, stdin io.Reader) ([]byte, error) {
	var buf bytes.Buffer
	if stdin != nil {
		_, _ = io.Copy(&buf, stdin)
	}
	m.mu.Lock()
	m.stdinCalls = append(m.stdinCalls, mockStdinCall{
		containerID: containerID,
		cmd:         append([]string(nil), cmd...),
		stdin:       buf.Bytes(),
	})
	resp := m.stdinResp
	err := m.stdinErr
	m.mu.Unlock()
	return resp, err
}

func TestBridge_FIFOMode(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("hello back\n"),
	}
	b := session.NewBridge(m)

	rec := &recipes.LegacyRecipe{
		Name: "picoclaw",
		ChatIO: recipes.ChatIO{
			Mode:            recipes.ChatIOFIFO,
			LaunchCmd:       []string{"picoclaw", "agent"},
			ResponseTimeout: 5 * time.Second,
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
	// The first Exec call should target chat.out.
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

func TestBridge_ExecMode(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("ok: got your message\n"),
	}
	b := session.NewBridge(m)

	rec := &recipes.LegacyRecipe{
		Name: "hermes",
		ChatIO: recipes.ChatIO{
			Mode:            recipes.ChatIOExec,
			ExecCmd:         []string{"hermes", "chat", "-q"},
			ResponseTimeout: 5 * time.Second,
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

	// The bridge must clone the execCmd, not mutate the recipe's slice.
	assert.Equal(t, []string{"hermes", "chat", "-q"}, rec.ChatIO.ExecCmd,
		"bridge must not mutate recipe.ChatIO.ExecCmd")
}

func TestBridge_Timeout(t *testing.T) {
	// Runner always returns empty output so FIFO poll never exits.
	m := &mockRunner{
		execResp:  []byte(""),
		stdinResp: []byte(""),
	}
	b := session.NewBridge(m)

	rec := &recipes.LegacyRecipe{
		Name: "picoclaw",
		ChatIO: recipes.ChatIO{
			Mode:            recipes.ChatIOFIFO,
			ResponseTimeout: 50 * time.Millisecond,
		},
	}

	_, err := b.SendMessage(context.Background(), "cid", rec, "", "hi")
	require.Error(t, err)
	assert.True(t, errors.Is(err, session.ErrTimeout), "expected ErrTimeout, got %v", err)
}

func TestBridge_TextWithShellMetacharacters(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("ok\n"),
	}
	b := session.NewBridge(m)

	rec := &recipes.LegacyRecipe{
		Name: "hermes",
		ChatIO: recipes.ChatIO{
			Mode:            recipes.ChatIOExec,
			ExecCmd:         []string{"hermes", "chat", "-q"},
			ResponseTimeout: 5 * time.Second,
		},
	}

	malicious := "; rm -rf / $(whoami) `id`"
	_, err := b.SendMessage(context.Background(), "cid", rec, "", malicious)
	require.NoError(t, err)

	require.Len(t, m.execCalls, 1)
	call := m.execCalls[0]
	// The malicious text must be a single argv element (index 3), literal bytes.
	require.Len(t, call.cmd, 4)
	assert.Equal(t, malicious, call.cmd[3],
		"user text must be a single argv element, not shell-expanded")
}

func TestBridge_StripsANSI(t *testing.T) {
	m := &mockRunner{
		execResp: []byte("\x1b[31mERR\x1b[0m\n"),
	}
	b := session.NewBridge(m)

	rec := &recipes.LegacyRecipe{
		Name: "hermes",
		ChatIO: recipes.ChatIO{
			Mode:            recipes.ChatIOExec,
			ExecCmd:         []string{"hermes", "chat", "-q"},
			ResponseTimeout: 5 * time.Second,
		},
	}

	resp, err := b.SendMessage(context.Background(), "cid", rec, "", "err")
	require.NoError(t, err)
	assert.Equal(t, "ERR", resp)
}
