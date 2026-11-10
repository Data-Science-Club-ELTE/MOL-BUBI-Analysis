"""Edge cases that keep the corridor ranking stable in CI (issue #78).

Complements tests/test_corridors.py. Every expected score is worked out by hand.
"""

import math
import random
import socket

import geopandas as gpd
import pandas as pd
import pytest
from pandera.errors import SchemaError, SchemaErrors
from shapely.geometry import LineString

from bubi.contracts.schemas import CorridorsSchema, EdgeScoresSchema
from bubi.corridors import (
    calculate_continuity_factors,
    calculate_edge_route_volumes,
    detect_gaps_and_score_edges,
    merge_edges_into_corridors,
)

pytestmark = pytest.mark.usefixtures("no_network")


def make_edges(rows):
    """rows: (edge_id, length_m, has_dedicated_lane[, osm_way_id]) -> EdgesSchema-shaped table."""
    return gpd.GeoDataFrame(
        [
            {
                "edge_id": row[0],
                "osm_way_id": row[3] if len(row) == 4 else 1,
                "length_m": float(row[1]),
                "has_dedicated_lane": row[2],
                "geometry": LineString([(19.05, 47.49), (19.06, 47.50)]),
            }
            for row in rows
        ],
        crs="EPSG:4326",
    )


def make_volumes(rows):
    """rows: (scenario, edge_id, volume) -> calculate_edge_route_volumes output."""
    return pd.DataFrame(rows, columns=["scenario", "edge_id", "volume"], dtype=object).astype(
        {"volume": float}
    )


def scores_by_edge(result, scenario="baseline"):
    rows = result[result["scenario"] == scenario]
    return dict(zip(rows["edge_id"], rows["score"]))


def base_scores(rows):
    """rows: (scenario, edge_id, base_score) -> calculate_continuity_factors input."""
    return pd.DataFrame(rows, columns=["scenario", "edge_id", "base_score"])


def corridor_chains(result, scenario="baseline"):
    rows = result[result["scenario"] == scenario]
    return [list(ids) for ids in rows["edge_ids"]]


def test_offline_guard_blocks_network_access():
    with pytest.raises(RuntimeError, match="must run offline"):
        socket.create_connection(("example.com", 80), timeout=1)


# ---------------------------------------------------------------- edge scoring


def test_zero_volume_gap_is_not_scored_and_lifts_no_neighbour():
    # a -> b -> c, no lanes. b -> c is unused, so it is no gap worth ranking and must not
    # count as a high-scoring neighbour of a -> b.
    edges = make_edges([("a-b-0", 100, False), ("b-c-0", 100, False)])
    volumes = make_volumes([("baseline", "a-b-0", 10), ("baseline", "b-c-0", 0)])

    result = detect_gaps_and_score_edges(edges, volumes)

    assert scores_by_edge(result) == {"a-b-0": 10 * 100}


def test_routes_with_zero_trips_give_an_empty_valid_table():
    edges = make_edges([("a-b-0", 100, False)])
    routes = pd.DataFrame({"scenario": ["baseline"], "edges": [["a-b-0"]], "trip_count": [0.0]})

    result = detect_gaps_and_score_edges(edges, calculate_edge_route_volumes(routes))

    assert result.empty
    EdgeScoresSchema.validate(result)


def test_continuity_breaks_a_tie_in_base_score():
    # 0-9 (isolated) and a-b both have base score 10 x 100 = 1000 and the same volume, so
    # without continuity "0-9-0" would win on edge_id. a-b leads into b-c (base 5000).
    # Percentiles of 1000, 1000, 5000: 0.25, 0.25, 1.0.
    #   a-b: neighbour b-c (1.0)  -> 1 + 0.25 * 1.0  = 1.25   -> 1250
    #   b-c: neighbour a-b (0.25) -> 1 + 0.25 * 0.25 = 1.0625 -> 5312.5
    #   0-9: no neighbour         -> 1.0                      -> 1000
    edges = make_edges([("0-9-0", 100, False), ("a-b-0", 100, False), ("b-c-0", 100, False)])
    volumes = make_volumes(
        [("baseline", "0-9-0", 10), ("baseline", "a-b-0", 10), ("baseline", "b-c-0", 50)]
    )

    result = detect_gaps_and_score_edges(edges, volumes)

    assert result["edge_id"].tolist() == ["b-c-0", "a-b-0", "0-9-0"]
    assert result["score"].tolist() == [5312.5, 1250.0, 1000.0]
    assert result["rank"].tolist() == [1, 2, 3]


