# Evaluation Metrics Specification

Issue: #18 · Module: `src/bubi/profiling` / `src/bubi/scenarios` · Owner: Aizirek Muradylova (BA / Data Analysis)
Version: 1.0 (Week 2) · Status: Proposal for Data Science and Dashboard implementation

This document specifies the evaluation metrics used to judge and compare the three project
scenarios (`baseline`, `lane_aware`, `population_only`). It turns the week-1 draft metrics
into exact mathematical definitions using the frozen data contract (`src/bubi/contracts/schemas.py`).

All measurements, distances, and spatial buffers use the Hungarian National Grid coordinate
system EPSG:23700 per design decision D14.

---

## 1. Scenario Definitions and Notation

The system models three scenarios:
- `baseline`: existing fixed docking stations from the Futár snapshot (704 stations).
- `lane_aware`: existing stations plus N = 10 proposed stations scored by population × lane connectivity.
- `population_only`: existing stations plus N = 10 proposed stations scored by population only.

Notation used in formulas:
- $S_{\text{existing}}$: set of existing station IDs from `stations.station_id`.
- $S_{\text{proposed}}(s)$: set of proposed station cell IDs for scenario $s$, where $s \in \{\text{lane\_aware}, \text{population\_only}\}$, selected from `station_candidates` where `scenario == s` and `rank` is not null.
- $C$: set of H3 resolution-9 cells in `population`.
- $\text{dist}(a, b)$: straight-line Euclidean distance in EPSG:23700 between spatial centroids (design decision D15).
- $d_{\text{walk}}$: walking-coverage threshold distance, default 350.0 m (`config/default_config.yaml`: `station_scoring.walk_coverage_threshold_m`).
- $k$: top-corridor cut-off rank (default proposal: $k = 10$).

---

## 2. Core Metrics Specification

### Metric 1: Newly Served Population (M1)

- **Explanation:** The total residential population living in H3 cells that fall within walking distance (350 m) of newly proposed stations and are not already within walking distance of any existing station.
- **Formula:**
  A population cell $c \in C$ is newly served under scenario $s \in \{\text{lane\_aware}, \text{population\_only}\}$ if:
  $$\min_{j \in S_{\text{existing}}} \text{dist}(c, j) > d_{\text{walk}} \quad \text{and} \quad \min_{p \in S_{\text{proposed}}(s)} \text{dist}(c, p) \le d_{\text{walk}}$$
  The metric sums the population of all unique newly served cells:
  $$\text{NewlyServedPop}(s) = \sum_{c \in C_{\text{newly\_served}}(s)} \text{population}[c]$$
  Each cell is counted exactly once, preventing double counting between nearby proposed stations.
- **Unit:** Persons (count of residents)
- **Tables and columns read:**
  - `population`: `cell_id`, `population`
  - `stations`: `station_id`, `lat`, `lon`
  - `station_candidates`: `scenario`, `cell_id`, `rank` (filter `rank.notna()`)
- **Scenarios:** Applies to `lane_aware` and `population_only`. For `baseline`, the value is 0 by definition.
- **Status:** **Available now** (all required tables and columns exist in the contract schemas).

---

### Metric 2: Population Newly Served per km of New Corridor (M6)

- **Explanation:** The number of newly served residents divided by the total physical length (in kilometres) of the top-k recommended bike-lane corridors, measuring infrastructure efficiency.
- **Formula:**
  $$\text{NewlyServedPopPerKm}(s, k) = \frac{\text{NewlyServedPop}(s)}{\text{CorridorLengthKm}(s, k)}$$
  where:
  $$\text{CorridorLengthKm}(s, k) = \frac{1}{1000} \sum_{i \in \text{TopKCorridors}(s)} \sum_{e \in \text{corridors.edge\_ids}[i]} \text{edges.length\_m}[e]$$
  $\text{TopKCorridors}(s)$ selects rows from `corridors` where `scenario == s` and `rank <= k`. Each corridor's `edge_ids` list is resolved against `edges.edge_id` to retrieve `edges.length_m`.
- **Unit:** Persons / km
- **Tables and columns read:**
  - `station_candidates`, `population`, `stations` (for `NewlyServedPop(s)`)
  - `corridors`: `scenario`, `corridor_id`, `edge_ids`, `rank`
  - `edges`: `edge_id`, `length_m`
