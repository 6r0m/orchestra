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

.PHONY: help up check down restart workbench-install workbench-uninstall workbench-start workbench-stop \
	workbench-restart workbench-status feature demo test public-check

help: ## Show these targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-19s %s\n", $$1, $$2}'

# The stack goes through its one owner (app/application/stack.py), as the Workbench's controls do.
up: ## Start the stack: Temporal, then both workers, each proven up
	@$(V) -m app.interfaces.cli --stack start

check: ## Show the stack — Temporal, and whether each worker runs and polls — and the Workbench's service
	@$(V) -m app.interfaces.cli --stack status; code=$$?; \
	  printf '%-16s %s\n' workbench "$$(systemctl --user is-active orchestra-workbench.service)"; exit $$code

down: ## Stop both workers, then Temporal; its data stays on its volume, and the Workbench keeps serving
	@$(V) -m app.interfaces.cli --stack stop

restart: ## Stop the stack, then start it
	@$(V) -m app.interfaces.cli --stack restart

# The Workbench is not part of the stack it controls: WSL's systemd starts it and keeps it running.
workbench-install: ## Install the Workbench as a systemd user service in WSL, enabled and (re)started
	@bash workers.sh workbench install

workbench-uninstall: ## Stop the Workbench's service and remove it
	@bash workers.sh workbench uninstall

workbench-start: ## Start the Workbench's service
	@bash workers.sh workbench start

workbench-stop: ## Stop the Workbench's service; the stack it controls keeps running
	@bash workers.sh workbench stop

workbench-restart: ## Restart the Workbench's service, to load this checkout's code; the stack keeps running
	@bash workers.sh workbench restart

workbench-status: ## Show the Workbench's service
	@bash workers.sh workbench status

feature: ## Run one task through the workflow (usage: make feature TASK="fix X in Y")
	@test -n "$$TASK_SAFE" || { echo 'usage: make feature TASK="fix X in Y"' >&2; exit 2; }
	@$(V) -m app.interfaces.cli "$$TASK_SAFE"

demo: ## Watch runs answered, stopped and force-terminated, and a worker brought back, in a Workbench of its own, with fake agents (needs `make up`)
	@$(V) tools/demo.py

test: ## Run the whole suite in this checkout's environment
	@bash run-tests.sh

public-check: ## Refuse to publish anything private: tracked files, secrets, history
	@bash tools/public_check.sh
