// Package handler's recipes.go implements the Phase 02.5 Plan 09
// public catalog endpoints:
//
//	GET /api/recipes         — list with optional filters
//	GET /api/recipes/:id     — single recipe detail
//
// Both endpoints return a public-metadata projection (RecipePublicView)
// — the full Recipe struct contains install/lifecycle/auth/isolation
// sub-blocks that MUST NOT leak over the API (threat T-02.5-02). The
// projection is an explicit allowlist: anything not in RecipePublicView
// simply does not reach the wire.
//
// Filter params (?family, ?tier, ?license, ?provider) are AND'd; any
// recipe matching ALL supplied filters is included. No filters = the
// whole catalog.
package handler

import (
	"net/http"
	"strings"

	"github.com/labstack/echo/v4"

	"github.com/agentplayground/api/internal/recipes"
)

// RecipeLoaderIface is the narrow subset of *recipes.Loader the
// handler consumes. Defining it as an interface lets recipes_test.go
// inject a pure in-memory fake without touching the filesystem.
//
// *recipes.Loader from Plan 01 satisfies this interface structurally
// via its All() and Get(id) methods.
type RecipeLoaderIface interface {
	All() []*recipes.Recipe
	Get(id string) (*recipes.Recipe, bool)
}

// RecipePublicView is the allowlisted projection of a Recipe for the
// public catalog endpoints. Fields NOT in this struct (install,
// lifecycle, auth, isolation, persistent_state, metadata) are NEVER
// serialized by GET /api/recipes — Plan 09's test suite asserts their
// JSON keys are absent from the response body.
type RecipePublicView struct {
	ID          string                  `json:"id"`
	Name        string                  `json:"name"`
	Description string                  `json:"description,omitempty"`
	License     string                  `json:"license,omitempty"`
	Category    string                  `json:"category,omitempty"`
	Runtime     RuntimePublicView       `json:"runtime"`
	Frontend    *recipes.RecipeFrontend `json:"frontend,omitempty"`
	PolicyFlags []string                `json:"policy_flags,omitempty"`
	TierBadge   string                  `json:"tier_badge,omitempty"`
	Providers   []ProviderPublicView    `json:"providers"`
	Models      []ModelPublicView       `json:"models"`
}

// RuntimePublicView exposes ONLY the runtime family — image tags,
// resource caps, and volume specs are internal implementation detail.
type RuntimePublicView struct {
	Family string `json:"family"`
}

// ProviderPublicView exposes ONLY the provider ID. API base URLs,
// auth styles, and env-var names are deployment-sensitive and stay
// server-side.
type ProviderPublicView struct {
	ID string `json:"id"`
}

// ModelPublicView exposes the model ID and its provider binding so
// the frontend can group models under providers. Token caps are
// tile-eligible metadata and can be added later without breaking the
// view.
type ModelPublicView struct {
	ID       string `json:"id"`
	Provider string `json:"provider"`
}

// ToPublicView projects a full Recipe onto the public view. This is
// the only function that decides which fields escape the API — if a
// future field is added to Recipe that should NOT leak, it lands here
// by default (absent) and only graduates to the view via a conscious
// plan decision.
func ToPublicView(r *recipes.Recipe) RecipePublicView {
	providers := make([]ProviderPublicView, 0, len(r.Providers))
	for _, p := range r.Providers {
		providers = append(providers, ProviderPublicView{ID: p.ID})
	}
	models := make([]ModelPublicView, 0, len(r.Models))
	for _, m := range r.Models {
		models = append(models, ModelPublicView{ID: m.ID, Provider: m.Provider})
	}
	var fe *recipes.RecipeFrontend
	if r.Frontend != (recipes.RecipeFrontend{}) {
		feCopy := r.Frontend
		fe = &feCopy
	}
	return RecipePublicView{
		ID:          r.ID,
		Name:        r.Name,
		Description: r.Description,
		License:     r.License,
		Category:    r.Category,
		Runtime:     RuntimePublicView{Family: r.Runtime.Family},
		Frontend:    fe,
		PolicyFlags: r.PolicyFlags,
		TierBadge:   r.TierBadge,
		Providers:   providers,
		Models:      models,
	}
}

// RegisterRecipesRoutes mounts GET /recipes and GET /recipes/:id on an
// already-authed Echo group. The caller (server.go) passes the same
// group /api/me lives on so Phase 1's auth middleware gates both.
//
// The loader argument is an interface so tests can inject a fake
// without touching the filesystem. Production passes *recipes.Loader
// from server.RecipeLoader().
func RegisterRecipesRoutes(g *echo.Group, loader RecipeLoaderIface) {
	if loader == nil {
		// Belt-and-suspenders: skip registration if the server didn't
		// wire a loader. Otherwise every GET would panic at All().
		return
	}
	g.GET("/recipes", func(c echo.Context) error {
		all := loader.All()
		filtered := filterRecipes(all, c)
		out := make([]RecipePublicView, 0, len(filtered))
		for _, r := range filtered {
			out = append(out, ToPublicView(r))
		}
		return c.JSON(http.StatusOK, out)
	})
	g.GET("/recipes/:id", func(c echo.Context) error {
		id := c.Param("id")
		r, ok := loader.Get(id)
		if !ok {
			return WriteError(c, http.StatusNotFound, ErrCodeRecipeNotFound, "recipe "+id+" not found")
		}
		return c.JSON(http.StatusOK, ToPublicView(r))
	})
}

// filterRecipes applies the four AND'd query-param filters in one
// linear pass. 02.5 ships two recipes total so a post-projection slice
// walk is fine; a future index map is Phase 4's concern if the catalog
// grows past ~100 entries.
func filterRecipes(all []*recipes.Recipe, c echo.Context) []*recipes.Recipe {
	family := c.QueryParam("family")
	tier := c.QueryParam("tier")
	license := c.QueryParam("license")
	provider := c.QueryParam("provider")

	out := make([]*recipes.Recipe, 0, len(all))
	for _, r := range all {
		if family != "" && r.Runtime.Family != family {
			continue
		}
		if tier != "" && r.Isolation.Tier != tier {
			continue
		}
		if license != "" && !strings.EqualFold(r.License, license) {
			continue
		}
		if provider != "" {
			found := false
			for _, p := range r.Providers {
				if p.ID == provider {
					found = true
					break
				}
			}
			if !found {
				continue
			}
		}
		out = append(out, r)
	}
	return out
}
