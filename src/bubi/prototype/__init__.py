"""MOL Bubi Bike-Lane & Station Recommendation Tool - Core Package."""

from bubi.prototype.contracts.schemas import EdgesSchema, RoutesSchema, SchemaError
from bubi.prototype.routing.cost import compute_edge_weight
from bubi.prototype.routing.dijkstra import RouteResult, dijkstra_shortest_path
from bubi.prototype.routing.engine import RouteReport, SyntheticRouteEngine
from bubi.prototype.routing.graph import DiGraph, load_graph_from_edges

__version__ = "0.1.0"

__all__ = [
    "EdgesSchema",
    "RoutesSchema",
    "SchemaError",
    "compute_edge_weight",
    "dijkstra_shortest_path",
    "RouteResult",
    "DiGraph",
    "load_graph_from_edges",
    "SyntheticRouteEngine",
    "RouteReport",
]
