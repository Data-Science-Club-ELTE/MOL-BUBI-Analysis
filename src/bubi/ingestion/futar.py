"""Ingestion module: BKK Futár station snapshot and observed trip data conversion."""

from pathlib import Path
from typing import Optional

import pandas as pd

from bubi.contracts.schemas import StationsSchema


def ingest_futar_stations(
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    snapshot_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Fetch MOL Bubi stations from BKK Futár API or load existing snapshot.

    Returns:
        pd.DataFrame adhering to StationsSchema.
    """
    if snapshot_path and Path(snapshot_path).exists():
        df = pd.read_parquet(snapshot_path)
        return StationsSchema.validate(df)

    # In production, query BKK Futár API
    # Example endpoint: https://futar.bkk.hu/api/query/v1/ws/otp/api/where/bicycle-rental.json
    raise NotImplementedError(
        "BKK API fetch not implemented yet. Set up BKK API key and write ingestion logic."
    )
