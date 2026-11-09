#!/usr/bin/env python3
"""Clip the chosen population raster to the Budapest study bbox with gdal_translate.

The clipped GeoTIFF is a derived input, so it stays in data/raw/ next to the country
raster rather than in data/processed/, which holds contract tables only.

  python scripts/clip_population.py
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path("config/default_config.yaml")


def clip_population(
    source: Path, destination: Path, bbox: tuple[float, float, float, float]
) -> Path:
    """Run gdal_translate over [min_lon, min_lat, max_lon, max_lat].

    gdal_translate cuts on the existing pixel grid, so the population values are copied
    without resampling. The window snaps outward to whole pixels, which puts the edge at
    most one pixel (about 90 m) outside the requested box.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    command = [
        "gdal_translate",
        "-projwin_srs",
        "EPSG:4326",
        "-projwin",
        str(min_lon),
        str(max_lat),
        str(max_lon),
        str(min_lat),
        "-co",
        "COMPRESS=LZW",
        "-co",
        "PREDICTOR=2",
        str(source),
        str(destination),
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(command, check=True)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    parser.add_argument("--config", type=Path, help="default: <root>/config/default_config.yaml")
    args = parser.parse_args(argv)

    config_path = args.config or args.root / DEFAULT_CONFIG
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw_dir = args.root / config["paths"]["data_raw_dir"]
    source = raw_dir / config["demand"]["population_source_file"]
    destination = raw_dir / config["demand"]["population_raster_file"]
    bbox = tuple(config["spatial"]["study_area_bbox"])

    if not source.exists():
        raise FileNotFoundError(f"population raster not found: {source}")

    clip_population(source, destination, bbox)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    print(f"clipped {source.name} -> {destination}")
    print(f"  bbox    {bbox} (EPSG:4326)")
    print(f"  bytes   {destination.stat().st_size}")
    print(f"  sha256  {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
