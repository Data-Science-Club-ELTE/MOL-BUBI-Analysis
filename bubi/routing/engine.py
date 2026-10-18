"""Synthetic route engine managing Dijkstra routing, caching, merging, and reporting.

Conforms to Technical Design Document (Section 6.4) and RoutesSchema contract (Section 5):
- Routes cached by station pair across queries/scenarios
- Merging identical routes by summing trip_count
- Reporting unroutable pairs and dropped trips
- Emitting routes conforming to RoutesSchema (route_type = 'synthetic')
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from bubi.contracts.schemas import RoutesSchema
from bubi.io.parquet import Table
from bubi.routing.dijkstra import RouteResult, dijkstra_shortest_path
from bubi.routing.graph import DiGraph


@dataclass
class RouteReport:
    """Execution summary report for synthetic route generation."""

    total_pairs: int = 0
    routed_pairs: int = 0
    unroutable_pairs: int = 0
    total_trips: float = 0.0
    routed_trips: float = 0.0
    dropped_trips: float = 0.0
    unroutable_details: List[Dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        """Formatted string summary of routing run."""
        return (
            f"Routing Report: {self.routed_pairs}/{self.total_pairs} pairs routed "
            f"({self.unroutable_pairs} unroutable). "
            f"Trips: {self.routed_trips:.1f}/{self.total_trips:.1f} routed "
            f"({self.dropped_trips:.1f} dropped)."
        )


class SyntheticRouteEngine:
    """Route engine computing synthetic bike routes with slope awareness and caching."""

    def __init__(
        self,
        graph: DiGraph,
        alpha: float = 10.0,
        scenario: str = "prototype",
        shared_cache: Optional[Dict[Tuple[Any, Any], RouteResult]] = None,
    ):
        self.graph = graph
        self.alpha = float(alpha)
        self.scenario = str(scenario)
        # Shared cache for station pairs across scenarios (Design Doc Section 6.4)
        self.cache: Dict[Tuple[Any, Any], RouteResult] = (
            shared_cache if shared_cache is not None else {}
        )

    def route_pair(self, start_station_id: Any, end_station_id: Any) -> RouteResult:
        """Find the shortest slope-aware path for a station pair, using cache if available."""
        pair_key = (start_station_id, end_station_id)
        if pair_key in self.cache:
            return self.cache[pair_key]

        res = dijkstra_shortest_path(
            graph=self.graph,
            source=start_station_id,
            target=end_station_id,
            alpha=self.alpha,
        )
        self.cache[pair_key] = res
        return res

    def process_trips(
        self,
        trip_requests: Sequence[Dict[str, Any]],
        validate_schema: bool = True,
    ) -> Tuple[List[Dict[str, Any]], RouteReport]:
        """Process a collection of trip demands between station pairs.

        Input records must contain:
        - start_station_id (str/int)
        - end_station_id (str/int)
        - trip_count (int/float, optional, default: 1.0)
        - scenario (str, optional, defaults to engine's scenario)

        Returns:
        - Tuple of (merged_routes_records, RouteReport)
          where merged_routes_records conforms to RoutesSchema.
        """
        report = RouteReport()

        # Temporary map for merging identical routes:
        # key = (scenario, start_station_id, end_station_id, route_type, tuple(edge_ids))
        merged_routes: Dict[Tuple[str, str, str, str, Tuple[str, ...]], float] = {}

        for req in trip_requests:
            start_id = req["start_station_id"]
            end_id = req["end_station_id"]
            trips = float(req.get("trip_count", 1.0))
            scen = str(req.get("scenario", self.scenario))

            report.total_pairs += 1
            report.total_trips += trips

            result = self.route_pair(start_id, end_id)

            if not result.found:
                # Unroutable pair handled gracefully without crashing
                report.unroutable_pairs += 1
                report.dropped_trips += trips
                report.unroutable_details.append({
                    "start_station_id": str(start_id),
                    "end_station_id": str(end_id),
                    "trip_count": trips,
                    "reason": "no_path_found",
                })
                continue

            report.routed_pairs += 1
            report.routed_trips += trips

            # Merge identical routes by summing trip_count
            route_key = (
                scen,
                str(start_id),
                str(end_id),
                "synthetic",
                tuple(result.edge_ids),
            )
            merged_routes[route_key] = merged_routes.get(route_key, 0.0) + trips

        # Format output conforming to RoutesSchema
        output_records: List[Dict[str, Any]] = []
        for (scen, start_id, end_id, r_type, edges_tuple), total_trips in merged_routes.items():
            output_records.append({
                "scenario": scen,
                "start_station_id": start_id,
                "end_station_id": end_id,
                "route_type": r_type,
                "edges": list(edges_tuple),
                "trip_count": total_trips,
            })

        if validate_schema and output_records:
            RoutesSchema.validate(output_records)

        return output_records, report

    def to_routes_table(self, records: List[Dict[str, Any]]) -> Table:
        """Convert output route records to a validated Table instance."""
        if records:
            RoutesSchema.validate(records)
            cols = {
                "scenario": [r["scenario"] for r in records],
                "start_station_id": [r["start_station_id"] for r in records],
                "end_station_id": [r["end_station_id"] for r in records],
                "route_type": [r["route_type"] for r in records],
                "edges": [r["edges"] for r in records],
                "trip_count": [r["trip_count"] for r in records],
            }
            return Table(cols)
        return Table({
            "scenario": [],
            "start_station_id": [],
            "end_station_id": [],
            "route_type": [],
            "edges": [],
            "trip_count": [],
        })
