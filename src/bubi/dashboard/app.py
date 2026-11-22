"""Interactive Streamlit + Folium dashboard for MOL Bubi recommendations.

The layout follows ``WIREFRAME.md``. It reads the contract tables through
:mod:`bubi.dashboard.data` (pipeline outputs or sample fixtures, never an external
API) and shows a clear message instead of crashing when data is missing or invalid.
Week 2 draws the whole Budapest street network as one GeoJSON layer coloured by
per-direction lane status, with a legend. Week 4 adds GeoJSON & CSV exports with
demo-mode provenance labels and explicit blocked-state notices. Week 5 adds the
scenario difference layers, robustness labels, and comparison panel.

Run with ``make dashboard``.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, replace
from html import escape
from pathlib import Path
from typing import Any

import folium
import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import shapely
import streamlit as st
from branca.element import Element, MacroElement, Template
from pyproj import Transformer
from streamlit_folium import st_folium

from bubi.corridors.scoring import calculate_edge_route_volumes
from bubi.dashboard.data import (
    BUDAPEST_CENTER,
    DATA_DIR_ENV,
    EXPORTS_DIR,
    SCENARIOS,
    DashboardData,
    DashboardDataError,
    as_id_list,
    cell_center,
    fixture_notes,
    for_scenario,
    load_config,
    load_dashboard_data,
    proposed_stations,
    resolve_table_paths,
)
from bubi.scenarios.runner import (
    LABEL_ROBUST,
    LABEL_STATION_DEPENDENT,
    build_scenario_comparison_view,
)

LANE_COLOR = "#2b8a3e"  # lane exists in this direction
NO_LANE_COLOR = "#adb5bd"  # no lane in this direction
GAP_COLOR = "#e8590c"  # priority corridor (gap)
STATION_COLOR = "#1c7ed6"
PROPOSED_COLOR = "#2b8a3e"
DIFF_NEW_STATION_COLOR = "#0b7285"  # distinct colour for "new: proposed" stations in diff mode
POPULATION_COLOR = "#f08c00"
ROBUST_COLOR = "#1971c2"
STATION_DEP_COLOR = "#f76707"
RANK_IMPROVED_COLOR = "#2f9e44"
RANK_WORSENED_COLOR = "#e03131"
RANK_NEW_TOPK_COLOR = "#ae3ec9"

DEMO_MODE_LABEL = "Synthetic demo data (D5): algorithm demonstration, not observed cycling"
FIXTURE_SCALE_NOTICE = (
    "Fixture-scale data: loaded from sample fixtures until full Budapest network "
    "ingestion (#15) merges."
)

# Route volume is a magnitude, so one hue from light to dark. Violet stays clear of the
# station blue, lane green/grey and corridor orange; every step keeps >= 2.6:1 contrast
# on both basemaps, so the lightest class is still visible.
ROUTE_RAMP = ("#9775fa", "#7950f2", "#5f3dc4", "#4527a0")
ROUTE_WEIGHTS = (2.5, 4.0, 5.5, 7.5)
# Further out than the lane lines (LANE_OFFSET_M) so a route never hides the lane colour.
ROUTE_OFFSET_M = 10.0
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
ROUTE_FIELDS = ("id", "volume", "heading", "lane", "step", "coords")
EMPTY_ROUTE_DATA = json.dumps(dict.fromkeys(ROUTE_FIELDS, []))

LANE_WEIGHT = 4
NO_LANE_WEIGHT = 2.5
# Both directions of a street share one geometry; each is drawn this far to the
# right of its direction of travel so the two sit side by side.
LANE_OFFSET_M = 4.0
METRIC_CRS = "EPSG:32634"  # UTM zone 34N, metres, covers Budapest
HUNGARIAN_CRS = "EPSG:23700"  # EOV / HD72, used for straight-line coverage distance (D15)
DEFAULT_WALK_COVERAGE_M = 350.0
SIMPLIFY_M = 1.0
# About 1 m. Rounding coordinates keeps the city-wide layer small enough to load quickly.
COORD_PRECISION = 1e-5

# Colours are picked in the browser, so the page carries no per-edge style data.
LANE_STYLE_JS = (
    "function (feature) {\n"
    '  var lane = feature.properties.lane === "yes";\n'
    "  return {\n"
    f'    color: lane ? "{LANE_COLOR}" : "{NO_LANE_COLOR}",\n'
    f"    weight: lane ? {LANE_WEIGHT} : {NO_LANE_WEIGHT},\n"
    "    opacity: 0.85\n"
    "  };\n"
    "}"
)

# CartoDB basemaps now need an API key; both of these work without one.
BASEMAPS = {
    "OpenStreetMap": {"tiles": "OpenStreetMap"},
    "Light grey (Esri)": {
        "tiles": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
            "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        ),
        "attr": "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
        # tiles stop at zoom 16; Leaflet scales them up beyond that
        "max_native_zoom": 16,
        "max_zoom": 19,
    },
}

# Required by the source licences; see docs/source_inventory.md.
DATA_ATTRIBUTION = (
    "Data source: BKK Zrt., "
    "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). "
    "Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) (ODbL). "
    "Population: WorldPop R2025A v1, constrained, 2026 (ODbL)."
)

SCENARIO_HELP = {
    "baseline": "Existing Futár stations only.",
    "lane_aware": "Existing + proposed stations scored by population × lane connectivity.",
    "population_only": "Existing + proposed stations scored by population only.",
}


@dataclass
class Settings:
    scenario: str
    basemap: str
    show_stations: bool
    show_proposed: bool
    show_population: bool
    show_lanes: bool
    show_routes: bool
    show_corridors: bool
    top_n: int
    show_diff: bool = False
    walk_coverage_m: float = DEFAULT_WALK_COVERAGE_M


@dataclass
class ScenarioSummary:
    """Single rebuilt state object holding comparison view and metrics across scenarios."""

    top_k: int
    walk_coverage_m: float
    comparison_view: pd.DataFrame
    corridor_labels: dict[tuple[str, str], str]
    edge_labels: dict[str, str]
    metrics_table: pd.DataFrame
    jaccard_table: pd.DataFrame
    newly_served_cells_by_scenario: dict[str, pd.DataFrame]
    new_corridors_by_scenario: dict[str, pd.DataFrame]
    rank_changes_by_scenario: dict[str, pd.DataFrame]
    notes: list[str]


# ---------------------------------------------------------------- data access


@st.cache_data(show_spinner="Loading data tables…")
def _cached_load(data_dir_override: str | None, files_changed_at: float) -> DashboardData:
    """Cached per data folder; ``files_changed_at`` makes the cache reload after data changes."""
    return load_dashboard_data()


@st.cache_resource(show_spinner="Preparing the street layer…")
def _cached_lane_geojson(data_dir_override: str | None, files_changed_at: float) -> str:
    return lane_status_geojson(_cached_load(data_dir_override, files_changed_at).get("edges"))


@st.cache_resource(show_spinner="Preparing the route-volume layer…")
def _cached_route_layer(
    data_dir_override: str | None, files_changed_at: float, scenario: str
) -> RouteLayer:
    """Built once per scenario, so toggling layers or switching back is instant."""
    data = _cached_load(data_dir_override, files_changed_at)
    return route_volume_layer(data.get("edges"), for_scenario(data.get("routes"), scenario))


def _latest_change() -> float:
    paths = [path for path, _ in resolve_table_paths().values() if path.exists()]
    return max((path.stat().st_mtime for path in paths), default=0.0)


def edge_ids_of_corridors(corridors: pd.DataFrame) -> set[str]:
    ids: set[str] = set()
    for value in corridors.get("edge_ids", []):
        ids.update(as_id_list(value))
    return ids


def route_volume_per_edge(routes: pd.DataFrame) -> pd.Series:
    """Total trips crossing each directed edge in the given routes (one scenario).

    Uses the corridor module's counting rules, so the map shows the same volumes that
    corridor scoring ranks: a route that passes an edge twice counts once.

    Raises:
        ValueError: if the routes table is malformed (see ``calculate_edge_route_volumes``).
    """
    if routes.empty:
        return pd.Series(dtype=float)
    volumes = calculate_edge_route_volumes(routes)
    return volumes.groupby("edge_id")["volume"].sum()


# ---------------------------------------------------------------- scenario comparison & diff logic


def newly_served_population_cells(
    population: pd.DataFrame | None,
    stations: pd.DataFrame | None,
    proposed: pd.DataFrame | None,
    walk_coverage_m: float = DEFAULT_WALK_COVERAGE_M,
) -> pd.DataFrame:
    """H3 cells within ``walk_coverage_m`` of a proposed station and outside existing stations.

    Uses straight-line distance in EPSG:23700 (design decision D15).
    """
    empty = pd.DataFrame(columns=["cell_id", "population"])
    if population is None or population.empty or proposed is None or proposed.empty:
        return empty

    prop_coords = [cell_center(str(cid)) for cid in proposed["cell_id"]]
    prop_coords = [c for c in prop_coords if c is not None]
    if not prop_coords:
        return empty

    cell_rows = []
    for _, row in population.iterrows():
        center = cell_center(str(row["cell_id"]))
        if center is not None:
            cell_rows.append((str(row["cell_id"]), float(row["population"]), center[0], center[1]))
    if not cell_rows:
        return empty

    transformer = Transformer.from_crs("EPSG:4326", HUNGARIAN_CRS, always_xy=True)

    c_lats = np.array([r[2] for r in cell_rows], dtype=float)
    c_lons = np.array([r[3] for r in cell_rows], dtype=float)
    cx, cy = transformer.transform(c_lons, c_lats)

    p_lats = np.array([c[0] for c in prop_coords], dtype=float)
    p_lons = np.array([c[1] for c in prop_coords], dtype=float)
    px, py = transformer.transform(p_lons, p_lats)

    dist_prop = np.hypot(cx[:, None] - px[None, :], cy[:, None] - py[None, :])
    near_proposed = (dist_prop <= walk_coverage_m).any(axis=1)

    if stations is not None and not stations.empty:
        s_lats = stations["lat"].to_numpy(dtype=float)
        s_lons = stations["lon"].to_numpy(dtype=float)
        sx, sy = transformer.transform(s_lons, s_lats)
        dist_existing = np.hypot(cx[:, None] - sx[None, :], cy[:, None] - sy[None, :])
        near_existing = (dist_existing <= walk_coverage_m).any(axis=1)
    else:
        near_existing = np.zeros(len(cell_rows), dtype=bool)

    mask = near_proposed & (~near_existing)
    if not mask.any():
        return empty

    selected = [
        {"cell_id": cell_rows[i][0], "population": cell_rows[i][1]} for i in np.flatnonzero(mask)
    ]
    return pd.DataFrame(selected)


def corridors_absent_from_baseline(
    corridors: pd.DataFrame | None,
    scenario: str,
    top_k: int = 10,
) -> pd.DataFrame:
    """Corridors present in ``scenario`` (top-k) whose directed edges are absent from baseline."""
    if corridors is None or corridors.empty or scenario == "baseline":
        return pd.DataFrame(columns=["corridor_id", "edge_ids", "score", "rank"])
    scen_top = for_scenario(corridors, scenario).sort_values("rank").head(top_k)
    if scen_top.empty:
        return scen_top
    base_top = for_scenario(corridors, "baseline").sort_values("rank").head(top_k)
    baseline_edges = edge_ids_of_corridors(base_top)
    if not baseline_edges:
        return scen_top.copy()

    keep = [
        not set(as_id_list(row["edge_ids"])).issubset(baseline_edges)
        for _, row in scen_top.iterrows()
    ]
    return scen_top.loc[keep].copy()


def edge_rank_changes(
    edge_scores: pd.DataFrame | None,
    scenario: str,
    top_k: int = 10,
) -> pd.DataFrame:
    """Compare edge ranks between ``scenario`` and ``baseline`` by ``edge_id``."""
    cols = ["edge_id", "baseline_rank", "scenario_rank", "rank_delta", "change_type"]
    if edge_scores is None or edge_scores.empty or scenario == "baseline":
        return pd.DataFrame(columns=cols)

    base = for_scenario(edge_scores, "baseline")[["edge_id", "rank"]].rename(
        columns={"rank": "baseline_rank"}
    )
    scen = for_scenario(edge_scores, scenario)[["edge_id", "rank"]].rename(
        columns={"rank": "scenario_rank"}
    )
    if scen.empty:
        return pd.DataFrame(columns=cols)

    merged = pd.merge(scen, base, on="edge_id", how="outer")
    rows = []
    for _, r in merged.iterrows():
        b_rank = None if pd.isna(r["baseline_rank"]) else int(r["baseline_rank"])
        s_rank = None if pd.isna(r["scenario_rank"]) else int(r["scenario_rank"])
        in_s_top = s_rank is not None and s_rank <= top_k
        in_b_top = b_rank is not None and b_rank <= top_k
        if not in_s_top and not in_b_top:
            continue
        if in_s_top and not in_b_top:
            change = "new_top_k"
            delta = None if b_rank is None else b_rank - s_rank
        elif b_rank is not None and s_rank is not None and s_rank < b_rank:
            change = "improved"
            delta = b_rank - s_rank
        elif b_rank is not None and s_rank is not None and s_rank > b_rank:
            change = "worsened"
            delta = b_rank - s_rank
        else:
            continue
        rows.append(
            {
                "edge_id": str(r["edge_id"]),
                "baseline_rank": b_rank,
                "scenario_rank": s_rank,
                "rank_delta": delta,
                "change_type": change,
            }
        )
    return pd.DataFrame(rows, columns=cols)


def pairwise_topk_jaccard(
    edge_scores: pd.DataFrame | None,
    corridors: pd.DataFrame | None,
    top_k: int = 10,
) -> pd.DataFrame:
    """Pairwise Jaccard overlap (M14) between top-k directed edge sets across scenarios."""
    edge_sets: dict[str, set[str]] = {}
    for scenario in SCENARIOS:
        if edge_scores is not None and not edge_scores.empty:
            sub = for_scenario(edge_scores, scenario)
            edge_sets[scenario] = set(sub.loc[sub["rank"] <= top_k, "edge_id"].astype(str))
        elif corridors is not None and not corridors.empty:
            sub = for_scenario(corridors, scenario).sort_values("rank").head(top_k)
            edge_sets[scenario] = edge_ids_of_corridors(sub)
        else:
            edge_sets[scenario] = set()

    pairs = [
        ("baseline", "lane_aware"),
        ("baseline", "population_only"),
        ("lane_aware", "population_only"),
    ]
    rows = []
    for a, b in pairs:
        sa, sb = edge_sets[a], edge_sets[b]
        union = sa | sb
        jaccard = (len(sa & sb) / len(union)) if union else 0.0
        rows.append(
            {
                "scenario_a": a,
                "scenario_b": b,
                "shared_edges": len(sa & sb),
                "union_edges": len(union),
                "jaccard_overlap_m14": round(jaccard, 3),
            }
        )
    return pd.DataFrame(rows)


def build_scenario_summary(
    data: DashboardData,
    top_k: int = 10,
    walk_coverage_m: float = DEFAULT_WALK_COVERAGE_M,
) -> ScenarioSummary:
    """Build a single consistent state object for all scenarios, layers, and metrics."""
    notes: list[str] = []
    edge_scores = data.get("edge_scores")
    corridors = data.get("corridors")
    stations = data.get("stations")
    population = data.get("population")
    edges = data.get("edges")

    comparison_view = pd.DataFrame()
    corridor_labels: dict[tuple[str, str], str] = {}
    edge_labels: dict[str, str] = {}

    if (
        edge_scores is not None
        and not edge_scores.empty
        and corridors is not None
        and not corridors.empty
    ):
        try:
            comparison_view = build_scenario_comparison_view(edge_scores, corridors, top_k=top_k)
            edge_sub = comparison_view[comparison_view["level"] == "edge"]
            edge_labels = dict(zip(edge_sub["item_id"].astype(str), edge_sub["label"].astype(str)))

            corr_groups = comparison_view[comparison_view["level"] == "corridor"]
            for scenario in SCENARIOS:
                scen_corrs = for_scenario(corridors, scenario)
                for _, crow in scen_corrs.iterrows():
                    c_edges = set(as_id_list(crow["edge_ids"]))
                    matched_label = LABEL_STATION_DEPENDENT
                    for _, grow in corr_groups.iterrows():
                        if c_edges & set(grow["edge_ids"] or []):
                            matched_label = str(grow["label"])
                            break
                    corridor_labels[(scenario, str(crow["corridor_id"]))] = matched_label
        except ValueError as err:
            notes.append(f"Scenario comparison view could not be built: {err}")
    elif corridors is not None and not corridors.empty:
        # Fallback edge-based classification from corridors when edge_scores is missing.
        top_sets = {
            s: edge_ids_of_corridors(for_scenario(corridors, s).sort_values("rank").head(top_k))
            for s in SCENARIOS
        }
        all_edges = set().union(*top_sets.values())
        for eid in all_edges:
            count = sum(eid in top_sets[s] for s in SCENARIOS)
            edge_labels[eid] = LABEL_ROBUST if count == len(SCENARIOS) else LABEL_STATION_DEPENDENT
        for scenario in SCENARIOS:
            for _, crow in for_scenario(corridors, scenario).iterrows():
                c_edges = set(as_id_list(crow["edge_ids"]))
                is_rob = bool(c_edges) and all(edge_labels.get(e) == LABEL_ROBUST for e in c_edges)
                corridor_labels[(scenario, str(crow["corridor_id"]))] = (
                    LABEL_ROBUST if is_rob else LABEL_STATION_DEPENDENT
                )

    routes_all = data.get("routes")
    base_routes = for_scenario(routes_all, "baseline")
    baseline_trips = float(base_routes["trip_count"].sum()) if not base_routes.empty else 0.0

    newly_served_cells_by_scenario: dict[str, pd.DataFrame] = {}
    new_corridors_by_scenario: dict[str, pd.DataFrame] = {}
    rank_changes_by_scenario: dict[str, pd.DataFrame] = {}
    metric_rows = []

    for scenario in SCENARIOS:
        prop = proposed_stations(data, scenario)
        scen_corridors = for_scenario(corridors, scenario)
        scen_top_corridors = (
            scen_corridors.sort_values("rank").head(top_k)
            if not scen_corridors.empty
            else scen_corridors
        )
        scen_routes = for_scenario(routes_all, scenario)
        trips = float(scen_routes["trip_count"].sum()) if not scen_routes.empty else 0.0

        if edges is not None and not edges.empty and not scen_top_corridors.empty:
            c_edges = edges[edges["edge_id"].isin(edge_ids_of_corridors(scen_top_corridors))]
            no_lane_m = float(c_edges.loc[~c_edges["has_dedicated_lane"], "length_m"].sum())
            corridor_km = no_lane_m / 1000.0
        else:
            corridor_km = 0.0

        if scenario == "baseline":
            newly_cells = pd.DataFrame(columns=["cell_id", "population"])
            m1_pop = 0.0
            m6_pop_per_km: float | None = None
            m11_demand_per_person: float | None = None
            m13_robust_share: float | None = None
        else:
            newly_cells = newly_served_population_cells(
                population, stations, prop, walk_coverage_m=walk_coverage_m
            )
            m1_pop = float(newly_cells["population"].sum()) if not newly_cells.empty else 0.0
            m6_pop_per_km = (m1_pop / corridor_km) if (m1_pop > 0 and corridor_km > 0) else None
            trip_delta = trips - baseline_trips
            m11_demand_per_person = (trip_delta / m1_pop) if m1_pop > 0 else None

            if edge_scores is not None and not edge_scores.empty:
                scen_top_edges = set(
                    for_scenario(edge_scores, scenario)
                    .loc[lambda d: d["rank"] <= top_k, "edge_id"]
                    .astype(str)
                )
            else:
                scen_top_edges = edge_ids_of_corridors(scen_top_corridors)
            if scen_top_edges:
                robust_count = sum(edge_labels.get(e) == LABEL_ROBUST for e in scen_top_edges)
                m13_robust_share = round(robust_count / len(scen_top_edges), 3)
            else:
                m13_robust_share = None

        newly_served_cells_by_scenario[scenario] = newly_cells
        new_corridors_by_scenario[scenario] = corridors_absent_from_baseline(
            corridors, scenario, top_k=top_k
        )
        rank_changes_by_scenario[scenario] = edge_rank_changes(edge_scores, scenario, top_k=top_k)

        metric_rows.append(
            {
                "scenario": scenario,
                "proposed_stations": len(prop),
                "corridors": len(scen_corridors),
                "new_corridors_vs_baseline": len(new_corridors_by_scenario[scenario]),
                "corridor_km": round(corridor_km, 2),
                "synthetic_trips_abs": round(trips, 1),
                "newly_served_pop_m1": round(m1_pop, 0),
                "pop_per_corridor_km_m6": round(m6_pop_per_km, 1)
                if m6_pop_per_km is not None
                else None,
                "demand_per_newly_served_m11": round(m11_demand_per_person, 3)
                if m11_demand_per_person is not None
                else None,
                "robust_corridor_share_m13": m13_robust_share,
            }
        )

    jaccard_table = pairwise_topk_jaccard(edge_scores, corridors, top_k=top_k)
    return ScenarioSummary(
        top_k=top_k,
        walk_coverage_m=walk_coverage_m,
        comparison_view=comparison_view,
        corridor_labels=corridor_labels,
        edge_labels=edge_labels,
        metrics_table=pd.DataFrame(metric_rows),
        jaccard_table=jaccard_table,
        newly_served_cells_by_scenario=newly_served_cells_by_scenario,
        new_corridors_by_scenario=new_corridors_by_scenario,
        rank_changes_by_scenario=rank_changes_by_scenario,
        notes=notes,
    )


# ---------------------------------------------------------------- map helpers


def offset_line(
    coords: list[tuple[float, float]], meters: float = 4.0
) -> list[tuple[float, float]]:
    """Shift a (lon, lat) line a few metres to its right and return (lat, lon) points.

    Both directions of a street share one geometry, so without the shift the
    reverse direction would be drawn exactly on top of the forward one.
    """
    if len(coords) < 2:
        return [(lat, lon) for lon, lat in coords]
    (lon0, lat0), (lon1, lat1) = coords[0], coords[-1]
    lat_m = 111_320.0
    lon_m = 111_320.0 * math.cos(math.radians((lat0 + lat1) / 2))
    dx, dy = (lon1 - lon0) * lon_m, (lat1 - lat0) * lat_m
    length = math.hypot(dx, dy) or 1.0
    # right-hand normal of the direction of travel
    off_lon, off_lat = (dy / length) * meters / lon_m, (-dx / length) * meters / lat_m
    return [(lat + off_lat, lon + off_lon) for lon, lat in coords]


def shift_right(lines: np.ndarray, distance: float) -> np.ndarray:
    """Move every vertex of each line ``distance`` to the right of travel.

    ``lines`` are LineStrings in a metric CRS. Each vertex moves along the average
    right-hand normal of the segments next to it. On sharp bends the shift is a little
    shorter than ``distance``, which is invisible at a few metres. This is about ten
    times faster than ``shapely.offset_curve`` on a city-wide network.
    """
    coords, line_index = shapely.get_coordinates(lines, return_index=True)
    segments = np.diff(coords, axis=0)
    lengths = np.hypot(segments[:, 0], segments[:, 1])
    # Skip the step from one line's last point to the next line's first, and repeated points.
    real = (line_index[1:] == line_index[:-1]) & (lengths > 0)
    unit = np.zeros_like(segments)
    unit[real] = segments[real] / lengths[real, None]
    right = np.column_stack([unit[:, 1], -unit[:, 0]])  # (dx, dy) turned 90° clockwise

    normals = np.zeros_like(coords)
    normals[:-1] += right  # each segment pushes its start point
    normals[1:] += right  # and its end point
    norms = np.hypot(normals[:, 0], normals[:, 1])
    normals[norms > 0] /= norms[norms > 0, None]
    # A point touching only zero-length segments takes the direction of its nearest
    # neighbour on the same line; a line that is a single repeated point stays put.
    normals[norms == 0] = np.nan
    by_line = pd.DataFrame(normals).groupby(line_index)
    normals = by_line.ffill().groupby(line_index).bfill().fillna(0.0).to_numpy()
    return shapely.linestrings(coords + distance * normals, indices=line_index)


def lane_status_geojson(edges: gpd.GeoDataFrame | None) -> str:
    """Every directed edge as GeoJSON text, grouped by lane status.

    The result is a FeatureCollection with at most two features: ``{"lane": "yes"}`` holds
    every direction that has a dedicated lane and ``{"lane": "no"}`` every direction that
    has none, each as one MultiLineString. Two features instead of one per edge keep the
    page small and let the browser draw the whole city at once.

    Each edge (a LineString) is moved ``LANE_OFFSET_M`` to the right of travel so both
    directions of a street stay visible, simplified to ``SIMPLIFY_M`` and rounded to
    about 1 m.
    """
    features = []
    if edges is not None and not edges.empty:
        source = gpd.GeoSeries(edges.geometry.values, crs=edges.crs or "EPSG:4326")
        simplified = source.to_crs(METRIC_CRS).simplify(SIMPLIFY_M)
        shifted = shift_right(simplified.to_numpy(), LANE_OFFSET_M)
        lines = (
            gpd.GeoSeries(shifted, crs=METRIC_CRS)
            .to_crs("EPSG:4326")
            .set_precision(COORD_PRECISION, mode="pointwise")
            .to_numpy()
        )
        has_lane = edges["has_dedicated_lane"].to_numpy(dtype=bool)
        for lane, mask in (("yes", has_lane), ("no", ~has_lane)):
            if not mask.any():
                continue
            geometry = shapely.to_geojson(shapely.multilinestrings(lines[mask]))
            features.append(
                f'{{"type":"Feature","properties":{{"lane":"{lane}"}},"geometry":{geometry}}}'
            )
    return '{"type":"FeatureCollection","features":[' + ",".join(features) + "]}"


@dataclass
class RouteLayer:
    """Everything the map needs to draw route volumes for one scenario."""

    data: str  # compact JSON, see route_volume_layer()
    legend: list[tuple[str, str]]  # (swatch HTML, label), lowest volume first
    label: str  # what kind of routes these are, shown on the layer (D5)
    notes: list[str]
    n_edges: int = 0


def volume_classes(volumes: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Split volumes into up to four classes at their quartiles.

    Returns the class of each volume (0 = lowest) and one label per class giving the
    smallest and largest volume actually in it. Ties at a quartile, or quartiles with no
    volume between them, give fewer classes.
    """
    breaks = np.unique(np.quantile(volumes, [0.25, 0.5, 0.75]))
    classes = np.searchsorted(breaks, volumes, side="left")
    present, classes = np.unique(classes, return_inverse=True)
    labels = []
    for c in range(len(present)):
        lo, hi = volumes[classes == c].min(), volumes[classes == c].max()
        labels.append(_volume_text(lo) if lo == hi else f"{_volume_text(lo)}–{_volume_text(hi)}")
    return classes, labels


