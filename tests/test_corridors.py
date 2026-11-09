"""Tests for gap scoring (issues #21 and #54) and corridor merging (#37).

Every expected edge score and continuity factor is worked out by hand; every corridor
score is the sum of its edges' scores.
"""

import random

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString

from bubi.contracts.schemas import CorridorsSchema, EdgeScoresSchema
from bubi.corridors import (
    calculate_continuity_factors,
    calculate_edge_route_volumes,
    detect_gaps_and_score_edges,
    merge_edges_into_corridors,
)


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


def test_isolated_gap_keeps_its_base_score():
    edges = make_edges([("a-b-0", 250, False)])
    volumes = make_volumes([("baseline", "a-b-0", 12)])

    result = detect_gaps_and_score_edges(edges, volumes)

    assert row_of(result, "a-b-0")["score"] == 12 * 250  # 3000
    assert row_of(result, "a-b-0")["volume"] == 12


def test_continuity_factors_use_hand_computed_percentiles_with_zero_and_tie():
    gap_scores = pd.DataFrame(
        [
            ("baseline", "a-b-0", 100.0),
            ("baseline", "b-c-0", 300.0),
            ("baseline", "c-d-0", 300.0),
            ("baseline", "x-y-0", 0.0),
        ],
        columns=["scenario", "edge_id", "base_score"],
    )

    factors = calculate_continuity_factors(gap_scores)

    assert factors.tolist() == pytest.approx([1.1875, 1.09375, 1.1875, 1.0])


def test_all_zero_and_single_edge_continuity_are_neutral():
    all_zero = pd.DataFrame(
        [("baseline", "a-b-0", 0.0), ("baseline", "b-c-0", 0.0)],
        columns=["scenario", "edge_id", "base_score"],
    )
    single_edge = pd.DataFrame(
        [("baseline", "a-b-0", 100.0)],
        columns=["scenario", "edge_id", "base_score"],
    )

    assert calculate_continuity_factors(all_zero).tolist() == [1.0, 1.0]
    assert calculate_continuity_factors(single_edge).tolist() == [1.0]


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


def test_negative_base_score_for_continuity_raises():
    gap_scores = pd.DataFrame(
        [("baseline", "a-b-0", -1.0)],
        columns=["scenario", "edge_id", "base_score"],
    )

    with pytest.raises(ValueError, match="base_score must be finite and non-negative"):
        calculate_continuity_factors(gap_scores)


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
    assert baseline["score"].tolist() == pytest.approx([180 * 950, 210 * 720, 115 * 450 * 1.1875])
    assert baseline["rank"].tolist() == [1, 2, 3]

    assert row_of(result, "n1-n3-0", "lane_aware")["score"] == 95 * 720
    assert row_of(result, "n1-n5-0", "population_only")["score"] == 140 * 950


# ---------------------------------------------------------------- corridors (#37)


def gap_network(rows):
    """rows: (edge_id, length_m, score[, osm_way_id]) -> (edges, baseline edge scores).

    Edges without a way ID all get way 1.
    """
    rows = [row if len(row) == 4 else (*row, 1) for row in rows]
    edges = make_edges([(edge_id, length, False) for edge_id, length, _, _ in rows])
    edges["osm_way_id"] = [way for *_, way in rows]
    scores = pd.DataFrame(
        {
            "scenario": "baseline",
            "edge_id": [edge_id for edge_id, *_ in rows],
            "volume": 1.0,
            "score": [float(score) for _, _, score, _ in rows],
            "rank": range(1, len(rows) + 1),
        }
    )
    return edges, scores


def corridor_list(result, scenario="baseline"):
    """[(edge_ids, score, rank)] of one scenario, in rank order."""
    rows = result[result["scenario"] == scenario]
    return [(list(r.edge_ids), r.score, r.rank) for r in rows.itertuples()]


def test_chain_of_three_becomes_one_corridor_in_travel_order():
    # a -> b -> c -> d, given out of order.
    edges, scores = gap_network([("c-d-0", 30, 3), ("a-b-0", 10, 1), ("b-c-0", 20, 2)])

    result = merge_edges_into_corridors(edges, scores)

    assert corridor_list(result) == [(["a-b-0", "b-c-0", "c-d-0"], 6.0, 1)]


