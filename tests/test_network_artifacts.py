"""Round-trip tests for the frozen network artefacts."""

import hashlib
from pathlib import Path

import pytest

from bubi.contracts.io import load_contract_table
from bubi.network.artifacts import (
    file_sha256,
    graph_summary,
    load_graph,
    save_edges,
    save_graph,
)
from bubi.network.graph import load_osm_graph, postprocess_graph

FIXTURE = Path(__file__).parent / "fixtures" / "lane_tags.osm"


@pytest.fixture(scope="module")
def graph_and_edges():
    graph = load_osm_graph(FIXTURE)
    _, edges = postprocess_graph(graph)
    return graph, edges


def test_graph_roundtrip(tmp_path, graph_and_edges):
    graph, _ = graph_and_edges
    path = tmp_path / "graph.graphml.gz"
    save_graph(graph, path)

    loaded = load_graph(path)

    assert loaded.number_of_nodes() == graph.number_of_nodes()
    assert loaded.number_of_edges() == graph.number_of_edges()
    assert loaded.graph["crs"] == graph.graph["crs"]


def test_save_graph_requires_gz(tmp_path, graph_and_edges):
    graph, _ = graph_and_edges
    with pytest.raises(ValueError, match="graphml.gz"):
        save_graph(graph, tmp_path / "graph.graphml")


def test_edges_roundtrip(tmp_path, graph_and_edges):
    _, edges = graph_and_edges
    path = tmp_path / "edges.parquet"
    save_edges(edges, path)

    loaded = load_contract_table("edges", path)

    assert len(loaded) == len(edges)
    assert set(loaded["edge_id"]) == set(edges["edge_id"])


def test_file_sha256_matches_hashlib(tmp_path):
    path = tmp_path / "value.bin"
    path.write_bytes(b"mol bubi")
    assert file_sha256(path) == hashlib.sha256(b"mol bubi").hexdigest()


def test_graph_summary_reports_file_and_counts(tmp_path, graph_and_edges):
    graph, _ = graph_and_edges
    path = tmp_path / "graph.graphml.gz"
    save_graph(graph, path)

    summary = graph_summary(graph, path)

    assert summary["sha256"] == file_sha256(path)
    assert summary["bytes"] == path.stat().st_size
    assert summary["nodes"] == graph.number_of_nodes()
    assert summary["edges"] == graph.number_of_edges()