def _volume_text(volume: float) -> str:
    """Whole trips from 10 up; one decimal below, so a small volume never reads as 0."""
    if volume >= 10:
        return f"{volume:,.0f}"
    return f"{volume:.1f}".removesuffix(".0")


def compass_headings(lines: np.ndarray) -> np.ndarray:
    """Eight-point compass heading from the first to the last point of each metric line."""
    start, end = shapely.get_point(lines, 0), shapely.get_point(lines, -1)
    dx = shapely.get_x(end) - shapely.get_x(start)
    dy = shapely.get_y(end) - shapely.get_y(start)
    bearing = np.degrees(np.arctan2(dx, dy)) % 360
    return np.array(COMPASS)[np.round(bearing / 45).astype(int) % len(COMPASS)]


def route_layer_label(routes: pd.DataFrame) -> str:
    kinds = set(routes["route_type"]) if "route_type" in routes else {"synthetic"}
    if kinds == {"synthetic"}:
        return "Synthetic demo data (D5): not observed cycling"
    if kinds == {"observed"}:
        return "Observed routes"
    return "Synthetic + observed routes"


def _flat_coords(lines: np.ndarray) -> list[list[float]]:
    """Each line's coordinates as one flat ``[lon, lat, lon, lat, …]`` list.

    Rounding to 5 decimals (about 1 m) also keeps the numbers short in JSON.
    """
    coords, line_index = shapely.get_coordinates(lines, return_index=True)
    starts = np.flatnonzero(np.diff(line_index)) + 1
    return [part.ravel().tolist() for part in np.split(np.round(coords, 5), starts)]


