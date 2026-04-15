package session

import (
	"context"
	"fmt"
	"strings"

	"github.com/agentplayground/api/internal/recipes"
)

// TemplateRenderer is the minimum surface Materialize needs from the
// recipes.TemplateRegistry type produced by Phase 02.5 Plan 02.
//
// Defining it as an interface here (instead of hard-importing the
// concrete type) lets the session package compile and test in
// isolation while Plan 02's TemplateRegistry lands in parallel. The
// concrete *recipes.TemplateRegistry naturally satisfies this shape
// because its Render signature is structurally identical — when the
// two worktrees merge, server.WithTemplateRegistry accepts the
// concrete pointer without a cast because Go interfaces are
// implicit.
type TemplateRenderer interface {
	Render(ctx context.Context, recipeID, name string, data any) (string, error)
}

// MaterializedRecipe is the bundle a session handler needs to launch
// a container for a given (recipe, provider, model) triple. Every
// secret reference has been resolved; every auth.files template has
// been rendered. The handler is responsible for writing each
// MaterializedFile to per-session host tmpfs (/tmp/ap/secrets/<id>/)
// and bind-mounting the directory read-only into the container at
// /run/secrets so the existing ap-base entrypoint shim (Phase 2) can
// copy each file to its declared auth.files[].target path.
//
// THREAT NOTE (T-02.5-02): MaterializedRecipe holds decrypted secret
// values in-memory for the lifetime of the handler call. It MUST NOT
// be logged, stored in Redis, or returned over the HTTP API. The
// handler discards it as soon as the container is started.
type MaterializedRecipe struct {
	Recipe *recipes.Recipe
	// Env is the resolved auth.env map. Values that were `secret:<name>`
	// in the recipe manifest are replaced with the literal secret; plain
	// literal values pass through unchanged.
	Env map[string]string
	// Files is the rendered auth.files set, one entry per
	// recipe.Auth.Files declaration. Order matches the manifest order.
	Files []MaterializedFile
}

// MaterializedFile is a single rendered auth.files entry. Body holds
// the template output (not a path — the caller writes the bytes).
type MaterializedFile struct {
	Target string // container path, e.g. /home/agent/.picoclaw/.security.yml
	Mode   string // octal string, e.g. "0600"
	Body   string // rendered template output
}

// Materialize walks a recipe's auth block, resolves every secret ref,
// renders every auth.files template, and returns the bundle the
// handler feeds into RunWithLifecycle.
//
// Parameters:
//   - ctx:       request context; propagated to template render for cancellation.
//   - recipe:    the fully validated recipe (Plan 01 Loader output).
//   - provider:  the LLM provider ID the user picked (must exist in recipe.Providers if non-empty).
//   - modelID:   the model ID the user picked; currently unused by Materialize but reserved for future provider-aware routing.
//   - secrets:   the SecretSource backing Resolve (DevEnvSecretSource in Phase 02.5, pgcrypto vault in Phase 3).
//   - templates: the TemplateRenderer that owns the sandboxed text/template registry.
//
// Errors:
//   - ErrSecretMissing wrapped with the env key or file secret name that could not be resolved.
//   - Template render errors wrapped with the recipe ID + template name.
//   - "provider %q not declared by recipe %q" when a non-empty provider argument is not listed in recipe.Providers.
//
// Error messages NEVER include resolved secret values — they reference
// field names and recipe IDs only. This is enforced by code review
// (threat model T-02.5-02b) and grep-guarded by the plan's verification.
func Materialize(
	ctx context.Context,
	recipe *recipes.Recipe,
	provider, modelID string,
	secrets SecretSource,
	templates TemplateRenderer,
) (*MaterializedRecipe, error) {
	if recipe == nil {
		return nil, fmt.Errorf("materialize: nil recipe")
	}
	if secrets == nil {
		return nil, fmt.Errorf("materialize: nil SecretSource for recipe %q", recipe.ID)
	}

	// 1. Validate provider first — fail fast before touching the vault.
	if provider != "" {
		found := false
		for _, p := range recipe.Providers {
			if p.ID == provider {
				found = true
				break
			}
		}
		if !found {
			return nil, fmt.Errorf("materialize: provider %q not declared by recipe %q", provider, recipe.ID)
		}
	}

	// 2. Resolve auth.env entries. Values may be literal or "secret:<name>".
	envOut := make(map[string]string, len(recipe.Auth.Env))
	for k, v := range recipe.Auth.Env {
		resolved, err := secrets.Resolve(v)
		if err != nil {
			return nil, fmt.Errorf("materialize env %q (recipe %q): %w", k, recipe.ID, err)
		}
		envOut[k] = resolved
	}

	// 3. Resolve auth.files secrets into the template context map.
	//    - Key the resolved value by BOTH the original name and the
	//      underscore-normalized name so templates can write
	//      {{ .secrets.anthropic_api_key }} or
	//      {{ index .secrets "anthropic-api-key" }} interchangeably.
	//    - text/template's default field-access tokenizer rejects
	//      hyphens, so the underscore form is the recommended style.
	secretCtx := make(map[string]string)
	for _, f := range recipe.Auth.Files {
		resolved, err := secrets.Resolve("secret:" + f.Secret)
		if err != nil {
			return nil, fmt.Errorf("materialize file secret %q (recipe %q): %w", f.Secret, recipe.ID, err)
		}
		secretCtx[underscoreName(f.Secret)] = resolved
		secretCtx[f.Secret] = resolved
	}
	// Expose resolved env values under secrets.<envkey-lowercased> for
	// templates that only declared the secret via auth.env (no auth.files
	// entry). This keeps security.yml templates terse.
	for k, v := range envOut {
		secretCtx[underscoreName(strings.ToLower(k))] = v
	}

	// 4. Render every auth.files template.
	data := map[string]any{
		"secrets": secretCtx,
		"env":     envOut,
		"recipe":  recipe,
	}

	if templates == nil && len(recipe.Auth.Files) > 0 {
		return nil, fmt.Errorf("materialize: templates required but TemplateRenderer is nil (recipe %q)", recipe.ID)
	}

	var files []MaterializedFile
	for _, f := range recipe.Auth.Files {
		body, err := templates.Render(ctx, recipe.ID, f.Template, data)
		if err != nil {
			return nil, fmt.Errorf("materialize render %s/%s: %w", recipe.ID, f.Template, err)
		}
		mode := f.Mode
		if mode == "" {
			mode = "0600"
		}
		files = append(files, MaterializedFile{
			Target: f.Target,
			Mode:   mode,
			Body:   body,
		})
	}

	return &MaterializedRecipe{
		Recipe: recipe,
		Env:    envOut,
		Files:  files,
	}, nil
}

// underscoreName converts "anthropic-api-key" → "anthropic_api_key".
// text/template's default field-access tokenizer does not accept
// hyphens, so templates must use the underscore form when writing
// {{ .secrets.<name> }}. Materialize normalizes both ways.
func underscoreName(s string) string {
	return strings.ReplaceAll(s, "-", "_")
}
