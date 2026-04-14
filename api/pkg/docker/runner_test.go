package docker

import (
	"bufio"
	"context"
	"errors"
	"net"
	"reflect"
	"strings"
	"testing"

	"github.com/moby/moby/api/types/container"
	"github.com/moby/moby/client"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// ---------- validation tests ----------

func TestValidateContainerID(t *testing.T) {
	valid := []string{
		"abc123",
		"playground-u1-s1",
		"my-container_v2",
		"0123456789abcdef",
		"a.b.c",
	}
	for _, id := range valid {
		t.Run("accept/"+id, func(t *testing.T) {
			assert.NoError(t, validateContainerID(id))
		})
	}

	invalid := []string{
		"",
		"; rm -rf /",
		"$(evil)",
		"container name with spaces",
		"`cmd`",
		"foo|bar",
		"-starts-with-dash",
		strings.Repeat("a", 129),
	}
	for _, id := range invalid {
		t.Run("reject/"+id, func(t *testing.T) {
			assert.Error(t, validateContainerID(id))
		})
	}
}

func TestValidateImageName(t *testing.T) {
	valid := []string{
		"alpine",
		"alpine:3.19",
		"registry.example.com/myimg:v1.2",
		"postgres:17-alpine",
		"library/ubuntu:22.04",
		"ghcr.io/owner/repo:latest",
	}
	for _, img := range valid {
		t.Run("accept/"+img, func(t *testing.T) {
			assert.NoError(t, validateImageName(img))
		})
	}

	invalid := []string{
		"",
		"; rm -rf /",
		"$(evil)",
		"image name",
		"`whoami`",
		"foo|bar",
		strings.Repeat("a", 257),
	}
	for _, img := range invalid {
		t.Run("reject/"+img, func(t *testing.T) {
			assert.Error(t, validateImageName(img))
		})
	}
}

func TestValidateEnvVar(t *testing.T) {
	valid := []string{
		"FOO=bar",
		"DATABASE_URL=postgresql://host:5432/db",
		"EMPTY=",
		"MULTI_WORD_KEY=some value with spaces",
		"_UNDERSCORE=ok",
		"A=1",
		// Lowercase keys are valid: POSIX proxy conventions (http_proxy, etc.)
		"http_proxy=http://proxy.example.com:3128",
		"https_proxy=http://proxy.example.com:3128",
		"no_proxy=localhost,127.0.0.1",
	}
	for _, env := range valid {
		t.Run("accept/"+env, func(t *testing.T) {
			assert.NoError(t, validateEnvVar(env))
		})
	}

	invalid := []string{
		"",
		"no_equals_sign",
		"FOO=$(evil)",
		"BAR=`cmd`",
		"1BAD=bad",
		"FOO BAR=bad",
		"FOO=value with $(subshell)",
	}
	for _, env := range invalid {
		t.Run("reject/"+env, func(t *testing.T) {
			assert.Error(t, validateEnvVar(env))
		})
	}
}

func TestValidateMountPath(t *testing.T) {
	valid := []string{
		"/host/path:/container/path",
		"/data:/workspace:ro",
		"/var/run/docker.sock:/var/run/docker.sock",
	}
	for _, m := range valid {
		t.Run("accept/"+m, func(t *testing.T) {
			assert.NoError(t, validateMountPath(m))
		})
	}

	invalid := []string{
		"",
		"no_colon",
		"/host/../etc:/container",
		"/host:/container:$(evil)",
		"/host:/container:`cmd`",
		"/host:/container|bar",
	}
	for _, m := range invalid {
		t.Run("reject/"+m, func(t *testing.T) {
			assert.Error(t, validateMountPath(m))
		})
	}
}

// ---------- mock DockerClient ----------

type createCall struct {
	opts client.ContainerCreateOptions
}

type execCreateCall struct {
	containerID string
	opts        client.ExecCreateOptions
}

type mockDockerClient struct {
	createResp client.ContainerCreateResult
	createErr  error
	startErr   error
	stopErr    error
	removeErr  error

	inspectResp client.ContainerInspectResult
	inspectErr  error

	execCreateResp  client.ExecCreateResult
	execCreateErr   error
	execAttachResp  client.ExecAttachResult
	execAttachErr   error
	execInspectResp client.ExecInspectResult
	execInspectErr  error

	createCalls     []createCall
	startCalls      []string
	stopCalls       []string
	removeCalls     []string
	inspectCalls    []string
	execCreateCalls []execCreateCall
	execAttachCalls []string
	execInspectCall []string
}

func (m *mockDockerClient) ContainerCreate(ctx context.Context, opts client.ContainerCreateOptions) (client.ContainerCreateResult, error) {
	m.createCalls = append(m.createCalls, createCall{opts: opts})
	return m.createResp, m.createErr
}

func (m *mockDockerClient) ContainerStart(ctx context.Context, containerID string, opts client.ContainerStartOptions) (client.ContainerStartResult, error) {
	m.startCalls = append(m.startCalls, containerID)
	return client.ContainerStartResult{}, m.startErr
}

func (m *mockDockerClient) ContainerStop(ctx context.Context, containerID string, opts client.ContainerStopOptions) (client.ContainerStopResult, error) {
	m.stopCalls = append(m.stopCalls, containerID)
	return client.ContainerStopResult{}, m.stopErr
}

func (m *mockDockerClient) ContainerRemove(ctx context.Context, containerID string, opts client.ContainerRemoveOptions) (client.ContainerRemoveResult, error) {
	m.removeCalls = append(m.removeCalls, containerID)
	return client.ContainerRemoveResult{}, m.removeErr
}

func (m *mockDockerClient) ContainerInspect(ctx context.Context, containerID string, opts client.ContainerInspectOptions) (client.ContainerInspectResult, error) {
	m.inspectCalls = append(m.inspectCalls, containerID)
	return m.inspectResp, m.inspectErr
}

func (m *mockDockerClient) ExecCreate(ctx context.Context, containerID string, opts client.ExecCreateOptions) (client.ExecCreateResult, error) {
	m.execCreateCalls = append(m.execCreateCalls, execCreateCall{containerID: containerID, opts: opts})
	return m.execCreateResp, m.execCreateErr
}

func (m *mockDockerClient) ExecAttach(ctx context.Context, execID string, opts client.ExecAttachOptions) (client.ExecAttachResult, error) {
	m.execAttachCalls = append(m.execAttachCalls, execID)
	return m.execAttachResp, m.execAttachErr
}

func (m *mockDockerClient) ExecInspect(ctx context.Context, execID string, opts client.ExecInspectOptions) (client.ExecInspectResult, error) {
	m.execInspectCall = append(m.execInspectCall, execID)
	return m.execInspectResp, m.execInspectErr
}

// ---------- Runner tests ----------

func newTestRunner(t *testing.T, m *mockDockerClient) *Runner {
	t.Helper()
	return NewRunnerWithClient(m, zerolog.Nop())
}

func TestRunner_Run_CallsCreateAndStart(t *testing.T) {
	m := &mockDockerClient{
		createResp: client.ContainerCreateResult{ID: "cid-123"},
	}
	r := newTestRunner(t, m)

	id, err := r.Run(context.Background(), RunOptions{
		Image: "alpine:3.19",
		Name:  "test-container",
		Env:   map[string]string{"FOO": "bar"},
		Cmd:   []string{"sleep", "30"},
	})
	require.NoError(t, err)
	assert.Equal(t, "cid-123", id)
	require.Len(t, m.createCalls, 1, "ContainerCreate called")
	require.Len(t, m.startCalls, 1, "ContainerStart called")
	assert.Equal(t, "cid-123", m.startCalls[0])

	cc := m.createCalls[0]
	assert.Equal(t, "alpine:3.19", cc.opts.Image)
	assert.Equal(t, "test-container", cc.opts.Name)
	require.NotNil(t, cc.opts.Config)
	assert.Contains(t, cc.opts.Config.Env, "FOO=bar")
	assert.Equal(t, []string{"sleep", "30"}, []string(cc.opts.Config.Cmd))
}

func TestRunner_Run_SetsResourceLimits(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)

	_, err := r.Run(context.Background(), RunOptions{
		Image:     "alpine",
		Memory:    512 * 1024 * 1024,
		CPUs:      2_000_000_000, // 2 vCPU in nanoCPUs
		PidsLimit: 100,
	})
	require.NoError(t, err)
	hc := m.createCalls[0].opts.HostConfig
	require.NotNil(t, hc)
	assert.Equal(t, int64(512*1024*1024), hc.Memory)
	assert.Equal(t, int64(2_000_000_000), hc.NanoCPUs)
	require.NotNil(t, hc.PidsLimit)
	assert.Equal(t, int64(100), *hc.PidsLimit)
}

