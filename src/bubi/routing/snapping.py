"""Snap stations to the nearest node of the street graph (groundwork for route generation).

The edges table has no node table, so node positions are read off the edges: the first point of
an edge's line is its ``u`` node and the last point is its ``v`` node (``edge_id`` is
``u-v-key``). Node ids are strings, exactly as they appear in ``edge_id``.

Distances are measured in EPSG:23700 (metres), never in degrees.
"""

from __future__ import annotations

import logging

import geopandas as gpd
import numpy as np
import pandas as pd

ANALYSIS_CRS = "EPSG:23700"
EXCHANGE_CRS = "EPSG:4326"

# A station further than this from every node is flagged instead of snapped. Not agreed yet:
# an assumption of roughly a block or two, to be tuned on the real graph.
DEFAULT_MAX_SNAP_DISTANCE_M = 200.0

logger = logging.getLogger(__name__)


def snap_stations(
    stations: pd.DataFrame,
    edges: gpd.GeoDataFrame,
    max_distance_m: float = DEFAULT_MAX_SNAP_DISTANCE_M,
) -> pd.DataFrame:
    """Snap every station to its nearest graph node.

    ``stations`` needs ``station_id``, ``lat`` and ``lon`` (see ``StationsSchema``); ``edges``
    follows ``EdgesSchema``. Returns one row per station with ``station_id``, ``node_id``,
    ``distance_m`` (to the nearest node, in metres) and ``too_far``.

    A station more than ``max_distance_m`` from every node is flagged (``too_far=True``) and gets
    no ``node_id``, so it is never snapped silently.
    """
    node_ids, node_x, node_y = _nodes(edges)
    station_x, station_y = _project(stations["lon"], stations["lat"], EXCHANGE_CRS)

    nearest = np.empty(len(stations), dtype=int)
    distance_m = np.empty(len(stations))
    for i, (x, y) in enumerate(zip(station_x, station_y)):
        to_nodes = np.hypot(node_x - x, node_y - y)
        nearest[i] = to_nodes.argmin()
        distance_m[i] = to_nodes[nearest[i]]

    # written so that a NaN distance (missing coordinates) also counts as too far
    too_far = ~(distance_m <= max_distance_m)

    snapped = pd.DataFrame(
        {
            "station_id": stations["station_id"].tolist(),
            "node_id": [None if far else node_ids[i] for i, far in zip(nearest, too_far)],
            "distance_m": distance_m,
            "too_far": too_far,
        }
    )
    if too_far.any():
        logger.warning(
            "%d station(s) are further than %.0f m from the graph and were not snapped: %s",
            too_far.sum(),
            max_distance_m,
            ", ".join(snapped.loc[snapped["too_far"], "station_id"]),
        )
    return snapped


def _split_edge_id(edge_id: str) -> tuple[str, str]:
    """The ``u`` and ``v`` node ids of an ``edge_id`` of the form ``u-v-key``."""
    parts = str(edge_id).split("-")
    if len(parts) != 3:
        raise ValueError(f"edge_id must look like 'u-v-key', got {edge_id!r}")
    return parts[0], parts[1]


def _nodes(edges: gpd.GeoDataFrame) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Node ids and their EPSG:23700 coordinates, read off the ends of the edge lines."""
    lonlat: dict[str, tuple[float, float]] = {}
    for edge_id, line in zip(edges["edge_id"], edges.geometry):
        u, v = _split_edge_id(edge_id)
        first, last = line.coords[0], line.coords[-1]
        lonlat.setdefault(u, (first[0], first[1]))
        lonlat.setdefault(v, (last[0], last[1]))
    if not lonlat:
        raise ValueError("edges table is empty: there are no nodes to snap to")

    crs = edges.crs if edges.crs is not None else EXCHANGE_CRS
    x, y = _project([p[0] for p in lonlat.values()], [p[1] for p in lonlat.values()], crs)
    return list(lonlat), x, y


def _project(x, y, crs) -> tuple[np.ndarray, np.ndarray]:
    """Project coordinates given in ``crs`` to EPSG:23700; returns x and y arrays in metres."""
    points = gpd.GeoSeries(gpd.points_from_xy(x, y), crs=crs).to_crs(ANALYSIS_CRS)
    return points.x.to_numpy(), points.y.to_numpy()