def _ramp_steps(n_classes: int) -> list[int]:
    """Which ``ROUTE_RAMP`` step each volume class uses, spread from lightest to darkest.

    A single class takes the darkest step so it stands out on the map.
    """
    last = len(ROUTE_RAMP) - 1
    if n_classes == 1:
        return [last]
    return np.round(np.linspace(0, last, n_classes)).astype(int).tolist()


def route_volume_layer(edges: gpd.GeoDataFrame, routes: pd.DataFrame) -> RouteLayer:
    """Route volume per directed edge for one scenario's routes, ready to draw.

    One line per edge that any route uses, shifted ``ROUTE_OFFSET_M`` to the right of
    travel (the same convention as the lane layer), coloured and sized by volume class.
    ``RouteLayer.data`` is compact JSON with one array per field, index-aligned:
    ``id``, ``volume``, ``heading`` (compass point), ``lane`` (1 = lane in this
    direction), ``step`` (index into ``ROUTE_RAMP``/``ROUTE_WEIGHTS``) and ``coords``
    (flat ``[lon, lat, lon, lat, …]`` per edge). City-wide, GeoJSON with per-feature
    properties was about three times larger. Problems with the routes table become
    notes instead of errors.
    """
    label = route_layer_label(routes)
    try:
        volumes = route_volume_per_edge(routes)
    except ValueError as err:
        notes = [f"Route volumes could not be computed: {err}"]
        return RouteLayer(EMPTY_ROUTE_DATA, [], label, notes)

    notes = []
    used = edges[edges["edge_id"].isin(volumes.index)]
    unknown = len(volumes) - len(used)
    if unknown:
        notes.append(f"{unknown} edge(s) used by routes are not in the edges table and not drawn.")
    if used.empty:
        return RouteLayer(EMPTY_ROUTE_DATA, [], label, notes)

    volume = volumes.reindex(used["edge_id"]).to_numpy(dtype=float)
    metric = gpd.GeoSeries(used.geometry.values, crs=edges.crs or "EPSG:4326").to_crs(METRIC_CRS)
    headings = compass_headings(metric.to_numpy())
    shifted = shift_right(metric.simplify(SIMPLIFY_M).to_numpy(), ROUTE_OFFSET_M)
    lines = gpd.GeoSeries(shifted, crs=METRIC_CRS).to_crs("EPSG:4326").to_numpy()
    classes, class_labels = volume_classes(volume)
    steps = _ramp_steps(len(class_labels))

    rounded = np.round(volume, 1)
    data = {
        "id": used["edge_id"].astype(str).tolist(),
        "volume": [int(v) if v.is_integer() else v for v in rounded.tolist()],
        "heading": headings.tolist(),
        "lane": used["has_dedicated_lane"].to_numpy(dtype=int).tolist(),
        "step": np.asarray(steps)[classes].tolist(),
        "coords": _flat_coords(lines),
    }
    legend = [
        (_line_swatch(ROUTE_RAMP[step], ROUTE_WEIGHTS[step]), f"{text} trips")
        for step, text in zip(steps, class_labels)
    ]
    return RouteLayer(json.dumps(data, separators=(",", ":")), legend, label, notes, len(used))


