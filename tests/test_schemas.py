"""Unit tests for EdgesSchema and RoutesSchema data contract validation."""

import unittest

from bubi.prototype.contracts.schemas import EdgesSchema, RoutesSchema, SchemaError


class TestSchemas(unittest.TestCase):
    """Tests for schema validation of EdgesSchema and RoutesSchema."""

    def test_valid_edges_pass_validation(self):
        """Valid edge records should pass EdgesSchema without error."""
        valid_edges = [
            {
                "edge_id": "1-2-0",
                "osm_way_id": 100,
                "length_m": 50.0,
                "has_dedicated_lane": True,
                "geometry": "LINESTRING(0 0, 1 1)",
            }
        ]
        res = EdgesSchema.validate(valid_edges)
        self.assertEqual(res, valid_edges)

    def test_edges_missing_required_field_raises(self):
        """Missing required fields in edges must raise SchemaError."""
        invalid_edges = [
            {
                "edge_id": "1-2-0",
                # missing osm_way_id
                "length_m": 50.0,
                "has_dedicated_lane": True,
                "geometry": "LINESTRING(0 0, 1 1)",
            }
        ]
        with self.assertRaises(SchemaError):
            EdgesSchema.validate(invalid_edges)

    def test_edges_negative_length_raises(self):
        """Negative edge length must raise SchemaError."""
        invalid_edges = [
            {
                "edge_id": "1-2-0",
                "osm_way_id": 100,
                "length_m": -5.0,
                "has_dedicated_lane": True,
                "geometry": "LINESTRING(0 0, 1 1)",
            }
        ]
        with self.assertRaises(SchemaError):
            EdgesSchema.validate(invalid_edges)

    def test_edges_empty_raises(self):
        """An empty edges dataset must raise SchemaError."""
        with self.assertRaises(SchemaError):
            EdgesSchema.validate([])

    def test_valid_routes_pass_validation(self):
        """Valid route records should pass RoutesSchema without error."""
        valid_routes = [
            {
                "scenario": "baseline",
                "start_station_id": "101",
                "end_station_id": "102",
                "route_type": "synthetic",
                "edges": ["1-2-0", "2-3-0"],
                "trip_count": 12.5,
            }
        ]
        res = RoutesSchema.validate(valid_routes)
        self.assertEqual(res, valid_routes)

    def test_routes_invalid_route_type_raises(self):
        """Route types other than 'synthetic' or 'observed' must raise SchemaError."""
        invalid_routes = [
            {
                "scenario": "baseline",
                "start_station_id": "101",
                "end_station_id": "102",
                "route_type": "estimated",  # invalid
                "edges": ["1-2-0"],
                "trip_count": 5.0,
            }
        ]
        with self.assertRaises(SchemaError):
            RoutesSchema.validate(invalid_routes)

    def test_routes_negative_trip_count_raises(self):
        """Negative trip count must raise SchemaError."""
        invalid_routes = [
            {
                "scenario": "baseline",
                "start_station_id": "101",
                "end_station_id": "102",
                "route_type": "synthetic",
                "edges": ["1-2-0"],
                "trip_count": -1.0,
            }
        ]
        with self.assertRaises(SchemaError):
            RoutesSchema.validate(invalid_routes)

    def test_routes_invalid_edges_element_raises(self):
        """Edges must be a sequence of non-empty strings."""
        invalid_routes = [
            {
                "scenario": "baseline",
                "start_station_id": "101",
                "end_station_id": "102",
                "route_type": "synthetic",
                "edges": [123],  # invalid type
                "trip_count": 1.0,
            }
        ]
        with self.assertRaises(SchemaError):
            RoutesSchema.validate(invalid_routes)


if __name__ == "__main__":
    unittest.main()
