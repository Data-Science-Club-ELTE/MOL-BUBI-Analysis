#!/usr/bin/env python3
"""Run the MOL Bubi pipeline stage by stage, validating every table it writes.

Stages run in dependency order. Each stage either:
- DONE: ran, validated its output through ``bubi.contracts.io`` and wrote it (or found
  the existing file identical and left it untouched);
- EXISTING: its module is not implemented yet, but a valid output file is already on
  disk, so later stages can use it;
- BLOCKED: its module is not implemented yet (owning issue named), or an input comes
  from a blocked stage;
- FAILED: an input is missing or invalid, or the stage raised; the run stops here;
- NOT_RUN: a previous stage failed.

Outputs are written to a temporary file and renamed into place only after validation,
so a failed stage never leaves a half-written table behind.

  python scripts/run_pipeline.py                      # same as `make run-pipeline`
  python scripts/run_pipeline.py --report-json report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd
import yaml
from pandera.errors import SchemaError, SchemaErrors

from bubi.contracts.io import SCHEMA_REGISTRY, load_contract_table, save_contract_table
from bubi.corridors import calculate_edge_route_volumes
from bubi.demand import generate_synthetic_trips
from bubi.ingestion import ingest_futar_stations
from bubi.ingestion.futar_snapshot import IngestionError

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path("config/default_config.yaml")
PROCESSED = "data/processed"

DONE, EXISTING, BLOCKED, FAILED, NOT_RUN = "DONE", "EXISTING", "BLOCKED", "FAILED", "NOT_RUN"
# Errors a stage can raise on bad or missing data. Anything else is a bug and propagates.
STAGE_ERRORS = (OSError, ValueError, SchemaError, SchemaErrors, IngestionError)

Runner = Callable[[list[Path], dict], pd.DataFrame]


@dataclass(frozen=True)
class Stage:
    name: str
    inputs: tuple[str, ...]  # paths relative to the repository root
    output: str
    schema: str  # contract table name in bubi.contracts.io.SCHEMA_REGISTRY
    run: Runner | None = None
    blocked_by: str | None = None  # owning issue while the module is not implemented
    # Validate only these schema columns, for intermediate tables that hold part of a
    # contract table (edge volumes are the first three columns of edge_scores).
    columns: tuple[str, ...] | None = None


@dataclass
class StageResult:
    stage: str
    status: str
    output: str
    detail: str = ""
    changed: bool = False


def _run_stations(inputs: list[Path], config: dict) -> pd.DataFrame:
    (raw_path,) = inputs
    expected = config["stations"]["snapshot_sha256"]
    actual = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(
            f"{raw_path} has SHA-256 {actual}, but config stations.snapshot_sha256 is {expected}"
        )
    return ingest_futar_stations(raw_path=raw_path)


def _run_trips(inputs: list[Path], config: dict) -> pd.DataFrame:
    stations_path, population_path = inputs
    # Baseline only: the other scenarios' station sets wait on the scenario stage.
    return generate_synthetic_trips(
        load_contract_table("stations", stations_path),
        load_contract_table("population", population_path),
        scenario="baseline",
        k_scaling=config["demand"]["gravity_scaling_k"],
        beta_decay=config["demand"]["gravity_beta"],
        random_seed=config["project"]["random_seed"],
        walk_threshold_m=config["station_scoring"]["walk_coverage_threshold_m"],
    )


def _run_volumes(inputs: list[Path], config: dict) -> pd.DataFrame:
    (routes_path,) = inputs
    return calculate_edge_route_volumes(load_contract_table("routes", routes_path))


def build_stages(config: dict) -> list[Stage]:
    """Declare every stage in dependency order."""
    raw_dir = config["paths"]["data_raw_dir"]
    stations = f"{PROCESSED}/stations.parquet"
    population = f"{PROCESSED}/population.parquet"
    edges = f"{PROCESSED}/edges.parquet"
    trips = f"{PROCESSED}/trip_matrix.parquet"
    routes = f"{PROCESSED}/routes.parquet"
    volumes = f"{PROCESSED}/edge_volumes.parquet"
    scores = f"{PROCESSED}/edge_scores.parquet"
    # Population and edges have no declared raw input yet: the source products are still
    # open questions in docs/source_inventory.md.
    return [
        Stage(
            "stations",
            (f"{raw_dir}/{config['stations']['snapshot_file']}",),
            stations,
            "stations",
            run=_run_stations,
        ),
        Stage("population", (), population, "population", blocked_by="#23"),
        Stage("edges", (), edges, "edges", blocked_by="#15"),
        Stage(
            "candidates",
            (stations, population, edges),
            f"{PROCESSED}/station_candidates.parquet",
            "station_candidates",
            blocked_by="#39",
        ),
        Stage("trips", (stations, population), trips, "trip_matrix", run=_run_trips),
        Stage("routes", (trips, edges), routes, "routes", blocked_by="#36"),
        Stage(
            "volumes",
            (routes,),
            volumes,
            "edge_scores",
            run=_run_volumes,
            columns=("scenario", "edge_id", "volume"),
        ),
        Stage("scores", (edges, volumes), scores, "edge_scores", blocked_by="#21"),
        Stage(
            "corridors",
            (edges, scores),
            f"{PROCESSED}/corridors.parquet",
            "corridors",
            blocked_by="#37",
        ),
    ]


def run_pipeline(root: Path, config: dict) -> list[StageResult]:
    """Run every stage under ``root`` and return one result per stage."""
    stages = build_stages(config)
    producer = {stage.output: stage for stage in stages}
    unavailable: set[str] = set()  # outputs of blocked stages that are not on disk
    results: list[StageResult] = []
    failed = False

    for stage in stages:
        output = root / stage.output
        if failed:
            results.append(StageResult(stage.name, NOT_RUN, stage.output))
            continue

        if stage.run is None:
            result = _use_existing_output(stage, output)
            if result.status == BLOCKED:
                unavailable.add(stage.output)
            failed = result.status == FAILED
            results.append(result)
            continue

        blocked_inputs = [path for path in stage.inputs if path in unavailable]
        if blocked_inputs:
            upstream = ", ".join(
                _blocked_label(producer[path], producer, unavailable) for path in blocked_inputs
            )
            results.append(StageResult(stage.name, BLOCKED, stage.output, f"upstream: {upstream}"))
            unavailable.add(stage.output)
            continue

        missing = [path for path in stage.inputs if not (root / path).exists()]
        if missing:
            detail = f"stage '{stage.name}' is missing input {', '.join(missing)}"
            results.append(StageResult(stage.name, FAILED, stage.output, detail))
            failed = True
            continue

        try:
            df = _validate(stage, stage.run([root / path for path in stage.inputs], config))
            changed = _write_if_changed(stage, df, output)
        except STAGE_ERRORS as exc:
            detail = f"stage '{stage.name}' failed: {type(exc).__name__}: {exc}"
            results.append(StageResult(stage.name, FAILED, stage.output, detail))
            failed = True
            continue
        detail = f"{len(df)} rows, {'written' if changed else 'unchanged'}"
        results.append(StageResult(stage.name, DONE, stage.output, detail, changed))

    return results


def _blocked_label(stage: Stage, producer: dict[str, Stage], unavailable: set[str]) -> str:
    """Name a blocked stage and, through its blocked inputs, the issue it waits on."""
    if stage.blocked_by:
        return f"{stage.name} ({stage.blocked_by})"
    upstream = ", ".join(
        _blocked_label(producer[path], producer, unavailable)
        for path in stage.inputs
        if path in unavailable
    )
    return f"{stage.name} (via {upstream})"


def _use_existing_output(stage: Stage, output: Path) -> StageResult:
    """Handle a stage whose module is not implemented yet."""
    if not output.exists():
        detail = f"module not implemented yet, owned by {stage.blocked_by}"
        return StageResult(stage.name, BLOCKED, stage.output, detail)
    try:
        df = _validate(stage, _read(stage, output))
    except STAGE_ERRORS as exc:
        detail = f"existing {stage.output} is invalid: {type(exc).__name__}: {exc}"
        return StageResult(stage.name, FAILED, stage.output, detail)
    detail = f"module blocked by {stage.blocked_by}; using existing file ({len(df)} rows)"
    return StageResult(stage.name, EXISTING, stage.output, detail)


def _read(stage: Stage, path: Path) -> pd.DataFrame:
    return load_contract_table(stage.schema, path, validate=False)


def _validate(stage: Stage, df: pd.DataFrame) -> pd.DataFrame:
    schema = SCHEMA_REGISTRY[stage.schema]
    if stage.columns is not None:
        schema = schema.select_columns(list(stage.columns))
    return schema.validate(df)


def _write_if_changed(stage: Stage, df: pd.DataFrame, output: Path) -> bool:
    """Write ``df`` atomically unless ``output`` already holds the same table."""
    if _same_as_existing(stage, df, output):
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f".{output.name}.tmp")
    try:
        save_contract_table(df, stage.schema, tmp, validate=False)
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)
    return True


def _same_as_existing(stage: Stage, df: pd.DataFrame, output: Path) -> bool:
    if not output.exists():
        return False
    try:
        existing = _validate(stage, _read(stage, output))
    except STAGE_ERRORS:
        return False  # an invalid old file is replaced by the new, validated table
    return existing.reset_index(drop=True).equals(df.reset_index(drop=True))


def format_report(results: list[StageResult]) -> str:
    width = max(len(result.stage) for result in results)
    lines = [f"{r.stage:<{width}}  {r.status:<8}  {r.output}  {r.detail}" for r in results]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    parser.add_argument("--config", type=Path, help="default: <root>/config/default_config.yaml")
    parser.add_argument("--report-json", type=Path, help="also write the results as JSON")
    args = parser.parse_args(argv)

    config_path = args.config or args.root / DEFAULT_CONFIG
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    results = run_pipeline(args.root, config)

    print(format_report(results))
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(result) for result in results]
        args.report_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 1 if any(result.status == FAILED for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