def test_fork_without_a_clear_street_ends_the_corridor():
    # a -> b, then b -> c and b -> d, all on the same OSM way: no single way on.
    edges, scores = gap_network([("a-b-0", 10, 5), ("b-c-0", 10, 4), ("b-d-0", 10, 3)])

    result = merge_edges_into_corridors(edges, scores)

    assert corridor_list(result) == [(["a-b-0"], 5.0, 1), (["b-c-0"], 4.0, 2), (["b-d-0"], 3.0, 3)]


def test_at_a_crossing_each_corridor_stays_on_its_own_street():
    # Main street (way 1) a -> b -> c crosses side street (way 2) x -> b -> y at b.
    edges, scores = gap_network(
        [
            ("a-b-0", 10, 4, 1),
            ("b-c-0", 10, 4, 1),
            ("x-b-0", 10, 1, 2),
            ("b-y-0", 10, 1, 2),
        ]
    )

    result = merge_edges_into_corridors(edges, scores)

    assert corridor_list(result) == [(["a-b-0", "b-c-0"], 8.0, 1), (["x-b-0", "b-y-0"], 2.0, 2)]


def test_at_a_fork_the_corridor_follows_its_own_street():
    # a -> b -> c is one street (way 1); b -> d branches off (way 2).
    edges, scores = gap_network([("a-b-0", 10, 1, 1), ("b-c-0", 10, 1, 1), ("b-d-0", 10, 5, 2)])

    result = merge_edges_into_corridors(edges, scores)

    assert corridor_list(result) == [(["b-d-0"], 5.0, 1), (["a-b-0", "b-c-0"], 2.0, 2)]


def test_join_ends_the_corridor_too():
    # a -> c and b -> c meet, then c -> d.
    edges, scores = gap_network([("a-c-0", 10, 1), ("b-c-0", 10, 2), ("c-d-0", 10, 3)])

    result = merge_edges_into_corridors(edges, scores)

    assert [ids for ids, _, _ in corridor_list(result)] == [["c-d-0"], ["b-c-0"], ["a-c-0"]]


def test_two_directions_of_a_road_stay_separate_corridors():
    # Two-way street a - b - c without a lane in either direction.
    edges, scores = gap_network(
        [("a-b-0", 10, 1), ("b-c-0", 10, 2), ("c-b-0", 10, 4), ("b-a-0", 10, 8)]
    )

    result = merge_edges_into_corridors(edges, scores)

    assert corridor_list(result) == [
        (["c-b-0", "b-a-0"], 12.0, 1),
        (["a-b-0", "b-c-0"], 3.0, 2),
    ]


def test_an_edge_is_never_joined_to_its_own_reverse():
    # A dead end: a -> b and back b -> a would be a U-turn.
    edges, scores = gap_network([("a-b-0", 10, 1), ("b-a-0", 10, 2)])

    result = merge_edges_into_corridors(edges, scores)

    assert [ids for ids, _, _ in corridor_list(result)] == [["b-a-0"], ["a-b-0"]]


def test_closed_loop_starts_at_its_smallest_edge_id():
    edges, scores = gap_network([("b-c-0", 10, 1), ("c-a-0", 10, 1), ("a-b-0", 10, 1)])

    result = merge_edges_into_corridors(edges, scores)

    assert corridor_list(result) == [(["a-b-0", "b-c-0", "c-a-0"], 3.0, 1)]


def test_ties_are_broken_by_length_then_first_edge_id():
    edges, scores = gap_network(
        [
            ("p-q-0", 10, 5),  # score 5, 10 m
            ("x-y-0", 50, 5),  # score 5, 50 m: longer, so ahead of p-q-0
            ("m-n-0", 10, 5),  # score 5, 10 m: same as p-q-0, m sorts first
        ]
    )

    result = merge_edges_into_corridors(edges, scores)

    assert [ids[0] for ids, _, _ in corridor_list(result)] == ["x-y-0", "m-n-0", "p-q-0"]


def test_result_does_not_depend_on_input_order():
    rows = [("a-b-0", 10, 1), ("b-c-0", 10, 2), ("c-d-0", 10, 1), ("b-e-0", 10, 7)]
    rows += [("x-y-0", 10, 4), ("y-x-0", 10, 4), ("q-r-0", 10, 4)]
    edges, scores = gap_network(rows)
    expected = merge_edges_into_corridors(edges, scores)

    for seed in range(5):
        shuffled = scores.sample(frac=1, random_state=seed)
        result = merge_edges_into_corridors(edges, shuffled)
        pd.testing.assert_frame_equal(result, expected)


