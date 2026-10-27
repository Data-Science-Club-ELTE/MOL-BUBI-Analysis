# Module: Corridor Scoring & Gap Detection (`src/bubi/corridors`)

**Owner**: CS 3  
**Collaborators**: Data Science MSc (Scoring & continuity formulation), Geoinformatics MSc (Lane tags)

---

## 1. Objective

1. **Volume Aggregation**: Calculate route volume traversing each directed edge across all routes.
2. **Missing-Lane Filter**: Filter directed edges where `has_dedicated_lane == False` in that specific travel direction (Decision D3).
3. **Edge Scoring**:
   $$\text{score} = \text{route volume} \times \text{gap length (m)} \times \text{continuity factor}$$
   - Continuity factor rewards edges connecting to adjacent high-scoring gaps (agreed in week 4).
4. **Corridor Merging**: Group adjacent missing-lane edges traveling in the same direction into coherent corridors.
5. **Ranking**: Assign ranks per scenario.

---

## 2. Data Contracts

### Inputs
- `edges`: `tests/fixtures/sample_edges.parquet`
- `routes`: `tests/fixtures/sample_routes.parquet`

### Outputs
- `edge_scores`: `tests/fixtures/sample_edge_scores.parquet` (validated by `EdgeScoresSchema`)
- `corridors`: `tests/fixtures/sample_corridors.parquet` (validated by `CorridorsSchema`)

| Table | Core Fields | Description |
|---|---|---|
| `edge_scores` | `scenario`, `edge_id`, `volume`, `score`, `rank` | Prioritized directed road edges |
| `corridors` | `scenario`, `corridor_id`, `edge_ids`, `score`, `rank` | Merged road corridors |

### Edge route volumes (`calculate_edge_route_volumes`)

Intermediate output of step 1, one row per `(scenario, edge_id)` with volume > 0:

| Field | Type | Meaning |
|---|---|---|
| `scenario` | str | Scenario of the routes |
| `edge_id` | str | Directed edge `u-v-key` |
| `volume` | float | Sum of `trip_count` of routes traversing the edge in that direction |

Rows are sorted by scenario, then volume (highest first), then `edge_id`.
These are the first three fields of `edge_scores`; `score` and `rank` are added by `detect_gaps_and_score_edges`.

Counting rules:

1. **Direction**: `u-v-key` and `v-u-key` are different edges and are counted separately; edge IDs are never normalised.
2. **Repeated use**: a route adds its `trip_count` once to each *distinct* edge it uses. A route that passes the same directed edge twice (possible in map-matched GPS traces) still counts once, so volume is the number of trips using the edge in that direction (design doc §7.1).
3. **Scenarios** are aggregated independently.
4. **Route types**: `synthetic` and `observed` routes of one scenario are summed; filter `route_type` beforehand if only one is wanted.
5. Routes with no edges or `trip_count == 0` contribute nothing.
6. `routes.edges` may be a list, a JSON array string, or a single edge-ID string.

---

## 3. How to Develop Independently

1. Load sample edges and sample routes:
   ```python
   import geopandas as gpd
   import pandas as pd
   from bubi.contracts.schemas import CorridorsSchema, EdgeScoresSchema

   gdf_edges = gpd.read_parquet("tests/fixtures/sample_edges.parquet")
   df_routes = pd.read_parquet("tests/fixtures/sample_routes.parquet")
   ```
2. Write volume counting and gap filtering logic in `src/bubi/corridors/scoring.py`.
3. Validate outputs:
   ```python
   EdgeScoresSchema.validate(df_edge_scores)
   CorridorsSchema.validate(df_corridors)
   ```
4. Run tests:
   ```bash
   pytest tests/test_contracts.py -k "edge_scores or corridors"
   ```
