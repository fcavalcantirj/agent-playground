package recipes

// Recipe is the YAML-backed ap.recipe/v1 type. JSON tags ONLY —
// sigs.k8s.io/yaml round-trips through JSON so yaml tags are ignored and
// any mis-tagged field would silently become zero (see Pitfall 1 in
// 02.5-RESEARCH.md). Keep every sub-struct pure JSON.
//
// Phase 02.5 Plan 01 introduces this type alongside the Phase 2 hardcoded
// catalog (renamed to the unexported legacyRecipe + exported LegacyRecipe
// alias). Plan 09 of Phase 02.5 removes the legacy path once handlers are
// swapped over to the YAML loader.
type Recipe struct {
	ID              string           `json:"id"`
	Name            string           `json:"name"`
	Description     string           `json:"description,omitempty"`
	Version         string           `json:"version,omitempty"`
	License         string           `json:"license,omitempty"`
	Category        string           `json:"category,omitempty"`
	ConfigFlavorOf  string           `json:"config_flavor_of,omitempty"`
	Runtime         RecipeRuntime    `json:"runtime"`
	Install         RecipeInstall    `json:"install"`
	Lifecycle       RecipeLifecycle  `json:"lifecycle,omitempty"`
	Launch          RecipeLaunch     `json:"launch"`
	ChatIO          RecipeChatIO     `json:"chat_io"`
	Auth            RecipeAuth       `json:"auth,omitempty"`
	Providers       []RecipeProvider `json:"providers,omitempty"`
	Models          []RecipeModel    `json:"models,omitempty"`
	ModelFlag       string           `json:"model_flag,omitempty"`
	Isolation       RecipeIsolation  `json:"isolation"`
	PersistentState RecipePersistent `json:"persistent_state,omitempty"`
	Frontend        RecipeFrontend   `json:"frontend,omitempty"`
	PolicyFlags     []string         `json:"policy_flags,omitempty"`
	TierBadge       string           `json:"tier_badge,omitempty"`
	Metadata        RecipeMetadata   `json:"metadata,omitempty"`
}

// RecipeRuntime describes the base image family and resource defaults
// the container will boot with. `family` is a closed enum gating the
// Phase 02.5 base image catalog (python + node shipped; go/rust/zig
// accepted by schema as forward-compat per D-08).
type RecipeRuntime struct {
	Family    string          `json:"family"`
	Version   string          `json:"version,omitempty"`
	Image     string          `json:"image,omitempty"`
	Resources RecipeResources `json:"resources,omitempty"`
	Volumes   []any           `json:"volumes,omitempty"`
}

// RecipeResources is the runtime resource cap block. Zero values mean
// "inherit the sandbox default" and are handled downstream — they are
// NOT schema errors.
type RecipeResources struct {
	MemoryMiB int     `json:"memory_mib,omitempty"`
	CPUs      float64 `json:"cpus,omitempty"`
	PidsLimit int     `json:"pids_limit,omitempty"`
}

// RecipeInstall describes the agent install step. `type` is a closed
// enum. For git_build, install.git.rev must be a 40-char hex SHA
// (schema-enforced) to prevent drift between recipe versions.
type RecipeInstall struct {
	Type    string     `json:"type"`
	Package string     `json:"package,omitempty"`
	Version string     `json:"version,omitempty"`
	Git     *RecipeGit `json:"git,omitempty"`
}

// RecipeGit pins the repo URL + exact commit SHA + optional build
// command the loader will run inside the container during the install
// lifecycle. REC-07 requires the SHA pin.
type RecipeGit struct {
	Repo     string   `json:"repo"`
	Rev      string   `json:"rev"`
	BuildCmd []string `json:"build_cmd,omitempty"`
}

// RecipeLifecycle mirrors the Dev Containers hook set (v0.1 subset):
// each hook field is `any` because v0.1 accepts string | []string |
// [][]string. Plan 03 will introduce recipes.NormalizeHook(v) to reduce
// every shape to [][]string for dispatch.
type RecipeLifecycle struct {
	InitializeCommand    any    `json:"initializeCommand,omitempty"`
	OnCreateCommand      any    `json:"onCreateCommand,omitempty"`
	UpdateContentCommand any    `json:"updateContentCommand,omitempty"`
	PostCreateCommand    any    `json:"postCreateCommand,omitempty"`
	PostStartCommand     any    `json:"postStartCommand,omitempty"`
	PostAttachCommand    any    `json:"postAttachCommand,omitempty"`
	WaitFor              string `json:"waitFor,omitempty"`

	InitializeTimeoutSec    int `json:"initialize_timeout_sec,omitempty"`
	OnCreateTimeoutSec      int `json:"onCreate_timeout_sec,omitempty"`
	UpdateContentTimeoutSec int `json:"updateContent_timeout_sec,omitempty"`
	PostCreateTimeoutSec    int `json:"postCreate_timeout_sec,omitempty"`
	PostStartTimeoutSec     int `json:"postStart_timeout_sec,omitempty"`
	PostAttachTimeoutSec    int `json:"postAttach_timeout_sec,omitempty"`
}

// RecipeLaunch is the argv (exec form, never shell form) that the
// session bridge runs inside the container when the agent process is
// started. Using exec form sidesteps shell-injection for user-provided
// strings bound into env.
type RecipeLaunch struct {
	Cmd     []string          `json:"cmd"`
	Workdir string            `json:"workdir,omitempty"`
	Env     map[string]string `json:"env,omitempty"`
}

