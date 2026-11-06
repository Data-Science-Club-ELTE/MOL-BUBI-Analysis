"""Gravity-style synthetic trip demand generator.

Model (see docs/gravity_model_spec.md):

    T_ij = C * P_i * P_j * exp(-beta * d_ij)        for i != j
    sum_ij T_ij = k * sum_i P_i                      (fixes C)

P_i is the catchment population of station i, d_ij is the straight-line distance in
metres (EPSG:23700) between stations i and j. The output is an *expected* trip count,
so it is deterministic; ``random_seed`` is kept in the signature for the day a sampling
step is added.
"""

from __future__ import annotations

import h3
import numpy as np
import pandas as pd
from pyproj import Transformer

_TO_EOV = Transformer.from_crs("EPSG:4326", "EPSG:23700", always_xy=True)


def _project(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    x, y = _TO_EOV.transform(lon, lat)
    return np.column_stack([x, y])


def assign_catchment_population(
    df_stations: pd.DataFrame,
    df_population: pd.DataFrame,
    walk_threshold_m: float = 350.0,
) -> pd.DataFrame:
    """Assign population cells to their nearest station catchment without double-counting.

    Each H3 cell goes to exactly one station: the nearest one by centroid distance.
    Cells farther than ``walk_threshold_m`` from every station are unserved and dropped.

    Returns:
        pd.DataFrame with columns: station_id, catchment_population
        (one row per station, 0.0 if nobody is assigned).
    """
    stations = df_stations.reset_index(drop=True)
    if df_population.empty:
        return pd.DataFrame({"station_id": stations["station_id"], "catchment_population": 0.0})

    centers = np.array([h3.cell_to_latlng(c) for c in df_population["cell_id"]])
    cell_xy = _project(centers[:, 1], centers[:, 0])
    st_xy = _project(stations["lon"].to_numpy(), stations["lat"].to_numpy())

    dist = np.linalg.norm(cell_xy[:, None, :] - st_xy[None, :, :], axis=2)  # cells x stations
    nearest = dist.argmin(axis=1)
    served = dist[np.arange(len(dist)), nearest] <= walk_threshold_m

    pop = df_population["population"].to_numpy(dtype=float)
    totals = np.zeros(len(stations))
    np.add.at(totals, nearest[served], pop[served])
    return pd.DataFrame(
        {"station_id": stations["station_id"].astype(str), "catchment_population": totals}
    )


def generate_synthetic_trips(
    df_stations: pd.DataFrame,
    df_population: pd.DataFrame,
    scenario: str = "baseline",
    k_scaling: float = 0.05,
    beta_decay: float = 0.0015,
    random_seed: int = 42,
    walk_threshold_m: float = 350.0,
) -> pd.DataFrame:
    """Generate station-to-station synthetic trip demand using a gravity model.

    Demand equation:
        trips(i -> j) proportional to P_i * P_j * exp(-beta * d_ij)
        Total demand = k * sum(P_i)

    ``df_stations`` must already hold the scenario's full station set (existing plus any
    proposed ``new:<cell_id>`` stations); this function does not pick stations.

    Returns:
        pd.DataFrame adhering to TripMatrixSchema.
    """
    del random_seed  # expected-value model: no randomness yet
    cols = ["scenario", "start_station_id", "end_station_id", "trip_count"]

    catch = assign_catchment_population(df_stations, df_population, walk_threshold_m)
    stations = df_stations.reset_index(drop=True).copy()
    stations["station_id"] = stations["station_id"].astype(str)
    stations = stations.merge(catch, on="station_id")
    stations = stations[stations["catchment_population"] > 0].reset_index(drop=True)
    if len(stations) < 2:
        return pd.DataFrame(columns=cols)

    p = stations["catchment_population"].to_numpy()
    xy = _project(stations["lon"].to_numpy(), stations["lat"].to_numpy())
    d = np.linalg.norm(xy[:, None, :] - xy[None, :, :], axis=2)

    weights = np.outer(p, p) * np.exp(-beta_decay * d)
    np.fill_diagonal(weights, 0.0)  # no same-station trips
    trips = weights * (k_scaling * p.sum() / weights.sum())

    i, j = np.nonzero(trips)
    out = pd.DataFrame(
        {
            "scenario": scenario,
            "start_station_id": stations["station_id"].to_numpy()[i],
            "end_station_id": stations["station_id"].to_numpy()[j],
            "trip_count": trips[i, j],
        }
    )
    return out[cols].reset_index(drop=True)
