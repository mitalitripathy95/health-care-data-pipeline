SHELL := /bin/bash
PYTHON ?= python3

.PHONY: install lint format test check preflight cost-preflight
install:
	$(PYTHON) -m pip install -e '.[dev]'

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

test:
	$(PYTHON) -m pytest

check: lint test

preflight:
	PYTHON_BIN=$(PYTHON) bash scripts/preflight/check_local_tools.sh

cost-preflight:
	bash scripts/cost/preflight.sh
