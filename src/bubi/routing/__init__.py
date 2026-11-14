"""Public routing API exports.

Only router symbols are exported at package level. Import station snapping and unroutable report
helpers from their submodules:

- ``from bubi.routing.snapping import snap_stations``
- ``from bubi.routing.report import unroutable_report``
"""

from bubi.routing.map_matching import CorridorMatcher, make_corridor_matcher
from bubi.routing.router import (
    build_graph,
    compute_edge_weight,
    interpolate_bridge_grade,
    route_station_pairs,
)

__all__ = [
    "CorridorMatcher",
    "build_graph",
    "compute_edge_weight",
    "interpolate_bridge_grade",
    "make_corridor_matcher",
    "route_station_pairs",
]