def stations_geojson(stations: pd.DataFrame) -> dict:
    """Stations as GeoJSON points with ``station_id`` and ``name``."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"station_id": str(station_id), "name": str(name)},
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            }
            for station_id, name, lat, lon in zip(
                stations["station_id"], stations["name"], stations["lat"], stations["lon"]
            )
        ],
    }


def map_bounds(
    stations: pd.DataFrame | None, edges: gpd.GeoDataFrame | None
) -> list[list[float]] | None:
    """South-west and north-east corners covering every station and edge, or None."""
    lats: list[float] = []
    lons: list[float] = []
    if stations is not None and not stations.empty:
        lats += [float(stations["lat"].min()), float(stations["lat"].max())]
        lons += [float(stations["lon"].min()), float(stations["lon"].max())]
    if edges is not None and not edges.empty:
        lonlat = edges if edges.crs is None else edges.to_crs("EPSG:4326")
        min_lon, min_lat, max_lon, max_lat = lonlat.total_bounds
        lats += [float(min_lat), float(max_lat)]
        lons += [float(min_lon), float(max_lon)]
    if not lats:
        return None
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


# ---------------------------------------------------------------- legend


def _line_swatch(color: str, weight: float) -> str:
    return (
        f'<span style="display:inline-block;width:22px;border-top:{weight}px solid {color};'
        'vertical-align:middle"></span>'
    )


def _dot_swatch(color: str) -> str:
    return (
        '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        f"background:{color};border:1.5px solid #fff;box-shadow:0 0 0 1px {color};"
        'vertical-align:middle"></span>'
    )


def _hexagon_swatch(color: str) -> str:
    return f'<span style="color:{color};font-size:15px;vertical-align:middle">&#11042;</span>'


def _area_swatch(color: str) -> str:
    return (
        f'<span style="display:inline-block;width:14px;height:10px;background:{color}66;'
        f'border:1px solid {color};vertical-align:middle"></span>'
    )


def legend_html(entries: list[tuple[str, str]], note: str = "") -> str:
    """HTML for the map legend: one row per (swatch HTML, label) pair, then an optional note."""
    rows = "".join(
        f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'
        f'<span style="width:22px;text-align:center">{swatch}</span>{escape(label)}</div>'
        for swatch, label in entries
    )
    note_html = (
        f'<div style="margin-top:6px;max-width:220px;color:#495057">{escape(note)}</div>'
        if note
        else ""
    )
    return (
        '<div style="background:#fff;color:#212529;padding:8px 10px;border-radius:6px;'
        'box-shadow:0 1px 4px rgba(0,0,0,.3);font:12px/1.35 system-ui,sans-serif">'
        f'<div style="font-weight:600;margin-bottom:4px">Legend</div>{rows}{note_html}</div>'
    )


class MapLegend(MacroElement):
    """A Leaflet control in the map's bottom-right corner holding :func:`legend_html`."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = L.control({position: "bottomright"});
        {{ this.get_name() }}.onAdd = function () {
            var div = L.DomUtil.create("div");
            div.innerHTML = {{ this.html|tojson }};
            L.DomEvent.disableScrollPropagation(div);
            return div;
        };
        {{ this.get_name() }}.addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, html: str) -> None:
        super().__init__()
        self._name = "MapLegend"
        self.html = html


