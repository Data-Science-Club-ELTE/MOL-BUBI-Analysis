# Module: Interactive Dashboard (`src/bubi/dashboard`)

**Owner**: CS 4  
**Collaborators**: BA / Data Analysis (Visual story & user testing), Geoinformatics MSc (Map layers)

---

## 1. Objective

1. Build an interactive Streamlit application with Folium maps.
2. Provide layer toggles:
   - Existing stations (BKK Futár snapshot).
   - Proposed expansion stations (`lane_aware` and `population_only`).
   - Street network with per-direction bike lane status (green = dedicated lane, gray = missing lane).
   - High-priority recommended corridors highlighted in bold red/amber.
3. Provide scenario switcher (`baseline`, `lane_aware`, `population_only`).
4. Display summary metrics (demand, served population, corridor km).
5. Enable export of GeoJSON and CSV files for decision-makers.

---

## 2. Data Contracts

The dashboard consumes pre-computed Parquet tables directly from `data/processed/` (or falls back seamlessly to `tests/fixtures/` during development):
- `stations.parquet` (`StationsSchema`)
- `edges.parquet` (`EdgesSchema`)
- `station_candidates.parquet` (`StationCandidatesSchema`)
- `corridors.parquet` (`CorridorsSchema`)
- `edge_scores.parquet` (`EdgeScoresSchema`)

---

## 3. How to Develop Independently

The dashboard works immediately out of the box using `tests/fixtures/`:

1. Launch local dev server:
   ```bash
   make dashboard
   # or
   streamlit run src/bubi/dashboard/app.py
   ```
2. Modify UI layout, tooltips, popups, and color maps in `src/bubi/dashboard/app.py`.
3. Test exporting CSV and GeoJSON files.

---

## 4. Week 1 Skeleton

| File | Purpose |
|---|---|
| `WIREFRAME.md`, `wireframe.svg` | Layout plan, numbered areas, open review questions and the review feedback log |
| `data.py` | Loads and validates every contract table; turns missing, invalid or unreadable files into a `DashboardDataError` with a plain-language message |
| `app.py` | Streamlit page following the wireframe: scenario selector, layer toggles, run parameters, metrics, map, detail panel, scenario comparison placeholder, tables and CSV export |

**Data source.** The app reads `data/processed/` if `stations.parquet` exists there, otherwise
`tests/fixtures/`. The two are never mixed. Set `BUBI_DATA_DIR=/some/folder` to point it at
another folder (the tests use this).

**Error handling.** If `stations` or `edges` is missing or invalid, the app shows a red error box
naming the table and file and stops. If an optional table (`population`, `station_candidates`,
`edge_scores`, `corridors`, `routes`) is missing or invalid, the app shows a warning and switches
off the layers that use it.

**Basemap.** OpenStreetMap tiles, because CartoDB basemaps now require an API key.

**Known fixture issue.** The H3 cell ids in `scripts/generate_fixtures.py` decode to southern
Poland (about 50.3° N, 21.0° E), not Budapest, so proposed stations and population cells from the
fixtures are skipped and the app says so under the map. Budapest cells at resolution 9 start with
`891e037…` (e.g. `891e037aacfffff`, Deák Ferenc tér).

**Tests.** `tests/test_dashboard.py` covers loading, error messages and a headless run of the app
for every scenario (`make test`).
