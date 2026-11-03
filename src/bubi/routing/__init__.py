"""Public routing API exports.

Only router symbols are exported at package level. Import station snapping and unroutable report
helpers from their submodules:

- ``from bubi.routing.snapping import snap_stations``
- ``from bubi.routing.report import unroutable_report``
"""

from bubi.routing.router import compute_edge_weight, route_station_pairs

__all__ = ["compute_edge_weight", "route_station_pairs"]
