# Module: Demand Generator (`src/bubi/demand`)

**Owner**: Data Science MSc  
**Collaborators**: CS 2 (Routing Engine), CS 5 (Station Scoring & Scenarios)

---

## 1. Objective

1. **Catchment Assignment**: Assign each populated H3 cell within walking threshold (300–400m) to its nearest station (no double-counting).
2. **Gravity Model**: Estimate directed trip counts between all station pairs $(i, j)$:
   $$\text{trips}(i \to j) \propto P_i \times P_j \times f(d_{ij})$$
   where $P_i$ is catchment population and $f(d_{ij}) = e^{-\beta d_{ij}}$ (or power law).
3. **Total Demand Scaling**: Ensure total trips scale as $k \times \sum P_i$ so proposed stations naturally increase system demand (Decision D10).
4. **Handoff Interface**: Emit the trip matrix directly to the Route Engine (`TripMatrixSchema`).

---

## 2. Data Contracts

### Inputs
- `stations`: `tests/fixtures/sample_stations.parquet`
- `population`: `tests/fixtures/sample_population.parquet`

### Output: `trip_matrix` (in-memory handoff or Parquet)
Validated against `TripMatrixSchema` (sample: `tests/fixtures/sample_trip_matrix.parquet`).

| Field | Type | Description |
|---|---|---|
| `scenario` | `str` | `"baseline"`, `"lane_aware"`, or `"population_only"` |
| `start_station_id` | `str` | Origin station ID |
| `end_station_id` | `str` | Destination station ID ($i \neq j$) |
| `trip_count` | `float` | Estimated number of trips (> 0.0) |

---

## 3. How to Develop Independently

You do not need to wait for real BKK data or OSMnx networks:

1. Load sample stations and population fixtures:
   ```python
   import pandas as pd
   from bubi.contracts.schemas import TripMatrixSchema

   df_stations = pd.read_parquet("tests/fixtures/sample_stations.parquet")
   df_pop = pd.read_parquet("tests/fixtures/sample_population.parquet")
   ```
2. Implement and test your gravity decay formula in `src/bubi/demand/gravity.py`.
3. Validate output:
   ```python
   TripMatrixSchema.validate(df_result)
   ```
4. Run tests:
   ```bash
   pytest tests/test_contracts.py -k trip_matrix
   ```
