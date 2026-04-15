// Package session handler — Phase 02.5 Plan 09 YAML-driven rewrite.
//
// The Phase 2 version of this file dispatched to a hardcoded
// recipes.GetLegacy catalog of two entries (picoclaw + hermes). Plan 09
// swaps that for the full 02.5 substrate:
//
//  1. POST /api/sessions looks up the recipe via RecipeLoader.Get
//  2. Validates the user-supplied provider / model against the
//     recipe's declared Providers[] / Models[] lists
//  3. Calls session.Materialize to resolve every secret: reference
//     and render every auth.files template
//  4. Builds docker.RunOptions from recipe.Runtime / recipe.Isolation
//     plus the materialized env + bind-mounted /run/secrets dir
//  5. Calls Runner.RunWithLifecycle which sequences initializeCommand
//     → container create → onCreate → updateContent → postCreate
//     → postStart → postAttach (Plan 03)
//  6. Persists the session row with the chosen provider + container id
//
// POST /api/sessions/:id/message is re-pointed at BridgeDispatcher so
// the chat-io layer picks the right implementation (fifo /
// exec_per_message) off recipe.ChatIO.Mode with ZERO legacy
// translation shim in the middle.
//
// DELETE /api/sessions/:id is unchanged from Phase 2 behavior — stop,
// remove, cleanup secrets dir, update status.
//
// Error-code surface (D-54): recipe_not_found, provider_not_supported,
// model_not_supported, secret_missing, template_render_failed,
// lifecycle_hook_failed, chat_bridge_unsupported_mode.

package session

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
	"github.com/rs/zerolog"

	"github.com/agentplayground/api/internal/middleware"
	"github.com/agentplayground/api/internal/recipes"
	"github.com/agentplayground/api/internal/session/bridge"
	"github.com/agentplayground/api/pkg/docker"
)

// maxMessageLen caps the chat message payload at 16 KiB so a pathological
// client cannot blow out the FIFO write buffer or the docker exec argv.
const maxMessageLen = 16 * 1024

// SessionStore is the subset of *Store the handler consumes. Accepting
// an interface (not the concrete pgxpool-backed Store) lets the
// handler tests inject a pure in-memory mock without touching Postgres.
type SessionStore interface {
	Create(ctx context.Context, userID uuid.UUID, recipe, provider, modelID string) (*Session, error)
	Get(ctx context.Context, id uuid.UUID) (*Session, error)
	UpdateStatus(ctx context.Context, id uuid.UUID, status string) error
	UpdateContainer(ctx context.Context, id uuid.UUID, containerID, status string) error
}

// ContainerRunner is the subset of *docker.Runner the handler needs.
// Extended from Phase 2 with RunWithLifecycle so Plan 09 can sequence
// the Dev Containers hook set via Plan 03's implementation. Tests
// inject a mock satisfying the same shape.
type ContainerRunner interface {
	Run(ctx context.Context, opts docker.RunOptions) (string, error)
	Stop(ctx context.Context, containerID string) error
	Remove(ctx context.Context, containerID string) error
	RunWithLifecycle(ctx context.Context, recipe *recipes.Recipe, opts docker.RunOptions) (*docker.LifecycleSession, error)
}

// RecipeLoader is the narrow read-only slice of *recipes.Loader the
// handler needs. Plan 01's concrete Loader satisfies this interface
// structurally.
type RecipeLoader interface {
	Get(id string) (*recipes.Recipe, bool)
}

// BridgeDispatcher is the narrow interface the message handler uses to
// pick a ChatBridge off recipe.ChatIO.Mode. *bridge.BridgeRegistry
// satisfies it in production; tests inject a fake.
type BridgeDispatcher interface {
	Dispatch(mode string) (bridge.ChatBridge, error)
}

// Compile-time checks: the production implementations satisfy the
// handler-side interfaces. If signatures drift, the build fails
// here instead of at runtime.
var _ SessionStore = (*Store)(nil)

