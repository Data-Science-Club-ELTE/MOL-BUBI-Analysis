# Futar bicycle-rental snapshot: acquisition notes (Issue #5)

## 1. API access and key status
- Portal: BKK OpenData Portal (opendata.bkk.hu), section "Key management".
- Own key requested on 2026-10-18 at 18:28 (portal time) as a non-commercial student project (Data Science Club ELTE).
- The portal says a requested key can be used only after BKK approves it. No approval has been received so far.
- The key worked about 6 minutes after the request (first snapshot at 18:34 local time, 16:34 UTC).
- Key check on the same endpoint (2026-10-18): no key -> HTTP 401, wrong key -> HTTP 401, own key -> HTTP 200. So the endpoint does validate the key.
- On 2026-10-26 the key owner emailed BKK to ask when the approval will arrive. No reply yet.
- Access status: technically the key works, but formal approval is pending. Until BKK replies, no new API requests are made; the two existing snapshots are enough, and the station table and tests use the saved raw file only.

## 2. Request
- Endpoint: `https://futar.bkk.hu/api/query/v1/ws/otp/api/where/bicycle-rental.json`
- Parameters: `version=2`, `appVersion=bubi-analysis-1.0`, `key=<hidden>`
- Access method: HTTP GET, key read from environment variable `BKK_FUTAR_API_KEY` (local `.env`, git-ignored)

## 3. First snapshot
- Retrieved at (UTC): 2026-10-18T16:34:42.759247+00:00
- Raw file: `data/raw/futar_bicycle_rental_20261018T163442Z.json` (not committed, `data/raw/` is git-ignored)
- Size: 190452 bytes
- SHA-256: `8c3fe365e1f0e59e7136edeb028f0d9f9e05a07d84c3195d6a3215278511d302`
- HTTP status: 200

## 4. Record count
- Number of records in the response: 925
- Counting method: `len(response['data']['list'])`
- All 925 records have `objectType = "station"`, unique `id` values and non-empty names.
- Breakdown by the `type` field: `virtual` 704, `bike` 144, `ebike` 77.
- Caution: not all records are fixed stations, see section 6.

## 5. Errors, missing fields, unexpected structure
- Problems reported by the script: none observed
- API status/code: OK / 200
- Top-level keys: code, currentTime, data, status, text, version
- `data` keys: class, limitExceeded, list, outOfRange, references
- Station fields seen: bikes, code, id, lat, lon, name, objectType, spaces, style, type
- `limitExceeded` is false and `outOfRange` is false, so the list does not look truncated.
- All coordinates are inside the `StationsSchema` ranges (lat 47.415-47.598, lon 18.965-19.294).

## 6. Observation: the response mixes two kinds of records
A second request about 4.5 hours later (21:08 UTC, 962 records) was compared with the first one:
- `virtual`: 704 records in both snapshots. They have real street names, small `spaces` values and a varying `bikes` count. They look like fixed stations.
- `bike` / `ebike`: 144 / 77 in the first and 170 / 88 in the second snapshot. 76 ids appear only in the second and 39 only in the first. They have `bikes = 1`, `spaces = 999`, `code = "BIKE"`, an icon named `mol-bubi-floating` and (almost always) `name` equal to the `id`. They look like individual free-floating bikes, not stations.
- Interpretation (not confirmed by BKK documentation): `virtual` = fixed stations; `bike`/`ebike` = single bikes.
- Checked by the project maintainer (oguzzkd): the `virtual` records are the real stations; the `bike`/`ebike` records have no station code, and no stations were found at the coordinates he checked. The processed table therefore contains only `virtual` records (section 8).

## 7. Sharing the raw file
- `data/raw/` is git-ignored, so the snapshot is NOT in the repo.
- Both raw snapshots and their `.meta.json` files are uploaded to the shared team Google Drive folder `MOL-BUBI_DSC/raw_futar_bicycle_rental` (the folder was created by the project maintainer for files outside GitHub).

