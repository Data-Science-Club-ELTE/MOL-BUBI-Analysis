"""Tests for the catchment analysis (issue #33)."""

import pandas as pd
import pytest

from bubi.profiling.catchment import build_catchment_report

DEAK = (47.4979, 19.0541)


def _stations(*points):
    return pd.DataFrame(
        {
            "station_id": [str(i) for i in range(len(points))],
            "name": [f"S{i}" for i in range(len(points))],
            "lat": [p[0] for p in points],
            "lon": [p[1] for p in points],
        }
    )


def test_distance_is_zero_at_station_and_grows_away():
    h3 = pytest.importorskip("h3")
    pytest.importorskip("pyproj")
    from bubi.profiling.catchment import nearest_station_distance_m

    here = h3.latlng_to_cell(*DEAK, 10)
    lat, lon = h3.cell_to_latlng(here)
    far = h3.latlng_to_cell(DEAK[0] + 0.01, DEAK[1], 10)  # about 1.1 km north
    d = nearest_station_distance_m([here, far], _stations((lat, lon)))
    assert d[0] == pytest.approx(0.0, abs=1.0)
    assert 1000 < d[1] < 1250


def test_coverage_floor_and_distances():
    h3 = pytest.importorskip("h3")
    pytest.importorskip("pyproj")
    from bubi.profiling.catchment import catchment_table

    near = h3.latlng_to_cell(*DEAK, 9)
    mid = h3.latlng_to_cell(DEAK[0] + 0.006, DEAK[1], 9)  # about 670 m away
    far = h3.latlng_to_cell(DEAK[0] + 0.03, DEAK[1], 9)  # about 3.3 km away
    pop = pd.DataFrame({"cell_id": [near, mid, far], "population": [500.0, 300.0, 50.0]})
    table = catchment_table({9: pop}, _stations(h3.cell_to_latlng(near)), [300.0, 1000.0])

    at_300 = table[table["distance_m"] == 300.0].iloc[0]
    assert at_300["covered_population"] == 500.0
    assert at_300["populated_cells_outside"] == 2
    assert at_300["outside_cells_at_floor"] == 1  # only `mid` has >= 100 people
    assert at_300["population_outside_at_floor"] == 300.0

    at_1000 = table[table["distance_m"] == 1000.0].iloc[0]
    assert at_1000["covered_population"] == 800.0
    assert at_1000["covered_share"] == pytest.approx(800 / 850)
    assert at_1000["covered_area_km2"] > at_300["covered_area_km2"]


def test_parent_aggregation_keeps_total():
    h3 = pytest.importorskip("h3")
    from bubi.profiling.catchment import aggregate_to_parent

    parent = h3.latlng_to_cell(*DEAK, 8)
    children = list(h3.cell_to_children(parent, 9))
    res9 = pd.DataFrame({"cell_id": children, "population": [10.0] * len(children)})
    res8 = aggregate_to_parent(res9, 8)
    assert list(res8["cell_id"]) == [parent]
    assert res8["population"].sum() == pytest.approx(10.0 * len(children))


def test_resolution_rule():
    pytest.importorskip("h3")
    from bubi.profiling.catchment import resolution_check

    rule = resolution_check([8, 10], [350.0])
    by_res = rule.set_index("resolution")["passes"]
    assert not by_res[8]  # ~530 m cells are larger than the walk distance
    assert by_res[10]  # ~76 m cells are small relative to 350 m


def test_report_sections():
    coverage = pd.DataFrame(
        [
            {
                "resolution": 9,
                "distance_m": 350.0,
                "total_population": 1000.0,
                "covered_population": 600.0,
                "covered_share": 0.6,
                "covered_area_km2": 1.5,
                "populated_cells_outside": 4,
                "outside_cells_at_floor": 2,
                "population_outside_at_floor": 350.0,
            }
        ]
    )
    rule = pd.DataFrame(
        [
            {
                "resolution": 9,
                "avg_edge_m": 200.8,
                "avg_area_km2": 0.105,
                "distance_m": 350.0,
                "edge_to_distance": 0.57,
                "passes": False,
            }
        ]
    )
    report = build_catchment_report(coverage, rule, map_path="docs/catchment_map.html")
    assert "lower bound" in report
    assert "| 9 | 350 | 1,000 | 600 | 60.0% | 1.5 | 4 | 2 | 350 |" in report
    assert "| 9 | 201 | 0.105 | 350 | 0.57 | False |" in report
    assert "## Recommendation" in report and "catchment_map.html" in report


def test_report_without_population():
    rule = pd.DataFrame(
        columns=[
            "resolution",
            "avg_edge_m",
            "avg_area_km2",
            "distance_m",
            "edge_to_distance",
            "passes",
        ]
    )
    report = build_catchment_report(pd.DataFrame(), rule)
    assert "Not computed: no population table was available." in report
