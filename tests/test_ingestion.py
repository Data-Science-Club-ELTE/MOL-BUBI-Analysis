import json
from datetime import datetime, timezone

import pytest

from bubi.ingestion import futar_snapshot as fs

GOOD = {
    "version": 2,
    "status": "OK",
    "code": 200,
    "text": "OK",
    "data": {
        "limitExceeded": False,
        "list": [
            {"id": "1", "name": "Station A", "lat": 47.5, "lon": 19.0, "bikes": 3},
            {"id": "2", "name": "Station B", "lat": 47.6, "lon": 19.1, "bikes": 0},
        ],
    },
}


def test_redact_removes_key():
    url = fs.build_url("SECRET123")
    assert "SECRET123" in url
    assert "SECRET123" not in fs.redact(url)
    assert "key=" not in fs.redact(url)


def test_inspect_good_payload():
    report = fs.inspect_payload(json.dumps(GOOD).encode())
    assert report["station_count"] == 2
    assert report["problems"] == []


def test_inspect_missing_fields_and_structure():
    bad = {"data": {"list": [{"id": "1", "name": "x"}]}}
    report = fs.inspect_payload(json.dumps(bad).encode())
    assert report["station_count"] == 1
    assert any("lat" in p for p in report["problems"])

    assert fs.inspect_payload(b"not json")["valid_json"] is False
    assert fs.inspect_payload(b'{"data": 5}')["station_count"] is None


def test_save_snapshot_keeps_raw_bytes_and_hides_key(tmp_path):
    body = json.dumps(GOOD, indent=1).encode()  # odd formatting must survive
    url = fs.build_url("SECRET123")
    now = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    raw, meta_path, meta = fs.save_snapshot(body, 200, url, tmp_path, now=now)

    assert raw.read_bytes() == body
    assert meta["station_count"] == 2
    assert "SECRET123" not in meta_path.read_text()

    with pytest.raises(fs.IngestionError):
        fs.save_snapshot(body, 200, url, tmp_path, now=now)  # no overwrite


def test_run_with_mocked_http(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "http_get", lambda url, timeout=30: (200, json.dumps(GOOD).encode()))
    assert fs.run(tmp_path, api_key="k") == 0
    assert len(list(tmp_path.glob("*.json"))) == 2  # raw + meta


def test_run_reports_http_error(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "http_get", lambda url, timeout=30: (401, b'{"text":"invalid key"}'))
    assert fs.run(tmp_path, api_key="bad") == 1
