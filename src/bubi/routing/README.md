# Module: Synthetic Route Engine (`src/bubi/routing`)

**Owner**: CS 2  
**Collaborators**: Geoinformatics MSc (Street graph & DEM), Data Science MSc (Trip matrix)

---

## 1. Objective

1. Compute shortest paths between station pairs using Dijkstra on the directed OSM street graph.
2. Apply uphill grade penalty:
   $$\text{cost} = \text{length} \times (1 + \alpha \cdot \max(0, \text{grade}))$$
   - Downhill and flat edges receive zero penalty.
   - Interpolate elevation along bridges and tunnels between endpoints so river/ground level doesn't produce artificial slopes.
   - Ignore traffic and bike infrastructure (Decision D2).
3. Maintain a **shared route cache** across scenarios (only new station pairs computed).
4. Merge identical routes by summing `trip_count`.
5. Log unroutable pairs and dropped trips.

---

## 2. Data Contracts

### Inputs
- `edges`: `tests/fixtures/sample_edges.parquet`
- `trip_matrix`: `tests/fixtures/sample_trip_matrix.parquet`

### Output: `routes` table
Parquet file saved to `data/processed/routes.parquet` (tested against `tests/fixtures/sample_routes.parquet`).

| Field | Type | Description |
|---|---|---|
| `scenario` | `str` | `"baseline"`, `"lane_aware"`, or `"population_only"` |
| `start_station_id` | `str` | Origin station ID |
| `end_station_id` | `str` | Destination station ID |
| `route_type` | `str` | `"synthetic"` (or `"observed"` for real data) |
| `edges` | `str` / `list` | Ordered list of `edge_id`s traversed |
| `trip_count` | `float` | Number of trips on this route |

---

## 3. How to Develop Independently

1. Load sample edges and sample trip matrix:
   ```python
   import geopandas as gpd
   import pandas as pd
   from bubi.contracts.schemas import RoutesSchema

   gdf_edges = gpd.read_parquet("tests/fixtures/sample_edges.parquet")
   df_trips = pd.read_parquet("tests/fixtures/sample_trip_matrix.parquet")
   ```
2. Build a local NetworkX graph from `sample_edges.parquet` and test Dijkstra routing with the slope penalty.
3. Validate output against `RoutesSchema`:
   ```python
   RoutesSchema.validate(df_routes)
   ```
4. Run tests:
   ```bash
   pytest tests/test_contracts.py -k routes
   ```
