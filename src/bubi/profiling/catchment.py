"""Catchment analysis: population covered by existing stations per walk distance and H3 resolution.

Issue #33. Distances are straight-line distances in EPSG:23700 from the H3 cell centre to the
nearest station, so they are a lower bound on real walking distance (design decision D15).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

DEFAULT_DISTANCES_M: tuple[float, ...] = (300.0, 350.0, 400.0)
DEFAULT_RESOLUTIONS: tuple[int, ...] = (8, 9, 10)
POPULATION_FLOOR = 100.0
# Rule used for the design §7.2 check: the largest centre-to-edge error of a cell (its average
# edge length, which equals the centre-to-vertex distance of a hexagon) must be at most this
# share of the walk distance. 0.5 is our reading of "small relative to the walk threshold".
MAX_CELL_TO_DISTANCE_RATIO = 0.5


def _to_eov(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    from pyproj import Transformer

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:23700", always_xy=True)
    x, y = transformer.transform(lon, lat)
    return np.column_stack([x, y])


def nearest_station_distance_m(
    cell_ids: Iterable[str], df_stations: pd.DataFrame, chunk_size: int = 5000
) -> np.ndarray:
    """Straight-line distance (m, EPSG:23700) from each H3 cell centre to the nearest station."""
    import h3

    cells = list(cell_ids)
    if not cells:
        return np.empty(0)
    if df_stations.empty:
        return np.full(len(cells), np.inf)

    latlng = np.array([h3.cell_to_latlng(c) for c in cells], dtype=float).reshape(-1, 2)
    cell_xy = _to_eov(latlng[:, 1], latlng[:, 0])
    station_xy = _to_eov(
        df_stations["lon"].to_numpy(dtype=float), df_stations["lat"].to_numpy(dtype=float)
    )

    out = np.empty(len(cell_xy))
    for start in range(0, len(cell_xy), chunk_size):
        block = cell_xy[start : start + chunk_size]
        diff = block[:, None, :] - station_xy[None, :, :]
        out[start : start + len(block)] = np.sqrt((diff**2).sum(axis=2)).min(axis=1)
    return out


def aggregate_to_parent(df_population: pd.DataFrame, resolution: int) -> pd.DataFrame:
    """Sum a population table to a coarser H3 resolution (exact; totals are preserved)."""
    import h3

    parents = df_population["cell_id"].map(lambda c: h3.cell_to_parent(c, resolution))
    out = df_population.assign(cell_id=parents).groupby("cell_id", as_index=False)["population"]
    return out.sum()


def catchment_table(
    population_by_resolution: dict[int, pd.DataFrame],
    df_stations: pd.DataFrame,
    distances_m: Iterable[float] = DEFAULT_DISTANCES_M,
    population_floor: float = POPULATION_FLOOR,
) -> pd.DataFrame:
    """Coverage numbers for every (H3 resolution, walk distance) pair.

    A cell counts as covered when its centre is within the distance of any station.
    Area is the summed area of covered cells that appear in the population table.
    """
    import h3

    rows = []
    for resolution, df in sorted(population_by_resolution.items()):
        cells = df["cell_id"].astype(str)
        pop = df["population"].astype(float).to_numpy()
        dist = nearest_station_distance_m(cells, df_stations)
        area = np.array([h3.cell_area(c, unit="km^2") for c in cells])
        total = float(pop.sum())
        for d in distances_m:
            covered = dist <= d
            outside_populated = ~covered & (pop > 0)
            outside_floor = ~covered & (pop >= population_floor)
            rows.append(
                {
                    "resolution": int(resolution),
                    "distance_m": float(d),
                    "total_population": total,
                    "covered_population": float(pop[covered].sum()),
                    "covered_share": float(pop[covered].sum() / total) if total > 0 else 0.0,
                    "covered_area_km2": float(area[covered].sum()),
                    "populated_cells_outside": int(outside_populated.sum()),
                    "outside_cells_at_floor": int(outside_floor.sum()),
                    "population_outside_at_floor": float(pop[outside_floor].sum()),
                }
            )
    return pd.DataFrame(rows)


def resolution_check(
    resolutions: Iterable[int] = DEFAULT_RESOLUTIONS,
    distances_m: Iterable[float] = DEFAULT_DISTANCES_M,
    max_ratio: float = MAX_CELL_TO_DISTANCE_RATIO,
) -> pd.DataFrame:
    """Compare average H3 cell size with each walk distance (design §7.2 rule)."""
    import h3

    rows = []
    for resolution in resolutions:
        edge = float(h3.average_hexagon_edge_length(resolution, unit="m"))
        area = float(h3.average_hexagon_area(resolution, unit="km^2"))
        for d in distances_m:
            ratio = edge / d
            rows.append(
                {
                    "resolution": int(resolution),
                    "avg_edge_m": edge,
                    "avg_area_km2": area,
                    "distance_m": float(d),
                    "edge_to_distance": ratio,
                    "passes": ratio <= max_ratio,
                }
            )
    return pd.DataFrame(rows)


def _fmt_table(df: pd.DataFrame, formats: dict[str, str]) -> list[str]:
    cols = list(formats)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.to_dict("records"):
        cells = []
        for col in cols:
            value = row[col]
            cells.append(formats[col].format(value) if formats[col] else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def build_catchment_report(
    coverage: pd.DataFrame,
    rule: pd.DataFrame,
    notes: Optional[list[str]] = None,
    map_path: Optional[str] = None,
    population_floor: float = POPULATION_FLOOR,
    max_ratio: float = MAX_CELL_TO_DISTANCE_RATIO,
) -> str:
    """Render the catchment analysis as Markdown (docs/catchment_analysis.md)."""
    lines = ["# Catchment Analysis (issue #33)", ""]
    if notes:
        lines += [f"- {n}" for n in notes] + [""]

    lines += [
        "## Method",
        "",
        "- A cell is covered when the straight-line distance from its centre to the nearest "
        "station (EPSG:23700) is at most the walk distance. Straight-line distance is a "
        "**lower bound** on walking distance (D15), so real coverage is lower than shown.",
        "- Covered area sums the areas of covered cells present in the population table.",
        f"- The {population_floor:.0f}-person floor is applied per cell, so it is stricter at "
        "fine resolutions (smaller cells) and looser at coarse ones.",
        "",
        "## Coverage by walk distance and H3 resolution",
        "",
    ]
    if coverage.empty:
        lines += ["Not computed: no population table was available.", ""]
    else:
        lines += _fmt_table(
            coverage,
            {
                "resolution": "",
                "distance_m": "{:.0f}",
                "total_population": "{:,.0f}",
                "covered_population": "{:,.0f}",
                "covered_share": "{:.1%}",
                "covered_area_km2": "{:.1f}",
                "populated_cells_outside": "{:,}",
                "outside_cells_at_floor": "{:,}",
                "population_outside_at_floor": "{:,.0f}",
            },
        )
        lines.append("")

    lines += [
        "## H3 resolution vs. walk distance (design §7.2)",
        "",
        f"Rule: average cell edge length (= largest centre-to-vertex error) at most "
        f"{max_ratio:.0%} of the walk distance.",
        "",
    ]
    lines += _fmt_table(
        rule,
        {
            "resolution": "",
            "avg_edge_m": "{:.0f}",
            "avg_area_km2": "{:.3f}",
            "distance_m": "{:.0f}",
            "edge_to_distance": "{:.2f}",
            "passes": "",
        },
    )
    lines.append("")

    if map_path:
        lines += ["## Map", "", f"Interactive map: [{map_path}]({Path(map_path).name})", ""]

    lines += [
        "## Recommendation",
        "",
        "To be written from the numbers above: state the chosen walk distance and H3 "
        "resolution, and what is given up (coverage vs. number of candidate cells, "
        "accuracy vs. cell count).",
        "",
    ]
    return "\n".join(lines)


def write_coverage_map(
    df_population: pd.DataFrame,
    df_stations: pd.DataFrame,
    distance_m: float,
    path: str | Path,
) -> Path:
    """Folium map: stations plus populated cells coloured covered / not covered."""
    import folium
    import h3

    dist = nearest_station_distance_m(df_population["cell_id"], df_stations)
    fmap = folium.Map(location=[47.4979, 19.0402], zoom_start=11, tiles="cartodbpositron")
    for cell, pop, d in zip(df_population["cell_id"], df_population["population"], dist):
        if pop <= 0:
            continue
        color = "#2b8a3e" if d <= distance_m else "#c92a2a"
        folium.Polygon(
            locations=[list(p) for p in h3.cell_to_boundary(cell)],
            color=color,
            weight=0,
            fill=True,
            fill_opacity=0.35,
            tooltip=f"{pop:,.0f} people, {d:,.0f} m",
        ).add_to(fmap)
    for _, st in df_stations.iterrows():
        folium.CircleMarker([st["lat"], st["lon"]], radius=2, color="#1c3d5a").add_to(fmap)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(out))
    return out
