"""End-to-end check of the observed-route converter on simulated GPS traces (issue #35).

Map-matching is still a placeholder, so these tests use a simple nearest-node matcher
over the sample edges. It stands in for CS 2's matcher only to exercise the seams:
converter -> RoutesSchema -> volume step.
"""

import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pandas.testing as pdt

from bubi.contracts.schemas import RoutesSchema
from bubi.corridors import calculate_edge_route_volumes
from bubi.ingestion import observed_routes as or_

FIXTURES = Path(__file__).parent / "fixtures"
FROZEN_STATIONS = Path(__file__).parents[1] / "data" / "processed" / "stations.parquet"
SNAP_RADIUS_M = 500.0
DROP_COUNTS = ("invalid_time", "unmatched_station", "no_gps", "unmatched_trace", "unknown_edge")


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Equirectangular approximation; accurate enough at city scale.
    dy = (lat2 - lat1) * 111_320.0
    dx = (lon2 - lon1) * 111_320.0 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def _nearest_node_matcher(edges: gpd.GeoDataFrame) -> or_.MapMatcher:
    """Snap each GPS point to the nearest graph node, then walk the directed edges."""
    nodes: dict[str, tuple[float, float]] = {}
    for edge in edges.itertuples():
        u, v, _ = edge.edge_id.split("-")
        coords = list(edge.geometry.coords)
        nodes[u] = (coords[0][1], coords[0][0])
        nodes[v] = (coords[-1][1], coords[-1][0])
    edge_ids = set(edges["edge_id"])

    def match(points: pd.DataFrame) -> list[str]:
        path: list[str] = []
        for point in points.itertuples():
            node, dist = min(
                ((n, _distance_m(point.lat, point.lon, *xy)) for n, xy in nodes.items()),
                key=lambda item: item[1],
            )
            if dist <= SNAP_RADIUS_M and (not path or path[-1] != node):
                path.append(node)
        matched = [f"{u}-{v}-0" for u, v in zip(path, path[1:])]
        if len(path) < 2 or not set(matched) <= edge_ids:
            return []
        return matched

    return match


def _simulated_inputs():
    trips = pd.read_csv(FIXTURES / "mock_trips.csv")
    gps = pd.read_csv(FIXTURES / "mock_gps_points.csv")
    stations = pd.read_parquet(FIXTURES / "sample_stations.parquet")
    edges = gpd.read_parquet(FIXTURES / "sample_edges.parquet")
    return trips, gps, stations, edges


def _assert_every_trip_accounted_for(report: dict) -> None:
    dropped = sum(report[key] for key in DROP_COUNTS)
    assert report["converted_trips"] + dropped == report["input_trips"]


def test_simulated_traces_convert_to_observed_routes():
    trips, gps, stations, edges = _simulated_inputs()
    routes, report = or_.convert_observed_routes(
        trips, gps, stations, matcher=_nearest_node_matcher(edges), edges=edges
    )

    RoutesSchema.validate(routes)
    assert set(routes["route_type"]) == {"observed"}
    by_pair = routes.set_index(["start_station_id", "end_station_id"])
    assert by_pair.loc[("futar_001", "futar_002"), "edges"] == ["n1-n2-0"]
    assert by_pair.loc[("futar_001", "futar_002"), "trip_count"] == 2.0  # t01 + t02
    # t03 passes near Deák tér (n1) on its way from Kálvin tér to Oktogon.
    assert by_pair.loc[("futar_002", "futar_003"), "edges"] == ["n2-n1-0", "n1-n3-0"]
    assert set(routes["edges"].explode()) <= set(edges["edge_id"])

    assert report["converted_trips"] == 3
    assert report["unmatched_trace"] == 0 and report["unknown_edge"] == 0
    _assert_every_trip_accounted_for(report)


def test_observed_routes_pass_through_volume_step_unchanged():
    trips, gps, stations, edges = _simulated_inputs()
    observed, _ = or_.convert_observed_routes(
        trips, gps, stations, matcher=_nearest_node_matcher(edges), edges=edges
    )
    synthetic = pd.read_parquet(FIXTURES / "sample_routes.parquet")
    combined = RoutesSchema.validate(pd.concat([synthetic, observed], ignore_index=True))

    observed_volumes = calculate_edge_route_volumes(observed)
    assert dict(zip(observed_volumes["edge_id"], observed_volumes["volume"])) == {
        "n1-n2-0": 2.0,
        "n2-n1-0": 1.0,
        "n1-n3-0": 1.0,
    }

    # The volume step sums both sources per edge without changing either.
    keys = ["scenario", "edge_id"]
    expected = (
        pd.concat([calculate_edge_route_volumes(synthetic), observed_volumes])
        .groupby(keys, as_index=False)["volume"]
        .sum()
    )
    actual = calculate_edge_route_volumes(combined).sort_values(keys, ignore_index=True)
    pdt.assert_frame_equal(actual, expected, check_dtype=False)

    totals = or_.volume_totals_by_route_type(combined).set_index(["scenario", "route_type"])
    assert totals.loc[("baseline", "observed")].to_dict() == {
        "routes": 2,
        "trips": 3.0,
        "edges": 3,
        "volume": 4.0,
    }
    assert totals.loc[("baseline", "synthetic"), "trips"] == 625.0
    assert ("lane_aware", "observed") not in totals.index


def test_volume_totals_on_empty_routes():
    empty = pd.DataFrame({column: [] for column in or_.ROUTE_COLUMNS})
    totals = or_.volume_totals_by_route_type(empty)
    assert totals.empty
    assert list(totals.columns) == or_.TOTALS_COLUMNS


def test_unknown_station_ids_against_frozen_station_list_are_reported():
    # The mock trips use fixture IDs (futar_001...), none of which are real Futár IDs, so
    # against the frozen 704-station list every trip with valid times must be reported.
    trips, gps, _, edges = _simulated_inputs()
    stations = pd.read_parquet(FROZEN_STATIONS)
    routes, report = or_.convert_observed_routes(
        trips, gps, stations, matcher=_nearest_node_matcher(edges), edges=edges
    )

    assert routes.empty
    assert report["unmatched_station"] == 5
    assert report["unmatched_station_trip_ids"] == ["t01", "t02", "t03", "t04", "t06"]
    assert "ghost_999" in report["unknown_station_ids"]
    _assert_every_trip_accounted_for(report)


def test_routes_with_edges_missing_from_the_graph_are_counted():
    trips, gps, stations, edges = _simulated_inputs()
    matcher = _nearest_node_matcher(edges)

    def matcher_with_ghost_edge(points):
        matched = matcher(points)
        return matched + ["n9-n8-0"] if points["trip_id"].iloc[0] == "t03" else matched

    routes, report = or_.convert_observed_routes(
        trips, gps, stations, matcher=matcher_with_ghost_edge, edges=edges
    )

    assert report["unknown_edge"] == 1
    assert report["unknown_edge_trip_ids"] == ["t03"]
    assert report["unknown_edge_ids"] == ["n9-n8-0"]
    assert set(routes["edges"].explode()) <= set(edges["edge_id"])
    _assert_every_trip_accounted_for(report)

    # Without the edges table the check is skipped and the ghost edge reaches the routes.
    unchecked, unchecked_report = or_.convert_observed_routes(
        trips, gps, stations, matcher=matcher_with_ghost_edge
    )
    assert unchecked_report["unknown_edge"] == 0
    assert "n9-n8-0" in set(unchecked["edges"].explode())
