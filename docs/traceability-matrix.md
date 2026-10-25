# Traceability matrix: design decisions D1-D11

Issue #4, `src/bubi/profiling`. Aizirek Muradylova (BA / Data Analysis).
Version 1.0, updated 25 Oct 2026.

Decisions are taken from section 2 of the technical design doc. For each one I list where it is
implemented, what tests it today, and what test we still need. Status is based on `develop`
unless a branch is named.

Status values:
- **Done**: implemented and tested
- **Partial**: implemented or tested only in part
- **Missing**: not implemented or no test yet

## Matrix

| ID | Decision | Module | Tested now by | Still needed | Code | Tests | Notes |
|---|---|---|---|---|---|---|---|
| D1 | Trips and routes are synthetic; real trip/GPS data replaces them if it arrives | `demand`, `routing`, `ingestion` | `test_gravity.py`; `route_type` check in `test_contracts.py` | Check routing output has `route_type = synthetic`; later, check `observed` routes go through corridors unchanged | Partial | Partial | Trips merged in #25. Routing is still on the `routing-prototype-issue-6` branch |
| D2 | Routing prefers flat and downhill roads, ignores traffic and bike lanes | `routing` | `test_modules_mock.py::test_routing_edge_weight`; routing branch has `test_cost.py`, `test_dijkstra.py`, `test_engine.py` | Test that the route doesn't change when `has_dedicated_lane` is flipped | Partial | Partial | Slope part is tested, "ignores lanes" part isn't |
| D3 | A direction counts as covered if it has a dedicated lane in that direction; we target busy directions with no lane | `network`, used by `corridors` and `stations` | `test_corridor_volumes.py::test_opposite_directions_are_counted_separately` | Tests for the OSM tag rule (`cycleway:left/right`, `oneway:bicycle`, parallel cycleways); check on 3 real streets (issue #1) | Missing | Missing | Lane extraction and gap filter are still stubs. Edge splitting rule due in week 2 |
| D4 | New stations come from existing lanes and population, not from trip demand | `stations` | `test_stations.py` (selection and connectivity tests) | Test that station output stays the same when trips/routes change | Done | Done | Merged in #26. Feasibility (legal, land use) is out of scope |
| D5 | Synthetic results are a demo and must be labelled; station picks use real inputs | `dashboard`, report | Dashboard branch shows a "synthetic data" badge | Test that the label is always shown | Partial | Missing | Dashboard branch not merged yet |
| D6 | Deliverable is a dashboard plus technical docs, code on GitHub | `dashboard`, `profiling`, repo/CI | CI workflow; dashboard branch test `test_app_runs_on_fixtures` | Demo checklist in week 7 | Partial | Partial | Report not started |
| D7 | Routing runs in-house on the OSM graph, no external service | `routing` | Routing branch runs Dijkstra locally with NetworkX, no HTTP calls | Check in review that `routing` makes no network calls | Partial | Partial | Needs the DEM source |
| D8 | Gravity model driven by population only, no time of day | `demand` | `test_gravity.py`; trip matrix schema has no time column | - | Done | Done | Merged in #25 |
| D9 | Station score is a product of normalized factors, not a weighted sum | `stations` | `test_stations.py` (zero connectivity gives score 0) | Test the formula directly on known numbers | Done | Partial | Merged in #26 |
| D10 | Total demand grows when new stations are added | `demand` | `test_gravity.py::test_total_demand_is_k_times_population`, `::test_new_station_grows_demand` | - | Done | Done | Merged in #25 |
| D11 | Three scenarios: baseline, lane-aware, population-only | `scenarios`, `stations` | `test_stations.py` covers both siting strategies | Test that scenarios differ only in station sets (same seed, parameters, N, spacing) | Missing | Partial | Scenario runner is a stub, planned for week 5 |

In total: 3 done (D4, D8, D10), 7 partial, 1 missing (D3).

## Gaps

Not implemented yet on `develop`:
- lane extraction in `network` and gap scoring/merging in `corridors` (D3)
- the scenario runner and comparison view (D11)
- the routing engine, which so far exists only on a branch (D1, D2, D7)
- also population aggregation, Futár ingestion and the traceability report generator

No tests yet for:
- the lane tag rule (D3)
- routing ignoring lanes and traffic (D2)
- the synthetic label on the dashboard (D5)
- the product formula (D9) and scenario parity (D11), which are only covered indirectly
- `tests/test_profiling.py`, mentioned in the profiling README but missing

Where the code differs from the design doc:
- Walking coverage should be measured along the walking network (section 7.2). The code currently uses straight-line distance.
- Trip generation should be seeded (section 6.3). The model is deterministic, so `random_seed` isn't used. We should check this still works for the stability check across seeds (section 9).
- The lane connectivity pass-rate test has only been run on the mock fixture, not on real OSM data.

## Section 9 checks

| Check | How it's covered | Status |
|---|---|---|
| Visual sanity review | Geoinformatics member, on the dashboard map | Not started |
| Stability across seeds and parameters | Metrics M14-M16 in `evaluation-metrics.md` | Draft |
| Traceability | This matrix and the "selected recommendation" panel on the dashboard | In progress |
| Scenario comparability | Planned test under D11 | Not started |

## Changes

| Date | Change |
|---|---|
| 18 Oct | First draft from the repo, issues and open branches |
| 25 Oct | Updated after #25 and #26 |
| 25 Oct | Filled in all decisions from the design doc, added gaps against the design and section 9 checks |
