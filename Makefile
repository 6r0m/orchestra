.DEFAULT_GOAL := help
SHELL := /bin/bash

# TASK is read through $(value ...) so Make does not expand what you typed: a task containing
# $(...), a bare $ or backticks must reach the CLI as data. TASK itself must not be exported —
# Make expands a command-line variable to put it in a recipe's environment, and that expansion
# alone would run a `$(shell ...)` someone typed into a task. TASK_SAFE holds the unexpanded text,
# and consuming it as "$$TASK_SAFE" keeps it out of shell syntax too.
TASK_SAFE := $(value TASK)
unexport TASK
export TASK_SAFE

# This checkout's uv-managed environment, on this host's own disk (app/foundation/envpath.py).
V = UV_PROJECT_ENVIRONMENT="$$(uv run --no-project --managed-python --python 3.13 python app/foundation/envpath.py $(CURDIR))" \
    uv run --locked python

.PHONY: help up check down feature test public-check

help: ## Show these targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

up: ## Start the Temporal stack, both workers and the workbench
	@bash workers.sh up

check: ## Show which worker queues are polled and the workbench URL
	@bash workers.sh check

down: ## Stop the workbench, both workers and the stack; its data stays on its volume
	@bash workers.sh down

feature: ## Run one task through the workflow (usage: make feature TASK="fix X in Y")
	@test -n "$$TASK_SAFE" || { echo 'usage: make feature TASK="fix X in Y"' >&2; exit 2; }
	@$(V) -m app.interfaces.cli "$$TASK_SAFE"

test: ## Run the whole suite in this checkout's environment
	@bash run-tests.sh

public-check: ## Refuse to publish anything private: tracked files, secrets, history
	@bash tools/public_check.sh
