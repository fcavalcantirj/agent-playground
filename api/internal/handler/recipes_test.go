package handler_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/labstack/echo/v4"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/agentplayground/api/internal/handler"
	"github.com/agentplayground/api/internal/recipes"
)

// fakeLoader is the in-memory RecipeLoaderIface the recipes-handler
// tests inject. Keyed by ID so Get is O(1); All walks the map.
type fakeLoader struct {
	recipes map[string]*recipes.Recipe
}

func (f *fakeLoader) All() []*recipes.Recipe {
	out := make([]*recipes.Recipe, 0, len(f.recipes))
	for _, r := range f.recipes {
		out = append(out, r)
	}
	return out
}

func (f *fakeLoader) Get(id string) (*recipes.Recipe, bool) {
	r, ok := f.recipes[id]
	return r, ok
}

// newTestLoader wires two canned recipes mirroring the Phase 02.5
// reference catalog: aider (python family, 2 providers) and picoclaw
// (node family, 1 provider). Tests assert filter semantics against
// this shape.
func newTestLoader() *fakeLoader {
	return &fakeLoader{
		recipes: map[string]*recipes.Recipe{
			"aider": {
				ID:          "aider",
				Name:        "Aider",
				Description: "AI pair programmer",
				License:     "Apache-2.0",
				Category:    "code-assistant",
				Runtime:     recipes.RecipeRuntime{Family: "python", Image: "ap-runtime-python:test"},
				Install:     recipes.RecipeInstall{Type: "pip", Package: "aider-chat"},
				Launch:      recipes.RecipeLaunch{Cmd: []string{"aider"}},
				ChatIO:      recipes.RecipeChatIO{Mode: "exec_per_message"},
				Auth: recipes.RecipeAuth{
					Mechanism: "env_var",
					Env: map[string]string{
						"ANTHROPIC_API_KEY":  "secret:anthropic-api-key",
						"OPENROUTER_API_KEY": "secret:openrouter-api-key",
					},
				},
				Providers: []recipes.RecipeProvider{
					{ID: "anthropic", APIBase: "https://api.anthropic.com/v1"},
					{ID: "openrouter", APIBase: "https://openrouter.ai/api/v1"},
				},
				Models: []recipes.RecipeModel{
					{ID: "claude-haiku-test", Provider: "anthropic"},
					{ID: "openrouter/auto", Provider: "openrouter"},
				},
				Isolation: recipes.RecipeIsolation{Tier: "strict"},
				Frontend:  recipes.RecipeFrontend{DisplayName: "Aider", Slug: "aider"},
			},
			"picoclaw": {
				ID:          "picoclaw",
				Name:        "PicoClaw",
				Description: "Minimal Claude agent",
				License:     "MIT",
				Category:    "general",
				Runtime:     recipes.RecipeRuntime{Family: "node", Image: "ap-runtime-node:test"},
				Install:     recipes.RecipeInstall{Type: "npm", Package: "picoclaw"},
				Launch:      recipes.RecipeLaunch{Cmd: []string{"picoclaw"}},
				ChatIO:      recipes.RecipeChatIO{Mode: "fifo"},
				Auth: recipes.RecipeAuth{
					Mechanism: "env_var",
					Env: map[string]string{
						"ANTHROPIC_API_KEY": "secret:anthropic-api-key",
					},
				},
				Providers: []recipes.RecipeProvider{
					{ID: "anthropic", APIBase: "https://api.anthropic.com/v1"},
				},
				Models: []recipes.RecipeModel{
					{ID: "claude-sonnet-test", Provider: "anthropic"},
				},
				Isolation: recipes.RecipeIsolation{Tier: "standard"},
			},
		},
	}
}

// mountRecipesRoutes builds an Echo instance with the Plan 09 recipes
// routes mounted on an /api group (no auth — tests only exercise the
// public projection + filter logic).
func mountRecipesRoutes(t *testing.T, loader handler.RecipeLoaderIface) *echo.Echo {
	t.Helper()
	e := echo.New()
	e.HideBanner = true
	g := e.Group("/api")
	handler.RegisterRecipesRoutes(g, loader)
	return e
}

func doGET(t *testing.T, e *echo.Echo, path string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(http.MethodGet, path, nil)
	rec := httptest.NewRecorder()
	e.ServeHTTP(rec, req)
	return rec
}

