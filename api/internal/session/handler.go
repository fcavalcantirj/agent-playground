package session

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
	"github.com/rs/zerolog"

	"github.com/agentplayground/api/internal/middleware"
	"github.com/agentplayground/api/internal/recipes"
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

// SecretProvisioner is the subset of *SecretWriter the handler needs.
// Matches the exact shape of SecretWriter so production wiring passes
// *SecretWriter directly and tests pass a mock.
type SecretProvisioner interface {
	Provision(sessionID uuid.UUID, required []string) (string, error)
	Cleanup(sessionID uuid.UUID) error
	BindMountSpec(sessionID uuid.UUID) string
	WriteAuthFile(sessionID uuid.UUID, filename, containerPath, content string) (string, error)
}

// ContainerRunner is the subset of *docker.Runner the handler needs for
// the create / delete paths. The bridge separately uses RunnerExec for
// chat dispatch. Both interfaces are satisfied by *docker.Runner in
// production, by the same mock in tests.
type ContainerRunner interface {
	Run(ctx context.Context, opts docker.RunOptions) (string, error)
	Stop(ctx context.Context, containerID string) error
	Remove(ctx context.Context, containerID string) error
}

// Compile-time checks: the production *Store / *SecretWriter satisfy
// the handler-side interfaces. If signatures drift, the build fails
// here instead of at runtime.
var (
	_ SessionStore      = (*Store)(nil)
	_ SecretProvisioner = (*SecretWriter)(nil)
)

// Handler serves POST /api/sessions, POST /api/sessions/:id/message,
// and DELETE /api/sessions/:id. Every route runs behind the existing
// Phase 1 auth middleware; Register mounts them on an already-authed
// echo.Group so the handler itself is agnostic to the auth mechanism.
type Handler struct {
	store   SessionStore
	runner  ContainerRunner
	secrets SecretProvisioner
	source  SecretSource
	bridge  *Bridge
	logger  zerolog.Logger
}

