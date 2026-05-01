.PHONY: e2e-inapp e2e-inapp-docker

e2e-inapp:  ## Phase 22c.3 SC-03 5-recipe end-to-end inapp gate; requires OPENROUTER_API_KEY.
	@test -n "$$OPENROUTER_API_KEY" || (echo "ERROR: OPENROUTER_API_KEY not set in env" && exit 1)
	@for img in hermes nanobot openclaw nullclaw zeroclaw; do \
		docker image inspect ap-recipe-$$img:latest >/dev/null 2>&1 || \
			(echo "ERROR: missing image ap-recipe-$$img:latest — run tools/run_recipe.py first" && exit 1); \
	done
	uv run pytest tests/e2e/test_inapp_5x5_matrix.py -v --tb=short -m api_integration
	@echo "---"
	@echo "Report: api_server/tests/e2e/e2e-report.json"
	@cat tests/e2e/e2e-report.json | python3 -c "import json,sys; r=json.load(sys.stdin); assert r['passed'], 'GATE FAIL'; print('GATE PASS — 5/5 cells')"

# Phase 22c.3.1-01-AC01 dockerized e2e harness — closes the macOS Docker
# Desktop bridge-IP unreachability blocker by running the pytest process
# INSIDE a container that shares the docker default `bridge` network with
# the recipe containers spawned by the route handler. Test/prod parity
# preserved (production = container→container via bridge IP; test now too).
# Linux CI can keep using the regular `make e2e-inapp` target — this is
# the macOS parity path, not a replacement.
#
# Network design:
#   * tools/run_recipe.py spawns recipe containers WITHOUT --network, so
#     they land on the docker default `bridge`. To reach those bridge IPs
#     from a container→container path, our test container must ALSO live
#     on `bridge`. Default `docker run` (no --network flag) does exactly
#     that — every container without an explicit network joins `bridge`.
#   * `AP_DOCKER_NETWORK=bridge` is set so the api_server's
#     InappRecipeIndex.get_container_ip reads the container's IP under
#     `NetworkSettings.Networks["bridge"].IPAddress` — same lookup the
#     production dispatcher does. The conftest `e2e_docker_network`
#     fixture honors `AP_E2E_NETWORK_PRESET=bridge` and skips its own
#     `docker network create` (the default bridge already exists).
#   * `AP_E2E_DOCKERIZED_HARNESS=1` flips `_E2EWrappedIndex.get_container_ip`
#     from the legacy host-published-port `127.0.0.1` shim to a real
#     `docker inspect`-driven bridge-IP lookup (delegating to the wrapped
#     real `InappRecipeIndex`).
#
# testcontainers in this mode:
#   * `TC_HOST=host.docker.internal` + `--add-host=host.docker.internal:host-gateway`
#     so the spawned postgres/redis containers' host-published ports
#     (which testcontainers maps onto the host) are reachable from the
#     test container via the host gateway. Verified working on both
#     Docker Desktop (macOS) and modern Docker Engine (Linux 20.10+).
e2e-inapp-docker:  ## Phase 22c.3.1-01-AC01: dockerized 5-cell route gate (macOS parity path).
	@test -n "$$OPENROUTER_API_KEY" || (echo "ERROR: OPENROUTER_API_KEY not set in env" && exit 1)
	@for img in hermes nanobot openclaw nullclaw zeroclaw; do \
		docker image inspect ap-recipe-$$img:latest >/dev/null 2>&1 || \
			(echo "ERROR: missing image ap-recipe-$$img:latest — run tools/run_recipe.py first" && exit 1); \
	done
	@docker image inspect ap-test-runner:latest >/dev/null 2>&1 || ( \
		echo "[e2e-inapp-docker] building ap-test-runner:latest from tools/Dockerfile.test-runner"; \
		cd .. && docker build -f tools/Dockerfile.test-runner -t ap-test-runner:latest . \
	)
	@REPO_ROOT="$$(cd .. && pwd)"; \
	echo "[e2e-inapp-docker] launching test container on docker default bridge"; \
	docker run --rm \
	  --add-host=host.docker.internal:host-gateway \
	  -e OPENROUTER_API_KEY \
	  -e ANTHROPIC_API_KEY \
	  -e TC_HOST=host.docker.internal \
	  -e AP_E2E_NETWORK_PRESET=bridge \
	  -e AP_E2E_DOCKERIZED_HARNESS=1 \
	  -v /var/run/docker.sock:/var/run/docker.sock \
	  -v "$$REPO_ROOT":/workspace \
	  -w /workspace/api_server \
	  ap-test-runner:latest \
	  pytest tests/e2e/test_inapp_5x5_matrix.py -v --tb=short -m api_integration; \
	rc=$$?; \
	echo "---"; \
	echo "Report: api_server/tests/e2e/e2e-report.json"; \
	if [ -f tests/e2e/e2e-report.json ]; then \
	  cat tests/e2e/e2e-report.json | python3 -c "import json,sys; r=json.load(sys.stdin); assert r['passed'], 'GATE FAIL: '+repr(r.get('failures')); print('GATE PASS — 5/5 cells')" || rc=1; \
	else \
	  echo "ERROR: e2e-report.json missing — pytest collection or fixture failure before report emit"; \
	  rc=1; \
	fi; \
	exit $$rc
