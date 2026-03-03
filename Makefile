# AgentCost — Makefile
#
# Common development and release commands.

.PHONY: install dev test lint format build publish-pypi publish-npm docker docs serve clean verify

# ── Development ──────────────────────────────────────────────────────────────

install:
	pip install -e ".[server]"

dev:
	pip install -e ".[dev,server,docs]"
	pre-commit install

test:
	pytest tests/ -v --tb=short

lint:
	ruff check agentcost/ tests/

format:
	ruff format agentcost/ tests/

# ── Server ───────────────────────────────────────────────────────────────────

serve:
	AGENTCOST_PORT=8100 python -m agentcost.api.server

serve-community:
	AGENTCOST_EDITION=community AGENTCOST_PORT=8100 python -m agentcost.api.server

serve-enterprise:
	AGENTCOST_EDITION=enterprise AGENTCOST_PORT=8100 python -m agentcost.api.server

seed:
	curl -s -X POST http://localhost:8100/api/seed \
		-H "Content-Type: application/json" \
		-d '{"days": 14, "clear": true}' | python -m json.tool

# ── Build & Publish ──────────────────────────────────────────────────────────

build:
	pip install build
	python -m build

publish-pypi: build
	twine upload dist/*

publish-npm:
	cd sdks/typescript && npm install && npm run build && npm publish --access public

docker:
	docker build -t agentcost -f docker/Dockerfile.dashboard .

docker-run: docker
	docker run -p 8100:8100 -v agentcost_data:/data agentcost

docker-compose-dev:
	docker compose -f docker-compose.dev.yml up --build

docker-compose-enterprise:
	docker compose up --build -d

# ── Documentation ────────────────────────────────────────────────────────────

docs:
	mkdocs build

docs-serve:
	mkdocs serve -a localhost:8200

docs-deploy:
	mkdocs gh-deploy --force

# ── Release ──────────────────────────────────────────────────────────────────

verify:
	python scripts/verify_release.py --full

release-check:
	@echo "Release checklist:"
	@echo "  1. Version in pyproject.toml:  $$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
	@echo "  2. Version in package.json:    $$(python -c "import json; print(json.load(open('sdks/typescript/package.json'))['version'])")"
	@echo "  3. CHANGELOG.md updated?"
	@echo "  4. All tests passing?"
	@echo ""
	@echo "To release:"
	@echo "  git tag v1.0.0"
	@echo "  git push origin v1.0.0"
	@echo ""
	@echo "CI will automatically publish to PyPI, npm, and GHCR."

# ── Cleanup ──────────────────────────────────────────────────────────────────

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
