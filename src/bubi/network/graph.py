"""OSM Street & Walking network extraction and per-direction bike-lane model."""

from pathlib import Path
from typing import Optional

import geopandas as gpd
import networkx as nx


def build_street_network(
    bbox: tuple[float, float, float, float],
    network_type: str = "bike",
    elevation_dem_path: Optional[Path] = None,
) -> tuple[nx.MultiDiGraph, gpd.GeoDataFrame]:
    """Download Budapest street network via OSMnx and build per-direction lane model.

    Args:
        bbox: (min_lon, min_lat, max_lon, max_lat)
        network_type: "bike" or "all"
        elevation_dem_path: Optional path to elevation raster (DEM) to add grades.

    Returns:
        Tuple of (NetworkX directed graph, GeoDataFrame adhering to EdgesSchema).
    """
    raise NotImplementedError(
        "OSM extraction not implemented yet. Implement download, lane-tag parser, and grade assignment."
    )


def extract_per_direction_edges(graph: nx.MultiDiGraph) -> gpd.GeoDataFrame:
    """Extract directed edges with per-direction has_dedicated_lane flag."""
    raise NotImplementedError("Per-direction edge extractor not implemented yet.")
