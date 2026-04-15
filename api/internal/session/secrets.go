package session

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/google/uuid"
)

// ErrSecretMissing is returned by SecretSource.Get / Resolve when the
// requested secret name is not known to the source. Callers should
// translate this to a 400/422 at the HTTP layer — the user picked a
// recipe whose RequiredSecrets list cannot be satisfied in the current
// deploy.
var ErrSecretMissing = errors.New("secret missing")

// SecretSource is the abstraction over "where does a secret value come
// from". Phase 2 shipped the `Get(name)` path; Phase 02.5 extends the
// interface with `Resolve(ref)` so recipe manifests can mix literal
// values and `secret:<name>` references without every call-site needing
// to know the split.
//
// Implementations MUST honor both methods:
//   - Get returns the raw secret value for a known name or
//     ErrSecretMissing.
//   - Resolve returns the ref unchanged if it has no `secret:` prefix
//     (literal passthrough); otherwise it strips the prefix and
//     delegates to Get.
//
// Phase 3+ will add a KMS-backed production source keyed by per-user
// KEKs; the interface is unchanged.
type SecretSource interface {
	Get(name string) (string, error)
	Resolve(ref string) (string, error)
}

// DevEnvSecretSource reads dev BYOK keys from the process environment.
// It recognises the well-known Anthropic and OpenRouter env vars used
// by the catalog recipes plus a generic `AP_DEV_<UPPER>_KEY` scan so
// operators can inject custom keys without a Go recompile.
//
// THREAT NOTE (T-02-01, T-02.5-02): values are held only in this struct
// and the resulting per-session tmpfs files materialized by Plan 05;
// they are NEVER logged and NEVER placed directly in the container's
// PID 1 env. The zerolog writer pipeline wraps stdout with
// logging.InstallRedactionHook as defence in depth.
type DevEnvSecretSource struct {
	AnthropicKey  string
	OpenRouterKey string
	// extras holds any AP_DEV_<NAME>_KEY env vars other than the two
	// well-known ones. Keys are hyphen-normalized lower case
	// ("AP_DEV_MY_CUSTOM_KEY" → "my-custom").
	extras map[string]string
}

// DevEnvSource is the Phase 2 type name kept as an alias so existing
// callers (main.go wiring, handler tests, etc.) keep compiling without
// touching a line. Every Phase 2 call site that declared
// `&session.DevEnvSource{AnthropicKey: ...}` still works because
// DevEnvSecretSource's first field is AnthropicKey.
type DevEnvSource = DevEnvSecretSource

// NewDevEnvSource is the Phase 2 constructor retained for backwards
// compatibility. It forwards to NewDevEnvSecretSource.
func NewDevEnvSource() *DevEnvSource {
	return NewDevEnvSecretSource()
}

// NewDevEnvSecretSource reads AP_DEV_BYOK_KEY (Anthropic),
// AP_DEV_OPENROUTER_KEY (OpenRouter), and any other AP_DEV_<NAME>_KEY
// env vars into the returned source. Empty values are permitted — the
// corresponding Resolve / Get call returns ErrSecretMissing.
func NewDevEnvSecretSource() *DevEnvSecretSource {
	s := &DevEnvSecretSource{
		AnthropicKey:  os.Getenv("AP_DEV_BYOK_KEY"),
		OpenRouterKey: os.Getenv("AP_DEV_OPENROUTER_KEY"),
		extras:        map[string]string{},
	}
	for _, kv := range os.Environ() {
		if !strings.HasPrefix(kv, "AP_DEV_") {
			continue
		}
		eq := strings.IndexByte(kv, '=')
		if eq < 0 {
			continue
		}
		name := kv[:eq]
		value := kv[eq+1:]
		if !strings.HasSuffix(name, "_KEY") {
			continue
		}
		if name == "AP_DEV_BYOK_KEY" || name == "AP_DEV_OPENROUTER_KEY" {
			continue
		}
		mid := strings.TrimSuffix(strings.TrimPrefix(name, "AP_DEV_"), "_KEY")
		if mid == "" {
			continue
		}
		normalized := strings.ToLower(strings.ReplaceAll(mid, "_", "-"))
		s.extras[normalized] = value
	}
	return s
}

