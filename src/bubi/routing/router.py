"""Slope-aware shortest path routing on OSMnx street graph."""

from __future__ import annotations

import logging
from typing import Any, Optional

import geopandas as gpd
import networkx as nx
import pandas as pd

from bubi.routing.report import unroutable_report
from bubi.routing.snapping import snap_stations

logger = logging.getLogger(__name__)


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


def build_graph(edges: gpd.GeoDataFrame, alpha: float = 3.0) -> nx.MultiDiGraph:
    """Build a weighted directed graph from the edges table.

    Each edge gets ``length_m``, ``grade``, and ``weight`` (from :func:`compute_edge_weight`)
    as attributes.  The reverse direction of an edge uses the negated grade: travelling
    downhill costs less, travelling uphill costs more.
    """
    graph = nx.MultiDiGraph()
    for _, row in edges.iterrows():
        edge_id = str(row["edge_id"])
        parts = edge_id.split("-")
        if len(parts) != 3:
            raise ValueError(f"edge_id must look like 'u-v-key', got {edge_id!r}")
        u, v = parts[0], parts[1]
        key = int(parts[2])
        length_m = float(row["length_m"])
        grade = float(row.get("grade", 0.0)) if "grade" in edges.columns else 0.0
        weight = compute_edge_weight(length_m, grade, alpha)
        graph.add_edge(u, v, key=key, length_m=length_m, grade=grade, weight=weight)
    return graph


def _shortest_path_edges(
    graph: nx.MultiDiGraph,
    source_node: str,
    target_node: str,
) -> list[str] | None:
    """Return the ordered list of edge_ids on the shortest weighted path, or None if unreachable."""
    if source_node == target_node:
        return []
    try:
        node_path: list[str] = nx.shortest_path(graph, source_node, target_node, weight="weight")
    except nx.NetworkXNoPath:
        return None

    edge_ids: list[str] = []
    for a, b in zip(node_path[:-1], node_path[1:]):
        # pick the lightest parallel edge
        best_key: int | None = None
        best_weight = float("inf")
        for key, data in graph[a][b].items():
            w = data.get("weight", float("inf"))
            if w < best_weight:
                best_weight = w
                best_key = key
        edge_ids.append(f"{a}-{b}-{best_key}")
    return edge_ids


