# Agent Playground — Phase 2 build targets.
# Pre-builds the ap-base image and the two recipe overlays so POST /api/sessions
# never has to docker-build at session-start time (D-17).

AP_BASE_TAG := ap-base:v0.1.0
PICOCLAW_TAG := ap-picoclaw:v0.1.0-c7461f9
HERMES_TAG := ap-hermes:v0.1.0-5621fc4

# Auto-detect ttyd release arch to match the local Docker build platform.
# Hetzner prod is amd64 (x86_64); Apple Silicon dev boxes are aarch64.
# ttyd publishes ttyd.x86_64 / ttyd.aarch64 / ttyd.arm / ttyd.mips.
UNAME_M := $(shell uname -m)
ifeq ($(UNAME_M),arm64)
	TTYD_ARCH := aarch64
else ifeq ($(UNAME_M),aarch64)
	TTYD_ARCH := aarch64
else
	TTYD_ARCH := x86_64
endif

PICOCLAW_SHA := c7461f9e963496c4471336642ac6a8d91a456978
HERMES_SHA := 5621fc449a7c00f11168328c87e024a0203792c3

.PHONY: build-ap-base build-picoclaw build-hermes build-recipes clean-recipes smoke-test \
	dev-frontend build-frontend lint-frontend install-frontend copy-schema

# copy-schema keeps the canonical Draft 2019-09 recipe schema in
# agents/schemas/ byte-identical to the embedded copy under
# api/internal/recipes/schema/. The Go loader uses //go:embed on the
# api/ copy because //go:embed cannot cross the api/ module boundary.
# Run this target after editing agents/schemas/recipe.schema.json, and
# CI should fail if the two files drift.
copy-schema:
	@mkdir -p api/internal/recipes/schema
	@cp agents/schemas/recipe.schema.json api/internal/recipes/schema/recipe.schema.json
	@diff -q agents/schemas/recipe.schema.json api/internal/recipes/schema/recipe.schema.json

build-ap-base:
	docker build -t $(AP_BASE_TAG) deploy/ap-base/

build-picoclaw: build-ap-base
	docker build \
		--build-arg PICOCLAW_SHA=$(PICOCLAW_SHA) \
		-t $(PICOCLAW_TAG) \
		agents/picoclaw/

build-hermes: build-ap-base
	docker build \
		--build-arg HERMES_SHA=$(HERMES_SHA) \
		-t $(HERMES_TAG) \
		agents/hermes/

build-recipes: build-ap-base build-picoclaw build-hermes
	@echo "Built: $(AP_BASE_TAG) $(PICOCLAW_TAG) $(HERMES_TAG)"

clean-recipes:
	-docker rmi $(PICOCLAW_TAG) $(HERMES_TAG) $(AP_BASE_TAG)

# --- Phase 02.5 runtime base images (D-18..D-23) ---
# 2 of the 5 planned language families; go/rust/zig deferred to Phase 4
# along with their consuming recipes. Each runtime base is a thin overlay
# on ap-base that adds ONLY the language toolchain — tini, tmux, ttyd,
# gosu, and the entrypoint shim are all inherited unchanged.
AP_RUNTIME_PYTHON_TAG := ap-runtime-python:v0.1.0-3.13
AP_RUNTIME_NODE_TAG   := ap-runtime-node:v0.1.0-22

.PHONY: build-runtime-python build-runtime-node build-runtimes clean-runtimes

build-runtime-python: build-ap-base
	docker build -t $(AP_RUNTIME_PYTHON_TAG) deploy/ap-runtime-python/

build-runtime-node: build-ap-base
	docker build -t $(AP_RUNTIME_NODE_TAG) deploy/ap-runtime-node/

build-runtimes: build-runtime-python build-runtime-node
	@echo "Built runtimes: $(AP_RUNTIME_PYTHON_TAG) $(AP_RUNTIME_NODE_TAG)"
	@docker images --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}' | grep -E 'ap-base|ap-runtime-'

clean-runtimes:
	-docker rmi $(AP_RUNTIME_PYTHON_TAG) $(AP_RUNTIME_NODE_TAG)

smoke-test:
	@if [ -z "$$AP_DEV_BYOK_KEY" ]; then \
		echo "SKIPPED: AP_DEV_BYOK_KEY not set (set to a real Anthropic key to run the live smoke test)"; \
		exit 0; \
	fi
	bash scripts/smoke-e2e.sh picoclaw
	bash scripts/smoke-e2e.sh hermes

# --- Frontend targets (Phase 3+) ---
# frontend/ is the v0-authored marketing + dashboard tree with auth
# logic ported from the legacy web/. The targets shell into that
# directory and delegate to pnpm — the rest of the repo never imports
# any Next.js build internals, so Makefile stays backend-first.
install-frontend:
	cd frontend && pnpm install

dev-frontend:
	cd frontend && pnpm dev

build-frontend:
	cd frontend && pnpm build

lint-frontend:
	cd frontend && pnpm lint
