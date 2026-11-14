# Demo Storyboard

Issue: #34 · Owner: Aizirek Muradylova (BA / Data Analysis)
Version: 1.0 (Week 3) · Status: Ready for team review

This document plans the final project demo as a six-step narrative. It follows
section 9.1 of the technical design document and lists exactly what appears on
screen at each step, what the presenter says, and what still needs to be built.

The dashboard is `src/bubi/dashboard/app.py`, run with `make dashboard`.
The wireframe layout is documented in `src/bubi/dashboard/WIREFRAME.md`.

Metric IDs (M1, M6, M11, M13, M14) and the top-k = 10 default are defined in
`docs/evaluation_metrics.md` (issue #18, branch `feature/18-metrics-specification`).

Audience: teammates and professors. No GIS expertise is assumed.

---

## Step 1: Current stations and routes

| Item | Detail |
|------|--------|
| **Title** | "704 stations across Budapest" |
| **On screen** | Main map (wireframe Area 6). Layers on: Existing stations, Bike-lane coverage, Synthetic routes. Scenario selector set to `baseline`. The D5 badge (Area 1) reads "Synthetic demo data (D5)". Key metrics bar (Area 5) shows station count and synthetic trip count. |
| **User action** | Open the dashboard. In the sidebar, set scenario to `baseline`, turn on "Existing stations", "Bike-lane coverage" and "Synthetic routes". |
| **Presenter says** | "This map shows all 704 MOL Bubi docking stations, the street network coloured by whether each direction has a dedicated bike lane, and the synthetic trip routes our gravity model generates between them." |
| **D5 label visible** | Yes. Synthetic routes and trip counts are displayed. |
| **Dashboard status** | **Exists today.** The scenario selector, existing-station layer, bike-lane-coverage layer and synthetic-routes layer are implemented in `app.py`. The D5 badge is shown in the top-right corner. Key metrics (station count, synthetic trips) are displayed. |

---

## Step 2: Lane coverage against high-use corridors

| Item | Detail |
|------|--------|
| **Title** | "Where cyclists ride versus where lanes exist" |
| **On screen** | Same main map. Layers on: Bike-lane coverage, Top corridors. The lane layer shows green (lane in that direction) and grey (no lane). Top corridors are highlighted. The "Top corridors to show" slider is set to 10. |
| **User action** | Turn off "Existing stations" and "Synthetic routes". Turn on "Top corridors". Set the corridor slider to 10. |
| **Presenter says** | "Green lines are directions with a dedicated bike lane; grey lines have none, and the highlighted corridors are the top-10 street segments where our model predicts high use but no lane exists." |
| **D5 label visible** | Yes. Corridor rankings are derived from synthetic route volumes. |
| **Dashboard status** | **Exists today.** The bike-lane-coverage layer (per-direction green/grey), the top-corridors layer and the corridor slider are implemented. |

---

## Step 3: Top corridors and station candidate scores

| Item | Detail |
|------|--------|
| **Title** | "How we score corridors and station candidates" |
| **On screen** | Main map with Top corridors and Proposed stations on. Scenario selector set to `lane_aware`. The detail panel under the map (wireframe Area 7) shows the score breakdown for the clicked corridor or station. The tables area (Area 9, tab "Top corridors") lists corridors sorted by rank. |
| **User action** | Switch scenario to `lane_aware`. Turn on "Proposed stations". Click a top corridor on the map to see its score breakdown in the detail panel. Scroll down to the "Top corridors" table tab. |
| **Presenter says** | "Each corridor is scored by route volume times gap length times a continuity factor, and each station candidate by population times lane connectivity; clicking any item shows exactly how its score was computed." |
| **D5 label visible** | Yes. Route volumes feeding corridor scores are synthetic. |
| **Dashboard status** | **Partially exists.** The corridor and proposed-station layers are drawn, and the tables tab works. The detail panel (Area 7) currently shows only the clicked tooltip; the full score breakdown (volume, gap length, continuity factor, rank, robustness label) is planned for Week 4. |

---

## Step 4: Scenario comparison

| Item | Detail |
|------|--------|
| **Title** | "Three scenarios: which corridors are robust?" |
| **On screen** | Scenario comparison area (wireframe Area 8): three small maps side by side, one per scenario (`baseline`, `lane_aware`, `population_only`), each showing existing stations, proposed stations and corridors. Below the maps, a comparison table shows per-scenario numbers: proposed station count, corridor count and synthetic trips. When the "Show difference vs baseline" toggle is on, difference layers highlight new stations, newly served cells and edges whose rank changed vs baseline. Metrics include newly served population (M1), population per km of new corridor (M6), demand per newly served person (M11), and robust corridor share (M13). Robustness is classified at the edge level first: edges and corridors are labelled "robust" (top-10 in all three scenarios) or "station-dependent" (top-10 in fewer than three). |
| **User action** | Scroll down to the "Scenario comparison" section. Turn on "Show difference vs baseline". Read the comparison table and the robust/station-dependent labels on the corridor maps. |
| **Presenter says** | "We compare three scenarios to find corridors that are needed regardless of which stations are built: robust corridors appear in the top-10 of all three scenarios, while station-dependent ones shift with the expansion strategy." |
| **D5 label visible** | Yes. All three scenarios use synthetic trips and routes. |
| **Dashboard status** | **Partially exists.** The three small maps and the basic comparison table (proposed stations, corridors, synthetic trips) are implemented. **Not yet built:** the "Show difference vs baseline" toggle is present but disabled (checkbox in sidebar, labelled "Week 5"); the difference layers (new stations, newly served cells, rank-changed edges); newly served population (M1), population per km (M6), demand per newly served person (M11) and robust corridor share (M13) metrics; edge-level and corridor robust vs station-dependent labels. These depend on `build_scenario_comparison_view` in `src/bubi/scenarios/runner.py` (which classifies at the edge level and groups corridors by shared edges). See `docs/scenario_comparison_requirements.md` for the full specification. |

---

## Step 5: Synthetic-to-real replacement path

| Item | Detail |
|------|--------|
| **Title** | "From synthetic model to real cycling data" |
| **On screen** | The "Methodology and limitations" tab (wireframe Area 9, tab 3). The presenter can also show the architecture diagram from the design document (section 3) if a slide or image is prepared. |
| **User action** | Click the "Methodology and limitations" tab in the tables area. |
| **Presenter says** | "When real trip data and GPS logs arrive, they replace only the trip and route layers; coverage analysis, scoring and the dashboard stay the same, so every recommendation is immediately re-evaluated against observed behaviour." |
| **D5 label visible** | Yes, because the current data is synthetic. The tab text explicitly states that results are synthetic (D5). |
| **Dashboard status** | **Partially exists.** The tab exists and shows a bullet list of limitations. The full methodology appendix text is planned for Week 6. The architecture diagram is in `bubi-technical-design.md` section 3 but is not embedded in the dashboard. If needed, prepare a slide or screenshot of the diagram from the design document. |

---

## Step 6: Limitations

| Item | Detail |
|------|--------|
| **Title** | "What our results can and cannot claim" |
| **On screen** | Same "Methodology and limitations" tab. Key limitations listed: synthetic data is a demonstration, not evidence (D5); demand is population-only with no time-of-day effects (D8); routing ignores traffic and existing lanes (D2); walking distances use straight-line as a lower bound (D15); station scores ignore legal and land-use feasibility (D4); scenario differences partly reflect model assumptions. |
| **User action** | Read through the limitations in the tab. |
| **Presenter says** | "Every limitation is documented: synthetic data is labelled as a demonstration, distances are straight-line lower bounds, and station scores do not account for legal or construction constraints." |
| **D5 label visible** | Yes. The D5 badge remains in the top-right corner throughout. |
| **Dashboard status** | **Partially exists.** The tab shows a summary of key limitations (D5, D8, D2, D4). The full methodology appendix with all limitations from design doc section 13.2 is planned for Week 6. |

---

## Backup plan

If the live dashboard fails during the presentation (network error, data loading
issue, or Streamlit crash), use one or more of these alternatives:

1. **Screenshots.** Before the demo, take a screenshot of each step above and
   save them in a presentation slide deck. Label each screenshot with its step
   number and the presenter sentence.

2. **Screen recording.** Record a short video walkthrough of the six steps. If
   the live demo fails, play the video instead.

3. **Exported tables.** Download the CSV exports (corridors and station
   candidates) from the dashboard beforehand. These can be shown in a
   spreadsheet if the map does not load.

The design document (section 9.2, "Pre-presentation checks") lists the checks
to run before presenting. Complete them the day before the demo.

---

## Summary of build status

| Step | Screen | Status |
|------|--------|--------|
| 1 | Stations, lanes, routes on main map | Exists today |
| 2 | Lane coverage vs top corridors | Exists today |
| 3 | Score breakdown in detail panel | Needs Week 4 work (detail panel) |
| 4 | Scenario comparison with difference layers and metrics | Needs Week 5 work (difference toggle, metrics, robustness labels) |
| 5 | Methodology tab and architecture diagram | Partially exists; full text in Week 6 |
| 6 | Limitations in methodology tab | Partially exists; full text in Week 6 |

---

## References

- Technical design: `bubi-technical-design.md`, sections 6.7, 7.3, 9.1, 13.2
- Dashboard wireframe: `src/bubi/dashboard/WIREFRAME.md`
- Dashboard code: `src/bubi/dashboard/app.py`
- Evaluation metrics spec: `docs/evaluation_metrics.md` (issue #18)
- Scenario comparison requirements: `docs/scenario_comparison_requirements.md` (this issue, #34)
- Scenario runner stub: `src/bubi/scenarios/runner.py`
