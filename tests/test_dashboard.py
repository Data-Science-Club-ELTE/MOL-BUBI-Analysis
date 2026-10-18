"""Tests for the dashboard skeleton: data loading, error messages and a headless app run."""

import shutil
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from bubi.dashboard.app import offset_line, route_volume_per_edge
from bubi.dashboard.data import (
    DATA_DIR_ENV,
    OPTIONAL_TABLES,
    REQUIRED_TABLES,
    DashboardDataError,
    as_id_list,
    cell_center,
    for_scenario,
    load_dashboard_data,
)

APP_PATH = Path(__file__).resolve().parents[1] / "src" / "bubi" / "dashboard" / "app.py"


@pytest.fixture
def fixture_copy(tmp_path: Path, fixtures_dir: Path) -> Path:
    """A throwaway copy of the fixtures that tests can break."""
    target = tmp_path / "fixtures"
    shutil.copytree(fixtures_dir, target)
    return target


# ---------------------------------------------------------------- loader


def test_loads_all_fixture_tables(fixtures_dir: Path):
    data = load_dashboard_data(fixtures_dir)
    assert data.source == "fixtures"
    assert set(data.tables) == set(REQUIRED_TABLES) | set(OPTIONAL_TABLES)
    assert data.warnings == []
    assert len(data.get("stations")) > 0


def test_missing_required_table_gives_clear_error(fixture_copy: Path):
    (fixture_copy / "sample_stations.parquet").unlink()
    with pytest.raises(DashboardDataError) as err:
        load_dashboard_data(fixture_copy)
    message = str(err.value)
    assert "`stations` table is missing" in message
    assert "make fixtures" in message


def test_missing_optional_table_only_warns(fixture_copy: Path):
    (fixture_copy / "sample_corridors.parquet").unlink()
    data = load_dashboard_data(fixture_copy)
    assert "corridors" not in data.tables
    assert any("`corridors`" in w for w in data.warnings)


def test_invalid_table_names_the_contract(fixture_copy: Path):
    bad = pd.DataFrame([{"station_id": "x", "name": "Out of Budapest", "lat": 10.0, "lon": 19.0}])
    bad.to_parquet(fixture_copy / "sample_stations.parquet", index=False)
    with pytest.raises(DashboardDataError, match="does not match its data contract"):
        load_dashboard_data(fixture_copy)


def test_corrupt_file_gives_clear_error(fixture_copy: Path):
    (fixture_copy / "sample_edges.parquet").write_bytes(b"not a parquet file")
    with pytest.raises(DashboardDataError, match="could not be read"):
        load_dashboard_data(fixture_copy)


# ---------------------------------------------------------------- helpers


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("n1-n3-0", ["n1-n3-0"]),
        ("n1-n3-0, n3-n4-0", ["n1-n3-0", "n3-n4-0"]),
        ('["a", "b"]', ["a", "b"]),
        (["a", "b"], ["a", "b"]),
        (None, []),
    ],
)
def test_as_id_list(value, expected):
    assert as_id_list(value) == expected


def test_cell_center_rejects_invalid_ids():
    assert cell_center("not-a-cell") is None
    lat, lon = cell_center("891e037aacfffff")  # Deák Ferenc tér, res 9
    assert 47.4 < lat < 47.6 and 19.0 < lon < 19.1


def test_for_scenario_handles_missing_table():
    assert for_scenario(None, "baseline").empty


def test_offset_line_separates_directions():
    forward = [(19.05, 47.49), (19.06, 47.50)]
    there = offset_line(forward)
    back = offset_line(list(reversed(forward)))
    assert there[0] != back[-1]  # the two directions no longer overlap


def test_route_volume_per_edge(sample_routes):
    volumes = route_volume_per_edge(sample_routes[sample_routes["scenario"] == "baseline"])
    assert volumes["n1-n3-0"] == 210.0


# ---------------------------------------------------------------- app


def _run_app(monkeypatch, data_dir: Path | None = None) -> AppTest:
    if data_dir is not None:
        monkeypatch.setenv(DATA_DIR_ENV, str(data_dir))
    return AppTest.from_file(str(APP_PATH), default_timeout=60).run()


def test_app_runs_on_fixtures(monkeypatch, fixtures_dir: Path):
    at = _run_app(monkeypatch, fixtures_dir)
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 4


@pytest.mark.parametrize("scenario", ["lane_aware", "population_only"])
def test_app_switches_scenario(monkeypatch, fixtures_dir: Path, scenario: str):
    at = _run_app(monkeypatch, fixtures_dir)
    at.sidebar.radio[0].set_value(scenario).run()
    assert not at.exception


def test_app_shows_error_instead_of_crashing(monkeypatch, fixture_copy: Path):
    (fixture_copy / "sample_edges.parquet").unlink()
    at = _run_app(monkeypatch, fixture_copy)
    assert not at.exception
    assert at.error and "`edges` table is missing" in at.error[0].value
