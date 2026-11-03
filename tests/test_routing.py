"""Tests for snapping stations to graph nodes and the unroutable-pair report."""

import networkx as nx
import pandas as pd

from bubi.routing.report import NO_PATH, STATION_TOO_FAR, STATION_UNKNOWN, unroutable_report
from bubi.routing.router import build_graph, compute_edge_weight, route_station_pairs
from bubi.routing.snapping import snap_stations

# the sample stations lie exactly on the nodes of the sample edges: futar_00k is node nk
FAR_STATION = {"station_id": "far_away", "name": "Far away", "lat": 47.54, "lon": 19.00}
# 0.0002 degrees (about 22 m) north of node n2, which is futar_002
NEAR_N2 = {"station_id": "near_n2", "name": "Near n2", "lat": 47.4895, "lon": 19.0617}


def _graph(edges) -> nx.MultiDiGraph:
    """Street graph from an edges table, using the u and v parts of each edge_id."""
    graph = nx.MultiDiGraph()
    for edge_id in edges["edge_id"]:
        u, v, key = edge_id.split("-")
        graph.add_edge(u, v, key=int(key))
    return graph


def _trips(*rows: tuple[str, str, float]) -> pd.DataFrame:
    """Trip matrix from ``(start, end, trip_count)`` rows."""
    return pd.DataFrame(
        [("baseline", start, end, count) for start, end, count in rows],
        columns=["scenario", "start_station_id", "end_station_id", "trip_count"],
    )


def _snapped(**node_of: str | None) -> pd.DataFrame:
    """Snapping result by hand: ``station_id=node`` pairs, ``None`` meaning too far."""
    return pd.DataFrame(
        {
            "station_id": list(node_of),
            "node_id": list(node_of.values()),
            "distance_m": 0.0,
            "too_far": [node is None for node in node_of.values()],
        }
    )


# --- snapping -------------------------------------------------------------------------------


def test_stations_snap_to_their_nearest_node(sample_stations, sample_edges):
    snapped = snap_stations(sample_stations, sample_edges)

    assert dict(zip(snapped["station_id"], snapped["node_id"])) == {
        "futar_001": "n1",
        "futar_002": "n2",
        "futar_003": "n3",
        "futar_004": "n4",
        "futar_005": "n5",
    }
    assert not snapped["too_far"].any()
    assert (snapped["distance_m"] < 1.0).all()


def test_distance_is_in_metres_and_threshold_decides_the_flag(sample_edges):
    stations = pd.DataFrame([NEAR_N2])

    within = snap_stations(stations, sample_edges, max_distance_m=30.0)
    beyond = snap_stations(stations, sample_edges, max_distance_m=10.0)

    assert within["node_id"].tolist() == ["n2"]
    assert 20.0 < within["distance_m"].iloc[0] < 25.0
    assert not within["too_far"].iloc[0]
    assert beyond["too_far"].iloc[0]


def test_station_too_far_from_the_graph_is_flagged_not_snapped(sample_stations, sample_edges):
    stations = pd.concat([sample_stations, pd.DataFrame([FAR_STATION])], ignore_index=True)

    snapped = snap_stations(stations, sample_edges).set_index("station_id")

    assert snapped.loc["far_away", "too_far"]
    assert pd.isna(snapped.loc["far_away", "node_id"])
    assert snapped.loc["far_away", "distance_m"] > 1000.0
    assert not snapped.drop(index="far_away")["too_far"].any()


# --- unroutable-pair report -----------------------------------------------------------------


def test_normal_pairs_are_all_routable(sample_stations, sample_edges, sample_trip_matrix):
    snapped = snap_stations(sample_stations, sample_edges)

    report = unroutable_report(_graph(sample_edges), sample_trip_matrix, snapped)

    assert report.total_pairs == len(sample_trip_matrix)
    assert report.unroutable_pairs == 0
    assert report.dropped_trips == 0.0
    assert report.total_trips == sample_trip_matrix["trip_count"].sum()
    assert report.pairs.empty


def test_pairs_with_a_station_too_far_from_the_graph_are_dropped(
    sample_stations, sample_edges, sample_trip_matrix
):
    stations = pd.concat([sample_stations, pd.DataFrame([FAR_STATION])], ignore_index=True)
    trips = pd.concat(
        [
            sample_trip_matrix,
            _trips(("far_away", "futar_001", 40.0), ("futar_002", "far_away", 7.0)),
        ],
        ignore_index=True,
    )
    snapped = snap_stations(stations, sample_edges)

    report = unroutable_report(_graph(sample_edges), trips, snapped)

    assert report.total_pairs == len(sample_trip_matrix) + 2
    assert report.unroutable_pairs == 2
    assert report.dropped_trips == 47.0
    assert report.pairs["reason"].tolist() == [STATION_TOO_FAR, STATION_TOO_FAR]