def test_continuity_can_lift_an_edge_above_a_higher_base_score():
    # Base scores: x-y 1000 (isolated), a-b 900, b-c 2000; percentiles 0.5, 0.0, 1.0.
    # a-b feeds b-c, so 900 x 1.25 = 1125 overtakes x-y; b-c's only neighbour has
    # percentile 0, so it keeps 2000. The lift is capped at 25%.
    edges = make_edges([("x-y-0", 100, False), ("a-b-0", 100, False), ("b-c-0", 100, False)])
    volumes = make_volumes(
        [("baseline", "x-y-0", 10), ("baseline", "a-b-0", 9), ("baseline", "b-c-0", 20)]
    )

    scores = detect_gaps_and_score_edges(edges, volumes)
    corridors = merge_edges_into_corridors(edges, scores)

    assert scores["edge_id"].tolist() == ["b-c-0", "a-b-0", "x-y-0"]
    assert scores["score"].tolist() == [2000.0, 1125.0, 1000.0]
    # Corridor scores are sums of the continuity-adjusted edge scores.
    assert corridor_chains(corridors) == [["a-b-0", "b-c-0"], ["x-y-0"]]
    assert corridors["score"].tolist() == [3125.0, 1000.0]


def test_scores_equal_base_score_times_the_continuity_factor():
    rng = random.Random(11)
    nodes = [f"n{i}" for i in range(25)]
    pairs = sorted({(u, v) for u in nodes for v in nodes if u != v and rng.random() < 0.15})
    edges = make_edges([(f"{u}-{v}-0", rng.randint(5, 60), rng.random() < 0.2) for u, v in pairs])
    volumes = make_volumes(
        [
            (scenario, edge_id, rng.randint(0, 30))
            for scenario in ("baseline", "lane_aware")
            for edge_id in edges["edge_id"]
        ]
    )

    result = detect_gaps_and_score_edges(edges, volumes)

    length = dict(zip(edges["edge_id"], edges["length_m"]))
    gaps = result.assign(base_score=result["volume"] * result["edge_id"].map(length))
    factors = calculate_continuity_factors(gaps)
    assert factors.between(1.0, 1.25).all()
    assert (factors > 1.0).any()  # the network is dense enough to have connected gaps
    assert result["score"].tolist() == (gaps["base_score"] * factors).tolist()


# ---------------------------------------------------------------- continuity factor


def test_empty_input_gives_empty_factors():
    factors = calculate_continuity_factors(base_scores([]))

    assert factors.empty
    assert factors.name == "continuity_factor"


def test_reverse_direction_alone_is_a_u_turn_not_a_neighbour():
    factors = calculate_continuity_factors(
        base_scores([("baseline", "a-b-0", 10.0), ("baseline", "b-a-0", 20.0)])
    )

    assert factors.tolist() == [1.0, 1.0]


def test_factors_are_computed_per_scenario():
    # The same two connected edges; which one is the strong neighbour depends on the scenario.
    # baseline: a-b 10, b-c 100 -> percentiles 0, 1 -> a-b lifted to 1.25.
    # lane_aware: a-b 10, b-c 0 -> only a-b is positive -> percentiles 1, 0 -> b-c lifted.
    factors = calculate_continuity_factors(
        base_scores(
            [
                ("baseline", "a-b-0", 10.0),
                ("baseline", "b-c-0", 100.0),
                ("lane_aware", "a-b-0", 10.0),
                ("lane_aware", "b-c-0", 0.0),
            ]
        )
    )

    assert factors.tolist() == [1.25, 1.0, 1.0, 1.25]


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([("baseline", "a-b-0", math.nan)], "finite and non-negative"),
        ([("baseline", "a-b-0", math.inf)], "finite and non-negative"),
        ([("baseline", "a-b-0", 1.0), ("baseline", "a-b-0", 2.0)], "one row per"),
        ([("baseline", None, 1.0)], "must not contain null"),
    ],
)
def test_bad_continuity_input_raises(rows, message):
    with pytest.raises(ValueError, match=message):
        calculate_continuity_factors(base_scores(rows))


