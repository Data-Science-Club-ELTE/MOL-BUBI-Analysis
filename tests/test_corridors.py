"""Tests for detect_gaps_and_score_edges (issue #21).

Every expected score below is worked out by hand as volume x length_m x continuity_factor.
"""

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString

from bubi.contracts.schemas import EdgeScoresSchema
from bubi.corridors import calculate_edge_route_volumes, detect_gaps_and_score_edges


def make_edges(rows):
    """rows: (edge_id, length_m, has_dedicated_lane) tuples -> EdgesSchema-shaped GeoDataFrame."""
    return gpd.GeoDataFrame(
        [
            {
                "edge_id": edge_id,
                "osm_way_id": 1,
                "length_m": float(length_m),
                "has_dedicated_lane": has_lane,
                "geometry": LineString([(19.05, 47.49), (19.06, 47.50)]),
            }
            for edge_id, length_m, has_lane in rows
        ],
        crs="EPSG:4326",
    )


def make_volumes(rows):
    """rows: (scenario, edge_id, volume) tuples -> calculate_edge_route_volumes output."""
    return pd.DataFrame(rows, columns=["scenario", "edge_id", "volume"])


def row_of(result, edge_id, scenario="baseline"):
    match = result[(result["scenario"] == scenario) & (result["edge_id"] == edge_id)]
    assert len(match) == 1, f"expected one row for {scenario}/{edge_id}, got {len(match)}"
    return match.iloc[0]


# A two-way road: lane only in the a->b direction.
ONE_SIDED_ROAD = [("a-b-0", 100, True), ("b-a-0", 100, False)]


def test_edge_with_lane_in_its_direction_is_excluded():
    edges = make_edges([("a-b-0", 100, True), ("c-d-0", 200, False)])
    volumes = make_volumes([("baseline", "a-b-0", 50), ("baseline", "c-d-0", 10)])

    result = detect_gaps_and_score_edges(edges, volumes)

    assert result["edge_id"].tolist() == ["c-d-0"]


def test_one_sided_lane_keeps_only_the_missing_direction():
    edges = make_edges(ONE_SIDED_ROAD)
    volumes = make_volumes([("baseline", "a-b-0", 40), ("baseline", "b-a-0", 30)])

    result = detect_gaps_and_score_edges(edges, volumes)

    assert result["edge_id"].tolist() == ["b-a-0"]
    assert row_of(result, "b-a-0")["score"] == 30 * 100  # 3000


def test_score_is_volume_times_length_times_continuity():
    edges = make_edges([("a-b-0", 250, False)])
    volumes = make_volumes([("baseline", "a-b-0", 12)])

    default = detect_gaps_and_score_edges(edges, volumes)
    doubled = detect_gaps_and_score_edges(edges, volumes, continuity_factor=2.0)

    assert row_of(default, "a-b-0")["score"] == 12 * 250 * 1.0  # 3000
    assert row_of(doubled, "a-b-0")["score"] == 12 * 250 * 2.0  # 6000
    assert row_of(default, "a-b-0")["volume"] == 12


def test_rank_is_per_scenario_highest_score_first():
    edges = make_edges([("a-b-0", 100, False), ("c-d-0", 300, False), ("e-f-0", 50, False)])
    volumes = make_volumes(
        [
            # baseline scores: a-b 20*100=2000, c-d 10*300=3000, e-f 100*50=5000
            ("baseline", "a-b-0", 20),
            ("baseline", "c-d-0", 10),
            ("baseline", "e-f-0", 100),
            # lane_aware scores: a-b 90*100=9000, c-d 1*300=300
            ("lane_aware", "a-b-0", 90),
            ("lane_aware", "c-d-0", 1),
        ]
    )

    result = detect_gaps_and_score_edges(edges, volumes)

    baseline = result[result["scenario"] == "baseline"]
    assert baseline["edge_id"].tolist() == ["e-f-0", "c-d-0", "a-b-0"]
    assert baseline["rank"].tolist() == [1, 2, 3]
    lane_aware = result[result["scenario"] == "lane_aware"]
    assert lane_aware["edge_id"].tolist() == ["a-b-0", "c-d-0"]
    assert lane_aware["rank"].tolist() == [1, 2]


