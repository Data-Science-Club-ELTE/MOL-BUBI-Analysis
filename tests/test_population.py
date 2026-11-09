"""Tests for raster-to-H3 population aggregation."""

import h3
import numpy as np
import pytest
import rasterio
import shapely
from rasterio.transform import from_origin
from shapely.geometry import box

from bubi.contracts.io import validate_table
from bubi.population.grid import _overlap_weights, aggregate_population_to_h3

CELL = h3.latlng_to_cell(47.4979, 19.0541, 9)
PIXEL_DEGREES = 1 / 1200


def write_raster(path, values, *, left, top, nodata=None):
    height, width = values.shape
    transform = from_origin(left, top, PIXEL_DEGREES, PIXEL_DEGREES)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=nodata,
    ) as dst:
        dst.write(values.astype("float32"), 1)
    return path


def cell_raster(tmp_path, values, *, nodata=None):
    """Raster whose pixel centres straddle CELL, with a known centre pixel."""
    lat, lon = h3.cell_to_latlng(CELL)
    left = lon - 5.5 * PIXEL_DEGREES
    top = lat + 5.5 * PIXEL_DEGREES
    return write_raster(tmp_path / "cell.tif", values, left=left, top=top, nodata=nodata)


def cell_bbox(padding=0.0005):
    boundary = h3.cell_to_boundary(CELL)
    lats = [point[0] for point in boundary]
    lons = [point[1] for point in boundary]
    return (min(lons) - padding, min(lats) - padding, max(lons) + padding, max(lats) + padding)


def test_centre_pixel_wholly_inside_cell_contributes_its_value(tmp_path):
    values = np.zeros((12, 12))
    values[5, 5] = 10.0
    result = aggregate_population_to_h3(cell_raster(tmp_path, values), bbox=cell_bbox())

    assert result["cell_id"].tolist() == [CELL]
    assert result["population"].iloc[0] == pytest.approx(10.0)


def test_zero_population_cell_is_still_published(tmp_path):
    result = aggregate_population_to_h3(cell_raster(tmp_path, np.zeros((12, 12))), bbox=cell_bbox())

    assert result["cell_id"].tolist() == [CELL]
    assert result["population"].iloc[0] == 0.0


def test_nodata_pixels_are_excluded(tmp_path):
    values = np.zeros((12, 12))
    values[5, 5] = 10.0
    values[5, 6] = -99999.0
    result = aggregate_population_to_h3(
        cell_raster(tmp_path, values, nodata=-99999.0), bbox=cell_bbox()
    )

    assert result["population"].iloc[0] == pytest.approx(10.0)


def test_overlap_fractions_sum_to_one_per_pixel():
    pixels = np.array([box(0.0, 0.0, 10.0, 10.0)], dtype=object)
    cells = np.array([box(0.0, 0.0, 5.0, 10.0), box(5.0, 0.0, 10.0, 10.0)], dtype=object)
    cell_index, pixel_index, fractions = _overlap_weights(cells, pixels, shapely.area(pixels))

    covered = np.bincount(pixel_index, weights=fractions)
    np.testing.assert_allclose(covered, 1.0)
    assert sorted(np.bincount(cell_index)) == [1, 1]


def test_bbox_aggregation_invariants(tmp_path):
    lat, lon = h3.cell_to_latlng(CELL)
    bbox = (lon - 0.025, lat - 0.015, lon + 0.025, lat + 0.015)
    width = int(round((bbox[2] - bbox[0]) / PIXEL_DEGREES))
    height = int(round((bbox[3] - bbox[1]) / PIXEL_DEGREES))
    values = np.linspace(0.0, 100.0, width * height).reshape(height, width)
    path = write_raster(tmp_path / "bbox.tif", values, left=bbox[0], top=bbox[3])

    result = aggregate_population_to_h3(path, bbox=bbox)

    validated = validate_table(result, "population")
    assert not validated.empty
    assert validated["cell_id"].is_unique
    assert all(h3.is_valid_cell(cell) for cell in validated["cell_id"])
    assert (validated["population"] >= 0.0).all()
    assert validated["population"].sum() <= values.sum() + 1e-6
