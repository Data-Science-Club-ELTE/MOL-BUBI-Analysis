"""Corridor-constrained shortest path map-matching seam (docs/map_matching_plan.md)."""

from __future__ import annotations

from collections import Counter

import geopandas as gpd
import pandas as pd


class CorridorMatcher:
    """Map-match one GPS trace to edges of the frozen graph (docs/map_matching_plan.md).

    Attributes:
        edges: Directed graph edges (GeoDataFrame adhering to EdgesSchema).
        study_area_bbox: Bounding box (min_lon, min_lat, max_lon, max_lat).
        buffer_m: Search corridor half-width in metres.
        max_gap_m: Maximum allowed straight-line gap between consecutive points.
        drops: Counter of unmatchable trace reasons ('outside_study_area', 'gap', 'no_path_in_corridor').
        suspect: List of trip IDs whose matched length ratio falls outside the expected band.
    """

    def __init__(
        self,
        edges: gpd.GeoDataFrame,
        study_area_bbox: tuple[float, float, float, float],
        buffer_m: float = 50.0,
        max_gap_m: float = 250.0,
    ) -> None:
        self.edges = edges
        self.study_area_bbox = study_area_bbox
        self.buffer_m = buffer_m
        self.max_gap_m = max_gap_m
        self.drops: Counter[str] = Counter()
        self.suspect: list[str] = []

    def __call__(self, points: pd.DataFrame) -> list[str]:
        """Match one trip's GPS points to directed edge IDs in travel order.

        Args:
            points: One trip's GPS points sorted by UTC timestamp, with columns
                ['trip_id', 'timestamp', 'lat', 'lon', 'timestamp_utc'].

        Returns:
            List of directed edge_id strings (u-v-key) in travel order, or an empty
            list if unmatchable.
        """
        raise NotImplementedError(
            "CorridorMatcher algorithm is tracked in the follow-up map-matching issue. "
            "See docs/map_matching_plan.md."
        )


def make_corridor_matcher(
    edges: gpd.GeoDataFrame,
    study_area_bbox: tuple[float, float, float, float],
    buffer_m: float = 50.0,
    max_gap_m: float = 250.0,
) -> CorridorMatcher:
    """Create a CorridorMatcher instance for the frozen street graph.

    Args:
        edges: Directed edges table conforming to EdgesSchema.
        study_area_bbox: (min_lon, min_lat, max_lon, max_lat).
        buffer_m: Corridor buffer radius in metres (default: 50.0 m).
        max_gap_m: Maximum gap between consecutive GPS points in metres (default: 250.0 m).

    Returns:
        Callable CorridorMatcher instance matching the MapMatcher protocol expected
        by bubi.ingestion.observed_routes.convert_observed_routes.
    """
    return CorridorMatcher(
        edges=edges,
        study_area_bbox=study_area_bbox,
        buffer_m=buffer_m,
        max_gap_m=max_gap_m,
    )
