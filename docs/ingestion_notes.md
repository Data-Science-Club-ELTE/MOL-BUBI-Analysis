# Futar bicycle-rental snapshot: acquisition notes (Issue #5)

## 1. API access and key status
- Portal: BKK OpenData Portal (opendata.bkk.hu), section "Key management"
- Key requested on: 2026-10-18 (non-commercial student project, Data Science Club ELTE)
- Key status: requested. The portal says a requested key becomes usable after BKK approval; approval was still pending when this note was written.
- Access blocker: none observed. The request (sent with the key from the local `.env`) returned HTTP 200. It is not known whether this endpoint validates the key or whether the key was already active.

## 2. Request
- Endpoint: `https://futar.bkk.hu/api/query/v1/ws/otp/api/where/bicycle-rental.json`
- Parameters: `version=2`, `appVersion=bubi-analysis-1.0`, `key=<hidden>`
- Access method: HTTP GET, key read from environment variable `BKK_FUTAR_API_KEY` (local `.env`, git-ignored)

## 3. Snapshot
- Retrieved at (UTC): 2026-10-18T16:34:42.759247+00:00
- Raw file: `data/raw/futar_bicycle_rental_20261018T163442Z.json` (not committed, `data/raw/` is git-ignored)
- Size: 190452 bytes
- SHA-256: `8c3fe365e1f0e59e7136edeb028f0d9f9e05a07d84c3195d6a3215278511d302`
- HTTP status: 200

## 4. Record count
- Number of station records: 925
- Counting method: `len(response['data']['list'])`
- All records have `objectType = "station"`; all 925 `id` values and all names are unique.

## 5. Errors, missing fields, unexpected structure
- Problems reported by the script: none observed
- API status/code: OK / 200
- Top-level keys: code, currentTime, data, status, text, version
- `data` keys: class, limitExceeded, list, outOfRange, references
- Station fields seen: bikes, code, id, lat, lon, name, objectType, spaces, style, type
- `limitExceeded` is false and `outOfRange` is false, so the list does not look truncated.
- All coordinates are inside the `StationsSchema` ranges (lat 47.415-47.598, lon 18.965-19.294); no record has an empty name.
- Open question: the `type` field has three values: `virtual` (704), `bike` (144), `ebike` (77). Their meaning is not documented here; to be clarified with the team before the later normalization step.

## 6. Sharing the raw file
- `data/raw/` is git-ignored, so the snapshot is NOT in the repo.
- Shared with the team via: TODO (waiting for the answer where to upload it)

## 7. Security check
- [x] `.env` is ignored by git (checked with `git check-ignore -v .env`)
- [ ] No API key appears in any committed file (check before committing)
