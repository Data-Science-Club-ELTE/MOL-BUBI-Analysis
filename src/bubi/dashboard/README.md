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

The dashboard consumes pre-computed Parquet tables from `data/processed/`. Any table the pipeline has not produced yet is read from `tests/fixtures/` instead:
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
| `WIREFRAME.md`, `wireframe.svg` | Layout plan, numbered areas and the review feedback log |
| `data.py` | Loads and validates every contract table; turns missing, invalid or unreadable files into a `DashboardDataError` with a plain-language message |
| `app.py` | Streamlit page following the wireframe: scenario selector, basemap choice, layer toggles, run parameters, metrics, full-width map, detail panel under the map, one small map per scenario, tables and CSV export |

**Data source.** Each table is read from `data/processed/<table>.parquet` if it exists, otherwise
from `tests/fixtures/sample_<table>.parquet`. Every table read from test data is listed in the notes
under the map, and the data-mode badge says "pipeline outputs + sample fixtures" when the two are
mixed. Set `BUBI_DATA_DIR=/some/folder` to read every table from one folder instead (the tests use
this).

**Error handling.** If `stations` or `edges` is missing or invalid, the app shows a red error box
naming the table and file and stops. If an optional table (`population`, `station_candidates`,
`edge_scores`, `corridors`, `routes`) is missing or invalid, the app shows a warning and switches
off the layers that use it.

**Basemap.** OpenStreetMap by default. The sidebar also offers Esri's light grey canvas, which
makes the lane colours easier to read on a projector. Neither needs an API key (CartoDB basemaps now
do).

**Proposed stations.** Only candidates with a `rank` are drawn and counted; candidates with an
empty rank were not selected.

**Tests.** `tests/test_dashboard.py` covers loading, error messages and a headless run of the app
for every scenario (`make test`).
