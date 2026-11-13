#!/usr/bin/env python3
"""Aggregate a population raster into H3 cells and validate the result.

Sample deliverable for issue #9: turn a WorldPop or GHSL GeoTIFF into a table
with ``cell_id`` and ``population`` that satisfies ``PopulationSchema``.

    python scripts/population_h3_sample.py \
        --raster data/raw/worldpop2026_density.tif \
        --output data/processed/population_h3_sample.parquet

Rasters are git-ignored. See ``docs/population_source.md`` for the product,
download URL and checksum behind the sample.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import h3
import numpy as np
import pandas as pd
import rasterio as rio
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon

from bubi.contracts.schemas import PopulationSchema

# Deak Ferenc ter, central Budapest: the area the contract fixtures also use.
DEFAULT_BBOX = (19.0441, 47.4879, 19.0641, 47.5079)  # min_lon, min_lat, max_lon, max_lat
DEFAULT_RESOLUTION = 9


def aggregate_to_h3(
    raster_path: Path,
    bbox: tuple[float, float, float, float],
    resolution: int = DEFAULT_RESOLUTION,
) -> pd.DataFrame:
    """Sum a population raster into H3 cells by area-weighted overlap.

    Each raster cell contributes ``value * (overlapped area / cell area)``, so a cell
    straddling an H3 boundary is split in proportion instead of being assigned
    wholesale to one hexagon. Nodata counts as zero population: in a constrained
    WorldPop product it marks land outside mapped settlement, not a missing value.

    Args:
        raster_path: Population GeoTIFF holding people per cell, not density.
        bbox: Study area as (min_lon, min_lat, max_lon, max_lat) in EPSG:4326.
        resolution: H3 resolution, 9 in the data contract.

    Returns:
        DataFrame with ``cell_id`` and ``population``, sorted by ``cell_id``.
    """
    with rio.open(raster_path) as src:
        data = src.read(1).astype("float64")
        if src.nodata is not None:
            data = np.where(data == src.nodata, 0.0, data)
        transform = src.transform
        to_source = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        rows = []

        for cell in h3.geo_to_cells(_bbox_geojson(bbox), resolution):
            ring = [(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]
            gx, gy = to_source.transform(*np.array(ring).T)
            hexagon = Polygon(np.column_stack([gx, gy]))
            window = _window(src, hexagon)
            if window is None:
                continue
            i0, i1, j0, j1 = window
            weights = _coverage(hexagon, transform, i0, i1, j0, j1)
            total = float((data[j0 : j1 + 1, i0 : i1 + 1] * weights).sum())
            rows.append({"cell_id": cell, "population": total})

    frame = pd.DataFrame(rows, columns=["cell_id", "population"]).sort_values("cell_id")
    return frame.reset_index(drop=True)


def _bbox_geojson(bbox: tuple[float, float, float, float]) -> dict:
    min_lon, min_lat, max_lon, max_lat = bbox
    ring = [
        [min_lon, min_lat],
        [max_lon, min_lat],
        [max_lon, max_lat],
        [min_lon, max_lat],
        [min_lon, min_lat],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def _window(src: rio.io.DatasetReader, hexagon: Polygon) -> tuple[int, int, int, int] | None:
    """Inclusive raster window (i0, i1, j0, j1) covering the hexagon's bounds."""
    transform = src.transform
    minx, miny, maxx, maxy = hexagon.bounds
    i0 = max(0, math.floor((minx - transform.c) / transform.a))
    i1 = min(src.width - 1, math.floor((maxx - transform.c) / transform.a))
    j0 = max(0, math.floor((maxy - transform.f) / transform.e))
    j1 = min(src.height - 1, math.floor((miny - transform.f) / transform.e))
    if i1 < i0 or j1 < j0:
        return None
    return i0, i1, j0, j1


def _coverage(
    hexagon: Polygon,
    transform: rio.Affine,
    i0: int,
    i1: int,
    j0: int,
    j1: int,
) -> np.ndarray:
    """Share of each raster cell covered by the hexagon, clipped to [0, 1]."""
    xs = transform.c + np.arange(i0, i1 + 1) * transform.a
    ys = transform.f + np.arange(j0, j1 + 1) * transform.e
    cells = shapely.box(
        xs[None, :], ys[:, None], xs[None, :] + transform.a, ys[:, None] + transform.e
    )
    areas = shapely.area(shapely.intersection(hexagon, cells))
    return np.clip(areas / abs(transform.a * transform.e), 0.0, 1.0)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raster", type=Path, required=True, help="population GeoTIFF")
    parser.add_argument("--output", type=Path, required=True, help="destination .parquet")
    parser.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        default=list(DEFAULT_BBOX),
        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
        help="study area, default is Deak Ferenc ter +- 0.01 degrees",
    )
    parser.add_argument("--resolution", type=int, default=DEFAULT_RESOLUTION, help="H3 resolution")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.raster.exists():
        print(f"Raster not found: {args.raster}")
        print("Rasters are git-ignored. docs/population_source.md lists the download")
        print("URL and the checksum to verify the copy against.")
        return 1

    frame = aggregate_to_h3(args.raster, tuple(args.bbox), args.resolution)
    validated = PopulationSchema.validate(frame)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    validated.to_parquet(args.output, index=False)

    print(f"{len(validated)} cells at H3 resolution {args.resolution}")
    print(f"total population {validated['population'].sum():,.0f}")
    print(f"range {validated['population'].min():,.1f} - {validated['population'].max():,.1f}")
    print(f"validated against PopulationSchema, written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
