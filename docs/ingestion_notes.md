# Futar bicycle-rental snapshot: acquisition notes (Issue #5)

## 1. API access and key status
- Portal: BKK OpenData Portal (opendata.bkk.hu), section "Key management".
- Own key requested on 2026-10-18 at 18:28 (portal time) as a non-commercial student project (Data Science Club ELTE).
- The portal says a requested key can be used after approval by BKK. It is not known whether an approval step happened or whether it was automatic.
- The key worked about 6 minutes after the request (first snapshot at 18:34 local time, 16:34 UTC).
- Key check on the same endpoint (2026-10-18): no key -> HTTP 401, wrong key -> HTTP 401, own key -> HTTP 200. So the endpoint does validate the key.
- Access blocker: none.

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
