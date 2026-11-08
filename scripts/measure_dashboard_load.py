"""Measure how long the dashboard needs to prepare the full-city baseline map.

Times the server-side steps of the main map: loading and validating the edges table,
building the lane-status GeoJSON layer, building the route-volume layer, building the
Folium map, and rendering it to HTML. It also reports the page size the browser has to download. Drawing time in the
browser is not included; open the dashboard to see that.

Until the real Budapest network is merged, the script generates a synthetic
city-sized edge table spread over Budapest, and synthetic routes over it.

Usage:
    make measure-dashboard
    make measure-dashboard MEASURE_ARGS="--n-edges 300000"
    make measure-dashboard MEASURE_ARGS="--n-routes 20000"        # plus the route-volume layer
    make measure-dashboard MEASURE_ARGS="--edges data/processed/edges.parquet"
    make measure-dashboard MEASURE_ARGS="--save-edges /tmp/city/edges.parquet"
"""

from __future__ import annotations

import argparse
import logging
import math
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString

from bubi.contracts.io import load_contract_table, validate_table
from bubi.dashboard.app import Settings, build_map, lane_status_geojson, route_volume_layer
from bubi.dashboard.data import FIXTURES_DIR, PROCESSED_DIR, DashboardData

# Budapest's administrative extent, roughly.
BBOX = (18.93, 47.35, 19.33, 47.61)  # min lon, min lat, max lon, max lat
METRES_PER_DEG_LAT = 111_320.0


