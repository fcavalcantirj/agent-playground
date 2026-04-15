package session_test

// handler_test.go — Phase 02.5 Plan 09 rewrite.
//
// The Phase 2 test suite constructed the handler against hardcoded
// legacy recipes (picoclaw / hermes). Plan 09 deletes that catalog
// and swaps the handler onto the YAML-backed Loader + Materialize +
// RunWithLifecycle + BridgeRegistry path. Every test below uses
// fake implementations of those collaborators so the suite stays
// pure-unit (no Docker, no Postgres, no filesystem beyond t.TempDir()).

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/internal/recipes"
	"github.com/agentplayground/api/internal/session"
	"github.com/agentplayground/api/internal/session/bridge"
	"github.com/agentplayground/api/pkg/docker"
)

// ---------- fakes ----------

type mockStore struct {
	mu sync.Mutex

	createFn func(ctx context.Context, userID uuid.UUID, recipe, provider, modelID string) (*session.Session, error)
	getFn    func(ctx context.Context, id uuid.UUID) (*session.Session, error)

	updateStatusCalls    []updateStatusCall
	updateContainerCalls []updateContainerCall
}

type updateStatusCall struct {
	id     uuid.UUID
	status string
}

type updateContainerCall struct {
	id          uuid.UUID
	containerID string
	status      string
}

func (m *mockStore) Create(ctx context.Context, userID uuid.UUID, recipe, provider, modelID string) (*session.Session, error) {
	if m.createFn != nil {
		return m.createFn(ctx, userID, recipe, provider, modelID)
	}
	return &session.Session{
		ID:            uuid.New(),
		UserID:        userID,
		RecipeName:    recipe,
		ModelProvider: provider,
		ModelID:       modelID,
		Status:        session.StatusPending,
	}, nil
}

func (m *mockStore) Get(ctx context.Context, id uuid.UUID) (*session.Session, error) {
	if m.getFn != nil {
		return m.getFn(ctx, id)
	}
	return nil, nil
}

func (m *mockStore) UpdateStatus(ctx context.Context, id uuid.UUID, status string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.updateStatusCalls = append(m.updateStatusCalls, updateStatusCall{id: id, status: status})
	return nil
}

func (m *mockStore) UpdateContainer(ctx context.Context, id uuid.UUID, containerID, status string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.updateContainerCalls = append(m.updateContainerCalls, updateContainerCall{id: id, containerID: containerID, status: status})
	return nil
}

// mockContainerRunner satisfies session.ContainerRunner. It records
// RunWithLifecycle / Stop / Remove calls and returns canned results.
type mockContainerRunner struct {
	mu sync.Mutex

	runFn         func(ctx context.Context, opts docker.RunOptions) (string, error)
	runLifecycle  func(ctx context.Context, recipe *recipes.Recipe, opts docker.RunOptions) (*docker.LifecycleSession, error)
	stopFn        func(ctx context.Context, id string) error
	removeFn      func(ctx context.Context, id string) error
	stopCalls     int
	removeCalls   int
	lifecycleHits int
	lastRunOpts   docker.RunOptions
	lastRecipe    *recipes.Recipe
}

func (m *mockContainerRunner) Run(ctx context.Context, opts docker.RunOptions) (string, error) {
	m.mu.Lock()
	m.lastRunOpts = opts
	m.mu.Unlock()
	if m.runFn != nil {
		return m.runFn(ctx, opts)
	}
	return "fakecontainerid0000", nil
}

func (m *mockContainerRunner) RunWithLifecycle(ctx context.Context, recipe *recipes.Recipe, opts docker.RunOptions) (*docker.LifecycleSession, error) {
	m.mu.Lock()
	m.lifecycleHits++
	m.lastRunOpts = opts
	m.lastRecipe = recipe
	m.mu.Unlock()
	if m.runLifecycle != nil {
		return m.runLifecycle(ctx, recipe, opts)
	}
	ch := make(chan struct{})
	close(ch)
	return &docker.LifecycleSession{
		ContainerID: "lc-fake-container-id",
		Recipe:      recipe,
		ReadyCh:     ch,
	}, nil
}

func (m *mockContainerRunner) Stop(ctx context.Context, id string) error {
	m.mu.Lock()
	m.stopCalls++
	m.mu.Unlock()
	if m.stopFn != nil {
		return m.stopFn(ctx, id)
	}
	return nil
}

