"""Unit tests for compute_edge_weight function and slope penalty logic."""

import unittest

from bubi.routing.cost import compute_edge_weight


class TestComputeEdgeWeight(unittest.TestCase):
    """Tests for edge weight calculation under varying slopes and alpha."""

    def test_flat_edge_no_penalty(self):
        """Flat edges (grade = 0) must incur zero penalty; cost equals length."""
        cost = compute_edge_weight(length_m=100.0, grade=0.0, alpha=10.0)
        self.assertAlmostEqual(cost, 100.0)

    def test_downhill_edge_no_penalty(self):
        """Downhill edges (grade < 0) must incur zero penalty per Design Decision D2."""
        cost = compute_edge_weight(length_m=100.0, grade=-0.08, alpha=10.0)
        self.assertAlmostEqual(cost, 100.0)

    def test_uphill_edge_with_slope_penalty(self):
        """Uphill edges (grade > 0) must apply penalty cost = length * (1 + alpha * grade)."""
        # 100m at +5% slope with alpha=10.0: cost = 100 * (1 + 10 * 0.05) = 150.0
        cost = compute_edge_weight(length_m=100.0, grade=0.05, alpha=10.0)
        self.assertAlmostEqual(cost, 150.0)

    def test_slope_penalty_tunable_with_alpha(self):
        """Higher alpha values should proportionally increase the uphill edge cost."""
        length = 100.0
        grade = 0.10  # 10% uphill

        cost_alpha_0 = compute_edge_weight(length, grade, alpha=0.0)
        cost_alpha_5 = compute_edge_weight(length, grade, alpha=5.0)
        cost_alpha_10 = compute_edge_weight(length, grade, alpha=10.0)

        self.assertAlmostEqual(cost_alpha_0, 100.0)
        self.assertAlmostEqual(cost_alpha_5, 150.0)
        self.assertAlmostEqual(cost_alpha_10, 200.0)
        self.assertGreater(cost_alpha_10, cost_alpha_5)
        self.assertGreater(cost_alpha_5, cost_alpha_0)

    def test_negative_length_raises_value_error(self):
        """Negative edge length is invalid and must raise ValueError."""
        with self.assertRaises(ValueError):
            compute_edge_weight(length_m=-10.0, grade=0.0)

    def test_negative_alpha_raises_value_error(self):
        """Negative alpha is invalid and must raise ValueError."""
        with self.assertRaises(ValueError):
            compute_edge_weight(length_m=100.0, grade=0.05, alpha=-2.0)

    def test_networkx_callback_convention(self):
        """Edge data dictionary convention compute_edge_weight(u, v, data) must work."""
        edge_data = {"length_m": 80.0, "grade": 0.05, "alpha": 10.0}
        cost = compute_edge_weight("u", "v", edge_data)
        self.assertAlmostEqual(cost, 80.0 * (1.0 + 10.0 * 0.05))


if __name__ == "__main__":
    unittest.main()
