# Methodology appendix

Issue: methodology appendix · Module: `docs/` · Owner: Gulzina Karimova
Status: draft for review by the Data Science MSc and the Project Leader
State of the code described: `develop` at commit `a0c1abc` (2026-11-19)

This appendix makes the project's claims checkable. It states what was assumed, what was simplified, and what the numbers do not mean. Where the design document (`bubi-technical-design.md`) describes a mitigation that the code does not yet apply, this appendix describes the code: the planned version is named only to say it is not in force.

---

## 1. What is real and what is a demonstration

| Layer | Table | Input | Status on `develop` |
| --- | --- | --- | --- |
| Existing stations | `data/processed/stations.parquet` | BKK Futár snapshot, 2026-10-18 | **Real.** 704 fixed (`virtual`) stations |
| Population | `data/processed/population.parquet` | WorldPop 2026 constrained, 100 m | **Real input, modelled values.** 8,155 H3 res-9 cells, 1,901,537 residents |
| Street network and lanes | `edges` | OpenStreetMap via OSMnx | **Not built.** No `data/processed/edges.parquet` exists |
| Trips | `data/processed/trip_matrix.parquet` | Gravity model on real stations and population | **Synthetic.** 126,380 station pairs, 23,420.8 trips |
| Routes | `routes` | Router on the street graph | **Not produced** on real data |
| Edge scores and corridors | `edge_scores`, `corridors` | Scoring on routes and edges | **Fixtures only** |
| Proposed stations | `station_candidates` | Selector on population, stations and lanes | `population_only` can run on real inputs; `lane_aware` waits for real lanes |

### 1.1 In our own words: what the demonstration layers are

Nobody has given this project a single real MOL Bubi trip. The trips are invented by a formula that says "more people at both ends and a shorter distance between them means more trips". The routes, the volume on each street and the ranking of bike-lane corridors are all built on top of those invented trips. They show that the method works from start to finish. They do **not** show where people in Budapest actually cycle, which streets they would use, or which corridor Budapest should build first. A corridor that ranks first in this project ranks first because of the formula, not because of observed demand. If real trip or GPS data arrives, these layers are rebuilt from it; until then, every trip count, route volume, gap score and corridor rank is a demonstration (design decision D5).

Station recommendations are different in kind: they use only real inputs (stations, population and, once built, OSM lanes) and no trips. They are still limited by §3 and §4.

---

## 2. Scoring formulas, as the code computes them

### 2.1 Station candidate score

Code: `src/bubi/stations/selector.py` (`filter_candidate_cells`, `compute_lane_connectivity`, `select_proposed_stations`).

**Step 1: candidate filter.** An H3 cell $c$ is a candidate when

$$
\text{pop}(c) \ge P_{\min} \quad\text{and}\quad \min_{j \in S} \lVert x_c - x_j \rVert > d_{\text{walk}}
$$

**Step 2: lane connectivity** (lane_aware only).

$$
\text{lane}(c) = \sum_{\ell \in L^{*}} \text{length}\big(\ell \cap \text{circle}(x_c, R)\big)
$$

**Step 3: score.**

$$
\text{norm}(v) = \frac{\ln(1 + v)}{\ln\!\big(1 + \max_{c' \in C^{\text{cand}}} v_{c'}\big)}
$$

$$
\text{score}_{\text{lane\_aware}}(c) = \text{norm}(\text{pop}(c)) \times \text{norm}(\text{lane}(c))
\qquad
\text{score}_{\text{population\_only}}(c) = \text{norm}(\text{pop}(c))
$$

If the maximum is 0, every normalised value is 0.

**Step 4: greedy selection.** Sort candidates by score (high first), then population (high first), then `cell_id`. Walk down the list; take a cell if it is at least $D_{\text{sp}}$ from every cell already taken. Stop after $N$ cells or at the first cell with score 0. Taken cells get `rank` 1 to $N$; all others keep `rank = <NA>`.

