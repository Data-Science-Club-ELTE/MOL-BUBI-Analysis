"""Gridded population ingestion and H3 hexagon aggregation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import h3
import numpy as np
import pandas as pd
import rasterio
import shapely
from pyproj import Transformer
from shapely import STRtree
from shapely.geometry import Polygon, box

RASTER_CRS = "EPSG:4326"
# Conformal CRS for Budapest; used only for overlap areas, never for coordinates.
AREA_CRS = "EPSG:23700"


def _transformer() -> Transformer:
    return Transformer.from_crs(RASTER_CRS, AREA_CRS, always_xy=True)


def _project_polygon(polygon: Polygon, transformer: Transformer) -> Polygon:
    """Project a lon/lat polygon by transforming its vertices."""
    x, y = transformer.transform(*np.asarray(polygon.exterior.coords).T)
    return Polygon(np.column_stack([x, y]))


def _pixel_values(src: rasterio.io.DatasetReader) -> tuple[np.ndarray, np.ndarray]:
    """Return flat pixel values and a valid-pixel mask (NoData excluded)."""
    band = src.read(1, masked=True)
    values = np.asarray(band.filled(0.0), dtype="float64").ravel()
    valid = ~np.ma.getmaskarray(band).ravel() & np.isfinite(values)
    return values, valid


def _pixel_polygons(
    src: rasterio.io.DatasetReader, transformer: Transformer
) -> tuple[np.ndarray, np.ndarray]:
    """Return every pixel as a polygon in AREA_CRS plus its area."""
    transform = src.transform
    xs = src.bounds.left + np.arange(src.width + 1) * transform.a
    ys = src.bounds.top + np.arange(src.height + 1) * transform.e
    grid_x, grid_y = np.meshgrid(xs, ys)
    px, py = transformer.transform(grid_x, grid_y)
    corners_x = [px[:-1, :-1], px[:-1, 1:], px[1:, :-1], px[1:, 1:]]
    corners_y = [py[:-1, :-1], py[:-1, 1:], py[1:, :-1], py[1:, 1:]]
    min_x = np.minimum.reduce(corners_x).ravel()
    max_x = np.maximum.reduce(corners_x).ravel()
    min_y = np.minimum.reduce(corners_y).ravel()
    max_y = np.maximum.reduce(corners_y).ravel()
    polygons = shapely.box(min_x, min_y, max_x, max_y)
    return polygons, shapely.area(polygons)


def _study_cells(
    bbox: tuple[float, float, float, float], resolution: int, transformer: Transformer
) -> tuple[list[str], np.ndarray]:
    """Return the H3 cells wholly inside the study bbox, as projected polygons."""
    min_lon, min_lat, max_lon, max_lat = bbox
    study = box(min_lon, min_lat, max_lon, max_lat)
    if not study.is_valid or study.area == 0.0:
        raise ValueError(f"Invalid study bbox: {bbox}")
    h3_shape = h3.geo_to_h3shape(study.__geo_interface__)
    # h3shape_to_cells keeps cells whose centre is in the polygon; the containment
    # filter below drops the boundary ring so every published value has full coverage.
    candidates = sorted(h3.h3shape_to_cells(h3_shape, resolution))
    boundaries = [h3.cell_to_boundary(cell) for cell in candidates]
    lats = np.concatenate([np.array([point[0] for point in b]) for b in boundaries])
    lons = np.concatenate([np.array([point[1] for point in b]) for b in boundaries])
    x, y = transformer.transform(lons, lats)
    polygons = []
    start = 0
    for boundary in boundaries:
        stop = start + len(boundary)
        polygons.append(Polygon(np.column_stack([x[start:stop], y[start:stop]])))
        start = stop
    polygons_array = np.array(polygons, dtype=object)
    inside = shapely.contains(_project_polygon(study, transformer), polygons_array)
    cells = [cell for cell, keep in zip(candidates, inside) if keep]
    return cells, polygons_array[inside]


def _overlap_weights(
    cell_polygons: np.ndarray, pixel_polygons: np.ndarray, pixel_areas: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (cell index, pixel index, overlap fraction) for every pixel-cell pair."""
    tree = STRtree(pixel_polygons)
    cell_index, pixel_index, fractions = [], [], []
    for index, cell in enumerate(cell_polygons):
        candidates = tree.query(cell)
        if candidates.size == 0:
            continue
        overlap = shapely.area(shapely.intersection(pixel_polygons[candidates], cell))
        fraction = np.clip(overlap / pixel_areas[candidates], 0.0, 1.0)
        keep = fraction > 0.0
        cell_index.append(np.full(candidates[keep].size, index))
        pixel_index.append(candidates[keep])
        fractions.append(fraction[keep])
    if not cell_index:
        empty = np.array([], dtype=int)
        return empty, empty, np.array([], dtype="float64")
    return (
        np.concatenate(cell_index),
        np.concatenate(pixel_index),
        np.concatenate(fractions),
    )


def aggregate_population_to_h3(
    raster_path: Path,
    h3_resolution: int = 9,
    bbox: Optional[tuple[float, float, float, float]] = None,
) -> pd.DataFrame:
    """Aggregate gridded population (WorldPop / GHSL raster) to H3 hexagon cells.

    Population is spread over each H3 cell by area: a pixel wholly inside a cell
    contributes its full count, a straddling pixel its count times the covered fraction.
    This assumes the people in a pixel are evenly distributed over it, which is the
    resolution limit of the source. Only cells wholly inside the bbox are returned, so
    edge cells are never published from truncated pixel coverage.

    Args:
        raster_path: Path to a population GeoTIFF in EPSG:4326, clipped to the study area.
        h3_resolution: H3 hexagon resolution (default 9).
        bbox: Optional (min_lon, min_lat, max_lon, max_lat) study area. Defaults to the
            raster bounds.

    Returns:
        pd.DataFrame adhering to PopulationSchema (cell_id, population), one row per
        selected cell including cells whose population is zero.
    """
    path = Path(raster_path)
    if not path.exists():
        raise FileNotFoundError(f"Population raster not found: {path}")

    transformer = _transformer()
    with rasterio.open(path) as src:
        if src.crs is None or src.crs.to_string() != RASTER_CRS:
            raise ValueError(f"{path} must be in {RASTER_CRS}, found {src.crs}")
        values, valid = _pixel_values(src)
        pixel_polygons, pixel_areas = _pixel_polygons(src, transformer)
        study_bbox = tuple(bbox) if bbox is not None else tuple(src.bounds)

    cells, cell_polygons = _study_cells(study_bbox, h3_resolution, transformer)
    cell_index, pixel_index, fractions = _overlap_weights(
        cell_polygons, pixel_polygons, pixel_areas
    )

    keep = valid[pixel_index]
    population = np.bincount(
        cell_index[keep],
        weights=fractions[keep] * values[pixel_index[keep]],
        minlength=len(cells),
    )
    frame = pd.DataFrame({"cell_id": cells, "population": population})
    return frame.sort_values("cell_id", ignore_index=True)