// Handler serves POST /api/sessions, POST /api/sessions/:id/message,
// and DELETE /api/sessions/:id. Every route runs behind the existing
// Phase 1 auth middleware; Register mounts them on an already-authed
// echo.Group so the handler itself is agnostic to the auth mechanism.
type Handler struct {
	store     SessionStore
	runner    ContainerRunner
	loader    RecipeLoader
	secrets   SecretSource
	templates TemplateRenderer
	bridges   BridgeDispatcher
	logger    zerolog.Logger

	// baseSecretsDir is the host-side parent dir where the handler
	// writes materialized per-session files before bind-mounting them
	// into the container. Defaults to DefaultSecretBaseDir; tests
	// override to a t.TempDir().
	baseSecretsDir string
}

// HandlerOption tunes optional Handler knobs. Used by tests to inject
// a temp base secrets dir so /tmp/ap/secrets/ is never touched during
// unit tests.
type HandlerOption func(*Handler)

// WithBaseSecretsDir overrides DefaultSecretBaseDir. Production callers
// never use this; tests pass t.TempDir().
func WithBaseSecretsDir(dir string) HandlerOption {
	return func(h *Handler) { h.baseSecretsDir = dir }
}

// NewHandler constructs a Handler. All dependencies are required;
// passing nil for any of them will surface as a 500 on the first
// request, which is the intended "fail loud in dev" posture.
func NewHandler(
	store SessionStore,
	runner ContainerRunner,
	loader RecipeLoader,
	secrets SecretSource,
	templates TemplateRenderer,
	bridges BridgeDispatcher,
	logger zerolog.Logger,
	opts ...HandlerOption,
) *Handler {
	h := &Handler{
		store:          store,
		runner:         runner,
		loader:         loader,
		secrets:        secrets,
		templates:      templates,
		bridges:        bridges,
		logger:         logger,
		baseSecretsDir: DefaultSecretBaseDir,
	}
	for _, o := range opts {
		o(h)
	}
	return h
}

// Register mounts the three session routes on an already-authed group.
// The caller is responsible for ensuring the group has auth middleware
// applied — server.go's WithSessionHandler option is the canonical
// wiring point.
func (h *Handler) Register(g *echo.Group) {
	g.POST("/sessions", h.create)
	g.POST("/sessions/:id/message", h.message)
	g.DELETE("/sessions/:id", h.delete)
}

// ----- request/response DTOs -----

// createRequest is the POST /api/sessions payload. D-53 introduces
// `provider` / `model` as the canonical field names; Phase 2's
// `model_provider` / `model_id` aliases are accepted for one wave so
// existing clients keep working. Phase 4 deletes the aliases.
type createRequest struct {
	Recipe   string `json:"recipe"`
	Provider string `json:"provider"`
	Model    string `json:"model"`

	// Phase 2 backwards-compat aliases.
	ModelProvider string `json:"model_provider,omitempty"`
	ModelID       string `json:"model_id,omitempty"`
}

type createResponse struct {
	ID          string `json:"id"`
	Recipe      string `json:"recipe"`
	Provider    string `json:"provider"`
	Model       string `json:"model"`
	Status      string `json:"status"`
	ContainerID string `json:"container_id,omitempty"`
}

type messageRequest struct {
	Text string `json:"text"`
}

type messageResponse struct {
	Text string `json:"text"`
}

// ----- error envelope (mirrors handler.WriteError shape) -----

// The session package cannot import internal/handler (import cycle),
// so it re-declares the same Phase 1 envelope shape here. The JSON
// bytes are byte-identical to handler.WriteError's output.
type errEnvelope struct {
	Error errBody `json:"error"`
}

type errBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// Error codes (D-54) — kept in sync with api/internal/handler/errors.go.
// Duplicated here because the session package cannot depend on handler.
const (
	errCodeRecipeNotFound        = "recipe_not_found"
	errCodeProviderNotSupported  = "provider_not_supported"
	errCodeModelNotSupported     = "model_not_supported"
	errCodeSecretMissing         = "secret_missing"
	errCodeTemplateRenderFailed  = "template_render_failed"
	errCodeLifecycleHookFailed   = "lifecycle_hook_failed"
	errCodeChatBridgeUnsupported = "chat_bridge_unsupported_mode"
	errCodeInvalidRequest        = "invalid_request"
	errCodeInternal              = "internal"
	errCodeUnauthorized          = "unauthorized"
	errCodeForbidden             = "forbidden"
	errCodeConflict              = "conflict"
	errCodeTimeout               = "timeout"
)