class _InlineDataLayer(MacroElement):
    """A layer whose (possibly multi-megabyte) JSON text is written into the page as is.

    ``folium.GeoJson`` would parse and re-serialise it on every Streamlit rerun, which
    takes seconds for a city-wide network.
    """

    def render(self, **kwargs) -> None:
        # MacroElement.render wraps the finished script in a new Jinja template, which
        # means re-parsing megabytes of coordinates on every rerun. Insert it as data.
        script = Element("{{ this.code }}")
        script.code = self._template.module.script(self, kwargs)
        self.get_root().script.add_child(script, name=self.get_name())


class LaneStatusLayer(_InlineDataLayer):
    """One Leaflet GeoJSON layer with every directed edge, coloured by lane status.

    Takes the text from :func:`lane_status_geojson`. The layer does not react to the
    mouse: checking 100,000+ lines on every mouse move makes the map lag.
    """

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = L.geoJson({{ this.geojson }}, {
            style: {{ this.style }},
            interactive: false
        }).addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, geojson: str, name: str = "Bike-lane status") -> None:
        super().__init__()
        self._name = "LaneStatusLayer"
        self.layer_name = name
        self.geojson = geojson
        self.style = LANE_STYLE_JS


class RouteVolumeLayer(_InlineDataLayer):
    """Route volume per directed edge, from :func:`route_volume_layer`.

    Colour and width come from each edge's volume class, and hovering shows the layer
    label (synthetic or observed), edge ID, direction, volume and lane status. The
    tooltip text is built only when hovered, so the page carries no per-edge text.
    """

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = (function () {
            var d = {{ this.data }};
            var colors = {{ this.colors|tojson }}, weights = {{ this.weights|tojson }};
            var label = {{ this.label|tojson }};
            var esc = function (s) {
                return String(s).replace(/[&<>"']/g, function (c) {
                    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
                });
            };
            var tooltip = function (line) {
                var i = line.bubiIndex, id = String(d.id[i]), parts = id.split("-");
                var nodes = parts.length === 3 ? "node " + parts[0] + " → " + parts[1] + ", " : "";
                return "<b>" + esc(label) + "</b><br>" +
                    "Edge " + esc(id) + "<br>" +
                    "Direction: " + esc(nodes + "heading " + d.heading[i]) + "<br>" +
                    "Trips: " + esc(d.volume[i].toLocaleString()) + "<br>" +
                    "Bike lane in this direction: " + (d.lane[i] ? "yes" : "no");
            };
            var group = L.featureGroup();
            for (var i = 0; i < d.id.length; i++) {
                var c = d.coords[i], points = [];
                for (var j = 0; j < c.length; j += 2) points.push([c[j + 1], c[j]]);
                var line = L.polyline(points, {
                    color: colors[d.step[i]], weight: weights[d.step[i]], opacity: 0.85
                });
                line.bubiIndex = i;
                line.bindTooltip(tooltip, {sticky: true});
                group.addLayer(line);
            }
            return group;
        })().addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, layer: RouteLayer, name: str = "Route volume") -> None:
        super().__init__()
        self._name = "RouteVolumeLayer"
        self.layer_name = name
        self.data = layer.data
        self.label = layer.label
        self.colors = list(ROUTE_RAMP)
        self.weights = list(ROUTE_WEIGHTS)


# ---------------------------------------------------------------- map