| Symbol | Meaning | Value in force | Unit |
| --- | --- | --- | --- |
| $c$ | an H3 resolution-9 cell from `population` | — | — |
| $\text{pop}(c)$ | `population.population` of the cell (WorldPop 2026, area-weighted) | — | residents |
| $P_{\min}$ | population floor | 100 (`population_threshold_per_cell`) | residents per cell |
| $S$ | existing stations (`stations`) | 704 | — |
| $x_c$, $x_j$ | cell centre (`h3.cell_to_latlng`) and station point, projected to EPSG:23700 | — | metres |
| $\lVert\cdot\rVert$ | straight-line (Euclidean) distance in EPSG:23700 | — | metres |
| $d_{\text{walk}}$ | walking-coverage threshold | 350 (`walk_coverage_threshold_m`) | metres |
| $L^{*}$ | dedicated-lane segments (`has_dedicated_lane == True`, either direction, reverse duplicates removed) in a lane component that comes within $a$ of at least one station | — | — |
| $a$ | station attachment distance | 200 (code default `station_attach_m`; not in config) | metres |
| $R$ | lane reach around the cell centre | 400 (`R`) | metres |
| $C^{\text{cand}}$ | all candidate cells of the run | — | — |
| $N$ | number of proposed stations | 10 (`candidate_n`) | stations |
| $D_{\text{sp}}$ | minimum spacing between proposed stations, straight-line | 400 (`min_spacing_m`) | metres |

Lane components are formed by joining lane segments that share an endpoint after rounding to 0.1 m.

### 2.2 Bike-lane gap (edge and corridor) score

Code: `src/bubi/corridors/scoring.py` (`calculate_edge_route_volumes`, `detect_gaps_and_score_edges`, `calculate_continuity_factors`, `merge_edges_into_corridors`). Definition: design §7.1 and §15.1.

An edge $i$ is scored in scenario $s$ only if $V_i > 0$ and it has **no** dedicated lane in its own direction (D3).

$$
B_i = V_i \times L_i
\qquad
C_i = 1 + w \cdot \overline{p}_{N_i}
\qquad
S_i = B_i \times C_i
$$

$$
\overline{p}_{N_i} = \frac{1}{|N_i|} \sum_{j \in N_i} p_j \quad (\text{and } C_i = 1 \text{ if } N_i = \varnothing)
$$

$$
p_j = \begin{cases}
0 & B_j = 0 \\
1 & B_j > 0 \text{ is the only positive score among several edges} \\
\dfrac{r_j - 1}{n_+ - 1} & \text{otherwise}
\end{cases}
$$

Corridor score: $\text{Score}(K) = \sum_{i \in K} S_i$.

| Symbol | Meaning | Value / unit |
| --- | --- | --- |
| $i$ | a directed edge `u-v-key`; `u-v-key` and `v-u-key` are different edges | — |
| $V_i$ | route volume: sum of `trip_count` of routes in scenario $s$ that use edge $i$ (a route counts once even if it uses the edge twice) | trips |
| $L_i$ | gap length: the whole edge's `length_m` | metres |
| $B_i$ | base score | trip-metres |
| $p_j$ | percentile of $B_j$ among the scenario's scored gap edges | 0 to 1 |
| $r_j$ | average rank of $B_j$ among positive scores (ties share the average rank) | — |
| $n_+$ | number of positive base scores in the scenario | — |
| $N_i$ | other scored gap edges in the same scenario that end where $i$ starts or start where $i$ ends; the reverse edge of $i$ (U-turn) is excluded | — |
| $w$ | continuity weight `CONTINUITY_WEIGHT` | 0.25 |
| $C_i$ | continuity factor | 1.0 to 1.25 |
| $S_i$ | final edge score (`edge_scores.score`) | trip-metres |
| $K$ | a corridor: gap edges chained in one travel direction, staying on the same OSM way at forks and crossings | — |

**Ranks.** Edges: by $S_i$ high first, then $V_i$ high first, then `edge_id`. Corridors: by score high first, then total length long first, then the first `edge_id`. Ranks restart at 1 in every scenario. Corridor IDs are `corr_<bl|la|po>_<rank>`.

---

## 3. Straight-line versus network distance

All distances below are straight-line distances in EPSG:23700 (D15). A walking or cycling route is never shorter than the straight line, so each one is a **lower bound** on the real distance. No walking graph exists yet, so none of them has been replaced.