// Get returns the raw secret value for a canonical name or
// ErrSecretMissing. The Phase 2 contract (Get("anthropic_key") returns
// AnthropicKey) is preserved exactly.
func (s *DevEnvSecretSource) Get(name string) (string, error) {
	if s == nil {
		return "", ErrSecretMissing
	}
	switch normalizeSecretName(name) {
	case "anthropic-api-key":
		if s.AnthropicKey == "" {
			return "", ErrSecretMissing
		}
		return s.AnthropicKey, nil
	case "openrouter-api-key":
		if s.OpenRouterKey == "" {
			return "", ErrSecretMissing
		}
		return s.OpenRouterKey, nil
	default:
		if v, ok := s.extras[normalizeSecretName(name)]; ok {
			return v, nil
		}
		return "", ErrSecretMissing
	}
}

// Resolve implements the Phase 02.5 secret-indirection API. Values
// without the `secret:` prefix pass through unchanged (literals);
// `secret:<name>` strips the prefix and delegates to Get.
func (s *DevEnvSecretSource) Resolve(ref string) (string, error) {
	key, ok := strings.CutPrefix(ref, "secret:")
	if !ok {
		return ref, nil
	}
	return s.Get(key)
}

// normalizeSecretName canonicalizes the secret name variants the dev
// source understands. Hyphen vs underscore, short vs long form, all
// collapse to the hyphenated canonical form used by the catalog
// recipes.
//
//	anthropic_key / anthropic-key / anthropic_api_key → anthropic-api-key
//	openrouter_key / openrouter-key / openrouter_api_key → openrouter-api-key
//
// Unknown names are lower-cased + hyphenated and looked up in the
// extras map verbatim.
func normalizeSecretName(name string) string {
	lower := strings.ToLower(strings.ReplaceAll(name, "_", "-"))
	switch lower {
	case "anthropic-key", "anthropic-api-key":
		return "anthropic-api-key"
	case "openrouter-key", "openrouter-api-key":
		return "openrouter-api-key"
	}
	return lower
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

// WriteAuthFile materializes a recipe-specific auth file under the
// per-session secrets dir and returns the "host:container:ro" bind
// mount spec for it. Each auth file is a separate file-level bind
// mount into the agent's $HOME so it overlays the image's baked copy
// (ap-picoclaw bakes an empty .security.yml; this replaces it with a
// key-populated one at session start).
//
// Called by the handler after Provision, once per entry in
// recipe.AgentAuthFiles. The returned spec targets the ABSOLUTE path
// that exists inside the Docker daemon's mount namespace — which is
// DefaultSecretBaseDir, NOT w.BaseDir — because containers only know
// about /tmp/ap/secrets (tests override BaseDir for isolation but
// production always uses the default).
func (w *SecretWriter) WriteAuthFile(sessionID uuid.UUID, filename, containerPath, content string) (string, error) {
	if w == nil {
		return "", errors.New("session: nil SecretWriter")
	}
	dir := filepath.Join(w.BaseDir, sessionID.String())
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", fmt.Errorf("session: mkdir secrets: %w", err)
	}
	hostPath := filepath.Join(dir, filename)
	if err := os.WriteFile(hostPath, []byte(content), 0o644); err != nil {
		return "", fmt.Errorf("session: write auth file %q: %w", filename, err)
	}
	if err := os.Chmod(hostPath, 0o644); err != nil {
		return "", fmt.Errorf("session: chmod auth file %q: %w", filename, err)
	}
	prodPath := filepath.Join(DefaultSecretBaseDir, sessionID.String(), filename)
	return fmt.Sprintf("%s:%s:ro", prodPath, containerPath), nil
}