func TestRecipesList_All(t *testing.T) {
	e := mountRecipesRoutes(t, newTestLoader())
	rec := doGET(t, e, "/api/recipes")
	require.Equal(t, http.StatusOK, rec.Code, "body=%s", rec.Body.String())

	var list []map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &list))
	assert.Len(t, list, 2)

	ids := map[string]bool{}
	for _, r := range list {
		ids[r["id"].(string)] = true
	}
	assert.True(t, ids["aider"], "aider must be present")
	assert.True(t, ids["picoclaw"], "picoclaw must be present")
}

func TestRecipesList_FilterFamily(t *testing.T) {
	e := mountRecipesRoutes(t, newTestLoader())
	rec := doGET(t, e, "/api/recipes?family=python")
	require.Equal(t, http.StatusOK, rec.Code)

	var list []map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &list))
	require.Len(t, list, 1)
	assert.Equal(t, "aider", list[0]["id"])
}

func TestRecipesList_FilterProvider(t *testing.T) {
	e := mountRecipesRoutes(t, newTestLoader())
	rec := doGET(t, e, "/api/recipes?provider=openrouter")
	require.Equal(t, http.StatusOK, rec.Code)

	var list []map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &list))
	require.Len(t, list, 1)
	assert.Equal(t, "aider", list[0]["id"])
}

func TestRecipesList_FilterTier(t *testing.T) {
	e := mountRecipesRoutes(t, newTestLoader())
	rec := doGET(t, e, "/api/recipes?tier=strict")
	require.Equal(t, http.StatusOK, rec.Code)

	var list []map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &list))
	require.Len(t, list, 1)
	assert.Equal(t, "aider", list[0]["id"])
}

func TestRecipesList_FilterLicense(t *testing.T) {
	e := mountRecipesRoutes(t, newTestLoader())
	rec := doGET(t, e, "/api/recipes?license=mit")
	require.Equal(t, http.StatusOK, rec.Code)

	var list []map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &list))
	require.Len(t, list, 1)
	assert.Equal(t, "picoclaw", list[0]["id"])
}

func TestRecipesList_NoMatch(t *testing.T) {
	e := mountRecipesRoutes(t, newTestLoader())
	rec := doGET(t, e, "/api/recipes?family=rust")
	require.Equal(t, http.StatusOK, rec.Code)
	assert.Equal(t, "[]\n", rec.Body.String())
}

func TestRecipesGet_Found(t *testing.T) {
	e := mountRecipesRoutes(t, newTestLoader())
	rec := doGET(t, e, "/api/recipes/aider")
	require.Equal(t, http.StatusOK, rec.Code)

	var view map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &view))
	assert.Equal(t, "aider", view["id"])
	assert.Equal(t, "Aider", view["name"])
	// Runtime should be the projected sub-object exposing only family.
	runtime, ok := view["runtime"].(map[string]any)
	require.True(t, ok)
	assert.Equal(t, "python", runtime["family"])
	_, hasImage := runtime["image"]
	assert.False(t, hasImage, "runtime.image must not leak")
}

func TestRecipesGet_NotFound(t *testing.T) {
	e := mountRecipesRoutes(t, newTestLoader())
	rec := doGET(t, e, "/api/recipes/nosuch")
	require.Equal(t, http.StatusNotFound, rec.Code)

	var env map[string]any
	require.NoError(t, json.Unmarshal(rec.Body.Bytes(), &env))
	errObj, ok := env["error"].(map[string]any)
	require.True(t, ok, "error envelope must be object: %s", rec.Body.String())
	assert.Equal(t, handler.ErrCodeRecipeNotFound, errObj["code"])
}

// TestRecipesList_NoLifecycleLeak verifies the public projection does
// NOT include lifecycle / install / auth / isolation / metadata JSON
// keys. Threat model T-02.5-02 mitigation — if this test fails, a
// recipe field that should be server-only has escaped to the API.
func TestRecipesList_NoLifecycleLeak(t *testing.T) {
	e := mountRecipesRoutes(t, newTestLoader())
	rec := doGET(t, e, "/api/recipes")
	require.Equal(t, http.StatusOK, rec.Code)

	body := rec.Body.String()
	forbidden := []string{
		`"lifecycle"`,
		`"install"`,
		`"auth"`,
		`"isolation"`,
		`"persistent_state"`,
		`"metadata"`,
	}
	for _, k := range forbidden {
		assert.NotContains(t, body, k, "public view must NOT contain %s key", k)
	}
}

func TestRecipesList_NilLoader(t *testing.T) {
	// A nil loader must not register routes — GET /api/recipes should
	// return 404 (Echo's "no route" response), not panic at All().
	e := mountRecipesRoutes(t, nil)
	rec := doGET(t, e, "/api/recipes")
	assert.Equal(t, http.StatusNotFound, rec.Code)
}
