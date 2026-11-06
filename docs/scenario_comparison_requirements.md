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

### R5: Corridors with changed rank layer (difference)

| Field | Value |
|-------|-------|
| **Description** | When the difference toggle is on, highlight corridors whose rank changed compared to `baseline`. Colour corridors that improved (lower rank number, meaning higher priority) in one colour (suggested: green) and corridors that worsened (higher rank number) in another (suggested: red). Corridors that are new (not in the baseline top-k) are marked as "new corridor". |
| **Tables and columns** | `corridors`: `scenario`, `corridor_id`, `edge_ids`, `score`, `rank`. Join `baseline` rows to `lane_aware` or `population_only` rows on `corridor_id` to compute rank differences. `edges`: `edge_id`, `geometry` (to draw the corridor on the map). |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`) for the map layer. The rank-comparison logic can be computed in the dashboard or in `build_scenario_comparison_view` in `src/bubi/scenarios/runner.py`. |
| **Status** | **Needs new code.** The corridor layer exists but does not compare ranks across scenarios. `build_scenario_comparison_view` in `src/bubi/scenarios/runner.py` is a stub (raises `NotImplementedError`). |

---

### R6: Robust vs station-dependent corridor labels

| Field | Value |
|-------|-------|
| **Description** | Each corridor in the top-k (k = 10) is labelled as either "robust" or "station-dependent". A corridor is robust if it appears in the top-10 in all three scenarios (`baseline`, `lane_aware`, `population_only`). A corridor is station-dependent if it appears in the top-10 of at least one scenario but not all three (design doc section 7.3, metric M13 in `docs/evaluation_metrics.md`). The label is shown in the corridor tooltip on the map, in the detail panel (wireframe Area 7), and in the corridors table (wireframe Area 9). |
| **Tables and columns** | `corridors`: `scenario`, `corridor_id`, `rank`. For each corridor, check whether `rank` is between 1 and 10 (inclusive) in all three scenarios. Alternatively, `edge_scores`: `scenario`, `edge_id`, `rank` can be used for edge-level classification. |
| **Module** | Scenarios (`src/bubi/scenarios/runner.py`, function `build_scenario_comparison_view`). Dashboard (`src/bubi/dashboard/app.py`) displays the label. |
| **Status** | **Needs new code.** `build_scenario_comparison_view` in `src/bubi/scenarios/runner.py` is a stub. It should accept `df_edge_scores`, `df_corridors`, and `top_k` (default 10) and return a DataFrame with corridor IDs, their scenario membership, and the robust/station-dependent classification. |

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
| **Description** | Display the pairwise Jaccard overlap between the edge sets of the top-k corridors across scenarios. This is a number between 0 and 1 showing how much the top corridors agree. Show in the scenario comparison area. |
| **Tables and columns** | `corridors`: `scenario`, `corridor_id`, `edge_ids`, `rank`. Or equivalently, `edge_scores`: `scenario`, `edge_id`, `rank`. For each scenario, collect the set of `edge_id` values where `rank` is between 1 and k. Compute the Jaccard similarity (intersection size divided by union size). |
| **Module** | Scenarios (`src/bubi/scenarios/runner.py`, inside `build_scenario_comparison_view`). Dashboard displays the result. |
| **Status** | **Needs new code.** `build_scenario_comparison_view` is a stub. The Jaccard calculation is straightforward once the function is implemented. |

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
| **Description** | The scenario comparison area (wireframe Area 8) shows a table with one row per scenario. Columns include: scenario name, proposed station count, corridor count, synthetic trips (absolute), newly served population (M1, absolute), population per km of corridor (M6), demand per newly served person (M11), and robust corridor share (M13). For `baseline`, M1 is 0 and M6, M11 and M13 are not applicable (show a dash). |
| **Tables and columns** | `station_candidates`: `scenario`, `rank` (count non-null ranks). `corridors`: `scenario`, `corridor_id`, `rank`. `routes`: `scenario`, `trip_count`. `population`, `stations`, `station_candidates` (for M1). `edges`: `edge_id`, `length_m` (for M6). |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`, function `render_scenario_comparison`). |
| **Status** | **Needs new code.** The current comparison table shows proposed stations, corridors and synthetic trips. Adding M1, M6, M11 and M13 requires implementing the metric calculations (see R7, R8, R9, R10) and adding columns to the table in `render_scenario_comparison`. |

