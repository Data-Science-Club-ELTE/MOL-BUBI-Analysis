"""Slope-aware shortest path routing on OSMnx street graph."""

from typing import Any, Optional

import networkx as nx
import pandas as pd


def compute_edge_weight(
    length_m: float,
    grade: float,
    alpha: float = 3.0,
) -> float:
    """Compute slope-penalized edge weight.

    Formula:
        cost = length_m * (1 + alpha * max(0, grade))
    """
    uphill_penalty = alpha * max(0.0, grade)
    return length_m * (1.0 + uphill_penalty)


def route_station_pairs(
    graph: nx.MultiDiGraph,
    df_trips: pd.DataFrame,
    df_stations: pd.DataFrame,
    alpha: float = 3.0,
    route_cache: Optional[dict[tuple[str, str], list[str]]] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compute slope-aware shortest paths for trip pairs and aggregate volume.

    Args:
        graph: NetworkX graph with length and grade edge attributes.
        df_trips: Handoff trip matrix (TripMatrixSchema).
        df_stations: Station coordinates for snapping to graph nodes.
        alpha: Uphill slope penalty factor.
        route_cache: Shared dictionary caching shortest paths across scenarios.

    Returns:
        Tuple of (pd.DataFrame adhering to RoutesSchema, routing_report_dict).
    """
    raise NotImplementedError(
        "Slope-aware routing not implemented yet. Implement snapping, Dijkstra, and route aggregation."
    )
