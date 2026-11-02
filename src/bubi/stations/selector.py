"""Station candidate scoring and greedy spatial selection.

Definitions live in docs/station_lane_connectivity.md.
"""

from __future__ import annotations

from typing import Optional

import geopandas as gpd
import h3
import networkx as nx
import numpy as np
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point

_TO_EOV = Transformer.from_crs("EPSG:4326", "EPSG:23700", always_xy=True)


def _cell_xy(cell_ids) -> np.ndarray:
    latlng = np.array([h3.cell_to_latlng(c) for c in cell_ids]).reshape(-1, 2)
    x, y = _TO_EOV.transform(latlng[:, 1], latlng[:, 0])
    return np.column_stack([x, y])


def _norm(values: pd.Series) -> pd.Series:
    """Log-scale normalisation to [0, 1]; 0 stays 0 (no connection -> score 0)."""
    v = np.log1p(values.astype(float).clip(lower=0))
    top = v.max()
    return v / top if top > 0 else v * 0.0


def filter_candidate_cells(
    df_population: pd.DataFrame,
    df_stations: pd.DataFrame,
    walk_coverage_threshold_m: float = 350.0,
    min_population: float = 100.0,
) -> pd.DataFrame:
    """Filter H3 cells outside existing station walking coverage with sufficient population.

    Coverage is straight-line distance from the cell centre to the nearest station
    (a lower bound on walking distance; swap in the walking graph once available).

    Returns:
        pd.DataFrame of candidate cell_ids with population.
    """
    pop = df_population[df_population["population"] >= min_population].reset_index(drop=True)
    if pop.empty:
        return pop[["cell_id", "population"]]
    st_x, st_y = _TO_EOV.transform(df_stations["lon"].to_numpy(), df_stations["lat"].to_numpy())
    st_xy = np.column_stack([st_x, st_y])
    d = np.linalg.norm(_cell_xy(pop["cell_id"])[:, None, :] - st_xy[None, :, :], axis=2).min(axis=1)
    return pop[d > walk_coverage_threshold_m][["cell_id", "population"]].reset_index(drop=True)


def _lane_edges_projected(gdf_edges: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Dedicated-lane edges in EPSG:23700, one row per undirected segment."""
    g = gdf_edges[gdf_edges["has_dedicated_lane"]].copy()
    if g.empty:
        return g
    g = g.set_crs("EPSG:4326") if g.crs is None else g
    g = g.to_crs("EPSG:23700")
    # a lane in either direction counts for connectivity; drop the reverse duplicate
    ends = g.geometry.apply(
        lambda ln: tuple(
            sorted([tuple(np.round(ln.coords[0], 1)), tuple(np.round(ln.coords[-1], 1))])
        )
    )
    g["_key"] = list(zip(g["osm_way_id"], ends))
    return g.drop_duplicates("_key").reset_index(drop=True)


def compute_lane_connectivity(
    candidate_cell_ids: list[str],
    gdf_edges: gpd.GeoDataFrame,
    df_stations: Optional[pd.DataFrame] = None,
    reach_m: float = 400.0,
    station_attach_m: float = 200.0,
) -> dict[str, float]:
    """Compute continuous lane connectivity score per candidate cell.

    lane_connectivity(c) = metres of dedicated bike lane within ``reach_m`` of the cell
    centre that belong to a lane network touching an existing station
    (a station is "touched" if a lane lies within ``station_attach_m`` of it).
    If ``df_stations`` is None the station condition is skipped (pure lane length).
    Cells with no such lane get exactly 0.0.
    """
    result = {c: 0.0 for c in candidate_cell_ids}
    lanes = _lane_edges_projected(gdf_edges)
    if lanes.empty or not candidate_cell_ids:
        return result

    if df_stations is not None:
        # connected components of the lane network (nodes = rounded line endpoints)
        graph = nx.Graph()
        for idx, ln in zip(lanes.index, lanes.geometry):
            a, b = tuple(np.round(ln.coords[0], 1)), tuple(np.round(ln.coords[-1], 1))
            graph.add_edge(a, b, idx=idx)
        comp_of_edge: dict[int, int] = {}
        for ci, comp in enumerate(nx.connected_components(graph)):
            for u, v, data in graph.subgraph(comp).edges(data=True):
                comp_of_edge[data["idx"]] = ci
        lanes["_comp"] = lanes.index.map(comp_of_edge)

        sx, sy = _TO_EOV.transform(df_stations["lon"].to_numpy(), df_stations["lat"].to_numpy())
        attached: set[int] = set()
        for x, y in zip(sx, sy):
            near = lanes[lanes.geometry.distance(Point(x, y)) <= station_attach_m]
            attached.update(near["_comp"].tolist())
        lanes = lanes[lanes["_comp"].isin(attached)]
        if lanes.empty:
            return result

    for cell, (x, y) in zip(candidate_cell_ids, _cell_xy(candidate_cell_ids)):
        circle = Point(x, y).buffer(reach_m)
        near = lanes[lanes.geometry.intersects(circle)]
        result[cell] = float(near.geometry.intersection(circle).length.sum())
    return result


def select_proposed_stations(
    df_candidates: pd.DataFrame,
    scenario: str = "lane_aware",
    n_stations: int = 10,
    min_spacing_m: float = 400.0,
) -> pd.DataFrame:
    """Score candidates and greedily pick top N stations with minimum spatial spacing.

    ``df_candidates`` needs cell_id, population and (for lane_aware) lane_connectivity.
        lane_aware:      score = norm(population) * norm(lane_connectivity)
        population_only: score = norm(population)
    Selected cells get rank 1..N; the rest keep rank = <NA>. Cells with score 0 are never
    selected.

    Returns:
        pd.DataFrame adhering to StationCandidatesSchema.
    """
    df = df_candidates.copy().reset_index(drop=True)
    pop_n = _norm(df["population"])
    if scenario == "lane_aware":
        df["score"] = pop_n * _norm(df["lane_connectivity"])
    elif scenario == "population_only":
        df["lane_connectivity"] = np.nan
        df["score"] = pop_n
    else:
        raise ValueError(f"scenario must be lane_aware or population_only, got {scenario!r}")

    xy = _cell_xy(df["cell_id"]) if len(df) else np.empty((0, 2))
    order = df.sort_values(["score", "population", "cell_id"], ascending=[False, False, True]).index
    chosen: list[int] = []
    for i in order:
        if len(chosen) == n_stations or df.at[i, "score"] <= 0:
            break
        if all(np.linalg.norm(xy[i] - xy[j]) >= min_spacing_m for j in chosen):
            chosen.append(i)

    df["rank"] = pd.array([pd.NA] * len(df), dtype="Int64")
    for r, i in enumerate(chosen, start=1):
        df.at[i, "rank"] = r
    df["scenario"] = scenario
    cols = ["scenario", "cell_id", "population", "lane_connectivity", "score", "rank"]
    return df[cols]
