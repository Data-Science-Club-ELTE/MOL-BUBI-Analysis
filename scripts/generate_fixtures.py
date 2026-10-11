#!/usr/bin/env python3
"""Generate small, self-contained mock fixtures for Budapest Belváros.

Allows all team members to develop and unit-test modules in isolation without
waiting for real BKK API keys, OSMnx downloads, or WorldPop rasters.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from bubi.contracts.io import save_contract_table


def generate_all_fixtures(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Generating contract fixtures in {output_dir}...")

    # 1. Stations (Futár snapshot) - Central Budapest
    stations_data = [
        {"station_id": "futar_001", "name": "Deák Ferenc tér", "lat": 47.4979, "lon": 19.0541},
        {"station_id": "futar_002", "name": "Kálvin tér", "lat": 47.4893, "lon": 19.0617},
        {"station_id": "futar_003", "name": "Oktogon", "lat": 47.5058, "lon": 19.0632},
        {"station_id": "futar_004", "name": "Fővám tér", "lat": 47.4862, "lon": 19.0558},
        {"station_id": "futar_005", "name": "Blaha Lujza tér", "lat": 47.4962, "lon": 19.0706},
    ]
    df_stations = pd.DataFrame(stations_data)
    save_contract_table(df_stations, "stations", output_dir / "sample_stations.parquet")

    # 2. Population (H3 res 9 cells)
    # Valid H3 res 9 indices around central Budapest
    h3_cells = [
        "891e285818fffff",
        "891e2858193ffff",
        "891e2858197ffff",
        "891e2858183ffff",
        "891e285818bffff",
        "891e28581a3ffff",
        "891e28581a7ffff",
        "891e28581abffff",
    ]
    pop_data = [
        {"cell_id": h3_cells[0], "population": 420.0},
        {"cell_id": h3_cells[1], "population": 610.0},
        {"cell_id": h3_cells[2], "population": 315.0},
        {"cell_id": h3_cells[3], "population": 520.0},
        {"cell_id": h3_cells[4], "population": 890.0},
        {"cell_id": h3_cells[5], "population": 380.0},
        {"cell_id": h3_cells[6], "population": 710.0},
        {"cell_id": h3_cells[7], "population": 250.0},
    ]
    df_population = pd.DataFrame(pop_data)
    save_contract_table(df_population, "population", output_dir / "sample_population.parquet")

    # 3. Directed Edges (OSM street graph snippet)
    edges_data = [
        {
            "edge_id": "n1-n2-0",
            "osm_way_id": 1001,
            "length_m": 450.0,
            "has_dedicated_lane": True,  # has bike lane
            "geometry": LineString([(19.0541, 47.4979), (19.0617, 47.4893)]),
        },
        {
            "edge_id": "n2-n1-0",
            "osm_way_id": 1001,
            "length_m": 450.0,
            "has_dedicated_lane": False,  # lane missing in reverse direction
            "geometry": LineString([(19.0617, 47.4893), (19.0541, 47.4979)]),
        },
        {
            "edge_id": "n1-n3-0",
            "osm_way_id": 1002,
            "length_m": 720.0,
            "has_dedicated_lane": False,  # missing lane
            "geometry": LineString([(19.0541, 47.4979), (19.0632, 47.5058)]),
        },
        {
            "edge_id": "n3-n1-0",
            "osm_way_id": 1002,
            "length_m": 720.0,
            "has_dedicated_lane": False,  # missing lane
            "geometry": LineString([(19.0632, 47.5058), (19.0541, 47.4979)]),
        },
        {
            "edge_id": "n2-n4-0",
            "osm_way_id": 1003,
            "length_m": 380.0,
            "has_dedicated_lane": True,  # has lane
            "geometry": LineString([(19.0617, 47.4893), (19.0558, 47.4862)]),
        },
        {
            "edge_id": "n4-n2-0",
            "osm_way_id": 1003,
            "length_m": 380.0,
            "has_dedicated_lane": True,  # has lane
            "geometry": LineString([(19.0558, 47.4862), (19.0617, 47.4893)]),
        },
        {
            "edge_id": "n1-n5-0",
            "osm_way_id": 1004,
            "length_m": 950.0,
            "has_dedicated_lane": False,  # missing lane
            "geometry": LineString([(19.0541, 47.4979), (19.0706, 47.4962)]),
        },
        {
            "edge_id": "n5-n1-0",
            "osm_way_id": 1004,
            "length_m": 950.0,
            "has_dedicated_lane": False,  # missing lane
            "geometry": LineString([(19.0706, 47.4962), (19.0541, 47.4979)]),
        },
    ]
    gdf_edges = gpd.GeoDataFrame(edges_data, crs="EPSG:4326")
    save_contract_table(gdf_edges, "edges", output_dir / "sample_edges.parquet")

    # 4. Station Candidates
    candidates_data = [
        {
            "scenario": "lane_aware",
            "cell_id": h3_cells[5],
            "population": 380.0,
            "lane_connectivity": 0.85,
            "score": 0.81,
            "rank": 1,
        },
        {
            "scenario": "lane_aware",
            "cell_id": h3_cells[6],
            "population": 710.0,
            "lane_connectivity": 0.40,
            "score": 0.55,
            "rank": 2,
        },
        {
            "scenario": "population_only",
            "cell_id": h3_cells[6],
            "population": 710.0,
            "lane_connectivity": None,
            "score": 0.95,
            "rank": 1,
        },
        {
            "scenario": "population_only",
            "cell_id": h3_cells[5],
            "population": 380.0,
            "lane_connectivity": None,
            "score": 0.52,
            "rank": 2,
        },
    ]
    df_candidates = pd.DataFrame(candidates_data)
    save_contract_table(
        df_candidates, "station_candidates", output_dir / "sample_station_candidates.parquet"
    )

    # 5. Routes table
    routes_data = [
        {
            "scenario": "baseline",
            "start_station_id": "futar_001",
            "end_station_id": "futar_002",
            "route_type": "synthetic",
            "edges": "n1-n2-0",
            "trip_count": 120.0,
        },
        {
            "scenario": "baseline",
            "start_station_id": "futar_002",
            "end_station_id": "futar_001",
            "route_type": "synthetic",
            "edges": "n2-n1-0",
            "trip_count": 115.0,
        },
        {
            "scenario": "baseline",
            "start_station_id": "futar_001",
            "end_station_id": "futar_003",
            "route_type": "synthetic",
            "edges": "n1-n3-0",
            "trip_count": 210.0,
        },
        {
            "scenario": "baseline",
            "start_station_id": "futar_001",
            "end_station_id": "futar_005",
            "route_type": "synthetic",
            "edges": "n1-n5-0",
            "trip_count": 180.0,
        },
        {
            "scenario": "lane_aware",
            "start_station_id": "futar_001",
            "end_station_id": f"new:{h3_cells[5]}",
            "route_type": "synthetic",
            "edges": "n1-n3-0",
            "trip_count": 95.0,
        },
        {
            "scenario": "population_only",
            "start_station_id": "futar_001",
            "end_station_id": f"new:{h3_cells[6]}",
            "route_type": "synthetic",
            "edges": "n1-n5-0",
            "trip_count": 140.0,
        },
    ]
    df_routes = pd.DataFrame(routes_data)
    save_contract_table(df_routes, "routes", output_dir / "sample_routes.parquet")

    # 6. Edge Scores
    edge_scores_data = [
        {"scenario": "baseline", "edge_id": "n1-n3-0", "volume": 210.0, "score": 1512.0, "rank": 1},
        {"scenario": "baseline", "edge_id": "n1-n5-0", "volume": 180.0, "score": 1710.0, "rank": 2},
        {"scenario": "baseline", "edge_id": "n2-n1-0", "volume": 115.0, "score": 517.5, "rank": 3},
        {
            "scenario": "lane_aware",
            "edge_id": "n1-n3-0",
            "volume": 305.0,
            "score": 2196.0,
            "rank": 1,
        },
        {
            "scenario": "lane_aware",
            "edge_id": "n1-n5-0",
            "volume": 180.0,
            "score": 1710.0,
            "rank": 2,
        },
        {
            "scenario": "population_only",
            "edge_id": "n1-n5-0",
            "volume": 320.0,
            "score": 3040.0,
            "rank": 1,
        },
        {
            "scenario": "population_only",
            "edge_id": "n1-n3-0",
            "volume": 210.0,
            "score": 1512.0,
            "rank": 2,
        },
    ]
    df_edge_scores = pd.DataFrame(edge_scores_data)
    save_contract_table(df_edge_scores, "edge_scores", output_dir / "sample_edge_scores.parquet")

    # 7. Corridors
    corridors_data = [
        {
            "scenario": "baseline",
            "corridor_id": "corr_bl_01",
            "edge_ids": "n1-n3-0",
            "score": 1512.0,
            "rank": 1,
        },
        {
            "scenario": "baseline",
            "corridor_id": "corr_bl_02",
            "edge_ids": "n1-n5-0",
            "score": 1710.0,
            "rank": 2,
        },
        {
            "scenario": "lane_aware",
            "corridor_id": "corr_la_01",
            "edge_ids": "n1-n3-0",
            "score": 2196.0,
            "rank": 1,
        },
        {
            "scenario": "population_only",
            "corridor_id": "corr_po_01",
            "edge_ids": "n1-n5-0",
            "score": 3040.0,
            "rank": 1,
        },
    ]
    df_corridors = pd.DataFrame(corridors_data)
    save_contract_table(df_corridors, "corridors", output_dir / "sample_corridors.parquet")

    # Trip Matrix handoff interface
    trip_matrix_data = [
        {
            "scenario": "baseline",
            "start_station_id": "futar_001",
            "end_station_id": "futar_002",
            "trip_count": 120.0,
        },
        {
            "scenario": "baseline",
            "start_station_id": "futar_002",
            "end_station_id": "futar_001",
            "trip_count": 115.0,
        },
        {
            "scenario": "baseline",
            "start_station_id": "futar_001",
            "end_station_id": "futar_003",
            "trip_count": 210.0,
        },
    ]
    df_trip_matrix = pd.DataFrame(trip_matrix_data)
    save_contract_table(df_trip_matrix, "trip_matrix", output_dir / "sample_trip_matrix.parquet")

    print(f"All 7 contract tables + trip matrix generated successfully in {output_dir}.")


if __name__ == "__main__":
    import sys

    target_dir = Path("tests/fixtures") if len(sys.argv) < 2 else Path(sys.argv[1])
    generate_all_fixtures(target_dir)
