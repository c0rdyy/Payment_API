.DEFAULT_GOAL := help
SHELL := /bin/bash

PYTHON ?= python3
COMPOSE ?= docker compose
APP_CONTAINER ?= api

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---- local environment ----

.PHONY: venv
venv: ## Create local virtualenv and install dev deps
	$(PYTHON) -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e '.[dev]'

.PHONY: install
install: ## Install dev dependencies into the active environment
	pip install -e '.[dev]'

# ---- docker ----

.PHONY: up
up: ## Build and start the full stack
	$(COMPOSE) up --build -d

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: nuke
nuke: ## Stop the stack and drop volumes
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail logs from the api container
	$(COMPOSE) logs -f $(APP_CONTAINER)

.PHONY: ps
ps: ## Show stack status
	$(COMPOSE) ps

.PHONY: shell
shell: ## Open a shell inside the api container
	$(COMPOSE) exec $(APP_CONTAINER) bash

# ---- database ----

.PHONY: migrate
migrate: ## Apply migrations (inside the container)
	$(COMPOSE) exec $(APP_CONTAINER) alembic upgrade head

.PHONY: migrate-local
migrate-local: ## Apply migrations using local interpreter
	alembic upgrade head

.PHONY: revision
revision: ## Create a new migration. Usage: make revision m="add payments table"
	$(COMPOSE) exec $(APP_CONTAINER) alembic revision --autogenerate -m "$(m)"

# ---- quality -----

.PHONY: lint
lint: ## Run ruff lint
	ruff check app tests

.PHONY: fmt
fmt: ## Format code with ruff
	ruff format app tests
	ruff check --fix app tests

.PHONY: typecheck
typecheck: ## Run mypy in strict mode
	mypy app

.PHONY: test
test: ## Run the test suite (unit only by default)
	pytest -m "not integration"

.PHONY: test-unit
test-unit: ## Run unit tests
	pytest tests/unit

.PHONY: test-integration
test-integration: ## Run integration tests
	DOCKER_HOST=$${DOCKER_HOST:-unix:///var/run/docker.sock} pytest tests/integration -m integration

.PHONY: test-all
test-all: ## Run unit + integration tests
	DOCKER_HOST=$${DOCKER_HOST:-unix:///var/run/docker.sock} pytest

.PHONY: check
check: lint typecheck test ## Run lint, typecheck, and unit tests
