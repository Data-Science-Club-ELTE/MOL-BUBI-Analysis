#!/usr/bin/env python3
"""Build the frozen Budapest bike and walk graphs from a Geofabrik extract.

The raw PBF stays out of git. This script clips it to the study bbox, keeps
only ways carrying a highway tag, builds both graphs, and writes the edges
table, the two gzipped GraphML files and a metadata sidecar.

    .venv/bin/python scripts/build_network.py --pbf data/raw/hungary-261121.osm.pbf

Output paths come from config/default_config.yaml (network.bike_graph_file,
network.walk_graph_file, network.network_metadata_file) plus
data/processed/edges.parquet.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import osmnx as ox
import yaml

from bubi.network.artifacts import file_sha256, graph_summary, save_edges, save_graph
from bubi.network.graph import build_street_network, build_walk_network

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "config" / "default_config.yaml"
TIMESTAMP = re.compile(r"timestamp=(\d{4}-\d{2}-\d{2})T")


def _run_osmium(args: list[str], *, capture: bool = False) -> str:
    try:
        result = subprocess.run(["osmium", *args], check=True, capture_output=capture, text=True)
    except FileNotFoundError as exc:
        raise SystemExit("osmium is not installed; install osmium-tool first") from exc
    return result.stdout if capture else ""


def _extract_date(pbf: Path) -> str:
    match = TIMESTAMP.search(_run_osmium(["fileinfo", "-e", str(pbf)], capture=True))
    if match is None:
        raise SystemExit(f"no timestamp in the header of {pbf}")
    return match.group(1)


def _highway_xml(pbf: Path, bbox: tuple[float, ...], work_dir: Path, rebuild: bool) -> Path:
    """Clip the PBF to the bbox and keep only ways with a highway tag."""
    date_tag = pbf.name.split(".")[0].rsplit("-", 1)[-1]
    target = work_dir / f"budapest-{date_tag}-highways.osm"
    if target.exists() and not rebuild and target.stat().st_mtime >= pbf.stat().st_mtime:
        return target

    full = work_dir / f"budapest-{date_tag}.osm"
    bbox_arg = ",".join(str(value) for value in bbox)
    _run_osmium(
        [
            "extract",
            "--bbox",
            bbox_arg,
            "--strategy",
            "complete_ways",
            "--set-bounds",
            "--overwrite",
            "-f",
            "osm",
            "-o",
            str(full),
            str(pbf),
        ]
    )
    try:
        _run_osmium(
            ["tags-filter", "--overwrite", "-f", "osm", "-o", str(target), str(full), "w/highway"]
        )
    finally:
        full.unlink(missing_ok=True)
    return target


def _bbox(value: str) -> tuple[float, float, float, float]:
    try:
        min_lon, min_lat, max_lon, max_lat = (float(part) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("bbox needs min_lon,min_lat,max_lon,max_lat") from exc
    return min_lon, min_lat, max_lon, max_lat


def _repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def _summary(graph, path: Path) -> dict:
    """Graph facts with a repository-relative file path."""
    summary = graph_summary(graph, path)
    summary["file"] = str(path.relative_to(REPO_ROOT))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, required=True, help="Geofabrik .osm.pbf extract")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--bbox", type=_bbox, help="min_lon,min_lat,max_lon,max_lat")
    parser.add_argument("--rebuild", action="store_true", help="re-clip even if cached")
    args = parser.parse_args(argv)

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    network = config["network"]
    bbox = args.bbox or tuple(config["spatial"]["study_area_bbox"])
    work_dir = _repo_path(config["paths"]["data_raw_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)

    pbf = args.pbf.resolve()
    if not pbf.exists():
        raise SystemExit(f"PBF not found: {pbf}")

    extract_date = _extract_date(pbf)
    configured_date = network.get("osm_extract_date")
    if configured_date and configured_date != extract_date:
        print(f"warning: config says {configured_date}, PBF header says {extract_date}")
    highways = _highway_xml(pbf, bbox, work_dir, args.rebuild)
    print(f"extract {extract_date}, source {highways.name}")

    bike, edges = build_street_network(bbox, source_path=highways)
    print(f"bike: {bike.number_of_nodes():,} nodes, {len(edges):,} directed edges")

    processed = _repo_path(config["paths"]["data_processed_dir"])
    edges_path = processed / "edges.parquet"
    save_edges(edges, edges_path)
    print(f"wrote {edges_path.relative_to(REPO_ROOT)}")

    bike_path = _repo_path(network["bike_graph_file"])
    save_graph(bike, bike_path)
    print(f"wrote {bike_path.relative_to(REPO_ROOT)}")

    walk = build_walk_network(bbox, source_path=highways)
    walk_path = _repo_path(network["walk_graph_file"])
    save_graph(walk, walk_path)
    print(f"walk: {walk.number_of_nodes():,} nodes, {walk.number_of_edges():,} edges")
    print(f"wrote {walk_path.relative_to(REPO_ROOT)}")

    metadata = {
        "frozen_graph_version": network["frozen_graph_version"],
        "osm_extract_date": extract_date,
        "osmnx_version": ox.__version__,
        "bbox": list(bbox),
        "pbf": {"file": pbf.name, "sha256": file_sha256(pbf)},
        "networks": {
            "bike": _summary(bike, bike_path),
            "walk": _summary(walk, walk_path),
        },
        "edges": {
            "file": str(edges_path.relative_to(REPO_ROOT)),
            "rows": len(edges),
            "dedicated_lane_share": round(float(edges["has_dedicated_lane"].mean()), 4),
            "sha256": file_sha256(edges_path),
        },
    }
    metadata_path = _repo_path(network["network_metadata_file"])
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {metadata_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