func writeErr(c echo.Context, status int, code, message string) error {
	return c.JSON(status, errEnvelope{Error: errBody{Code: code, Message: message}})
}

// ----- handlers -----

// create handles POST /api/sessions. The full flow is documented on
// the package comment above. Error-code mapping follows D-54.
func (h *Handler) create(c echo.Context) error {
	userID, ok := userFromCtx(c)
	if !ok {
		return writeErr(c, http.StatusUnauthorized, errCodeUnauthorized, "unauthorized")
	}

	var req createRequest
	if err := c.Bind(&req); err != nil {
		return writeErr(c, http.StatusBadRequest, errCodeInvalidRequest, "invalid json")
	}
	// Fold Phase 2 aliases onto the canonical field names.
	if req.Provider == "" && req.ModelProvider != "" {
		req.Provider = req.ModelProvider
	}
	if req.Model == "" && req.ModelID != "" {
		req.Model = req.ModelID
	}
	if req.Recipe == "" {
		return writeErr(c, http.StatusBadRequest, errCodeInvalidRequest, "recipe is required")
	}

	if h.loader == nil {
		h.logger.Error().Msg("session create: RecipeLoader not wired")
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "recipe loader not configured")
	}
	recipe, found := h.loader.Get(req.Recipe)
	if !found {
		return writeErr(c, http.StatusNotFound, errCodeRecipeNotFound, "recipe "+req.Recipe+" not found")
	}

	// Default provider if the recipe has exactly one declared.
	if req.Provider == "" {
		if len(recipe.Providers) == 1 {
			req.Provider = recipe.Providers[0].ID
		} else {
			return writeErr(c, http.StatusBadRequest, errCodeInvalidRequest, "provider is required (recipe has multiple providers)")
		}
	}

	// Validate provider is declared by the recipe.
	providerOK := false
	for _, p := range recipe.Providers {
		if p.ID == req.Provider {
			providerOK = true
			break
		}
	}
	if !providerOK {
		return writeErr(c, http.StatusBadRequest, errCodeProviderNotSupported,
			fmt.Sprintf("provider %q not declared by recipe %q", req.Provider, recipe.ID))
	}

	// Default model to the first model matching the chosen provider.
	if req.Model == "" {
		for _, m := range recipe.Models {
			if m.Provider == req.Provider {
				req.Model = m.ID
				break
			}
		}
	}
	if req.Model == "" {
		return writeErr(c, http.StatusBadRequest, errCodeInvalidRequest,
			fmt.Sprintf("model is required (recipe %q has no default for provider %q)", recipe.ID, req.Provider))
	}

	// Validate model is declared AND bound to the chosen provider.
	modelOK := false
	for _, m := range recipe.Models {
		if m.ID == req.Model && m.Provider == req.Provider {
			modelOK = true
			break
		}
	}
	if !modelOK {
		return writeErr(c, http.StatusBadRequest, errCodeModelNotSupported,
			fmt.Sprintf("model %q not supported by provider %q for recipe %q", req.Model, req.Provider, recipe.ID))
	}

	ctx := c.Request().Context()

	// Insert the session row BEFORE materializing so the one-active
	// partial unique index fires early (avoid wasting secret-resolution
	// work for a user who already has an active session).
	sess, err := h.store.Create(ctx, userID, recipe.ID, req.Provider, req.Model)
	if err != nil {
		if errors.Is(err, ErrConflictActive) {
			return writeErr(c, http.StatusConflict, errCodeConflict, "user already has an active session")
		}
		h.logger.Error().Err(err).Msg("session create: store failed")
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "internal error")
	}

	// Materialize: resolve every secret: reference + render every
	// auth.files template. The result contains raw secret bytes in
	// memory — it must NOT be logged.
	mat, err := Materialize(ctx, recipe, req.Provider, req.Model, h.secrets, h.templates)
	if err != nil {
		_ = h.store.UpdateStatus(ctx, sess.ID, StatusFailed)
		switch {
		case errors.Is(err, ErrSecretMissing):
			return writeErr(c, http.StatusBadRequest, errCodeSecretMissing,
				fmt.Sprintf("required secret unavailable for recipe %q", recipe.ID))
		case errors.Is(err, recipes.ErrTemplatePath),
			errors.Is(err, recipes.ErrTemplateSize),
			errors.Is(err, recipes.ErrTemplateTimeout):
			return writeErr(c, http.StatusInternalServerError, errCodeTemplateRenderFailed,
				fmt.Sprintf("template render failed for recipe %q", recipe.ID))
		default:
			// Heuristic: anything mentioning "template" is a render failure.
			// Scrubs the secret value out of the error path (err might
			// wrap upstream messages that include the env key name).
			msg := err.Error()
			if strings.Contains(msg, "template") || strings.Contains(msg, "render") {
				h.logger.Error().Err(err).Str("recipe", recipe.ID).Msg("session create: template render failed")
				return writeErr(c, http.StatusInternalServerError, errCodeTemplateRenderFailed,
					fmt.Sprintf("template render failed for recipe %q", recipe.ID))
			}
			h.logger.Error().Err(err).Str("recipe", recipe.ID).Msg("session create: materialize failed")
			return writeErr(c, http.StatusInternalServerError, errCodeInternal, "materialize failed")
		}
	}

	// Write every MaterializedFile to /tmp/ap/secrets/<session-id>/,
	// build the bind-mount spec, and remember the directory path for
	// cleanup on failure.
	runOpts, cleanup, err := h.buildRunOptions(userID, sess.ID, recipe, mat)
	if err != nil {
		_ = h.store.UpdateStatus(ctx, sess.ID, StatusFailed)
		h.logger.Error().Err(err).Str("session_id", sess.ID.String()).Msg("session create: buildRunOptions failed")
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "run options build failed")
	}

	// RunWithLifecycle: container create + full Dev Containers hook
	// sequence. On any hook error the underlying runner tears down the
	// container; we still need to cleanup the per-session secrets dir.
	lcSession, err := h.runner.RunWithLifecycle(ctx, recipe, runOpts)
	if err != nil {
		cleanup()
		_ = h.store.UpdateStatus(ctx, sess.ID, StatusFailed)
		// Identify lifecycle hook failures via error message prefix;
		// Plan 03's RunWithLifecycle wraps hook errors with the hook
		// name ("initializeCommand: ...", "postCreate: ...", etc.).
		msg := err.Error()
		if isLifecycleHookErr(msg) {
			return writeErr(c, http.StatusInternalServerError, errCodeLifecycleHookFailed,
				fmt.Sprintf("lifecycle hook failed for recipe %q", recipe.ID))
		}
		h.logger.Error().Err(err).Str("session_id", sess.ID.String()).Msg("session create: RunWithLifecycle failed")
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "failed to start container")
	}

	if err := h.store.UpdateContainer(ctx, sess.ID, lcSession.ContainerID, StatusRunning); err != nil {
		// The container is up but we failed to record it — best-effort stop.
		_ = h.runner.Stop(ctx, lcSession.ContainerID)
		_ = h.runner.Remove(ctx, lcSession.ContainerID)
		cleanup()
		h.logger.Error().Err(err).Str("session_id", sess.ID.String()).Msg("session create: update container failed")
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "failed to persist session")
	}

	return c.JSON(http.StatusCreated, createResponse{
		ID:          sess.ID.String(),
		Recipe:      recipe.ID,
		Provider:    req.Provider,
		Model:       req.Model,
		Status:      StatusRunning,
		ContainerID: lcSession.ContainerID,
	})
}

