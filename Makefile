# Hermes Agent — common developer commands
#
# Usage:
#   make build         Build the Docker image
#   make test          Run the test suite
#   make lint          Run linters (ruff)
#   make run           Start the interactive CLI (local Python, no Docker)
#   make run-docker    Start the interactive CLI inside Docker
#   make gateway       Start the messaging gateway (local Python)
#   make health        Start the health-check server (local Python)
#   make release TAG=v0.7.0  Tag + push a release

.DEFAULT_GOAL := help
SHELL         := /bin/bash

# ── Config ────────────────────────────────────────────────────────────────────

IMAGE         ?= nousresearch/hermes-agent
TAG           ?= dev
PYTHON        ?= python3
UV            ?= uv
PYTEST        ?= pytest
HEALTH_PORT   ?= 9090

# ── Helpers ───────────────────────────────────────────────────────────────────

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' \
		| sort

# ── Install / setup ───────────────────────────────────────────────────────────

.PHONY: install
install: ## Install all Python dependencies into a venv via uv
	$(UV) venv .venv
	$(UV) pip install -e ".[all,dev]"
	@echo "Activate with: source .venv/bin/activate"

.PHONY: install-hooks
install-hooks: ## Install the pre-commit secret-scanning hook
	bash scripts/install_hooks.sh

# ── Test ──────────────────────────────────────────────────────────────────────

.PHONY: test
test: ## Run unit tests (parallel, no integration tests)
	$(PYTEST) tests/ -q --ignore=tests/integration --tb=short -n auto

.PHONY: test-verbose
test-verbose: ## Run tests with full output
	$(PYTEST) tests/ -v --ignore=tests/integration --tb=long -n auto

.PHONY: test-coverage
test-coverage: ## Run tests and print a coverage report
	$(PYTEST) tests/ --ignore=tests/integration --tb=short -n auto \
		--cov=. --cov-report=term-missing --cov-report=html:htmlcov

.PHONY: test-integration
test-integration: ## Run integration tests (requires real API keys)
	$(PYTEST) tests/integration/ -v --tb=short

# ── Lint ──────────────────────────────────────────────────────────────────────

.PHONY: lint
lint: ## Lint with ruff
	ruff check .

.PHONY: lint-fix
lint-fix: ## Lint and auto-fix with ruff
	ruff check . --fix

.PHONY: scan-secrets
scan-secrets: ## Scan the whole repo for committed secrets
	$(PYTHON) scripts/scan_secrets.py --all

# ── Run (local Python) ────────────────────────────────────────────────────────

.PHONY: run
run: ## Start the Hermes interactive CLI
	hermes

.PHONY: gateway
gateway: ## Start the messaging gateway
	hermes gateway start

.PHONY: health
health: ## Start the health-check server on port $(HEALTH_PORT)
	HERMES_HEALTH_PORT=$(HEALTH_PORT) $(PYTHON) scripts/health_server.py

# ── Docker ────────────────────────────────────────────────────────────────────

.PHONY: build
build: ## Build the Docker image (IMAGE:TAG)
	docker build -t $(IMAGE):$(TAG) .

.PHONY: build-no-cache
build-no-cache: ## Build the Docker image without layer cache
	docker build --no-cache -t $(IMAGE):$(TAG) .

.PHONY: run-docker
run-docker: ## Run the interactive CLI inside Docker
	docker compose run --rm hermes

.PHONY: gateway-docker
gateway-docker: ## Start the gateway in Docker (detached)
	docker compose up -d gateway

.PHONY: down
down: ## Stop and remove all compose services
	docker compose down

.PHONY: logs
logs: ## Tail logs from all compose services
	docker compose logs -f

.PHONY: push
push: ## Push IMAGE:TAG to Docker Hub (requires docker login)
	docker push $(IMAGE):$(TAG)

# ── Release ───────────────────────────────────────────────────────────────────

.PHONY: release
release: ## Tag and push a release: make release TAG=v0.7.0
ifndef TAG
	$(error TAG is required: make release TAG=v0.7.0)
endif
	@echo "Tagging release $(TAG)"
	git tag -a $(TAG) -m "Release $(TAG)"
	git push origin $(TAG)
	@echo "Tag pushed — GitHub Actions will build and publish the Docker image."

.PHONY: version
version: ## Print current package version
	@$(PYTHON) -c "from importlib.metadata import version; print(version('hermes-agent'))" 2>/dev/null \
		|| grep '^version' pyproject.toml | head -1

# ── Cleanup ───────────────────────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove build artifacts and caches
	rm -rf build dist *.egg-info htmlcov .coverage .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
