.PHONY: install test lint format fixtures dashboard measure-dashboard run-pipeline clean

VENV = .venv
PYTHON = $(VENV)/bin/python
UV = uv

install:
	$(UV) venv $(VENV)
	$(UV) pip install -e ".[dev]"

fixtures:
	$(PYTHON) scripts/generate_fixtures.py

test:
	$(PYTHON) -m pytest tests/ -v

lint:
	$(PYTHON) -m ruff check .

format:
	$(PYTHON) -m ruff format .

run-pipeline:
	$(PYTHON) scripts/run_pipeline.py $(PIPELINE_ARGS)

dashboard:
	$(PYTHON) -m streamlit run src/bubi/dashboard/app.py

measure-dashboard:
	$(PYTHON) scripts/measure_dashboard_load.py $(MEASURE_ARGS)

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache __pycache__ build dist *.egg-info
