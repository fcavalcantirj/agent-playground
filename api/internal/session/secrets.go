package session

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"github.com/google/uuid"
)

// ErrSecretMissing is returned by SecretSource.Get when the requested
// secret name is not known to the source. Callers should translate this
// to a 400/422 at the HTTP layer — the user picked a recipe whose
// RequiredSecrets list cannot be satisfied in the current deploy.
var ErrSecretMissing = errors.New("secret missing")

// SecretSource is the Phase 2 abstraction over "where does a secret
// value come from". Phase 2 ships exactly one implementation
// (DevEnvSource); Phase 3+ will add a KMS-backed production source
// keyed by per-user KEKs.
type SecretSource interface {
	// Get returns the raw secret value for a known name, or
	// ErrSecretMissing if the source doesn't know about it.
	Get(name string) (string, error)
}

// DevEnvSource reads the dev BYOK key from the process environment. It
// is intentionally restricted to "anthropic_key" — Phase 2 only drives
// Anthropic-backed recipes, and adding more providers belongs to Phase 4.
//
// THREAT NOTE (T-02-01): AnthropicKey is held only in this struct and
// the resulting on-disk file; it is NEVER logged and NEVER placed in
// the container PID 1's environment (ap-base's entrypoint reads the
// file and populates a per-agent env slice — see Plan 02-01 SUMMARY).
type DevEnvSource struct {
	AnthropicKey string
}

// NewDevEnvSource reads AP_DEV_BYOK_KEY from the process environment
// at call time and returns a source populated with whatever was set.
// An empty value is permitted — Get will then return ErrSecretMissing
// for every name, which the handler layer should surface as a 422.
func NewDevEnvSource() *DevEnvSource {
	return &DevEnvSource{
		AnthropicKey: os.Getenv("AP_DEV_BYOK_KEY"),
	}
}

// Get returns the secret value or ErrSecretMissing.
func (s *DevEnvSource) Get(name string) (string, error) {
	if s == nil {
		return "", ErrSecretMissing
	}
	switch name {
	case "anthropic_key":
		if s.AnthropicKey == "" {
			return "", ErrSecretMissing
		}
		return s.AnthropicKey, nil
	default:
		// Dev source only knows about anthropic_key in Phase 2.
		return "", ErrSecretMissing
	}
}

// DefaultSecretBaseDir is the host-side base directory where
// SecretWriter drops per-session secret files before bind-mounting
// them at /run/secrets inside the container. Each session gets its
// own subdirectory named by session UUID so Cleanup can nuke it
// atomically.
const DefaultSecretBaseDir = "/tmp/ap/secrets"

// SecretWriter materializes secrets from a SecretSource onto the host
// filesystem in a shape suitable for a Docker bind mount. It owns the
// /tmp/ap/secrets/<session_id>/ directory lifecycle.
//
// FILE PERMS (Pitfall 6 — userns-remap): Docker's userns-remap feature
// maps in-container uid 10000 (the `agent` user ap-base creates) to
// host uid 110000+. The secret file MUST be world-readable (0644)
// because the host kernel will see the container's read as coming from
// the remapped uid, which does NOT match the API server's uid that
// wrote the file. The enclosing directory is 0700 because only the API
// server process needs to list it — the container only needs to read
// the specific file by name via the bind mount.
//
// The bind mount itself is read-only (`:ro`) so the container cannot
// mutate the secret value or create new secret files at runtime.
type SecretWriter struct {
	// BaseDir defaults to DefaultSecretBaseDir. Tests override it to a
	// t.TempDir() path to avoid polluting /tmp.
	BaseDir string
	// Source is the upstream SecretSource this writer pulls values from.
	Source SecretSource
}

// NewSecretWriter returns a writer backed by the given source and
// defaulted to DefaultSecretBaseDir.
func NewSecretWriter(source SecretSource) *SecretWriter {
	return &SecretWriter{
		BaseDir: DefaultSecretBaseDir,
		Source:  source,
	}
}

// Provision creates <BaseDir>/<sessionID>/ with mode 0700, then for
// each required secret name, resolves the value from Source and writes
// it to a file of mode 0644 inside that directory. Returns the
// absolute directory path on success.
//
// The function is idempotent: calling it twice for the same session ID
// will overwrite existing files but preserve the directory.
//
// If any required secret is missing from the Source, Provision returns
// ErrSecretMissing and leaves the partially-populated directory in
// place so the caller can see what succeeded. The caller (Plan 05
// handler) should call Cleanup on error.
func (w *SecretWriter) Provision(sessionID uuid.UUID, required []string) (string, error) {
	if w == nil || w.Source == nil {
		return "", errors.New("session: nil SecretWriter or Source")
	}
	dir := filepath.Join(w.BaseDir, sessionID.String())
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", fmt.Errorf("session: mkdir secrets: %w", err)
	}
	// os.MkdirAll honors umask, so re-chmod to the exact posture we want.
	if err := os.Chmod(dir, 0o700); err != nil {
		return "", fmt.Errorf("session: chmod secrets dir: %w", err)
	}

	for _, name := range required {
		val, err := w.Source.Get(name)
		if err != nil {
			return dir, fmt.Errorf("session: secret %q: %w", name, err)
		}
		path := filepath.Join(dir, name)
		if err := os.WriteFile(path, []byte(val), 0o644); err != nil {
			return dir, fmt.Errorf("session: write secret %q: %w", name, err)
		}
		// Defense in depth: WriteFile honors umask; force 0644.
		if err := os.Chmod(path, 0o644); err != nil {
			return dir, fmt.Errorf("session: chmod secret %q: %w", name, err)
		}
	}
	return dir, nil
}

// Cleanup removes the entire <BaseDir>/<sessionID>/ subtree. Safe to
// call even if Provision was never called — os.RemoveAll on a
// non-existent path returns nil.
func (w *SecretWriter) Cleanup(sessionID uuid.UUID) error {
	if w == nil {
		return nil
	}
	dir := filepath.Join(w.BaseDir, sessionID.String())
	if err := os.RemoveAll(dir); err != nil {
		return fmt.Errorf("session: cleanup secrets: %w", err)
	}
	return nil
}

// BindMountSpec returns the "host:container:ro" string the caller adds
// to RunOptions.Mounts so Docker bind-mounts the per-session secrets
// directory into /run/secrets inside the container. The `:ro` suffix
// makes the mount read-only; the container cannot mutate the values
// or introduce new secret files at runtime.
//
// Note: BindMountSpec always returns a path under DefaultSecretBaseDir
// (not w.BaseDir) because production containers always bind-mount
// /tmp/ap/secrets. Tests that override BaseDir do NOT exercise the
// bind mount — that is Plan 05's handler-level responsibility.
func (w *SecretWriter) BindMountSpec(sessionID uuid.UUID) string {
	return fmt.Sprintf("%s/%s:/run/secrets:ro", DefaultSecretBaseDir, sessionID.String())
}
