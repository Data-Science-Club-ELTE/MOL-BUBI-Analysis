# Scenario Comparison Requirements

Issue: #34 · Owner: Aizirek Muradylova (BA / Data Analysis)
Version: 1.0 (Week 3) · Status: Ready for CS4 and Data Science implementation

This document specifies exactly what the scenario-comparison view must show in
the dashboard. It gives CS4 (dashboard owner) and the Data Science member
requirements they can build and test against.

Metric IDs (M1, M6, M11, M13, M14) and the top-k = 10 default are defined in
`docs/evaluation_metrics.md` (issue #18, branch `feature/18-metrics-specification`).
Table and column names come from `src/bubi/contracts/schemas.py` and
`docs/data_dictionary.md`. All names in this document have been verified against
those files unless marked "unverified".

Audience: teammates (CS4, Data Science MSc) and professors. No GIS expertise is
assumed.

---

## 1. The three scenarios

| Scenario | Station set | Siting rule |
|----------|------------|-------------|
| `baseline` | Existing 704 stations only | None |
| `lane_aware` | Existing + 10 proposed stations | population times lane connectivity |
| `population_only` | Existing + 10 proposed stations | population only |

All scenarios share the same random seed, walk-coverage threshold (350 m),
minimum spacing (400 m), N = 10 proposed stations, gravity parameters and H3
resolution 9. Only the station sets differ (design decision D11, design doc
section 7.3).

**How the user switches:** The sidebar radio selector "Active scenario" in
`src/bubi/dashboard/app.py` already lets the user pick one of the three
scenarios. The main map, metrics bar, detail panel and tables all update to show
that scenario's data.

---

## 2. Requirements

### R1: Scenario selector

| Field | Value |
|-------|-------|
| **Description** | The sidebar provides a radio selector with the three scenario names. Selecting a scenario updates the main map, metrics, detail panel, tables and exports. |
| **Tables and columns** | `edge_scores.scenario`, `corridors.scenario`, `station_candidates.scenario`, `routes.scenario` (all filtered by the selected scenario value). |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`) |
| **Status** | **Available now.** The radio selector and per-scenario filtering are implemented. |

---

### R2: Difference-from-baseline toggle

| Field | Value |
|-------|-------|
| **Description** | A checkbox in the sidebar labelled "Show difference vs baseline". When turned on, the main map and scenario comparison area highlight what changed compared to the `baseline` scenario. When the active scenario is `baseline`, the toggle is disabled (there is no difference to show). |
| **Tables and columns** | No new table. The toggle controls which layers and metrics are displayed. |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`) |
| **Status** | **Needs new code.** The checkbox exists in the sidebar but is disabled with `disabled=True` and a "Week 5" help label. Enable it and wire it to the difference layers described in R3 through R6. |

---

### R3: New stations layer (difference)

| Field | Value |
|-------|-------|
| **Description** | When the difference toggle (R2) is on and the active scenario is `lane_aware` or `population_only`, the map draws the proposed stations in a distinct colour (suggested: blue circles) and labels them "new: proposed". Baseline has no proposed stations, so every proposed station is "new" by definition. |
| **Tables and columns** | `station_candidates`: `scenario`, `cell_id`, `population`, `score`, `rank`. Only rows where `rank` is not null (selected candidates). |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`) |
| **Status** | **Partially available.** Proposed-station markers are already drawn on the map (positioned at their H3 cell centre). The difference mode only needs to change their colour and label; no new data is required. |

---

### R4: Newly served population cells layer (difference)

| Field | Value |
|-------|-------|
| **Description** | When the difference toggle is on, shade H3 cells that are newly served under the active scenario. A cell is newly served if it is within 350 m of a proposed station and not within 350 m of any existing station (see metric M1 in `docs/evaluation_metrics.md`). Colour cells by their population value (suggested: light-to-dark orange gradient). |
| **Tables and columns** | `population`: `cell_id`, `population`. `stations`: `station_id`, `lat`, `lon`. `station_candidates`: `scenario`, `cell_id`, `rank`. |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`) for the map layer. The newly-served-population calculation itself can live in `src/bubi/scenarios/runner.py` or a helper in `src/bubi/stations/`. |
| **Status** | **Needs new code.** The population H3 layer exists (toggle "Population (H3 cells)"), but it currently shows all cells. A filter to identify and shade only newly served cells needs to be implemented. The distance calculation uses straight-line distance in EPSG:23700 (design decision D15). |