func (m *mockContainerRunner) Remove(ctx context.Context, id string) error {
	m.mu.Lock()
	m.removeCalls++
	m.mu.Unlock()
	if m.removeFn != nil {
		return m.removeFn(ctx, id)
	}
	return nil
}

// fakeLoader is the in-memory RecipeLoader the handler tests use.
type fakeLoader struct {
	byID map[string]*recipes.Recipe
}

func (f *fakeLoader) Get(id string) (*recipes.Recipe, bool) {
	r, ok := f.byID[id]
	return r, ok
}

// fakeSecretSource returns preconfigured secret values keyed by
// normalized name. Any `secret:<name>` ref with a matching key
// resolves; literal refs pass through unchanged.
type fakeSecretSource struct {
	values  map[string]string
	missing bool
}

func (f *fakeSecretSource) Get(name string) (string, error) {
	if f.missing {
		return "", session.ErrSecretMissing
	}
	if v, ok := f.values[name]; ok {
		return v, nil
	}
	return "", session.ErrSecretMissing
}

func (f *fakeSecretSource) Resolve(ref string) (string, error) {
	key, ok := strings.CutPrefix(ref, "secret:")
	if !ok {
		return ref, nil
	}
	return f.Get(key)
}

// fakeTemplates is a no-op TemplateRenderer: returns the empty
// string for any render request. The handler tests don't exercise
// auth.files materialization (the plan's acceptance criteria only
// require secret-missing + happy-path coverage), so an empty
// implementation is sufficient.
type fakeTemplates struct{}

func (fakeTemplates) Render(ctx context.Context, recipeID, name string, data any) (string, error) {
	return "", nil
}

// fakeBridges dispatches recipe.ChatIO.Mode to a captured fake
// ChatBridge. The default bridge returns a canned reply; tests can
// override on a per-case basis.
type fakeBridges struct {
	sendFn  func(ctx context.Context, containerID string, recipe *recipes.Recipe, modelID, text string) (string, error)
	dispErr error
}

type fakeBridge struct {
	parent *fakeBridges
}

func (b *fakeBridge) SendMessage(ctx context.Context, containerID string, recipe *recipes.Recipe, modelID, text string) (string, error) {
	if b.parent.sendFn != nil {
		return b.parent.sendFn(ctx, containerID, recipe, modelID, text)
	}
	return "ack: " + text, nil
}

func (f *fakeBridges) Dispatch(mode string) (bridge.ChatBridge, error) {
	if f.dispErr != nil {
		return nil, f.dispErr
	}
	return &fakeBridge{parent: f}, nil
}

// ---------- recipe fixtures ----------

// testAiderRecipe returns a two-provider (anthropic + openrouter)
// recipe used by most create-session tests. Matches the shape the
// Plan 09 plan spec calls out.
func testAiderRecipe() *recipes.Recipe {
	return &recipes.Recipe{
		ID:      "aider",
		Name:    "Aider",
		License: "Apache-2.0",
		Runtime: recipes.RecipeRuntime{
			Family: "python",
			Image:  "ap-runtime-python:test",
		},
		Install: recipes.RecipeInstall{Type: "pip", Package: "aider-chat"},
		Launch:  recipes.RecipeLaunch{Cmd: []string{"aider"}},
		ChatIO:  recipes.RecipeChatIO{Mode: "exec_per_message"},
		Auth: recipes.RecipeAuth{
			Mechanism: "env_var",
			Env: map[string]string{
				"ANTHROPIC_API_KEY":  "secret:anthropic-api-key",
				"OPENROUTER_API_KEY": "secret:openrouter-api-key",
			},
			SecretsSchema: []recipes.RecipeSecretDecl{
				{Name: "anthropic-api-key"},
				{Name: "openrouter-api-key"},
			},
		},
		Providers: []recipes.RecipeProvider{
			{ID: "anthropic"},
			{ID: "openrouter"},
		},
		Models: []recipes.RecipeModel{
			{ID: "claude-haiku-test", Provider: "anthropic"},
			{ID: "openrouter/auto", Provider: "openrouter"},
		},
		Isolation: recipes.RecipeIsolation{Tier: "strict"},
	}
}

