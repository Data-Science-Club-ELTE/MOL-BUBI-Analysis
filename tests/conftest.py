"""Shared pytest fixtures for MOL Bubi recommender tests."""

import socket
from pathlib import Path

import pytest

from bubi.contracts.io import load_contract_table

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def sample_stations(fixtures_dir: Path):
    return load_contract_table("stations", fixtures_dir / "sample_stations.parquet")


@pytest.fixture
def sample_population(fixtures_dir: Path):
    return load_contract_table("population", fixtures_dir / "sample_population.parquet")


@pytest.fixture
def sample_edges(fixtures_dir: Path):
    return load_contract_table("edges", fixtures_dir / "sample_edges.parquet")


@pytest.fixture
def sample_candidates(fixtures_dir: Path):
    return load_contract_table(
        "station_candidates", fixtures_dir / "sample_station_candidates.parquet"
    )


@pytest.fixture
def sample_routes(fixtures_dir: Path):
    return load_contract_table("routes", fixtures_dir / "sample_routes.parquet")


@pytest.fixture
def sample_edge_scores(fixtures_dir: Path):
    return load_contract_table("edge_scores", fixtures_dir / "sample_edge_scores.parquet")


@pytest.fixture
def sample_corridors(fixtures_dir: Path):
    return load_contract_table("corridors", fixtures_dir / "sample_corridors.parquet")


@pytest.fixture
def sample_trip_matrix(fixtures_dir: Path):
    return load_contract_table("trip_matrix", fixtures_dir / "sample_trip_matrix.parquet")


@pytest.fixture
def no_network(monkeypatch):
    """Fail any test that opens a network connection, so CI never waits on a download."""

    def refuse(*args, **kwargs):
        raise RuntimeError("this test must run offline but tried to open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
