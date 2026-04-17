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
	dev-frontend build-frontend lint-frontend install-frontend copy-schema \
	install-tools test lint-recipes check

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

# --- Phase 09: Python recipe tools (D-10, D-20) ---

install-tools:
	pip install -e "tools/[dev]"

test:
	pytest tools/tests/ -v

lint-recipes:
	python3 tools/run_recipe.py --lint-all

check: lint-recipes test

# ---------------------------------------------------------------
# Phase 19: API server (FastAPI at api_server/)
# ---------------------------------------------------------------
.PHONY: install-api test-api test-api-integration migrate-api dev-api \
        smoke-api smoke-api-live generate-ts-client check-api

install-api:
	pip install -e "api_server/[dev]"

test-api:
	cd api_server && pytest -q -m "not api_integration"

test-api-integration:
	cd api_server && pytest -m api_integration

migrate-api:
	cd api_server && alembic upgrade head

dev-api:
	cd api_server && AP_ENV=dev \
	  DATABASE_URL=postgresql+asyncpg://temporal:temporal@localhost:5432/agent_playground_api \
	  AP_RECIPES_DIR=../recipes \
	  uvicorn api_server.main:app --reload --port 8000

smoke-api:
	bash test/smoke-api.sh

smoke-api-live:
	API_BASE=https://api.agentplayground.dev bash test/smoke-api.sh --live

generate-ts-client:
	npx -y openapi-typescript "$${API_BASE:-http://localhost:8000}/openapi.json" \
	  -o /tmp/api-client.ts && npx -y typescript tsc --noEmit /tmp/api-client.ts \
	  && echo 'TS client valid'

check-api: test-api

# ---------------------------------------------------------------
# Phase 19: production-shaped local stack (Docker compose, prod image, prod compose)
#
# Brings up the SAME container topology that runs on Hetzner — postgres + api_server
# in containers, asyncpg pool over compose-internal networking, alembic migrations
# applied inside the api_server image. Caddy is intentionally skipped (TLS needs a
# real DNS name + ACME). Use this to catch Dockerfile / compose / env-file bugs
# locally before pushing to the box. Frontend (`make dev-frontend`) talks to the
# api_server through `frontend/next.config.mjs` rewrites.
#
#   make dev-api-local         # build + boot postgres + api_server, run alembic
#   make dev-api-local-logs    # follow api_server stdout
#   make dev-api-local-down    # stop + drop volume
#
# Tip: open a second terminal and run `make dev-frontend` so http://localhost:3000
# proxies through to the containerized API.
.PHONY: dev-api-local dev-api-local-logs dev-api-local-down

DEPLOY_COMPOSE := docker compose -f deploy/docker-compose.prod.yml -f deploy/docker-compose.local.yml --env-file deploy/.env.prod

dev-api-local:
	@if [ ! -s deploy/secrets/pg_password ]; then \
	  echo "[dev-api-local] generating deploy/secrets/pg_password (32 bytes hex)"; \
	  mkdir -p deploy/secrets; \
	  openssl rand -hex 32 > deploy/secrets/pg_password; \
	  chmod 600 deploy/secrets/pg_password; \
	fi
	@if [ ! -s deploy/.env.prod ]; then \
	  printf "POSTGRES_PASSWORD=%s\n" "$$(cat deploy/secrets/pg_password)" > deploy/.env.prod; \
	  chmod 600 deploy/.env.prod; \
	fi
	DOCKER_GID=999 $(DEPLOY_COMPOSE) build api_server
	$(DEPLOY_COMPOSE) up -d postgres
	@echo "[dev-api-local] waiting for postgres healthy"
	@for i in $$(seq 1 30); do \
	  if $(DEPLOY_COMPOSE) exec -T postgres pg_isready -U ap >/dev/null 2>&1; then break; fi; \
	  sleep 1; \
	done
	$(DEPLOY_COMPOSE) run --rm api_server alembic upgrade head
	$(DEPLOY_COMPOSE) up -d api_server
	@echo "[dev-api-local] waiting for /healthz"
	@for i in $$(seq 1 20); do \
	  if curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1; then \
	    echo "[dev-api-local] up — http://127.0.0.1:8000/healthz responding"; \
	    curl -s http://127.0.0.1:8000/readyz; echo; \
	    exit 0; \
	  fi; \
	  sleep 1; \
	done; \
	echo "[dev-api-local] FAILED — /healthz not responding"; \
	$(DEPLOY_COMPOSE) logs --tail 50 api_server; \
	exit 1

dev-api-local-logs:
	$(DEPLOY_COMPOSE) logs -f api_server

dev-api-local-down:
	$(DEPLOY_COMPOSE) down -v