---

### R5: Rank-change layer (difference)

| Field | Value |
|-------|-------|
| **Description** | When the difference toggle is on, highlight network edges whose rank changed compared to `baseline`. Compare scenarios at the edge level using `edge_scores` (`scenario`, `edge_id`, `rank`, `score`) by matching on `edge_id`. Do not join on `corridor_id` across scenarios: corridors are built separately per scenario, so the same road can get different `corridor_id`s; `edge_id` is the same in every scenario, so it avoids showing one road as two corridors. On the map, draw each edge using `edges.geometry` and colour it by how its rank changed versus baseline: edges that improved (lower rank number, meaning higher priority) use one colour (suggested: green), edges that worsened (higher rank number) use another (suggested: red), and edges that are new to the top-k in the active scenario are marked as new. |
| **Tables and columns** | `edge_scores`: `scenario`, `edge_id`, `score`, `rank`. Match `baseline` rows to `lane_aware` or `population_only` rows on `edge_id` (not `corridor_id`) to compute rank differences. `edges`: `edge_id`, `geometry` (to draw each edge on the map). |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`) for the map layer. Edge rank comparisons are computed from `edge_scores` or `build_scenario_comparison_view` in `src/bubi/scenarios/runner.py`. |
| **Status** | **Needs new code.** The dashboard edge and corridor layers exist but do not yet display rank differences across scenarios. `build_scenario_comparison_view` in `src/bubi/scenarios/runner.py` computes per-scenario edge ranks; dashboard rendering needs to be wired up. |

---

### R6: Robust vs station-dependent labels

| Field | Value |
|-------|-------|
| **Description** | Classify network elements at the edge level first. An edge is robust if it appears in the top-k (k = 10, per `docs/evaluation_metrics.md` section 5) in all three scenarios (`baseline`, `lane_aware`, `population_only`). An edge is station-dependent if it is in the top-k of at least one scenario but not all three. Corridors are built separately per scenario, so the same road can get different `corridor_id`s; `edge_id` is the same in every scenario, so it avoids showing one road as two corridors.<br><br>**Note for reviewer (corridor label from edges):** In `build_scenario_comparison_view` (`src/bubi/scenarios/runner.py`), corridors are matched across scenarios into groups whenever they share at least one directed edge (`edge_id`). Chains of shared edges form a single corridor group. For each scenario, the group evaluates the best rank of any corridor of that scenario covering any of the group's edges. A corridor group is labelled robust if it reaches the top-k (rank &le; k) in all three scenarios (`baseline`, `lane_aware`, `population_only`), and station-dependent if it is in the top-k of fewer than three scenarios. Individual edges in the view retain their own edge-level robustness labels. Labels are displayed in the map tooltips, the detail panel (wireframe Area 7), and the recommendations table (wireframe Area 9). |
| **Tables and columns** | `edge_scores`: `scenario`, `edge_id`, `rank`, `score`. `corridors`: `scenario`, `corridor_id`, `edge_ids`, `rank`, `score`. `edges`: `edge_id`, `geometry`. Compare by matching `edge_id` across scenarios. Do not join on `corridor_id` across scenarios. |
| **Module** | Scenarios (`src/bubi/scenarios/runner.py`, function `build_scenario_comparison_view`). Dashboard (`src/bubi/dashboard/app.py`) displays the labels. |
| **Status** | **Available in scenario module; needs dashboard wiring.** `build_scenario_comparison_view` in `src/bubi/scenarios/runner.py` is implemented and classifies both edge rows and corridor groups across scenarios. The dashboard needs to consume this view and display the labels on map layers and tables. |

---

### R7: Newly served population metric (M1)

| Field | Value |
|-------|-------|
| **Description** | Display the total number of residents newly served by the proposed stations. A person is newly served if their H3 cell is within 350 m of a proposed station and not within 350 m of any existing station. Show this as a number in the metrics bar (wireframe Area 5) and in the scenario comparison table (wireframe Area 8). For `baseline`, the value is 0 (no proposed stations). |
| **Tables and columns** | `population`: `cell_id`, `population`. `stations`: `station_id`, `lat`, `lon`. `station_candidates`: `scenario`, `cell_id`, `rank`. |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`) for display. The calculation can live in `src/bubi/scenarios/runner.py` or `src/bubi/stations/`. |
| **Status** | **Needs new code.** The metrics bar currently shows "Population in proposed cells" as a placeholder. Replace it with the newly served population count using metric M1. |