// testPicoclawRecipe returns a single-provider recipe used by the
// "provider default" tests. Picoclaw only supports anthropic in v0.1.
func testPicoclawRecipe() *recipes.Recipe {
	return &recipes.Recipe{
		ID:      "picoclaw",
		Name:    "PicoClaw",
		License: "MIT",
		Runtime: recipes.RecipeRuntime{Family: "node", Image: "ap-runtime-node:test"},
		Install: recipes.RecipeInstall{Type: "npm", Package: "picoclaw"},
		Launch:  recipes.RecipeLaunch{Cmd: []string{"picoclaw"}},
		ChatIO:  recipes.RecipeChatIO{Mode: "fifo"},
		Auth: recipes.RecipeAuth{
			Mechanism: "env_var",
			Env: map[string]string{
				"ANTHROPIC_API_KEY": "secret:anthropic-api-key",
			},
			SecretsSchema: []recipes.RecipeSecretDecl{
				{Name: "anthropic-api-key"},
			},
		},
		Providers: []recipes.RecipeProvider{
			{ID: "anthropic"},
		},
		Models: []recipes.RecipeModel{
			{ID: "claude-sonnet-test", Provider: "anthropic"},
		},
		Isolation: recipes.RecipeIsolation{Tier: "standard"},
	}
}

// ---------- helpers ----------

type rig struct {
	e       *echo.Echo
	store   *mockStore
	runner  *mockContainerRunner
	loader  *fakeLoader
	secrets *fakeSecretSource
	bridges *fakeBridges
	userID  uuid.UUID
}

func newRig(t *testing.T, withRecipes ...*recipes.Recipe) *rig {
	t.Helper()
	store := &mockStore{}
	runner := &mockContainerRunner{}
	byID := map[string]*recipes.Recipe{}
	for _, r := range withRecipes {
		byID[r.ID] = r
	}
	loader := &fakeLoader{byID: byID}
	secrets := &fakeSecretSource{
		values: map[string]string{
			"anthropic-api-key":  "sk-ant-test",
			"openrouter-api-key": "sk-or-test",
		},
	}
	bridges := &fakeBridges{}
	tempDir := t.TempDir()

	h := session.NewHandler(
		store,
		runner,
		loader,
		secrets,
		fakeTemplates{},
		bridges,
		zerolog.Nop(),
		session.WithBaseSecretsDir(tempDir),
	)

	e := echo.New()
	e.HideBanner = true
	userID := uuid.New()
	authed := e.Group("/api", func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			authHdr := c.Request().Header.Get("X-Test-Auth")
			if authHdr == "" {
				return c.JSON(http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			}
			uid, err := uuid.Parse(authHdr)
			if err != nil {
				return c.JSON(http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			}
			c.Set("user_id", uid)
			return next(c)
		}
	})
	h.Register(authed)

	return &rig{e: e, store: store, runner: runner, loader: loader, secrets: secrets, bridges: bridges, userID: userID}
}

// newRigFixedUser mounts the handler behind middleware that always
// sets a specific user id (used for DELETE/message tests where the
// mock store row ownership must match).
func newRigFixedUser(t *testing.T, uid uuid.UUID, withRecipes ...*recipes.Recipe) *rig {
	t.Helper()
	store := &mockStore{}
	runner := &mockContainerRunner{}
	byID := map[string]*recipes.Recipe{}
	for _, r := range withRecipes {
		byID[r.ID] = r
	}
	loader := &fakeLoader{byID: byID}
	secrets := &fakeSecretSource{
		values: map[string]string{
			"anthropic-api-key":  "sk-ant-test",
			"openrouter-api-key": "sk-or-test",
		},
	}
	bridges := &fakeBridges{}
	tempDir := t.TempDir()

	h := session.NewHandler(
		store,
		runner,
		loader,
		secrets,
		fakeTemplates{},
		bridges,
		zerolog.Nop(),
		session.WithBaseSecretsDir(tempDir),
	)

	e := echo.New()
	authed := e.Group("/api", func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			c.Set("user_id", uid)
			return next(c)
		}
	})
	h.Register(authed)
	return &rig{e: e, store: store, runner: runner, loader: loader, secrets: secrets, bridges: bridges, userID: uid}
}

func doRequest(t *testing.T, e *echo.Echo, method, path, body string, userID uuid.UUID, auth bool) *httptest.ResponseRecorder {
	t.Helper()
	var r io.Reader
	if body != "" {
		r = strings.NewReader(body)
	}
	req := httptest.NewRequest(method, path, r)
	if body != "" {
		req.Header.Set(echo.HeaderContentType, "application/json")
	}
	if auth {
		req.Header.Set("X-Test-Auth", userID.String())
	}
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)
	return rec
}

