"""Ingestion module: BKK Futár station snapshot and observed trip data conversion."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bubi.ingestion import futar_snapshot as fs
from bubi.ingestion import stations_table as st


def ingest_futar_stations(
    raw_path: Path | None = None,
    api_key: str | None = None,
    out_dir: Path = fs.DEFAULT_OUT_DIR,
) -> pd.DataFrame:
    """Build the MOL Bubi stations table from a raw Futár ``bicycle-rental`` response.

    With ``raw_path`` the saved snapshot is read offline. Without it the endpoint is
    queried and the response is first stored unchanged under ``out_dir``, so every
    table can be traced back to a raw file.

    Returns:
        pd.DataFrame adhering to StationsSchema.

    Raises:
        fs.IngestionError: no API key, a non-200 response, or the two station
            selection rules disagree.
    """
    if raw_path is None:
        raw_path = _fetch_snapshot(api_key, out_dir)

    records = st.load_records(raw_path)
    report = st.compare_selections(records)
    if not report["agree"]:
        raise fs.IngestionError(
            f"Station selection rules disagree in {raw_path}: "
            f"only by type {report['only_by_type'][:10]}, "
            f"only by icon {report['only_by_icon'][:10]}"
        )
    return st.to_stations_frame(st.select_by_type(records))


def _fetch_snapshot(api_key: str | None, out_dir: Path) -> Path:
    api_key = api_key or fs.load_api_key()
    if not api_key:
        raise fs.IngestionError(f"No API key found; set {fs.ENV_KEY_NAME}")
    url = fs.build_url(api_key)
    status, body = fs.http_get(url)
    # Keep the raw body even on failure: it is the evidence for the access notes.
    raw_path, _, meta = fs.save_snapshot(body, status, url, out_dir)
    if status != 200 or meta["station_count"] is None:
        raise fs.IngestionError(
            f"Unusable Futár response (HTTP {status}) saved to {raw_path}; "
            f"endpoint {fs.redact(url)}"
        )
    return raw_path
