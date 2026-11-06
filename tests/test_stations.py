"""Tests for station candidate filtering, lane connectivity and selection (Task #16)."""

import pandas as pd

from bubi.contracts.schemas import StationCandidatesSchema
from bubi.stations import (
    compute_lane_connectivity,
    filter_candidate_cells,
    lane_connectivity_pass_rate,
    select_proposed_stations,
)


def _cands(pop, stations):
    return filter_candidate_cells(pop, stations, 350.0, 100.0)


def test_filter_excludes_covered_and_small_cells(sample_stations, sample_population):
    c = _cands(sample_population, sample_stations)
    assert set(c["cell_id"]) == {"891e037aa0bffff", "891e037ae63ffff", "891e037aa4bffff"}
    tiny = filter_candidate_cells(sample_population, sample_stations, 350.0, 500.0)
    assert set(tiny["cell_id"]) == {"891e037ae63ffff"}


def test_connectivity_continuous_and_zero_when_unconnected(
    sample_stations, sample_population, sample_edges
):
    c = _cands(sample_population, sample_stations)
    conn = compute_lane_connectivity(c["cell_id"].tolist(), sample_edges, sample_stations)
    assert conn["891e037aa0bffff"] > 0  # lane within reach
    assert conn["891e037ae63ffff"] == 0.0  # no lane within reach
    # larger reach can only add lane length
    wide = compute_lane_connectivity(
        c["cell_id"].tolist(), sample_edges, sample_stations, reach_m=800.0
    )
    assert all(wide[k] >= conn[k] for k in conn)


def test_selection_schema_spacing_and_scenarios(sample_stations, sample_population, sample_edges):
    c = _cands(sample_population, sample_stations)
    c["lane_connectivity"] = c["cell_id"].map(
        compute_lane_connectivity(c["cell_id"].tolist(), sample_edges, sample_stations)
    )
    la = StationCandidatesSchema.validate(select_proposed_stations(c, "lane_aware", 5, 400.0))
    po = StationCandidatesSchema.validate(select_proposed_stations(c, "population_only", 5, 400.0))
    assert la["lane_connectivity"].notna().any() and po["lane_connectivity"].isna().all()
    # zero-connectivity cells are never selected under lane_aware
    assert la.loc[la["lane_connectivity"] == 0, "rank"].isna().all()
    # the two siting rules disagree on the top cell (the point of the comparison)
    assert la.loc[la["rank"] == 1, "cell_id"].iloc[0] != po.loc[po["rank"] == 1, "cell_id"].iloc[0]


def test_min_spacing_blocks_neighbours():
    cells = pd.DataFrame(
        {"cell_id": ["891e037aa0bffff", "891e037aa4bffff"], "population": [500.0, 400.0]}
    )
    far = select_proposed_stations(cells, "population_only", 2, 10.0)
    near = select_proposed_stations(cells, "population_only", 2, 5000.0)
    assert far["rank"].notna().sum() == 2
    assert near["rank"].notna().sum() == 1


def test_pass_rate_table(sample_stations, sample_population, sample_edges):
    r = lane_connectivity_pass_rate(sample_population, sample_stations, sample_edges)
    assert r["pass_rate"].between(0, 1).all()
    # requiring station connection can only lower the pass rate
    a = r[(~r.station_connected) & (r.reach_m == 400) & (r.min_lane_m == 0)]["pass_rate"].iloc[0]
    b = r[(r.station_connected) & (r.reach_m == 400) & (r.min_lane_m == 0)]["pass_rate"].iloc[0]
    assert b <= a