def synthetic_edges(n_edges: int, seed: int = 42) -> gpd.GeoDataFrame:
    """A random street network over Budapest, with both directions of every street.

    Streets have 2 to 6 points, 30 to 80 m apart. About 10% have a lane both ways and
    another 10% a lane in one direction only, so both colours and one-sided lanes appear.
    """
    rng = np.random.default_rng(seed)
    n_streets = max(1, n_edges // 2)
    lon_scale = METRES_PER_DEG_LAT * math.cos(math.radians((BBOX[1] + BBOX[3]) / 2))

    rows = []
    for i in range(n_streets):
        lon = rng.uniform(BBOX[0], BBOX[2])
        lat = rng.uniform(BBOX[1], BBOX[3])
        heading = rng.uniform(0, 2 * math.pi)
        points = [(lon, lat)]
        for _ in range(rng.integers(1, 6)):
            heading += rng.normal(0, 0.3)
            step = rng.uniform(30, 80)
            lon += step * math.cos(heading) / lon_scale
            lat += step * math.sin(heading) / METRES_PER_DEG_LAT
            points.append((lon, lat))
        line = LineString(points)
        length = sum(
            math.hypot((x1 - x0) * lon_scale, (y1 - y0) * METRES_PER_DEG_LAT)
            for (x0, y0), (x1, y1) in zip(points, points[1:])
        )
        draw = rng.random()
        forward, back = draw < 0.15, draw < 0.10 or 0.15 <= draw < 0.20
        rows.append((f"s{i}a-s{i}b-0", i, length, forward, line))
        rows.append((f"s{i}b-s{i}a-0", i, length, back, line.reverse()))

    edge_id, way_id, length_m, lane, geometry = zip(*rows)
    return gpd.GeoDataFrame(
        {
            "edge_id": edge_id,
            "osm_way_id": way_id,
            "length_m": length_m,
            "has_dedicated_lane": lane,
        },
        geometry=list(geometry),
        crs="EPSG:4326",
    )


def synthetic_routes(
    edges: gpd.GeoDataFrame, n_routes: int, edges_per_route: int = 50, seed: int = 42
) -> pd.DataFrame:
    """Baseline routes that each use ``edges_per_route`` random edges.

    The edges are not a connected path; that does not matter for timing, which depends
    on how many (route, edge) pairs are counted and how many distinct edges get a volume.
    Trip counts are heavy-tailed like gravity-model output.
    """
    rng = np.random.default_rng(seed)
    ids = edges["edge_id"].to_numpy()
    return pd.DataFrame(
        {
            "scenario": "baseline",
            "start_station_id": [f"s{i}" for i in range(n_routes)],
            "end_station_id": [f"t{i}" for i in range(n_routes)],
            "route_type": "synthetic",
            "edges": [list(rng.choice(ids, edges_per_route)) for _ in range(n_routes)],
            "trip_count": np.round(rng.lognormal(1.0, 1.0, n_routes), 1) + 0.1,
        }
    )


def load_stations() -> pd.DataFrame:
    processed = PROCESSED_DIR / "stations.parquet"
    path = processed if processed.exists() else FIXTURES_DIR / "sample_stations.parquet"
    return load_contract_table("stations", path)


def measure(
    edges: gpd.GeoDataFrame, stations: pd.DataFrame, routes: pd.DataFrame | None = None
) -> list[tuple[str, str]]:
    """Run the main-map steps once and return (step, result) rows."""
    results = []

    started = time.perf_counter()
    edges = validate_table(edges, "edges")
    results.append(("Validate edges (EdgesSchema)", f"{time.perf_counter() - started:.2f} s"))

    started = time.perf_counter()
    geojson = lane_status_geojson(edges)
    results.append(("Build lane-status GeoJSON", f"{time.perf_counter() - started:.2f} s"))

    tables = {"stations": stations, "edges": edges}
    route_layer = None
    if routes is not None and not routes.empty:
        tables["routes"] = routes
        started = time.perf_counter()
        route_layer = route_volume_layer(edges, routes)
        results.append(("Build route-volume layer", f"{time.perf_counter() - started:.2f} s"))
        results.append(("Edges with route volume", f"{route_layer.n_edges:,}"))

    data = DashboardData(tables=tables)
    settings = Settings(
        scenario="baseline",
        basemap="OpenStreetMap",
        show_stations=True,
        show_proposed=False,
        show_population=False,
        show_lanes=True,
        show_routes=route_layer is not None,
        show_corridors=False,
        top_n=10,
    )
    started = time.perf_counter()
    fmap, _ = build_map(data, settings, geojson, route_layer)
    results.append(("Build Folium map", f"{time.perf_counter() - started:.2f} s"))

    started = time.perf_counter()
    html = fmap.get_root().render()
    results.append(("Render map to HTML", f"{time.perf_counter() - started:.2f} s"))
    results.append(("Page size", f"{len(html.encode('utf-8')) / 1e6:.1f} MB"))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--edges", type=Path, help="Edges table (GeoParquet) to measure.")
    source.add_argument(
        "--n-edges",
        type=int,
        default=200_000,
        help="Size of the synthetic network when --edges is not given (default: 200000).",
    )
    parser.add_argument(
        "--n-routes",
        type=int,
        default=0,
        help="Synthetic routes of 50 edges each over the measured edges, to also time the "
        "route-volume layer (default: 0, street layer only).",
    )
    parser.add_argument("--save-edges", type=Path, help="Also write the measured edges here.")
    args = parser.parse_args()

    # Streamlit warns about running outside `streamlit run`; that is expected here.
    logging.getLogger("streamlit").setLevel(logging.ERROR)

    if args.edges:
        edges = load_contract_table("edges", args.edges)
        label = str(args.edges)
    else:
        edges = synthetic_edges(args.n_edges)
        label = "synthetic network over Budapest (seed 42)"
    stations = load_stations()
    routes = synthetic_routes(edges, args.n_routes) if args.n_routes > 0 else None

    if args.save_edges:
        args.save_edges.parent.mkdir(parents=True, exist_ok=True)
        edges.to_parquet(args.save_edges, index=False)

    print(f"Edges: {len(edges):,} directed edges, {label}")
    print(f"Stations: {len(stations):,}")
    print(f"Routes: {0 if routes is None else len(routes):,} synthetic, 50 edges each")
    for step, result in measure(edges, stations, routes):
        print(f"  {step:<30} {result}")


if __name__ == "__main__":
    main()
