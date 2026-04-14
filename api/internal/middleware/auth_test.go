package middleware_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/internal/middleware"
)

// fakeProvider is a stub SessionProvider used by middleware tests. It returns
// the configured userID for any token in `valid` and ErrNoSession otherwise.
type fakeProvider struct {
	valid  map[string]uuid.UUID
	expErr error
}

var errNoSession = errors.New("no session")

func (f *fakeProvider) CreateSession(_ context.Context, userID uuid.UUID) (string, error) {
	tok := "token-" + userID.String()
	if f.valid == nil {
		f.valid = map[string]uuid.UUID{}
	}
	f.valid[tok] = userID
	return tok, nil
}

func (f *fakeProvider) ValidateSession(_ context.Context, token string) (uuid.UUID, error) {
	if f.expErr != nil {
		return uuid.Nil, f.expErr
	}
	id, ok := f.valid[token]
	if !ok {
		return uuid.Nil, errNoSession
	}
	return id, nil
}

func (f *fakeProvider) DestroySession(_ context.Context, token string) error {
	delete(f.valid, token)
	return nil
}

// runWithCookie wires AuthMiddleware in front of an "ok" handler and runs one
// HTTP request, optionally attaching a cookie.
func runWithCookie(t *testing.T, prov middleware.SessionProvider, secret []byte, cookie *http.Cookie) *httptest.ResponseRecorder {
	t.Helper()
	e := echo.New()
	h := middleware.AuthMiddleware(prov, secret)(func(c echo.Context) error {
		// Confirm middleware put a user on the context.
		if _, err := middleware.GetUserID(c); err != nil {
			t.Fatalf("user id not set on context: %v", err)
		}
		return c.String(http.StatusOK, "ok")
	})

	req := httptest.NewRequest(http.MethodGet, "/api/me", nil)
	if cookie != nil {
		req.AddCookie(cookie)
	}
	rec := httptest.NewRecorder()
	c := e.NewContext(req, rec)
	if err := h(c); err != nil {
		// Echo error handlers normally write to rec, but our middleware
		// returns the response directly via c.JSON.
		t.Fatalf("middleware returned error: %v", err)
	}
	return rec
}

func TestAuthMiddleware_NoCookie(t *testing.T) {
	rec := runUnauthorized(t, &fakeProvider{}, []byte("test-secret-needs-32-characters!!"), nil)
	require.Equal(t, http.StatusUnauthorized, rec.Code)
}

func TestAuthMiddleware_BadHMAC(t *testing.T) {
	prov := &fakeProvider{valid: map[string]uuid.UUID{"tok1": uuid.New()}}
	cookie := &http.Cookie{
		Name:  middleware.CookieName,
		Value: "deadbeef.tok1", // bogus hmac
	}
	rec := runUnauthorized(t, prov, []byte("test-secret-needs-32-characters!!"), cookie)
	require.Equal(t, http.StatusUnauthorized, rec.Code)
}

func TestAuthMiddleware_MalformedValue(t *testing.T) {
	prov := &fakeProvider{}
	cookie := &http.Cookie{Name: middleware.CookieName, Value: "no-dot-here"}
	rec := runUnauthorized(t, prov, []byte("test-secret-needs-32-characters!!"), cookie)
	require.Equal(t, http.StatusUnauthorized, rec.Code)
}

func TestAuthMiddleware_ValidCookie(t *testing.T) {
	uid := uuid.New()
	prov := &fakeProvider{valid: map[string]uuid.UUID{"tok1": uid}}
	secret := []byte("test-secret-needs-32-characters!!")
	cookie := &http.Cookie{
		Name:  middleware.CookieName,
		Value: middleware.SignCookieValue("tok1", secret),
	}
	rec := runWithCookie(t, prov, secret, cookie)
	require.Equal(t, http.StatusOK, rec.Code)
	require.Equal(t, "ok", rec.Body.String())
}

func TestAuthMiddleware_ExpiredSession(t *testing.T) {
	prov := &fakeProvider{expErr: errNoSession} // provider rejects all
	secret := []byte("test-secret-needs-32-characters!!")
	cookie := &http.Cookie{
		Name:  middleware.CookieName,
		Value: middleware.SignCookieValue("expired-token", secret),
	}
	rec := runUnauthorized(t, prov, secret, cookie)
	require.Equal(t, http.StatusUnauthorized, rec.Code)
}

// runUnauthorized runs a request expected to be rejected. It uses a sentinel
// handler that should NEVER fire; if it does, we fail loudly.
func runUnauthorized(t *testing.T, prov middleware.SessionProvider, secret []byte, cookie *http.Cookie) *httptest.ResponseRecorder {
	t.Helper()
	e := echo.New()
	called := false
	h := middleware.AuthMiddleware(prov, secret)(func(c echo.Context) error {
		called = true
		return c.String(http.StatusOK, "should not run")
	})

	req := httptest.NewRequest(http.MethodGet, "/api/me", nil)
	if cookie != nil {
		req.AddCookie(cookie)
	}
	rec := httptest.NewRecorder()
	c := e.NewContext(req, rec)
	if err := h(c); err != nil {
		t.Fatalf("middleware returned error: %v", err)
	}
	require.False(t, called, "downstream handler must NOT be called for unauthorized requests")
	return rec
}
