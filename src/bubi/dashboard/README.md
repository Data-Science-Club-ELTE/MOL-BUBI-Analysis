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
