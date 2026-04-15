// Package recipes hosts two catalogs that COEXIST during Phase 02.5:
//
//  1. The Phase 2 hardcoded LegacyRecipe catalog (this file) — two
//     entries (picoclaw, hermes) that the Phase 2 session handler + bridge
//     still consume. Plan 09 of Phase 02.5 removes it once every caller
//     is swapped over to the YAML-backed Recipe type.
//  2. The Phase 02.5 YAML-backed Recipe + SchemaValidator + Loader
//     (recipe.go / schema.go / loader.go / cache.go) — the new substrate.
//     Plan 01 of Phase 02.5 introduced it without wiring any consumer.
//
// Cross-phase contract for legacy data: the Image tags below MUST match
// the outputs of Plan 02-03 (ap-picoclaw / ap-hermes) exactly. Any drift
// will cause session spawns to fail at the docker-pull step.
package recipes

import (
	"fmt"
	"strings"
	"time"
)

// LegacyAuthFile describes a recipe-specific auth artifact the session
// bridge must template with a BYOK key and bind-mount into a running
// container. Used when the agent binary inside the recipe image does NOT
// honor /run/secrets/<key> or env vars directly and instead reads auth
// from its own config file under $HOME.
//
// Example: picoclaw reads api_keys from ~/.picoclaw/.security.yml, NOT
// from ANTHROPIC_API_KEY env or /run/secrets/anthropic_key. The recipe
// declares an AuthFile so the handler can render a per-session
// .security.yml into the secrets dir and mount it at the expected path.
//
// Deprecated: Phase 02.5 Plan 09 will remove the hardcoded Phase 2
// catalog and drive auth-file rendering from RecipeAuth.Files in the
// YAML-backed Recipe type.
type LegacyAuthFile struct {
	// HostFilename is the leaf name the handler will write into the
	// per-session secrets directory (e.g. ".security.yml"). It is NOT a
	// full path; the handler prepends /tmp/ap/secrets/<session-id>/.
	HostFilename string
	// ContainerPath is the absolute path inside the container where the
	// file must appear (e.g. "/home/agent/.picoclaw/.security.yml").
	// Docker bind-mounts overlay even read-only rootfs at this point.
	ContainerPath string
	// Render produces the file's content for a given BYOK key. Each
	// recipe supplies its own template; picoclaw emits a .security.yml
	// with `api_keys: [<key>]` under the model entry.
	Render func(key string) string
}

// ChatIOMode selects how the session bridge layer talks to the in-container
// agent binary. FIFO = long-lived agent process whose stdin/stdout we tee
// through /run/ap/chat.{in,out}; Exec = the agent binary is invoked fresh
// per user message via `docker exec` and its stdout is returned verbatim.
//
// Note: these are Phase 2 Go constants, NOT the YAML-level chat_io.mode
// values (which are "fifo" / "exec_per_message" per D-10). The Phase 2
// catalog predates the schema and uses "stdin_fifo" as the FIFO value.
type ChatIOMode string

const (
	// ChatIOFIFO — picoclaw pattern. ap-base's entrypoint.sh launches the
	// agent with stdin/stdout redirected to the pre-opened FIFOs on
	// /run/ap/. The session bridge writes messages into chat.in and reads
	// replies from chat.out.
	ChatIOFIFO ChatIOMode = "stdin_fifo"

	// ChatIOExec — Hermes pattern. The container is up, but the agent
	// process is NOT long-lived; instead each chat message spawns a fresh
	// `hermes chat -q "<msg>"` via docker exec and captures its stdout.
	ChatIOExec ChatIOMode = "exec_per_message"
)

// ChatIO describes how messages flow to/from the agent binary inside the
// container. Only one of LaunchCmd (FIFO) or ExecCmd (Exec) is meaningful
// per recipe; the other is left empty.
//
// Phase 2 legacy type: the YAML-backed equivalent is RecipeChatIO in
// recipe.go. Both exist until Plan 02.5-09 cuts the legacy path.
type ChatIO struct {
	// Mode selects the bridge strategy.
	Mode ChatIOMode

	// LaunchCmd is the argv ap-base's entrypoint.sh uses as AP_AGENT_CMD
	// when Mode == ChatIOFIFO. The process runs under tmux in the chat
	// window with stdin/stdout wired to the FIFOs.
	LaunchCmd []string

	// ExecCmd is the argv the bridge passes to docker exec when
	// Mode == ChatIOExec. The user message is appended as the final argv
	// element at call time.
	ExecCmd []string

	// ResponseTimeout caps how long the bridge waits for a reply before
	// returning an error to the HTTP client.
	ResponseTimeout time.Duration
}

// ResourceOverrides let a recipe tighten or loosen the DefaultSandbox
// baseline for fields that are safe to tweak per recipe (Memory, CPUs,
// PidsLimit). Security knobs (CapDrop, ReadOnlyRootfs, NoNewPrivs) are
// intentionally NOT exposed here — the default is always strict.
type ResourceOverrides struct {
	// Memory in bytes. Zero means inherit DefaultSandbox.
	Memory int64
	// CPUs in nanoCPUs (1 vCPU = 1e9). Zero means inherit.
	CPUs int64
	// PidsLimit caps PID creation. Zero means inherit.
	PidsLimit int64
}

