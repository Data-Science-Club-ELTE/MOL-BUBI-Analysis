"""Gridded population ingestion and H3 hexagon aggregation."""

from pathlib import Path
from typing import Optional

import pandas as pd


def aggregate_population_to_h3(
    raster_path: Path,
    h3_resolution: int = 9,
    bbox: Optional[tuple[float, float, float, float]] = None,
) -> pd.DataFrame:
    """Aggregate gridded population (WorldPop / GHSL raster) to H3 hexagon cells.

    Args:
        raster_path: Path to population GeoTIFF raster.
        h3_resolution: H3 hexagon resolution (default 9).
        bbox: Optional (min_lon, min_lat, max_lon, max_lat) clip bounding box.

    Returns:
        pd.DataFrame adhering to PopulationSchema (cell_id, population).
    """
    raise NotImplementedError(
        "Raster to H3 aggregation not implemented yet. Implement raster read and H3 cell zonal sum."
    )