func decodeErrorCode(t *testing.T, body []byte) string {
	t.Helper()
	var env map[string]any
	require.NoError(t, json.Unmarshal(body, &env), "body=%s", string(body))
	errObj, ok := env["error"].(map[string]any)
	if !ok {
		return ""
	}
	code, _ := errObj["code"].(string)
	return code
}

// ---------- tests ----------

func TestCreateSession_Success_Aider(t *testing.T) {
	rig := newRig(t, testAiderRecipe())

	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"aider","provider":"anthropic","model":"claude-haiku-test"}`,
		rig.userID, true)

	require.Equal(t, http.StatusCreated, rec.Code, "body=%s", rec.Body.String())

	var resp map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &resp))
	assert.NotEmpty(t, resp["id"])
	assert.Equal(t, "aider", resp["recipe"])
	assert.Equal(t, "anthropic", resp["provider"])
	assert.Equal(t, "claude-haiku-test", resp["model"])
	assert.Equal(t, "running", resp["status"])
	assert.NotEmpty(t, resp["container_id"])

	require.Equal(t, 1, rig.runner.lifecycleHits, "RunWithLifecycle must be called exactly once")
	require.GreaterOrEqual(t, len(rig.store.updateContainerCalls), 1)

	rig.runner.mu.Lock()
	opts := rig.runner.lastRunOpts
	rig.runner.mu.Unlock()
	assert.Equal(t, "ap-runtime-python:test", opts.Image)
	assert.Contains(t, opts.Env, "ANTHROPIC_API_KEY")
	assert.Equal(t, "sk-ant-test", opts.Env["ANTHROPIC_API_KEY"])
	// Phase 5 reconciliation labels.
	assert.Equal(t, rig.userID.String(), opts.Labels["ap.user_id"])
	assert.Equal(t, "aider", opts.Labels["ap.recipe"])
	assert.NotEmpty(t, opts.Labels["ap.session_id"])
}

func TestCreateSession_BackwardsCompat_ModelProviderAlias(t *testing.T) {
	rig := newRig(t, testAiderRecipe())

	// Phase 2 clients send model_provider / model_id — handler must
	// fold them onto the canonical provider / model before validating.
	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"aider","model_provider":"openrouter","model_id":"openrouter/auto"}`,
		rig.userID, true)

	require.Equal(t, http.StatusCreated, rec.Code, "body=%s", rec.Body.String())

	var resp map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &resp))
	assert.Equal(t, "openrouter", resp["provider"])
	assert.Equal(t, "openrouter/auto", resp["model"])
}

func TestCreateSession_ProviderRequired_MultiProvider(t *testing.T) {
	rig := newRig(t, testAiderRecipe())

	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"aider","model":"claude-haiku-test"}`,
		rig.userID, true)

	require.Equal(t, http.StatusBadRequest, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, "invalid_request", decodeErrorCode(t, rec.Body.Bytes()))
}

func TestCreateSession_ProviderDefaulted_SingleProvider(t *testing.T) {
	rig := newRig(t, testPicoclawRecipe())

	// Omitting provider on a single-provider recipe should default
	// and succeed. Omitting model should default to the sole model.
	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"picoclaw"}`,
		rig.userID, true)

	require.Equal(t, http.StatusCreated, rec.Code, "body=%s", rec.Body.String())

	var resp map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &resp))
	assert.Equal(t, "anthropic", resp["provider"])
	assert.Equal(t, "claude-sonnet-test", resp["model"])
}

func TestCreateSession_ProviderNotSupported(t *testing.T) {
	rig := newRig(t, testPicoclawRecipe())

	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"picoclaw","provider":"openai","model":"gpt-4o"}`,
		rig.userID, true)

	require.Equal(t, http.StatusBadRequest, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, "provider_not_supported", decodeErrorCode(t, rec.Body.Bytes()))
}

func TestCreateSession_ModelNotSupported(t *testing.T) {
	rig := newRig(t, testAiderRecipe())

	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"aider","provider":"anthropic","model":"claude-impossible"}`,
		rig.userID, true)

	require.Equal(t, http.StatusBadRequest, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, "model_not_supported", decodeErrorCode(t, rec.Body.Bytes()))
}

