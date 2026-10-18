"""Gravity-style synthetic trip demand generator."""

import pandas as pd


def assign_catchment_population(
    df_stations: pd.DataFrame,
    df_population: pd.DataFrame,
    walk_threshold_m: float = 350.0,
) -> pd.DataFrame:
    """Assign population cells to their nearest station catchment without double-counting.

    Returns:
        pd.DataFrame with columns: station_id, catchment_population
    """
    raise NotImplementedError("Catchment assignment not implemented yet.")


def generate_synthetic_trips(
    df_stations: pd.DataFrame,
    df_population: pd.DataFrame,
    scenario: str = "baseline",
    k_scaling: float = 0.05,
    beta_decay: float = 0.0015,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Generate station-to-station synthetic trip demand using a gravity model.

    Demand equation:
        trips(i -> j) proportional to P_i * P_j * exp(-beta * d_ij)
        Total demand = k * sum(P_i)

    Args:
        df_stations: Stations table adhering to StationsSchema.
        df_population: Population table adhering to PopulationSchema.
        scenario: 'baseline', 'lane_aware', or 'population_only'.
        k_scaling: Global demand scaling factor.
        beta_decay: Exponential distance decay parameter.
        random_seed: Seed for reproducibility.

    Returns:
        pd.DataFrame adhering to TripMatrixSchema.
    """
    raise NotImplementedError("Gravity trip generation not implemented yet.")
