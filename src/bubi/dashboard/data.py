"""Load and validate the contract tables the dashboard reads.

The dashboard reads from ``data/processed/`` when pipeline outputs exist there and
falls back to the sample fixtures in ``tests/fixtures/`` otherwise. It never calls
an external API. Every table is validated against its data contract, and any
problem is raised as a :class:`DashboardDataError` with a message the app can show
to the user instead of a raw traceback.
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
DEFAULT_BBOX = (18.92, 47.35, 19.33, 47.61)  # min_lon, min_lat, max_lon, max_lat


class DashboardDataError(Exception):
    """A data problem explained in plain words, safe to show in the app."""


@dataclass
class DashboardData:
    """Contract tables loaded for the dashboard, plus notes about anything skipped."""

    source: str  # "processed" or "fixtures"
    data_dir: Path
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def get(self, name: str) -> pd.DataFrame | None:
        return self.tables.get(name)


def resolve_data_dir(
    processed_dir: Path = PROCESSED_DIR, fixtures_dir: Path = FIXTURES_DIR
) -> tuple[Path, str]:
    """Use processed pipeline outputs if they exist, otherwise the sample fixtures.

    Setting the ``BUBI_DATA_DIR`` environment variable points the dashboard at
    another folder (used by the tests). Tables are never mixed between sources,
    so real and sample data cannot end up on the same map.
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        path = Path(override)
        return path, ("fixtures" if any(path.glob("sample_*.parquet")) else "processed")
    if (processed_dir / "stations.parquet").exists():
        return processed_dir, "processed"
    return fixtures_dir, "fixtures"


def table_path(data_dir: Path, table_name: str, source: str) -> Path:
    """Fixtures are named ``sample_<table>.parquet``; pipeline outputs ``<table>.parquet``."""
    prefix = "sample_" if source == "fixtures" else ""
    return data_dir / f"{prefix}{table_name}.parquet"


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


def load_dashboard_data(data_dir: Path | None = None, source: str | None = None) -> DashboardData:
    """Load every table the dashboard uses.

    Raises:
        DashboardDataError: if a required table is missing or invalid.
    """
    if data_dir is None:
        data_dir, source = resolve_data_dir()
    elif source is None:
        source = "fixtures" if any(Path(data_dir).glob("sample_*.parquet")) else "processed"
    data_dir = Path(data_dir)

    data = DashboardData(source=source, data_dir=data_dir)

    for name in REQUIRED_TABLES:
        data.tables[name] = load_table(name, table_path(data_dir, name, source))

    for name in OPTIONAL_TABLES:
        try:
            data.tables[name] = load_table(name, table_path(data_dir, name, source))
        except DashboardDataError as err:
            data.warnings.append(f"Layers using `{name}` are switched off. {err}")

    return data


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


def in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
