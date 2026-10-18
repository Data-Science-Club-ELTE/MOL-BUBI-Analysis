"""Tests for reading standard Parquet datasets through the project I/O layer."""

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from bubi.contracts.schemas import EdgesSchema
from bubi.io.parquet import read_parquet
from bubi.routing.dijkstra import dijkstra_shortest_path
from bubi.routing.graph import load_graph_from_edges


class TestParquetSamples(unittest.TestCase):
    def _write_parquet(self, records):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "sample.parquet"
        pq.write_table(pa.Table.from_pylist(records), path)
        return str(path)

    def test_reads_edge_scores_table(self):
        records = [
            {
                "scenario": "baseline",
                "edge_id": "n1-n2-0",
                "volume": 210.0,
                "score": 1512.0,
                "rank": 1,
            }
        ]
        table = read_parquet(self._write_parquet(records))

        self.assertEqual(
            table.columns,
            ["scenario", "edge_id", "volume", "score", "rank"],
        )
        self.assertEqual(table.to_records(), records)

    def test_reads_and_routes_edges_with_binary_geometry(self):
        geometry = b"\x01\x02\x00\x00\x00"
        records = [
            {
                "edge_id": "n1-n2-0",
                "osm_way_id": 1001,
                "length_m": 450.0,
                "has_dedicated_lane": True,
                "geometry": geometry,
            },
            {
                "edge_id": "n2-n1-0",
                "osm_way_id": 1001,
                "length_m": 450.0,
                "has_dedicated_lane": False,
                "geometry": geometry,
            },
        ]
        path = self._write_parquet(records)
        table = read_parquet(path)
        edge_records = table.to_records()

        EdgesSchema.validate(edge_records)
        graph = load_graph_from_edges(path)
        result = dijkstra_shortest_path(graph, "n1", "n2")

        self.assertTrue(result.found)
        self.assertEqual(result.edge_ids, ["n1-n2-0"])
        self.assertEqual(
            graph.get_edge_data("n1", "n2")["geometry"],
            geometry,
        )


if __name__ == "__main__":
    unittest.main()