// NewHandler constructs a Handler. All dependencies are required;
// passing nil for any of them will surface as a nil-pointer panic at
// the first request, which is the intended "fail loud in dev" posture.
// source is used only when a recipe declares AgentAuthFiles that need
// the raw BYOK key inlined into a per-session config file.
func NewHandler(store SessionStore, runner ContainerRunner, secrets SecretProvisioner, source SecretSource, bridge *Bridge, logger zerolog.Logger) *Handler {
	return &Handler{
		store:   store,
		runner:  runner,
		secrets: secrets,
		source:  source,
		bridge:  bridge,
		logger:  logger,
	}
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

type createRequest struct {
	Recipe        string `json:"recipe"`
	ModelProvider string `json:"model_provider"`
	ModelID       string `json:"model_id"`
}

type createResponse struct {
	ID          string `json:"id"`
	Status      string `json:"status"`
	ContainerID string `json:"container_id,omitempty"`
}

type messageRequest struct {
	Text string `json:"text"`
}

type messageResponse struct {
	Text string `json:"text"`
}

// ----- handlers -----

// create handles POST /api/sessions. Flow:
//  1. Auth: read user from ctx (middleware.GetUserID).
//  2. Validate recipe + provider via recipes.Get.
//  3. Store.Create — returns 409 on ErrConflictActive.
//  4. Provision secrets — returns 503 on ErrSecretMissing.
//  5. Compose RunOptions: DefaultSandbox + recipe overrides + bind-mount
//     + BuildContainerName + recipe image + env.
//  6. runner.Run → UpdateContainer(StatusRunning).
//  7. Return 201 with the session id.
func (h *Handler) create(c echo.Context) error {
	userID, ok := userFromCtx(c)
	if !ok {
		return c.JSON(http.StatusUnauthorized, errorBody("unauthorized"))
	}

	var req createRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, errorBody("invalid json"))
	}
	if req.Recipe == "" || req.ModelProvider == "" || req.ModelID == "" {
		return c.JSON(http.StatusBadRequest, errorBody("recipe, model_provider, and model_id are required"))
	}

	recipe := recipes.Get(req.Recipe)
	if recipe == nil {
		return c.JSON(http.StatusBadRequest, errorBody(fmt.Sprintf("unknown recipe: %s", req.Recipe)))
	}
	// Validate provider is supported by this recipe.
	providerOK := false
	for _, p := range recipe.SupportedProviders {
		if p == req.ModelProvider {
			providerOK = true
			break
		}
	}
	if !providerOK {
		return c.JSON(http.StatusBadRequest, errorBody(fmt.Sprintf("recipe %s does not support provider %s", req.Recipe, req.ModelProvider)))
	}

	ctx := c.Request().Context()

	sess, err := h.store.Create(ctx, userID, recipe.Name, req.ModelProvider, req.ModelID)
	if err != nil {
		if errors.Is(err, ErrConflictActive) {
			return c.JSON(http.StatusConflict, errorBody("user already has an active session"))
		}
		h.logger.Error().Err(err).Msg("session create: store failed")
		return c.JSON(http.StatusInternalServerError, errorBody("internal error"))
	}

	if _, err := h.secrets.Provision(sess.ID, recipe.RequiredSecrets); err != nil {
		// Best-effort: clean the partial dir so the next attempt starts fresh.
		_ = h.secrets.Cleanup(sess.ID)
		_ = h.store.UpdateStatus(ctx, sess.ID, StatusFailed)
		if errors.Is(err, ErrSecretMissing) {
			return c.JSON(http.StatusServiceUnavailable, errorBody("required secret unavailable in this deploy"))
		}
		h.logger.Error().Err(err).Msg("session create: secret provision failed")
		return c.JSON(http.StatusInternalServerError, errorBody("secret provision failed"))
	}

	// Compose RunOptions from DefaultSandbox baseline.
	opts := DefaultSandbox()
	opts.Image = recipe.Image
	opts.Name = docker.BuildContainerName(userID, sess.ID)
	opts.Mounts = append(opts.Mounts, h.secrets.BindMountSpec(sess.ID))

	// Recipe-specific auth file injection (e.g. picoclaw's .security.yml).
	// When the agent binary doesn't honor env vars or /run/secrets, the
	// recipe declares AgentAuthFiles and we render + bind-mount each one.
	if len(recipe.AgentAuthFiles) > 0 {
		key, keyErr := h.source.Get("anthropic_key")
		if keyErr != nil {
			_ = h.secrets.Cleanup(sess.ID)
			_ = h.store.UpdateStatus(ctx, sess.ID, StatusFailed)
			h.logger.Error().Err(keyErr).Msg("session create: anthropic_key unavailable for auth file render")
			return c.JSON(http.StatusServiceUnavailable, errorBody("BYOK key unavailable"))
		}
		for _, af := range recipe.AgentAuthFiles {
			spec, afErr := h.secrets.WriteAuthFile(sess.ID, af.HostFilename, af.ContainerPath, af.Render(key))
			if afErr != nil {
				_ = h.secrets.Cleanup(sess.ID)
				_ = h.store.UpdateStatus(ctx, sess.ID, StatusFailed)
				h.logger.Error().Err(afErr).Msg("session create: auth file write failed")
				return c.JSON(http.StatusInternalServerError, errorBody("auth file provisioning failed"))
			}
			opts.Mounts = append(opts.Mounts, spec)
		}
	}
	if opts.Env == nil {
		opts.Env = make(map[string]string, len(recipe.EnvOverrides)+1)
	}
	for k, v := range recipe.EnvOverrides {
		opts.Env[k] = v
	}
	// For FIFO-mode recipes, tell ap-base's entrypoint.sh which agent process
	// to launch in the tmux chat window. The entrypoint interpolates this into
	// `bash -c '$AP_AGENT_CMD < $FIFO_IN > $FIFO_OUT'`, so join with spaces.
	// ExecMode recipes (Hermes) leave AP_AGENT_CMD empty — POST /messages does
	// one `docker exec` per message instead.
	if recipe.ChatIO.Mode == recipes.ChatIOFIFO && len(recipe.ChatIO.LaunchCmd) > 0 {
		launch := append([]string{}, recipe.ChatIO.LaunchCmd...)
		if recipe.ModelFlag != "" {
			launch = append(launch, recipe.ModelFlag, req.ModelID)
		}
		opts.Env["AP_AGENT_CMD"] = strings.Join(launch, " ")
	}
	// Resource overrides only touch Memory / CPUs / PidsLimit — security knobs
	// stay locked (T-02-02 mitigation).
	if recipe.ResourceOverrides.Memory > 0 {
		opts.Memory = recipe.ResourceOverrides.Memory
	}
	if recipe.ResourceOverrides.CPUs > 0 {
		opts.CPUs = recipe.ResourceOverrides.CPUs
	}
	if recipe.ResourceOverrides.PidsLimit > 0 {
		opts.PidsLimit = recipe.ResourceOverrides.PidsLimit
	}

	containerID, err := h.runner.Run(ctx, opts)
	if err != nil {
		_ = h.secrets.Cleanup(sess.ID)
		_ = h.store.UpdateStatus(ctx, sess.ID, StatusFailed)
		h.logger.Error().Err(err).Str("session_id", sess.ID.String()).Msg("session create: runner.Run failed")
		return c.JSON(http.StatusInternalServerError, errorBody("failed to start container"))
	}

	if err := h.store.UpdateContainer(ctx, sess.ID, containerID, StatusRunning); err != nil {
		// The container is up but we failed to record it — best-effort stop.
		_ = h.runner.Stop(ctx, containerID)
		_ = h.runner.Remove(ctx, containerID)
		_ = h.secrets.Cleanup(sess.ID)
		h.logger.Error().Err(err).Str("session_id", sess.ID.String()).Msg("session create: update container failed")
		return c.JSON(http.StatusInternalServerError, errorBody("failed to persist session"))
	}

	return c.JSON(http.StatusCreated, createResponse{
		ID:          sess.ID.String(),
		Status:      StatusRunning,
		ContainerID: containerID,
	})
}