- **Scenarios:** Applies to `lane_aware` and `population_only`. For `baseline`, newly served population is 0 (no proposed stations exist), so the metric is not defined (division of 0 by corridor length).
- **Comparison to baseline:** Not defined for baseline. Reported as a comparison between `lane_aware` and `population_only`. Per design doc §7.3, `lane_aware` stations sit on connected bike lanes by construction, so this metric tests whether they serve more people per kilometre of new lane needed.
- **Status:** **Available now** (calculated by joining `corridors.edge_ids` to `edges.length_m`).

---

### Metric 3: Total Demand per Newly Served Person (M11)

- **Explanation:** The increase in total synthetic bike trips generated under an expansion scenario compared to baseline, divided by the newly served population.
- **Formula:**
  $$\text{DemandPerNewlyServedPerson}(s) = \frac{\text{TotalTrips}(s) - \text{TotalTrips}(\text{baseline})}{\text{NewlyServedPop}(s)}$$
  where total trips in scenario $s$ is the sum of trip counts from the stored contract table `routes`:
  $$\text{TotalTrips}(s) = \sum \text{routes.trip\_count} \quad \text{where } \text{routes.scenario} == s$$
  (The in-memory interface table `trip_matrix.trip_count` can also be used as an alternative before the routing stage).
  Per design decision D10, demand expands when proposed stations capture previously unserved population: $\Delta \text{Trips} = k_{\text{scaling}} \times \Delta P$, with scaling factor $k_{\text{scaling}} = 0.05$ (`config/default_config.yaml`: `demand.gravity_scaling_k`).
- **Unit:** Trips / person
- **Tables and columns read:**
  - `routes`: `scenario`, `trip_count` (primary stored contract table; `trip_matrix.trip_count` as an in-memory alternative)
  - `station_candidates`, `population`, `stations` (for `NewlyServedPop(s)`)
- **Scenarios:** Applies to `lane_aware` and `population_only`. For `baseline`, both the increase in trips ($\text{TotalTrips}(\text{baseline}) - \text{TotalTrips}(\text{baseline}) = 0$) and the newly served population ($\text{NewlyServedPop}(\text{baseline}) = 0$) are zero, resulting in a 0/0 division; therefore, the metric is not defined for `baseline`.
- **Comparison to baseline:** Directly computed as the difference from `baseline` trips.
- **Status:** **Available now** (all columns exist in `routes` and `population`).

---

### Metric 4: Top-k Corridor Overlap across Scenarios and Seeds (M13, M14)

- **Explanation:** The degree of agreement between the top-k recommended corridors across scenarios, used to classify corridors as robust (needed in all scenarios) or station-dependent (needed only under specific expansions).
- **Formula:**
  Let $E(s, k)$ be the set of unique directed `edge_id`s in the top-$k$ corridors of scenario $s$:
  $$E(s, k) = \bigcup_{i \in \text{corridors where } \text{scenario}=s \text{ and } \text{rank} \le k} \text{edge\_ids}[i]$$
  (An edge-level equivalent can also be calculated directly using `edge_scores` where `scenario == s` and `rank <= k`).

  1. **Pairwise Jaccard Overlap:**
     $$J(s_1, s_2; k) = \frac{|E(s_1, k) \cap E(s_2, k)|}{|E(s_1, k) \cup E(s_2, k)|}$$
  2. **Robust Corridor Share:**
     $$\text{RobustShare}(k) = \frac{|E(\text{baseline}, k) \cap E(\text{lane\_aware}, k) \cap E(\text{population\_only}, k)|}{|E(\text{baseline}, k) \cup E(\text{lane\_aware}, k) \cup E(\text{population\_only}, k)|}$$
  3. **Classification per corridor / edge (design doc §7.3):**
     - **Robust:** appears in the top-$k$ in **all three scenarios**:
       $$e \in E(\text{baseline}, k) \cap E(\text{lane\_aware}, k) \cap E(\text{population\_only}, k)$$
     - **Station-dependent:** appears in the top-$k$ of at least one scenario, but **not all three scenarios** (otherwise):
       $$e \in \Big(E(\text{baseline}, k) \cup E(\text{lane\_aware}, k) \cup E(\text{population\_only}, k)\Big) \setminus \Big(E(\text{baseline}, k) \cap E(\text{lane\_aware}, k) \cap E(\text{population\_only}, k)\Big)$$

