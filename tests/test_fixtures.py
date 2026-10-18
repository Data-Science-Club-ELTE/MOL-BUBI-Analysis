"""Acceptance tests verifying the prototype against sample fixture tables and contracts.

Acceptance Criteria:
- The prototype loads the sample edge fixture and builds a traversable graph
- Dijkstra returns a route between a connected fixture pair
- Edge costs are calculated using compute_edge_weight
- A test demonstrates that the slope penalty affects route cost or route choice
- An unreachable pair is handled without crashing, if covered by the fixture or a focused test
"""

import os
import unittest

from bubi.contracts.schemas import EdgesSchema, RoutesSchema
from bubi.io.parquet import read_parquet
from bubi.routing.dijkstra import dijkstra_shortest_path
from bubi.routing.engine import SyntheticRouteEngine
from bubi.routing.graph import load_graph_from_edges


class TestFixtureAcceptance(unittest.TestCase):
    """End-to-end acceptance tests on the prototype routing edge fixture."""

    @classmethod
    def setUpClass(cls):
        fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        cls.parquet_path = os.path.join(fixtures_dir, "sample_routing_edges.parquet")

    def test_fixture_file_exists(self):
        """Fixture tests/fixtures/sample_edges.parquet must exist."""
        self.assertTrue(
            os.path.exists(self.parquet_path),
            f"Expected routing fixture file at {self.parquet_path}",
        )

    def test_fixture_conforms_to_edges_schema(self):
        """Sample edges fixture must pass EdgesSchema validation."""
        table = read_parquet(self.parquet_path)
        records = table.to_records()
        self.assertGreater(len(records), 0)

        # Validate against EdgesSchema
        validated = EdgesSchema.validate(records)
        self.assertEqual(len(validated), len(records))

        # Check required schema columns are present
        first_row = records[0]
        self.assertIn("edge_id", first_row)
        self.assertIn("osm_way_id", first_row)
        self.assertIn("length_m", first_row)
        self.assertIn("has_dedicated_lane", first_row)
        self.assertIn("geometry", first_row)

    def test_load_graph_builds_traversable_graph(self):
        """Loading sample edges builds a populated, traversable DiGraph."""
        graph = load_graph_from_edges(self.parquet_path, validate=True)
        self.assertGreater(len(graph.nodes), 0)
        self.assertGreater(graph.number_of_edges(), 0)

        # Nodes from fixture (1, 2, 3, 4, 98, 99)
        self.assertTrue(graph.has_node(1))
        self.assertTrue(graph.has_node(2))
        self.assertTrue(graph.has_node(99))

    def test_dijkstra_routes_connected_fixture_pair(self):
        """Dijkstra returns a valid route between connected fixture pair (1 -> 2)."""
        graph = load_graph_from_edges(self.parquet_path)
        result = dijkstra_shortest_path(graph, source=1, target=2, alpha=10.0)

        self.assertTrue(result.found)
        self.assertEqual(result.source, 1)
        self.assertEqual(result.target, 2)
        self.assertEqual(result.path_nodes, [1, 3, 2])
        self.assertEqual(result.edge_ids, ["1-3-0", "3-2-0"])
        self.assertAlmostEqual(result.total_cost, 120.0)
        self.assertAlmostEqual(result.total_length_m, 120.0)

    def test_slope_penalty_affects_route_choice_on_fixture(self):
        """Demonstrate slope penalty flips route choice on the fixture graph."""
        graph = load_graph_from_edges(self.parquet_path)

        # alpha=0: selects shorter steep path via node 4
        res_flat = dijkstra_shortest_path(graph, source=1, target=2, alpha=0.0)
        self.assertTrue(res_flat.found)
        self.assertEqual(res_flat.path_nodes, [1, 4, 2])
        self.assertEqual(res_flat.edge_ids, ["1-4-0", "4-2-0"])
        self.assertAlmostEqual(res_flat.total_cost, 100.0)

        # alpha=10: selects flat path via node 3
        res_slope = dijkstra_shortest_path(graph, source=1, target=2, alpha=10.0)
        self.assertTrue(res_slope.found)
        self.assertEqual(res_slope.path_nodes, [1, 3, 2])
        self.assertEqual(res_slope.edge_ids, ["1-3-0", "3-2-0"])
        self.assertAlmostEqual(res_slope.total_cost, 120.0)

        self.assertNotEqual(res_flat.edge_ids, res_slope.edge_ids)

    def test_unreachable_fixture_pair_handled_without_crash(self):
        """Unreachable pair in the fixture (1 -> 99) is handled without crashing."""
        graph = load_graph_from_edges(self.parquet_path)
        result = dijkstra_shortest_path(graph, source=1, target=99, alpha=10.0)

        self.assertFalse(result.found)
        self.assertEqual(result.path_nodes, [])
        self.assertEqual(result.edge_ids, [])
        self.assertEqual(result.total_cost, float("inf"))

    def test_prototype_emits_routes_conforming_to_routes_schema(self):
        """Prototype SyntheticRouteEngine emits route table conforming to RoutesSchema."""
        graph = load_graph_from_edges(self.parquet_path)
        engine = SyntheticRouteEngine(graph=graph, alpha=10.0, scenario="prototype")

        trips = [
            {"start_station_id": 1, "end_station_id": 2, "trip_count": 5},
            {"start_station_id": 1, "end_station_id": 99, "trip_count": 2},  # unreachable
        ]

        route_records, report = engine.process_trips(trips)

        # Unreachable pair reported without crashing
        self.assertEqual(report.total_pairs, 2)
        self.assertEqual(report.routed_pairs, 1)
        self.assertEqual(report.unroutable_pairs, 1)
        self.assertEqual(report.dropped_trips, 2.0)

        # Routes table conforms to RoutesSchema
        self.assertEqual(len(route_records), 1)
        RoutesSchema.validate(route_records)

        r = route_records[0]
        self.assertEqual(r["scenario"], "prototype")
        self.assertEqual(r["start_station_id"], "1")
        self.assertEqual(r["end_station_id"], "2")
        self.assertEqual(r["route_type"], "synthetic")
        self.assertEqual(r["edges"], ["1-3-0", "3-2-0"])
        self.assertEqual(r["trip_count"], 5.0)


if __name__ == "__main__":
    unittest.main()