// LegacyRecipe is the Phase 2 hardcoded catalog entry shape. Phase 2
// ships two instances; Phase 02.5 Plan 01 introduced the YAML-backed
// Recipe type alongside this one, and Plan 02.5-09 removes the legacy
// path entirely once handlers are swapped over to the Loader.
//
// Deprecated: use the YAML-backed Recipe struct once Plan 02.5-09 lands.
type LegacyRecipe struct {
	// Name is the short key used in LegacyAllRecipes and the HTTP API payload.
	Name string

	// Image is the fully qualified tag produced by Plan 02-03's Dockerfile
	// overlays. Must NOT include a registry prefix in Phase 2 — the image
	// is built locally by `make build-recipes` and referenced by its
	// local tag.
	Image string

	// ChatIO describes the message bridge wiring.
	ChatIO ChatIO

	// RequiredSecrets lists the files that SecretWriter.Provision must
	// drop into /tmp/ap/secrets/<session_id>/ before the container starts.
	// Names here match filenames (no extension, no directory).
	RequiredSecrets []string

	// EnvOverrides are env vars injected into the container on top of
	// whatever the image bakes in. NEVER put raw secrets here — secrets
	// go through the bind-mounted /run/secrets/ path. This is for
	// non-sensitive config like "which provider" or "quiet mode".
	EnvOverrides map[string]string

	// SupportedProviders lists the model providers the recipe can drive.
	// Phase 2 every recipe supports "anthropic" and only anthropic.
	SupportedProviders []string

	// ModelFlag is the CLI flag the recipe's agent binary uses to accept a
	// model name (e.g. "--model" for picoclaw). The handler appends
	// `ModelFlag <user-chosen model>` to LaunchCmd (FIFO recipes) or
	// ExecCmd (Exec recipes) per session. Leave empty when the agent picks
	// its model from an env var via EnvOverrides + ModelEnvVar instead.
	ModelFlag string

	// ModelEnvVar is the env-var name the recipe's agent binary reads to
	// pick a model. The handler sets opts.Env[ModelEnvVar] = modelID per
	// session. Leave empty when the agent takes the model via ModelFlag.
	ModelEnvVar string

	// AgentAuthFiles are recipe-specific auth artifacts the session
	// bridge renders per-session and bind-mounts into the container.
	// Needed when the agent binary reads API keys from its own config
	// file (e.g. picoclaw's ~/.picoclaw/.security.yml) instead of env
	// vars or /run/secrets/. Empty for recipes whose agent honors
	// ANTHROPIC_API_KEY / OPENAI_API_KEY / etc. directly.
	AgentAuthFiles []LegacyAuthFile

	// ResourceOverrides optionally tightens DefaultSandbox resource caps.
	ResourceOverrides ResourceOverrides
}

// LegacyAllRecipes is the Phase 2 hardcoded catalog. Keys are the short
// names the API accepts in POST /api/sessions {"recipe": "picoclaw"}.
//
// Deprecated: consumers should migrate to the Loader catalog once
// Plan 02.5-09 swaps the session handler.
var LegacyAllRecipes = map[string]*LegacyRecipe{
	"picoclaw": {
		Name:  "picoclaw",
		Image: "ap-picoclaw:v0.1.0-c7461f9",
		ChatIO: ChatIO{
			Mode:            ChatIOFIFO,
			LaunchCmd:       []string{"picoclaw", "agent", "--session", "cli:default"},
			ResponseTimeout: 60 * time.Second,
		},
		RequiredSecrets:    []string{"anthropic_key"},
		EnvOverrides:       map[string]string{"PICOCLAW_PROVIDER": "anthropic"},
		SupportedProviders: []string{"anthropic"},
		ModelFlag:          "--model",
		// Picoclaw reads api_keys from ~/.picoclaw/.security.yml, indexed
		// by <model_name>:<index>. It does NOT honor ANTHROPIC_API_KEY or
		// /run/secrets/anthropic_key. Confirmed against sipeed/picoclaw
		// commit c7461f9 — pkg/config/config_struct.go#SecureModelList.
		AgentAuthFiles: []LegacyAuthFile{
			{
				HostFilename:  "picoclaw-security.yml",
				ContainerPath: "/home/agent/.picoclaw/.security.yml",
				Render:        renderPicoclawSecurityYAML,
			},
		},
	},
	"hermes": {
		Name:  "hermes",
		Image: "ap-hermes:v0.1.0-5621fc4",
		ChatIO: ChatIO{
			Mode:            ChatIOExec,
			ExecCmd:         []string{"hermes", "chat", "-q"},
			ResponseTimeout: 120 * time.Second,
		},
		RequiredSecrets: []string{"anthropic_key"},
		EnvOverrides: map[string]string{
			"HERMES_INFERENCE_PROVIDER": "anthropic",
			"HERMES_QUIET":              "1",
		},
		SupportedProviders: []string{"anthropic"},
		ModelFlag:          "--model",
		ResourceOverrides: ResourceOverrides{
			Memory: 2 << 30, // 2 GiB; Hermes's Python venv + chromium is heavier
		},
	},
}

// GetLegacy returns the Phase 2 legacy recipe for a given name, or nil
// if no such recipe exists. Callers should treat a nil return as a 404
// at the API layer.
//
// Deprecated: use Loader.Get once Plan 02.5-09 swaps the session handler.
func GetLegacy(name string) *LegacyRecipe {
	return LegacyAllRecipes[name]
}

// renderPicoclawSecurityYAML emits the .security.yml picoclaw reads at
// startup. Picoclaw indexes api_keys by "<model_name>:<index>"; ":0" is
// the first (and only) occurrence of each model. The key is quoted to
// survive YAML string escaping even though sk-ant- keys don't contain
// YAML metacharacters in practice. Models that are not in Phase 2's
// supported set get empty entries so picoclaw's loader still recognizes
// the schema version 2 pattern the baked config expects.
func renderPicoclawSecurityYAML(key string) string {
	// Escape any embedded double quotes defensively.
	escaped := strings.ReplaceAll(key, `"`, `\"`)
	return fmt.Sprintf(`channels:
  telegram: {}
model_list:
  claude-sonnet-4.6:0:
    api_keys:
      - "%s"
web:
  brave: {}
  tavily: {}
`, escaped)
}
