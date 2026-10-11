# Module: Station Scoring & Selection (`src/bubi/stations`)

**Owner**: CS 5  
**Collaborators**: Data Science MSc (Product scoring & connectivity metric), Geoinformatics MSc (Walking network & CRS)

---

## 1. Objective

1. **Walking Coverage Filter**: Exclude H3 cells within walking distance (300–400m, default 350m) of existing Futár stations.
2. **Population Filter**: Exclude cells below minimum population threshold.
3. **Continuous Lane Connectivity**: Measure existing bike lane length within reach and connectivity back to existing stations.
4. **Product Scoring**:
   - `lane_aware`: $\text{score} = \text{norm}(\text{population}) \times \text{norm}(\text{lane connectivity})$
   - `population_only`: $\text{score} = \text{norm}(\text{population})$
5. **Greedy Spatial Selection**: Select top $N$ cells iteratively, excluding neighbors within minimum spacing (e.g. 400m).
6. Emit selected cells as proposed stations formatted as `new:<cell_id>`.

---

## 2. Data Contracts

### Inputs
- `stations`: `tests/fixtures/sample_stations.parquet`
- `population`: `tests/fixtures/sample_population.parquet`
- `edges`: `tests/fixtures/sample_edges.parquet`

### Output: `station_candidates` table
Parquet file saved to `data/processed/station_candidates.parquet` (tested against `tests/fixtures/sample_station_candidates.parquet`).

| Field | Type | Description |
|---|---|---|
| `scenario` | `str` | `"lane_aware"` or `"population_only"` |
| `cell_id` | `str` | H3 resolution-9 hexagon index |
| `population` | `float` | Population in candidate cell |
| `lane_connectivity` | `float` (nullable)| Continuous connectivity measure (null for `population_only`) |
| `score` | `float` | Combined score |
| `rank` | `int` (nullable) | Selection rank 1..N (null if unselected) |

---

## 3. How to Develop Independently

1. Load fixtures:
   ```python
   import pandas as pd
   from bubi.contracts.schemas import StationCandidatesSchema

   df_stations = pd.read_parquet("tests/fixtures/sample_stations.parquet")
   df_pop = pd.read_parquet("tests/fixtures/sample_population.parquet")
   ```
2. Implement cell filtering and greedy spacing in `src/bubi/stations/selector.py`.
3. Validate output:
   ```python
   StationCandidatesSchema.validate(df_candidates)
   ```
4. Run tests:
   ```bash
   pytest tests/test_contracts.py -k station_candidates
   ```