func TestRunner_Run_SetsEnvVarsAndLabels(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)

	_, err := r.Run(context.Background(), RunOptions{
		Image:  "alpine",
		Env:    map[string]string{"A": "1", "B": "two"},
		Labels: map[string]string{"app": "playground"},
	})
	require.NoError(t, err)
	cfg := m.createCalls[0].opts.Config
	require.NotNil(t, cfg)
	assert.ElementsMatch(t, []string{"A=1", "B=two"}, cfg.Env)
	assert.Equal(t, "playground", cfg.Labels["app"])
}

func TestRunner_Run_RejectsInvalidImage(t *testing.T) {
	m := &mockDockerClient{}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{Image: "; rm -rf /"})
	assert.Error(t, err)
	assert.Empty(t, m.createCalls, "SDK must not be called on invalid input")
}

func TestRunner_Run_RejectsInvalidEnvVar(t *testing.T) {
	m := &mockDockerClient{}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{
		Image: "alpine",
		Env:   map[string]string{"FOO": "$(evil)"},
	})
	assert.Error(t, err)
	assert.Empty(t, m.createCalls)
}

func TestRunner_Run_StartFailsRemovesContainer(t *testing.T) {
	m := &mockDockerClient{
		createResp: client.ContainerCreateResult{ID: "cid-1"},
		startErr:   errors.New("boom"),
	}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{Image: "alpine"})
	assert.Error(t, err)
	// Best-effort cleanup: orphan container should be removed
	assert.NotEmpty(t, m.removeCalls, "orphan container removed after start failure")
}

