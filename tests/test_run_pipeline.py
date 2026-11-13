import hashlib
import importlib.util
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
import yaml
from rasterio.transform import from_origin

from bubi.contracts.io import load_contract_table
from bubi.contracts.schemas import CorridorsSchema, EdgeScoresSchema, TripMatrixSchema
from bubi.corridors import (
    calculate_edge_route_volumes,
    detect_gaps_and_score_edges,
    merge_edges_into_corridors,
)

ROOT = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
RAW_SAMPLE = FIXTURES / "futar_bicycle_rental_sample.json"
SNAPSHOT = "futar_bicycle_rental_sample.json"
RASTER = "population_sample.tif"
# Covers the sample stations in Belváros with 3 arc-second pixels of 20 people each.
RASTER_BBOX = (19.045, 47.48, 19.08, 47.515)
PIXEL_DEGREES = 1 / 1200


def _load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up while it is loading
    spec.loader.exec_module(module)
    return module


rp = _load_script("run_pipeline")
repro = _load_script("check_reproducibility")


@pytest.fixture
def config():
    cfg = yaml.safe_load((ROOT / "config" / "default_config.yaml").read_text(encoding="utf-8"))
    cfg["stations"]["snapshot_file"] = SNAPSHOT
    cfg["stations"]["snapshot_sha256"] = hashlib.sha256(RAW_SAMPLE.read_bytes()).hexdigest()
    cfg["demand"]["population_raster_file"] = RASTER
    cfg["spatial"]["study_area_bbox"] = list(RASTER_BBOX)
    return cfg


def _with_raw_snapshot(root: Path) -> None:
    (root / "data" / "raw").mkdir(parents=True, exist_ok=True)
    shutil.copy(RAW_SAMPLE, root / "data" / "raw" / SNAPSHOT)


def _with_population_raster(root: Path) -> None:
    min_lon, min_lat, max_lon, max_lat = RASTER_BBOX
    width = round((max_lon - min_lon) / PIXEL_DEGREES)
    height = round((max_lat - min_lat) / PIXEL_DEGREES)
    (root / "data" / "raw").mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        root / "data" / "raw" / RASTER,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=from_origin(min_lon, max_lat, PIXEL_DEGREES, PIXEL_DEGREES),
    ) as dst:
        dst.write(np.full((height, width), 20.0, dtype="float32"), 1)


def _with_raw_inputs(root: Path) -> None:
    _with_raw_snapshot(root)
    _with_population_raster(root)


def _place(root: Path, fixture: str, table: str) -> None:
    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES / fixture, processed / f"{table}.parquet")


def _by_stage(results):
    return {result.stage: result for result in results}


def test_stages_are_declared_in_dependency_order(config):
    stages = rp.build_stages(config)
    assert [stage.name for stage in stages] == [
        "stations",
        "population",
        "edges",
        "candidates",
        "trips",
        "routes",
        "volumes",
        "scores",
        "corridors",
    ]
    produced = set()
    for stage in stages:
        upstream = {path for path in stage.inputs if path.startswith(rp.PROCESSED)}
        assert upstream <= produced, f"{stage.name} reads a table produced later"
        assert stage.schema in rp.SCHEMA_REGISTRY
        produced.add(stage.output)


def test_missing_input_stops_the_run_and_writes_nothing(tmp_path, config):
    results = _by_stage(rp.run_pipeline(tmp_path, config))

    stations = results["stations"]
    assert stations.status == rp.FAILED
    assert "stage 'stations'" in stations.detail
    assert f"data/raw/{SNAPSHOT}" in stations.detail
    assert {r.status for name, r in results.items() if name != "stations"} == {rp.NOT_RUN}
    assert not (tmp_path / "data" / "processed").exists()


def test_invalid_output_leaves_no_half_written_table(tmp_path, config, monkeypatch):
    _with_raw_inputs(tmp_path)
    bad_trips = pd.DataFrame(
        {"scenario": ["baseline"], "start_station_id": ["a"], "end_station_id": ["b"]}
    )
    monkeypatch.setattr(rp, "generate_synthetic_trips", lambda *args, **kwargs: bad_trips)

    results = _by_stage(rp.run_pipeline(tmp_path, config))

    assert results["trips"].status == rp.FAILED
    assert "SchemaError" in results["trips"].detail
    assert results["routes"].status == rp.NOT_RUN
    processed = sorted(path.name for path in (tmp_path / "data" / "processed").iterdir())
    assert processed == ["population.parquet", "stations.parquet"]


def test_missing_population_raster_names_the_file_and_stage(tmp_path, config):
    _with_raw_snapshot(tmp_path)

    results = _by_stage(rp.run_pipeline(tmp_path, config))

    population = results["population"]
    assert population.status == rp.FAILED
    assert "stage 'population'" in population.detail
    assert f"data/raw/{RASTER}" in population.detail
    assert results["trips"].status == rp.NOT_RUN
    processed = sorted(path.name for path in (tmp_path / "data" / "processed").iterdir())
    assert processed == ["stations.parquet"]


