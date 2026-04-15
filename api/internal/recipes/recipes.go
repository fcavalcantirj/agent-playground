// Package recipes provides the ap.recipe/v1 YAML-backed recipe type,
// JSON Schema validator, filesystem loader, template registry,
// lifecycle hook normalizer, and catalog cache for the Agent
// Playground.
//
// This file previously held the Phase 2 LegacyRecipe hardcoded
// catalog (picoclaw + hermes) plus a GetLegacy accessor. Phase 02.5
// Plan 09 swapped the session handler onto the YAML-backed path and
// DELETED every legacy symbol in a single commit. The substance of
// this package now lives in:
//
//   - recipe.go    — the Recipe type and its sub-structs
//   - schema.go    — JSON Schema validator
//   - loader.go    — filesystem catalog loader with atomic reload
//   - template.go  — sandboxed text/template registry
//   - hook.go      — lifecycle hook normalizer + timeout resolver
//   - cache.go     — SIGHUP watcher + atomic cache swap
//
// No runtime code lives here. Kept as a package-doc anchor so
// `go doc ./internal/recipes` still has a useful landing comment.
package recipes