| Where | Number it affects | Effect of using straight-line distance |
| --- | --- | --- |
| Candidate filter, `selector.filter_candidate_cells` (350 m) | Which cells may receive a new station | Cells that are farther than 350 m on foot but within 350 m as the crow flies are wrongly treated as covered, so the candidate set is **too small** |
| Greedy spacing, `select_proposed_stations` (400 m) | Which candidates can be picked together | Two picks may be closer on foot than 400 m apart suggests only if the street network is unusual; mostly minor |
| Lane reach and station attachment, `compute_lane_connectivity` (400 m, 200 m) | `lane_connectivity`, hence the lane_aware score | Lanes are counted inside a circle, not within a 400 m ride; lanes behind a river or rail line count as reachable |
| Gravity catchments, `demand.gravity.assign_catchment_population` (350 m) | Which residents feed which station; total demand | Catchment population is **overstated**: 356 of 704 stations have residents within 350 m, covering 468,416 of 1,901,537 residents; the walking-distance figure will be lower |
| Gravity decay, $d_{ij}$ with $\beta = 0.0002419675$ m⁻¹ | Trips per station pair; the 3,000 m mean trip distance | Pairs look closer than they are by bike, so distant pairs get more trips than routed distance would give; $\beta$ was calibrated to a straight-line mean |
| Evaluation metrics M1, M2, M3, M6, M11 (`docs/evaluation_metrics.md`) | Newly served and served population, and every ratio built on them | Served population is an **upper bound**; ratios inherit the bias |
| Catchment analysis, `profiling/catchment.py` (300, 350, 400 m) | Population and area covered by existing stations | Coverage is an **upper bound** at every distance |
| Selection sensitivity, `scripts/station_selection_sensitivity.py` | `outputs/exports/station_selection_sensitivity.csv` | Inherits the candidate-filter bias |

Two further simplifications sit on top of the distance: a cell counts as covered when its **centre** is within the threshold, so the whole cell's population is counted in or out together (coarser cells make this worse); and distance is measured to the nearest station regardless of whether it has free docks.

Not affected: edge and corridor scores use `length_m` along each edge's geometry, and route volumes come from paths on the street graph, so they do not use straight-line distance.

---

## 4. Limitations (design §13.2) and the mitigation actually in force

"In force" means the code on `develop` does it now. "Not in force" means the design plans it but the code does not do it.

| # | Limitation | Mitigation in force | Status |
| --- | --- | --- | --- |
| 1 | Synthetic trips, routes and corridor rankings do not reflect real cyclists | The dashboard always shows "Synthetic demo data (D5)" with the data source, notes every table read from test data, and lists the limitations in its own tab. §1.1 of this appendix states it in words. No real corridor ranking exists to mislabel: edges are not built | In force |
| 2 | Demand is population-only; no time of day, season or land use | `demand/gravity.py` uses only population (D8). No real trip data exists to revisit it | In force (by design) |
| 3 | Demand is deterministic and uses straight-line, not routed, distance | Deterministic expected values; `random_seed` is accepted and discarded. Distance is straight-line (§3). The planned swap to routed length has not happened: no street graph is built | Partly: labelled, not replaced |
| 4 | Routing uses slope only and ignores traffic and lane preference | Path search now exists (`routing/router.py`, `route_station_pairs`), and traffic and lanes are not inputs (D2). **Slope is not in force:** `network.build_street_network` accepts `elevation_dem_path` but never reads it, so the edges table has no `grade` column and `build_graph` gives every edge grade 0. Routes on real edges would therefore be shortest-length routes. Bridges and tunnels: the code sets their grade to 0 rather than interpolating, and the network module does not yet produce `is_bridge`/`is_tunnel` | Not in force (slope); in force (no traffic/lanes) |
| 5 | Walking coverage, catchments and spacing use straight-line distance | Labelled a lower bound in code docstrings, `docs/gravity_model_spec.md`, `docs/evaluation_metrics.md` and §3 here. Not replaced: no walking graph exists | Partly: labelled, not replaced |
| 6 | Only fixed docking stations are modelled | `ingestion/stations_table.py` keeps the 704 `virtual` records only; two independent selection rules must agree (D13) | In force |
| 7 | Scenario differences partly reflect the demand model | `check_scenarios_comparable` refuses runs whose seed, N, spacing, walk distance or β differ, and `build_scenario_comparison_view` labels corridors robust or station-dependent. The runner `run_all_scenarios` still raises `NotImplementedError`, so **no scenario comparison has been produced**; both tools have run on fixtures only | Partly: guards exist, no comparison yet |
| 8 | `lane_aware` stations need fewer new corridors by construction | The planned counter-measure, reporting newly served population per km of new corridor (M6), is defined in `docs/evaluation_metrics.md` but **not implemented** in code; the dashboard says it arrives later | Not in force |
| 9 | Station scores ignore legal, land-use and construction feasibility | The selector reads only population, lanes and stations (D4); it cannot account for feasibility | In force (by design) |
| 10 | Dashboard shows fixture data and placeholder station positions | Proposed-station markers are now drawn at the H3 cell centre (`dashboard/data.py`), so the placeholder is gone. Every table is validated against its contract on load. Tables without pipeline output (edges, routes, edge scores, corridors) still come from fixtures, and the dashboard names each one | In force for positions and labelling; fixture fallback remains |

