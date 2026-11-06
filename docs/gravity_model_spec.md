# Gravity model specification (Task #2)

**Module:** `src/bubi/demand/gravity.py` · **Output:** `TripMatrixSchema` · **Fixture:** `tests/fixtures/sample_trip_matrix.parquet`

## 1. Purpose
No real trip data exists, so we generate *expected* station-to-station trips from population only.
This is synthetic demand: it demonstrates the pipeline, not observed cyclist behaviour.

## 2. Steps
1. **Catchments.** Each populated H3-9 cell goes to its single nearest station (centroid distance, EPSG:23700).
   Cells farther than `walk_coverage_threshold_m` (350 m) from every station are unserved and ignored.
   Station population `P_i` = sum of its assigned cells (no double counting).
2. **Raw weights.** For every ordered pair i != j:  `w_ij = P_i * P_j * exp(-beta * d_ij)`
   with `d_ij` = straight-line distance in metres, `beta = 0.0015` (mean trip length about 1/beta = 670 m).
3. **Scale to total demand.** `T_ij = w_ij * k * sum(P) / sum(w)` so that `sum(T) = k * sum(P_i)`, k = 0.05.
   Adding a proposed station that captures previously unserved cells raises `sum(P)`, hence total demand (Decision D10).
4. **Emit** rows `(scenario, start_station_id, end_station_id, trip_count)`, `trip_count > 0`, no i == j.

## 3. Parameters (config/default_config.yaml)
| Param | Value | Meaning |
|---|---|---|
| `gravity_scaling_k` | 0.05 | trips per resident in the catchments |
| `gravity_beta` | 0.0015 /m | exponential distance decay |
| `walk_coverage_threshold_m` | 350 | catchment radius |

## 4. Properties (tested in `tests/test_gravity.py`)
- Total trips = k * total catchment population.
- Symmetric matrix (T_ij = T_ji), no self-trips.
- Larger beta concentrates trips on near pairs.
- A proposed station on unserved cells increases total demand.

## 5. Known simplifications / open points
- Euclidean distance, not network distance (swap `d_ij` for routed length later).
- Deterministic expected values, so `random_seed` is currently unused.
- Station weight is population only (no POIs, capacity, or time of day).
- Scenario stations: caller passes the full station set; proposed stations use id `new:<cell_id>`.
- Power-law decay (`d^-gamma`) is listed in config but not yet implemented.

## 6. Fixture
`python scripts/generate_fixtures.py` now builds the trip-matrix fixture by calling the model
(baseline, 5 stations, 20 ordered pairs, total 137.75 trips).
