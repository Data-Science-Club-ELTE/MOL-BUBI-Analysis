# Module: Ingestion (`src/bubi/ingestion`)

**Owner**: CS 1  
**Collaborators**: Project Leader (BKK API key & data access agreements), BA / Data Science (data dictionary)

---

## 1. Objective

1. **Week 1–2**: Ingest MOL Bubi stations from the BKK Futár API and persist a frozen snapshot as a Parquet table matching `StationsSchema`.
2. **Week 6 (Conditional)**: If real trip / GPS data arrives before the week 4 contract deadline, build the conversion pipeline transforming raw GPS traces into the `RoutesSchema` with `route_type = "observed"`.

---

## 2. Data Contracts

### Output: `stations` table
Parquet file saved to `data/processed/stations.parquet` (tested against `tests/fixtures/sample_stations.parquet`).

| Field | Type | Description |
|---|---|---|
| `station_id` | `str` | Futár station ID as string (e.g., `"futar_001"`) |
| `name` | `str` | Human-readable station name |
| `lat` | `float` | Latitude in EPSG:4326 (WGS84, [47.0, 48.0]) |
| `lon` | `float` | Longitude in EPSG:4326 (WGS84, [18.0, 20.0]) |

---

## 3. How to Develop Independently

You do not need other members' work. Your upstream is the BKK Futár API (or a cached JSON response).

1. Review `src/bubi/ingestion/futar.py`.
2. Test your implementation against mock data:
   ```python
   from bubi.contracts.schemas import StationsSchema
   import pandas as pd

   # Load your output and validate:
   df = pd.read_parquet("tests/fixtures/sample_stations.parquet")
   StationsSchema.validate(df)
   ```
3. Run tests:
   ```bash
   pytest tests/test_contracts.py -k stations
   ```

---

## 4. Definition of Done
- [x] BKK Futár endpoint queried and station list extracted.
- [x] Output table strictly validated by `StationsSchema`.
- [x] Snapshot saved to `data/processed/stations.parquet`.
- [x] Unit test written under `tests/test_ingestion.py`.
- [x] Frozen snapshot date recorded in `config/default_config.yaml` (`stations.snapshot_date`).

---

## 5. Week 1: Raw Futár snapshot (Issue #5)

`src/bubi/ingestion/futar_snapshot.py` fetches the `bicycle-rental` response and stores it **unchanged** under `data/raw/` (git-ignored; share it with the team outside git).
Next to it a `*.meta.json` records the retrieval time, endpoint (without key), HTTP status, station count and SHA-256.

```bash
cp .env.example .env     # put your BKK Futár key into .env (never commit it)
python -m bubi.ingestion.futar_snapshot
pytest tests/test_ingestion.py
```

Station count = `len(response["data"]["list"])`. Acquisition notes: `docs/ingestion_notes.md`.
The normalization into `StationsSchema` (`data/processed/stations.parquet`) is a later step, once the real response structure is known.

## 6. Processed stations table

`src/bubi/ingestion/stations_table.py` converts a raw snapshot into the contract table `data/processed/stations.parquet` (`StationsSchema`: `station_id`, `name`, `lat`, `lon`).

The raw response contains fixed stations and free-floating bikes. Stations are selected in two independent ways and the table is only written if both give exactly the same records:

1. `type == "virtual"`
2. style icon is not `vehicle-rental/mol-bubi-floating`

```bash
python -m bubi.ingestion.stations_table data/raw/futar_bicycle_rental_<stamp>.json
pytest tests/test_stations_table.py
```

## 7. Python interface and frozen snapshot (Issue #19)

`ingest_futar_stations` returns the stations table as a DataFrame validated by `StationsSchema`. It does not write the Parquet file; `stations_table.py` does that.

```python
from pathlib import Path

from bubi.ingestion import ingest_futar_stations

# Offline, from a saved raw response:
df = ingest_futar_stations(raw_path=Path("data/raw/futar_bicycle_rental_20261018T163442Z.json"))

# Online: reads BKK_FUTAR_API_KEY, saves the raw response under data/raw/ first.
df = ingest_futar_stations()
```

It raises `IngestionError` when no API key is found, the response is not HTTP 200, or the two selection rules disagree. On a failed request the raw body and `*.meta.json` are still saved, without the key.

The frozen snapshot is recorded under `stations` in `config/default_config.yaml`: `snapshot_date: "2026-10-18"`, the raw file name and its SHA-256. Offline tests use the synthetic response `tests/fixtures/futar_bicycle_rental_sample.json`.

## 8. Observed routes converter: assumed input format (Issue #24)

No real trip or GPS data has arrived yet. `src/bubi/ingestion/observed_routes.py` converts data in the format below into `routes` rows with `route_type = "observed"` and `scenario = "baseline"`. When real data arrives, compare it with this section first; only the reading side should need to change.

**Trips** (one row per trip):

| Column | Type | Meaning |
|---|---|---|
| `trip_id` | str | Unique trip ID |
| `start_station_id` | str | Futár station `id`, the same IDs as `data/processed/stations.parquet` |
| `end_station_id` | str | Futár station `id` |
| `start_time`, `end_time` | ISO 8601 string | Trip start and end |

**GPS points** (one row per point):

| Column | Type | Meaning |
|---|---|---|
| `trip_id` | str | Links the point to a trip |
| `timestamp` | ISO 8601 string | Time of the point |
| `lat`, `lon` | float | WGS84 (EPSG:4326) |

Rules:

- **Timestamps:** values with an offset (`+02:00`, `Z`) are used as given. Values without one are read as Europe/Budapest local time. All times are stored in UTC. Europe/Budapest is used again only for the local-hour bin (`start_hour_local`, and `trips_by_local_hour` in the report).
- **Invalid times:** a trip is dropped if a timestamp cannot be parsed, falls in a daylight-saving switch (ambiguous or nonexistent local time), or the trip ends before it starts. GPS points with such timestamps are dropped too.
- **Stations:** a trip is dropped if its start or end station ID is not in the Futár station list. The report lists the count, trip IDs and unknown station IDs.
- **Map-matching:** each trip's GPS points, sorted by UTC time, are turned into an ordered list of `edge_id`s by `map_match_trace`. This is a **placeholder** that raises `NotImplementedError`; CS 2 implements it following the geoinformatics member's plan. Trips without GPS points, or whose trace matches no edges, are dropped and counted.
- **Merging:** routes with the same scenario, station pair, route type and edge list are merged by summing `trip_count`. `edges` is stored as a Python list.

```python
import pandas as pd

from bubi.ingestion.observed_routes import convert_observed_routes

trips = pd.read_csv("tests/fixtures/mock_trips.csv")
gps = pd.read_csv("tests/fixtures/mock_gps_points.csv")
stations = pd.read_parquet("tests/fixtures/sample_stations.parquet")

routes, report = convert_observed_routes(
    trips,
    gps,
    stations,
    matcher=lambda points: ["n1-n2-0"],  # stand-in for map-matching
)
```

Without `matcher`, the call raises `NotImplementedError` until map-matching exists. The mock files cover each drop reason: an unknown station (`t04`), a daylight-saving-ambiguous time (`t05`), a trip without GPS points (`t06`) and a trip that ends before it starts (`t07`).

Questions to settle against the real data:

- Are station IDs Futár `id`s, or station codes or names?
- Which timezone are the timestamps in, and do they carry an offset?
- Do trips and GPS points come in one file or two, and in which format (CSV, JSON, Parquet)?
