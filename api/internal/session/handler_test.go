package session_test

import (
	"context"
	"encoding/json"
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

	"github.com/agentplayground/api/internal/session"
	"github.com/agentplayground/api/pkg/docker"
)

// ----- mocks -----

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

type mockSecretWriter struct {
	provisionFn func(sessionID uuid.UUID, required []string) (string, error)
	cleanupFn   func(sessionID uuid.UUID) error

	mu           sync.Mutex
	cleanupCalls int
}

func (m *mockSecretWriter) Provision(sessionID uuid.UUID, required []string) (string, error) {
	if m.provisionFn != nil {
		return m.provisionFn(sessionID, required)
	}
	return "/tmp/ap/secrets/" + sessionID.String(), nil
}

func (m *mockSecretWriter) Cleanup(sessionID uuid.UUID) error {
	m.mu.Lock()
	m.cleanupCalls++
	m.mu.Unlock()
	if m.cleanupFn != nil {
		return m.cleanupFn(sessionID)
	}
	return nil
}

func (m *mockSecretWriter) BindMountSpec(sessionID uuid.UUID) string {
	return "/tmp/ap/secrets/" + sessionID.String() + ":/run/secrets:ro"
}

func (m *mockSecretWriter) WriteAuthFile(sessionID uuid.UUID, filename, containerPath, content string) (string, error) {
	return "/tmp/ap/secrets/" + sessionID.String() + "/" + filename + ":" + containerPath + ":ro", nil
}

type mockContainerRunner struct {
	runFn    func(ctx context.Context, opts docker.RunOptions) (string, error)
	stopFn   func(ctx context.Context, id string) error
	removeFn func(ctx context.Context, id string) error

	mu          sync.Mutex
	stopCalls   int
	removeCalls int
	lastRunOpts docker.RunOptions

	execFn          func(ctx context.Context, containerID string, cmd []string) ([]byte, error)
	execWithStdinFn func(ctx context.Context, containerID string, cmd []string, stdin io.Reader) ([]byte, error)
}

func (m *mockContainerRunner) Run(ctx context.Context, opts docker.RunOptions) (string, error) {
	m.mu.Lock()
	m.lastRunOpts = opts
	m.mu.Unlock()
	if m.runFn != nil {
		return m.runFn(ctx, opts)
	}
	return "fakecontainerid1234567890abcdef", nil
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

func (m *mockContainerRunner) Exec(ctx context.Context, containerID string, cmd []string) ([]byte, error) {
	if m.execFn != nil {
		return m.execFn(ctx, containerID, cmd)
	}
	return []byte("mock-reply"), nil
}

func (m *mockContainerRunner) ExecWithStdin(ctx context.Context, containerID string, cmd []string, stdin io.Reader) ([]byte, error) {
	if m.execWithStdinFn != nil {
		return m.execWithStdinFn(ctx, containerID, cmd, stdin)
	}
	return nil, nil
}

// ----- test helpers -----

func buildHandlerTest(t *testing.T, store *mockStore, sw *mockSecretWriter, runner *mockContainerRunner) (*echo.Echo, uuid.UUID) {
	t.Helper()
	if store == nil {
		store = &mockStore{}
	}
	if sw == nil {
		sw = &mockSecretWriter{}
	}
	if runner == nil {
		runner = &mockContainerRunner{}
	}

	bridge := session.NewBridge(runner)
	h := session.NewHandler(store, runner, sw, &session.DevEnvSource{AnthropicKey: "sk-ant-test"}, bridge, zerolog.Nop())

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

	return e, userID
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

// buildWithFixedUser mounts the handler behind middleware that always sets
// the provided user_id on the context — used for DELETE/message tests
// where we need a known user to match the mockStore row's ownership.
func buildWithFixedUser(t *testing.T, uid uuid.UUID, store *mockStore, sw *mockSecretWriter, runner *mockContainerRunner) *echo.Echo {
	t.Helper()
	if store == nil {
		store = &mockStore{}
	}
	if sw == nil {
		sw = &mockSecretWriter{}
	}
	if runner == nil {
		runner = &mockContainerRunner{}
	}
	h := session.NewHandler(store, runner, sw, &session.DevEnvSource{AnthropicKey: "sk-ant-test"}, session.NewBridge(runner), zerolog.Nop())
	e := echo.New()
	authed := e.Group("/api", func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			c.Set("user_id", uid)
			return next(c)
		}
	})
	h.Register(authed)
	return e
}

