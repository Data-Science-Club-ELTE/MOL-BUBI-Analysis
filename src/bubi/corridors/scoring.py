"""Bike-lane gap detection, edge scoring, and corridor merging."""

import geopandas as gpd
import pandas as pd


def calculate_edge_route_volumes(
    df_routes: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate total trip volume passing through each directed edge.

    Returns:
        pd.DataFrame with columns: scenario, edge_id, volume
    """
    raise NotImplementedError("Edge volume calculation not implemented yet.")


def detect_gaps_and_score_edges(
    gdf_edges: gpd.GeoDataFrame,
    df_volumes: pd.DataFrame,
    scenario: str = "baseline",
    continuity_factor: float = 1.0,
) -> pd.DataFrame:
    """Filter for missing-lane edges in given direction and score priority.

    Formula:
        score = volume * missing_gap_length_m * continuity_factor

    Returns:
        pd.DataFrame adhering to EdgeScoresSchema.
    """
    raise NotImplementedError("Gap scoring not implemented yet.")


def merge_edges_into_corridors(
    gdf_edges: gpd.GeoDataFrame,
    df_edge_scores: pd.DataFrame,
    scenario: str = "baseline",
) -> pd.DataFrame:
    """Merge contiguous directed gap edges into readable corridors and rank.

    Returns:
        pd.DataFrame adhering to CorridorsSchema.
    """
    raise NotImplementedError("Corridor merging not implemented yet.")
