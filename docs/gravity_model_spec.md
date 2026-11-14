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
   with `d_ij` = straight-line distance in metres and `beta = 0.0002419675 /m`, the production
   default calibrated on the processed city tables for a 3,000 m target mean (see Section 7).
3. **Scale to total demand.** `T_ij = w_ij * k * sum(P) / sum(w)` so that `sum(T) = k * sum(P_i)`, k = 0.05.
   Adding a proposed station that captures previously unserved cells raises `sum(P)`, hence total demand (Decision D10).
4. **Emit** rows `(scenario, start_station_id, end_station_id, trip_count)`, `trip_count > 0`, no i == j.

## 3. Parameters (config/default_config.yaml)
| Param | Value | Meaning |
|---|---|---|
| `gravity_scaling_k` | 0.05 | trips per resident in the catchments |
| `gravity_beta` | 0.0002419675 /m | production exponential decay, calibrated on the processed city tables to a 3,000 m target mean (Section 7) |
| `walk_coverage_threshold_m` | 350 | catchment radius |

## 4. Properties (tested in `tests/test_demand.py`)
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
(baseline, 5 stations, 20 ordered pairs, total 137.75 trips, weighted mean 1,223.8 m).

## 7. Gravity Model Calibration

### Target Mean Trip Distance

The baseline demand-weighted mean straight-line trip distance is set to **3,000 m**. This is a city-scale target: it allows trips across several central neighborhoods rather than concentrating demand almost entirely between adjacent stations. It is a modeling target, not a claim about observed MOL Bubi trips; it should be revisited when an observed trip-length distribution is available.

Two beta values appear in this document:

| Name | Value | Role |
| --- | ---: | --- |
| Analytical beta | 2 / 3,000 = 0.0006666667 /m | Derivation reference on an unbounded two-dimensional plane; used by the grid test only |
| Production beta (`DEFAULT_BETA_DECAY`, `gravity_beta`) | 0.0002419675 /m | Selected value, calibrated on the processed city tables so the real network hits the 3,000 m target |

The two values differ because the analytical derivation assumes an unbounded plane with evenly spread population. Budapest's stations cover roughly 20 km by 12 km, most residents sit near central stations, and with no distance decay at all (beta = 0) the same run gives 4,261.3 m. The city network therefore needs a weaker decay than the derivation predicts; the divergence is expected, not an error in either value.

The generator normalizes the gravity weights to a total demand of k times the population assigned to station catchments and excludes same-station trips. Total trips and pair count are therefore independent of beta; only the per-pair distribution changes.

### Analytical Derivation

The previous default, $\beta = 0.0015\ \mathrm{m}^{-1}$, has an exponential distance scale of only

$$
1/\beta = 1/0.0015 \approx 667\ \mathrm{m}.
$$

That scale is too short for the intended city-scale demand model. In a two-dimensional city, the number of potential destinations in a thin ring grows approximately with its radius. With an exponential deterrence kernel, the radial distance density is therefore proportional to $r e^{-\beta r}$, whose mean is

$$
\frac{\int_0^\infty r^2 e^{-\beta r}\,dr}{\int_0^\infty r e^{-\beta r}\,dr}
= \frac{2}{\beta}.
$$

Thus a two-dimensional weighted mean is nearer $2/\beta$ than $1/\beta$. Setting that mean to the 3,000 m target gives

$$
\beta = \frac{2}{3,000\ \mathrm{m}}
= 0.0006666667\ \mathrm{m}^{-1}.
$$

This value is kept as the analytical reference and as the input to `test_infinite_plane_beta_matches_grid_target` in `tests/test_demand.py`. It is not the production default.

### City Run: Production Calibration

`data/processed/population.parquet` exists, so the generator was run on the processed city tables with `python scripts/gravity_mean_distance.py`. Only 356 of the 704 stations have residents within the 350 m walking threshold, and those stations cover 468,416 of the 1,901,537 gridded residents. The baseline matrix has 126,380 directed pairs and 23,420.8 trips, matching `data/processed/trip_matrix.parquet`.

| beta (1/m) | Weighted mean trip distance |
| ---: | ---: |
| 0.0015 (previous default) | 1,149.1 m |
| 0.0006666667 (analytical) | 1,986.3 m |
| 0.00025 | 2,972.5 m |
| **0.0002419675 (selected)** | **3,000.0 m** |

The selected value is 0.0002419675 /m. It is the value that hits the 3,000 m target on the current tables, quoted to full precision so the reported mean rounds to 3,000.0 m. It carries no meaning beyond the population and station tables it was calibrated on, so re-run the script whenever either changes.

### Validation Results

The generated trip matrix's demand-weighted mean is calculated from its `trip_count` values and straight-line station distances, using the same EPSG:23700 projection as the generator.

| Dataset | beta (1/m) | Weighted mean distance | Result |
| --- | ---: | ---: | --- |
| Synthetic 17 x 17 city grid, 1 km spacing | 0.0006666667 (analytical) | 2,813.4 m | 186.6 m below the 3,000 m target; within the test tolerance of +/-250 m |
| Synthetic 17 x 17 city grid, 1 km spacing | 0.0002419675 (production) | 5,399.9 m | Shows that the unbounded-plane derivation does not transfer to the production value |
| Committed sample fixtures | 0.0002419675 (production) | 1,223.8 m | Fixture-only diagnostic; its small and irregular extent is not expected to match the city target |
| Processed city tables: 704 stations, 8,155 population cells | 0.0002419675 (production) | 3,000.0 m | Hits the target on the real network |
| Processed city tables: 704 stations, 8,155 population cells | 0.0006666667 (analytical) | 1,986.3 m | Historical result for the previous default; misses the target by 1,013.7 m |

The grid result at the analytical beta is below the infinite-plane approximation because the finite square has fewer available destinations near its boundaries.

### Decision Record

The production default is set from the city run, beta = 0.0002419675 /m, not from the synthetic grid. Model parameters are calibrated against processed real data when it exists; the analytical beta is retained only as the derivation reference and as the grid test input. This keeps the mathematical check without constraining production.

Consequences:

- Changing `gravity_beta` or `DEFAULT_BETA_DECAY` requires regenerating `tests/fixtures/sample_trip_matrix.parquet` and `data/processed/trip_matrix.parquet`, and updating the golden mean in `tests/test_demand.py`.
- `test_config_beta_matches_calibrated_default` fails if the config value and the module constant drift apart.
- The calibration is only valid for the current population and station tables. Re-run the calibration script after either changes and update this section.