---

## 5. Claims the data cannot support

Do not make the following claims in the report, slides or dashboard text. Each is listed with the reason.

1. **"Corridor X is where Budapest needs a bike lane."** Corridor rankings come from synthetic trips (§1.1) and, at this revision, from fixture edges only.
2. **"N people cycle along this street"** or any statement about real route volumes. No real trips or routes exist.
3. **"The model predicts 23,421 trips per day."** The total is $k \times$ catchment population with $k = 0.05$ chosen, not estimated; it has no time unit and is not a ridership forecast.
4. **"Bubi trips average 3 km."** 3,000 m is the target the decay $\beta$ was tuned to, not an observation.
5. **"X% of residents live within a 350 m walk of a station."** Distances are straight-line (§3), so this is an upper bound on walking coverage; say "within 350 m straight-line".
6. **"X% of Budapest's population."** The population table covers the study bounding box (1,901,537 residents), not the city's administrative area (census 2022: 1,685,342). Name the study area as the denominator.
7. **"Routes avoid hills."** No elevation data is attached to edges (§4, row 4).
8. **"Lane-aware siting is better (or worse) than population-only."** No scenario comparison has been run, and M6 is not implemented.
9. **"The recommended stations are buildable."** Feasibility is out of scope (D4).
10. **"The ranking is stable across random seeds."** The demand model has no randomness (D16); a seed test would trivially return 100% overlap.
11. **Any time-of-day, weekday or seasonal pattern.** The model has none (D8).
12. **Anything about free-floating bikes, station capacity or dock availability.** Only fixed station locations are modelled.
13. **Precise population per cell.** WorldPop values are modelled estimates (alpha release R2025A) disaggregated from census data, not counts.

---

## 6. Parameters in force

| Parameter | Value | Source |
| --- | --- | --- |
| Random seed | 42 (unused by the deterministic model) | `config/default_config.yaml` |
| CRS for exchange / measurement | EPSG:4326 / EPSG:23700 | config |
| H3 resolution | 9 | config |
| Walking coverage $d_{\text{walk}}$ | 350 m | config, `selector.py`, `gravity.py` |
| Population floor $P_{\min}$ | 100 | config, `selector.py` |
| Proposed stations $N$ | 10 | config, `selector.py` |
| Minimum spacing $D_{\text{sp}}$ | 400 m | config, `selector.py` |
| Lane reach $R$ | 400 m | config, `selector.py` |
| Station attachment $a$ | 200 m | `selector.py` only |
| Gravity scaling $k$ | 0.05 | config, `gravity.py` |
| Gravity decay $\beta$ | 0.0002419675 m⁻¹ | config, `gravity.py` (`DEFAULT_BETA_DECAY`) |
| Uphill penalty $\alpha$ | 3.0 (no effect while grades are missing) | config, `router.py` |
| Continuity weight $w$ | 0.25 | `corridors/scoring.py` |
| Top-k for the comparison view | 10 | `docs/evaluation_metrics.md` §5 |
| Station snapshot | 2026-10-18, `futar_bicycle_rental_20261018T163442Z.json` | config |
| Population source | WorldPop 2026 constrained, `hun_pop_2026_CN_100m_R2025A_v1.tif` | config, `docs/population_source.md` |

Note: design decision D14 in `bubi-technical-design.md` still lists β = 0.0006666667 m⁻¹; the value in force is 0.0002419675 m⁻¹ (`docs/gravity_model_spec.md` §7).

---

## 7. Open points for the reviewers

- Confirm the wording of §1.1 (demonstration statement) and §5 (unsupported claims).
- §4 row 4: should the design document's §6.4 status be corrected to say that slope is not applied until the network module attaches grades?
- §4 row 8: who owns the implementation of M6 before the scenario comparison is presented?
- Update this appendix when `edges.parquet`, routes or the scenario runner land; §1 and §4 are the sections that change.

## Review

- [ ] Data Science MSc
- [ ] Project Leader