def test_equal_scores_get_unique_ranks_by_volume_then_edge_id():
    # All three score 1000: a-b 10*100, c-d 20*50, e-f 20*50.
    edges = make_edges([("a-b-0", 100, False), ("c-d-0", 50, False), ("e-f-0", 50, False)])
    volumes = make_volumes(
        [("baseline", "a-b-0", 10), ("baseline", "e-f-0", 20), ("baseline", "c-d-0", 20)]
    )

    result = detect_gaps_and_score_edges(edges, volumes)

    assert result["edge_id"].tolist() == ["c-d-0", "e-f-0", "a-b-0"]
    assert result["rank"].tolist() == [1, 2, 3]


def test_scenario_argument_scores_only_that_scenario():
    edges = make_edges([("a-b-0", 100, False)])
    volumes = make_volumes([("baseline", "a-b-0", 5), ("population_only", "a-b-0", 7)])

    result = detect_gaps_and_score_edges(edges, volumes, scenario="population_only")

    assert result["scenario"].tolist() == ["population_only"]
    assert row_of(result, "a-b-0", "population_only")["score"] == 700


def test_unused_edges_are_not_scored():
    edges = make_edges([("a-b-0", 100, False), ("c-d-0", 100, False)])
    volumes = make_volumes([("baseline", "a-b-0", 0), ("baseline", "c-d-0", 3)])

    result = detect_gaps_and_score_edges(edges, volumes)

    assert result["edge_id"].tolist() == ["c-d-0"]


def test_no_gaps_returns_empty_valid_table():
    edges = make_edges([("a-b-0", 100, True)])
    volumes = make_volumes([("baseline", "a-b-0", 9)])

    result = detect_gaps_and_score_edges(edges, volumes)

    assert result.empty
    assert list(result.columns) == ["scenario", "edge_id", "volume", "score", "rank"]


def test_volume_edge_missing_from_edges_raises():
    edges = make_edges([("a-b-0", 100, False)])
    volumes = make_volumes([("baseline", "x-y-0", 9)])

    with pytest.raises(ValueError, match="not in the edges table"):
        detect_gaps_and_score_edges(edges, volumes)


def test_lane_flag_given_as_text_raises():
    edges = make_edges([("a-b-0", 100, False)])
    edges["has_dedicated_lane"] = ["False"]
    volumes = make_volumes([("baseline", "a-b-0", 9)])

    with pytest.raises(ValueError, match="has_dedicated_lane must be boolean"):
        detect_gaps_and_score_edges(edges, volumes)


def test_negative_continuity_factor_raises():
    edges = make_edges([("a-b-0", 100, False)])
    volumes = make_volumes([("baseline", "a-b-0", 9)])

    with pytest.raises(ValueError, match="continuity_factor"):
        detect_gaps_and_score_edges(edges, volumes, continuity_factor=-1.0)


def test_repo_fixtures_end_to_end(sample_edges, sample_routes):
    """Week 1 volumes from the sample routes feed straight into gap scoring."""
    volumes = calculate_edge_route_volumes(sample_routes)

    result = detect_gaps_and_score_edges(sample_edges, volumes)

    EdgeScoresSchema.validate(result)
    # n1-n2-0 carries 120 trips but has a lane in that direction, so it is dropped;
    # its reverse n2-n1-0 has no lane and stays.
    assert "n1-n2-0" not in set(result["edge_id"])

    baseline = result[result["scenario"] == "baseline"]
    assert baseline["edge_id"].tolist() == ["n1-n5-0", "n1-n3-0", "n2-n1-0"]
    assert baseline["score"].tolist() == [180 * 950, 210 * 720, 115 * 450]
    assert baseline["rank"].tolist() == [1, 2, 3]

    assert row_of(result, "n1-n3-0", "lane_aware")["score"] == 95 * 720
    assert row_of(result, "n1-n5-0", "population_only")["score"] == 140 * 950
