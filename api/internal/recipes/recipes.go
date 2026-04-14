// Package recipes is the Phase 2 hardcoded recipe catalog. Phase 4 replaces
// this with a DB/file-backed registry; Phase 2 ships exactly two entries so
// the session spawn path has concrete targets to point at.
//
// Cross-phase contract: the Image tags below MUST match the outputs of Plan
// 02-03 (ap-picoclaw / ap-hermes) exactly. Any drift will cause session
// spawns to fail at the docker-pull step.
package recipes

import (
	"fmt"
	"strings"
	"time"
)

// AuthFile describes a recipe-specific auth artifact the session bridge
// must template with a BYOK key and bind-mount into a running container.
// Used when the agent binary inside the recipe image does NOT honor
// /run/secrets/<key> or env vars directly and instead reads auth from
// its own config file under $HOME.
//
// Example: picoclaw reads api_keys from ~/.picoclaw/.security.yml, NOT
// from ANTHROPIC_API_KEY env or /run/secrets/anthropic_key. The recipe
// declares an AuthFile so the handler can render a per-session
// .security.yml into the secrets dir and mount it at the expected path.
type AuthFile struct {
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

// Recipe is a single catalog entry. Phase 2 has two of these hardcoded.
type Recipe struct {
	// Name is the short key used in AllRecipes and the HTTP API payload.
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
	AgentAuthFiles []AuthFile

	// ResourceOverrides optionally tightens DefaultSandbox resource caps.
	ResourceOverrides ResourceOverrides
}

// AllRecipes is the Phase 2 hardcoded catalog. Keys are the short names
// the API accepts in POST /api/sessions {"recipe": "picoclaw"}.
var AllRecipes = map[string]*Recipe{
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
		AgentAuthFiles: []AuthFile{
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

// Get returns the recipe for a given name, or nil if no such recipe exists.
// Callers should treat a nil return as a 404 at the API layer.
func Get(name string) *Recipe {
	return AllRecipes[name]
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