// ----- tests -----

func TestHandler_CreateSession_Success(t *testing.T) {
	store := &mockStore{}
	sw := &mockSecretWriter{}
	runner := &mockContainerRunner{}
	e, userID := buildHandlerTest(t, store, sw, runner)

	rec := doRequest(t, e, http.MethodPost, "/api/sessions",
		`{"recipe":"picoclaw","model_provider":"anthropic","model_id":"claude-3-5-sonnet"}`,
		userID, true)

	require.Equal(t, http.StatusCreated, rec.Code, "body=%s", rec.Body.String())
	var resp map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &resp))
	assert.NotEmpty(t, resp["id"])
	assert.Equal(t, "running", resp["status"])
	assert.GreaterOrEqual(t, len(store.updateContainerCalls), 1)

	// Verify sandbox defaults were applied to the RunOptions.
	runner.mu.Lock()
	opts := runner.lastRunOpts
	runner.mu.Unlock()
	assert.True(t, opts.ReadOnlyRootfs, "ReadOnlyRootfs must be true")
	assert.True(t, opts.NoNewPrivs, "NoNewPrivs must be true")
	assert.Contains(t, opts.CapDrop, "ALL", "CapDrop must contain ALL")
	assert.Equal(t, "ap-picoclaw:v0.1.0-c7461f9", opts.Image)
	// Name should be the deterministic playground- format.
	assert.Contains(t, opts.Name, "playground-")
	// BindMountSpec should be appended to Mounts.
	found := false
	for _, m := range opts.Mounts {
		if strings.Contains(m, "/run/secrets:ro") {
			found = true
		}
	}
	assert.True(t, found, "secrets bind mount must be in Mounts")
}

func TestHandler_CreateSession_UnknownRecipe(t *testing.T) {
	e, userID := buildHandlerTest(t, nil, nil, nil)
	rec := doRequest(t, e, http.MethodPost, "/api/sessions",
		`{"recipe":"bogus","model_provider":"anthropic","model_id":"x"}`,
		userID, true)
	assert.Equal(t, http.StatusBadRequest, rec.Code)
}

func TestHandler_CreateSession_NoAuth(t *testing.T) {
	e, userID := buildHandlerTest(t, nil, nil, nil)
	rec := doRequest(t, e, http.MethodPost, "/api/sessions",
		`{"recipe":"picoclaw","model_provider":"anthropic","model_id":"x"}`,
		userID, false)
	assert.Equal(t, http.StatusUnauthorized, rec.Code)
}

func TestHandler_CreateSession_OneActive(t *testing.T) {
	store := &mockStore{
		createFn: func(ctx context.Context, userID uuid.UUID, recipe, provider, modelID string) (*session.Session, error) {
			return nil, session.ErrConflictActive
		},
	}
	e, userID := buildHandlerTest(t, store, nil, nil)
	rec := doRequest(t, e, http.MethodPost, "/api/sessions",
		`{"recipe":"picoclaw","model_provider":"anthropic","model_id":"x"}`,
		userID, true)
	assert.Equal(t, http.StatusConflict, rec.Code)
}

func TestHandler_CreateSession_MissingSecret(t *testing.T) {
	sw := &mockSecretWriter{
		provisionFn: func(sessionID uuid.UUID, required []string) (string, error) {
			return "", session.ErrSecretMissing
		},
	}
	e, userID := buildHandlerTest(t, nil, sw, nil)
	rec := doRequest(t, e, http.MethodPost, "/api/sessions",
		`{"recipe":"picoclaw","model_provider":"anthropic","model_id":"x"}`,
		userID, true)
	assert.Equal(t, http.StatusServiceUnavailable, rec.Code)
}