// message handles POST /api/sessions/:id/message. Looks up the session,
// enforces ownership, checks status, dispatches to the chat bridge,
// and returns the agent's reply. Timeouts surface as 504.
func (h *Handler) message(c echo.Context) error {
	userID, ok := userFromCtx(c)
	if !ok {
		return c.JSON(http.StatusUnauthorized, errorBody("unauthorized"))
	}

	sessID, err := uuid.Parse(c.Param("id"))
	if err != nil {
		return c.JSON(http.StatusBadRequest, errorBody("invalid session id"))
	}

	var req messageRequest
	if err := c.Bind(&req); err != nil {
		return c.JSON(http.StatusBadRequest, errorBody("invalid json"))
	}
	if req.Text == "" {
		return c.JSON(http.StatusBadRequest, errorBody("text is required"))
	}
	if len(req.Text) > maxMessageLen {
		return c.JSON(http.StatusRequestEntityTooLarge, errorBody(fmt.Sprintf("message too long (max %d bytes)", maxMessageLen)))
	}

	ctx := c.Request().Context()
	sess, err := h.store.Get(ctx, sessID)
	if err != nil {
		h.logger.Error().Err(err).Msg("session message: store.Get failed")
		return c.JSON(http.StatusInternalServerError, errorBody("internal error"))
	}
	if sess == nil {
		return c.JSON(http.StatusNotFound, errorBody("session not found"))
	}
	if sess.UserID != userID {
		return c.JSON(http.StatusForbidden, errorBody("forbidden"))
	}
	if sess.Status != StatusRunning {
		return c.JSON(http.StatusConflict, errorBody("session is not running"))
	}
	if sess.ContainerID == nil || *sess.ContainerID == "" {
		return c.JSON(http.StatusConflict, errorBody("session has no container"))
	}

	recipe := recipes.Get(sess.RecipeName)
	if recipe == nil {
		return c.JSON(http.StatusInternalServerError, errorBody("session recipe no longer available"))
	}

	reply, err := h.bridge.SendMessage(ctx, *sess.ContainerID, recipe, sess.ModelID, req.Text)
	if err != nil {
		if errors.Is(err, ErrTimeout) {
			return c.JSON(http.StatusGatewayTimeout, errorBody("agent response timeout"))
		}
		h.logger.Error().Err(err).Str("session_id", sessID.String()).Msg("session message: bridge failed")
		return c.JSON(http.StatusBadGateway, errorBody("agent bridge failed"))
	}

	return c.JSON(http.StatusOK, messageResponse{Text: reply})
}

// delete handles DELETE /api/sessions/:id. Best-effort cleanup chain:
// Stop → Remove → secrets.Cleanup → UpdateStatus(stopped). Each step
// logs on failure but does not short-circuit — stale containers and
// stale secret dirs are both worse than a noisy log line.
func (h *Handler) delete(c echo.Context) error {
	userID, ok := userFromCtx(c)
	if !ok {
		return c.JSON(http.StatusUnauthorized, errorBody("unauthorized"))
	}

	sessID, err := uuid.Parse(c.Param("id"))
	if err != nil {
		return c.JSON(http.StatusBadRequest, errorBody("invalid session id"))
	}

	ctx := c.Request().Context()
	sess, err := h.store.Get(ctx, sessID)
	if err != nil {
		h.logger.Error().Err(err).Msg("session delete: store.Get failed")
		return c.JSON(http.StatusInternalServerError, errorBody("internal error"))
	}
	if sess == nil {
		return c.JSON(http.StatusNotFound, errorBody("session not found"))
	}
	if sess.UserID != userID {
		return c.JSON(http.StatusForbidden, errorBody("forbidden"))
	}

	if sess.ContainerID != nil && *sess.ContainerID != "" {
		if err := h.runner.Stop(ctx, *sess.ContainerID); err != nil {
			h.logger.Warn().Err(err).Str("container_id", *sess.ContainerID).Msg("session delete: stop failed")
		}
		if err := h.runner.Remove(ctx, *sess.ContainerID); err != nil {
			h.logger.Warn().Err(err).Str("container_id", *sess.ContainerID).Msg("session delete: remove failed")
		}
	}

	if err := h.secrets.Cleanup(sess.ID); err != nil {
		h.logger.Warn().Err(err).Str("session_id", sess.ID.String()).Msg("session delete: secret cleanup failed")
	}

	if err := h.store.UpdateStatus(ctx, sess.ID, StatusStopped); err != nil {
		h.logger.Error().Err(err).Str("session_id", sess.ID.String()).Msg("session delete: update status failed")
		return c.JSON(http.StatusInternalServerError, errorBody("failed to mark session stopped"))
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

// errorBody is the uniform JSON shape for error responses, matching
// internal/handler/devauth.go's `{"error": "..."}` envelope.
func errorBody(msg string) map[string]string {
	return map[string]string{"error": msg}
}
