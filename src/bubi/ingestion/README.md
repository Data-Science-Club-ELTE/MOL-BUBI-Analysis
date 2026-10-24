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

1. Review and implement `src/bubi/ingestion/futar.py`.
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
- [ ] BKK Futár endpoint queried and station list extracted.
- [ ] Output table strictly validated by `StationsSchema`.
- [ ] Snapshot saved to `data/processed/stations.parquet`.
- [ ] Unit test written under `tests/test_ingestion.py`.

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