---

### R8: Population per km of new corridor metric (M6)

| Field | Value |
|-------|-------|
| **Description** | Display the number of newly served residents divided by the total length in kilometres of the top-k corridors. This measures infrastructure efficiency: how many people are served per kilometre of new bike lane. Show in the metrics bar and the scenario comparison table. Not defined for `baseline` (newly served population is 0). |
| **Tables and columns** | `population`, `stations`, `station_candidates` (for M1). `corridors`: `scenario`, `corridor_id`, `edge_ids`, `rank`. `edges`: `edge_id`, `length_m`. Sum `edges.length_m` for edges in the top-k corridors, then divide M1 by that sum in km. |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`) for display. Corridor length is already partially computed in `app.py` (`corridor_km`). |
| **Status** | **Needs new code.** The corridor-km metric exists in `app.py` but newly served population (M1) is not yet computed. Once M1 is available, the ratio M1 / corridor-km gives M6. |

---

### R9: Demand per newly served person metric (M11)

| Field | Value |
|-------|-------|
| **Description** | Display the increase in total synthetic trips under the active scenario compared to `baseline`, divided by the newly served population (M1). This shows how many additional trips each newly served person generates. Show in the scenario comparison table. Not defined for `baseline`. |
| **Tables and columns** | `routes`: `scenario`, `trip_count`. Sum `trip_count` for the active scenario and for `baseline`, take the difference. Divide by M1. |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`) for display. |
| **Status** | **Needs new code.** Trip sums per scenario are already computed in the comparison table. The newly served population (M1) is not yet available. Once M1 is computed, M11 is a simple ratio. |

---

### R10: Top-k corridor overlap metric (M14)

| Field | Value |
|-------|-------|
| **Description** | Display the pairwise Jaccard overlap between the top-k directed edge sets across scenarios (M14 in `docs/evaluation_metrics.md`). This is a number between 0 and 1 showing how much the top recommendations agree. Compare scenarios at the edge level using edge sets extracted from top-k `edge_scores` or unique `edge_ids` of top-k corridors; do not join on `corridor_id` across scenarios. Show in the scenario comparison area. |
| **Tables and columns** | `edge_scores`: `scenario`, `edge_id`, `rank`. Or `corridors`: `scenario`, `corridor_id`, `edge_ids`, `rank`. For each scenario, collect the set of `edge_id` values where `rank` is between 1 and k. Compute the Jaccard similarity (intersection size divided by union size). |
| **Module** | Scenarios (`src/bubi/scenarios/runner.py`, or calculated in dashboard). Dashboard displays the result. |
| **Status** | **Available in scenario module; needs dashboard wiring.** `build_scenario_comparison_view` in `src/bubi/scenarios/runner.py` provides edge-level scenario presence and ranks. Calculating pairwise Jaccard overlap across the three scenarios and displaying it in the comparison area needs dashboard wiring. |

