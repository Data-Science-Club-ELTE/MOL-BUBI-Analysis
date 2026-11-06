"""Fetch the initial BKK Futar ``bicycle-rental`` snapshot and store it raw.

Usage (from the repository root):

    export BKK_FUTAR_API_KEY="your-key"        # or put it in a local .env file
    python -m bubi.ingestion.futar_snapshot

What it does
1. Calls the Futar ``bicycle-rental`` endpoint.
2. Saves the response body byte-for-byte under ``data/raw/`` (never modified).
3. Writes a small ``*.meta.json`` next to it: retrieval time, endpoint
   (WITHOUT the API key), HTTP status, station count, counting method, SHA-256.
4. Reports problems (HTTP errors, missing fields, unexpected structure).

The API key is read from the environment only. It is never written to disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = "https://futar.bkk.hu/api/query/v1/ws/otp/api/where/bicycle-rental.json"
DEFAULT_OUT_DIR = Path("data/raw")
ENV_KEY_NAME = "BKK_FUTAR_API_KEY"

# Fields we expect on each station record. Missing ones are reported, not fatal.
EXPECTED_STATION_FIELDS = ("id", "name", "lat", "lon")

COUNT_METHOD = "len(response['data']['list'])"


class IngestionError(RuntimeError):
    """Raised when the snapshot cannot be fetched."""


def load_api_key(env_file: Path = Path(".env")) -> str | None:
    """Read the key from the environment, falling back to a local .env file."""
    key = os.environ.get(ENV_KEY_NAME)
    if key:
        return key.strip()
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{ENV_KEY_NAME}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def build_url(api_key: str | None, endpoint: str = ENDPOINT) -> str:
    params = {"version": "2", "appVersion": "bubi-analysis-1.0"}
    if api_key:
        params["key"] = api_key
    return f"{endpoint}?{urllib.parse.urlencode(params)}"


def redact(url: str) -> str:
    """Return the URL with the API key removed (safe to store / print)."""
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k != "key"]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def http_get(url: str, timeout: int = 30) -> tuple[int, bytes]:
    """GET a URL and return (status_code, body). HTTP errors keep their body."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise IngestionError(f"Network error: {exc.reason}") from exc


def inspect_payload(body: bytes) -> dict:
    """Describe the response without altering it. Never raises on bad content."""
    report: dict = {"valid_json": False, "station_count": None, "problems": []}
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        report["problems"].append(f"Response is not valid JSON: {exc}")
        return report
    report["valid_json"] = True

    if not isinstance(payload, dict):
        report["problems"].append("Top-level JSON is not an object")
        return report

    report["api_status"] = payload.get("status")
    report["api_code"] = payload.get("code")
    report["api_text"] = payload.get("text")
    report["top_level_keys"] = sorted(payload.keys())

    data = payload.get("data")
    if not isinstance(data, dict):
        report["problems"].append("Missing or non-object 'data' field")
        return report
    report["data_keys"] = sorted(data.keys())

    stations = data.get("list")
    if not isinstance(stations, list):
        report["problems"].append("Missing or non-list 'data.list' field")
        return report

    report["station_count"] = len(stations)
    if data.get("limitExceeded"):
        report["problems"].append("limitExceeded is true: list may be truncated")

    missing: dict[str, int] = {}
    seen_keys: set[str] = set()
    for item in stations:
        if not isinstance(item, dict):
            missing["<record is not an object>"] = missing.get("<record is not an object>", 0) + 1
            continue
        seen_keys.update(item.keys())
        for field in EXPECTED_STATION_FIELDS:
            if field not in item:
                missing[field] = missing.get(field, 0) + 1
    report["station_fields_seen"] = sorted(seen_keys)
    for field, n in missing.items():
        report["problems"].append(f"{n} record(s) missing field '{field}'")
    if not stations:
        report["problems"].append("Station list is empty")
    return report


def save_snapshot(
    body: bytes,
    status: int,
    url: str,
    out_dir: Path = DEFAULT_OUT_DIR,
    now: datetime | None = None,
) -> tuple[Path, Path, dict]:
    """Write the raw body and a metadata sidecar. Refuses to overwrite files."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / f"futar_bicycle_rental_{stamp}.json"
    meta_path = out_dir / f"futar_bicycle_rental_{stamp}.meta.json"
    if raw_path.exists() or meta_path.exists():
        raise IngestionError(f"{raw_path} already exists; refusing to overwrite raw data")

    # 1) Raw bytes first, exactly as received.
    with open(raw_path, "xb") as fh:
        fh.write(body)

    # 2) Then describe it.
    report = inspect_payload(body)
    meta = {
        "retrieved_at_utc": now.isoformat(),
        "endpoint": redact(url),
        "http_status": status,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "station_count": report["station_count"],
        "station_count_method": COUNT_METHOD,
        "inspection": report,
        "raw_file": raw_path.name,
    }
    with open(meta_path, "x", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return raw_path, meta_path, meta


def run(out_dir: Path = DEFAULT_OUT_DIR, api_key: str | None = None) -> int:
    api_key = api_key or load_api_key()
    if not api_key:
        print(
            f"WARNING: no API key found ({ENV_KEY_NAME}). Trying without a key; "
            "this will probably be rejected. Document the result as an access blocker.",
            file=sys.stderr,
        )
    url = build_url(api_key)
    print(f"GET {redact(url)}")
    status, body = http_get(url)
    print(f"HTTP {status}, {len(body)} bytes")

    raw_path, meta_path, meta = save_snapshot(body, status, url, out_dir)
    print(f"Saved raw response : {raw_path}")
    print(f"Saved metadata     : {meta_path}")
    print(f"Station count      : {meta['station_count']}  (method: {COUNT_METHOD})")
    for problem in meta["inspection"]["problems"]:
        print(f"PROBLEM: {problem}", file=sys.stderr)

    if status != 200 or meta["station_count"] is None:
        print(
            "Snapshot is NOT usable. Copy the details into docs/ingestion_notes.md.",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)
    try:
        return run(args.out_dir)
    except IngestionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
