package recipes

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"

	"github.com/rs/zerolog"
	"sigs.k8s.io/yaml"
)

// Loader errors. The exported set is intentionally small — callers
// discriminate via errors.Is so we avoid coupling to message strings.
var (
	// ErrRecipeInvalid wraps every recipe-level failure the loader
	// surfaces. Callers use errors.Is(err, ErrRecipeInvalid) to decide
	// whether the API should refuse to boot.
	ErrRecipeInvalid = errors.New("recipe invalid")

	// ErrFlavorChain fires when a flavor points at another flavor. v0.1
	// bans chains to keep resolution a single second pass.
	ErrFlavorChain = errors.New("flavor of flavor not allowed")

	// ErrFlavorRedeclaresInstall fires when a flavor carries its own
	// install block. The parent owns install; the flavor owns every
	// other field (env, models, launch args, etc.).
	ErrFlavorRedeclaresInstall = errors.New("flavor cannot redeclare install")

	// ErrInstallRuntimeMismatch fires when install.type and
	// runtime.family disagree (e.g. pip + node).
	ErrInstallRuntimeMismatch = errors.New("install.type does not match runtime.family")

	// ErrSecretRefMissingSchema fires when auth.env or auth.files
	// references a secret that is not declared in auth.secrets_schema.
	// Without this check, a typo in auth.env would silently resolve to
	// an empty string at render time (Pitfall 2 backstop).
	ErrSecretRefMissingSchema = errors.New("auth references secret not listed in auth.secrets_schema")
)

// sha40RE enforces a 40-char lowercase hex SHA for git-built installs.
// Belt-and-suspenders: the schema already enforces the same pattern.
var sha40RE = regexp.MustCompile(`^[a-f0-9]{40}$`)

// Loader owns the on-disk → in-memory pipeline for ap.recipe/v1 YAML
// files. One Loader instance maps to one recipe root directory and
// holds the current catalog behind a read-write mutex. Loader.Reload
// swaps the entire map atomically so readers never observe a torn
// state (D-35).
type Loader struct {
	root      string
	validator *SchemaValidator
	logger    zerolog.Logger

	mu    sync.RWMutex
	cache map[string]*Recipe
}

// NewLoader constructs a Loader rooted at the given directory.
// The caller supplies the SchemaValidator so its compile cost is paid
// exactly once at API boot.
func NewLoader(root string, v *SchemaValidator, logger zerolog.Logger) *Loader {
	return &Loader{
		root:      root,
		validator: v,
		logger:    logger,
		cache:     map[string]*Recipe{},
	}
}

// LoadAll walks the configured root, validates + semantically checks
// every `<id>/recipe.yaml` file it finds, resolves flavors in a second
// pass, and atomically swaps the in-memory cache on success. On any
// failure the previous cache is left intact — partial loads never
// reach readers.
//
// The loader skips a handful of reserved subdirectories so the layout
//
//	agents/
//	├── schemas/          (JSON Schema lives here, not a recipe)
//	├── community/        (Phase 8 bootstrap dest; not loaded in v1)
//	└── <id>/recipe.yaml
//
// can coexist.
func (l *Loader) LoadAll(ctx context.Context) error {
	entries, err := os.ReadDir(l.root)
	if err != nil {
		return fmt.Errorf("recipes: read root %q: %w", l.root, err)
	}

	loaded := make(map[string]*Recipe)
	for _, e := range entries {
		if !e.IsDir() || e.Name() == "schemas" || e.Name() == "community" {
			continue
		}
		id := e.Name()
		path := filepath.Join(l.root, id, "recipe.yaml")
		raw, err := os.ReadFile(path)
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return fmt.Errorf("recipes: read %s: %w", path, err)
		}
		if err := l.validator.ValidateYAML(raw); err != nil {
			return fmt.Errorf("%w: %s: %v", ErrRecipeInvalid, id, err)
		}
		var r Recipe
		if err := yaml.UnmarshalStrict(raw, &r); err != nil {
			return fmt.Errorf("%w: %s unmarshal: %v", ErrRecipeInvalid, id, err)
		}
		if r.ID != id {
			return fmt.Errorf("%w: directory %q has recipe.id=%q", ErrRecipeInvalid, id, r.ID)
		}
		if err := l.semanticCheck(&r); err != nil {
			return fmt.Errorf("%w: %s: %w", ErrRecipeInvalid, id, err)
		}
		loaded[id] = &r
	}

	// Second pass: flavor resolution.
	// We walk the map in two phases — first verifying the parent exists
	// and is itself not a flavor, then verifying the flavor does not
	// carry its own install block. This ordering matches Pitfall 6: we
	// want the most specific error possible.
	for _, r := range loaded {
		if r.ConfigFlavorOf == "" {
			continue
		}
		parent, ok := loaded[r.ConfigFlavorOf]
		if !ok {
			return fmt.Errorf("%w: %s references unknown parent %q",
				ErrRecipeInvalid, r.ID, r.ConfigFlavorOf)
		}
		if parent.ConfigFlavorOf != "" {
			return fmt.Errorf("%w: %s → %s → %s",
				ErrFlavorChain, r.ID, parent.ID, parent.ConfigFlavorOf)
		}
		if r.Install.Type != "" {
			return fmt.Errorf("%w: %s", ErrFlavorRedeclaresInstall, r.ID)
		}
	}

	// Honor context cancellation — late in the function so we still
	// commit the loaded map if the caller didn't cancel.
	if err := ctx.Err(); err != nil {
		return err
	}

	l.mu.Lock()
	l.cache = loaded
	l.mu.Unlock()
	l.logger.Info().Int("count", len(loaded)).Str("root", l.root).Msg("recipes loaded")
	return nil
}

