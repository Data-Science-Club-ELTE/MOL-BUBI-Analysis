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
- Open question for the team: the later `StationsSchema` table should probably contain only `type = "virtual"` records (704). To be decided before the normalization step.

## 7. Sharing the raw file
- `data/raw/` is git-ignored, so the snapshot is NOT in the repo.
- The first raw file was sent directly to the project maintainer (oguzzkd) in chat on 2026-10-18. A shared upload location for the team has not been decided yet.

## 8. Security check
- [x] `.env` is ignored by git (checked with `git check-ignore -v .env`)
- [x] The key value does not appear in any repository file (checked by searching the project for it before committing)