func TestRunner_Exec_CallsCreateAttachInspect(t *testing.T) {
	// Build a fake hijacked response. Use net.Pipe to model a connection;
	// close the server side so the runner reads EOF immediately.
	serverConn, clientConn := net.Pipe()
	go func() { _ = serverConn.Close() }()

	hijacked := client.HijackedResponse{
		Conn:   clientConn,
		Reader: bufio.NewReader(clientConn),
	}

	m := &mockDockerClient{
		execCreateResp:  client.ExecCreateResult{ID: "exec-1"},
		execAttachResp:  client.ExecAttachResult{HijackedResponse: hijacked},
		execInspectResp: client.ExecInspectResult{ID: "exec-1", ExitCode: 0, Running: false},
	}
	r := newTestRunner(t, m)

	_, err := r.Exec(context.Background(), "cid-1", []string{"echo", "hi"})
	require.NoError(t, err)
	require.Len(t, m.execCreateCalls, 1)
	assert.Equal(t, "cid-1", m.execCreateCalls[0].containerID)
	assert.Equal(t, []string{"echo", "hi"}, []string(m.execCreateCalls[0].opts.Cmd))
	assert.True(t, m.execCreateCalls[0].opts.AttachStdout)
	assert.True(t, m.execCreateCalls[0].opts.AttachStderr)
	assert.Len(t, m.execAttachCalls, 1)
	assert.Equal(t, "exec-1", m.execAttachCalls[0])
	assert.Len(t, m.execInspectCall, 1)
}

func TestRunner_Exec_RejectsInvalidContainerID(t *testing.T) {
	m := &mockDockerClient{}
	r := newTestRunner(t, m)
	_, err := r.Exec(context.Background(), "; rm -rf /", []string{"ls"})
	assert.Error(t, err)
	assert.Empty(t, m.execCreateCalls)
}