// RecipeChatIO selects how the session bridge talks to the agent
// process. v0.1 cut the mode set to exactly two entries per D-10 —
// fifo (long-lived process reading from named pipes) and exec_per_message
// (fresh docker exec per user turn).
type RecipeChatIO struct {
	Mode               string            `json:"mode"`
	ResponseTimeoutSec int               `json:"response_timeout_sec,omitempty"`
	FIFO               *RecipeChatIOFIFO `json:"fifo,omitempty"`
	ExecPerMessage     *RecipeChatIOExec `json:"exec_per_message,omitempty"`
}

// RecipeChatIOFIFO holds the FIFO-mode knobs. `strip_ansi` is common
// enough (picoclaw emits ANSI color codes by default) that it's
// first-class on the recipe.
type RecipeChatIOFIFO struct {
	FIFOIn    string `json:"fifo_in,omitempty"`
	FIFOOut   string `json:"fifo_out,omitempty"`
	StripANSI bool   `json:"strip_ansi,omitempty"`
}

// RecipeChatIOExec holds the exec-per-message mode template. The
// actual user message is appended by the bridge at invocation time;
// the template is NOT a string with `{msg}` placeholder — it is an
// argv that the bridge extends.
type RecipeChatIOExec struct {
	CmdTemplate    []string `json:"cmd_template,omitempty"`
	DockerExecUser string   `json:"docker_exec_user,omitempty"`
}

// RecipeAuth describes how the agent receives credentials. Env-var
// mode is the simplest path; secret_file_mount handles agents (like
// picoclaw) that require a specific config file at a specific path.
type RecipeAuth struct {
	Mechanism     string               `json:"mechanism,omitempty"`
	HeadlessSafe  bool                 `json:"headless_safe,omitempty"`
	Env           map[string]string    `json:"env,omitempty"`
	Files         []RecipeAuthFileDecl `json:"files,omitempty"`
	SecretsSchema []RecipeSecretDecl   `json:"secrets_schema,omitempty"`
}

// RecipeAuthFileDecl describes a secret-backed file the loader will
// template and mount at container start. `template` is the name of
// a Go text/template registered in the templates registry (Plan 02
// of Phase 02.5 — not this plan).
type RecipeAuthFileDecl struct {
	Secret   string `json:"secret"`
	Target   string `json:"target"`
	Mode     string `json:"mode,omitempty"`
	Template string `json:"template"`
}

// RecipeSecretDecl is the name of a secret the recipe consumes. The
// loader semantic check verifies every `secret:<name>` reference in
// auth.env or auth.files has a matching entry here.
type RecipeSecretDecl struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	Required    bool   `json:"required,omitempty"`
}

// RecipeProvider lists the upstream LLM providers the recipe can
// drive. Closed enum; adding a provider requires touching the schema.
type RecipeProvider struct {
	ID           string `json:"id"`
	APIBase      string `json:"api_base,omitempty"`
	APIKeyEnvVar string `json:"api_key_env_var,omitempty"`
	AuthStyle    string `json:"auth_style,omitempty"`
}

// RecipeModel is an individual model the recipe pins. The matrix
// smoke test (Phase 02.5 acceptance gate) iterates over this list.
type RecipeModel struct {
	ID              string `json:"id"`
	Provider        string `json:"provider"`
	MaxInputTokens  int    `json:"max_input_tokens,omitempty"`
	MaxOutputTokens int    `json:"max_output_tokens,omitempty"`
}

// RecipeIsolation exposes the sandbox knobs that are safe to tune per
// recipe. `tier` gates which OCI runtime the session picks (runc for
// strict/standard, sysbox-runc for sysbox). Security hardening defaults
// are applied downstream if these fields are zero.
type RecipeIsolation struct {
	Tier           string   `json:"tier"`
	CapDrop        []string `json:"cap_drop,omitempty"`
	CapAdd         []string `json:"cap_add,omitempty"`
	NoNewPrivs     bool     `json:"no_new_privs,omitempty"`
	ReadOnlyRootfs bool     `json:"read_only_rootfs,omitempty"`
}

// RecipePersistent holds tmpfs + volume declarations. v0.1 keeps
// volumes loosely typed because Phase 02.5 does not use them —
// Plan 05 of a later phase will lock the shape down.
type RecipePersistent struct {
	Tmpfs   []RecipeTmpfs `json:"tmpfs,omitempty"`
	Volumes []any         `json:"volumes,omitempty"`
}

// RecipeTmpfs is a single tmpfs mount request.
type RecipeTmpfs struct {
	Path    string `json:"path"`
	SizeMiB int    `json:"size_mib,omitempty"`
}

// RecipeFrontend is the tile copy the Next.js catalog uses. No
// behavior hangs off these fields; they are plumbing only.
type RecipeFrontend struct {
	DisplayName   string `json:"display_name,omitempty"`
	Slug          string `json:"slug,omitempty"`
	Icon          string `json:"icon,omitempty"`
	CategoryBadge string `json:"category_badge,omitempty"`
	Tooltip       string `json:"tooltip,omitempty"`
	TierBadge     string `json:"tier_badge,omitempty"`
}

// RecipeMetadata records provenance. `source_sha` matches the schema's
// 40-char hex pattern so the bootstrap flow in Phase 8 can stamp it
// automatically when it snapshots a community recipe.
type RecipeMetadata struct {
	SourceRepo         string `json:"source_repo,omitempty"`
	SourceSHA          string `json:"source_sha,omitempty"`
	LastVerified       string `json:"last_verified,omitempty"`
	BootstrapGenerated bool   `json:"bootstrap_generated,omitempty"`
}
