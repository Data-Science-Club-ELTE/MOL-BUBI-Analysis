"""Lane-connectivity pass-rate test (Task #16, week 2).

Question answered: if lane connectivity were a *hard filter* instead of a continuous
score, how many candidate cells would survive? Run on real OSM edges to decide.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from bubi.stations.selector import compute_lane_connectivity, filter_candidate_cells


def lane_connectivity_pass_rate(
    df_population: pd.DataFrame,
    df_stations: pd.DataFrame,
    gdf_edges: gpd.GeoDataFrame,
    reach_m_grid: tuple[float, ...] = (200.0, 300.0, 400.0, 600.0),
    min_lane_m_grid: tuple[float, ...] = (0.0, 100.0, 250.0),
    walk_coverage_threshold_m: float = 350.0,
    min_population: float = 100.0,
    station_attach_m: float = 200.0,
) -> pd.DataFrame:
    """Share of candidate cells that would pass a hard lane-connectivity filter.

    A cell "passes" if lane_connectivity > min_lane_m. Reported per reach radius, per
    minimum lane length, with and without the "connected to an existing station" condition,
    both as share of cells and share of candidate population.
    """
    cand = filter_candidate_cells(
        df_population, df_stations, walk_coverage_threshold_m, min_population
    )
    rows = []
    for with_station in (False, True):
        for reach in reach_m_grid:
            conn = compute_lane_connectivity(
                cand["cell_id"].tolist(),
                gdf_edges,
                df_stations if with_station else None,
                reach_m=reach,
                station_attach_m=station_attach_m,
            )
            vals = cand["cell_id"].map(conn)
            for min_lane in min_lane_m_grid:
                passed = vals > min_lane
                rows.append(
                    {
                        "station_connected": with_station,
                        "reach_m": reach,
                        "min_lane_m": min_lane,
                        "n_candidates": len(cand),
                        "n_pass": int(passed.sum()),
                        "pass_rate": float(passed.mean()) if len(cand) else float("nan"),
                        "pop_weighted_pass_rate": (
                            float(cand.loc[passed, "population"].sum() / cand["population"].sum())
                            if len(cand)
                            else float("nan")
                        ),
                    }
                )
    return pd.DataFrame(rows)
