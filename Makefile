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

.PHONY: build-ap-base build-picoclaw build-hermes build-recipes clean-recipes smoke-test

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

smoke-test:
	@if [ -z "$$AP_DEV_BYOK_KEY" ]; then \
		echo "SKIPPED: AP_DEV_BYOK_KEY not set (set to a real Anthropic key to run the live smoke test)"; \
		exit 0; \
	fi
	bash scripts/smoke-e2e.sh picoclaw
	bash scripts/smoke-e2e.sh hermes
