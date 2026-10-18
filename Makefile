.PHONY: all test lint format clean

PYTHON ?= python

all: lint test

test:
	@$(PYTHON) -m unittest discover tests 2>/dev/null || py -m unittest discover tests

lint:
	@$(PYTHON) scripts/lint.py 2>/dev/null || py scripts/lint.py

format:
	@$(PYTHON) -m ruff format . 2>/dev/null || py -m ruff format . 2>/dev/null || true

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
