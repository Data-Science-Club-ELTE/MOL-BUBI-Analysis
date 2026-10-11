"""Station candidate scoring and greedy spatial selection."""

import geopandas as gpd
import pandas as pd


def filter_candidate_cells(
    df_population: pd.DataFrame,
    df_stations: pd.DataFrame,
    walk_coverage_threshold_m: float = 350.0,
    min_population: float = 100.0,
) -> pd.DataFrame:
    """Filter H3 cells outside existing station walking coverage with sufficient population.

    Returns:
        pd.DataFrame of candidate cell_ids with population.
    """
    raise NotImplementedError("Candidate cell filtering not implemented yet.")


def compute_lane_connectivity(
    candidate_cell_ids: list[str],
    gdf_edges: gpd.GeoDataFrame,
) -> dict[str, float]:
    """Compute continuous lane connectivity score per candidate cell.

    Continuous measure of bike lanes reachable from the cell and connecting to existing stations.
    """
    raise NotImplementedError("Lane connectivity calculation not implemented yet.")


def select_proposed_stations(
    df_candidates: pd.DataFrame,
    scenario: str = "lane_aware",
    n_stations: int = 10,
    min_spacing_m: float = 400.0,
) -> pd.DataFrame:
    """Score candidates and greedily pick top N stations with minimum spatial spacing.

    Returns:
        pd.DataFrame adhering to StationCandidatesSchema.
    """
    raise NotImplementedError("Greedy station selection not implemented yet.")
