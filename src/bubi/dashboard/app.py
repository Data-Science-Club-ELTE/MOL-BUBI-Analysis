"""Interactive Streamlit + Folium dashboard for MOL Bubi recommendations."""

from pathlib import Path

import folium
import streamlit as st
from streamlit_folium import st_folium

from bubi.contracts.io import load_contract_table

st.set_page_config(
    page_title="MOL Bubi Bike-Lane & Station Recommender",
    page_icon="🚲",
    layout="wide",
)


def get_data_dir() -> Path:
    """Resolve data directory (processed first, fallback to fixtures)."""
    processed = Path("data/processed")
    if (processed / "stations.parquet").exists():
        return processed
    return Path("tests/fixtures")


def load_scenario_data(data_dir: Path, scenario: str):
    stations_file = (
        "stations.parquet"
        if (data_dir / "stations.parquet").exists()
        else "sample_stations.parquet"
    )
    edges_file = (
        "edges.parquet" if (data_dir / "edges.parquet").exists() else "sample_edges.parquet"
    )
    candidates_file = (
        "station_candidates.parquet"
        if (data_dir / "station_candidates.parquet").exists()
        else "sample_station_candidates.parquet"
    )
    corridors_file = (
        "corridors.parquet"
        if (data_dir / "corridors.parquet").exists()
        else "sample_corridors.parquet"
    )
    edge_scores_file = (
        "edge_scores.parquet"
        if (data_dir / "edge_scores.parquet").exists()
        else "sample_edge_scores.parquet"
    )

    df_stations = load_contract_table("stations", data_dir / stations_file, validate=False)
    gdf_edges = load_contract_table("edges", data_dir / edges_file, validate=False)
    df_candidates = load_contract_table(
        "station_candidates", data_dir / candidates_file, validate=False
    )
    df_corridors = load_contract_table("corridors", data_dir / corridors_file, validate=False)
    df_edge_scores = load_contract_table("edge_scores", data_dir / edge_scores_file, validate=False)

    df_scen_candidates = df_candidates[df_candidates["scenario"] == scenario]
    df_scen_corridors = df_corridors[df_corridors["scenario"] == scenario]
    df_scen_edge_scores = df_edge_scores[df_edge_scores["scenario"] == scenario]

    return df_stations, gdf_edges, df_scen_candidates, df_scen_corridors, df_scen_edge_scores


def main():
    st.title("🚲 MOL Bubi Bike-Lane & Station Recommendation Tool")
    st.markdown(
        "Interactive decision support tool for Budapest bike infrastructure planning. "
        "Comparing synthetic bicycle trip demand against current OpenStreetMap dedicated bike lanes."
    )

    data_dir = get_data_dir()
    if "fixtures" in str(data_dir):
        st.info("ℹ️ Running in demo/mock mode using sample fixtures from `tests/fixtures/`.")

    # Sidebar controls
    st.sidebar.header("Scenario Configuration")
    scenario = st.sidebar.selectbox(
        "Active Scenario",
        options=["baseline", "lane_aware", "population_only"],
        index=0,
        help="Baseline = existing stations. Lane-aware = sited with lanes. Pop-only = sited with density.",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("Layer Controls")
    show_stations = st.sidebar.checkbox("Existing Stations", value=True)
    show_proposed = st.sidebar.checkbox("Proposed Stations", value=True)
    show_edges = st.sidebar.checkbox("Street Network (Lane status)", value=True)
    show_top_corridors = st.sidebar.checkbox("Top Priority Corridors", value=True)

    df_stations, gdf_edges, df_candidates, df_corridors, df_edge_scores = load_scenario_data(
        data_dir, scenario
    )

    # Key Metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Active Scenario", scenario.replace("_", " ").title())
    col2.metric("Existing Stations", len(df_stations))
    col3.metric("Proposed Stations", len(df_candidates))
    col4.metric("Recommended Corridors", len(df_corridors))

    # Folium Map
    st.subheader("Interactive Infrastructure Map")
    center_lat = df_stations["lat"].mean() if not df_stations.empty else 47.4979
    center_lon = df_stations["lon"].mean() if not df_stations.empty else 19.0541

    m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles="CartoDB positron")

    # Add Street Network Edges
    if show_edges and not gdf_edges.empty:
        for _, row in gdf_edges.iterrows():
            coords = [(lat, lon) for lon, lat in row.geometry.coords]
            color = "#2ecc71" if row["has_dedicated_lane"] else "#95a5a6"
            weight = 3 if row["has_dedicated_lane"] else 1.5
            tooltip = f"Edge: {row['edge_id']} | Has Lane: {row['has_dedicated_lane']}"
            folium.PolyLine(
                coords, color=color, weight=weight, opacity=0.7, tooltip=tooltip
            ).add_to(m)

    # Highlight Top Corridors
    if show_top_corridors and not df_corridors.empty:
        corridor_edge_ids = set()
        for _, c_row in df_corridors.iterrows():
            edge_list = (
                c_row["edge_ids"] if isinstance(c_row["edge_ids"], list) else [c_row["edge_ids"]]
            )
            corridor_edge_ids.update(edge_list)

        highlight_edges = gdf_edges[gdf_edges["edge_id"].isin(corridor_edge_ids)]
        for _, row in highlight_edges.iterrows():
            coords = [(lat, lon) for lon, lat in row.geometry.coords]
            folium.PolyLine(
                coords,
                color="#e74c3c",
                weight=5,
                opacity=0.9,
                tooltip=f"HIGH PRIORITY GAP: {row['edge_id']}",
            ).add_to(m)

    # Add Existing Stations
    if show_stations:
        for _, row in df_stations.iterrows():
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=6,
                color="#2980b9",
                fill=True,
                fill_color="#3498db",
                fill_opacity=0.9,
                popup=f"Station: {row['name']} ({row['station_id']})",
                tooltip=row["name"],
            ).add_to(m)

    # Add Proposed Stations
    if show_proposed and not df_candidates.empty:
        for _, row in df_candidates.iterrows():
            # For H3 cells in candidate table
            folium.Marker(
                location=[center_lat + 0.005, center_lon + 0.005],  # Example offset location
                icon=folium.Icon(color="green", icon="plus"),
                popup=f"Proposed Station: {row['cell_id']} (Score: {row['score']:.2f})",
                tooltip=f"Proposed: {row['cell_id']}",
            ).add_to(m)

    # Render Map
    st_folium(m, width="100%", height=500)

    # Tables & Exports
    st.subheader("Priority Corridors & Station Recommendations")
    tab1, tab2 = st.tabs(["Top Corridors", "Station Candidates"])

    with tab1:
        if not df_corridors.empty:
            st.dataframe(df_corridors, use_container_width=True)
            csv_corridors = df_corridors.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Export Corridors (CSV)", csv_corridors, "corridors.csv", "text/csv"
            )
        else:
            st.write("No corridors found for this scenario.")

    with tab2:
        if not df_candidates.empty:
            st.dataframe(df_candidates, use_container_width=True)
            csv_cand = df_candidates.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Export Candidates (CSV)", csv_cand, "station_candidates.csv", "text/csv"
            )
        else:
            st.write("No proposed stations in baseline scenario.")


if __name__ == "__main__":
    main()
