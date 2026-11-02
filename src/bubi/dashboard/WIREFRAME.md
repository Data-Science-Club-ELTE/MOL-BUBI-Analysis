# Dashboard Wireframe (Week 1)

Issue: #8 · Module: `src/bubi/dashboard` · Owner: CS 4

![Dashboard wireframe](wireframe.svg)

The wireframe follows section 6.7 and the demo storyline in section 9 of the technical
design. All numbers on it are placeholders.

## Areas

| # | Area | What it shows | Data source | Week |
|---|------|---------------|-------------|------|
| 1 | Data-mode badge | Always visible label that results are synthetic (decision D5), and whether the app reads `data/processed/` or `tests/fixtures/` | app state | 1 |
| 2 | Scenario selector | `baseline`, `lane_aware`, `population_only`, plus a "difference vs baseline" toggle | config `scenarios.active` | 1 (selector), 5 (difference) |
| 3 | Map layers | Basemap choice (OpenStreetMap or a light grey keyless basemap), existing stations, proposed stations, population (H3), per-direction bike-lane coverage, synthetic routes, top corridors; slider for how many corridors to show | `stations`, `station_candidates`, `population`, `edges`, `routes`, `corridors` | 1 (stations, edges, population, corridors), 3 (routes) |
| 4 | Exports | Corridors and stations as GeoJSON and CSV | `corridors` + `edges`, `stations` + `station_candidates` | 1 (CSV), 5 (GeoJSON) |
| 5 | Key metrics | Station count, newly served population, km of new corridor needed, synthetic trip count | scenario outputs | 1 (counts), 5 (served population, km) |
| 6 | **Main map area** | Folium map. Lanes drawn per direction: green = lane in that direction, grey = none, orange = priority gap. Tooltip shows rank, direction, volume, lane status | `edges`, `edge_scores`, `corridors` | 1 |
| 7 | Selected recommendation | Under the map, so the map gets the full width. Score breakdown for the clicked corridor or station (traceability check in section 9): volume, gap length, continuity factor, rank, scenario, robustness label | `edge_scores`, `corridors`, `station_candidates` | 4 |
| 8 | **Scenario comparison space** | One small map for each of the three scenarios, always visible, demand in absolute terms and per newly served person, newly served people per km of new corridor, robust vs station-dependent corridors (section 7.3) | derived view over `edge_scores` | 1 (maps, counts), 5 (metrics) |
| 9 | Tables | Tabs for top corridors, station candidates, methodology and limitations (section 13.2) | `corridors`, `station_candidates` | 1 (tables), 6 (methodology) |

## Interaction flow

1. Pick a scenario in the sidebar; map, metrics and tables update.
2. Turn layers on and off to compare bike-lane coverage with high-use corridors.
3. Click a corridor or station on the map to see its score breakdown in the panel under the map.
4. Scroll down to compare scenarios and see which corridors are robust.
5. Export the current scenario's recommendations.

## Review feedback

| Date | Reviewer | Feedback | Decision |
|------|----------|----------|----------|
| 2026-10-18 | oguzzkd | The third scenario map should always be visible. | All three scenario maps are always shown side by side in the scenario comparison area. |
| 2026-10-18 | oguzzkd | Put the detail panel under the map; map width matters more. | "Selected recommendation" moved under the map; the map uses the full page width. |
| 2026-10-18 | oguzzkd | OpenStreetMap is good; add a keyless basemap option that shows the lanes more clearly. | OpenStreetMap stays the default. The sidebar adds "Light grey (Esri)", which needs no API key. |
| 2026-10-18 | oguzzkd | The fixture H3 cells are fixed; remove the cell filtering. | Study-area filtering removed. Only cells with an invalid H3 id are skipped, with a note. |
| 2026-10-18 | oguzzkd | When the app reads test data instead of real data, add it to the notes. | Each table is read from `data/processed/` when it exists, otherwise from `tests/fixtures/`. Every table read from test data is listed in the notes under the map. |
