"""The prototype on the real sample fixture, ``tests/fixtures/sample_edges.parquet``.

Needs the full project environment (pandera, geopandas, pyarrow) to load the fixture.
"""

from math import isclose
from pathlib import Path

from bubi.contracts.io import load_contract_table
from bubi.routing.prototype import build_graph, shortest_route
from bubi.routing.router import compute_edge_weight

FIXTURE = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "sample_edges.parquet"


def _load_edges():
    # validates against the real EdgesSchema while loading
    return load_contract_table("edges", FIXTURE)


def _length(edges, edge_id):
    return float(edges.loc[edges["edge_id"] == edge_id, "length_m"].iloc[0])


def test_fixture_builds_a_traversable_graph():
    graph = build_graph(_load_edges())

    assert graph.number_of_nodes() == 5
    assert graph.number_of_edges() == 8


def test_route_between_connected_fixture_pair():
    edges = _load_edges()

    route = shortest_route(build_graph(edges), "n3", "n4", alpha=3.0)

    # the fixture is a tree, so there is exactly one way: n3 -> n1 -> n2 -> n4
    assert route is not None
    assert route.nodes == ["n3", "n1", "n2", "n4"]
    assert route.edge_ids == ["n3-n1-0", "n1-n2-0", "n2-n4-0"]
    # the fixture has no grade column, so every edge is flat and cost equals length
    assert isclose(route.length_m, sum(_length(edges, e) for e in route.edge_ids))
    assert isclose(route.cost, route.length_m)


def test_slope_penalty_raises_route_cost_on_fixture():
    edges = _load_edges()
    edges["grade"] = 0.0
    edges.loc[edges["edge_id"] == "n1-n2-0", "grade"] = 0.10  # uphill n1 -> n2
    edges.loc[edges["edge_id"] == "n2-n1-0", "grade"] = -0.10  # downhill n2 -> n1
    graph = build_graph(edges)
    length = _length(edges, "n1-n2-0")

    no_penalty = shortest_route(graph, "n1", "n2", alpha=0.0)
    uphill = shortest_route(graph, "n1", "n2", alpha=5.0)
    downhill = shortest_route(graph, "n2", "n1", alpha=5.0)

    assert isclose(no_penalty.cost, length)
    assert isclose(uphill.cost, compute_edge_weight(length, 0.10, 5.0))
    assert uphill.cost > no_penalty.cost
    assert isclose(downhill.cost, length)