def test_sha_mismatch_fails_the_stations_stage(tmp_path, config):
    _with_raw_snapshot(tmp_path)
    config["stations"]["snapshot_sha256"] = "0" * 64

    results = _by_stage(rp.run_pipeline(tmp_path, config))

    assert results["stations"].status == rp.FAILED
    assert "SHA-256" in results["stations"].detail


def test_blocked_stages_name_their_owning_issue(tmp_path, config):
    _with_raw_inputs(tmp_path)

    results = _by_stage(rp.run_pipeline(tmp_path, config))

    for stage in ("stations", "population", "trips"):
        assert results[stage].status == rp.DONE
    owners = {"edges": "#15", "candidates": "#39", "routes": "#15"}
    for stage, issue in owners.items():
        assert results[stage].status == rp.BLOCKED
        assert issue in results[stage].detail
    assert results["volumes"].detail == "upstream: routes (#15)"
    # Scores and corridors are implemented (#21, #37) and wait only on their inputs.
    assert results["scores"].detail == "upstream: edges (#15), volumes (via routes (#15))"
    assert results["corridors"].detail.startswith("upstream: edges (#15), scores (via ")
    assert not any(r.status == rp.FAILED for r in results.values())


def test_implemented_stages_run_and_validate_on_existing_inputs(tmp_path, config):
    _with_raw_inputs(tmp_path)
    _place(tmp_path, "sample_routes.parquet", "routes")

    results = _by_stage(rp.run_pipeline(tmp_path, config))

    assert results["routes"].status == rp.EXISTING
    for stage in ("stations", "population", "trips", "volumes"):
        assert results[stage].status == rp.DONE and results[stage].changed
    processed = tmp_path / "data" / "processed"
    trips = TripMatrixSchema.validate(pd.read_parquet(processed / "trip_matrix.parquet"))
    assert not trips.empty and set(trips["scenario"]) == {"baseline"}
    volumes = pd.read_parquet(processed / "edge_volumes.parquet")
    assert list(volumes.columns) == ["scenario", "edge_id", "volume"]
    assert results["scores"].status == rp.BLOCKED  # edges are still missing

    # A second run finds every table identical and rewrites nothing.
    rerun = _by_stage(rp.run_pipeline(tmp_path, config))
    assert not any(result.changed for result in rerun.values())


def test_scores_and_corridors_run_once_edges_and_routes_exist(tmp_path, config):
    _with_raw_inputs(tmp_path)
    _place(tmp_path, "sample_edges.parquet", "edges")
    _place(tmp_path, "sample_routes.parquet", "routes")

    results = _by_stage(rp.run_pipeline(tmp_path, config))

    for stage in ("volumes", "scores", "corridors"):
        assert results[stage].status == rp.DONE and results[stage].changed
    processed = tmp_path / "data" / "processed"
    edges = load_contract_table("edges", FIXTURES / "sample_edges.parquet")
    routes = load_contract_table("routes", FIXTURES / "sample_routes.parquet")
    expected_scores = detect_gaps_and_score_edges(edges, calculate_edge_route_volumes(routes))
    scores = EdgeScoresSchema.validate(pd.read_parquet(processed / "edge_scores.parquet"))
    pd.testing.assert_frame_equal(scores, expected_scores)
    corridors = CorridorsSchema.validate(pd.read_parquet(processed / "corridors.parquet"))
    expected_corridors = merge_edges_into_corridors(edges, expected_scores)
    assert corridors["corridor_id"].tolist() == expected_corridors["corridor_id"].tolist()
    assert [list(ids) for ids in corridors["edge_ids"]] == expected_corridors["edge_ids"].tolist()
    assert corridors["score"].tolist() == expected_corridors["score"].tolist()

    # A second run finds every table identical and rewrites nothing.
    rerun = _by_stage(rp.run_pipeline(tmp_path, config))
    assert not any(result.changed for result in rerun.values())


def test_main_exit_code_and_json_report(tmp_path, config):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    report = tmp_path / "report.json"

    assert rp.main(["--root", str(tmp_path), "--config", str(config_path)]) == 1
    _with_raw_inputs(tmp_path)
    args = ["--root", str(tmp_path), "--config", str(config_path), "--report-json", str(report)]
    assert rp.main(args) == 0
    assert '"status": "BLOCKED"' in report.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("status", "changed", "committed", "verdict"),
    [
        ("DONE", False, True, "PASS"),
        ("DONE", True, True, "FAIL"),
        ("DONE", True, False, "PASS"),
        ("EXISTING", False, True, "PASS"),
        ("BLOCKED", False, False, "BLOCKED"),
        ("FAILED", False, False, "FAIL"),
        ("NOT_RUN", False, False, "FAIL"),
    ],
)
def test_reproducibility_verdicts(status, changed, committed, verdict):
    stage = {"status": status, "changed": changed, "detail": "x", "output": "t.parquet"}
    assert repro.classify(stage, committed)[0] == verdict


def test_invalid_old_output_is_replaced(tmp_path, config):
    _with_raw_snapshot(tmp_path)
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    pd.DataFrame({"unexpected": [1]}).to_parquet(processed / "stations.parquet")

    results = _by_stage(rp.run_pipeline(tmp_path, config))

    assert results["stations"].status == rp.DONE and results["stations"].changed
    assert "station_id" in pd.read_parquet(processed / "stations.parquet").columns
