"""Dijkstra shortest-path routing with slope penalty evaluation.

Conforms to Technical Design Document (Section 6.4) and task specifications:
- Dijkstra returns a route between a connected fixture pair
- Edge costs are calculated using compute_edge_weight
- Demonstrates slope penalty affects route cost or route choice
- Unreachable pairs handled gracefully without crashing
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from bubi.prototype.routing.cost import compute_edge_weight
from bubi.prototype.routing.graph import DiGraph


@dataclass
class RouteResult:
    """Result of a Dijkstra routing query."""

    found: bool
    source: Any
    target: Any
    path_nodes: List[Any] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)
    total_cost: float = float("inf")
    total_length_m: float = 0.0
    edges_data: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "found": self.found,
            "source": str(self.source),
            "target": str(self.target),
            "path_nodes": [str(n) for n in self.path_nodes],
            "edge_ids": list(self.edge_ids),
            "total_cost": self.total_cost,
            "total_length_m": self.total_length_m,
        }


def dijkstra_shortest_path(
    graph: DiGraph,
    source: Any,
    target: Any,
    alpha: float = 10.0,
    weight_fn: Optional[Callable[[Dict[str, Any]], float]] = None,
) -> RouteResult:
    """Find the shortest path between source and target using Dijkstra's algorithm.

    Edge costs are calculated using compute_edge_weight with slope penalty alpha.

    Parameters:
    - graph: DiGraph instance representing the street network.
    - source: Origin node ID.
    - target: Destination node ID.
    - alpha: Slope penalty multiplier (default: 10.0).
    - weight_fn: Optional custom edge cost function taking edge_data dict.

    Returns:
    - RouteResult: contains path nodes, traversed edge IDs, total cost, and length.
      If target is unreachable or nodes are absent, returns RouteResult with found=False.
    """
    # Check if endpoints exist in the graph
    if not graph.has_node(source) or not graph.has_node(target):
        return RouteResult(
            found=False,
            source=source,
            target=target,
            path_nodes=[],
            edge_ids=[],
            total_cost=float("inf"),
            total_length_m=0.0,
        )

    # Trivial case: source is target
    if source == target:
        return RouteResult(
            found=True,
            source=source,
            target=target,
            path_nodes=[source],
            edge_ids=[],
            total_cost=0.0,
            total_length_m=0.0,
        )

    # Priority queue: entries are (cost, current_node)
    pq: List[tuple[float, Any]] = [(0.0, source)]
    dist: Dict[Any, float] = {source: 0.0}
    predecessor: Dict[Any, Optional[Any]] = {source: None}
    edge_taken: Dict[Any, Optional[str]] = {source: None}
    edge_data_taken: Dict[Any, Optional[Dict[str, Any]]] = {source: None}
    length_accum: Dict[Any, float] = {source: 0.0}
    visited: set = set()

    while pq:
        current_cost, u = heapq.heappop(pq)

        if u == target:
            break

        if u in visited:
            continue
        visited.add(u)

        if current_cost > dist.get(u, float("inf")):
            continue

        for _, v, key, data in graph.out_edges(u):
            if v in visited:
                continue

            # Calculate edge cost
            if weight_fn is not None:
                edge_cost = float(weight_fn(data))
            else:
                length_m = float(data.get("length_m", 0.0))
                grade = float(data.get("grade", 0.0))
                edge_cost = compute_edge_weight(length_m=length_m, grade=grade, alpha=alpha)

            new_cost = current_cost + edge_cost

            if new_cost < dist.get(v, float("inf")):
                dist[v] = new_cost
                predecessor[v] = u
                edge_taken[v] = str(data.get("edge_id", f"{u}-{v}-{key}"))
                edge_data_taken[v] = dict(data)
                length_accum[v] = length_accum[u] + float(data.get("length_m", 0.0))
                heapq.heappush(pq, (new_cost, v))

    # Check if target was reached
    if target not in dist or dist[target] == float("inf"):
        # Unreachable pair handled gracefully without crashing
        return RouteResult(
            found=False,
            source=source,
            target=target,
            path_nodes=[],
            edge_ids=[],
            total_cost=float("inf"),
            total_length_m=0.0,
        )

    # Reconstruct path and edge sequences
    path_nodes = []
    edge_ids = []
    edges_data = []

    curr: Optional[Any] = target
    while curr is not None:
        path_nodes.append(curr)
        e_id = edge_taken.get(curr)
        e_data = edge_data_taken.get(curr)
        if e_id is not None:
            edge_ids.append(e_id)
        if e_data is not None:
            edges_data.append(e_data)
        curr = predecessor.get(curr)

    path_nodes.reverse()
    edge_ids.reverse()
    edges_data.reverse()

    return RouteResult(
        found=True,
        source=source,
        target=target,
        path_nodes=path_nodes,
        edge_ids=edge_ids,
        total_cost=dist[target],
        total_length_m=length_accum[target],
        edges_data=edges_data,
    )
