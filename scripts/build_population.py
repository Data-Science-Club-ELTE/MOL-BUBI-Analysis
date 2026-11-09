#!/usr/bin/env python3
"""Build the population table: clipped raster -> H3 cells, validated Parquet."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import rasterio
import yaml

from bubi.contracts.io import save_contract_table
from bubi.population.grid import aggregate_population_to_h3

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path("config/default_config.yaml")


def raster_total(path: Path) -> float:
    """Sum the raster, ignoring NoData pixels."""
    with rasterio.open(path) as src:
        return float(src.read(1, masked=True).sum())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    parser.add_argument("--config", type=Path, help="default: <root>/config/default_config.yaml")
    args = parser.parse_args(argv)

    config_path = args.config or args.root / DEFAULT_CONFIG
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_dir = args.root / config["paths"]["data_raw_dir"]
    raster_path = raw_dir / config["demand"]["population_raster_file"]
    output_path = args.root / config["paths"]["data_processed_dir"] / "population.parquet"
    bbox = tuple(config["spatial"]["study_area_bbox"])

    started = time.perf_counter()
    frame = aggregate_population_to_h3(
        raster_path,
        h3_resolution=config["spatial"]["h3_resolution"],
        bbox=bbox,
    )
    elapsed = time.perf_counter() - started

    saved = save_contract_table(frame, "population", output_path)
    total = frame["population"].sum()
    raster_sum = raster_total(raster_path)
    dropped = raster_sum - total
    dropped_share = dropped / raster_sum if raster_sum else 0.0

    print(f"population table {saved}")
    print(f"  source   {raster_path} ({config['demand']['population_source']})")
    print(f"  bbox     {bbox}")
    print(f"  cells    {len(frame)} ({int((frame['population'] > 0).sum())} populated)")
    print(f"  total    {total:.1f} people")
    print(
        f"  clipped raster total {raster_sum:.1f}; edge ring excluded {dropped:.1f} "
        f"({dropped_share:.2%})"
    )
    print(f"  elapsed  {elapsed:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
