"""Tests for the slope-aware Dijkstra prototype, on small graphs built inline."""

from math import isclose

import pandas as pd

from bubi.routing.prototype import build_graph, shortest_route
from bubi.routing.router import compute_edge_weight

ALPHA = 10.0


def _edges(*rows: tuple[str, float, float]) -> pd.DataFrame:
    """Edges table from ``(edge_id, length_m, grade)`` rows."""
    return pd.DataFrame(rows, columns=["edge_id", "length_m", "grade"])


def _diamond() -> pd.DataFrame:
    """Two ways from 1 to 2: flat via 3 (120 m) or uphill then downhill via 4 (100 m)."""
    return _edges(
        ("1-3-0", 60.0, 0.0),
        ("3-2-0", 60.0, 0.0),
        ("1-4-0", 50.0, 0.15),
        ("4-2-0", 50.0, -0.10),
        ("98-99-0", 100.0, 0.0),  # a separate component
    )


def test_route_between_connected_nodes():
    route = shortest_route(build_graph(_diamond()), "1", "2", alpha=0.0)

    assert route is not None
    assert route.nodes == ["1", "4", "2"]
    assert route.edge_ids == ["1-4-0", "4-2-0"]
    assert isclose(route.cost, 100.0)
    assert isclose(route.length_m, 100.0)


def test_slope_penalty_changes_route_choice():
    graph = build_graph(_diamond())

    ignoring_slope = shortest_route(graph, "1", "2", alpha=0.0)
    avoiding_hill = shortest_route(graph, "1", "2", alpha=ALPHA)

    # without a penalty the shorter hilly route wins; with it, the flat detour is cheaper
    # (hilly: 50 * (1 + 10 * 0.15) + 50 = 175, flat: 120)
    assert ignoring_slope.edge_ids == ["1-4-0", "4-2-0"]
    assert avoiding_hill.edge_ids == ["1-3-0", "3-2-0"]
    assert isclose(avoiding_hill.cost, 120.0)
    assert isclose(avoiding_hill.length_m, 120.0)


def test_costs_come_from_compute_edge_weight():
    graph = build_graph(_edges(("1-2-0", 100.0, 0.05), ("2-1-0", 100.0, -0.05)))

    uphill = shortest_route(graph, "1", "2", alpha=ALPHA)
    downhill = shortest_route(graph, "2", "1", alpha=ALPHA)
    default_alpha = shortest_route(graph, "1", "2")

    assert isclose(uphill.cost, compute_edge_weight(100.0, 0.05, ALPHA))
    assert uphill.cost > uphill.length_m
    assert isclose(downhill.cost, 100.0)  # downhill is not penalised
    assert isclose(default_alpha.cost, compute_edge_weight(100.0, 0.05))


def test_missing_grade_column_means_flat():
    graph = build_graph(pd.DataFrame({"edge_id": ["1-2-0"], "length_m": [100.0]}))

    route = shortest_route(graph, "1", "2", alpha=ALPHA)

    assert isclose(route.cost, 100.0)


def test_parallel_edges_use_the_cheaper_one():
    graph = build_graph(_edges(("1-2-0", 100.0, 0.10), ("1-2-1", 120.0, 0.0)))

    short_but_steep = shortest_route(graph, "1", "2", alpha=0.0)
    flat_detour = shortest_route(graph, "1", "2", alpha=ALPHA)

    assert short_but_steep.edge_ids == ["1-2-0"]
    assert flat_detour.edge_ids == ["1-2-1"]
    assert isclose(flat_detour.cost, 120.0)


def test_unreachable_pair_returns_none():
    graph = build_graph(_diamond())

    assert shortest_route(graph, "1", "99", alpha=ALPHA) is None


def test_node_not_in_graph_returns_none():
    graph = build_graph(_diamond())

    assert shortest_route(graph, "1", "nowhere") is None
    assert shortest_route(graph, "nowhere", "1") is None


def test_same_source_and_target_is_a_zero_cost_route():
    route = shortest_route(build_graph(_diamond()), "1", "1", alpha=ALPHA)

    assert route is not None
    assert route.nodes == ["1"]
    assert route.edge_ids == []
    assert route.cost == 0.0