func TestRunner_Exec_NonZeroExitReturnsError(t *testing.T) {
	serverConn, clientConn := net.Pipe()
	go func() { _ = serverConn.Close() }()
	hijacked := client.HijackedResponse{
		Conn:   clientConn,
		Reader: bufio.NewReader(clientConn),
	}

	m := &mockDockerClient{
		execCreateResp:  client.ExecCreateResult{ID: "exec-1"},
		execAttachResp:  client.ExecAttachResult{HijackedResponse: hijacked},
		execInspectResp: client.ExecInspectResult{ID: "exec-1", ExitCode: 2, Running: false},
	}
	r := newTestRunner(t, m)
	_, err := r.Exec(context.Background(), "cid-1", []string{"false"})
	assert.Error(t, err)
}

func TestRunner_Inspect_MapsContainerInfo(t *testing.T) {
	m := &mockDockerClient{
		inspectResp: client.ContainerInspectResult{
			Container: container.InspectResponse{
				ID:   "cid-abc",
				Name: "/my-container",
				State: &container.State{
					Status:  container.StateRunning,
					Running: true,
				},
			},
		},
	}
	r := newTestRunner(t, m)
	info, err := r.Inspect(context.Background(), "cid-abc")
	require.NoError(t, err)
	assert.Equal(t, "cid-abc", info.ID)
	assert.Equal(t, "/my-container", info.Name)
	assert.Equal(t, "running", info.Status)
	assert.True(t, info.Running)
	assert.Len(t, m.inspectCalls, 1)
}

func TestRunner_Inspect_RejectsInvalidContainerID(t *testing.T) {
	m := &mockDockerClient{}
	r := newTestRunner(t, m)
	_, err := r.Inspect(context.Background(), "$(evil)")
	assert.Error(t, err)
	assert.Empty(t, m.inspectCalls)
}

func TestRunner_Stop_CallsContainerStop(t *testing.T) {
	m := &mockDockerClient{}
	r := newTestRunner(t, m)
	err := r.Stop(context.Background(), "cid-1")
	require.NoError(t, err)
	require.Len(t, m.stopCalls, 1)
	assert.Equal(t, "cid-1", m.stopCalls[0])
}

func TestRunner_Stop_RejectsInvalidContainerID(t *testing.T) {
	m := &mockDockerClient{}
	r := newTestRunner(t, m)
	err := r.Stop(context.Background(), "; rm -rf /")
	assert.Error(t, err)
	assert.Empty(t, m.stopCalls)
}

func TestRunner_Remove_CallsContainerRemove(t *testing.T) {
	m := &mockDockerClient{}
	r := newTestRunner(t, m)
	err := r.Remove(context.Background(), "cid-1")
	require.NoError(t, err)
	require.Len(t, m.removeCalls, 1)
	assert.Equal(t, "cid-1", m.removeCalls[0])
}

func TestRunner_Remove_RejectsInvalidContainerID(t *testing.T) {
	m := &mockDockerClient{}
	r := newTestRunner(t, m)
	err := r.Remove(context.Background(), "")
	assert.Error(t, err)
	assert.Empty(t, m.removeCalls)
}

// ---------- Phase 2 sandbox fields ----------

func TestRunOptions_AppliesNoNewPrivs(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{
		Image:      "alpine:3.19",
		NoNewPrivs: true,
	})
	require.NoError(t, err)
	hc := m.createCalls[0].opts.HostConfig
	require.NotNil(t, hc)
	assert.Contains(t, hc.SecurityOpt, "no-new-privileges:true")
}

func TestRunOptions_AppliesSeccompProfile(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{
		Image:          "alpine:3.19",
		SeccompProfile: "/etc/docker/seccomp.json",
	})
	require.NoError(t, err)
	hc := m.createCalls[0].opts.HostConfig
	require.NotNil(t, hc)
	assert.Contains(t, hc.SecurityOpt, "seccomp=/etc/docker/seccomp.json")
}

func TestRunOptions_ComposesSecurityOpt(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{
		Image:          "alpine:3.19",
		NoNewPrivs:     true,
		SeccompProfile: "/x",
	})
	require.NoError(t, err)
	hc := m.createCalls[0].opts.HostConfig
	require.NotNil(t, hc)
	assert.ElementsMatch(t, []string{"no-new-privileges:true", "seccomp=/x"}, hc.SecurityOpt)
}