def build_map(
    data: DashboardData,
    settings: Settings,
    lane_geojson: str | None = None,
    route_layer: RouteLayer | None = None,
    summary: ScenarioSummary | None = None,
    robustness_style: bool = False,
) -> tuple[folium.Map, list[str]]:
    """Draw the enabled layers. Returns the map and notes about anything not drawn.

    ``lane_geojson`` is the output of :func:`lane_status_geojson` and ``route_layer`` of
    :func:`route_volume_layer` for ``settings.scenario``; pass cached copies to avoid
    rebuilding them. The map opens zoomed to every station and edge.
    """
    notes: list[str] = []
    legend: list[tuple[str, str]] = []
    stations = data.get("stations")
    edges = data.get("edges")
    scenario = settings.scenario
    diff_active = bool(settings.show_diff and scenario != "baseline")

    # Canvas draws tens of thousands of lines much faster than one SVG element per line.
    fmap = folium.Map(
        location=BUDAPEST_CENTER, zoom_start=12, prefer_canvas=True, **BASEMAPS[settings.basemap]
    )
    bounds = map_bounds(stations, edges)
    if bounds is not None:
        fmap.fit_bounds(bounds)

    # Population layer: in difference mode, shade only newly served H3 cells (R4).
    population = data.get("population")
    if diff_active:
        newly_cells = (
            summary.newly_served_cells_by_scenario.get(scenario)
            if summary is not None
            else newly_served_population_cells(
                population,
                stations,
                proposed_stations(data, scenario),
                walk_coverage_m=settings.walk_coverage_m,
            )
        )
        if newly_cells is not None and not newly_cells.empty:
            layer = folium.FeatureGroup(name="Newly served population (H3)")
            max_pop = float(newly_cells["population"].max()) or 1.0
            for _, row in newly_cells.iterrows():
                if cell_center(row["cell_id"]) is None:
                    continue
                folium.Polygon(
                    locations=h3.cell_to_boundary(row["cell_id"]),
                    color=POPULATION_COLOR,
                    weight=1.0,
                    fill=True,
                    fill_opacity=0.2 + 0.55 * float(row["population"]) / max_pop,
                    tooltip=(
                        f"Newly served cell {row['cell_id']} · population: {row['population']:.0f}"
                    ),
                ).add_to(layer)
            layer.add_to(fmap)
            legend.append(
                (
                    _area_swatch(POPULATION_COLOR),
                    "Newly served population (within 350 m of proposed)",
                )
            )
    elif settings.show_population:
        if population is None or population.empty:
            reason = data.missing_reason("population")
            if reason:
                notes.append(f"Population layer is blocked: {reason}")
        else:
            layer = folium.FeatureGroup(name="Population (H3)")
            max_pop = float(population["population"].max()) or 1.0
            skipped = 0
            for _, row in population.iterrows():
                if cell_center(row["cell_id"]) is None:
                    skipped += 1
                    continue
                folium.Polygon(
                    locations=h3.cell_to_boundary(row["cell_id"]),
                    color=POPULATION_COLOR,
                    weight=0.5,
                    fill=True,
                    fill_opacity=0.15 + 0.5 * row["population"] / max_pop,
                    tooltip=f"Population: {row['population']:.0f}",
                ).add_to(layer)
            layer.add_to(fmap)
            legend.append((_area_swatch(POPULATION_COLOR), "Population (darker = more people)"))
            if skipped:
                notes.append(
                    f"{skipped} population cell(s) have an invalid H3 id and are not drawn."
                )

    if settings.show_lanes and not edges.empty:
        geojson = lane_geojson if lane_geojson is not None else lane_status_geojson(edges)
        fmap.add_child(LaneStatusLayer(geojson))
        legend.append((_line_swatch(LANE_COLOR, LANE_WEIGHT), "Bike lane in this direction"))
        legend.append(
            (_line_swatch(NO_LANE_COLOR, NO_LANE_WEIGHT), "No bike lane in this direction")
        )

    routes_raw = data.get("routes")
    routes = for_scenario(routes_raw, scenario)
    route_shown = False
    if settings.show_routes:
        if routes_raw is None or routes_raw.empty:
            reason = data.missing_reason("routes")
            if reason:
                notes.append(f"Routes layer is blocked: {reason}")
        elif not routes.empty:
            if route_layer is None:
                route_layer = route_volume_layer(edges, routes)
            notes.extend(route_layer.notes)
            if route_layer.legend:
                fmap.add_child(RouteVolumeLayer(route_layer))
                legend.extend(route_layer.legend)
                route_shown = True

    # Rank-change edge layer in difference mode (R5).
    if diff_active and edges is not None and not edges.empty:
        changes = (
            summary.rank_changes_by_scenario.get(scenario)
            if summary is not None
            else edge_rank_changes(data.get("edge_scores"), scenario, top_k=settings.top_n)
        )
        if changes is not None and not changes.empty:
            edges_by_id = edges.set_index("edge_id")
            layer = folium.FeatureGroup(name="Rank changes vs baseline")
            change_colors = {
                "improved": (RANK_IMPROVED_COLOR, "Rank improved vs baseline"),
                "worsened": (RANK_WORSENED_COLOR, "Rank worsened vs baseline"),
                "new_top_k": (RANK_NEW_TOPK_COLOR, "New to top-k vs baseline"),
            }
            seen_types: set[str] = set()
            for _, ch in changes.iterrows():
                eid = ch["edge_id"]
                if eid not in edges_by_id.index:
                    continue
                ctype = str(ch["change_type"])
                color, _ = change_colors[ctype]
                seen_types.add(ctype)
                rob_label = (
                    summary.edge_labels.get(eid, LABEL_STATION_DEPENDENT)
                    if summary is not None
                    else LABEL_STATION_DEPENDENT
                )
                folium.PolyLine(
                    offset_line(list(edges_by_id.loc[eid].geometry.coords), meters=7.0),
                    color=color,
                    weight=5,
                    opacity=0.9,
                    tooltip=(
                        f"Edge {eid} · {ctype} (baseline rank {ch['baseline_rank']} → "
                        f"{ch['scenario_rank']}) · {rob_label}"
                    ),
                ).add_to(layer)
            layer.add_to(fmap)
            for ctype in ("new_top_k", "improved", "worsened"):
                if ctype in seen_types:
                    color, label_text = change_colors[ctype]
                    legend.append((_line_swatch(color, 5), label_text))

    corridors_raw = data.get("corridors")
    corridors = for_scenario(corridors_raw, scenario)
    if settings.show_corridors:
        if corridors_raw is None or corridors_raw.empty:
            reason = data.missing_reason("corridors")
            if reason:
                notes.append(f"Top corridors layer is blocked: {reason}")
        elif not corridors.empty:
            if diff_active:
                top = (
                    summary.new_corridors_by_scenario.get(scenario)
                    if summary is not None
                    else corridors_absent_from_baseline(
                        corridors_raw, scenario, top_k=settings.top_n
                    )
                )
                layer_name = "New corridors vs baseline"
            else:
                top = corridors.sort_values("rank").head(settings.top_n)
                layer_name = "Top corridors"

            if top is not None and not top.empty:
                layer = folium.FeatureGroup(name=layer_name)
                edges_by_id = edges.set_index("edge_id")
                used_robust = False
                used_dep = False
                for _, corridor in top.iterrows():
                    cid = str(corridor["corridor_id"])
                    rob_label = (
                        summary.corridor_labels.get((scenario, cid), LABEL_STATION_DEPENDENT)
                        if summary is not None
                        else LABEL_STATION_DEPENDENT
                    )
                    if robustness_style and scenario != "baseline":
                        is_rob = rob_label == LABEL_ROBUST
                        color = ROBUST_COLOR if is_rob else STATION_DEP_COLOR
                        dash_array = None if is_rob else "8, 6"
                        used_robust = used_robust or is_rob
                        used_dep = used_dep or (not is_rob)
                    else:
                        color = GAP_COLOR
                        dash_array = None

                    for edge_id in as_id_list(corridor["edge_ids"]):
                        if edge_id not in edges_by_id.index:
                            notes.append(f"Corridor {cid} uses unknown edge `{edge_id}`.")
                            continue
                        folium.PolyLine(
                            offset_line(list(edges_by_id.loc[edge_id].geometry.coords)),
                            color=color,
                            weight=7,
                            opacity=0.9,
                            dash_array=dash_array,
                            tooltip=(
                                f"Corridor {cid} · scenario {scenario} · rank {corridor['rank']} · "
                                f"edge {edge_id} · score {corridor['score']:.0f} · {rob_label}"
                            ),
                        ).add_to(layer)
                layer.add_to(fmap)
                if robustness_style and scenario != "baseline":
                    if used_robust:
                        legend.append(
                            (_line_swatch(ROBUST_COLOR, 6), "Robust corridor (all 3 scenarios)")
                        )
                    if used_dep:
                        legend.append(
                            (_line_swatch(STATION_DEP_COLOR, 6), "Station-dependent corridor")
                        )
                elif diff_active:
                    legend.append(
                        (_line_swatch(GAP_COLOR, 6), f"New corridor vs baseline ({len(top)})")
                    )
                else:
                    legend.append((_line_swatch(GAP_COLOR, 6), "Priority corridor (missing lane)"))

    if settings.show_stations and not stations.empty:
        # One GeoJSON layer: a separate Folium marker per station adds about 1 s per rerun
        # for Budapest's ~700 stations.
        folium.GeoJson(
            stations_geojson(stations),
            name="Existing stations",
            marker=folium.CircleMarker(
                radius=6,
                color="#ffffff",
                weight=1.5,
                fill=True,
                fill_color=STATION_COLOR,
                fill_opacity=0.95,
            ),
            tooltip=folium.GeoJsonTooltip(fields=["name", "station_id"], aliases=["Station", "ID"]),
        ).add_to(fmap)
        legend.append((_dot_swatch(STATION_COLOR), "Existing station"))

    candidates_raw = data.get("station_candidates")
    candidates = proposed_stations(data, scenario)
    if settings.show_proposed:
        if candidates_raw is None or candidates_raw.empty:
            reason = data.missing_reason("station_candidates")
            if reason:
                notes.append(f"Proposed stations layer is blocked: {reason}")
        elif not candidates.empty:
            layer_title = "New proposed stations" if diff_active else "Proposed stations"
            marker_color = DIFF_NEW_STATION_COLOR if diff_active else PROPOSED_COLOR
            layer = folium.FeatureGroup(name=layer_title)
            skipped = 0
            for _, row in candidates.iterrows():
                center = cell_center(row["cell_id"])
                if center is None:
                    skipped += 1
                    continue
                folium.RegularPolygonMarker(
                    location=center,
                    number_of_sides=6,
                    radius=9,
                    color="#ffffff",
                    weight=1.5,
                    fill_color=marker_color,
                    fill_opacity=0.95,
                    tooltip=(
                        f"new: proposed · {row['cell_id']} · rank {row['rank']} · "
                        f"population {row['population']:.0f} · score {row['score']:.2f}"
                    ),
                ).add_to(layer)
            layer.add_to(fmap)
            legend_label = (
                "new: proposed station (diff vs baseline)"
                if diff_active
                else "Proposed station (H3 cell centre)"
            )
            legend.append((_hexagon_swatch(marker_color), legend_label))
            if skipped:
                notes.append(
                    f"{skipped} proposed station(s) have an invalid H3 id and are not drawn."
                )

    if legend:
        note = []
        if settings.show_lanes or route_shown:
            note.append(
                "Each direction of a street is drawn on the right-hand side of travel, so a "
                "two-way street shows two lines."
            )
        if route_shown:
            note.append(f"Route volume, darker and wider = more trips. {route_layer.label}.")
        fmap.add_child(MapLegend(legend_html(legend, " ".join(note))))
    return fmap, notes


# ---------------------------------------------------------------- exports


