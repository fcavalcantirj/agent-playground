// Package docker provides a thin, testable wrapper over the Docker Engine SDK
// (github.com/moby/moby/client) used by the Agent Playground orchestrator to
// manage per-user containers.
//
// Design notes:
//
//   - Uses the Docker Engine SDK directly per CLAUDE.md — NO os/exec CLI shelling.
//   - Exposes a DockerClient interface that covers the subset of SDK methods we
//     need. Production builds inject *client.Client; tests inject a mock.
//   - All user-controlled inputs (container IDs, image names, env vars, mount
//     paths) are validated against shell-metacharacter injection BEFORE they
//     reach the SDK, even though the SDK uses the Docker daemon's HTTP API
//     (not a shell). Defense in depth for Phase 5 session lifecycle.
//
// This is Plan 01-02; Phase 5 wires this runner into the session lifecycle.
package docker

import (
	"context"
	"fmt"
	"io"
	"regexp"
	"strings"

	"github.com/moby/moby/api/types/container"
	"github.com/moby/moby/client"
	"github.com/rs/zerolog"
)

// DockerClient abstracts the Docker Engine SDK client methods used by Runner.
// In production, this is satisfied by *client.Client from github.com/moby/moby/client.
// In tests, inject a mock implementation.
//
// Signatures mirror the v0.4.0 moby/moby/client options-struct API.
type DockerClient interface {
	ContainerCreate(ctx context.Context, opts client.ContainerCreateOptions) (client.ContainerCreateResult, error)
	ContainerStart(ctx context.Context, containerID string, opts client.ContainerStartOptions) (client.ContainerStartResult, error)
	ContainerStop(ctx context.Context, containerID string, opts client.ContainerStopOptions) (client.ContainerStopResult, error)
	ContainerRemove(ctx context.Context, containerID string, opts client.ContainerRemoveOptions) (client.ContainerRemoveResult, error)
	ContainerInspect(ctx context.Context, containerID string, opts client.ContainerInspectOptions) (client.ContainerInspectResult, error)
	ExecCreate(ctx context.Context, containerID string, opts client.ExecCreateOptions) (client.ExecCreateResult, error)
	ExecAttach(ctx context.Context, execID string, opts client.ExecAttachOptions) (client.ExecAttachResult, error)
	ExecInspect(ctx context.Context, execID string, opts client.ExecInspectOptions) (client.ExecInspectResult, error)
}

// RunOptions captures everything Runner.Run needs to create and start a
// container. Keep this struct additive — adding fields must not break existing
// callers.
type RunOptions struct {
	// Image is the fully qualified image reference, e.g. "alpine:3.19" or
	// "ghcr.io/owner/repo:tag". Validated against shell metacharacters.
	Image string
	// Name is an optional container name. If empty, Docker assigns a random one.
	Name string
	// Env holds environment variables passed to the container. Keys must match
	// [A-Z_][A-Z0-9_]*; values must not contain backticks or $( ) sequences.
	Env map[string]string
	// Mounts is a list of bind mounts in "host:container[:ro]" format.
	Mounts []string
	// Network is an optional Docker network name (e.g. a per-tenant bridge).
	Network string
	// Memory is the memory limit in bytes. 0 = no explicit limit.
	Memory int64
	// CPUs is the CPU quota in nanoCPUs (1 vCPU = 1e9). 0 = no explicit limit.
	CPUs int64
	// PidsLimit caps the number of PIDs the container may create. 0 = no limit.
	PidsLimit int64
	// Remove controls the --rm auto-remove behaviour.
	Remove bool
	// Labels are attached to the container for orchestration/reconciliation.
	Labels map[string]string
	// Cmd is the command to run inside the container. If empty, the image
	// ENTRYPOINT/CMD is used.
	Cmd []string
}

// ContainerInfo is the Runner's distilled view of a Docker container. It is
// intentionally smaller than container.InspectResponse so callers are not
// tied to SDK internals.
type ContainerInfo struct {
	ID      string
	Name    string
	Status  string // "created", "running", "paused", "restarting", "removing", "exited", "dead"
	Running bool
}

