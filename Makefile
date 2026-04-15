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
AP_RUNTIME_PYTHON_TAG      := ap-runtime-python:v0.1.0-3.13
AP_RUNTIME_PYTHON_312_TAG  := ap-runtime-python:v0.1.0-3.12
AP_RUNTIME_NODE_TAG        := ap-runtime-node:v0.1.0-22

.PHONY: build-runtime-python build-runtime-python-3.12 build-runtime-node build-runtimes clean-runtimes

build-runtime-python: build-ap-base
	docker build -t $(AP_RUNTIME_PYTHON_TAG) deploy/ap-runtime-python/

build-runtime-python-3.12: build-ap-base
	docker build -t $(AP_RUNTIME_PYTHON_312_TAG) deploy/ap-runtime-python-3.12/

build-runtime-node: build-ap-base
	docker build -t $(AP_RUNTIME_NODE_TAG) deploy/ap-runtime-node/

build-runtimes: build-runtime-python build-runtime-python-3.12 build-runtime-node
	@echo "Built runtimes: $(AP_RUNTIME_PYTHON_TAG) $(AP_RUNTIME_PYTHON_312_TAG) $(AP_RUNTIME_NODE_TAG)"
	@docker images --format 'table {{.Repository}}:{{.Tag}}\t{{.Size}}' | grep -E 'ap-base|ap-runtime-'

clean-runtimes:
	-docker rmi $(AP_RUNTIME_PYTHON_TAG) $(AP_RUNTIME_PYTHON_312_TAG) $(AP_RUNTIME_NODE_TAG)

# --- Phase 02.5 Gate A smoke-test matrix (D-46, D-47) ---
# Runs the 2x2 matrix ({aider,picoclaw} x {anthropic,openrouter}) against a
# live API server. The server must already be running — this target does
# NOT start it (concurrency complexity; deferred to Plan 11 if useful).
#
# Operator workflow (two terminals):
#
#   # Terminal 1: start the API
#   cd api && \
#     AP_DEV_MODE=true \
#     AP_SESSION_SECRET=test-secret-that-is-at-least-32-characters-long \
#     AP_DEV_BYOK_KEY=sk-ant-... \
#     AP_DEV_OPENROUTER_KEY=sk-or-v1-... \
#     DATABASE_URL=postgres://temporal:temporal@localhost:5432/agent_playground?sslmode=disable \
#     REDIS_URL=redis://localhost:6379 \
#     API_PORT=8080 \
#     go run ./cmd/server/
#
#   # Terminal 2: run the matrix
#   make smoke-test-matrix
API_URL ?= http://127.0.0.1:8080

.PHONY: smoke-test-matrix

smoke-test-matrix:
	@echo "Gate A: smoke-test matrix"
	@echo "Prereqs:"
	@echo "  - API server running at $(API_URL) (cd api && AP_DEV_MODE=true go run ./cmd/server/)"
	@echo "  - AP_DEV_BYOK_KEY set (Anthropic)"
	@echo "  - AP_DEV_OPENROUTER_KEY set (OpenRouter)"
	@echo "  - ap-runtime-python + ap-runtime-node images built (make build-runtimes)"
	@echo "  - ap-aider + ap-picoclaw images built (agents/*/Dockerfile)"
	@echo
	@API_URL=$(API_URL) bash test/smoke-matrix.sh

# --- Phase 02.5 Gate B architectural drop-in test (D-01b, D-50a..d) ---
# Runs test/drop-in.sh against a target recipe the operator has hand-written
# under agents/<TARGET>/ (pure directory add, zero substrate edits).
#
# Usage:
#   make test-architectural-drop-in                # default: null-echo (D-50d synthetic fallback)
#   make test-architectural-drop-in TARGET=openclaw
#
# Protocol (D-50b):
#   1. Operator hand-writes agents/$(TARGET)/recipe.yaml + optional templates/*.tmpl
#      + optional Dockerfile using only the locked v0.1 schema
#   2. Operator must NOT edit api/, agents/schemas/, Makefile (D-50c)
#   3. OPTIONAL escape hatch: new deploy/ap-runtime-<family>/Dockerfile if the
#      target needs a language family no runtime base exists for yet
#   4. This target invokes test/drop-in.sh which enforces D-50c via git diff,
#      SIGHUPs the running API server, then re-runs the Gate A matrix with
#      the new recipe appended. Gate B passes when all non-SKIP cells pass
#      and zero substrate edits occurred.
TARGET ?= null-echo

.PHONY: test-architectural-drop-in

test-architectural-drop-in:
	@echo "Gate B: architectural drop-in test (D-01b / D-50a..d)"
	@echo "Target:        $(TARGET)"
	@echo "Protocol (D-50b):"
	@echo "  1. agents/$(TARGET)/recipe.yaml must already exist (hand-written by operator)"
	@echo "  2. DO NOT edit api/, agents/schemas/, Makefile (D-50c); the script enforces this"
	@echo "  3. OPTIONAL: new deploy/ap-runtime-<family>/Dockerfile is the ONLY allowed escape hatch"
	@echo "  4. API server must be running at $(API_URL); this target SIGHUPs it to reload"
	@echo
	@API_URL=$(API_URL) bash test/drop-in.sh $(TARGET)

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
