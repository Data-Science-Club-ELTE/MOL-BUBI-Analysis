# Requirements Traceability Matrix - Design Decisions D1–D11

Issue: #4 · Module: `src/bubi/profiling` · Owner: Aizirek Muradylova (BA / Data Analysis)

Status: **DRAFT v0.2** (Week 2) · Last updated: 2026-10-25

This matrix links each technical design decision (D1–D11) to the module that implements it
and the test or validation method that checks it. It is updated as modules land on `develop`.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Implemented and covered by a test |
| 🟡 | Partially implemented or partially tested |
| 🔴 | **Gap**: not implemented and/or no test yet |
| ❓ | Decision text not yet confirmed from the technical design document |

Sources are listed per row: repo path on `develop`, or an unmerged branch (marked *branch*).

---

## 1. Matrix

| ID | Decision (short) | Responsible module(s) | Existing test / validation | Planned test / validation | Impl. | Test | Notes |
|---|---|---|---|---|---|---|---|
| **D1** | ❓ *Not defined in repo* | — | — | — | ❓ | ❓ | Pending text from technical design doc |
| **D2** | Routing prefers flat/downhill roads; ignores traffic and existing bike infrastructure | `routing` (`router.py`) | `tests/test_modules_mock.py::test_routing_edge_weight` (uphill penalty, zero for flat/downhill). *Branch* `routing-prototype-issue-6`: `test_cost.py`, `test_dijkstra.py`, `test_engine.py` | Unit test: route on `sample_edges` is identical when `has_dedicated_lane` is flipped (proves lanes are ignored) | 🟡 `compute_edge_weight` on `develop`; Dijkstra engine on unmerged branch | 🟡 | "Ignores lanes/traffic" half still untested |
| **D3** | Per-direction OSM tag rule defining a *dedicated bike lane* | `network` (`graph.py`); consumed by `corridors`, `stations` | `test_corridor_volumes.py::test_opposite_directions_are_counted_separately` (direction handling); `test_contracts.py::test_edges_contract_valid` (type only) | Unit tests on tag combinations (`cycleway:left/right`, `cycleway=lane\|track`, `oneway:bicycle`); manual check on 3 real Budapest streets (issue #1) | 🔴 `extract_per_direction_edges` still a stub | 🔴 | Rule note `docs/decisions/dem-and-lane-tags.md` (issue #1) not on `develop` yet |
| **D4** | Station scores ignore legal, land-use and construction feasibility | `stations` (`selector.py`); `dashboard` limitations tab | `tests/test_stations.py::test_selection_schema_spacing_and_scenarios` (score built from population and lane connectivity only); `docs/station_lane_connectivity.md` §3 | Report review; keep `StationCandidatesSchema` free of feasibility fields | ✅ selector implemented (PR #26) | 🟡 | Scope limitation; validated by inspection rather than a dedicated assertion |
| **D5** | Results are synthetic and must be labelled as such | `dashboard` (`app.py`); also stated in `docs/gravity_model_spec.md` §1 | *Branch* `feature/dashboard-wireframe-skeleton`: synthetic-data badge, methodology text, `test_app_runs_on_fixtures` | UI test asserting the synthetic badge is always rendered | 🟡 dashboard branch not merged | 🟡 | No test asserts the badge yet |
| **D6** | ❓ *Not defined in repo* | — | — | — | ❓ | ❓ | Pending |
| **D7** | ❓ *Not defined in repo* | — | — | — | ❓ | ❓ | Pending |
| **D8** | Demand driven by population only; no time-of-day effects | `demand` (`gravity.py`) | `tests/test_gravity.py` (all 5 tests use population + distance only); `TripMatrixSchema` has no time column; spec §5 | — | ✅ implemented (PR #25) | ✅ | Spec lists "no POIs, capacity, or time of day" as a known simplification |
| **D9** | ❓ *Not defined in repo* | — | — | — | ❓ | ❓ | Pending |
| **D10** | Total trips scale as k × ΣP, so new stations increase system demand | `demand` (`gravity.py`); config `gravity_scaling_k = 0.05` | `tests/test_gravity.py::test_total_demand_is_k_times_population`, `::test_new_station_grows_demand` | — | ✅ implemented (PR #25) | ✅ | Fully traced |
| **D11** | ❓ *Not defined in repo* | — | — | — | ❓ | ❓ | Pending |

**Summary:** 2 ✅ fully traced (D8, D10) · 4 partial or gap (D2, D3, D4, D5) · 5 undefined (D1, D6, D7, D9, D11)

---

## 2. Flagged gaps

**Missing definitions**
- D1, D6, D7, D9, D11 are not written anywhere in the repo, issues or PRs. They live in the
  technical design document (cited as "sections 6.7, 7.3, 9, 13.2" in the dashboard branch).
  → Action: obtain the decision list from the project leader.

**Missing implementation** (functions still raising `NotImplementedError` on `develop`)
- `network` (graph build, per-direction edges), `population` (H3 aggregation), `ingestion.futar`,
  `routing.route_station_pairs`, `corridors` (gap scoring, corridor merging),
  `scenarios` (runner, comparison view), `profiling.generate_traceability_report`.

**Missing tests**
- No behaviour tests for D3 (lane tag rule) yet.
- D2 is only half tested (slope penalty yes, "ignores lanes/traffic" no).
- D5 has no test asserting the synthetic label.
- `tests/test_profiling.py` is referenced in the profiling README but does not exist.

**Open risks from new work**
- Catchments and candidate filtering use straight-line distance, not the walking network
  (`gravity_model_spec.md` §5, `station_lane_connectivity.md` §1).
- Lane-connectivity pass-rate test has only been run on the 8-cell mock fixture.
- `random_seed` is unused because demand is deterministic. Check whether that conflicts with scenario parameter parity.

---

## 3. Design choices found in the repo without a decision number

These may correspond to D1, D6, D7, D9 or D11. They are to be matched once the list is confirmed.

| Choice | Where | Value |
|---|---|---|
| Walking coverage threshold for existing stations | `stations`, `demand`; config `walk_coverage_threshold_m` | 350 m (range 300–400 m) |
| Straight-line distance as stand-in for walking distance | `demand`, `stations` | temporary |
| Spatial unit = H3 resolution 9 | `population`; config `h3_resolution` | 9 |
| Population source | `population`; config `population_source` | WorldPop 2026 100 m (vs GHSL, issue #9) |
| Analysis CRS | config `crs_analysis` | EPSG:23700 (EOV) |
| Frozen OSM graph version | `network`; config `frozen_graph_version` | `budapest_osm_2026w1` |
| Uphill penalty strength α | `routing`; config `uphill_penalty_alpha` | 3.0 |
| Gravity distance decay | `demand`; config `gravity_distance_decay`, `gravity_beta` | exponential, β = 0.0015 |
| Lane connectivity is a continuous score, not a hard filter | `stations`; `station_lane_connectivity.md` §4 | proposed rule, to be agreed |
| Lane-connectivity reach R | `stations` | 400 m (config key to add) |
| Corridor score = volume × gap length × continuity | `corridors` README | continuity factor agreed in week 4 |
| Two siting strategies (lane-aware vs population-only) + baseline | `stations`, `scenarios` | 3 scenarios |
| Parameter parity across scenarios (seed, β, N, walk distance) | `scenarios` README | seed 42, N = 10 |
| Greedy station spacing | `stations`; config `min_spacing_m` | 400 m |
| Observed GPS routes only if data arrives before week 4 | `ingestion` README | conditional |

---

## 4. Update log

| Date | Change |
|---|---|
| 2026-10-18 | v0.1: first draft from repo, issues #1–#9 and open branches |
| 2026-10-25 | v0.2: D8 and D10 marked fully traced after PR #25 (gravity model); D4 updated after PR #26 (station selection); D2 notes routing branch tests; gap list and design-choice table refreshed |
