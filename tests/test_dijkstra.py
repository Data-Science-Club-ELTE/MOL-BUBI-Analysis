"""Unit tests for Dijkstra shortest path routing algorithm and slope awareness."""

import unittest

from bubi.prototype.routing.dijkstra import dijkstra_shortest_path
from bubi.prototype.routing.graph import DiGraph


class TestDijkstraRouting(unittest.TestCase):
    """Tests for Dijkstra algorithm, slope choice/cost impact, and unreachable pairs."""

    def setUp(self):
        """Construct a controlled test graph with competing flat vs steep paths."""
        self.graph = DiGraph()

        # Path 1 (Flat, longer): 1 -> 3 -> 2
        # Length = 60 + 60 = 120m, Grade = 0.0, Cost = 120 (for any alpha)
        self.graph.add_edge(1, 3, key=0, edge_id="1-3-0", length_m=60.0, grade=0.0)
        self.graph.add_edge(3, 2, key=0, edge_id="3-2-0", length_m=60.0, grade=0.0)

        # Path 2 (Steep, shorter): 1 -> 4 -> 2
        # Length = 50 + 50 = 100m, Grade: 1->4 is +15%, 4->2 is -10% (downhill)
        # Cost (alpha=0) = 50 + 50 = 100
        # Cost (alpha=10) = 50*(1 + 10*0.15) + 50*(1 + 0) = 125 + 50 = 175
        self.graph.add_edge(1, 4, key=0, edge_id="1-4-0", length_m=50.0, grade=0.15)
        self.graph.add_edge(4, 2, key=0, edge_id="4-2-0", length_m=50.0, grade=-0.10)

        # Disconnected component for unreachable pair testing
        self.graph.add_edge(98, 99, key=0, edge_id="98-99-0", length_m=100.0, grade=0.0)

    def test_dijkstra_finds_connected_route(self):
        """Dijkstra returns a valid route between a connected pair."""
        result = dijkstra_shortest_path(self.graph, source=1, target=2, alpha=0.0)
        self.assertTrue(result.found)
        self.assertEqual(result.source, 1)
        self.assertEqual(result.target, 2)
        self.assertEqual(result.path_nodes[0], 1)
        self.assertEqual(result.path_nodes[-1], 2)
        self.assertGreater(len(result.edge_ids), 0)

    def test_slope_penalty_affects_route_cost(self):
        """Uphill path cost must strictly increase when slope penalty alpha > 0."""
        # Route specifically along the steep path 1 -> 4
        res_alpha_0 = dijkstra_shortest_path(self.graph, source=1, target=4, alpha=0.0)
        res_alpha_10 = dijkstra_shortest_path(self.graph, source=1, target=4, alpha=10.0)

        self.assertTrue(res_alpha_0.found)
        self.assertTrue(res_alpha_10.found)
        self.assertEqual(res_alpha_0.total_cost, 50.0)
        self.assertEqual(res_alpha_10.total_cost, 125.0)
        self.assertGreater(res_alpha_10.total_cost, res_alpha_0.total_cost)

    def test_slope_penalty_affects_route_choice(self):
        """Demonstrate that slope penalty flips routing preference from steep to flat path.

        Acceptance Criterion:
        'A test demonstrates that the slope penalty affects route cost or route choice'
        """
        # When alpha = 0.0 (distance only):
        # Path 2 (100m) is shorter than Path 1 (120m) -> chooses Path 2 (via node 4)
        flat_preference = dijkstra_shortest_path(self.graph, source=1, target=2, alpha=0.0)
        self.assertTrue(flat_preference.found)
        self.assertEqual(flat_preference.path_nodes, [1, 4, 2])
        self.assertEqual(flat_preference.edge_ids, ["1-4-0", "4-2-0"])
        self.assertAlmostEqual(flat_preference.total_cost, 100.0)

        # When alpha = 10.0 (steep penalty applied):
        # Path 2 cost becomes 175.0, while flat Path 1 remains 120.0
        # -> Dijkstra switches to Path 1 (via node 3) to avoid the steep hill!
        hill_avoidance = dijkstra_shortest_path(self.graph, source=1, target=2, alpha=10.0)
        self.assertTrue(hill_avoidance.found)
        self.assertEqual(hill_avoidance.path_nodes, [1, 3, 2])
        self.assertEqual(hill_avoidance.edge_ids, ["1-3-0", "3-2-0"])
        self.assertAlmostEqual(hill_avoidance.total_cost, 120.0)

        # Confirm route choice changed
        self.assertNotEqual(flat_preference.edge_ids, hill_avoidance.edge_ids)

    def test_unreachable_pair_handled_gracefully(self):
        """Routing to an unreachable node must return found=False without crashing.

        Acceptance Criterion:
        'An unreachable pair is handled without crashing, if covered by the fixture or a focused test'
        """
        result = dijkstra_shortest_path(self.graph, source=1, target=99, alpha=10.0)
        self.assertFalse(result.found)
        self.assertEqual(result.path_nodes, [])
        self.assertEqual(result.edge_ids, [])
        self.assertEqual(result.total_cost, float("inf"))

    def test_nonexistent_nodes_handled_gracefully(self):
        """Nodes not present in graph must return found=False without crashing."""
        result = dijkstra_shortest_path(self.graph, source=999, target=888)
        self.assertFalse(result.found)

    def test_same_source_and_target(self):
        """Same source and target returns found=True with zero cost."""
        result = dijkstra_shortest_path(self.graph, source=1, target=1)
        self.assertTrue(result.found)
        self.assertEqual(result.path_nodes, [1])
        self.assertEqual(result.edge_ids, [])
        self.assertEqual(result.total_cost, 0.0)


if __name__ == "__main__":
    unittest.main()