func TestRunOptions_AppliesReadOnlyRootfs(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{
		Image:          "alpine:3.19",
		ReadOnlyRootfs: true,
	})
	require.NoError(t, err)
	hc := m.createCalls[0].opts.HostConfig
	require.NotNil(t, hc)
	assert.True(t, hc.ReadonlyRootfs)
}

func TestRunOptions_AppliesTmpfs(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{
		Image: "alpine:3.19",
		Tmpfs: map[string]string{"/tmp": "rw,size=64m"},
	})
	require.NoError(t, err)
	hc := m.createCalls[0].opts.HostConfig
	require.NotNil(t, hc)
	assert.Equal(t, "rw,size=64m", hc.Tmpfs["/tmp"])
}

func TestRunOptions_AppliesCapDrop(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{
		Image:   "alpine:3.19",
		CapDrop: []string{"ALL"},
	})
	require.NoError(t, err)
	hc := m.createCalls[0].opts.HostConfig
	require.NotNil(t, hc)
	assert.Contains(t, []string(hc.CapDrop), "ALL")
}

func TestRunOptions_AppliesCapAdd(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{
		Image:  "alpine:3.19",
		CapAdd: []string{"NET_BIND_SERVICE"},
	})
	require.NoError(t, err)
	hc := m.createCalls[0].opts.HostConfig
	require.NotNil(t, hc)
	assert.Contains(t, []string(hc.CapAdd), "NET_BIND_SERVICE")
}

func TestRunOptions_AppliesRuntime(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{
		Image:   "alpine:3.19",
		Runtime: "runsc",
	})
	require.NoError(t, err)
	hc := m.createCalls[0].opts.HostConfig
	require.NotNil(t, hc)
	assert.Equal(t, "runsc", hc.Runtime)

	// Empty runtime passes through as empty.
	m2 := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-2"}}
	r2 := newTestRunner(t, m2)
	_, err = r2.Run(context.Background(), RunOptions{Image: "alpine:3.19"})
	require.NoError(t, err)
	assert.Equal(t, "", m2.createCalls[0].opts.HostConfig.Runtime)
}

func TestRunOptions_DefaultsAreEmpty(t *testing.T) {
	m := &mockDockerClient{createResp: client.ContainerCreateResult{ID: "cid-1"}}
	r := newTestRunner(t, m)
	_, err := r.Run(context.Background(), RunOptions{Image: "alpine:3.19"})
	require.NoError(t, err)
	hc := m.createCalls[0].opts.HostConfig
	require.NotNil(t, hc)
	assert.Empty(t, hc.SecurityOpt)
	assert.False(t, hc.ReadonlyRootfs)
	assert.Empty(t, hc.Tmpfs)
	assert.Empty(t, []string(hc.CapDrop))
	assert.Empty(t, []string(hc.CapAdd))
	assert.Equal(t, "", hc.Runtime)
}

func TestRunOptions_NoPrivilegedField(t *testing.T) {
	// SBX-05 invariant: RunOptions must never expose a Privileged field.
	_, found := reflect.TypeOf(RunOptions{}).FieldByName("Privileged")
	assert.False(t, found, "RunOptions must not expose a Privileged field (SBX-05)")
}

// ---------- Integration test (skipped under -short) ----------

func TestDockerIntegration_RunInspectStopRemove(t *testing.T) {
	if testing.Short() {
		t.Skip("integration test requires Docker daemon; skipping under -short")
	}
	r, err := NewRunner(zerolog.Nop())
	require.NoError(t, err)

	ctx := context.Background()
	id, err := r.Run(ctx, RunOptions{
		Image:  "alpine:3.19",
		Cmd:    []string{"sleep", "30"},
		Remove: false,
	})
	require.NoError(t, err)
	t.Cleanup(func() {
		_ = r.Stop(context.Background(), id)
		_ = r.Remove(context.Background(), id)
	})

	info, err := r.Inspect(ctx, id)
	require.NoError(t, err)
	assert.True(t, info.Running)

	require.NoError(t, r.Stop(ctx, id))
	info, err = r.Inspect(ctx, id)
	require.NoError(t, err)
	assert.False(t, info.Running)
	require.NoError(t, r.Remove(ctx, id))
}
