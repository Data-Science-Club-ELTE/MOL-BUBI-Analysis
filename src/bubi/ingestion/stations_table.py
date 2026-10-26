"""Build the processed stations table from a raw Futar ``bicycle-rental`` snapshot.

The raw response mixes fixed stations with free-floating bikes. Fixed stations
are selected in two independent ways, and the table is only written when both
selections return exactly the same records:

1. ``type == "virtual"``
2. the style icon is not ``vehicle-rental/mol-bubi-floating``

Usage (from the repository root):

    python -m bubi.ingestion.stations_table data/raw/futar_bicycle_rental_<stamp>.json

Output: ``data/processed/stations.parquet`` (columns of ``StationsSchema``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from bubi.contracts.schemas import StationsSchema

FLOATING_ICON = "vehicle-rental/mol-bubi-floating"
RAW_DIR = Path("data/raw")
DEFAULT_OUT = Path("data/processed/stations.parquet")


def icon_name(record: dict) -> str | None:
    """Return ``record["style"]["icon"]["name"]`` or None when it is missing."""
    return ((record.get("style") or {}).get("icon") or {}).get("name")


def load_records(raw_path: Path) -> list[dict]:
    payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    return payload["data"]["list"]


def select_by_type(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("type") == "virtual"]


def select_by_icon(records: list[dict]) -> list[dict]:
    return [r for r in records if icon_name(r) != FLOATING_ICON]


def compare_selections(records: list[dict]) -> dict:
    """Compare the two selection methods and describe any difference."""
    by_type = {r["id"] for r in select_by_type(records)}
    by_icon = {r["id"] for r in select_by_icon(records)}
    return {
        "total": len(records),
        "by_type": len(by_type),
        "by_icon": len(by_icon),
        "only_by_type": sorted(by_type - by_icon),
        "only_by_icon": sorted(by_icon - by_type),
        "agree": by_type == by_icon,
    }


def to_stations_frame(records: list[dict]) -> pd.DataFrame:
    """Convert station records into a DataFrame that satisfies ``StationsSchema``."""
    df = pd.DataFrame(
        {
            "station_id": [str(r["id"]) for r in records],
            "name": [r["name"] for r in records],
            "lat": [r["lat"] for r in records],
            "lon": [r["lon"] for r in records],
        }
    )
    df = df.sort_values("station_id", kind="stable").reset_index(drop=True)
    return StationsSchema.validate(df)


def build_stations_table(
    raw_path: Path, out_path: Path = DEFAULT_OUT
) -> tuple[pd.DataFrame | None, dict]:
    """Write the stations table; return (None, report) if the two selections disagree."""
    records = load_records(raw_path)
    report = compare_selections(records)
    if not report["agree"]:
        return None, report
    df = to_stations_frame(select_by_type(records))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return df, report


def latest_raw_snapshot(raw_dir: Path = RAW_DIR) -> Path:
    files = [
        p for p in sorted(raw_dir.glob("futar_bicycle_rental_*.json")) if ".meta." not in p.name
    ]
    if not files:
        raise FileNotFoundError(f"No raw snapshot found in {raw_dir}")
    return files[-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_file", nargs="?", type=Path, help="raw snapshot (default: latest)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    raw_file = args.raw_file or latest_raw_snapshot()
    print(f"Raw snapshot : {raw_file}")
    df, report = build_stations_table(raw_file, args.out)
    print(f"Total records       : {report['total']}")
    print(f"type == 'virtual'   : {report['by_type']}")
    print(f"icon is not floating: {report['by_icon']}")
    if df is None:
        print("The two selections DIFFER, nothing was written.", file=sys.stderr)
        print(f"Only by type: {report['only_by_type'][:10]}", file=sys.stderr)
        print(f"Only by icon: {report['only_by_icon'][:10]}", file=sys.stderr)
        return 1
    print(f"Selections agree. Wrote {len(df)} stations to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
