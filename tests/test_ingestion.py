import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from bubi.contracts.schemas import StationsSchema
from bubi.ingestion import futar_snapshot as fs
from bubi.ingestion import ingest_futar_stations

SAMPLE_RESPONSE = Path(__file__).parent / "fixtures" / "futar_bicycle_rental_sample.json"

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


def test_ingest_from_saved_response_keeps_only_stations():
    df = ingest_futar_stations(raw_path=SAMPLE_RESPONSE)

    StationsSchema.validate(df)
    assert list(df.columns) == ["station_id", "name", "lat", "lon"]
    assert list(df["station_id"]) == ["0101", "0102", "0103"]  # floating bikes dropped
    assert df.loc[0, "name"] == "Synthetic Station A"
    assert (df.loc[0, "lat"], df.loc[0, "lon"]) == (47.4979, 19.0402)


def test_ingest_rejects_disagreeing_selection_rules(tmp_path):
    payload = json.loads(SAMPLE_RESPONSE.read_text(encoding="utf-8"))
    payload["data"]["list"][0]["style"]["icon"]["name"] = "vehicle-rental/mol-bubi-floating"
    raw = tmp_path / "disagree.json"
    raw.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(fs.IngestionError, match="disagree"):
        ingest_futar_stations(raw_path=raw)


def test_ingest_fetches_saves_raw_and_never_leaks_key(tmp_path, monkeypatch, capsys):
    body = SAMPLE_RESPONSE.read_bytes()
    monkeypatch.setattr(fs, "http_get", lambda url, timeout=30: (200, body))

    df = ingest_futar_stations(api_key="SECRET123", out_dir=tmp_path)

    assert len(df) == 3
    raw = [p for p in tmp_path.glob("*.json") if ".meta." not in p.name]
    assert len(raw) == 1 and raw[0].read_bytes() == body
    for path in tmp_path.iterdir():
        assert "SECRET123" not in path.read_text(encoding="utf-8")
    out = capsys.readouterr()
    assert "SECRET123" not in out.out + out.err


def test_ingest_reads_key_from_environment(tmp_path, monkeypatch):
    seen = {}

    def fake_get(url, timeout=30):
        seen["url"] = url
        return 200, SAMPLE_RESPONSE.read_bytes()

    monkeypatch.setenv(fs.ENV_KEY_NAME, "ENVKEY")
    monkeypatch.setattr(fs, "http_get", fake_get)
    ingest_futar_stations(out_dir=tmp_path)
    assert "key=ENVKEY" in seen["url"]


def test_ingest_without_key_fails_before_request(tmp_path, monkeypatch):
    monkeypatch.delenv(fs.ENV_KEY_NAME, raising=False)
    monkeypatch.setattr(fs, "load_api_key", lambda: None)
    monkeypatch.setattr(fs, "http_get", lambda *a, **k: pytest.fail("must not call the API"))

    with pytest.raises(fs.IngestionError, match=fs.ENV_KEY_NAME):
        ingest_futar_stations(out_dir=tmp_path)


def test_ingest_http_error_keeps_raw_and_hides_key(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "http_get", lambda url, timeout=30: (401, b'{"text":"invalid key"}'))

    with pytest.raises(fs.IngestionError, match="HTTP 401") as exc:
        ingest_futar_stations(api_key="SECRET123", out_dir=tmp_path)
    assert "SECRET123" not in str(exc.value)
    assert len(list(tmp_path.glob("*.json"))) == 2  # raw + meta still written


def test_frozen_snapshot_is_recorded_in_config():
    config_path = Path(__file__).parents[1] / "config" / "default_config.yaml"
    stations = yaml.safe_load(config_path.read_text(encoding="utf-8"))["stations"]
    assert stations["snapshot_date"] == "2026-10-18"
    assert stations["snapshot_file"].startswith("futar_bicycle_rental_20261018T")
    assert len(stations["snapshot_sha256"]) == 64
