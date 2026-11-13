"""Tests for the profiling quality checks (issue #17)."""

import pandas as pd
import pytest

from bubi.profiling import build_quality_report, profile_dataset


def _status(profile, check_name):
    return next(c["status"] for c in profile["checks"] if c["check"] == check_name)


def _failed(profile):
    return {c["check"] for c in profile["checks"] if c["status"] == "fail"}


# ------------------------------------------------------------------ stations
def test_summary_fields_are_kept():
    df = pd.DataFrame({"a": [1, None]})
    summary = profile_dataset(df, "other")
    assert summary["rows"] == 2
    assert summary["columns"] == ["a"]
    assert summary["null_counts"] == {"a": 1}
    assert summary["checks"] == []


def test_clean_stations_pass():
    df = pd.DataFrame(
        {
            "station_id": ["1", "2"],
            "name": ["A", "B"],
            "lat": [47.50, 47.51],
            "lon": [19.04, 19.05],
        }
    )
    profile = profile_dataset(df, "stations", reference_count=2)
    assert _failed(profile) == set()


def test_station_problems_are_flagged():
    df = pd.DataFrame(
        {
            "station_id": ["1", "1", "3"],
            "name": ["A", "A", "C"],
            "lat": [47.50, 47.50, 47.90],  # station 3 is north of Budapest
            "lon": [19.04, 19.04, 19.05],
        }
    )
    profile = profile_dataset(df, "stations", reference_count=704)
    assert _failed(profile) == {
        "Coordinates inside Budapest bounding box",
        "No duplicate station IDs",
        "No duplicate locations (same lat/lon to ~1 m)",
        "Station count vs. Futár",
    }


def test_station_count_unresolved_without_reference():
    df = pd.DataFrame({"station_id": ["1"], "name": ["A"], "lat": [47.5], "lon": [19.0]})
    profile = profile_dataset(df, "stations")
    assert _status(profile, "Station count vs. Futár") == "unresolved"


# ---------------------------------------------------------------- population
def test_population_problems_are_flagged():
    h3 = pytest.importorskip("h3")
    good = h3.latlng_to_cell(47.4979, 19.0541, 9)
    wrong_res = h3.latlng_to_cell(47.4979, 19.0541, 8)
    df = pd.DataFrame(
        {"cell_id": [good, wrong_res, "not-a-cell"], "population": [100.0, -5.0, 10.0]}
    )
    profile = profile_dataset(df, "population")
    assert _failed(profile) == {
        "No negative population values",
        "Cell IDs are valid H3 resolution 9",
    }


def test_population_total_compared_with_official_figure():
    h3 = pytest.importorskip("h3")
    cell = h3.latlng_to_cell(47.4979, 19.0541, 9)
    df = pd.DataFrame({"cell_id": [cell], "population": [950.0]})
    near = profile_dataset(df, "population", reference_total=1000.0)  # -5%
    far = profile_dataset(df, "population", reference_total=2000.0)  # -52.5%
    assert _status(near, "Total population vs. official figure") == "pass"
    assert _status(far, "Total population vs. official figure") == "fail"
    assert _status(profile_dataset(df, "population"), "Total population vs. official figure") == (
        "unresolved"
    )


# --------------------------------------------------------------------- edges
def test_edge_problems_are_flagged():
    df = pd.DataFrame(
        {
            "edge_id": ["1-2-0", "1-2-0", "2-3-0"],
            "length_m": [100.0, 100.0, 0.0],
            "has_dedicated_lane": [True, False, False],
        }
    )
    assert _failed(profile_dataset(df, "edges")) == {
        "No duplicate edge_id",
        "No zero or negative lengths",
    }


def test_lane_share_per_direction():
    df = pd.DataFrame(
        {
            "edge_id": ["1-2-0", "2-1-0", "1-3-0", "3-1-0", "2-4-0", "4-2-0", "5-6-0"],
            "length_m": [100.0] * 7,
            "has_dedicated_lane": [True, False, False, False, True, True, True],
        }
    )
    checks = {c["check"]: c["detail"] for c in profile_dataset(df, "edges")["checks"]}
    assert checks["Share of directed edges with a dedicated lane"].startswith("4 of 7 edges")
    assert checks["Lane per direction on two-way streets"] == (
        "3 two-way streets: lane in both directions 1, one direction only 1, none 1; "
        "1 one-way edges"
    )


# -------------------------------------------------------------------- report
def test_report_lists_problems():
    df = pd.DataFrame(
        {"edge_id": ["1-2-0", "1-2-0"], "length_m": [5.0, 5.0], "has_dedicated_lane": [True, True]}
    )
    report = build_quality_report([profile_dataset(df, "edges")], title="Test")
    assert report.startswith("# Test")
    assert "| No duplicate edge_id | FAIL |" in report
    assert "`edges`: No duplicate edge_id" in report


# ------------------------------------------------------------------ fixtures
def test_fixture_tables_pass(sample_stations, sample_population, sample_edges):
    for df, name in [
        (sample_stations, "stations"),
        (sample_population, "population"),
        (sample_edges, "edges"),
    ]:
        assert _failed(profile_dataset(df, name, validate_schema=True)) == set(), name
