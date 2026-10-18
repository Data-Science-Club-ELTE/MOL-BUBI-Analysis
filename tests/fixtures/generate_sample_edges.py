"""Generate the sample edge fixtures for MOL Bubi routing prototype."""

from __future__ import annotations

import json
import os
import sys

# Ensure root directory is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from bubi.contracts.schemas import EdgesSchema
from bubi.io.parquet import write_parquet


def generate_fixtures() -> None:
    fixtures_dir = os.path.abspath(os.path.dirname(__file__))
    parquet_path = os.path.join(fixtures_dir, "sample_routing_edges.parquet")
    json_path = os.path.join(fixtures_dir, "sample_edges.json")

    edges = [
        # Path 1: Longer flat path between 1 and 2 (length = 120m, grade = 0.0)
        {
            "edge_id": "1-3-0",
            "u": 1,
            "v": 3,
            "key": 0,
            "osm_way_id": 101,
            "length_m": 60.0,
            "grade": 0.0,
            "has_dedicated_lane": True,
            "geometry": "LINESTRING(19.040 47.497, 19.045 47.498)",
        },
        {
            "edge_id": "3-2-0",
            "u": 3,
            "v": 2,
            "key": 0,
            "osm_way_id": 102,
            "length_m": 60.0,
            "grade": 0.0,
            "has_dedicated_lane": True,
            "geometry": "LINESTRING(19.045 47.498, 19.050 47.499)",
        },
        # Path 2: Shorter steep path between 1 and 2 (length = 100m, uphill + downhill)
        {
            "edge_id": "1-4-0",
            "u": 1,
            "v": 4,
            "key": 0,
            "osm_way_id": 201,
            "length_m": 50.0,
            "grade": 0.15,  # +15% uphill
            "has_dedicated_lane": False,
            "geometry": "LINESTRING(19.040 47.497, 19.044 47.495)",
        },
        {
            "edge_id": "4-2-0",
            "u": 4,
            "v": 2,
            "key": 0,
            "osm_way_id": 202,
            "length_m": 50.0,
            "grade": -0.10,  # -10% downhill
            "has_dedicated_lane": False,
            "geometry": "LINESTRING(19.044 47.495, 19.050 47.499)",
        },
        # Reverse directions for round-trip traversal
        {
            "edge_id": "2-3-0",
            "u": 2,
            "v": 3,
            "key": 0,
            "osm_way_id": 102,
            "length_m": 60.0,
            "grade": 0.0,
            "has_dedicated_lane": True,
            "geometry": "LINESTRING(19.050 47.499, 19.045 47.498)",
        },
        {
            "edge_id": "3-1-0",
            "u": 3,
            "v": 1,
            "key": 0,
            "osm_way_id": 101,
            "length_m": 60.0,
            "grade": 0.0,
            "has_dedicated_lane": True,
            "geometry": "LINESTRING(19.045 47.498, 19.040 47.497)",
        },
        {
            "edge_id": "2-4-0",
            "u": 2,
            "v": 4,
            "key": 0,
            "osm_way_id": 202,
            "length_m": 50.0,
            "grade": 0.10,  # uphill when returning
            "has_dedicated_lane": False,
            "geometry": "LINESTRING(19.050 47.499, 19.044 47.495)",
        },
        {
            "edge_id": "4-1-0",
            "u": 4,
            "v": 1,
            "key": 0,
            "osm_way_id": 201,
            "length_m": 50.0,
            "grade": -0.15,  # downhill when returning
            "has_dedicated_lane": False,
            "geometry": "LINESTRING(19.044 47.495, 19.040 47.497)",
        },
        # Disconnected component to test unreachable pairs
        {
            "edge_id": "98-99-0",
            "u": 98,
            "v": 99,
            "key": 0,
            "osm_way_id": 901,
            "length_m": 100.0,
            "grade": 0.0,
            "has_dedicated_lane": False,
            "geometry": "LINESTRING(19.100 47.500, 19.105 47.500)",
        },
    ]

    # Validate against EdgesSchema
    EdgesSchema.validate(edges)

    # Save to Parquet
    write_parquet(parquet_path, edges)
    print(f"Generated fixture: {parquet_path}")

    # Also save to JSON for transparent inspection
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(edges, f, indent=2)
    print(f"Generated fixture: {json_path}")


if __name__ == "__main__":
    generate_fixtures()