func TestCreateSession_ModelBoundToWrongProvider(t *testing.T) {
	rig := newRig(t, testAiderRecipe())

	// openrouter/auto belongs to the openrouter provider; asking for
	// it under anthropic must fail with model_not_supported.
	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"aider","provider":"anthropic","model":"openrouter/auto"}`,
		rig.userID, true)

	require.Equal(t, http.StatusBadRequest, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, "model_not_supported", decodeErrorCode(t, rec.Body.Bytes()))
}

func TestCreateSession_RecipeNotFound(t *testing.T) {
	rig := newRig(t, testAiderRecipe())

	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"nosuch","provider":"anthropic","model":"x"}`,
		rig.userID, true)

	require.Equal(t, http.StatusNotFound, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, "recipe_not_found", decodeErrorCode(t, rec.Body.Bytes()))
}

func TestCreateSession_SecretMissing(t *testing.T) {
	rig := newRig(t, testPicoclawRecipe())
	rig.secrets.values = map[string]string{} // drop all keys

	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"picoclaw"}`,
		rig.userID, true)

	require.Equal(t, http.StatusBadRequest, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, "secret_missing", decodeErrorCode(t, rec.Body.Bytes()))
}

func TestCreateSession_LifecycleHookFailed(t *testing.T) {
	rig := newRig(t, testPicoclawRecipe())
	rig.runner.runLifecycle = func(ctx context.Context, recipe *recipes.Recipe, opts docker.RunOptions) (*docker.LifecycleSession, error) {
		return nil, errors.New("postCreateCommand: exec [pip install ...]: exit 1")
	}

	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"picoclaw"}`,
		rig.userID, true)

	require.Equal(t, http.StatusInternalServerError, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, "lifecycle_hook_failed", decodeErrorCode(t, rec.Body.Bytes()))
}