---

### R11: D5 synthetic-data label on every relevant view

| Field | Value |
|-------|-------|
| **Description** | The D5 warning badge ("Synthetic demo data (D5)") must be visible on every screen that shows synthetic trips, routes, corridor rankings or scenario-comparison results. This includes: the main map when synthetic routes or corridors are shown, the scenario comparison area, the metrics bar, and the detail panel. The label is already shown in the top-right corner of the page and persists across all views. If observed routes are loaded alongside synthetic ones, the badge text changes to "Synthetic + observed routes". |
| **Tables and columns** | `routes`: `route_type` (checked for whether the value is `synthetic` or `observed`). |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`) |
| **Status** | **Available now.** The D5 badge is implemented. It reads `routes.route_type` and displays the appropriate label. No changes needed unless new views are added outside the current page. |

---

### R12: Scenario comparison table with absolute and per-person numbers

| Field | Value |
|-------|-------|
| **Description** | The scenario comparison area (wireframe Area 8) shows a table with one row per scenario. Columns include: scenario name, proposed station count, corridor count, synthetic trips (absolute), newly served population (M1, absolute), population per km of corridor (M6), demand per newly served person (M11), and robust corridor share (M13). For `baseline`, M1 is 0 and M6, M11 and M13 are not applicable (show a dash). Robust corridor share (M13) is evaluated across scenarios at the edge level using the share of top-k edges present in all three scenarios per `docs/evaluation_metrics.md` section 2, without joining on `corridor_id`. |
| **Tables and columns** | `station_candidates`: `scenario`, `rank` (count non-null ranks). `corridors`: `scenario`, `corridor_id`, `rank`. `routes`: `scenario`, `trip_count`. `population`, `stations`, `station_candidates` (for M1). `edges`: `edge_id`, `length_m` (for M6). `edge_scores`: `scenario`, `edge_id`, `rank` (for M13 edge-level robustness). |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`, function `render_scenario_comparison`). |
| **Status** | **Needs new code.** The current comparison table shows proposed stations, corridors and synthetic trips. Adding M1, M6, M11 and M13 requires implementing the metric calculations (see R7, R8, R9, R10) and adding columns to the table in `render_scenario_comparison`. |

---

### R13: Scenario comparison small maps with difference colouring

| Field | Value |
|-------|-------|
| **Description** | The three small maps in the scenario comparison area (wireframe Area 8) should reflect the difference toggle (R2). When it is on, the `lane_aware` and `population_only` maps colour network segments by their robustness label (R6): one colour for robust (suggested: solid blue), another for station-dependent (suggested: dashed orange). Robustness is classified at the edge level first, with geometries drawn using `edges.geometry` mapped by `edge_id` (or corridors coloured by their aggregated edge robustness; do not join on `corridor_id` across scenarios). The `baseline` map shows corridors in their default colour. |
| **Tables and columns** | `edge_scores`: `scenario`, `edge_id`, `rank`. `corridors`: `scenario`, `corridor_id`, `edge_ids`, `rank`. `edges`: `edge_id`, `geometry`. The robustness classification from `build_scenario_comparison_view`. |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`, function `render_scenario_comparison`). |
| **Status** | **Needs new code.** The three small maps are drawn but do not distinguish robust from station-dependent segments. Requires consuming the output of `build_scenario_comparison_view` (R6). |

---

### R14: Corridor detail panel with robustness label

| Field | Value |
|-------|-------|
| **Description** | When a user clicks a corridor on the main map, the detail panel under the map (wireframe Area 7) shows: corridor ID, rank, score, the edges in the corridor, the scenario, and the robustness label (robust or station-dependent, determined from edge-level classifications per R6 without joining on `corridor_id` across scenarios). If the score breakdown is available (volume, gap length, continuity factor), show those too. |
| **Tables and columns** | `corridors`: `scenario`, `corridor_id`, `edge_ids`, `score`, `rank`. `edge_scores`: `scenario`, `edge_id`, `volume`, `score`, `rank`. `edges`: `edge_id`, `length_m`. The robustness classification from `build_scenario_comparison_view`. |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`, function `render_detail_panel`). |
| **Status** | **Needs new code.** The detail panel currently shows only the clicked tooltip text. The full score breakdown and robustness label are planned for Week 4 (score breakdown) and Week 5 (robustness label). |

