"""Public routing API exports.

Only router symbols are exported at package level. Import station snapping and unroutable report
helpers from their submodules:

- ``from bubi.routing.snapping import snap_stations``
- ``from bubi.routing.report import unroutable_report``
"""

from bubi.routing.router import (
    build_graph,
    compute_edge_weight,
    interpolate_bridge_grade,
    route_station_pairs,
    routes_from_matched_edges,
)

__all__ = [
    "build_graph",
    "compute_edge_weight",
    "interpolate_bridge_grade",
    "route_station_pairs",
    "routes_from_matched_edges",
]