def test_ranks_and_ids_restart_per_scenario():
    edges, scores = gap_network([("a-b-0", 10, 1), ("c-d-0", 10, 2)])
    lane_aware = scores.assign(scenario="lane_aware", score=[9.0, 1.0])
    both = pd.concat([scores, lane_aware], ignore_index=True)

    result = merge_edges_into_corridors(edges, both)

    assert result["corridor_id"].tolist() == [
        "corr_bl_01",
        "corr_bl_02",
        "corr_la_01",
        "corr_la_02",
    ]
    assert result["rank"].tolist() == [1, 2, 1, 2]
    # baseline: c-d-0 (2) beats a-b-0 (1); lane_aware: a-b-0 (9) beats c-d-0 (1).
    assert [list(ids) for ids in result["edge_ids"]] == [["c-d-0"], ["a-b-0"], ["a-b-0"], ["c-d-0"]]


def test_scenario_argument_merges_only_that_scenario():
    edges, scores = gap_network([("a-b-0", 10, 1)])
    both = pd.concat([scores, scores.assign(scenario="lane_aware")], ignore_index=True)

    result = merge_edges_into_corridors(edges, both, scenario="lane_aware")

    assert result["scenario"].tolist() == ["lane_aware"]


def test_every_edge_lands_in_exactly_one_connected_one_way_corridor():
    rng = random.Random(7)
    nodes = [f"n{i}" for i in range(12)]
    pairs = {(u, v) for u in nodes for v in nodes if u != v and rng.random() < 0.15}
    rows = [(f"{u}-{v}-0", rng.randint(5, 50), rng.randint(0, 9)) for u, v in sorted(pairs)]
    edges, scores = gap_network(rows)

    result = merge_edges_into_corridors(edges, scores)

    all_ids = [e for ids in result["edge_ids"] for e in ids]
    assert sorted(all_ids) == sorted(scores["edge_id"])
    for ids in result["edge_ids"]:
        for first, second in zip(ids, ids[1:]):
            u1, v1, _ = first.split("-")
            u2, v2, _ = second.split("-")
            assert v1 == u2  # end to end, same direction of travel
            assert (u2, v2) != (v1, u1)  # never the same road backwards


def test_no_gap_edges_gives_an_empty_valid_table():
    edges, scores = gap_network([("a-b-0", 10, 1)])

    result = merge_edges_into_corridors(edges, scores.iloc[0:0])

    assert result.empty
    assert list(result.columns) == ["scenario", "corridor_id", "edge_ids", "score", "rank"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda s: s.assign(edge_id=["x-y-0"]), "not in the edges table"),
        (lambda s: pd.concat([s, s]), "one row per"),
        (lambda s: s.assign(edge_id=["not-an-id"]), "u-v-key"),
        (lambda s: s.assign(score=[-1.0]), "non-negative"),
        (lambda s: s.drop(columns="score"), "missing required column"),
    ],
)
def test_bad_edge_scores_raise_clear_errors(change, message):
    edges, scores = gap_network([("a-b-0", 10, 1)])

    with pytest.raises(ValueError, match=message):
        merge_edges_into_corridors(edges, change(scores))


def test_repo_fixtures_corridors_end_to_end(sample_edges, sample_routes):
    """Week 1 volumes -> week 2 gap scores -> corridors, on the repo fixtures."""
    scores = detect_gaps_and_score_edges(sample_edges, calculate_edge_route_volumes(sample_routes))

    result = merge_edges_into_corridors(sample_edges, scores)

    CorridorsSchema.validate(result)
    # n2-n1-0 ends at n1, where two gap edges leave (n1-n3-0 and n1-n5-0): a fork,
    # so all three stay separate corridors.
    assert corridor_list(result) == [
        (["n1-n5-0"], 180 * 950, 1),
        (["n1-n3-0"], 210 * 720, 2),
        (["n2-n1-0"], 115 * 450 * 1.1875, 3),
    ]
    assert result.loc[result["scenario"] == "lane_aware", "corridor_id"].tolist() == ["corr_la_01"]
