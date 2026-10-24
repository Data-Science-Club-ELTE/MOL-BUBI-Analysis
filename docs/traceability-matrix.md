# Requirements Traceability Matrix — Design Decisions D1–D11

Issue: #4 · Module: `src/bubi/profiling` · Owner: Aizirek Muradylova (BA / Data Analysis)
Status: **DRAFT v0.1** (Week 1) · Last updated: 2026-10-18

This matrix links each technical design decision (D1–D11) to the module that implements it
and the test or validation method that checks it. It is updated as modules land on `develop`.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Implemented and covered by a test |
| 🟡 | Partially implemented or partially tested |
| 🔴 | **Gap**: not implemented and/or no test yet |
| ❓ | Decision text not yet confirmed from the technical design document |

Sources are listed per row: repo path on `develop`, or an open PR branch (marked *PR #n*).

---

## 1. Matrix

| ID | Decision (short) | Responsible module(s) | Existing test / validation | Planned test / validation | Impl. | Test | Notes |
|---|---|---|---|---|---|---|---|
| **D1** | ❓ *Not defined in repo* | — | — | — | ❓ | ❓ | Pending text from technical design doc |
| **D2** | Routing prefers flat/downhill roads; ignores traffic and existing bike infrastructure | `routing` (`router.py`) | `tests/test_modules_mock.py::test_routing_edge_weight` — checks uphill penalty, zero penalty for flat/downhill | Unit test: route on `sample_edges` gives identical path when `has_dedicated_lane` is flipped (proves lanes are ignored). Integration test: no traffic fields used in cost | 🟡 `compute_edge_weight` done; `route_station_pairs` not implemented | 🟡 | Slope half tested; "ignores lanes/traffic" half untested |
| **D3** | Per-direction OSM tag rule defining a *dedicated bike lane* | `network` (`graph.py`), consumed by `corridors` | `test_contracts.py::test_edges_contract_valid` (type check only). *PR #7*: `test_opposite_directions_are_counted_separately` (direction handling in volumes) | Unit tests on tag combinations (`cycleway:left/right`, `cycleway=lane\|track`, `oneway:bicycle`); manual validation on 3 real Budapest streets (issue #1) | 🔴 `extract_per_direction_edges` not implemented; rule drafted in issue #1 | 🔴 | Rule note due at `docs/decisions/dem-and-lane-tags.md`. Open question: mixed tags on one edge (Week 2) |
| **D4** | Station scores ignore legal, land-use and construction feasibility | `stations` (`selector.py`), `dashboard` (limitations tab) | *PR #8*: stated in dashboard methodology tab | Schema review: `station_candidates` has no feasibility fields; unit test: score depends only on population (+ lane connectivity) | 🔴 selector not implemented | 🔴 | Scope limitation — validation is mainly documentation review |
| **D5** | Results are synthetic and must be labelled as such (not evidence of real cyclist behaviour) | `dashboard` (`app.py`) | *PR #8*: synthetic-data badge + methodology text; `test_app_runs_on_fixtures` (app loads) | UI test asserting the synthetic badge is always rendered; report review | 🟡 on PR #8, not on `develop` | 🟡 | No test asserts the badge exists yet |
| **D6** | ❓ *Not defined in repo* | — | — | — | ❓ | ❓ | Pending |
| **D7** | ❓ *Not defined in repo* | — | — | — | ❓ | ❓ | Pending |
| **D8** | Demand driven by population only; no time-of-day effects | `demand` (`gravity.py`) | `test_contracts.py::test_trip_matrix_contract_valid` (schema has no time column) | Unit test: trip counts change only when population/distance inputs change | 🔴 `generate_synthetic_trips` not implemented | 🟡 schema only | — |
| **D9** | ❓ *Not defined in repo* | — | — | — | ❓ | ❓ | Pending |
| **D10** | Total trips scale as k × ΣP, so new stations increase system demand | `demand` (`gravity.py`); config `demand.gravity_scaling_k = 0.05` | — | Unit test: `sum(trip_count) == k * sum(catchment_pop)` (tolerance); test that adding a station with population increases total trips | 🔴 not implemented | 🔴 | — |
| **D11** | ❓ *Not defined in repo* | — | — | — | ❓ | ❓ | Pending |

---

## 2. Flagged gaps

**Missing definitions**
- D1, D6, D7, D9, D11 are not written anywhere in the repo, issues or PRs. The source is the
  technical design document (referenced as "sections 6.7, 7.3, 9, 13.2" in PR #8).
  → Action: obtain the decision list from the project leader.

**Missing implementation** (all stubs raise `NotImplementedError` on `develop`)
- `network`, `demand`, `routing.route_station_pairs`, `corridors` (gap scoring, merging),
  `stations`, `scenarios`, `profiling.generate_traceability_report`.

**Missing tests**
- Only schema/contract tests exist on `develop` (`test_contracts.py`, `test_modules_mock.py`).
- No behaviour tests for D3, D4, D8, D10.
- D2 is only half tested (slope penalty yes, "ignores lanes/traffic" no).
- `tests/test_profiling.py` is referenced in the profiling README but does not exist.

---

## 3. Design choices found in the repo without a decision number

These may correspond to D1, D6, D7, D9 or D11. To be matched once the list is confirmed.

| Choice | Where | Value |
|---|---|---|
| Walking coverage threshold for existing stations | `stations`, `demand`; `config station_scoring.walk_coverage_threshold_m` | 350 m (range 300–400 m) |
| Spatial unit = H3 resolution 9 | `population`; `config spatial.h3_resolution` | 9 |
| Population source | `population`; `config demand.population_source` | WorldPop 2026 100 m (vs GHSL, issue #9) |
| Analysis CRS | `config spatial.crs_analysis` | EPSG:23700 (EOV) |
| Frozen OSM graph version | `network`; `config network.frozen_graph_version` | `budapest_osm_2026w1` |
| Uphill penalty strength α | `routing`; `config network.uphill_penalty_alpha` | 3.0 |
| Gravity distance decay | `demand`; `config demand.gravity_distance_decay`, `gravity_beta` | exponential, β = 0.0015 |
| Corridor score = volume × gap length × continuity | `corridors` README | continuity factor agreed in week 4 |
| Two siting strategies (lane-aware vs population-only) + baseline | `stations`, `scenarios` | 3 scenarios |
| Parameter parity across scenarios (seed, β, N, walk distance) | `scenarios` README | seed 42, N = 10 |
| Greedy station spacing | `stations`; `config station_scoring.min_spacing_m` | 400 m |
| Observed GPS routes only if data arrives before week 4 | `ingestion` README | conditional |

---

## 4. Update log

| Date | Change |
|---|---|
| 2026-10-18 | v0.1 — first draft from repo, issues #1–#9 and open PRs (#5, #7, #8) |
