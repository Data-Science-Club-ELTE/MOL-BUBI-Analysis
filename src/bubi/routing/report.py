"""Report which station pairs of a trip matrix cannot be routed (groundwork for route generation).

A pair is unroutable when one of its stations was flagged too far from the graph, is not in the
snapping result at all, or when no path leads from the first station's node to the second's.
Paths are directed, so a pair can be routable one way and not the other.

Two stations snapped to the same node are routable: the route is empty, not missing.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import pandas as pd

STATION_TOO_FAR = "station_too_far"
STATION_UNKNOWN = "station_unknown"
NO_PATH = "no_path"


@dataclass(frozen=True)
class UnroutableReport:
    """Outcome of :func:`unroutable_report`."""

    total_pairs: int
    unroutable_pairs: int
    total_trips: float
    dropped_trips: float
    pairs: pd.DataFrame  # the unroutable rows of the trip matrix, plus a ``reason`` column


def unroutable_report(
    graph: nx.Graph, trips: pd.DataFrame, snapped: pd.DataFrame
) -> UnroutableReport:
    """Count the unroutable pairs of a trip matrix and the trips that would be dropped.

    ``trips`` is a trip matrix (see ``TripMatrixSchema``) and ``snapped`` is the result of
    ``snap_stations``. ``graph`` must use the same node ids, which are the strings in ``edge_id``.
    """
    flagged = set(snapped.loc[snapped["too_far"], "station_id"])
    ok = snapped[~snapped["too_far"]]
    node_of = dict(zip(ok["station_id"], ok["node_id"]))
    reachable: dict[str, set[str]] = {}  # node -> nodes reachable from it, computed once per node

    def reason(start: str, end: str) -> str | None:
        if start in flagged or end in flagged:
            return STATION_TOO_FAR
        if start not in node_of or end not in node_of:
            return STATION_UNKNOWN
        a, b = node_of[start], node_of[end]
        if not (graph.has_node(a) and graph.has_node(b)):
            return NO_PATH
        if a not in reachable:
            reachable[a] = nx.descendants(graph, a)
        return None if a == b or b in reachable[a] else NO_PATH

    reasons = [reason(s, e) for s, e in zip(trips["start_station_id"], trips["end_station_id"])]
    unroutable = trips.assign(reason=reasons)
    unroutable = unroutable[unroutable["reason"].notna()].reset_index(drop=True)
    return UnroutableReport(
        total_pairs=len(trips),
        unroutable_pairs=len(unroutable),
        total_trips=float(trips["trip_count"].sum()),
        dropped_trips=float(unroutable["trip_count"].sum()),
        pairs=unroutable,
    )