## 8. Processed stations table
- Code: `src/bubi/ingestion/stations_table.py` (run with `python -m bubi.ingestion.stations_table <raw file>`).
- Input: the first raw snapshot, `futar_bicycle_rental_20261018T163442Z.json` (925 records).
- Stations are selected in two independent ways: `type == "virtual"` (704 records) and "style icon is not `vehicle-rental/mol-bubi-floating`" (704 records). Both selections return exactly the same records, so the table was written.
- Output: `data/processed/stations.parquet`, 704 rows, columns `station_id`, `name`, `lat`, `lon` (`StationsSchema`). `station_id` is the Futar `id` as a string; rows are sorted by `station_id`.
- Frozen snapshot (issue #19): the first snapshot, `futar_bicycle_rental_20261018T163442Z.json`. It is recorded under `stations` in `config/default_config.yaml` (`snapshot_date: "2026-10-18"`, file name and SHA-256).
- Why the first one: the processed table already came from it. The second snapshot (21:08 UTC) has the same 704 `virtual` records with identical `id`, `name`, `lat` and `lon`, so the choice does not change the table.
- `ingest_futar_stations(raw_path=...)` in `src/bubi/ingestion/futar.py` applies the same two selection rules and returns the table without writing it. Run on the frozen snapshot, it returns a table equal to the committed `data/processed/stations.parquet` (704 rows).

## 9. Security check
- [x] `.env` is ignored by git (checked with `git check-ignore -v .env`)
- [x] The key value does not appear in any repository file (checked by searching the project for it before committing)

## 10. Raw inputs, restoring them, and rebuilding the processed tables (Issue #40)

### 10.1 Where each input lives

| Input | Path in the checkout | In git? | Where the copy is kept | Used by stage |
|---|---|---|---|---|
| Frozen Futár snapshot | `data/raw/futar_bicycle_rental_20261018T163442Z.json` | No (`data/raw/` is ignored) | Drive `MOL-BUBI_DSC/raw_futar_bicycle_rental` | `stations` |
| Second Futár snapshot and both `.meta.json` files | `data/raw/` | No | Same Drive folder | None; kept as evidence (§6) |
| Processed stations table | `data/processed/stations.parquet` | Yes | The repository | Input to `candidates` and `trips` |
| Population raster | Not decided | No | Not decided | `population` (#23); product is an open question in `docs/source_inventory.md` §2–3 |
| OSM street and walking graphs | Not decided | No | Not decided | `edges` (#15); snapshot date is an open question in `docs/source_inventory.md` §1 |
| Real trips and GPS points | None received | No | None | Not wired into the pipeline yet; see `src/bubi/ingestion/README.md` §8 |

Git ignores `data/raw/`, `data/cache/`, `data/interim/` and `.env`. Git does **not** ignore `data/processed/`, so tables written there by the pipeline show up as untracked files until someone decides to commit them.

### 10.2 Restoring the raw inputs

1. Download `futar_bicycle_rental_20261018T163442Z.json` from the Drive folder `MOL-BUBI_DSC/raw_futar_bicycle_rental`.
2. Put it in `data/raw/` with the same file name.
3. Check it: the SHA-256 must equal `stations.snapshot_sha256` in `config/default_config.yaml`. The `stations` stage of the pipeline checks this and fails if it differs.

```bash
sha256sum data/raw/futar_bicycle_rental_20261018T163442Z.json
```

### 10.3 Environment variables

| Name | Needed for | Where it is set |
|---|---|---|
| `BKK_FUTAR_API_KEY` | Fetching a **new** Futár snapshot (`python -m bubi.ingestion.futar_snapshot`, or `ingest_futar_stations` without `raw_path`) | Shell environment or the git-ignored `.env`; template in `.env.example` |

The pipeline and the reproducibility check need no environment variables. They read the saved snapshot only and make no API requests, which follows the pending-approval rule in §1.

### 10.4 Running the pipeline

```bash
make run-pipeline
```

This runs `scripts/run_pipeline.py`. The script runs these stages in order: `stations`, `population`, `edges`, `candidates`, `trips`, `routes`, `volumes`, `scores`, `corridors`. Each stage validates its output against its schema through `bubi.contracts.io` before the next stage starts. Outputs go to a temporary file first and replace the real file only after validation. If the new table equals the file already on disk, the file is left untouched.

| Status | Meaning |
|---|---|
| `DONE` | The stage ran and its output validated. The detail says `written` or `unchanged`. |
| `EXISTING` | The module is not implemented yet, but a valid output file is already on disk; later stages use it. |
| `BLOCKED` | The module is not implemented yet, or an input comes from a blocked stage. The detail names the owning issue. |
| `FAILED` | An input is missing or invalid, or the stage raised an error. The detail names the stage and the file. The run stops and the command exits with 1. |
| `NOT_RUN` | An earlier stage failed. |

`edge_volumes.parquet` is an intermediate table, not one of the seven contract tables. It is validated against the `scenario`, `edge_id` and `volume` columns of `EdgeScoresSchema`. The `trips` stage builds the `baseline` scenario only; the other scenarios wait on the scenario storage-layout decision.

Result on 2026-10-27, with the frozen snapshot restored:

```text
stations    DONE      data/processed/stations.parquet  704 rows, unchanged
population  BLOCKED   data/processed/population.parquet  module not implemented yet, owned by #23
edges       BLOCKED   data/processed/edges.parquet  module not implemented yet, owned by #15
candidates  BLOCKED   data/processed/station_candidates.parquet  module not implemented yet, owned by #39
trips       BLOCKED   data/processed/trip_matrix.parquet  upstream: population (#23)
routes      BLOCKED   data/processed/routes.parquet  module not implemented yet, owned by #36
volumes     BLOCKED   data/processed/edge_volumes.parquet  upstream: routes (#36)
scores      BLOCKED   data/processed/edge_scores.parquet  module not implemented yet, owned by #21
corridors   BLOCKED   data/processed/corridors.parquet  module not implemented yet, owned by #37
```

The `trips` and `volumes` stages run once their inputs exist. `tests/test_run_pipeline.py` runs them on the sample population and routes fixtures.

### 10.5 Reproducibility check

```bash
python scripts/check_reproducibility.py              # current commit, this interpreter
python scripts/check_reproducibility.py --install    # also runs `make install` in the clone
```

The script works in four steps:

1. It clones the repository into a temporary directory. Only committed files are checked.
2. It copies the frozen snapshot from `data/raw/` into the clone (`--raw-dir` changes the source).
3. It runs `make run-pipeline` in the clone.
4. It reports `PASS`, `BLOCKED` or `FAIL` for each processed table.

A committed table that comes out different from its committed copy is a `FAIL`. The command exits with 1 if any table fails. Without `--install`, the clone runs with the current interpreter and with its own `src/` first on `PYTHONPATH`.

Result on 2026-10-27, run both with and without `--install`:

```text
Reproducibility per processed table:
  PASS     data/processed/stations.parquet  rebuilt identically to the committed copy
  BLOCKED  data/processed/population.parquet  module not implemented yet, owned by #23
  BLOCKED  data/processed/edges.parquet  module not implemented yet, owned by #15
  BLOCKED  data/processed/station_candidates.parquet  module not implemented yet, owned by #39
  BLOCKED  data/processed/trip_matrix.parquet  upstream: population (#23)
  BLOCKED  data/processed/routes.parquet  module not implemented yet, owned by #36
  BLOCKED  data/processed/edge_volumes.parquet  upstream: routes (#36)
  BLOCKED  data/processed/edge_scores.parquet  module not implemented yet, owned by #21
  BLOCKED  data/processed/corridors.parquet  module not implemented yet, owned by #37
```

Without the raw snapshot, the `stations` table is reported as `FAIL` with the missing file name, the other tables as `FAIL` (not run), and the command exits with 1.