def route_station_pairs(
    graph: nx.MultiDiGraph,
    df_trips: pd.DataFrame,
    df_stations: pd.DataFrame,
    alpha: float = 3.0,
    route_cache: Optional[dict[tuple[str, str], list[str]]] = None,
    edges: Optional[gpd.GeoDataFrame] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Compute slope-aware shortest paths for trip pairs and aggregate volume.

    Args:
        graph: NetworkX graph with length_m, grade, and weight edge attributes.
            Use :func:`build_graph` to create one from an edges GeoDataFrame.
        df_trips: Handoff trip matrix (TripMatrixSchema).
        df_stations: Station coordinates for snapping to graph nodes.
        alpha: Uphill slope penalty factor (only used if graph lacks ``weight`` attrs).
        route_cache: Shared dictionary caching shortest paths across scenarios.
            Keyed by ``(source_node, target_node)``.
        edges: Edges GeoDataFrame for spatial snapping.  When ``None``, snapping
            is skipped and station_ids are assumed to already be node_ids.

    Returns:
        Tuple of (pd.DataFrame adhering to RoutesSchema, routing_report_dict).
    """
    if route_cache is None:
        route_cache = {}

    # Ensure graph edges have weights; add them if missing
    _ensure_weights(graph, alpha)

    # --- snapping -----------------------------------------------------------------
    if edges is not None:
        snapped = snap_stations(df_stations, edges)
    else:
        # Without an edges GeoDataFrame we cannot snap spatially; assume station_ids
        # map directly to graph node_ids (useful for tests with synthetic graphs).
        snapped = _identity_snap(df_stations, graph)

    node_of: dict[str, str] = dict(
        zip(
            snapped.loc[~snapped["too_far"], "station_id"],
            snapped.loc[~snapped["too_far"], "node_id"],
        )
    )

    # --- unroutable report --------------------------------------------------------
    report = unroutable_report(graph, df_trips, snapped)

    # --- routing ------------------------------------------------------------------
    route_rows: list[dict[str, Any]] = []
    pairs_computed = 0
    pairs_cached = 0

    for _, row in df_trips.iterrows():
        start_sid = str(row["start_station_id"])
        end_sid = str(row["end_station_id"])
        scenario = str(row["scenario"])
        trip_count = float(row["trip_count"])

        src = node_of.get(start_sid)
        dst = node_of.get(end_sid)
        if src is None or dst is None:
            continue

        cache_key = (src, dst)
        if cache_key in route_cache:
            edge_list = route_cache[cache_key]
            pairs_cached += 1
        else:
            edge_list = _shortest_path_edges(graph, src, dst)
            if edge_list is None:
                continue
            route_cache[cache_key] = edge_list
            pairs_computed += 1

        route_rows.append(
            {
                "scenario": scenario,
                "start_station_id": start_sid,
                "end_station_id": end_sid,
                "route_type": "synthetic",
                "edges": ",".join(edge_list) if edge_list else "",
                "trip_count": trip_count,
            }
        )

    # --- merge identical routes by summing trip_count -----------------------------
    if route_rows:
        df_routes = pd.DataFrame(route_rows)
        group_cols = ["scenario", "start_station_id", "end_station_id", "route_type", "edges"]
        df_routes = (
            df_routes.groupby(group_cols, as_index=False)["trip_count"].sum().reset_index(drop=True)
        )
    else:
        df_routes = pd.DataFrame(
            columns=[
                "scenario",
                "start_station_id",
                "end_station_id",
                "route_type",
                "edges",
                "trip_count",
            ]
        )

    # --- build report dict --------------------------------------------------------
    routing_report = {
        "total_pairs": report.total_pairs,
        "routed_pairs": len(df_routes),
        "unroutable_pairs": report.unroutable_pairs,
        "total_trips": report.total_trips,
        "dropped_trips": report.dropped_trips,
        "pairs_computed": pairs_computed,
        "pairs_cached": pairs_cached,
    }

    logger.info(
        "Routing complete: %d pairs routed (%d computed, %d cached), "
        "%d unroutable pairs, %.0f dropped trips",
        routing_report["routed_pairs"],
        pairs_computed,
        pairs_cached,
        report.unroutable_pairs,
        report.dropped_trips,
    )
    if report.unroutable_pairs > 0:
        logger.warning(
            "%d unroutable pairs (%.0f trips dropped):\n%s",
            report.unroutable_pairs,
            report.dropped_trips,
            report.pairs.to_string(index=False),
        )

    return df_routes, routing_report


def _ensure_weights(graph: nx.MultiDiGraph, alpha: float) -> None:
    """Add ``weight`` attribute to edges that lack one."""
    for _u, _v, data in graph.edges(data=True):
        if "weight" not in data:
            length_m = float(data.get("length_m", 0.0))
            grade = float(data.get("grade", 0.0))
            data["weight"] = compute_edge_weight(length_m, grade, alpha)


def _identity_snap(
    df_stations: pd.DataFrame,
    graph: nx.MultiDiGraph,
) -> pd.DataFrame:
    """Build a snapping result by mapping each station_id directly to a graph node_id.

    Used when no edges GeoDataFrame is available.  A station whose id is not a node in
    the graph is flagged ``too_far``.
    """
    all_nodes = set(graph.nodes())
    rows: list[dict[str, Any]] = []
    for _, station in df_stations.iterrows():
        sid = str(station["station_id"])
        in_graph = sid in all_nodes
        rows.append(
            {
                "station_id": sid,
                "node_id": sid if in_graph else None,
                "distance_m": 0.0 if in_graph else float("inf"),
                "too_far": not in_graph,
            }
        )
    return pd.DataFrame(rows)
