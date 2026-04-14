// Package middleware hosts cross-cutting Echo middleware. Plan 01-01 adds the
// session cookie validator behind a SessionProvider interface so Phase 3 can
// swap goth in without touching middleware or handler code.
package middleware

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
)

// CookieName is the name of the session cookie set by the dev auth handler
// and validated by AuthMiddleware. Phase 3 (goth) reuses the same name.
const CookieName = "ap_session"

// userIDContextKey is the key under which AuthMiddleware stores the resolved
// user id on the echo.Context. Use GetUserID to read it.
const userIDContextKey = "user_id"

// SessionProvider abstracts the persistence layer behind cookie-based sessions.
// Plan 01-01 ships DevSessionStore (Postgres-backed). Phase 3 will provide an
// equivalent goth-backed implementation -- middleware and handlers stay the
// same because they only depend on this interface.
type SessionProvider interface {
	// CreateSession issues a fresh session token for the user and persists it.
	// The returned token is the raw value placed in the cookie (server-side it
	// is hashed before storage).
	CreateSession(ctx context.Context, userID uuid.UUID) (token string, err error)

	// ValidateSession checks that a token is currently valid (exists and not
	// expired) and returns the owning user id.
	ValidateSession(ctx context.Context, token string) (userID uuid.UUID, err error)

	// DestroySession deletes the persisted session row for a token. Idempotent:
	// destroying an already-removed token is not an error.
	DestroySession(ctx context.Context, token string) error
}

// AuthMiddleware returns Echo middleware that gates protected routes behind a
// valid signed session cookie. The cookie value format is `<hmac_hex>.<token>`
// where hmac_hex is HMAC-SHA256 of the token with the provided secret.
//
// On any failure (missing cookie, malformed value, bad HMAC, expired session)
// the request is rejected with 401 and a {"error":"unauthorized"} body. The
// response intentionally does NOT distinguish between failure modes so an
// attacker cannot probe the session store.
func AuthMiddleware(provider SessionProvider, secret []byte) echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			cookie, err := c.Cookie(CookieName)
			if err != nil || cookie == nil || cookie.Value == "" {
				return unauthorized(c)
			}

			token, ok := VerifyCookie(cookie.Value, secret)
			if !ok {
				return unauthorized(c)
			}

			userID, err := provider.ValidateSession(c.Request().Context(), token)
			if err != nil || userID == uuid.Nil {
				return unauthorized(c)
			}

			c.Set(userIDContextKey, userID)
			return next(c)
		}
	}
}

// SignCookieValue returns the cookie value to set for a given session token.
// Format: `<hmac_hex>.<token>` -- hmac_hex is constant-time-comparable in
// verifyCookie so attackers cannot tamper with the token without invalidating
// the signature.
func SignCookieValue(token string, secret []byte) string {
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(token))
	sig := hex.EncodeToString(mac.Sum(nil))
	return sig + "." + token
}

// VerifyCookie parses a `<hmac_hex>.<token>` value and returns the token if
// the signature matches. Constant-time comparison via hmac.Equal.
func VerifyCookie(value string, secret []byte) (string, bool) {
	idx := strings.IndexByte(value, '.')
	if idx <= 0 || idx == len(value)-1 {
		return "", false
	}
	gotSigHex := value[:idx]
	token := value[idx+1:]

	gotSig, err := hex.DecodeString(gotSigHex)
	if err != nil {
		return "", false
	}

	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(token))
	wantSig := mac.Sum(nil)

	if !hmac.Equal(gotSig, wantSig) {
		return "", false
	}
	return token, true
}

// GetUserID extracts the authenticated user id stored on the context by
// AuthMiddleware. Returns an error if no user id is present (route was not
// gated by AuthMiddleware, or the value is the wrong type).
func GetUserID(c echo.Context) (uuid.UUID, error) {
	v := c.Get(userIDContextKey)
	if v == nil {
		return uuid.Nil, errors.New("no user in context")
	}
	id, ok := v.(uuid.UUID)
	if !ok {
		return uuid.Nil, errors.New("user id has wrong type in context")
	}
	return id, nil
}

func unauthorized(c echo.Context) error {
	return c.JSON(http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
}
