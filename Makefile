# kasas-skill developer tasks. Mirrors what CI runs (see .github/workflows/ci.yml).
# Python helpers are stdlib-only; the lint/format tooling is ruff.

PY ?= python3
# Prefer a project-local ruff; fall back to `uvx ruff` (no install needed).
RUFF := $(shell command -v ruff 2>/dev/null || echo "uvx ruff")

.DEFAULT_GOAL := ci
.PHONY: ci validate lint fmt fmt-check test claude-validate help

ci: validate lint fmt-check test ## Everything CI runs

validate: ## Structural + semantic plugin/skill validation (stdlib)
	$(PY) tools/validate_plugin.py

claude-validate: ## Official plugin validation (requires the claude CLI)
	claude plugin validate .

lint: ## Lint the Python helpers and tooling
	$(RUFF) check scripts tools tests

fmt: ## Auto-format the Python helpers and tooling
	$(RUFF) format scripts tools tests

fmt-check: ## Fail if anything is not formatted
	$(RUFF) format --check scripts tools tests

test: ## Run the pipeline smoke tests
	$(PY) -m unittest discover -s tests -v

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'
