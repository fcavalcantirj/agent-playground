package handler

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/labstack/echo/v4"

	"github.com/agentplayground/api/internal/middleware"
)

// devSessionTTL is how long a dev login session is valid before it expires.
// 24h matches MSV's session window and gives developers a full day of work
// without re-logging.
const devSessionTTL = 24 * time.Hour

// DevAuthHandler implements the dev-mode-only POST /api/dev/login flow.
//
// Plan 01-01 D-09: enabled only when AP_DEV_MODE=true. Phase 3 will replace
// this with goth (Google + GitHub OAuth) -- the SessionProvider interface and
// AuthMiddleware stay unchanged.
type DevAuthHandler struct {
	pool     *pgxpool.Pool
	provider middleware.SessionProvider
	secret   []byte
	devMode  bool
}

// NewDevAuthHandler wires the dependencies for the dev auth routes.
func NewDevAuthHandler(pool *pgxpool.Pool, provider middleware.SessionProvider, secret []byte, devMode bool) *DevAuthHandler {
	return &DevAuthHandler{
		pool:     pool,
		provider: provider,
		secret:   secret,
		devMode:  devMode,
	}
}

// devLoginRequest is the JSON body POST /api/dev/login accepts. Both fields
// are optional; sane defaults make it a one-click login in dev.
type devLoginRequest struct {
	Email       string `json:"email"`
	DisplayName string `json:"display_name"`
}

// devLoginResponse is what /api/dev/login returns on success.
type devLoginResponse struct {
	UserID      string `json:"user_id"`
	DisplayName string `json:"display_name"`
}

// Login upserts a dev user and issues a signed session cookie. Returns 404
// when AP_DEV_MODE is false so the route is dead code in production -- this
// is the T-1-03 mitigation in the threat model.
func (h *DevAuthHandler) Login(c echo.Context) error {
	if !h.devMode {
		return echo.NewHTTPError(http.StatusNotFound, "not found")
	}

	var req devLoginRequest
	// Body is optional. Ignore decode errors when there's no body.
	if c.Request().ContentLength > 0 {
		if err := json.NewDecoder(c.Request().Body).Decode(&req); err != nil {
			return echo.NewHTTPError(http.StatusBadRequest, "invalid json")
		}
	}
	if req.Email == "" {
		req.Email = "dev@test.com"
	}
	if req.DisplayName == "" {
		req.DisplayName = "Dev User"
	}

	ctx := c.Request().Context()

	// Upsert the dev user. The unique index on (provider, provider_sub) is
	// partial -- we only enforce it for non-null providers, which the dev row
	// satisfies.
	var userID uuid.UUID
	err := h.pool.QueryRow(ctx, `
		INSERT INTO users (provider, provider_sub, email, display_name)
		VALUES ('dev', 'dev-local', $1, $2)
		ON CONFLICT (provider, provider_sub)
			WHERE provider IS NOT NULL AND provider_sub IS NOT NULL
		DO UPDATE SET email = EXCLUDED.email,
		              display_name = EXCLUDED.display_name,
		              updated_at = NOW()
		RETURNING id
	`, req.Email, req.DisplayName).Scan(&userID)
	if err != nil {
		return fmt.Errorf("upsert dev user: %w", err)
	}

	token, err := h.provider.CreateSession(ctx, userID)
	if err != nil {
		return fmt.Errorf("create session: %w", err)
	}

	c.SetCookie(&http.Cookie{
		Name:     middleware.CookieName,
		Value:    middleware.SignCookieValue(token, h.secret),
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   false, // dev only -- prod path comes with goth in Phase 3
		MaxAge:   int(devSessionTTL / time.Second),
	})

	return c.JSON(http.StatusOK, devLoginResponse{
		UserID:      userID.String(),
		DisplayName: req.DisplayName,
	})
}

// Logout destroys the session row and clears the cookie. Idempotent: missing
// or already-invalid cookies still return 200 to avoid leaking session state.
func (h *DevAuthHandler) Logout(c echo.Context) error {
	cookie, err := c.Cookie(middleware.CookieName)
	if err == nil && cookie != nil && cookie.Value != "" {
		// Try to extract the underlying token and destroy it. Even if the
		// HMAC is wrong we still clear the cookie below.
		if token, ok := extractToken(cookie.Value, h.secret); ok {
			_ = h.provider.DestroySession(c.Request().Context(), token)
		}
	}

	c.SetCookie(&http.Cookie{
		Name:     middleware.CookieName,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   -1,
	})
	return c.JSON(http.StatusOK, map[string]string{"message": "logged out"})
}

