# Traceability matrix: design decisions D1-D17

Issue #4, `src/bubi/profiling`. Aizirek Muradylova (BA / Data Analysis).
Version 2.0, updated 6 Nov 2026.

Decisions are taken from section 2 of the technical design doc (`bubi-technical-design.md`). For each
one I list where it is implemented, what tests it today, what test we still need, the code status,
and the test status. Status is based on `develop` at revision `4e73b55` (and merge commit).

Status values:
- **Done**: implemented and tested
- **Partial**: implemented or tested only in part
- **Missing**: not implemented or no test yet

## Matrix

| ID | Decision | Module | Tested now by | Still needed | Code | Tests | Notes |
|---|---|---|---|---|---|---|---|
| D1 | Trips and routes are synthetic; real trip/GPS data replaces them if it arrives | `demand`, `routing`, `ingestion`, `corridors` | `test_gravity.py`; `test_routing.py::test_output_validates_against_routes_schema`; `test_contracts.py::test_routes_contract_valid`; `test_observed_routes_e2e.py::test_simulated_traces_convert_to_observed_routes`, `::test_observed_routes_pass_through_volume_step_unchanged`; `test_dashboard.py::test_route_layer_labels_observed_routes_honestly` | End-to-end test with real GPS map-matching once `map_match_trace` is implemented | Partial | Partial | Synthetic trips and slope-aware routing merged. Observed route conversion drafted; map-matching is a placeholder |
| D2 | Routing prefers flat and downhill roads, ignores traffic and bike lanes | `routing` | `test_routing.py::test_flat_versus_uphill_route_prefers_flat`, `::test_reverse_direction_uses_negated_grade`, `::test_build_graph_sets_correct_weights`; `test_modules_mock.py::test_routing_edge_weight` | Explicit test confirming that route choice does not change when `has_dedicated_lane` is toggled | Done | Partial | Slope weighting and Dijkstra path search merged in `routing/router.py`. Slope penalty tested; "ignores lanes" is true in code but needs an explicit test |
| D3 | A direction counts as covered if it has a dedicated lane in that direction; we target busy directions with no lane | `network`, `corridors`, `dashboard` | `test_corridors.py::test_edge_with_lane_in_its_direction_is_excluded`, `::test_one_sided_lane_keeps_only_the_missing_direction`; `test_corridor_volumes.py::test_opposite_directions_are_counted_separately`; `test_dashboard.py::test_lane_geojson_groups_directions_by_their_own_lane_status`, `::test_lane_geojson_draws_each_direction_on_its_right_side` | Tests for the OSM tag extraction rule in `network/graph.py` (`cycleway:left/right`, `oneway:bicycle`, parallel cycleways) on real Budapest streets (issue #1) | Partial | Partial | Gap detection in `corridors` and direction rendering in `dashboard` are implemented and tested. `network/graph.py` edge extraction is still a stub |
| D4 | New stations come from existing lanes and population, not from trip demand | `stations` | `test_stations.py::test_filter_excludes_covered_and_small_cells`, `::test_connectivity_continuous_and_zero_when_unconnected`, `::test_selection_schema_spacing_and_scenarios`, `::test_min_spacing_blocks_neighbours`; `test_contracts.py::test_station_candidates_contract_valid` | - | Done | Done | Merged in #26. Siting uses only population and existing lanes; demand is not an input |
| D5 | Synthetic results are a demo and must be labelled; station picks use real inputs | `dashboard`, report | `test_dashboard.py::test_route_layer_is_labelled_synthetic`, `::test_route_layer_labels_observed_routes_honestly`, `::test_route_layer_on_the_map_shows_label_tooltip_and_legend`, `::test_app_runs_on_fixtures` | Written methodology appendix and presentation storyline | Partial | Done | Dashboard displays demo notices, and route layer/tooltips explicitly show "Synthetic demo data (D5)". Written report not started |
| D6 | Deliverable is a dashboard plus technical docs, code on GitHub | `dashboard`, `profiling`, repo/CI | CI workflow; `test_dashboard.py` (56 tests including `test_app_runs_on_fixtures`, `test_app_shows_bkk_and_osm_attribution`, `test_export_csv_writes_edge_ids_as_a_json_array`) | Final technical report; live demo checklist and rehearsal in week 7 | Partial | Done | Interactive Streamlit prototype merged with tests and CSV export. Written report pending |
| D7 | Routing runs in-house on the OSM graph, no external service | `routing` | `test_routing.py::test_connected_pair_is_routed`, `::test_route_station_pairs_with_edges_geodataframe`, `::test_route_cache_avoids_recomputation` | Test against full Budapest OSMnx graph once `network/graph.py` builds it | Done | Done | Router runs Dijkstra locally using NetworkX in `routing/router.py` without external HTTP calls |
| D8 | Gravity model driven by population only, no time of day | `demand` | `test_gravity.py` (`test_catchment_no_double_counting`, `test_total_demand_is_k_times_population`, `test_no_self_trips_and_symmetric`, `test_distance_decay`); `test_contracts.py::test_trip_matrix_contract_valid` | - | Done | Done | Merged in #25. Gravity model produces trip matrix with no time-of-day fields |
| D9 | Station score is a product of normalized factors, not a weighted sum | `stations` | `test_stations.py::test_connectivity_continuous_and_zero_when_unconnected`, `::test_selection_schema_spacing_and_scenarios` | Direct unit test comparing calculated score against exact hand-computed values | Done | Partial | Implemented in `stations/selector.py` (#26). Zero connectivity forces zero score in `lane_aware` |
| D10 | Total demand grows when new stations are added | `demand` | `test_gravity.py::test_total_demand_is_k_times_population`, `::test_new_station_grows_demand` | - | Done | Done | Merged in #25. Explicitly verified by property tests in `test_gravity.py` |
| D11 | Three scenarios: baseline, lane-aware, population-only | `scenarios`, `stations`, `corridors`, `dashboard` | `test_stations.py::test_selection_schema_spacing_and_scenarios`; `test_corridor_volumes.py::test_scenarios_are_aggregated_independently`; `test_corridors.py::test_scenario_argument_scores_only_that_scenario`, `::test_ranks_and_ids_restart_per_scenario`; `test_dashboard.py::test_app_switches_scenario` | Test verifying scenario parameter parity (same seed, parameters, N, spacing) in `scenarios/runner.py` | Partial | Partial | Station siting, corridor scoring, and dashboard layer switching support all three scenarios. Orchestrator in `scenarios/runner.py` is still a stub |
| D12 | Data contract is frozen in code as Pandera schemas in `contracts/schemas.py` and documented in `docs/data_dictionary.md` | `contracts` | `test_contracts.py` (9 tests validating all 7 tables and `trip_matrix`); CI fixture regeneration in `.github/workflows/ci.yml` | - | Done | Done | Frozen schemas in `contracts/schemas.py` govern all table interfaces. Documented in `docs/data_dictionary.md` |
| D13 | Stations come from Futár `bicycle-rental` snapshot, keeping only fixed stations (`type == "virtual"`, style not floating), yielding 704 stations | `ingestion` | `test_stations_table.py::test_selections_agree_and_table_is_written`, `::test_disagreement_writes_nothing`, `::test_invalid_coordinates_are_rejected`; `test_ingestion.py::test_ingest_from_saved_response_keeps_only_stations`, `::test_ingest_rejects_disagreeing_selection_rules`, `::test_frozen_snapshot_is_recorded_in_config` | - | Done | Done | Dual selection rules verified; produces `data/processed/stations.parquet` with 704 fixed stations from 2026-10-18 snapshot |
| D14 | Tunable parameters live in `config/default_config.yaml` (seed 42, EPSG:4326/23700, H3 res 9, α=3.0, walk 350m, k=0.05, β=0.0015, pop floor 100, N=10, spacing 400m, R=400m) | `config`, `dashboard`, `scripts` | `test_dashboard.py::test_missing_config_falls_back_to_defaults`, `::test_broken_config_is_reported_not_ignored`; `test_ingestion.py::test_frozen_snapshot_is_recorded_in_config`; `test_run_pipeline.py::test_stages_are_declared_in_dependency_order` | Test that module function argument defaults stay strictly in sync with `config/default_config.yaml` | Partial | Partial | Config file created and used by scripts and dashboard. Wiring config directly into module signatures is an open item (§14.4) |
| D15 | Distance filters use straight-line distance in EPSG:23700 as a documented lower bound until network layers land | `stations`, `demand` | `test_stations.py::test_filter_excludes_covered_and_small_cells`, `::test_min_spacing_blocks_neighbours`; `test_gravity.py::test_distance_decay`, `::test_catchment_no_double_counting` | Tests with walking-network and street-routed distances once `network/graph.py` is implemented | Done | Done | Accepted design decision. Straight-line Euclidean distance in Hungarian national grid (EPSG:23700) is implemented as documented lower bound |
| D16 | Gravity model emits deterministic expected trip counts (seed is unused); exponential distance decay is implemented | `demand` | `test_gravity.py::test_total_demand_is_k_times_population`, `::test_no_self_trips_and_symmetric`, `::test_distance_decay`, `::test_new_station_grows_demand` | Tests for random seed reproducibility and power-law decay if stochastic sampling or power-law option is added | Done | Done | Accepted design decision. Model is deterministic; exponential decay formula verified in `docs/gravity_model_spec.md` |
| D17 | Pipeline is a Python package under `src/bubi/`, managed with `uv`, validated with Pandera, tested with pytest, linted with ruff, CI on GitHub Actions | repo / package scaffold | GitHub Actions workflow (`.github/workflows/ci.yml`); `test_run_pipeline.py::test_stages_are_declared_in_dependency_order`, `::test_main_exit_code_and_json_report`; all 209 tests passing in pytest; ruff check passing | End-to-end CI run with full pipeline once all modules are implemented | Done | Done | Packaging, Pandera schemas, ruff rules (E, F, I, W), pytest suite, and CI automation are fully operational |

In total: 9 done (D4, D7, D8, D10, D12, D13, D15, D16, D17), 8 partial (D1, D2, D3, D5, D6, D9, D11, D14), 0 missing.

## Gaps

Not implemented yet on `develop`:
- Functions that still raise `NotImplementedError`:
  - `src/bubi/network/graph.py`: `build_street_graph` and `extract_directed_edges` (OSM network download and per-direction edge extraction)
  - `src/bubi/population/grid.py`: `raster_to_h3` (population raster aggregation to H3 cells)
  - `src/bubi/ingestion/observed_routes.py`: `map_match_trace` (GPS trace map-matching)
  - `src/bubi/scenarios/runner.py`: `run_all_scenarios` and `build_scenario_comparison_view` (scenario runner and comparison view)
  - `src/bubi/profiling/profiler.py`: `generate_traceability_report` (traceability report generator)
- Deliverables still pending:
  - final technical report and methodology appendix (D5, D6)

No tests yet for:
- the OSM lane tag extraction rule (`network/graph.py`)
- routing explicitly ignoring bike lanes and traffic (test in `routing` confirming route invariance to `has_dedicated_lane`)
- the station product formula checked against exact hand-calculated values (direct arithmetic test in `stations`)
- scenario parameter parity check across scenarios in `scenarios/runner.py` (same seed, parameters, N, spacing)
- synchronization check between `config/default_config.yaml` and function default arguments
- `tests/test_profiling.py`, mentioned in the profiling README but missing

Where the code differs from the design doc:
- In `config/default_config.yaml`, power-law decay is listed as an option, but only exponential decay is implemented (D16).
- The lane connectivity pass-rate test has only been run on mock fixtures, not on real OSM data.

## Section 9 checks

| Check | How it's covered | Status |
|---|---|---|
| Visual sanity review | Geoinformatics member, on the dashboard map | Not started (waiting on real network in `network/graph.py`) |
| Stability across seeds and parameters | Clean rebuild reproducibility is covered by `scripts/check_reproducibility.py` and tested in `test_run_pipeline.py`. Initial threshold sensitivity is checked on fixtures by `scripts/lane_connectivity_pass_rate.py`. The trip generator is deterministic (D16), so seed variation does not apply. Parameter sensitivity across thresholds (metrics M14-M16 in `evaluation-metrics.md`) remains draft | Partial |
| Traceability | This matrix (`docs/traceability-matrix.md`), `docs/data_dictionary.md`, `docs/source_inventory.md`, and dashboard metadata tooltips. Automated report in `profiling/profiler.py` is still a stub | In progress |
| Scenario comparability | Siting, scoring, and dashboard layer switching support all 3 scenarios; parity rule fixed in D14/§7.3. Scenario runner in `scenarios/runner.py` is still a stub | Partial |
| Contract compliance | Every contract table validates against Pandera schemas in `src/bubi/contracts/schemas.py`. Automated on CI and in `tests/test_contracts.py` | Done |

## Changes

| Date | Change |
|---|---|
| 18 Oct | First draft from the repo, issues and open branches |
| 25 Oct | Updated after #25 and #26 |
| 25 Oct | Filled in all decisions from the design doc, added gaps against the design and section 9 checks |
| 6 Nov | Added decisions D12-D17, updated D1-D11 to reflect latest develop (corridors, routing, dashboard, and reproducibility checks merged; 209 tests passing), moved D15 and D16 to normal rows, and refreshed gaps |