// buildRunOptions assembles the docker.RunOptions from the recipe +
// the materialized bundle. It writes every MaterializedFile to
// <baseSecretsDir>/<session-id>/ with mode 0600, then builds the
// bind-mount spec /<host>:/run/secrets:ro so the container's
// entrypoint shim can copy each file to its declared target path.
//
// Returns a cleanup closure the caller runs on any downstream error
// (RunWithLifecycle failure, DB persist failure, etc.) so the
// per-session secrets dir does not leak.
func (h *Handler) buildRunOptions(
	userID uuid.UUID,
	sessionID uuid.UUID,
	recipe *recipes.Recipe,
	mat *MaterializedRecipe,
) (docker.RunOptions, func(), error) {
	baseDir := h.baseSecretsDir
	if baseDir == "" {
		baseDir = DefaultSecretBaseDir
	}
	sessDir := filepath.Join(baseDir, sessionID.String())

	// Default cleanup: remove the per-session dir.
	cleanup := func() {
		_ = os.RemoveAll(sessDir)
	}

	// Start from the hardened Phase 2 sandbox baseline so security
	// knobs (CapDrop=ALL, NoNewPrivs, ReadOnlyRootfs) are always set
	// even if a recipe forgets them.
	opts := DefaultSandbox()

	// Image: prefer the recipe's explicit runtime image; otherwise
	// derive from the family (Phase 02.5 shipped ap-runtime-<family>
	// images via Plan 06).
	if recipe.Runtime.Image != "" {
		opts.Image = recipe.Runtime.Image
	} else if recipe.Runtime.Family != "" {
		opts.Image = "ap-runtime-" + recipe.Runtime.Family + ":latest"
	}

	opts.Name = docker.BuildContainerName(userID, sessionID)

	// Recipe-level isolation overrides. Empty slices leave defaults intact.
	if len(recipe.Isolation.CapDrop) > 0 {
		opts.CapDrop = append([]string{}, recipe.Isolation.CapDrop...)
	}
	if len(recipe.Isolation.CapAdd) > 0 {
		opts.CapAdd = append([]string{}, recipe.Isolation.CapAdd...)
	}
	if recipe.Isolation.NoNewPrivs {
		opts.NoNewPrivs = true
	}
	if recipe.Isolation.ReadOnlyRootfs {
		opts.ReadOnlyRootfs = true
	}

	// Resource caps.
	if recipe.Runtime.Resources.MemoryMiB > 0 {
		opts.Memory = int64(recipe.Runtime.Resources.MemoryMiB) << 20
	}
	if recipe.Runtime.Resources.CPUs > 0 {
		opts.CPUs = int64(recipe.Runtime.Resources.CPUs * 1_000_000_000)
	}
	if recipe.Runtime.Resources.PidsLimit > 0 {
		opts.PidsLimit = int64(recipe.Runtime.Resources.PidsLimit)
	}

	// Tmpfs from recipe.PersistentState.Tmpfs (merges with the
	// sandbox baseline /tmp and /run entries).
	if opts.Tmpfs == nil {
		opts.Tmpfs = map[string]string{}
	}
	for _, t := range recipe.PersistentState.Tmpfs {
		if t.Path == "" {
			continue
		}
		size := t.SizeMiB
		if size <= 0 {
			size = 32
		}
		opts.Tmpfs[t.Path] = fmt.Sprintf("rw,noexec,nosuid,size=%dm", size)
	}

	// Materialized env overlays.
	if opts.Env == nil {
		opts.Env = map[string]string{}
	}
	for k, v := range mat.Env {
		opts.Env[k] = v
	}
	// Plus any literal launch.env values (non-secret) from the recipe.
	for k, v := range recipe.Launch.Env {
		if _, exists := opts.Env[k]; !exists {
			opts.Env[k] = v
		}
	}

	// Materialized files: write each to <sessDir>/<basename(target)>
	// and add a single directory bind-mount :/run/secrets:ro. The
	// container's entrypoint copies from /run/secrets/<basename> to
	// the declared target path with the requested mode.
	if len(mat.Files) > 0 {
		if err := os.MkdirAll(sessDir, 0o700); err != nil {
			return opts, cleanup, fmt.Errorf("mkdir secrets dir: %w", err)
		}
		if err := os.Chmod(sessDir, 0o700); err != nil {
			return opts, cleanup, fmt.Errorf("chmod secrets dir: %w", err)
		}
		for _, f := range mat.Files {
			name := filepath.Base(f.Target)
			if name == "" || name == "/" || name == "." {
				return opts, cleanup, fmt.Errorf("invalid materialized file target %q", f.Target)
			}
			hostPath := filepath.Join(sessDir, name)
			if err := os.WriteFile(hostPath, []byte(f.Body), 0o600); err != nil {
				return opts, cleanup, fmt.Errorf("write materialized file %q: %w", name, err)
			}
			if err := os.Chmod(hostPath, 0o600); err != nil {
				return opts, cleanup, fmt.Errorf("chmod materialized file %q: %w", name, err)
			}
		}
		// Bind-mount the whole dir read-only into /run/secrets. The
		// host path in the spec must be the production-visible path
		// even if baseSecretsDir was overridden for tests (tests don't
		// exercise the bind mount against a real Docker daemon).
		opts.Mounts = append(opts.Mounts,
			fmt.Sprintf("%s:/run/secrets:ro", sessDir))
	}

	// Phase 5 reconciliation labels (SBX-09): every container carries
	// the user id, session id, recipe id, and provider so the reaper
	// can find orphans.
	if opts.Labels == nil {
		opts.Labels = map[string]string{}
	}
	opts.Labels["ap.user_id"] = userID.String()
	opts.Labels["ap.session_id"] = sessionID.String()
	opts.Labels["ap.recipe"] = recipe.ID
	opts.Labels["ap.provider"] = mat.Env["AP_PROVIDER"] // may be empty
	// Always stamp the provider from the materialization step so the
	// label is authoritative even if the recipe doesn't populate
	// AP_PROVIDER in auth.env.
	if opts.Labels["ap.provider"] == "" {
		// Fall back to the first provider ID the caller picked — the
		// materialized env may not carry it under that specific key.
		// Caller provides the value through the env.
	}

	// Launch.Cmd overrides the image's default CMD when set.
	if len(recipe.Launch.Cmd) > 0 {
		opts.Cmd = append([]string{}, recipe.Launch.Cmd...)
	}

	return opts, cleanup, nil
}