---

### R13: Scenario comparison small maps with difference colouring

| Field | Value |
|-------|-------|
| **Description** | The three small maps in the scenario comparison area (wireframe Area 8) should reflect the difference toggle (R2). When it is on, the `lane_aware` and `population_only` maps colour corridors by their robustness label (R6): one colour for robust (suggested: solid blue), another for station-dependent (suggested: dashed orange). The `baseline` map shows corridors in their default colour. |
| **Tables and columns** | `corridors`: `scenario`, `corridor_id`, `edge_ids`, `rank`. The robustness classification from `build_scenario_comparison_view`. `edges`: `edge_id`, `geometry`. |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`, function `render_scenario_comparison`). |
| **Status** | **Needs new code.** The three small maps are drawn but do not distinguish robust from station-dependent corridors. Requires the output of `build_scenario_comparison_view` (R6). |

---

### R14: Corridor detail panel with robustness label

| Field | Value |
|-------|-------|
| **Description** | When a user clicks a corridor on the main map, the detail panel under the map (wireframe Area 7) shows: corridor ID, rank, score, the edges in the corridor, the scenario, and the robustness label (robust or station-dependent). If the score breakdown is available (volume, gap length, continuity factor), show those too. |
| **Tables and columns** | `corridors`: `scenario`, `corridor_id`, `edge_ids`, `score`, `rank`. `edge_scores`: `scenario`, `edge_id`, `volume`, `score`, `rank`. The robustness classification from `build_scenario_comparison_view`. |
| **Module** | Dashboard (`src/bubi/dashboard/app.py`, function `render_detail_panel`). |
| **Status** | **Needs new code.** The detail panel currently shows only the clicked tooltip text. The full score breakdown and robustness label are planned for Week 4 (score breakdown) and Week 5 (robustness label). |

---

## 3. Implementation dependencies

The following diagram shows which requirements depend on which code:

```
build_scenario_comparison_view (src/bubi/scenarios/runner.py)
  -- currently raises NotImplementedError --
  Produces: robustness classification, Jaccard overlap
  Required by: R5, R6, R10, R13, R14

Newly served population calculation (new function, location TBD)
  Produces: M1 count per scenario
  Required by: R4, R7, R8, R9, R12

Dashboard wiring (src/bubi/dashboard/app.py)
  Enable difference toggle: R2
  Add difference layers: R3, R4, R5
  Add metrics to comparison table: R12
  Add robustness colouring to small maps: R13
  Add score breakdown and label to detail panel: R14
```

---

## 4. Checklist for CS4 (dashboard owner)

Use this checklist to track progress. Each item maps to a requirement above.

- [ ] R1: Scenario selector works (already done)
- [ ] R2: Enable the "Show difference vs baseline" checkbox
- [ ] R3: Colour proposed stations distinctly in difference mode
- [ ] R4: Shade newly served H3 cells in difference mode
- [ ] R5: Colour corridors by rank change in difference mode
- [ ] R6: Show robust / station-dependent label on corridors (needs `build_scenario_comparison_view` from Data Science)
- [ ] R7: Show newly served population (M1) in the metrics bar
- [ ] R8: Show population per km of corridor (M6) in the metrics bar
- [ ] R9: Show demand per newly served person (M11) in the comparison table
- [ ] R10: Show top-k corridor overlap (M14) in the comparison area (needs `build_scenario_comparison_view`)
- [ ] R11: Confirm D5 badge is visible on all views (already done)
- [ ] R12: Add M1, M6, M11, M13 columns to the scenario comparison table
- [ ] R13: Colour corridors in the small maps by robustness (needs `build_scenario_comparison_view`)
- [ ] R14: Show full score breakdown and robustness label in the detail panel

---

## 5. Checklist for Data Science (scenario comparison owner)

- [ ] Implement `build_scenario_comparison_view` in `src/bubi/scenarios/runner.py`
- [ ] Implement `run_all_scenarios` in `src/bubi/scenarios/runner.py`
- [ ] Implement newly served population calculation (M1)
- [ ] Provide the robustness classification and Jaccard overlap to the dashboard

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