// Runner manages Docker container lifecycle operations via the Engine SDK.
type Runner struct {
	client DockerClient
	logger zerolog.Logger
}

// NewRunner creates a Runner backed by a real Docker Engine SDK client.
// It uses env-based configuration (DOCKER_HOST etc.) and automatic API version
// negotiation, matching CLAUDE.md §Version Compatibility.
func NewRunner(logger zerolog.Logger) (*Runner, error) {
	cli, err := client.New(client.FromEnv, client.WithAPIVersionNegotiation())
	if err != nil {
		return nil, fmt.Errorf("docker: new client: %w", err)
	}
	return &Runner{client: cli, logger: logger}, nil
}

// Compile-time check that *client.Client from the Docker Engine SDK satisfies
// our DockerClient interface. If the upstream SDK changes a signature, this
// line breaks the build — surfacing the drift before runtime.
var _ DockerClient = (*client.Client)(nil)

// NewRunnerWithClient builds a Runner around an injected DockerClient. Used
// by tests (with a mock) and by higher layers that want to own client lifecycle.
func NewRunnerWithClient(cli DockerClient, logger zerolog.Logger) *Runner {
	return &Runner{client: cli, logger: logger}
}

// Run validates inputs, creates a container via the SDK, and starts it.
// On success it returns the container ID. If the start call fails after the
// create call succeeded, Run attempts a best-effort Remove of the orphaned
// container so callers don't leak infrastructure.
func (r *Runner) Run(ctx context.Context, opts RunOptions) (string, error) {
	if err := validateImageName(opts.Image); err != nil {
		return "", fmt.Errorf("docker run: %w", err)
	}
	if opts.Name != "" {
		if err := validateContainerID(opts.Name); err != nil {
			return "", fmt.Errorf("docker run: invalid name: %w", err)
		}
	}

	envSlice := make([]string, 0, len(opts.Env))
	for k, v := range opts.Env {
		kv := k + "=" + v
		if err := validateEnvVar(kv); err != nil {
			return "", fmt.Errorf("docker run: %w", err)
		}
		envSlice = append(envSlice, kv)
	}

	for _, m := range opts.Mounts {
		if err := validateMountPath(m); err != nil {
			return "", fmt.Errorf("docker run: %w", err)
		}
	}

	cfg := &container.Config{
		// NOTE: Image lives on ContainerCreateOptions.Image (SDK-level shortcut);
		// leave Config.Image empty to avoid the SDK's "either Image or config.Image
		// should be set" invariant.
		Env:    envSlice,
		Cmd:    opts.Cmd,
		Labels: opts.Labels,
	}

	hostCfg := &container.HostConfig{
		AutoRemove:  opts.Remove,
		Binds:       opts.Mounts,
		NetworkMode: container.NetworkMode(opts.Network),
	}
	hostCfg.Memory = opts.Memory
	hostCfg.NanoCPUs = opts.CPUs
	if opts.PidsLimit > 0 {
		pl := opts.PidsLimit
		hostCfg.PidsLimit = &pl
	}

	createRes, err := r.client.ContainerCreate(ctx, client.ContainerCreateOptions{
		Config:     cfg,
		HostConfig: hostCfg,
		Name:       opts.Name,
		Image:      opts.Image,
	})
	if err != nil {
		r.logger.Error().Err(err).Str("image", opts.Image).Msg("docker create failed")
		return "", fmt.Errorf("docker run: create: %w", err)
	}

	if _, err := r.client.ContainerStart(ctx, createRes.ID, client.ContainerStartOptions{}); err != nil {
		r.logger.Error().Err(err).Str("container", createRes.ID).Msg("docker start failed")
		// Best-effort cleanup so we don't leak orphan containers.
		if _, rmErr := r.client.ContainerRemove(ctx, createRes.ID, client.ContainerRemoveOptions{Force: true}); rmErr != nil {
			r.logger.Warn().Err(rmErr).Str("container", createRes.ID).Msg("orphan container cleanup failed")
		}
		return "", fmt.Errorf("docker run: start %s: %w", createRes.ID, err)
	}

	r.logger.Info().Str("container", createRes.ID).Str("image", opts.Image).Msg("container started")
	return createRes.ID, nil
}

