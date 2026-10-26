"""Prototype: slope-aware Dijkstra routing on the street edge graph.

Builds a ``networkx.MultiDiGraph`` from an ``edges`` table (see ``EdgesSchema``) and finds the
cheapest route between two nodes, where every edge costs
``compute_edge_weight(length_m, grade, alpha)``.

This is a self-contained prototype. It is not wired into ``route_station_pairs`` (the full route
engine: snapping stations to nodes, caching, merging) and nothing else imports it.

Conventions:
- Node ids are the ``u`` and ``v`` parts of ``edge_id`` (``u-v-key``), kept as strings.
- ``grade`` is signed and belongs to the directed edge (uphill is positive). The ``edges`` table
  does not carry it yet, so a missing ``grade`` column means every edge is flat.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import pandas as pd

from bubi.routing.router import compute_edge_weight


@dataclass(frozen=True)
class Route:
    """A route found by :func:`shortest_route`."""

    nodes: list[str]
    edge_ids: list[str]  # ordered, as in the ``routes`` table
    cost: float  # slope-penalised cost
    length_m: float  # plain length, without the penalty


def _split_edge_id(edge_id: str) -> tuple[str, str, int]:
    """Split ``"u-v-key"`` into ``(u, v, key)``."""
    parts = str(edge_id).split("-")
    if len(parts) != 3:
        raise ValueError(f"edge_id must look like 'u-v-key', got {edge_id!r}")
    u, v, key = parts
    return u, v, int(key)


def build_graph(edges: pd.DataFrame) -> nx.MultiDiGraph:
    """Build a directed multigraph from an ``edges`` table.

    Needs ``edge_id`` and ``length_m``. Uses ``grade`` if present, otherwise every edge is flat.
    """
    grades = edges["grade"] if "grade" in edges.columns else [0.0] * len(edges)
    graph = nx.MultiDiGraph()
    for edge_id, length_m, grade in zip(edges["edge_id"], edges["length_m"], grades):
        u, v, key = _split_edge_id(edge_id)
        graph.add_edge(u, v, key=key, edge_id=edge_id, length_m=float(length_m), grade=float(grade))
    return graph


def _edge_cost(attrs: dict, alpha: float | None) -> float:
    """Cost of one edge. ``alpha=None`` uses the default of ``compute_edge_weight``."""
    if alpha is None:
        return compute_edge_weight(attrs["length_m"], attrs["grade"])
    return compute_edge_weight(attrs["length_m"], attrs["grade"], alpha)


def shortest_route(
    graph: nx.MultiDiGraph, source: str, target: str, alpha: float | None = None
) -> Route | None:
    """Cheapest route from ``source`` to ``target``, or ``None`` if there is none.

    ``None`` covers both an unreachable target and a node that is not in the graph. When two
    nodes are joined by parallel edges, the cheaper one is used.
    """

    def weight(u: str, v: str, parallel: dict[int, dict]) -> float:
        # networkx passes a multigraph weight function {key: attrs} for all edges u -> v
        return min(_edge_cost(attrs, alpha) for attrs in parallel.values())

    try:
        cost, nodes = nx.single_source_dijkstra(graph, source, target, weight=weight)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None

    edge_ids: list[str] = []
    length_m = 0.0
    for u, v in zip(nodes, nodes[1:]):
        best = min(graph[u][v].values(), key=lambda attrs: _edge_cost(attrs, alpha))
        edge_ids.append(best["edge_id"])
        length_m += best["length_m"]
    return Route(nodes=nodes, edge_ids=edge_ids, cost=cost, length_m=length_m)
