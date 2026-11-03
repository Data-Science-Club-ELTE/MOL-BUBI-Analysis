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

---

## 5. Week 2: Baseline Map for All of Budapest

The main map opens zoomed to every station and street, and draws the whole street network coloured
by lane status per direction.

### How the street layer is drawn

| What | How |
|---|---|
| One layer | `lane_status_geojson()` turns the `edges` table into one GeoJSON FeatureCollection with two MultiLineString features: `{"lane": "yes"}` and `{"lane": "no"}`. `LaneStatusLayer` adds it to the map as a single `L.geoJson` layer. Week 1 drew one Folium `PolyLine` per edge. |
| Per direction | Each directed edge is shifted 4 m to the right of travel (`shift_right()`), so a two-way street shows two lines. Green: that direction has a dedicated lane. Grey: it has none. |
| Colours | A JavaScript style function picks the colour in the browser, so the page carries no per-edge style data. |
| Size | Geometries are simplified to 1 m and coordinates rounded to 5 decimals (about 1 m). |
| Drawing | The map uses Leaflet's canvas renderer (`prefer_canvas=True`). The street layer ignores the mouse; checking every line on each mouse move makes the map lag. |
| Caching | The layer is built once per data version (`st.cache_resource`) and reused on every rerun. |

Existing stations are also one GeoJSON layer instead of one marker each. Hovering a station still
shows its name and ID, and clicking it fills the "Selected recommendation" panel.

### Legend

A legend in the bottom-right corner of the map lists only the layers that are switched on, and
explains that each direction of a street is drawn on its own side.

### Proposed stations

Proposed-station markers sit on the centre of their H3 cell (`h3.cell_to_latlng`).

### Scenario comparison maps

The three small maps leave out the street layer, so the city network is drawn once per page instead
of four times. They still show stations, proposed stations and corridors.

### Load time

The main map shows a caption with the number of street edges and the server time to prepare the
map. To time the server-side steps without opening the app:

```bash
make measure-dashboard                                                   # synthetic network, 200,000 edges
make measure-dashboard MEASURE_ARGS="--edges data/processed/edges.parquet"   # real network, once merged
```

The real Budapest network was not in the repository yet, so the numbers below come from a
synthetic network spread over Budapest (`synthetic_edges()` in the script) and the 704 real
stations in `data/processed/stations.parquet`. They were taken on a 2-CPU cloud machine with
headless Chromium and no map tiles. A laptop is likely faster.

| Directed edges | Build street layer (once) | Page size | Browser: first open | Browser: later opens |
|---:|---:|---:|---:|---:|
| 100,000 | 1.2 s | 7.8 MB | 8.6 s | 4.7–5.0 s |
| 200,000 | 2.4 s | 15.5 MB | 13.7 s | 7.2–7.5 s |
| 300,000 | 3.5 s | 23.3 MB | 17.6 s | 10.3–11.3 s |

"Browser" is the time from opening the page until the main map is drawn. The first open after
starting the app includes loading the tables and building the street layer. On reruns (changing a
setting) the server prepares the map in about 0.02 s.

For comparison, week 1's one-line-per-edge map took 15.6 s on the server and produced an 18.6 MB
page for only 20,000 edges.

### Known limits

- The street layer has no hover tooltip; the legend explains the colours. Corridors keep their
  tooltips with edge ID, rank and score.
- Routes, corridors and population cells are still drawn one object each. That is fine for the top
  corridors, but the routes and population layers may need the same treatment at city scale.