func TestHandler_DeleteSession(t *testing.T) {
	sid := uuid.New()
	uid := uuid.New()
	cid := "fakecontainer"
	store := &mockStore{
		getFn: func(ctx context.Context, id uuid.UUID) (*session.Session, error) {
			return &session.Session{
				ID:          sid,
				UserID:      uid,
				RecipeName:  "picoclaw",
				Status:      session.StatusRunning,
				ContainerID: &cid,
			}, nil
		},
	}
	sw := &mockSecretWriter{}
	runner := &mockContainerRunner{}
	e := buildWithFixedUser(t, uid, store, sw, runner)

	req := httptest.NewRequest(http.MethodDelete, "/api/sessions/"+sid.String(), nil)
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusOK, rec.Code, "body=%s", rec.Body.String())
	assert.Equal(t, 1, runner.stopCalls)
	assert.Equal(t, 1, runner.removeCalls)
	assert.Equal(t, 1, sw.cleanupCalls)
	found := false
	for _, u := range store.updateStatusCalls {
		if u.status == session.StatusStopped {
			found = true
		}
	}
	assert.True(t, found, "expected UpdateStatus(stopped) to be called")
}

func TestHandler_DeleteSession_OtherUser(t *testing.T) {
	sid := uuid.New()
	ownerID := uuid.New()
	attackerID := uuid.New()
	cid := "fakecontainer"
	store := &mockStore{
		getFn: func(ctx context.Context, id uuid.UUID) (*session.Session, error) {
			return &session.Session{
				ID:          sid,
				UserID:      ownerID,
				Status:      session.StatusRunning,
				ContainerID: &cid,
			}, nil
		},
	}
	sw := &mockSecretWriter{}
	runner := &mockContainerRunner{}
	e := buildWithFixedUser(t, attackerID, store, sw, runner)

	req := httptest.NewRequest(http.MethodDelete, "/api/sessions/"+sid.String(), nil)
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusForbidden, rec.Code)
	assert.Equal(t, 0, runner.stopCalls)
}

func TestHandler_Message_Timeout(t *testing.T) {
	sid := uuid.New()
	uid := uuid.New()
	cid := "fakecontainer"
	store := &mockStore{
		getFn: func(ctx context.Context, id uuid.UUID) (*session.Session, error) {
			return &session.Session{
				ID:          sid,
				UserID:      uid,
				RecipeName:  "hermes",
				Status:      session.StatusRunning,
				ContainerID: &cid,
			}, nil
		},
	}
	runner := &mockContainerRunner{
		execFn: func(ctx context.Context, containerID string, cmd []string) ([]byte, error) {
			return nil, context.DeadlineExceeded
		},
	}
	sw := &mockSecretWriter{}
	e := buildWithFixedUser(t, uid, store, sw, runner)

	req := httptest.NewRequest(http.MethodPost, "/api/sessions/"+sid.String()+"/message",
		strings.NewReader(`{"text":"hello"}`))
	req.Header.Set(echo.HeaderContentType, "application/json")
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusGatewayTimeout, rec.Code, "body=%s", rec.Body.String())
}

func TestHandler_Message_NotRunning(t *testing.T) {
	sid := uuid.New()
	uid := uuid.New()
	cid := "fakecontainer"
	store := &mockStore{
		getFn: func(ctx context.Context, id uuid.UUID) (*session.Session, error) {
			return &session.Session{
				ID:          sid,
				UserID:      uid,
				RecipeName:  "hermes",
				Status:      session.StatusStopped,
				ContainerID: &cid,
			}, nil
		},
	}
	runner := &mockContainerRunner{}
	sw := &mockSecretWriter{}
	e := buildWithFixedUser(t, uid, store, sw, runner)

	req := httptest.NewRequest(http.MethodPost, "/api/sessions/"+sid.String()+"/message",
		strings.NewReader(`{"text":"hello"}`))
	req.Header.Set(echo.HeaderContentType, "application/json")
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)

	assert.Equal(t, http.StatusConflict, rec.Code)
}