- **Stability across random seeds (Decision D16):**
  Per design decision D16, the gravity demand model in `src/bubi/demand/gravity.py` emits deterministic expected trip counts without stochastic sampling (`random_seed` is currently unused in code). Consequently, across random seeds the overlap is identically 1.0 (100%). Seed variation checks will become meaningful if stochastic trip generation is introduced in a future release.
- **Unit:** Dimensionless ratio in $[0.0, 1.0]$ or percentage ($0\% - 100\%$)
- **Tables and columns read:**
  - `corridors`: `scenario`, `corridor_id`, `edge_ids`, `rank`
  - `edge_scores`: `scenario`, `edge_id`, `rank`
- **Scenarios:** Evaluates all three scenarios simultaneously (`baseline`, `lane_aware`, `population_only`).
- **Status:**
  - Jaccard overlap and set intersections: **Available now** (computed directly from `corridors.edge_ids` or `edge_scores.edge_id`).
  - Classification view: **Needs new table / view** — `src/bubi/scenarios/runner.py` specifies `build_scenario_comparison_view(df_edge_scores, df_corridors, top_k)`, which is currently a stub raising `NotImplementedError`. It should return a comparison table with corridor IDs, scenario membership, and the `robust` vs `station_dependent` classification.

---

## 3. Additional Defined Metrics

The following metrics from the week-1 draft have exact definitions and can be implemented immediately:

### Metric 5: Share of City Population Served (M2)
- **Explanation:** The proportion of Budapest's total gridded population living within walking coverage (350 m) of a station.
- **Formula:** $\text{ServedPop}(s) / \sum_{c \in C} \text{population}[c]$, where $\text{ServedPop}(s)$ sums population cells within 350 m of any active station in scenario $s$.
- **Unit:** Percentage ($0\% - 100\%$)
- **Tables:** `population` (`population`), `stations`, `station_candidates`
- **Status:** **Available now**

### Metric 6: Newly Served Population per New Station (M3)
- **Explanation:** The average number of newly served residents gained per newly proposed station.
- **Formula:** $\text{NewlyServedPop}(s) / N$, where $N = 10$ (`config/default_config.yaml`: `candidate_n: 10`).
- **Unit:** Persons / station
- **Tables:** `station_candidates`, `population`
- **Status:** **Available now**

### Metric 7: Recommended Corridor Length (M5)
- **Explanation:** Total physical length in kilometres of the top-$k$ recommended corridors.
- **Formula:** $\frac{1}{1000} \sum_{i \in \text{TopKCorridors}(s)} \sum_{e \in \text{edge\_ids}[i]} \text{edges.length\_m}[e]$.
- **Unit:** Kilometres (km)
- **Tables:** `corridors` (`rank`, `edge_ids`), `edges` (`length_m`)
- **Status:** **Available now**

### Metric 8: Route Volume Covered per km (M7)
- **Explanation:** Average trip volume carried per kilometre of new corridor built among top-$k$ recommendations.
- **Formula:** $\sum_{e \in E(s, k)} \text{edge\_scores.volume}[e] / \text{CorridorLengthKm}(s, k)$.
- **Unit:** Trips / km
- **Tables:** `edge_scores` (`volume`, `rank`), `corridors`, `edges` (`length_m`)
- **Status:** **Available now**

### Metric 9: Total Synthetic Trips (M10)
- **Explanation:** Total volume of synthetic trips across all station pairs in a scenario.
- **Formula:** $\sum \text{trip\_matrix.trip\_count}$ for the given scenario.
- **Unit:** Trips
- **Tables:** `trip_matrix` (`scenario`, `trip_count`)
- **Status:** **Available now**

### Metric 10: Unroutable Station Pairs and Dropped Trips (M12)
- **Explanation:** Count and share of station pairs and trips that could not be connected on the street network.
- **Formula:** Count of station pairs where `snap_stations` marks `too_far == True` or `nx.has_path` is false, and the sum of `trip_count` on those dropped pairs.
- **Unit:** Count of pairs / percentage of total trips
- **Source:** Output report dictionary of `src/bubi/routing/router.py`: `route_station_pairs` (`routing_report["unroutable_pairs"]`, `routing_report["unroutable_trips"]`).
- **Status:** **Available now** (in routing report; data-quality metric).

---

## 4. Deferred Draft Metrics