def test_disconnected_pair_is_unroutable():
    graph = nx.MultiDiGraph([("n1", "n2"), ("n2", "n1"), ("x1", "x2"), ("x2", "x1")])
    snapped = _snapped(a="n1", b="n2", island="x1")
    trips = _trips(("a", "b", 5.0), ("a", "island", 30.0), ("island", "a", 12.0))

    report = unroutable_report(graph, trips, snapped)

    assert report.total_pairs == 3
    assert report.unroutable_pairs == 2
    assert report.total_trips == 47.0
    assert report.dropped_trips == 42.0
    assert report.pairs["reason"].tolist() == [NO_PATH, NO_PATH]


def test_one_way_street_is_routable_in_one_direction_only():
    graph = nx.MultiDiGraph([("n1", "n2")])
    snapped = _snapped(a="n1", b="n2")

    report = unroutable_report(graph, _trips(("a", "b", 3.0), ("b", "a", 4.0)), snapped)

    assert report.unroutable_pairs == 1
    assert report.dropped_trips == 4.0
    assert report.pairs[["start_station_id", "end_station_id"]].values.tolist() == [["b", "a"]]


def test_station_missing_from_the_snapping_result_is_reported():
    graph = nx.MultiDiGraph([("n1", "n2")])

    report = unroutable_report(graph, _trips(("a", "ghost", 9.0)), _snapped(a="n1"))

    assert report.unroutable_pairs == 1
    assert report.dropped_trips == 9.0
    assert report.pairs["reason"].tolist() == [STATION_UNKNOWN]


# --- route_station_pairs (issue #36) --------------------------------------------------------


def _weighted_graph() -> nx.MultiDiGraph:
    """Build a small directed graph with length_m and grade for routing tests.

    Graph:
        A ---> B (500m, grade=0.0)   flat
        B ---> A (500m, grade=0.0)   flat
        A ---> C (400m, grade=0.05)  uphill A->C
        C ---> A (400m, grade=-0.05) downhill C->A (negated grade)
        B ---> C (300m, grade=0.0)   flat

    With alpha=3.0:
        A->B weight = 500 * (1 + 0) = 500
        B->A weight = 500 * (1 + 0) = 500
        A->C weight = 400 * (1 + 3*0.05) = 400 * 1.15 = 460
        C->A weight = 400 * (1 + 0) = 400  (grade=-0.05, max(0, -0.05)=0)
        B->C weight = 300 * (1 + 0) = 300
    """
    g = nx.MultiDiGraph()
    g.add_edge("A", "B", key=0, length_m=500.0, grade=0.0)
    g.add_edge("B", "A", key=0, length_m=500.0, grade=0.0)
    g.add_edge("A", "C", key=0, length_m=400.0, grade=0.05)
    g.add_edge("C", "A", key=0, length_m=400.0, grade=-0.05)
    g.add_edge("B", "C", key=0, length_m=300.0, grade=0.0)
    return g


def _station_df(*ids: str) -> pd.DataFrame:
    """Station DataFrame where station_ids are the same as node_ids (identity snap)."""
    return pd.DataFrame({"station_id": list(ids)})


def test_connected_pair_is_routed():
    """A connected pair produces a route with the correct edges and trip_count."""
    graph = _weighted_graph()
    stations = _station_df("A", "B")
    trips = _trips(("A", "B", 10.0))

    df_routes, report = route_station_pairs(graph, trips, stations, alpha=3.0)

    assert len(df_routes) == 1
    assert report["routed_pairs"] == 1
    assert report["unroutable_pairs"] == 0
    assert report["dropped_trips"] == 0.0

    row = df_routes.iloc[0]
    assert row["start_station_id"] == "A"
    assert row["end_station_id"] == "B"
    assert row["route_type"] == "synthetic"
    assert row["trip_count"] == 10.0
    assert row["edges"] == "A-B-0"


def test_unreachable_pair_is_reported():
    """An unreachable pair (disconnected island) is dropped and reported."""
    graph = _weighted_graph()
    # Add an isolated node
    graph.add_node("island")
    stations = _station_df("A", "island")
    trips = _trips(("A", "island", 25.0), ("island", "A", 15.0))

    df_routes, report = route_station_pairs(graph, trips, stations, alpha=3.0)

    assert len(df_routes) == 0
    assert report["routed_pairs"] == 0
    assert report["unroutable_pairs"] == 2
    assert report["dropped_trips"] == 40.0


def test_flat_versus_uphill_route_prefers_flat():
    """Dijkstra with slope penalty picks the flat path over the shorter uphill one.

    From A to C:
        - Direct: A->C = 400m * (1 + 3*0.05) = 460 (uphill)
        - Via B:  A->B + B->C = 500 + 300 = 800 (flat, but longer)

    Direct (460) < via-B (800), so the direct uphill route wins despite the penalty.
    But let's make a graph where the flat path actually wins.
    """
    g = nx.MultiDiGraph()
    # Direct path: short but steep uphill
    g.add_edge("A", "C", key=0, length_m=200.0, grade=0.3)  # 200*(1+3*0.3)=200*1.9=380
    # Flat detour: longer but no grade
    g.add_edge("A", "B", key=0, length_m=150.0, grade=0.0)  # 150*(1+0)=150
    g.add_edge("B", "C", key=0, length_m=150.0, grade=0.0)  # 150*(1+0)=150
    # Flat via-B total: 300; direct uphill: 380 => flat wins

    stations = _station_df("A", "B", "C")
    trips = _trips(("A", "C", 5.0))

    df_routes, _report = route_station_pairs(g, trips, stations, alpha=3.0)

    assert len(df_routes) == 1
    # Should pick the flat detour A->B->C over the direct uphill A->C
    assert df_routes.iloc[0]["edges"] == "A-B-0,B-C-0"