// Exec runs a command inside a running container and returns its combined
// output as a byte slice. If the exec exits non-zero, Exec returns an error
// that includes the exit code.
//
// The caller is responsible for validating cmd elements — Exec does NOT
// interpret the command through a shell (the SDK sends []string directly to
// the daemon), so argv splitting attacks are structurally blocked, but passing
// unvalidated user input as a single element is still the caller's problem.
func (r *Runner) Exec(ctx context.Context, containerID string, cmd []string) ([]byte, error) {
	if err := validateContainerID(containerID); err != nil {
		return nil, fmt.Errorf("docker exec: %w", err)
	}

	createRes, err := r.client.ExecCreate(ctx, containerID, client.ExecCreateOptions{
		Cmd:          cmd,
		AttachStdout: true,
		AttachStderr: true,
	})
	if err != nil {
		return nil, fmt.Errorf("docker exec: create %s: %w", containerID, err)
	}

	attachRes, err := r.client.ExecAttach(ctx, createRes.ID, client.ExecAttachOptions{})
	if err != nil {
		return nil, fmt.Errorf("docker exec: attach %s: %w", createRes.ID, err)
	}
	// Best-effort close of the hijacked connection.
	defer func() {
		if attachRes.Conn != nil {
			_ = attachRes.Conn.Close()
		}
	}()

	var output []byte
	if attachRes.Reader != nil {
		output, err = io.ReadAll(attachRes.Reader)
		if err != nil {
			return nil, fmt.Errorf("docker exec: read output %s: %w", createRes.ID, err)
		}
	}

	inspectRes, err := r.client.ExecInspect(ctx, createRes.ID, client.ExecInspectOptions{})
	if err != nil {
		return output, fmt.Errorf("docker exec: inspect %s: %w", createRes.ID, err)
	}
	if inspectRes.ExitCode != 0 {
		return output, fmt.Errorf("docker exec: %s exited with code %d", createRes.ID, inspectRes.ExitCode)
	}

	r.logger.Debug().Str("container", containerID).Strs("cmd", cmd).Msg("exec completed")
	return output, nil
}

// Inspect returns a distilled view of a container's current state.
func (r *Runner) Inspect(ctx context.Context, containerID string) (*ContainerInfo, error) {
	if err := validateContainerID(containerID); err != nil {
		return nil, fmt.Errorf("docker inspect: %w", err)
	}

	res, err := r.client.ContainerInspect(ctx, containerID, client.ContainerInspectOptions{})
	if err != nil {
		return nil, fmt.Errorf("docker inspect %s: %w", containerID, err)
	}

	info := &ContainerInfo{
		ID:   res.Container.ID,
		Name: res.Container.Name,
	}
	if res.Container.State != nil {
		info.Status = string(res.Container.State.Status)
		info.Running = res.Container.State.Running
	}
	return info, nil
}

// Stop requests a graceful container stop with the daemon default grace period.
// Callers that need a custom timeout should call ContainerStop on the SDK
// client directly.
func (r *Runner) Stop(ctx context.Context, containerID string) error {
	if err := validateContainerID(containerID); err != nil {
		return fmt.Errorf("docker stop: %w", err)
	}
	if _, err := r.client.ContainerStop(ctx, containerID, client.ContainerStopOptions{}); err != nil {
		r.logger.Error().Err(err).Str("container", containerID).Msg("docker stop failed")
		return fmt.Errorf("docker stop %s: %w", containerID, err)
	}
	r.logger.Info().Str("container", containerID).Msg("container stopped")
	return nil
}

// Kill is an alias for Stop provided for MSV naming compatibility. Session
// lifecycle code ported from MSV calls r.Kill; new code should call Stop.
func (r *Runner) Kill(ctx context.Context, containerID string) error {
	return r.Stop(ctx, containerID)
}

