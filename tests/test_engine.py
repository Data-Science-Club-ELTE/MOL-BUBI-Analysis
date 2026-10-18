"""Unit tests for SyntheticRouteEngine caching, merging, and reporting."""

import unittest

from bubi.routing.engine import SyntheticRouteEngine
from bubi.routing.graph import DiGraph


class TestSyntheticRouteEngine(unittest.TestCase):
    """Tests for SyntheticRouteEngine route processing and caching."""

    def setUp(self):
        self.graph = DiGraph()
        # Simple triangle network
        self.graph.add_edge(1, 2, key=0, edge_id="1-2-0", length_m=100.0, grade=0.0)
        self.graph.add_edge(2, 3, key=0, edge_id="2-3-0", length_m=150.0, grade=0.0)
        # Disconnected node 99
        self.graph.add_node(99)

    def test_route_caching(self):
        """Pairs routed once should be retrieved from cache on subsequent calls."""
        engine = SyntheticRouteEngine(graph=self.graph, alpha=10.0)
        self.assertEqual(len(engine.cache), 0)

        res1 = engine.route_pair(1, 2)
        self.assertEqual(len(engine.cache), 1)
        self.assertTrue(res1.found)

        # Second call must return the cached object
        res2 = engine.route_pair(1, 2)
        self.assertIs(res1, res2)

    def test_shared_cache_across_scenarios(self):
        """Cache can be shared across scenarios per Design Doc Section 6.4."""
        shared_cache = {}
        engine_baseline = SyntheticRouteEngine(
            graph=self.graph, scenario="baseline", shared_cache=shared_cache
        )
        engine_expansion = SyntheticRouteEngine(
            graph=self.graph, scenario="lane_aware", shared_cache=shared_cache
        )

        res1 = engine_baseline.route_pair(1, 2)
        self.assertIn((1, 2), shared_cache)

        res2 = engine_expansion.route_pair(1, 2)
        self.assertIs(res1, res2)

    def test_identical_routes_merged_by_summing_trips(self):
        """Identical routes (same pair, scenario, and edges) sum their trip_counts."""
        engine = SyntheticRouteEngine(graph=self.graph, scenario="baseline")

        trips = [
            {"start_station_id": 1, "end_station_id": 2, "trip_count": 10},
            {"start_station_id": 1, "end_station_id": 2, "trip_count": 15},
            {"start_station_id": 1, "end_station_id": 2, "trip_count": 5},
        ]

        routes, report = engine.process_trips(trips)
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0]["trip_count"], 30.0)
        self.assertEqual(report.total_pairs, 3)
        self.assertEqual(report.routed_pairs, 3)
        self.assertEqual(report.unroutable_pairs, 0)
        self.assertEqual(report.routed_trips, 30.0)

    def test_unroutable_pairs_and_dropped_trips_reported(self):
        """Unroutable pairs increment unroutable count and dropped trips without crashing."""
        engine = SyntheticRouteEngine(graph=self.graph, scenario="baseline")

        trips = [
            {"start_station_id": 1, "end_station_id": 2, "trip_count": 10},
            {"start_station_id": 1, "end_station_id": 99, "trip_count": 7},  # unreachable
        ]

        routes, report = engine.process_trips(trips)
        self.assertEqual(len(routes), 1)
        self.assertEqual(report.total_pairs, 2)
        self.assertEqual(report.routed_pairs, 1)
        self.assertEqual(report.unroutable_pairs, 1)
        self.assertEqual(report.routed_trips, 10.0)
        self.assertEqual(report.dropped_trips, 7.0)
        self.assertEqual(len(report.unroutable_details), 1)
        self.assertEqual(report.unroutable_details[0]["start_station_id"], "1")
        self.assertEqual(report.unroutable_details[0]["end_station_id"], "99")

    def test_to_routes_table(self):
        """to_routes_table returns a validated Table."""
        engine = SyntheticRouteEngine(graph=self.graph, scenario="baseline")
        trips = [{"start_station_id": 1, "end_station_id": 2, "trip_count": 4}]
        routes, _ = engine.process_trips(trips)
        table = engine.to_routes_table(routes)

        self.assertEqual(len(table), 1)
        self.assertIn("scenario", table.columns)
        self.assertIn("edges", table.columns)
        self.assertIn("trip_count", table.columns)


if __name__ == "__main__":
    unittest.main()