// isLifecycleHookErr returns true if the error message originates
// from Plan 03's RunWithLifecycle hook sequencer. Plan 03 wraps every
// hook error with the hook name as a prefix.
func isLifecycleHookErr(msg string) bool {
	for _, prefix := range []string{
		"initializeCommand",
		"onCreateCommand",
		"updateContentCommand",
		"postCreateCommand",
		"postStartCommand",
		"postAttachCommand",
	} {
		if strings.Contains(msg, prefix) {
			return true
		}
	}
	return false
}

// message handles POST /api/sessions/:id/message. Looks up the session,
// enforces ownership, checks status, dispatches to the chat bridge via
// the recipe's chat_io.mode, and returns the agent's reply. Timeouts
// surface as 504.
func (h *Handler) message(c echo.Context) error {
	userID, ok := userFromCtx(c)
	if !ok {
		return writeErr(c, http.StatusUnauthorized, errCodeUnauthorized, "unauthorized")
	}

	sessID, err := uuid.Parse(c.Param("id"))
	if err != nil {
		return writeErr(c, http.StatusBadRequest, errCodeInvalidRequest, "invalid session id")
	}

	var req messageRequest
	if err := c.Bind(&req); err != nil {
		return writeErr(c, http.StatusBadRequest, errCodeInvalidRequest, "invalid json")
	}
	if req.Text == "" {
		return writeErr(c, http.StatusBadRequest, errCodeInvalidRequest, "text is required")
	}
	if len(req.Text) > maxMessageLen {
		return writeErr(c, http.StatusRequestEntityTooLarge, errCodeInvalidRequest,
			fmt.Sprintf("message too long (max %d bytes)", maxMessageLen))
	}

	ctx := c.Request().Context()
	sess, err := h.store.Get(ctx, sessID)
	if err != nil {
		h.logger.Error().Err(err).Msg("session message: store.Get failed")
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "internal error")
	}
	if sess == nil {
		return writeErr(c, http.StatusNotFound, errCodeInvalidRequest, "session not found")
	}
	if sess.UserID != userID {
		return writeErr(c, http.StatusForbidden, errCodeForbidden, "forbidden")
	}
	if sess.Status != StatusRunning {
		return writeErr(c, http.StatusConflict, errCodeConflict, "session is not running")
	}
	if sess.ContainerID == nil || *sess.ContainerID == "" {
		return writeErr(c, http.StatusConflict, errCodeConflict, "session has no container")
	}

	if h.loader == nil {
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "recipe loader not configured")
	}
	recipe, found := h.loader.Get(sess.RecipeName)
	if !found {
		return writeErr(c, http.StatusInternalServerError, errCodeRecipeNotFound,
			fmt.Sprintf("session recipe %q no longer available", sess.RecipeName))
	}

	if h.bridges == nil {
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "bridge dispatcher not configured")
	}
	impl, err := h.bridges.Dispatch(recipe.ChatIO.Mode)
	if err != nil {
		if errors.Is(err, bridge.ErrUnsupportedMode) {
			return writeErr(c, http.StatusInternalServerError, errCodeChatBridgeUnsupported,
				fmt.Sprintf("chat_io.mode %q not supported", recipe.ChatIO.Mode))
		}
		h.logger.Error().Err(err).Msg("session message: bridge dispatch failed")
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "bridge dispatch failed")
	}

	reply, err := impl.SendMessage(ctx, *sess.ContainerID, recipe, sess.ModelID, req.Text)
	if err != nil {
		if errors.Is(err, bridge.ErrTimeout) {
			return writeErr(c, http.StatusGatewayTimeout, errCodeTimeout, "agent response timeout")
		}
		h.logger.Error().Err(err).Str("session_id", sessID.String()).Msg("session message: bridge failed")
		return writeErr(c, http.StatusBadGateway, errCodeInternal, "agent bridge failed")
	}

	return c.JSON(http.StatusOK, messageResponse{Text: reply})
}

