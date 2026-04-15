// Package handler's errors.go centralizes the Phase 02.5 error-code
// constants (D-54) and the WriteError envelope helper used by the
// recipes + sessions HTTP layers.
//
// The JSON envelope matches the Phase 1 contract already emitted by
// devauth.go:
//
//	{"error": {"code": "...", "message": "..."}}
//
// Code strings are stable external identifiers — renaming one is an
// API break.
package handler

import (
	"github.com/labstack/echo/v4"
)

// Error code constants (D-54). The set is closed — adding a new code
// requires a plan amend so the frontend error-handling layer stays in
// sync.
const (
	ErrCodeRecipeNotFound        = "recipe_not_found"
	ErrCodeProviderNotSupported  = "provider_not_supported"
	ErrCodeModelNotSupported     = "model_not_supported"
	ErrCodeSecretMissing         = "secret_missing"
	ErrCodeTemplateRenderFailed  = "template_render_failed"
	ErrCodeLifecycleHookFailed   = "lifecycle_hook_failed"
	ErrCodeChatBridgeUnsupported = "chat_bridge_unsupported_mode"
	ErrCodeInvalidRequest        = "invalid_request"
	ErrCodeInternal              = "internal"
	ErrCodeUnauthorized          = "unauthorized"
	ErrCodeForbidden             = "forbidden"
	ErrCodeConflict              = "conflict"
	ErrCodeTimeout               = "timeout"
)

// errorEnvelope is the Phase 1 JSON shape. The `error` object is a
// stable two-field structure {code, message} — no other keys.
type errorEnvelope struct {
	Error errorBody `json:"error"`
}

type errorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// WriteError renders the Phase 1 error envelope with a stable code + a
// human-readable message. Every 4xx/5xx session + recipe response goes
// through this helper so the shape cannot drift between handlers.
//
// The message MUST NOT contain resolved secret values — callers are
// responsible for scrubbing (threat model T-02.5-02b).
func WriteError(c echo.Context, status int, code, message string) error {
	return c.JSON(status, errorEnvelope{Error: errorBody{Code: code, Message: message}})
}