func TestCreateSession_OneActive_Conflict(t *testing.T) {
	rig := newRig(t, testPicoclawRecipe())
	rig.store.createFn = func(ctx context.Context, userID uuid.UUID, recipe, provider, modelID string) (*session.Session, error) {
		return nil, session.ErrConflictActive
	}

	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"picoclaw"}`,
		rig.userID, true)

	require.Equal(t, http.StatusConflict, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, "conflict", decodeErrorCode(t, rec.Body.Bytes()))
}

func TestCreateSession_Unauthorized(t *testing.T) {
	rig := newRig(t, testAiderRecipe())

	rec := doRequest(t, rig.e, http.MethodPost, "/api/sessions",
		`{"recipe":"aider","provider":"anthropic","model":"claude-haiku-test"}`,
		rig.userID, false)

	assert.Equal(t, http.StatusUnauthorized, rec.Code)
}

func TestDeleteSession(t *testing.T) {
	sid := uuid.New()
	uid := uuid.New()
	cid := "fakecontainer"
	rig := newRigFixedUser(t, uid, testPicoclawRecipe())
	rig.store.getFn = func(ctx context.Context, id uuid.UUID) (*session.Session, error) {
		return &session.Session{
			ID:          sid,
			UserID:      uid,
			RecipeName:  "picoclaw",
			Status:      session.StatusRunning,
			ContainerID: &cid,
		}, nil
	}

	req := httptest.NewRequest(http.MethodDelete, "/api/sessions/"+sid.String(), nil)
	rec := httptest.NewRecorder()
	rig.e.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, 1, rig.runner.stopCalls)
	assert.Equal(t, 1, rig.runner.removeCalls)
	found := false
	for _, u := range rig.store.updateStatusCalls {
		if u.status == session.StatusStopped {
			found = true
		}
	}
	assert.True(t, found, "expected UpdateStatus(stopped) to be called")
}

func TestDeleteSession_OtherUser(t *testing.T) {
	sid := uuid.New()
	ownerID := uuid.New()
	attackerID := uuid.New()
	cid := "fakecontainer"
	rig := newRigFixedUser(t, attackerID, testPicoclawRecipe())
	rig.store.getFn = func(ctx context.Context, id uuid.UUID) (*session.Session, error) {
		return &session.Session{
			ID:          sid,
			UserID:      ownerID,
			Status:      session.StatusRunning,
			ContainerID: &cid,
		}, nil
	}

	req := httptest.NewRequest(http.MethodDelete, "/api/sessions/"+sid.String(), nil)
	rec := httptest.NewRecorder()
	rig.e.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusForbidden, rec.Code)
	assert.Equal(t, 0, rig.runner.stopCalls)
}

func TestMessage_DispatchesThroughBridgeRegistry(t *testing.T) {
	sid := uuid.New()
	uid := uuid.New()
	cid := "fakecontainer"
	rig := newRigFixedUser(t, uid, testAiderRecipe())
	rig.store.getFn = func(ctx context.Context, id uuid.UUID) (*session.Session, error) {
		return &session.Session{
			ID:          sid,
			UserID:      uid,
			RecipeName:  "aider",
			ModelID:     "claude-haiku-test",
			Status:      session.StatusRunning,
			ContainerID: &cid,
		}, nil
	}

	req := httptest.NewRequest(http.MethodPost, "/api/sessions/"+sid.String()+"/message",
		strings.NewReader(`{"text":"hello"}`))
	req.Header.Set(echo.HeaderContentType, "application/json")
	rec := httptest.NewRecorder()
	rig.e.ServeHTTP(rec, req)

	require.Equal(t, http.StatusOK, rec.Code, "body=%s", rec.Body.String())
	var resp map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &resp))
	assert.Equal(t, "ack: hello", resp["text"])
}

func TestMessage_UnsupportedMode(t *testing.T) {
	sid := uuid.New()
	uid := uuid.New()
	cid := "fakecontainer"
	rig := newRigFixedUser(t, uid, testAiderRecipe())
	rig.bridges.dispErr = bridge.ErrUnsupportedMode
	rig.store.getFn = func(ctx context.Context, id uuid.UUID) (*session.Session, error) {
		return &session.Session{
			ID:          sid,
			UserID:      uid,
			RecipeName:  "aider",
			ModelID:     "claude-haiku-test",
			Status:      session.StatusRunning,
			ContainerID: &cid,
		}, nil
	}

	req := httptest.NewRequest(http.MethodPost, "/api/sessions/"+sid.String()+"/message",
		strings.NewReader(`{"text":"hi"}`))
	req.Header.Set(echo.HeaderContentType, "application/json")
	rec := httptest.NewRecorder()
	rig.e.ServeHTTP(rec, req)

	require.Equal(t, http.StatusInternalServerError, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, "chat_bridge_unsupported_mode", decodeErrorCode(t, rec.Body.Bytes()))
}

func TestMessage_NotRunning(t *testing.T) {
	sid := uuid.New()
	uid := uuid.New()
	cid := "fakecontainer"
	rig := newRigFixedUser(t, uid, testAiderRecipe())
	rig.store.getFn = func(ctx context.Context, id uuid.UUID) (*session.Session, error) {
		return &session.Session{
			ID:          sid,
			UserID:      uid,
			RecipeName:  "aider",
			Status:      session.StatusStopped,
			ContainerID: &cid,
		}, nil
	}

	req := httptest.NewRequest(http.MethodPost, "/api/sessions/"+sid.String()+"/message",
		strings.NewReader(`{"text":"hello"}`))
	req.Header.Set(echo.HeaderContentType, "application/json")
	rec := httptest.NewRecorder()
	rig.e.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusConflict, rec.Code)
}

func TestMessage_Timeout(t *testing.T) {
	sid := uuid.New()
	uid := uuid.New()
	cid := "fakecontainer"
	rig := newRigFixedUser(t, uid, testAiderRecipe())
	rig.bridges.sendFn = func(ctx context.Context, containerID string, recipe *recipes.Recipe, modelID, text string) (string, error) {
		return "", bridge.ErrTimeout
	}
	rig.store.getFn = func(ctx context.Context, id uuid.UUID) (*session.Session, error) {
		return &session.Session{
			ID:          sid,
			UserID:      uid,
			RecipeName:  "aider",
			ModelID:     "claude-haiku-test",
			Status:      session.StatusRunning,
			ContainerID: &cid,
		}, nil
	}

	req := httptest.NewRequest(http.MethodPost, "/api/sessions/"+sid.String()+"/message",
		strings.NewReader(`{"text":"hello"}`))
	req.Header.Set(echo.HeaderContentType, "application/json")
	rec := httptest.NewRecorder()
	rig.e.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusGatewayTimeout, rec.Code, "body=%s", rec.Body.String())
}