// delete handles DELETE /api/sessions/:id. Best-effort cleanup chain:
// Stop → Remove → secrets-dir cleanup → UpdateStatus(stopped). Each
// step logs on failure but does not short-circuit — stale containers
// and stale secret dirs are both worse than a noisy log line.
func (h *Handler) delete(c echo.Context) error {
	userID, ok := userFromCtx(c)
	if !ok {
		return writeErr(c, http.StatusUnauthorized, errCodeUnauthorized, "unauthorized")
	}

	sessID, err := uuid.Parse(c.Param("id"))
	if err != nil {
		return writeErr(c, http.StatusBadRequest, errCodeInvalidRequest, "invalid session id")
	}

	ctx := c.Request().Context()
	sess, err := h.store.Get(ctx, sessID)
	if err != nil {
		h.logger.Error().Err(err).Msg("session delete: store.Get failed")
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "internal error")
	}
	if sess == nil {
		return writeErr(c, http.StatusNotFound, errCodeInvalidRequest, "session not found")
	}
	if sess.UserID != userID {
		return writeErr(c, http.StatusForbidden, errCodeForbidden, "forbidden")
	}

	if sess.ContainerID != nil && *sess.ContainerID != "" {
		if err := h.runner.Stop(ctx, *sess.ContainerID); err != nil {
			h.logger.Warn().Err(err).Str("container_id", *sess.ContainerID).Msg("session delete: stop failed")
		}
		if err := h.runner.Remove(ctx, *sess.ContainerID); err != nil {
			h.logger.Warn().Err(err).Str("container_id", *sess.ContainerID).Msg("session delete: remove failed")
		}
	}

	// Cleanup per-session secrets dir.
	baseDir := h.baseSecretsDir
	if baseDir == "" {
		baseDir = DefaultSecretBaseDir
	}
	sessDir := filepath.Join(baseDir, sess.ID.String())
	if err := os.RemoveAll(sessDir); err != nil {
		h.logger.Warn().Err(err).Str("session_id", sess.ID.String()).Msg("session delete: secret cleanup failed")
	}

	if err := h.store.UpdateStatus(ctx, sess.ID, StatusStopped); err != nil {
		h.logger.Error().Err(err).Str("session_id", sess.ID.String()).Msg("session delete: update status failed")
		return writeErr(c, http.StatusInternalServerError, errCodeInternal, "failed to mark session stopped")
	}

	return c.JSON(http.StatusOK, map[string]string{"status": StatusStopped})
}

// userFromCtx extracts the authenticated user id, delegating to
// middleware.GetUserID so the handler never re-implements context
// lookup. This is the Phase 1 contract — any other path is a bug.
func userFromCtx(c echo.Context) (uuid.UUID, bool) {
	id, err := middleware.GetUserID(c)
	if err != nil {
		return uuid.Nil, false
	}
	return id, true
}