// Remove deletes a (stopped) container. Pass Force via the SDK directly if you
// need to remove a running container.
func (r *Runner) Remove(ctx context.Context, containerID string) error {
	if err := validateContainerID(containerID); err != nil {
		return fmt.Errorf("docker remove: %w", err)
	}
	if _, err := r.client.ContainerRemove(ctx, containerID, client.ContainerRemoveOptions{Force: false}); err != nil {
		r.logger.Error().Err(err).Str("container", containerID).Msg("docker remove failed")
		return fmt.Errorf("docker remove %s: %w", containerID, err)
	}
	r.logger.Info().Str("container", containerID).Msg("container removed")
	return nil
}

// -----------------------------------------------------------------------------
// Input validation
// -----------------------------------------------------------------------------
//
// These validators intentionally reject more than strict Docker naming rules
// would require: they also block shell metacharacters so that even if a caller
// accidentally passes a validated string to a helper that shells out, it stays
// safe. Defense in depth.

var (
	// containerIDPattern: Docker names and IDs. Must start alnum, then
	// alphanumerics, underscore, period, or dash. Max 128 chars.
	containerIDPattern = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$`)

	// imageNamePattern: registry/repo:tag style. Allows alnum, underscore,
	// period, slash, and dash; optional :tag suffix.
	imageNamePattern = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9_./\-]*(:[a-zA-Z0-9_.\-]+)?$`)

	// envKeyPattern: standard POSIX-ish env var key.
	envKeyPattern = regexp.MustCompile(`^[A-Z_][A-Z0-9_]*$`)
)

const (
	maxContainerIDLen = 128
	maxImageNameLen   = 256
)

// validateContainerID checks a container name or ID against shell injection
// and Docker naming rules.
func validateContainerID(id string) error {
	if id == "" {
		return fmt.Errorf("empty container ID")
	}
	if len(id) > maxContainerIDLen {
		return fmt.Errorf("container ID too long: %d > %d", len(id), maxContainerIDLen)
	}
	if !containerIDPattern.MatchString(id) {
		return fmt.Errorf("invalid container ID: %q", id)
	}
	return nil
}

// validateImageName checks a Docker image reference.
func validateImageName(image string) error {
	if image == "" {
		return fmt.Errorf("empty image name")
	}
	if len(image) > maxImageNameLen {
		return fmt.Errorf("image name too long: %d > %d", len(image), maxImageNameLen)
	}
	if !imageNamePattern.MatchString(image) {
		return fmt.Errorf("invalid image name: %q", image)
	}
	return nil
}

// validateEnvVar checks a "KEY=VALUE" env var string. Keys must match
// envKeyPattern; values must not contain backticks or $( command substitution
// sequences (defense in depth against CLI shell-outs).
func validateEnvVar(env string) error {
	idx := strings.Index(env, "=")
	if idx <= 0 {
		return fmt.Errorf("invalid env var: missing '=' or empty key in %q", env)
	}
	key := env[:idx]
	val := env[idx+1:]
	if !envKeyPattern.MatchString(key) {
		return fmt.Errorf("invalid env var key: %q", key)
	}
	if strings.Contains(val, "`") || strings.Contains(val, "$(") {
		return fmt.Errorf("invalid env var value: contains shell substitution in %q", env)
	}
	return nil
}

// validateMountPath checks a "host:container[:ro]" bind mount spec for path
// traversal and shell metacharacters.
func validateMountPath(mount string) error {
	if mount == "" {
		return fmt.Errorf("empty mount path")
	}
	parts := strings.Split(mount, ":")
	if len(parts) < 2 || len(parts) > 3 {
		return fmt.Errorf("invalid mount format: expected host:container[:opts], got %q", mount)
	}
	for _, p := range parts {
		if p == "" {
			return fmt.Errorf("invalid mount: empty component in %q", mount)
		}
		if strings.Contains(p, "..") {
			return fmt.Errorf("invalid mount: path traversal in %q", mount)
		}
		if strings.ContainsAny(p, "`$|;&<>*?\\\"'") {
			return fmt.Errorf("invalid mount: shell metacharacter in %q", mount)
		}
	}
	return nil
}
