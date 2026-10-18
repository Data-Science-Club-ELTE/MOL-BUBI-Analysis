"""I/O functions and schema validation wrappers for MOL Bubi data contracts."""

from pathlib import Path
from typing import Union

import geopandas as gpd
import pandas as pd
import pandera as pa

from bubi.contracts.schemas import (
    CorridorsSchema,
    EdgeScoresSchema,
    EdgesSchema,
    PopulationSchema,
    RoutesSchema,
    StationCandidatesSchema,
    StationsSchema,
    TripMatrixSchema,
)

SCHEMA_REGISTRY: dict[str, pa.DataFrameSchema] = {
    "stations": StationsSchema,
    "population": PopulationSchema,
    "edges": EdgesSchema,
    "station_candidates": StationCandidatesSchema,
    "routes": RoutesSchema,
    "edge_scores": EdgeScoresSchema,
    "corridors": CorridorsSchema,
    "trip_matrix": TripMatrixSchema,
}


def validate_table(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    """Validate DataFrame against the named data contract schema."""
    if table_name not in SCHEMA_REGISTRY:
        raise ValueError(
            f"Unknown table '{table_name}'. Registered: {list(SCHEMA_REGISTRY.keys())}"
        )
    schema = SCHEMA_REGISTRY[table_name]
    return schema.validate(df)


def save_contract_table(
    df: Union[pd.DataFrame, gpd.GeoDataFrame],
    table_name: str,
    output_path: Union[str, Path],
    validate: bool = True,
) -> Path:
    """Validate and persist a contract table to Parquet/GeoParquet."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if validate:
        df = validate_table(df, table_name)

    if isinstance(df, gpd.GeoDataFrame):
        if df.crs is None:
            df = df.set_crs("EPSG:4326")
        elif df.crs.to_string() != "EPSG:4326":
            df = df.to_crs("EPSG:4326")
        df.to_parquet(path)
    else:
        df.to_parquet(path, index=False)

    return path


def load_contract_table(
    table_name: str,
    input_path: Union[str, Path],
    validate: bool = True,
) -> Union[pd.DataFrame, gpd.GeoDataFrame]:
    """Read Parquet/GeoParquet table and optionally validate against schema."""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Contract table '{table_name}' not found at {path}")

    if table_name == "edges":
        df = gpd.read_parquet(path)
        if df.crs is None:
            df = df.set_crs("EPSG:4326")
    else:
        df = pd.read_parquet(path)

    if validate:
        df = validate_table(df, table_name)

    return df


def export_geojson(gdf: gpd.GeoDataFrame, output_path: Union[str, Path]) -> Path:
    """Export GeoDataFrame to GeoJSON in EPSG:4326 for presentation/GIS."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif gdf.crs.to_string() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
    gdf.to_file(path, driver="GeoJSON")
    return path


def export_csv(df: pd.DataFrame, output_path: Union[str, Path]) -> Path:
    """Export tabular DataFrame to CSV for presentation/reporting."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path
