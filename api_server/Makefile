.PHONY: e2e-inapp

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
