"""Load and validate the contract tables the dashboard reads.

Each table is read from ``data/processed/`` when the pipeline has produced it and
from the sample fixtures in ``tests/fixtures/`` otherwise, so the dashboard keeps
working while the pipeline is only partly built. It never calls an external API.
Every table is validated against its data contract, and any problem is raised as a
:class:`DashboardDataError` with a message the app can show to the user instead of
a raw traceback.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import h3
import pandas as pd
import pandera.errors as pa_errors
import yaml

from bubi.contracts.io import load_contract_table

REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
CONFIG_PATH = REPO_ROOT / "config" / "default_config.yaml"
DATA_DIR_ENV = "BUBI_DATA_DIR"

# The app cannot draw a map without these.
REQUIRED_TABLES = ("stations", "edges")
# Missing or invalid optional tables only switch off the layers that use them.
OPTIONAL_TABLES = ("population", "station_candidates", "edge_scores", "corridors", "routes")

SCENARIOS = ("baseline", "lane_aware", "population_only")
BUDAPEST_CENTER = (47.4979, 19.0541)


class DashboardDataError(Exception):
    """A data problem explained in plain words, safe to show in the app."""


@dataclass
class DashboardData:
    """Contract tables loaded for the dashboard, plus notes about anything skipped."""

    paths: dict[str, Path] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)  # "processed" or "fixtures"
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def get(self, name: str) -> pd.DataFrame | None:
        return self.tables.get(name)

    @property
    def fixture_tables(self) -> list[str]:
        """Loaded tables that come from test data rather than pipeline outputs."""
        return [name for name in self.tables if self.sources.get(name) == "fixtures"]

    @property
    def source(self) -> str:
        """``processed``, ``fixtures`` or ``mixed``, for the data-mode badge."""
        kinds = {self.sources[name] for name in self.tables}
        return kinds.pop() if len(kinds) == 1 else "mixed"


def table_path(data_dir: Path, table_name: str, source: str) -> Path:
    """Fixtures are named ``sample_<table>.parquet``; pipeline outputs ``<table>.parquet``."""
    prefix = "sample_" if source == "fixtures" else ""
    return data_dir / f"{prefix}{table_name}.parquet"


def resolve_table_paths(
    data_dir: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
    fixtures_dir: Path = FIXTURES_DIR,
) -> dict[str, tuple[Path, str]]:
    """Where each table is read from, and whether that file is pipeline output or test data.

    By default every table comes from ``processed_dir`` if the pipeline has written it
    and from ``fixtures_dir`` otherwise. ``data_dir`` (or the ``BUBI_DATA_DIR``
    environment variable, used by the tests) reads every table from one folder instead.
    """
    names = REQUIRED_TABLES + OPTIONAL_TABLES
    if data_dir is None and os.environ.get(DATA_DIR_ENV):
        data_dir = Path(os.environ[DATA_DIR_ENV])
    if data_dir is not None:
        source = "fixtures" if any(data_dir.glob("sample_*.parquet")) else "processed"
        return {name: (table_path(data_dir, name, source), source) for name in names}

    paths = {}
    for name in names:
        processed = table_path(processed_dir, name, "processed")
        if processed.exists():
            paths[name] = (processed, "processed")
        else:
            paths[name] = (table_path(fixtures_dir, name, "fixtures"), "fixtures")
    return paths


def _first_lines(text: str, max_lines: int = 3, max_chars: int = 400) -> str:
    lines = [line for line in str(text).strip().splitlines() if line.strip()]
    short = "\n".join(lines[:max_lines])
    return short if len(short) <= max_chars else short[:max_chars] + "…"


def load_table(table_name: str, path: Path) -> pd.DataFrame:
    """Load one contract table and validate it, turning failures into clear messages."""
    try:
        return load_contract_table(table_name, path, validate=True)
    except FileNotFoundError as err:
        raise DashboardDataError(
            f"The `{table_name}` table is missing. Expected file: `{path}`. "
            "Run `make fixtures` to recreate the sample data."
        ) from err
    except (pa_errors.SchemaError, pa_errors.SchemaErrors) as err:
        raise DashboardDataError(
            f"The `{table_name}` table at `{path}` does not match its data contract "
            f"(`src/bubi/contracts/schemas.py`):\n\n{_first_lines(err)}"
        ) from err
    except Exception as err:  # unreadable or corrupt file
        raise DashboardDataError(
            f"The `{table_name}` table at `{path}` could not be read "
            f"({type(err).__name__}: {_first_lines(err, max_lines=1)})."
        ) from err


def load_dashboard_data(data_dir: Path | None = None) -> DashboardData:
    """Load every table the dashboard uses (see :func:`resolve_table_paths` for where from).

    Raises:
        DashboardDataError: if a required table is missing or invalid.
    """
    data = DashboardData()
    for name, (path, source) in resolve_table_paths(data_dir).items():
        data.paths[name] = path
        data.sources[name] = source
        try:
            data.tables[name] = load_table(name, path)
        except DashboardDataError as err:
            if name in REQUIRED_TABLES:
                raise
            data.warnings.append(f"Layers using `{name}` are switched off. {err}")
    return data


def fixture_notes(data: DashboardData) -> list[str]:
    """One note per table that is read from test data instead of pipeline output."""
    notes = []
    for name in data.fixture_tables:
        path = data.paths[name]
        shown = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
        notes.append(f"`{name}` is read from test data (`{shown}`), not from pipeline output.")
    return notes


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """Read the project config; the dashboard still runs with defaults if it is missing."""
    try:
        with open(path, encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}


def for_scenario(df: pd.DataFrame | None, scenario: str) -> pd.DataFrame:
    """Rows of a scenario-keyed table for one scenario (empty if the table is missing)."""
    if df is None or df.empty:
        return pd.DataFrame()
    return df[df["scenario"] == scenario]


def proposed_stations(data: DashboardData, scenario: str) -> pd.DataFrame:
    """Candidates selected as new stations; unselected candidates have no rank."""
    candidates = for_scenario(data.get("station_candidates"), scenario)
    if candidates.empty:
        return candidates
    return candidates[candidates["rank"].notna()]


def as_id_list(value: Any) -> list[str]:
    """Normalise an edge-id list stored as a list, an array, a JSON string or a comma string."""
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                return [str(v) for v in json.loads(text)]
            except json.JSONDecodeError:
                pass
        return [part.strip() for part in text.split(",") if part.strip()]
    if hasattr(value, "__iter__"):
        return [str(v) for v in value]
    return [str(value)]


def cell_center(cell_id: str) -> tuple[float, float] | None:
    """Centre of an H3 cell as (lat, lon), or None if the id is not a valid cell."""
    try:
        return h3.cell_to_latlng(cell_id)
    except (ValueError, TypeError, h3.H3BaseException):
        return None