// meResponse is the JSON body returned by GET /api/me.
type meResponse struct {
	ID          string  `json:"id"`
	Email       *string `json:"email"`
	DisplayName *string `json:"display_name"`
	AvatarURL   *string `json:"avatar_url"`
	Provider    *string `json:"provider"`
}

// Me returns the authenticated user's profile. Requires AuthMiddleware to
// have populated the context.
func (h *DevAuthHandler) Me(c echo.Context) error {
	userID, err := middleware.GetUserID(c)
	if err != nil {
		return echo.NewHTTPError(http.StatusUnauthorized, "unauthorized")
	}

	var resp meResponse
	resp.ID = userID.String()
	err = h.pool.QueryRow(c.Request().Context(), `
		SELECT email, display_name, avatar_url, provider
		FROM users WHERE id = $1
	`, userID).Scan(&resp.Email, &resp.DisplayName, &resp.AvatarURL, &resp.Provider)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return echo.NewHTTPError(http.StatusNotFound, "user not found")
		}
		return fmt.Errorf("load user: %w", err)
	}
	return c.JSON(http.StatusOK, resp)
}

// extractToken parses the cookie value and returns the underlying token if
// the HMAC matches. Delegates to middleware.VerifyCookie for constant-time
// HMAC verification to prevent timing-based forgery attacks.
func extractToken(cookieValue string, secret []byte) (string, bool) {
	return middleware.VerifyCookie(cookieValue, secret)
}

// DevSessionStore is the Plan 01-01 SessionProvider implementation. Sessions
// live in the user_sessions table; the cookie carries a random 32-byte token
// and the DB stores the SHA-256 hash so the token never sits at rest in plain
// text.
//
// Phase 3 will replace this struct with a goth-backed equivalent that
// satisfies the same interface.
type DevSessionStore struct {
	Pool *pgxpool.Pool
}

// NewDevSessionStore constructs a DevSessionStore.
func NewDevSessionStore(pool *pgxpool.Pool) *DevSessionStore {
	return &DevSessionStore{Pool: pool}
}

// CreateSession generates a fresh token, stores its SHA-256 hash with a 24h
// expiry, and returns the raw token to the caller.
func (s *DevSessionStore) CreateSession(ctx context.Context, userID uuid.UUID) (string, error) {
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", fmt.Errorf("generate session token: %w", err)
	}
	token := hex.EncodeToString(raw)
	hash := sha256Hex(token)

	_, err := s.Pool.Exec(ctx, `
		INSERT INTO user_sessions (user_id, token_hash, expires_at)
		VALUES ($1, $2, NOW() + $3::interval)
	`, userID, hash, fmt.Sprintf("%d seconds", int(devSessionTTL/time.Second)))
	if err != nil {
		return "", fmt.Errorf("insert session: %w", err)
	}
	return token, nil
}

// ValidateSession looks up the session by hashed token and returns the user
// id if the row exists and has not expired.
func (s *DevSessionStore) ValidateSession(ctx context.Context, token string) (uuid.UUID, error) {
	hash := sha256Hex(token)
	var userID uuid.UUID
	err := s.Pool.QueryRow(ctx, `
		SELECT user_id FROM user_sessions
		WHERE token_hash = $1 AND expires_at > NOW()
	`, hash).Scan(&userID)
	if err != nil {
		return uuid.Nil, err
	}
	return userID, nil
}

// DestroySession deletes the session row by hashed token. Missing rows are
// silently ignored; the operation is idempotent.
func (s *DevSessionStore) DestroySession(ctx context.Context, token string) error {
	hash := sha256Hex(token)
	_, err := s.Pool.Exec(ctx, `DELETE FROM user_sessions WHERE token_hash = $1`, hash)
	return err
}

// sha256Hex is a tiny helper -- the hash never changes shape, no need for the
// crypto/sha256 import boilerplate at every call site.
func sha256Hex(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}