---

## 3. Implementation dependencies

The following diagram shows which requirements depend on which code:

```
build_scenario_comparison_view (src/bubi/scenarios/runner.py)
  -- implemented; evaluates at edge level and groups corridors by shared edge_ids --
  Produces: edge-level and corridor robustness classification, per-scenario ranks
  Required by: R5, R6, R10, R13, R14

Newly served population calculation (new function, location TBD)
  Produces: M1 count per scenario
  Required by: R4, R7, R8, R9, R12

Dashboard wiring (src/bubi/dashboard/app.py)
  Enable difference toggle: R2
  Add difference layers: R3, R4, R5 (R5 joins edge_scores on edge_id, drawn with edges.geometry)
  Add metrics to comparison table: R12 (M13 uses top-k edge_id overlap)
  Add robustness colouring to small maps: R13
  Add score breakdown and robustness label to detail panel: R14
```

---

## 4. Checklist for CS4 (dashboard owner)

Use this checklist to track progress. Each item maps to a requirement above.

- [ ] R1: Scenario selector works (already done)
- [ ] R2: Enable the "Show difference vs baseline" checkbox
- [ ] R3: Colour proposed stations distinctly in difference mode
- [ ] R4: Shade newly served H3 cells in difference mode
- [ ] R5: Colour edges by rank change in difference mode (match on edge_id, draw with edges.geometry)
- [ ] R6: Show robust / station-dependent labels on edges and corridors (classified at edge level via edge_scores / build_scenario_comparison_view)
- [ ] R7: Show newly served population (M1) in the metrics bar
- [ ] R8: Show population per km of corridor (M6) in the metrics bar
- [ ] R9: Show demand per newly served person (M11) in the comparison table
- [ ] R10: Show top-k corridor/edge overlap (M14) in the comparison area (using top-k edge sets)
- [ ] R11: Confirm D5 badge is visible on all views (already done)
- [ ] R12: Add M1, M6, M11, M13 columns to the scenario comparison table (M13 computed on edge sets)
- [ ] R13: Colour edges and corridors in the small maps by robustness (using edge-level classification)
- [ ] R14: Show full score breakdown and edge/corridor robustness labels in the detail panel

---

## 5. Checklist for Data Science (scenario comparison owner)

- [x] Implement `build_scenario_comparison_view` in `src/bubi/scenarios/runner.py` (implemented; compares at edge level and groups corridors by shared edge_ids)
- [ ] Confirm corridor-level robustness rule (grouping corridors by shared edge_ids per build_scenario_comparison_view) with reviewer (oguzzkd)
- [ ] Implement `run_all_scenarios` in `src/bubi/scenarios/runner.py`
- [ ] Implement newly served population calculation (M1)
- [ ] Provide the edge-level robustness classification and Jaccard overlap to the dashboard

---

## References

- Technical design: `bubi-technical-design.md`, sections 6.7, 7.3, 9.1, 13.2
- Dashboard wireframe: `src/bubi/dashboard/WIREFRAME.md`
- Dashboard code: `src/bubi/dashboard/app.py`
- Data dictionary: `docs/data_dictionary.md`
- Contract schemas: `src/bubi/contracts/schemas.py`
- Evaluation metrics spec: `docs/evaluation_metrics.md` (issue #18)
- Demo storyboard: `docs/demo_storyboard.md` (this issue, #34)
- Scenario runner stub: `src/bubi/scenarios/runner.py`