// semanticCheck runs the cross-field invariants the schema cannot
// express directly. It is called per-recipe during the first pass;
// flavor resolution happens separately after all recipes are loaded.
func (l *Loader) semanticCheck(r *Recipe) error {
	// (a) install.type ↔ runtime.family coherence. Flavors skip —
	// their parent supplies install, so they may have an empty
	// Install.Type at this point in the pipeline.
	if r.ConfigFlavorOf == "" {
		if r.Install.Type == "" {
			return fmt.Errorf("install.type is required for non-flavor recipes")
		}
		want := map[string]string{
			"pip":      "python",
			"npm":      "node",
			"cargo":    "rust",
			"go_build": "go",
		}
		if fam, ok := want[r.Install.Type]; ok && r.Runtime.Family != fam {
			return fmt.Errorf("%w: install.type=%s requires runtime.family=%s, got %s",
				ErrInstallRuntimeMismatch, r.Install.Type, fam, r.Runtime.Family)
		}
	}

	// (b) every secret reference (auth.env values prefixed with
	// "secret:" and every auth.files[].secret) must be declared in
	// auth.secrets_schema. Catches typos that would otherwise render
	// an empty string at container-start time.
	declared := map[string]bool{}
	for _, s := range r.Auth.SecretsSchema {
		declared[s.Name] = true
	}
	for k, v := range r.Auth.Env {
		if strings.HasPrefix(v, "secret:") {
			name := strings.TrimPrefix(v, "secret:")
			if !declared[name] {
				return fmt.Errorf("%w: auth.env.%s references %q",
					ErrSecretRefMissingSchema, k, name)
			}
		}
	}
	for _, f := range r.Auth.Files {
		if !declared[f.Secret] {
			return fmt.Errorf("%w: auth.files references %q",
				ErrSecretRefMissingSchema, f.Secret)
		}
	}

	// (c) git_build → 40-char hex SHA. The schema already enforces this
	// when install.git is present, but we re-check defensively.
	if r.Install.Type == "git_build" {
		if r.Install.Git == nil || !sha40RE.MatchString(r.Install.Git.Rev) {
			return fmt.Errorf("install.git.rev must be 40-char hex")
		}
	}

	// (d) fifo mode needs a postAttachCommand so the session bridge has
	// a chance to verify FIFO readiness after the agent boots.
	if r.ChatIO.Mode == "fifo" && r.Lifecycle.PostAttachCommand == nil {
		return fmt.Errorf("chat_io.mode=fifo requires lifecycle.postAttachCommand to verify FIFO readiness")
	}

	// (e) exec_per_message mode needs a cmd_template — otherwise the
	// bridge has nothing to invoke.
	if r.ChatIO.Mode == "exec_per_message" {
		if r.ChatIO.ExecPerMessage == nil || len(r.ChatIO.ExecPerMessage.CmdTemplate) == 0 {
			return fmt.Errorf("chat_io.mode=exec_per_message requires chat_io.exec_per_message.cmd_template")
		}
	}

	return nil
}

// Get returns the recipe for the given ID. The returned pointer is
// read-only from the caller's perspective — Loader.Reload swaps the
// entire map on the next reload, so mutation would be lost and may
// race with a concurrent reload.
func (l *Loader) Get(id string) (*Recipe, bool) {
	l.mu.RLock()
	defer l.mu.RUnlock()
	r, ok := l.cache[id]
	return r, ok
}

// All returns a snapshot slice of every loaded recipe. The slice is a
// copy, but the *Recipe pointers inside are shared with the cache —
// same contract as Get.
func (l *Loader) All() []*Recipe {
	l.mu.RLock()
	defer l.mu.RUnlock()
	out := make([]*Recipe, 0, len(l.cache))
	for _, r := range l.cache {
		out = append(out, r)
	}
	return out
}

// Reload re-runs LoadAll. On success the cache is swapped atomically;
// on failure the previous cache is preserved (LoadAll never writes
// partial state).
func (l *Loader) Reload(ctx context.Context) error {
	return l.LoadAll(ctx)
}
