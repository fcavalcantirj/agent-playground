package bridge_test

import (
	"bytes"
	"context"
	"errors"
	"io"
	"sync"
	"testing"

	"github.com/agentplayground/api/internal/session/bridge"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// mockRunner is the shared RunnerExec fake used by fifo/exec/registry
// tests in this package. It preserves the exact Phase 2 mock shape so
// ported tests from session/bridge_test.go do not need to drift.
type mockRunner struct {
	mu sync.Mutex

	execCalls  []mockExecCall
	stdinCalls []mockStdinCall

	// execFn overrides the default "return execResp, execErr" behavior
	// when set. Useful for timeout / polling simulations.
	execFn   func(ctx context.Context, containerID string, cmd []string) ([]byte, error)
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

func newTestRegistry(r bridge.RunnerExec) *bridge.BridgeRegistry {
	return bridge.NewBridgeRegistry(r, zerolog.Nop())
}

func TestBridgeRegistry_Dispatch_Fifo(t *testing.T) {
	m := &mockRunner{}
	reg := newTestRegistry(m)

	b, err := reg.Dispatch("fifo")
	require.NoError(t, err)
	require.NotNil(t, b)

	// Must be the FIFO implementation — a type assertion is enough.
	_, ok := b.(*bridge.FIFOBridge)
	assert.True(t, ok, "fifo mode should dispatch to *FIFOBridge, got %T", b)
}

func TestBridgeRegistry_Dispatch_Exec(t *testing.T) {
	m := &mockRunner{}
	reg := newTestRegistry(m)

	b, err := reg.Dispatch("exec_per_message")
	require.NoError(t, err)
	require.NotNil(t, b)

	_, ok := b.(*bridge.ExecBridge)
	assert.True(t, ok, "exec_per_message mode should dispatch to *ExecBridge, got %T", b)
}

func TestBridgeRegistry_Dispatch_Unsupported(t *testing.T) {
	m := &mockRunner{}
	reg := newTestRegistry(m)

	b, err := reg.Dispatch("http_gateway")
	require.Error(t, err)
	assert.Nil(t, b)
	assert.True(t, errors.Is(err, bridge.ErrUnsupportedMode),
		"unknown mode must wrap ErrUnsupportedMode, got %v", err)
	assert.Contains(t, err.Error(), "http_gateway",
		"error should name the rejected mode")
}

func TestStripANSI(t *testing.T) {
	in := "\x1b[31mERR\x1b[0m"
	assert.Equal(t, "ERR", bridge.StripANSI(in))
}
