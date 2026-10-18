"""Interactive Streamlit + Folium dashboard for MOL Bubi recommendations.

Week 1 skeleton: the layout follows ``WIREFRAME.md``. It reads the contract tables
through :mod:`bubi.dashboard.data` (pipeline outputs or sample fixtures, never an
external API) and shows a clear message instead of crashing when data is missing
or invalid.

Run with ``make dashboard``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import folium
import h3
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from bubi.dashboard.data import (
    BUDAPEST_CENTER,
    DEFAULT_BBOX,
    SCENARIOS,
    DashboardData,
    DashboardDataError,
    as_id_list,
    cell_center,
    for_scenario,
    in_bbox,
    load_config,
    load_dashboard_data,
    resolve_data_dir,
)

LANE_COLOR = "#2b8a3e"  # lane exists in this direction
NO_LANE_COLOR = "#adb5bd"  # no lane in this direction
GAP_COLOR = "#e8590c"  # priority corridor (gap)
STATION_COLOR = "#1c7ed6"
PROPOSED_COLOR = "#2b8a3e"
ROUTE_COLOR = "#7048e8"
POPULATION_COLOR = "#f08c00"

SCENARIO_HELP = {
    "baseline": "Existing Futár stations only.",
    "lane_aware": "Existing + proposed stations scored by population × lane connectivity.",
    "population_only": "Existing + proposed stations scored by population only.",
}


@dataclass
class Settings:
    scenario: str
    show_stations: bool
    show_proposed: bool
    show_population: bool
    show_lanes: bool
    show_routes: bool
    show_corridors: bool
    top_n: int


# ---------------------------------------------------------------- data access


@st.cache_data(show_spinner="Loading data tables…")
def _cached_load(data_dir: str, source: str, files_changed_at: float) -> DashboardData:
    """Cached per folder; ``files_changed_at`` makes the cache reload after data changes."""
    return load_dashboard_data(Path(data_dir), source)


def _latest_change(data_dir: Path) -> float:
    return max((p.stat().st_mtime for p in data_dir.glob("*.parquet")), default=0.0)


def edge_ids_of_corridors(corridors: pd.DataFrame) -> set[str]:
    ids: set[str] = set()
    for value in corridors.get("edge_ids", []):
        ids.update(as_id_list(value))
    return ids


def route_volume_per_edge(routes: pd.DataFrame) -> pd.Series:
    """Total trips crossing each directed edge in the given routes."""
    if routes.empty:
        return pd.Series(dtype=float)
    exploded = routes.assign(edge_id=routes["edges"].map(as_id_list)).explode("edge_id")
    return exploded.groupby("edge_id")["trip_count"].sum()


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


def map_center(stations: pd.DataFrame) -> tuple[float, float]:
    if stations.empty:
        return BUDAPEST_CENTER
    return float(stations["lat"].mean()), float(stations["lon"].mean())


def build_map(data: DashboardData, settings: Settings, bbox) -> tuple[folium.Map, list[str]]:
    """Draw the enabled layers. Returns the map and notes about anything not drawn."""
    notes: list[str] = []
    stations = data.get("stations")
    edges = data.get("edges")
    scenario = settings.scenario

    # CartoDB basemaps now need an API key, so use plain OpenStreetMap tiles.
    fmap = folium.Map(location=map_center(stations), zoom_start=14, tiles="OpenStreetMap")

    population = data.get("population")
    if settings.show_population and population is not None and not population.empty:
        layer = folium.FeatureGroup(name="Population (H3)")
        max_pop = float(population["population"].max()) or 1.0
        skipped = 0
        for _, row in population.iterrows():
            center = cell_center(row["cell_id"])
            if center is None or not in_bbox(center[0], center[1], bbox):
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
        if skipped:
            notes.append(
                f"{skipped} population cell(s) lie outside the study area and are not drawn."
            )

    if settings.show_lanes and not edges.empty:
        layer = folium.FeatureGroup(name="Bike-lane coverage")
        for _, row in edges.iterrows():
            has_lane = bool(row["has_dedicated_lane"])
            folium.PolyLine(
                offset_line(list(row.geometry.coords)),
                color=LANE_COLOR if has_lane else NO_LANE_COLOR,
                weight=4 if has_lane else 2.5,
                opacity=0.85,
                tooltip=f"Edge {row['edge_id']} · lane in this direction: {'yes' if has_lane else 'no'}",
            ).add_to(layer)
        layer.add_to(fmap)

    routes = for_scenario(data.get("routes"), scenario)
    if settings.show_routes and not routes.empty:
        volumes = route_volume_per_edge(routes)
        layer = folium.FeatureGroup(name="Synthetic routes")
        max_vol = float(volumes.max()) or 1.0
        for _, row in edges[edges["edge_id"].isin(volumes.index)].iterrows():
            vol = float(volumes[row["edge_id"]])
            folium.PolyLine(
                offset_line(list(row.geometry.coords), meters=8),
                color=ROUTE_COLOR,
                weight=2 + 6 * vol / max_vol,
                opacity=0.6,
                tooltip=f"Edge {row['edge_id']} · synthetic trips: {vol:.0f}",
            ).add_to(layer)
        layer.add_to(fmap)

    corridors = for_scenario(data.get("corridors"), scenario)
    if settings.show_corridors and not corridors.empty:
        top = corridors.sort_values("rank").head(settings.top_n)
        layer = folium.FeatureGroup(name="Top corridors")
        edges_by_id = edges.set_index("edge_id")
        for _, corridor in top.iterrows():
            for edge_id in as_id_list(corridor["edge_ids"]):
                if edge_id not in edges_by_id.index:
                    notes.append(
                        f"Corridor {corridor['corridor_id']} uses unknown edge `{edge_id}`."
                    )
                    continue
                folium.PolyLine(
                    offset_line(list(edges_by_id.loc[edge_id].geometry.coords)),
                    color=GAP_COLOR,
                    weight=7,
                    opacity=0.9,
                    tooltip=(
                        f"Corridor {corridor['corridor_id']} · rank {corridor['rank']} · "
                        f"edge {edge_id} · score {corridor['score']:.0f}"
                    ),
                ).add_to(layer)
        layer.add_to(fmap)

    if settings.show_stations and not stations.empty:
        layer = folium.FeatureGroup(name="Existing stations")
        for _, row in stations.iterrows():
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=6,
                color="#ffffff",
                weight=1.5,
                fill=True,
                fill_color=STATION_COLOR,
                fill_opacity=0.95,
                tooltip=f"{row['name']} ({row['station_id']})",
            ).add_to(layer)
        layer.add_to(fmap)

    candidates = for_scenario(data.get("station_candidates"), scenario)
    if settings.show_proposed and not candidates.empty:
        layer = folium.FeatureGroup(name="Proposed stations")
        skipped = 0
        for _, row in candidates.iterrows():
            center = cell_center(row["cell_id"])
            if center is None or not in_bbox(center[0], center[1], bbox):
                skipped += 1
                continue
            folium.RegularPolygonMarker(
                location=center,
                number_of_sides=6,
                radius=9,
                color="#ffffff",
                weight=1.5,
                fill_color=PROPOSED_COLOR,
                fill_opacity=0.95,
                tooltip=(
                    f"Proposed new:{row['cell_id']} · rank {row['rank']} · "
                    f"population {row['population']:.0f} · score {row['score']:.2f}"
                ),
            ).add_to(layer)
        layer.add_to(fmap)
        if skipped:
            notes.append(
                f"{skipped} proposed station(s) have an H3 cell outside the study area and are not drawn."
            )

    return fmap, notes


# ---------------------------------------------------------------- page sections


def render_header(data: DashboardData | None) -> None:
    left, right = st.columns([3, 1])
    left.title("🚲 MOL Bubi Bike-Lane & Station Recommendation Tool")
    if data is None:
        return
    source = "sample fixtures" if data.source == "fixtures" else "pipeline outputs"
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
    sidebar.checkbox("Show difference vs baseline", value=False, disabled=True, help="Week 5")

    sidebar.divider()
    sidebar.header("Map layers")
    settings = Settings(
        scenario=scenario,
        show_stations=sidebar.checkbox("Existing stations", value=True),
        show_proposed=sidebar.checkbox("Proposed stations", value=True),
        show_population=sidebar.checkbox("Population (H3 cells)", value=False),
        show_lanes=sidebar.checkbox("Bike-lane coverage", value=True),
        show_routes=sidebar.checkbox("Synthetic routes", value=False),
        show_corridors=sidebar.checkbox("Top corridors", value=True),
        top_n=sidebar.slider("Top corridors to show", min_value=1, max_value=50, value=10),
    )

    sidebar.divider()
    sidebar.header("Run parameters")
    sidebar.caption("Read-only, from `config/default_config.yaml`")
    scoring = config.get("station_scoring", {})
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


def render_metrics(data: DashboardData, scenario: str) -> None:
    stations = data.get("stations")
    candidates = for_scenario(data.get("station_candidates"), scenario)
    corridors = for_scenario(data.get("corridors"), scenario)
    routes = for_scenario(data.get("routes"), scenario)
    edges = data.get("edges")

    corridor_edges = edges[edges["edge_id"].isin(edge_ids_of_corridors(corridors))]
    corridor_km = corridor_edges.loc[~corridor_edges["has_dedicated_lane"], "length_m"].sum() / 1000

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stations (existing + proposed)", f"{len(stations)} + {len(candidates)}")
    c2.metric(
        "Population in proposed cells",
        f"{candidates['population'].sum():,.0f}" if not candidates.empty else "–",
        help="Newly served population is computed in week 5.",
    )
    c3.metric("Corridor km without a lane", f"{corridor_km:.2f} km")
    c4.metric(
        "Synthetic trips",
        f"{routes['trip_count'].sum():,.0f}" if not routes.empty else "–",
    )


def render_detail_panel(map_state: dict | None) -> None:
    st.markdown("#### Selected recommendation")
    clicked = (map_state or {}).get("last_object_clicked_tooltip")
    if clicked:
        st.info(clicked)
    else:
        st.caption("Click a corridor or station on the map.")
    st.caption(
        "Week 4: full score breakdown here (volume × gap length × continuity, or "
        "population × lane connectivity) and the robustness label."
    )


def render_scenario_comparison(data: DashboardData) -> None:
    st.subheader("Scenario comparison")
    st.caption(
        "Week 5: small maps per scenario, demand per newly served person, people served per km "
        "of new corridor, and robust vs station-dependent corridors. Counts below come from the "
        "loaded tables."
    )
    rows = []
    for scenario in SCENARIOS:
        corridors = for_scenario(data.get("corridors"), scenario)
        routes = for_scenario(data.get("routes"), scenario)
        rows.append(
            {
                "scenario": scenario,
                "proposed stations": len(for_scenario(data.get("station_candidates"), scenario)),
                "corridors": len(corridors),
                "synthetic trips": float(routes["trip_count"].sum()) if not routes.empty else 0.0,
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render_tables(data: DashboardData, scenario: str) -> None:
    corridors = for_scenario(data.get("corridors"), scenario)
    candidates = for_scenario(data.get("station_candidates"), scenario)
    tab1, tab2, tab3 = st.tabs(["Top corridors", "Station candidates", "Methodology & limitations"])

    with tab1:
        if corridors.empty:
            st.write("No corridors for this scenario.")
        else:
            table = corridors.sort_values("rank")
            st.dataframe(table, hide_index=True, width="stretch")
            st.download_button(
                "📥 Export corridors (CSV)",
                table.to_csv(index=False).encode("utf-8"),
                f"corridors_{scenario}.csv",
                "text/csv",
            )

    with tab2:
        if candidates.empty:
            st.write("No proposed stations in this scenario.")
        else:
            table = candidates.sort_values("rank")
            st.dataframe(table, hide_index=True, width="stretch")
            st.download_button(
                "📥 Export station candidates (CSV)",
                table.to_csv(index=False).encode("utf-8"),
                f"station_candidates_{scenario}.csv",
                "text/csv",
            )

    with tab3:
        st.markdown(
            "- Synthetic trips, routes and corridor rankings are an algorithm demonstration, "
            "not evidence of real cyclist behaviour (D5).\n"
            "- Demand is driven by population only, with no time-of-day effects (D8).\n"
            "- Routing prefers flat and downhill roads and ignores traffic and existing lanes (D2).\n"
            "- Station scores ignore legal, land-use and construction feasibility (D4).\n"
            "- Scenario results are a comparison, not a forecast.\n\n"
            "The full methodology appendix is added in week 6."
        )


# ---------------------------------------------------------------- entry point


def main() -> None:
    st.set_page_config(
        page_title="MOL Bubi Bike-Lane & Station Recommender",
        page_icon="🚲",
        layout="wide",
    )
    config = load_config()
    bbox = tuple(config.get("spatial", {}).get("study_area_bbox") or DEFAULT_BBOX)
    settings = render_sidebar(config)

    try:
        data_dir, source = resolve_data_dir()
        data = _cached_load(str(data_dir), source, _latest_change(data_dir))
    except DashboardDataError as err:
        render_header(None)
        st.error(f"**The dashboard cannot start because of a data problem.**\n\n{err}")
        st.stop()

    render_header(data)
    for warning in data.warnings:
        st.warning(warning)

    render_metrics(data, settings.scenario)

    map_col, detail_col = st.columns([3, 1])
    with map_col:
        fmap, notes = build_map(data, settings, bbox)
        map_state = st_folium(
            fmap,
            height=520,
            use_container_width=True,
            returned_objects=["last_object_clicked_tooltip"],
        )
        for note in notes:
            st.caption(f"⚠️ {note}")
    with detail_col:
        render_detail_panel(map_state)

    render_scenario_comparison(data)
    render_tables(data, settings.scenario)


if __name__ == "__main__":
    main()
