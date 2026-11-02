"""Tests for calculate_edge_route_volumes (issue #7)."""

import pandas as pd
import pytest

from bubi.contracts.schemas import EdgeScoresSchema, RoutesSchema
from bubi.corridors import calculate_edge_route_volumes

# EdgeScoresSchema restricted to the fields this step produces (score/rank come later).
VolumeSchema = EdgeScoresSchema.select_columns(["scenario", "edge_id", "volume"])


def make_routes(rows):
    """rows: (scenario, edges, trip_count) tuples -> RoutesSchema-shaped DataFrame."""
    return pd.DataFrame(
        [
            {
                "scenario": scenario,
                "start_station_id": "s1",
                "end_station_id": "s2",
                "route_type": "synthetic",
                "edges": edges,
                "trip_count": float(trip_count),
            }
            for scenario, edges, trip_count in rows
        ]
    )


def volume_of(result, edge_id, scenario="baseline"):
    match = result[(result["scenario"] == scenario) & (result["edge_id"] == edge_id)]
    return float(match["volume"].iloc[0]) if len(match) else 0.0


def test_edge_used_by_multiple_routes_sums_trip_counts():
    routes = make_routes(
        [
            ("baseline", ["n1-n2-0", "n2-n3-0"], 5),
            ("baseline", ["n4-n2-0", "n2-n3-0"], 3),
        ]
    )
    result = calculate_edge_route_volumes(routes)

    assert volume_of(result, "n2-n3-0") == 8
    assert volume_of(result, "n1-n2-0") == 5
    assert volume_of(result, "n4-n2-0") == 3


def test_opposite_directions_are_counted_separately():
    routes = make_routes(
        [
            ("baseline", ["n1-n2-0"], 7),
            ("baseline", ["n2-n1-0"], 2),
        ]
    )
    result = calculate_edge_route_volumes(routes)

    assert volume_of(result, "n1-n2-0") == 7
    assert volume_of(result, "n2-n1-0") == 2
    assert len(result) == 2


def test_parallel_edges_with_different_keys_are_separate():
    result = calculate_edge_route_volumes(make_routes([("baseline", ["n1-n2-0", "n1-n2-1"], 4)]))

    assert volume_of(result, "n1-n2-0") == 4
    assert volume_of(result, "n1-n2-1") == 4


def test_repeated_edge_within_one_route_counts_once():
    loop = ["n1-n2-0", "n2-n3-0", "n3-n1-0", "n1-n2-0"]
    result = calculate_edge_route_volumes(make_routes([("baseline", loop, 6)]))

    assert volume_of(result, "n1-n2-0") == 6


def test_scenarios_are_aggregated_independently():
    routes = make_routes(
        [
            ("baseline", ["n1-n2-0"], 5),
            ("lane_aware", ["n1-n2-0"], 4),
        ]
    )
    result = calculate_edge_route_volumes(routes)

    assert volume_of(result, "n1-n2-0", "baseline") == 5
    assert volume_of(result, "n1-n2-0", "lane_aware") == 4


@pytest.mark.parametrize(
    "edges",
    [
        ["n1-n2-0", "n2-n3-0"],
        ("n1-n2-0", "n2-n3-0"),
        '["n1-n2-0", "n2-n3-0"]',
    ],
)
def test_edges_accepted_as_list_or_json_string(edges):
    result = calculate_edge_route_volumes(make_routes([("baseline", edges, 2)]))

    assert sorted(result["edge_id"]) == ["n1-n2-0", "n2-n3-0"]


def test_single_edge_id_string_is_one_edge():
    result = calculate_edge_route_volumes(make_routes([("baseline", "n1-n2-0", 3)]))

    assert result["edge_id"].tolist() == ["n1-n2-0"]


def test_fractional_trip_counts_are_kept():
    routes = make_routes(
        [
            ("baseline", ["n1-n2-0"], 0.25),
            ("baseline", ["n1-n2-0"], 1.5),
        ]
    )
    assert volume_of(calculate_edge_route_volumes(routes), "n1-n2-0") == pytest.approx(1.75)


def test_zero_trip_and_empty_routes_contribute_nothing():
    routes = make_routes(
        [
            ("baseline", ["n1-n2-0"], 0),
            ("baseline", [], 9),
            ("baseline", ["n5-n6-0"], 1),
        ]
    )
    assert calculate_edge_route_volumes(routes)["edge_id"].tolist() == ["n5-n6-0"]


def test_output_columns_and_order():
    routes = make_routes(
        [
            ("lane_aware", ["n9-n8-0"], 1),
            ("baseline", ["n1-n2-0", "n3-n4-0"], 2),
            ("baseline", ["n3-n4-0"], 5),
        ]
    )
    result = calculate_edge_route_volumes(routes)

    assert list(result.columns) == ["scenario", "edge_id", "volume"]
    assert result[["scenario", "edge_id"]].values.tolist() == [
        ["baseline", "n3-n4-0"],
        ["baseline", "n1-n2-0"],
        ["lane_aware", "n9-n8-0"],
    ]
    VolumeSchema.validate(result)


def test_empty_routes_return_empty_table():
    result = calculate_edge_route_volumes(pd.DataFrame(columns=list(RoutesSchema.columns)))

    assert result.empty
    assert list(result.columns) == ["scenario", "edge_id", "volume"]


def test_parquet_round_trip(tmp_path):
    # Parquet returns list cells as numpy arrays.
    path = tmp_path / "routes.parquet"
    make_routes([("baseline", ["n1-n2-0", "n2-n3-0"], 5)]).to_parquet(path)
    result = calculate_edge_route_volumes(pd.read_parquet(path))

    assert volume_of(result, "n2-n3-0") == 5


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("trip_count", -1.0, "non-negative"),
        ("trip_count", None, "null"),
        ("trip_count", "many", "numeric"),
        ("edges", 42, "list or JSON"),
        ("edges", ["n1-n2"], "u-v-key"),
        ("edges", "n1-n2-0, n2-n3-0", "u-v-key"),
    ],
)
def test_invalid_input_raises(column, value, message):
    routes = make_routes([("baseline", ["n1-n2-0"], 1)])
    routes[column] = routes[column].astype(object)
    routes.at[0, column] = value

    with pytest.raises(ValueError, match=message):
        calculate_edge_route_volumes(routes)


def test_missing_column_raises():
    routes = make_routes([("baseline", ["n1-n2-0"], 1)]).drop(columns="trip_count")

    with pytest.raises(ValueError, match="trip_count"):
        calculate_edge_route_volumes(routes)


def test_sample_routes_fixture(sample_routes):
    result = calculate_edge_route_volumes(sample_routes)

    VolumeSchema.validate(result)
    assert not result.duplicated(["scenario", "edge_id"]).any()
    # The fixture contains both directions of the n1-n2 street.
    assert volume_of(result, "n1-n2-0") == 120
    assert volume_of(result, "n2-n1-0") == 115
    assert volume_of(result, "n1-n3-0", "lane_aware") == 95
    assert result["volume"].sum() == pytest.approx(sample_routes["trip_count"].sum())
