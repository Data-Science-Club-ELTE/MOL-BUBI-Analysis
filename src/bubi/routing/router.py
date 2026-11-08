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


def interpolate_bridge_grade(
    grade: float,
    is_bridge: bool = False,
    is_tunnel: bool = False,
) -> float:
    """Replace false DEM grades on bridges and tunnels with zero.

    A DEM (Digital Elevation Model) samples ground or water-surface elevation,
    not the road surface.  A bridge over a river valley gets a large negative grade
    from the DEM even though the road is flat; a tunnel under a hill gets a large
    positive grade.  This function zeroes out the grade for edges tagged as bridge
    or tunnel in OSM, so ``compute_edge_weight`` does not penalise them.
    """
    if is_bridge or is_tunnel:
        return 0.0
    return grade


def build_graph(edges: gpd.GeoDataFrame, alpha: float = 3.0) -> nx.MultiDiGraph:
    """Build a weighted directed graph from the edges table.

    Each edge gets ``length_m``, ``grade``, and ``weight`` (from :func:`compute_edge_weight`)
    as attributes.  The reverse direction of an edge uses the negated grade: travelling
    downhill costs less, travelling uphill costs more.

    If the edges table contains ``is_bridge`` or ``is_tunnel`` columns, grade is
    interpolated to zero for those edges before computing the weight.
    """
    graph = nx.MultiDiGraph()
    has_grade = "grade" in edges.columns
    has_bridge = "is_bridge" in edges.columns
    has_tunnel = "is_tunnel" in edges.columns
    for _, row in edges.iterrows():
        edge_id = str(row["edge_id"])
        parts = edge_id.split("-")
        if len(parts) != 3:
            raise ValueError(f"edge_id must look like 'u-v-key', got {edge_id!r}")
        u, v = parts[0], parts[1]
        key = int(parts[2])
        length_m = float(row["length_m"])
        raw_grade = float(row.get("grade", 0.0)) if has_grade else 0.0
        is_bridge = bool(row.get("is_bridge", False)) if has_bridge else False
        is_tunnel = bool(row.get("is_tunnel", False)) if has_tunnel else False
        grade = interpolate_bridge_grade(raw_grade, is_bridge, is_tunnel)
        weight = compute_edge_weight(length_m, grade, alpha)
        graph.add_edge(u, v, key=key, length_m=length_m, grade=grade, weight=weight)
    return graph


def _shortest_path_edges(
    graph: nx.MultiDiGraph,
    source_node: str,
    target_node: str,
) -> list[str] | None:
    """Return the ordered list of edge_ids on the shortest weighted path, or None if unreachable.

    When parallel edges connect two nodes, the lightest one is chosen.  Ties are broken
    by key (lowest first) so the result is deterministic.
    """
    if source_node == target_node:
        return []
    try:
        node_path: list[str] = nx.shortest_path(graph, source_node, target_node, weight="weight")
    except nx.NetworkXNoPath:
        return None

    edge_ids: list[str] = []
    for a, b in zip(node_path[:-1], node_path[1:]):
        best_key: int | None = None
        best_weight = float("inf")
        for key in sorted(graph[a][b]):
            w = graph[a][b][key].get("weight", float("inf"))
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
            df_routes.groupby(group_cols, as_index=False, sort=False)["trip_count"]
            .sum()
            .reset_index(drop=True)
        )
    else:
        df_routes = _empty_routes()

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


def routes_from_matched_edges(
    matched: list[dict[str, Any]],
    scenario: str = "baseline",
    route_type: str = "observed",
) -> pd.DataFrame:
    """Build a ``routes`` DataFrame from pre-matched edge lists.

    This is the entry point for map-matched GPS data: the ingestion converter
    (``bubi.ingestion.observed_routes``) calls the map-matcher for each trip and
    collects the results as dicts.  This function turns them into a DataFrame that
    conforms to ``RoutesSchema``.

    Each element of *matched* must have at least:

    - ``start_station_id`` (str)
    - ``end_station_id`` (str)
    - ``edges`` (list[str]): directed edge_ids in travel order
    - ``trip_count`` (float, optional, default 1.0)

    Identical routes (same scenario, station pair, route type and edge list) are
    merged by summing ``trip_count``.

    Args:
        matched: One dict per successfully matched trip.
        scenario: Value for the ``scenario`` column (default ``"baseline"``).
        route_type: Value for the ``route_type`` column (default ``"observed"``).

    Returns:
        pd.DataFrame conforming to ``RoutesSchema``.
    """
    if not matched:
        return _empty_routes()

    rows: list[dict[str, Any]] = []
    for item in matched:
        edge_list = item["edges"]
        if isinstance(edge_list, list):
            edges_str = ",".join(str(e) for e in edge_list)
        else:
            edges_str = str(edge_list)
        rows.append(
            {
                "scenario": scenario,
                "start_station_id": str(item["start_station_id"]),
                "end_station_id": str(item["end_station_id"]),
                "route_type": route_type,
                "edges": edges_str,
                "trip_count": float(item.get("trip_count", 1.0)),
            }
        )

    df = pd.DataFrame(rows)
    group_cols = ["scenario", "start_station_id", "end_station_id", "route_type", "edges"]
    return (
        df.groupby(group_cols, as_index=False, sort=False)["trip_count"]
        .sum()
        .reset_index(drop=True)
    )


def _empty_routes() -> pd.DataFrame:
    """Return an empty DataFrame with the RoutesSchema columns."""
    return pd.DataFrame(
        columns=[
            "scenario",
            "start_station_id",
            "end_station_id",
            "route_type",
            "edges",
            "trip_count",
        ]
    )


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
