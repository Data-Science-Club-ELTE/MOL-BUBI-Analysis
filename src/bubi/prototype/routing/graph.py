"""Directed graph representation and loaders for the street network.

Conforms to Technical Design Document (Section 5 and 6.2):
- Node IDs and edge IDs ('u-v-key')
- Edge attributes: length_m, grade, osm_way_id, has_dedicated_lane, geometry
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from bubi.prototype.contracts.schemas import EdgesSchema, _normalize_records
from bubi.prototype.io.parquet import Table, read_parquet


class DiGraph:
    """Directed graph representation supporting multiple directed edges between nodes."""

    def __init__(self):
        self._adj: Dict[Any, Dict[Any, Dict[int, Dict[str, Any]]]] = {}
        self._nodes: Dict[Any, Dict[str, Any]] = {}

    def add_node(self, node: Any, **attrs: Any) -> None:
        """Add a node and optional node attributes."""
        if node not in self._nodes:
            self._nodes[node] = dict(attrs)
            self._adj[node] = {}
        else:
            self._nodes[node].update(attrs)

    def add_edge(self, u: Any, v: Any, key: int = 0, **attrs: Any) -> None:
        """Add a directed edge from u to v with specified key and attributes."""
        self.add_node(u)
        self.add_node(v)
        if v not in self._adj[u]:
            self._adj[u][v] = {}
        self._adj[u][v][key] = dict(attrs)

    def has_node(self, node: Any) -> bool:
        """Check if node exists in the graph."""
        return node in self._nodes

    def has_edge(self, u: Any, v: Any, key: Optional[int] = None) -> bool:
        """Check if directed edge u -> v exists."""
        if u not in self._adj or v not in self._adj[u]:
            return False
        if key is None:
            return len(self._adj[u][v]) > 0
        return key in self._adj[u][v]

    @property
    def nodes(self) -> List[Any]:
        """List of all nodes in the graph."""
        return list(self._nodes.keys())

    def successors(self, u: Any) -> List[Any]:
        """List of target nodes reachable directly from u."""
        if u not in self._adj:
            return []
        return list(self._adj[u].keys())

    def out_edges(self, u: Any) -> List[Tuple[Any, Any, int, Dict[str, Any]]]:
        """Return list of outgoing edges from u as (u, v, key, edge_data)."""
        if u not in self._adj:
            return []
        edges = []
        for v, key_dict in self._adj[u].items():
            for key, data in key_dict.items():
                edges.append((u, v, key, data))
        return edges

    def get_edge_data(self, u: Any, v: Any, key: int = 0) -> Optional[Dict[str, Any]]:
        """Get attributes dict for edge (u, v, key)."""
        if u in self._adj and v in self._adj[u] and key in self._adj[u][v]:
            return self._adj[u][v][key]
        return None

    def __len__(self) -> int:
        """Return number of nodes."""
        return len(self._nodes)

    def number_of_edges(self) -> int:
        """Return total number of directed edges."""
        count = 0
        for u in self._adj:
            for v in self._adj[u]:
                count += len(self._adj[u][v])
        return count

    def to_networkx(self):
        """Convert to a NetworkX MultiDiGraph if networkx is available."""
        try:
            import networkx as nx

            G = nx.MultiDiGraph()
            for node, attrs in self._nodes.items():
                G.add_node(node, **attrs)
            for u in self._adj:
                for v in self._adj[u]:
                    for key, data in self._adj[u][v].items():
                        G.add_edge(u, v, key=key, **data)
            return G
        except ImportError:
            return None


def _parse_edge_id(edge_id: str) -> Tuple[Union[int, str], Union[int, str], int]:
    """Parse 'u-v-key' into (u, v, key)."""
    parts = str(edge_id).split("-")
    if len(parts) >= 3:
        u_str, v_str, key_str = parts[0], parts[1], parts[2]
        try:
            u_val = int(u_str)
        except ValueError:
            u_val = u_str
        try:
            v_val = int(v_str)
        except ValueError:
            v_val = v_str
        try:
            key_val = int(key_str)
        except ValueError:
            key_val = 0
        return u_val, v_val, key_val
    elif len(parts) == 2:
        try:
            u_val = int(parts[0])
        except ValueError:
            u_val = parts[0]
        try:
            v_val = int(parts[1])
        except ValueError:
            v_val = parts[1]
        return u_val, v_val, 0
    else:
        raise ValueError(f"Invalid edge_id format: '{edge_id}'. Expected 'u-v-key'.")


def load_graph_from_edges(
    edges_data: Union[str, Table, Dict[str, Any], List[Dict[str, Any]], Any],
    validate: bool = True,
) -> DiGraph:
    """Load and build a traversable DiGraph from edges data.

    Parameters:
    - edges_data: Filepath to parquet file, Table object, DataFrame, dict, or list of dicts.
    - validate: Whether to validate input against EdgesSchema (default: True).

    Returns:
    - A populated, traversable DiGraph instance.
    """
    if isinstance(edges_data, str):
        # Filepath (e.g. tests/fixtures/sample_edges.parquet)
        table = read_parquet(edges_data)
        records = table.to_records()
    elif isinstance(edges_data, Table):
        records = edges_data.to_records()
    else:
        records = _normalize_records(edges_data)

    if validate:
        EdgesSchema.validate(records)

    graph = DiGraph()

    for row in records:
        # Determine u, v, key
        if "u" in row and "v" in row and row["u"] is not None and row["v"] is not None:
            u = row["u"]
            v = row["v"]
            key = int(row.get("key", 0))
        else:
            u, v, key = _parse_edge_id(row["edge_id"])

        edge_attrs = {
            "edge_id": str(row["edge_id"]),
            "osm_way_id": int(row["osm_way_id"]),
            "length_m": float(row["length_m"]),
            "grade": float(row.get("grade", 0.0)),
            "has_dedicated_lane": bool(row["has_dedicated_lane"]),
            "geometry": row.get("geometry", ""),
        }
        graph.add_edge(u, v, key=key, **edge_attrs)

    return graph
