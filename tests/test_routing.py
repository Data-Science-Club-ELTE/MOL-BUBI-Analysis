"""Tests for snapping stations to graph nodes and the unroutable-pair report."""

import networkx as nx
import pandas as pd

from bubi.routing.report import NO_PATH, STATION_TOO_FAR, STATION_UNKNOWN, unroutable_report
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
