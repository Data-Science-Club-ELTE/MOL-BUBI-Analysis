# MOL Bubi Bike-Lane & Station Recommendation Tool

An interactive, data-driven decision support tool recommending prioritized bike-lane corridors and expansion stations in Budapest based on network connectivity, topography, and population demand.

---

## 1. Quick Start

### Prerequisites
- Python >= 3.10
- [`uv`](https://docs.astral.sh/uv/) installed on your machine.

### Installation & Environment Setup
```bash
# Clone the repository
git clone <repo-url>
cd scaffold

# Create virtual environment and install all dependencies in editable mode
make install
# or directly:
uv venv .venv
uv pip install -e ".[dev]"

# Generate mock data fixtures (Budapest Belváros sample)
make fixtures

# Run contract tests to verify environment
make test

# Launch the interactive Streamlit dashboard
make dashboard
```

---

## 2. Team Architecture & Module Ownership

Modules are designed to be **completely independent**. Each module has its own `README.md` with input/output contracts and sample fixtures under `tests/fixtures/`. You do **not** need to wait for upstream pipelines to write and test your logic.

| Module | Subpackage | Owner | Core Deliverable |
|---|---|---|---|
| **Station Ingestion** | `src/bubi/ingestion/` | CS 1 | BKK Futár station snapshot + real GPS route conversion |
| **Network & Lanes** | `src/bubi/network/` | Geoinformatics MSc | OSMnx street/walk graphs, per-direction lane tags, slope integration |
| **Population** | `src/bubi/population/` | CS 5 & Geoinformatics MSc | WorldPop/GHSL raster to H3 res-9 grid aggregation |
| **Demand Generator** | `src/bubi/demand/` | Data Science MSc | Gravity-style trip generation $P_i \times P_j \times f(d_{ij})$ |
| **Routing Engine** | `src/bubi/routing/` | CS 2 | Slope-aware routing with bridge/tunnel slope interpolation |
| **Corridor Scoring** | `src/bubi/corridors/` | CS 3 & Data Science MSc | Per-direction gap detection, volume aggregation, corridor ranking |
| **Station Scoring** | `src/bubi/stations/` | CS 5 & Data Science MSc | Station candidate filtering, lane connectivity, product scoring |
| **Scenario Runner** | `src/bubi/scenarios/` | CS 5 & Data Science MSc | Tri-scenario execution (`baseline`, `lane_aware`, `population_only`) |
| **Dashboard** | `src/bubi/dashboard/` | CS 4 & BA / Data Analysis | Streamlit + Folium interactive map & scenario comparison |
| **Data Profiling** | `src/bubi/profiling/` | BA / Data Science & BA / DA | Profiling reports, data dictionary, traceability check |

---

## 3. Data Contracts

All data passing between modules is strictly validated using [Pandera](https://pandera.readthedocs.io/) schemas defined in `src/bubi/contracts/schemas.py`:

1. `stations`: `station_id`, `name`, `lat`, `lon`
2. `population`: `cell_id` (H3 res 9), `population`
3. `edges`: `edge_id` (`u-v-key`), `osm_way_id`, `length_m`, `has_dedicated_lane`, `geometry` (LineString)
4. `station_candidates`: `scenario`, `cell_id`, `population`, `lane_connectivity`, `score`, `rank`
5. `routes`: `scenario`, `start_station_id`, `end_station_id`, `route_type`, `edges`, `trip_count`
6. `edge_scores`: `scenario`, `edge_id`, `volume`, `score`, `rank`
7. `corridors`: `scenario`, `corridor_id`, `edge_ids`, `score`, `rank`

---

## 4. How to Work in Isolation

1. Check your assigned module's `README.md` (e.g. `src/bubi/routing/README.md`).
2. Load mock fixtures from `tests/fixtures/` using `bubi.contracts.io.load_contract_table`.
3. Implement your core function inside the module stub.
4. Validate your outputs against the contract schema:
   ```python
   from bubi.contracts.schemas import RoutesSchema

   RoutesSchema.validate(df_result)
   ```
5. Run your module test:
   ```bash
   pytest tests/test_modules_mock.py
   ```
6. Format and lint before submitting a PR:
   ```bash
   make lint
   ```

The standalone routing prototype and its lightweight Parquet reader live under
`src/bubi/prototype/`, separate from the application modules to avoid package
name collisions while keeping both available in the installed project.
