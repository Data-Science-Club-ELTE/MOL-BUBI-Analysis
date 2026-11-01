"""Smoke tests checking module interfaces and isolation."""

from pathlib import Path

import pytest

from bubi.contracts.schemas import StationsSchema
from bubi.ingestion import ingest_futar_stations
from bubi.network import build_street_network
from bubi.profiling import profile_dataset
from bubi.routing import compute_edge_weight
from bubi.scenarios import run_all_scenarios


def test_routing_edge_weight():
    # Downhill / flat should have zero penalty
    cost_flat = compute_edge_weight(length_m=100.0, grade=0.0, alpha=3.0)
    assert cost_flat == 100.0

    cost_downhill = compute_edge_weight(length_m=100.0, grade=-0.05, alpha=3.0)
    assert cost_downhill == 100.0

    # Uphill should increase cost
    cost_uphill = compute_edge_weight(length_m=100.0, grade=0.05, alpha=3.0)
    assert cost_uphill == 100.0 * (1.0 + 3.0 * 0.05)


def test_profiling_stub(sample_stations):
    summary = profile_dataset(sample_stations, "stations")
    assert summary["rows"] == len(sample_stations)
    assert "station_id" in summary["columns"]


def test_ingestion_interface_returns_stations_table(fixtures_dir: Path):
    df = ingest_futar_stations(raw_path=fixtures_dir / "futar_bicycle_rental_sample.json")
    StationsSchema.validate(df)


def test_module_stubs_raise_not_implemented():
    with pytest.raises(NotImplementedError):
        build_street_network((19.0, 47.4, 19.1, 47.5))

    with pytest.raises(NotImplementedError):
        run_all_scenarios({})
