# production-infrastructure-blueprint - quality gates.
# Every target delegates to scripts/pib.py (cross-platform Python) so local
# runs, CI and Taskfile users execute exactly the same checks.
#   make help
SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

ifeq ($(OS),Windows_NT)
  VENV_PY := .venv/Scripts/python.exe
else
  VENV_PY := .venv/bin/python
endif
PYTHON ?= python3
PY := $(VENV_PY)
PIB := $(PY) scripts/pib.py
STRICT ?=
## STRICT=--strict makes NOT RUN checks fail (used in CI)

.PHONY: help setup tools format lint validate security docs-check test test-unit test-integration test-e2e \
        test-security test-performance test-all list report clean clean-all

help: ## Show available targets
	@awk 'BEGIN{FS=":.*## "} /^[a-zA-Z_-]+:.*## /{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Create .venv, install pinned Python/Node tooling and checksum-verified binaries
	$(PYTHON) -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements/dev.txt
	$(PY) scripts/setup/install_tools.py
	npm ci --ignore-scripts --no-audit --no-fund

tools: ## (Re)install pinned validator binaries into .tools/bin
	$(PY) scripts/setup/install_tools.py

format: ## Apply formatters (ruff, shfmt, terraform fmt)
	$(PY) scripts/format/format.py

lint: ## Syntax + style linters
	$(PIB) run lint $(STRICT)

validate: ## Schema/semantic validation (K8s, Helm, Kustomize, Terraform, Prometheus, Compose, ...)
	$(PIB) run validate $(STRICT)

security: test-security ## Alias for test-security

test-security: ## Secret scanning, misconfiguration and vulnerability scanning, CI policy
	$(PIB) run security $(STRICT)

docs-check: ## Markdown lint, relative links, repository hygiene
	$(PIB) run docs $(STRICT)

test-unit: ## Unit tests (framework, policies, scripts, reference app, alert rules)
	$(PIB) run unit $(STRICT)

test-integration: ## Integration tests (local processes; Docker-backed tests need Docker)
	$(PIB) run integration $(STRICT)

test-e2e: ## End-to-end reference stacks (requires Docker)
	$(PIB) run e2e $(STRICT)

test-performance: ## Safety-capped k6 smoke/baseline against a LOCAL reference app
	$(PIB) run performance $(STRICT)

test: test-unit test-integration ## Unit + integration tests

test-all: ## Every stage (lint, validate, security, docs, unit, integration, e2e, performance)
	$(PIB) run all $(STRICT)

list: ## Show the test matrix with matched target counts
	$(PIB) list

report: ## Regenerate reports/*.md from the inventory and latest recorded results
	$(PIB) report

clean: ## Remove caches and generated output (keeps .venv, .tools, node_modules)
	$(PY) scripts/cleanup/clean.py

clean-all: ## clean + remove .venv, .tools and node_modules
	$(PY) scripts/cleanup/clean.py --all