def test_missing_base_score_column_raises():
    with pytest.raises(ValueError, match="missing required column"):
        calculate_continuity_factors(base_scores([]).drop(columns="base_score"))


# ---------------------------------------------------------------- corridors


def test_single_gap_edge_is_one_corridor_of_one_edge():
    edges = make_edges([("a-b-0", 120, False)])
    scores = detect_gaps_and_score_edges(edges, make_volumes([("baseline", "a-b-0", 5)]))

    result = merge_edges_into_corridors(edges, scores)

    assert result["corridor_id"].tolist() == ["corr_bl_01"]
    assert corridor_chains(result) == [["a-b-0"]]
    assert result["score"].tolist() == [5 * 120]


@pytest.mark.parametrize(
    ("shared_way", "expected"),
    [
        # Shared segment b -> c on the main street (way 1): the main street keeps it, the
        # side street (way 2) is split around it.
        (1, [["a-b-0", "b-c-0", "c-d-0"], ["c-y-0"], ["x-b-0"]]),
        # On a third way, neither street can claim it: every edge stands alone.
        (3, [["a-b-0"], ["b-c-0"], ["c-d-0"], ["c-y-0"], ["x-b-0"]]),
    ],
)
def test_two_streets_sharing_one_edge_never_duplicate_it(shared_way, expected):
    # Main street a -> b -> c -> d (way 1) and side street x -> b -> c -> y (way 2) share b -> c.
    edges = make_edges(
        [
            ("a-b-0", 10, False, 1),
            ("b-c-0", 10, False, shared_way),
            ("c-d-0", 10, False, 1),
            ("x-b-0", 10, False, 2),
            ("c-y-0", 10, False, 2),
        ]
    )
    scores = pd.DataFrame(
        {
            "scenario": "baseline",
            "edge_id": edges["edge_id"],
            "volume": 1.0,
            "score": 1.0,
            "rank": range(1, 6),
        }
    )

    result = merge_edges_into_corridors(edges, scores)

    chains = corridor_chains(result)
    assert chains == expected
    assert sum(chain.count("b-c-0") for chain in chains) == 1
    assert sorted(e for chain in chains for e in chain) == sorted(edges["edge_id"])


# ---------------------------------------------------------------- output schemas

VALID_EDGE_SCORE = {
    "scenario": "baseline",
    "edge_id": "a-b-0",
    "volume": 1.0,
    "score": 1.0,
    "rank": 1,
}
VALID_CORRIDOR = {
    "scenario": "baseline",
    "corridor_id": "corr_bl_01",
    "edge_ids": ["a-b-0"],
    "score": 1.0,
    "rank": 1,
}


def test_valid_rows_pass_both_output_schemas():
    EdgeScoresSchema.validate(pd.DataFrame([VALID_EDGE_SCORE]))
    CorridorsSchema.validate(pd.DataFrame([VALID_CORRIDOR]))


@pytest.mark.parametrize(
    "change",
    [
        {"scenario": "unknown"},
        {"edge_id": None},
        {"volume": -1.0},
        {"score": -1.0},
        {"rank": 0},
        {"extra": 1},
    ],
)
def test_edge_scores_schema_rejects_bad_rows(change):
    with pytest.raises((SchemaError, SchemaErrors)):
        EdgeScoresSchema.validate(pd.DataFrame([{**VALID_EDGE_SCORE, **change}]))


@pytest.mark.parametrize(
    "change",
    [
        {"scenario": "unknown"},
        {"corridor_id": None},
        {"edge_ids": None},
        {"score": -1.0},
        {"rank": 0},
        {"extra": 1},
    ],
)
def test_corridors_schema_rejects_bad_rows(change):
    with pytest.raises((SchemaError, SchemaErrors)):
        CorridorsSchema.validate(pd.DataFrame([{**VALID_CORRIDOR, **change}]))


@pytest.mark.parametrize(
    ("schema", "row", "missing"),
    [(EdgeScoresSchema, VALID_EDGE_SCORE, "rank"), (CorridorsSchema, VALID_CORRIDOR, "edge_ids")],
)
def test_output_schemas_reject_a_missing_column(schema, row, missing):
    row = {key: value for key, value in row.items() if key != missing}

    with pytest.raises((SchemaError, SchemaErrors)):
        schema.validate(pd.DataFrame([row]))