def test_reverse_direction_uses_negated_grade():
    """Downhill direction (negated grade) gets no penalty, producing a cheaper route.

    A->C uphill:   400*(1+3*0.05) = 460
    C->A downhill: 400*(1+0)      = 400  (grade=-0.05, clamped to 0)
    """
    graph = _weighted_graph()
    stations = _station_df("A", "C")
    trips = _trips(("A", "C", 7.0), ("C", "A", 3.0))

    df_routes, _report = route_station_pairs(graph, trips, stations, alpha=3.0)

    assert len(df_routes) == 2
    ac_route = df_routes[df_routes["start_station_id"] == "A"].iloc[0]
    ca_route = df_routes[df_routes["start_station_id"] == "C"].iloc[0]

    # Both take the direct edge (it's the only path with those directions)
    assert ac_route["edges"] == "A-C-0"
    assert ca_route["edges"] == "C-A-0"


def test_route_cache_avoids_recomputation():
    """Cache is populated on first call and reused on second call for the same node pair."""
    graph = _weighted_graph()
    stations = _station_df("A", "B")
    cache: dict[tuple[str, str], list[str]] = {}

    trips1 = _trips(("A", "B", 10.0))
    _df1, report1 = route_station_pairs(graph, trips1, stations, route_cache=cache)
    assert report1["pairs_computed"] == 1
    assert report1["pairs_cached"] == 0
    assert ("A", "B") in cache

    trips2 = _trips(("A", "B", 20.0))
    _df2, report2 = route_station_pairs(graph, trips2, stations, route_cache=cache)
    assert report2["pairs_computed"] == 0
    assert report2["pairs_cached"] == 1


def test_identical_routes_merged_by_summing_trip_count():
    """Two trip-matrix rows for the same pair in the same scenario are merged."""
    graph = _weighted_graph()
    stations = _station_df("A", "B")
    trips = pd.DataFrame(
        [
            ("baseline", "A", "B", 10.0),
            ("baseline", "A", "B", 5.0),
        ],
        columns=["scenario", "start_station_id", "end_station_id", "trip_count"],
    )

    df_routes, _report = route_station_pairs(graph, trips, stations, alpha=3.0)

    assert len(df_routes) == 1
    assert df_routes.iloc[0]["trip_count"] == 15.0


def test_output_validates_against_routes_schema():
    """Output DataFrame passes RoutesSchema validation with route_type='synthetic'."""
    from bubi.contracts.schemas import RoutesSchema

    graph = _weighted_graph()
    stations = _station_df("A", "B", "C")
    trips = _trips(("A", "B", 10.0), ("B", "C", 5.0))

    df_routes, _report = route_station_pairs(graph, trips, stations, alpha=3.0)

    # Should not raise
    RoutesSchema.validate(df_routes)
    assert (df_routes["route_type"] == "synthetic").all()


def test_same_station_pair_produces_empty_edge_list():
    """A trip from a station to itself produces a route with an empty edge list."""
    graph = _weighted_graph()
    stations = _station_df("A")
    trips = _trips(("A", "A", 2.0))

    df_routes, report = route_station_pairs(graph, trips, stations, alpha=3.0)

    assert len(df_routes) == 1
    assert df_routes.iloc[0]["edges"] == ""
    assert report["routed_pairs"] == 1


def test_route_station_pairs_with_edges_geodataframe(
    sample_stations, sample_edges, sample_trip_matrix
):
    """Full integration: build graph from edges GeoDataFrame, snap stations, route."""
    graph = build_graph(sample_edges, alpha=3.0)

    df_routes, report = route_station_pairs(
        graph, sample_trip_matrix, sample_stations, alpha=3.0, edges=sample_edges
    )

    assert report["unroutable_pairs"] == 0
    assert report["routed_pairs"] > 0
    assert len(df_routes) > 0
    assert (df_routes["route_type"] == "synthetic").all()
    assert (df_routes["trip_count"] > 0).all()


def test_build_graph_sets_correct_weights(sample_edges):
    """build_graph produces edges with the correct compute_edge_weight values."""
    graph = build_graph(sample_edges, alpha=3.0)

    for u, v, key, data in graph.edges(keys=True, data=True):
        expected = compute_edge_weight(data["length_m"], data["grade"], alpha=3.0)
        assert data["weight"] == expected, f"edge {u}-{v}-{key}"
