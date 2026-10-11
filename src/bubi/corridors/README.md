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