def _json_safe(value: Any) -> Any:
    """Convert NumPy / pandas scalars into plain JSON-serialisable Python types."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if math.isnan(float(value)) else float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def export_csv(table: pd.DataFrame, *, demo_mode: bool = True) -> bytes:
    """A table as UTF-8 CSV for download, preserving demo/synthetic labels.

    ``edge_ids`` is written as a JSON array, the contract's string form. A list read
    back from Parquet is a NumPy array, and pandas would otherwise write it as
    ``['a-b-0' 'b-c-0']``, which spreadsheets and other tools cannot parse.
    """
    out = table.copy()
    if "edge_ids" in out:
        out["edge_ids"] = out["edge_ids"].map(lambda v: json.dumps(as_id_list(v)))
    if "demo_mode" not in out:
        out["demo_mode"] = demo_mode
    if "data_label" not in out:
        out["data_label"] = DEMO_MODE_LABEL if demo_mode else "Observed data"
    return out.to_csv(index=False).encode("utf-8")


def corridors_geojson(
    corridors: pd.DataFrame,
    edges: gpd.GeoDataFrame | None,
    *,
    scenario: str | None = None,
    demo_mode: bool = True,
) -> bytes:
    """Export corridors as plain RFC 7946 GeoJSON with demo-mode & synthetic metadata."""
    lonlat = (
        edges.to_crs("EPSG:4326")
        if edges is not None and not edges.empty and edges.crs is not None
        else edges
    )
    edges_by_id = lonlat.set_index("edge_id") if lonlat is not None and not lonlat.empty else None
    label = DEMO_MODE_LABEL if demo_mode else "Observed data"

    features = []
    for _, row in corridors.iterrows():
        edge_ids = as_id_list(row.get("edge_ids"))
        lines = []
        if edges_by_id is not None:
            for eid in edge_ids:
                if eid in edges_by_id.index:
                    geom = edges_by_id.loc[eid].geometry
                    if isinstance(geom, gpd.GeoSeries):
                        geom = geom.iloc[0]
                    lines.append([[round(float(x), 6), round(float(y), 6)] for x, y in geom.coords])

        geometry = (
            None
            if not lines
            else (
                {"type": "LineString", "coordinates": lines[0]}
                if len(lines) == 1
                else {"type": "MultiLineString", "coordinates": lines}
            )
        )
        props = {k: _json_safe(v) for k, v in row.items() if k not in {"edge_ids", "geometry"}}
        props["edge_ids"] = edge_ids
        if scenario is not None and "scenario" not in props:
            props["scenario"] = scenario
        props["demo_mode"] = demo_mode
        props["data_label"] = label
        features.append({"type": "Feature", "properties": props, "geometry": geometry})

    payload = {
        "type": "FeatureCollection",
        "name": f"corridors_{scenario}" if scenario else "corridors",
        "properties": {
            "scenario": scenario,
            "demo_mode": demo_mode,
            "data_label": label,
        },
        "features": features,
    }
    return json.dumps(payload, indent=2).encode("utf-8")


def station_candidates_geojson(
    candidates: pd.DataFrame,
    *,
    scenario: str | None = None,
    demo_mode: bool = True,
) -> bytes:
    """Export station candidates as plain RFC 7946 Point GeoJSON with demo-mode labels."""
    label = DEMO_MODE_LABEL if demo_mode else "Observed data"
    features = []
    for _, row in candidates.iterrows():
        center = cell_center(str(row.get("cell_id", "")))
        geometry = (
            None
            if center is None
            else {"type": "Point", "coordinates": [round(center[1], 6), round(center[0], 6)]}
        )
        props = {k: _json_safe(v) for k, v in row.items() if k != "geometry"}
        if scenario is not None and "scenario" not in props:
            props["scenario"] = scenario
        props["demo_mode"] = demo_mode
        props["data_label"] = label
        features.append({"type": "Feature", "properties": props, "geometry": geometry})

    payload = {
        "type": "FeatureCollection",
        "name": f"station_candidates_{scenario}" if scenario else "station_candidates",
        "properties": {
            "scenario": scenario,
            "demo_mode": demo_mode,
            "data_label": label,
        },
        "features": features,
    }
    return json.dumps(payload, indent=2).encode("utf-8")


def write_export(filename: str, payload: bytes, exports_dir: Path = EXPORTS_DIR) -> Path:
    """Write an export file to ``outputs/exports/`` so plain files are persisted on disk."""
    exports_dir.mkdir(parents=True, exist_ok=True)
    target = exports_dir / filename
    target.write_bytes(payload)
    return target


# ---------------------------------------------------------------- page sections


def render_header(data: DashboardData | None) -> None:
    left, right = st.columns([3, 1])
    left.title("🚲 MOL Bubi Bike-Lane & Station Recommendation Tool")
    if data is None:
        return
    source = {
        "fixtures": "fixture-scale sample data (until #15 merges)",
        "processed": "pipeline outputs",
        "mixed": "pipeline outputs + fixture-scale sample data (until #15 merges)",
    }[data.source]
    right.warning(f"**Synthetic demo data** (D5) · {source}")


def render_sidebar(config: dict) -> Settings:
    sidebar = st.sidebar
    sidebar.header("Scenario")
    active = config.get("scenarios", {}).get("active") or list(SCENARIOS)
    scenario = sidebar.radio(
        "Active scenario",
        options=active,
        format_func=lambda s: s,
        help="\n\n".join(f"**{s}**: {SCENARIO_HELP.get(s, '')}" for s in active),
        label_visibility="collapsed",
    )
    is_baseline = scenario == "baseline"
    show_diff = sidebar.checkbox(
        "Show difference vs baseline",
        value=False if is_baseline else False,
        disabled=is_baseline,
        help=(
            "Disabled on baseline (no difference to show)."
            if is_baseline
            else (
                "Highlight new stations, newly served H3 cells, new corridors, "
                "and rank changes vs baseline."
            )
        ),
    )

    sidebar.divider()
    sidebar.header("Map layers")
    scoring = config.get("station_scoring", {})
    walk_coverage_m = float(scoring.get("walk_coverage_threshold_m", DEFAULT_WALK_COVERAGE_M))
    settings = Settings(
        scenario=scenario,
        basemap=sidebar.selectbox(
            "Basemap",
            options=list(BASEMAPS),
            help="The light grey basemap makes the lane colours easier to read on a projector.",
        ),
        show_stations=sidebar.checkbox("Existing stations", value=True),
        show_proposed=sidebar.checkbox("Proposed stations", value=True),
        show_population=sidebar.checkbox("Population (H3 cells)", value=False),
        show_lanes=sidebar.checkbox("Bike-lane coverage", value=True),
        show_routes=sidebar.checkbox("Synthetic routes", value=False),
        show_corridors=sidebar.checkbox("Top corridors", value=True),
        top_n=sidebar.slider("Top corridors to show", min_value=1, max_value=50, value=10),
        show_diff=show_diff and not is_baseline,
        walk_coverage_m=walk_coverage_m,
    )

    sidebar.divider()
    sidebar.header("Run parameters")
    sidebar.caption("Read-only, from `config/default_config.yaml`")
    spatial = config.get("spatial", {})
    network = config.get("network", {})
    project = config.get("project", {})
    sidebar.markdown(
        f"- Walk coverage: {scoring.get('walk_coverage_threshold_m', '–')} m\n"
        f"- Proposed stations N: {scoring.get('candidate_n', '–')}\n"
        f"- Min spacing: {scoring.get('min_spacing_m', '–')} m\n"
        f"- Seed: {project.get('random_seed', '–')} · H3 res {spatial.get('h3_resolution', '–')}\n"
        f"- OSM graph: {network.get('frozen_graph_version', '–')}"
    )
    return settings


def render_metrics(data: DashboardData, scenario: str, summary: ScenarioSummary) -> None:
    stations = data.get("stations")
    row = summary.metrics_table.set_index("scenario").loc[scenario]
    m1 = row["newly_served_pop_m1"]
    m6 = row["pop_per_corridor_km_m6"]
    corridor_km = row["corridor_km"]
    trips = row["synthetic_trips_abs"]
    new_corr_count = int(row["new_corridors_vs_baseline"])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Stations (existing + proposed)",
        f"{len(stations)} + {int(row['proposed_stations'])}",
    )
    c2.metric(
        "Newly served population (M1)",
        f"{m1:,.0f}" if scenario != "baseline" else "0",
        help="Residents within 350 m of a proposed station and outside existing stations (D15).",
    )
    c3.metric(
        "Corridor km without a lane (M6)",
        f"{corridor_km:.2f} km",
        delta=(
            f"{m6:,.0f} newly served / km · {new_corr_count} new corridors"
            if scenario != "baseline" and pd.notna(m6)
            else (f"{new_corr_count} new corridors vs baseline" if scenario != "baseline" else None)
        ),
    )
    c4.metric(
        "Synthetic trips",
        f"{trips:,.0f}" if trips > 0 else "–",
    )


def render_detail_panel(
    map_state: dict | None,
    data: DashboardData,
    scenario: str,
    summary: ScenarioSummary,
) -> None:
    st.markdown("#### Selected recommendation")
    clicked = (map_state or {}).get("last_object_clicked_tooltip")
    if not clicked:
        st.caption("Click a corridor or station on the map.")
        return

    st.info(clicked)
    # Enrich corridor clicks with robustness label and edge breakdown if corridor ID is in tooltip.
    corridors = for_scenario(data.get("corridors"), scenario)
    for _, crow in corridors.iterrows():
        cid = str(crow["corridor_id"])
        if f"Corridor {cid} " in clicked or clicked.startswith(f"Corridor {cid}"):
            rob_label = summary.corridor_labels.get((scenario, cid), LABEL_STATION_DEPENDENT)
            eids = as_id_list(crow["edge_ids"])
            st.markdown(
                f"- **Scenario:** `{scenario}` · **Rank:** #{int(crow['rank'])} · "
                f"**Score:** {float(crow['score']):.1f} · **Robustness:** `{rob_label}`\n"
                f"- **Edges ({len(eids)}):** {', '.join(f'`{e}`' for e in eids)}"
            )
            break


def render_scenario_comparison(
    data: DashboardData, settings: Settings, summary: ScenarioSummary
) -> None:
    st.subheader("Scenario comparison")
    st.caption(
        "Side-by-side comparison across `baseline`, `lane_aware`, and `population_only`. "
        "When 'Show difference vs baseline' is active, proposed-station maps highlight robust "
        "(blue solid) vs station-dependent (orange dashed) corridors. "
        "Absolute counts and per-newly-served-person metrics "
        "(M1, M6, M11, M13, M14) are shown below."
    )

    timings: list[str] = []
    for column, scenario in zip(st.columns(len(SCENARIOS)), SCENARIOS):
        with column:
            t0 = time.perf_counter()
            fmap, _ = build_map(
                data,
                replace(settings, scenario=scenario, show_lanes=False, show_routes=False),
                summary=summary,
                robustness_style=settings.show_diff,
            )
            elapsed = time.perf_counter() - t0
            timings.append(f"`{scenario}`: {elapsed:.2f} s")
            st.markdown(f"**{scenario}** *(prepared in {elapsed:.2f} s)*")
            st_folium(
                fmap,
                height=300,
                use_container_width=True,
                returned_objects=[],
                key=f"comparison_map_{scenario}_{int(settings.show_diff)}",
            )

    st.caption("Scenario map preparation times — " + " · ".join(timings))

    display_df = summary.metrics_table.copy()
    per_person_cols = (
        "pop_per_corridor_km_m6",
        "demand_per_newly_served_m11",
        "robust_corridor_share_m13",
    )
    for col in per_person_cols:
        display_df[col] = display_df[col].map(lambda v: "–" if pd.isna(v) else v)

    st.dataframe(display_df, hide_index=True, width="stretch")

    if not summary.jaccard_table.empty:
        st.caption("Top-k directed edge Jaccard overlap across scenarios (M14):")
        st.dataframe(summary.jaccard_table, hide_index=True, width="stretch")


def render_tables(data: DashboardData, scenario: str, summary: ScenarioSummary) -> None:
    corridors_raw = data.get("corridors")
    candidates_raw = data.get("station_candidates")
    corridors = for_scenario(corridors_raw, scenario)
    candidates = for_scenario(candidates_raw, scenario)
    edges = data.get("edges")
    tab1, tab2, tab3 = st.tabs(["Top corridors", "Station candidates", "Methodology & limitations"])

    with tab1:
        if corridors_raw is None or corridors_raw.empty:
            st.info(f"Corridors table is unavailable. {data.missing_reason('corridors') or ''}")
        elif corridors.empty:
            st.write("No corridors for this scenario.")
        else:
            table = corridors.sort_values("rank").copy()
            table["robustness"] = table["corridor_id"].map(
                lambda cid: summary.corridor_labels.get(
                    (scenario, str(cid)), LABEL_STATION_DEPENDENT
                )
            )
            st.dataframe(table, hide_index=True, width="stretch")
            csv_bytes = export_csv(table, demo_mode=True)
            geojson_bytes = corridors_geojson(table, edges, scenario=scenario, demo_mode=True)
            col_csv, col_geo = st.columns(2)
            with col_csv:
                st.download_button(
                    "📥 Export corridors (CSV)",
                    csv_bytes,
                    f"corridors_{scenario}.csv",
                    "text/csv",
                    on_click=write_export,
                    args=(f"corridors_{scenario}.csv", csv_bytes),
                )
            with col_geo:
                st.download_button(
                    "🌍 Export corridors (GeoJSON)",
                    geojson_bytes,
                    f"corridors_{scenario}.geojson",
                    "application/geo+json",
                    on_click=write_export,
                    args=(f"corridors_{scenario}.geojson", geojson_bytes),
                )

    with tab2:
        if candidates_raw is None or candidates_raw.empty:
            st.info(
                "Station candidates table is unavailable. "
                f"{data.missing_reason('station_candidates') or ''}"
            )
        elif candidates.empty:
            st.write("No proposed stations in this scenario.")
        else:
            table = candidates.sort_values("rank")
            st.caption("Candidates without a rank were not selected as new stations.")
            st.dataframe(table, hide_index=True, width="stretch")
            csv_bytes = export_csv(table, demo_mode=True)
            geojson_bytes = station_candidates_geojson(table, scenario=scenario, demo_mode=True)
            col_csv, col_geo = st.columns(2)
            with col_csv:
                st.download_button(
                    "📥 Export station candidates (CSV)",
                    csv_bytes,
                    f"station_candidates_{scenario}.csv",
                    "text/csv",
                    on_click=write_export,
                    args=(f"station_candidates_{scenario}.csv", csv_bytes),
                )
            with col_geo:
                st.download_button(
                    "🌍 Export station candidates (GeoJSON)",
                    geojson_bytes,
                    f"station_candidates_{scenario}.geojson",
                    "application/geo+json",
                    on_click=write_export,
                    args=(f"station_candidates_{scenario}.geojson", geojson_bytes),
                )

    with tab3:
        st.markdown(
            "- Synthetic trips, routes and corridor rankings are an algorithm demonstration, "
            "not evidence of real cyclist behaviour (D5).\n"
            "- Current tables use fixture-scale sample data until full Budapest network "
            "ingestion (#15) merges.\n"
            "- Demand is driven by population only, with no time-of-day effects (D8).\n"
            "- Routing prefers flat/downhill roads and ignores traffic and existing lanes (D2).\n"
            "- Station scores ignore legal, land-use and construction feasibility (D4).\n"
            "- Scenario results are a comparison, not a forecast."
        )


# ---------------------------------------------------------------- entry point


def main() -> None:
    st.set_page_config(
        page_title="MOL Bubi Bike-Lane & Station Recommender",
        page_icon="🚲",
        layout="wide",
    )
    try:
        config = load_config()
    except DashboardDataError as err:
        st.warning(str(err))
        config = {}
    settings = render_sidebar(config)

    cache_key = (os.environ.get(DATA_DIR_ENV), _latest_change())
    try:
        data = _cached_load(*cache_key)
    except DashboardDataError as err:
        render_header(None)
        st.error(f"**The dashboard cannot start because of a data problem.**\n\n{err}")
        st.stop()

    render_header(data)
    if data.fixture_tables:
        st.info(FIXTURE_SCALE_NOTICE)
    for warning in data.warnings:
        st.warning(warning)

    summary = build_scenario_summary(
        data, top_k=settings.top_n, walk_coverage_m=settings.walk_coverage_m
    )

    render_metrics(data, settings.scenario, summary)

    started = time.perf_counter()
    lane_geojson = _cached_lane_geojson(*cache_key) if settings.show_lanes else None
    route_layer = (
        _cached_route_layer(*cache_key, settings.scenario) if settings.show_routes else None
    )
    fmap, notes = build_map(data, settings, lane_geojson, route_layer, summary=summary)
    map_elapsed = time.perf_counter() - started
    map_state = st_folium(
        fmap,
        height=560,
        use_container_width=True,
        key=f"main_map_{settings.scenario}_{int(settings.show_diff)}",
        returned_objects=["last_object_clicked_tooltip"],
    )
    if settings.show_diff and settings.scenario != "baseline":
        new_corr = summary.new_corridors_by_scenario.get(settings.scenario)
        new_corr_n = len(new_corr) if new_corr is not None else 0
        st.caption(
            f"Difference mode (`{settings.scenario}` vs `baseline`): "
            f"**{new_corr_n}** corridor(s) absent from baseline shown."
        )
    st.caption(
        f"{len(data.get('edges')):,} directed street edges · scenario `{settings.scenario}` map "
        f"prepared on the server in {map_elapsed:.2f} s (the browser needs extra time to draw it)."
    )
    st.caption(DATA_ATTRIBUTION)
    for note in fixture_notes(data) + summary.notes + notes:
        st.caption(f"⚠️ {note}")
    render_detail_panel(map_state, data, settings.scenario, summary)

    render_scenario_comparison(data, settings, summary)
    render_tables(data, settings.scenario, summary)


if __name__ == "__main__":
    main()
