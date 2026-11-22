"""Persist and verify the frozen network artefacts."""

import gzip
import hashlib
import shutil
from pathlib import Path
from typing import Any

import networkx as nx
import osmnx as ox
import pandas as pd

from bubi.contracts.io import save_contract_table

CHUNK = 1024 * 1024


def file_sha256(path: Path) -> str:
    """SHA-256 of a file, read in chunks so graph files do not load into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_graph(graph: nx.MultiDiGraph, path: Path) -> None:
    """Write a gzipped GraphML file. OSMnx itself always writes plain GraphML."""
    if path.suffix != ".gz":
        raise ValueError("save_graph expects a .graphml.gz path")
    path.parent.mkdir(parents=True, exist_ok=True)
    plain = path.with_name(path.name.removesuffix(".gz"))
    tmp = plain.with_name(plain.name + ".tmp")
    try:
        ox.save_graphml(graph, tmp)
        with tmp.open("rb") as source, gzip.open(path, "wb", compresslevel=6) as target:
            shutil.copyfileobj(source, target, length=CHUNK)
    finally:
        tmp.unlink(missing_ok=True)


def load_graph(path: Path) -> nx.MultiDiGraph:
    """Read a graph written by save_graph."""
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return ox.load_graphml(graphml_str=handle.read())
    return ox.load_graphml(path)


def save_edges(edges: pd.DataFrame, path: Path) -> None:
    """Validate the edges table against EdgesSchema and write GeoParquet."""
    save_contract_table(edges, "edges", path)


def graph_summary(graph: nx.MultiDiGraph, path: Path) -> dict[str, Any]:
    """The facts a reader needs to trust a frozen graph file."""
    return {
        "file": str(path),
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "crs": str(graph.graph.get("crs")),
    }