The following metrics from the week-1 draft cannot be computed deterministically yet and are deferred:
- **M4 (Network walking distance vs straight-line buffer):** Deferred until `src/bubi/network/graph.py` builds the walking graph. Straight-line distance (D15) is used in the interim.
- **M8 (Gap share of trips):** Requires joining every route's edge sequence against `edges.has_dedicated_lane`. Can be added once the full routing stage is integrated.
- **M9 (Corridor continuity index):** Depends on the continuity factor in corridor scoring, which is currently set to default 1.0 awaiting the final OSM lane tag rules.
- **M15 & M16 (Parameter sensitivity across grid):** Defined as an exploratory offline analysis (varying $\alpha \pm 50\%$, $\beta \pm 50\%$, walk threshold 300 vs 400 m) for the report methodology appendix rather than an automated pipeline metric. The pass-rate test in `scripts/lane_connectivity_pass_rate.py` provides the initial check.

---

## 5. Top-k Cut-Off Proposal

Design doc §7.3 and `src/bubi/scenarios/runner.py` require a cut-off threshold $k$ to identify top corridors and classify them as robust versus station-dependent.

### Proposal: Recommended default $k = 10$

**Justification in plain words:**
1. **Match with proposed stations ($N = 10$):** Siting recommends 10 new stations. Evaluating 10 corridors provides a balanced 1:1 comparison between station recommendations and corridor recommendations.
2. **Dashboard usability:** In the Streamlit dashboard wireframe, Area 5 (Key metrics) and Area 7 (Recommendations table) display priority items in a compact table. A list of 10 corridors fits on a standard laptop display without pagination or vertical scrolling.
3. **Planning realism:** Municipal cycling infrastructure plans in Budapest focus on a manageable cohort of top-priority interventions (5–10 corridors) per planning cycle.

### Sensitivity range for the team to test
To confirm that results are not sensitive to an arbitrary choice of $k$, the pipeline and dashboard should evaluate three values:
- **$k = 5$:** "Immediate priorities" — core high-demand corridors that appear first in any scenario.
- **$k = 10$ (Recommended default):** "Standard programme" — balanced intervention set.
- **$k = 20$:** "Network expansion" — broader view evaluating secondary connections.

*This proposal is marked for project leader and Data Science confirmation.*

---

## 6. Summary for the Project Leader

| Metric | Available now? | New column or table needed | Responsible module |
|---|---|---|---|
| **Newly served population (M1)** | Yes | None (computed from `station_candidates`, `population`, `stations`) | `src/bubi/stations/` / `scenarios/` |
| **Share of city population served (M2)** | Yes | None (M1 / total `population.population`) | `src/bubi/scenarios/` |
| **Newly served population per station (M3)** | Yes | None (M1 / $N$) | `src/bubi/scenarios/` |
| **Recommended corridor length (M5)** | Yes | None (sum `edges.length_m` via `corridors.edge_ids`) | `src/bubi/corridors/` / `scenarios/` |
| **Population newly served per km of corridor (M6)** | Yes | None (ratio M1 / M5; undefined for baseline; adding `length_m` column to `corridors` would simplify querying) | `src/bubi/scenarios/` |
| **Route volume covered per km (M7)** | Yes | None (sum `edge_scores.volume` on top-k edges / M5) | `src/bubi/corridors/` / `scenarios/` |
| **Total synthetic trips (M10)** | Yes | None (sum `trip_matrix.trip_count`) | `src/bubi/demand/` / `scenarios/` |
| **Demand per newly served person (M11)** | Yes | None (trip difference from `routes.trip_count` / M1; undefined for baseline) | `src/bubi/scenarios/` |
| **Unroutable / dropped trips (M12)** | Yes | None (emitted in `routing_report` dict from `route_station_pairs`) | `src/bubi/routing/` |
| **Top-k corridor overlap across scenarios (M14)** | Yes | None (Jaccard similarity on top-k `edge_ids`) | `src/bubi/scenarios/` |
| **Robust corridor classification (M13)** | Needs new view | Derived comparison view table classifying corridors as robust (in all 3 scenarios) vs station-dependent (otherwise) | `src/bubi/scenarios/runner.py` (`build_scenario_comparison_view`) |
| **Top-k overlap across seeds** | N/A today | None needed today; deterministic model (D16). Seed testing applies only if sampling is added | `src/bubi/demand/` |
