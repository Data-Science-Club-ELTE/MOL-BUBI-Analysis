import json

import pandas as pd
import pytest

from bubi.contracts.schemas import StationsSchema
from bubi.ingestion import stations_table as st


def _station(sid, name, lat=47.5, lon=19.05, icon="vehicle-rental/mol-bubi"):
    return {
        "id": sid,
        "lat": lat,
        "lon": lon,
        "objectType": "station",
        "name": name,
        "code": sid,
        "type": "virtual",
        "bikes": 2,
        "spaces": 6,
        "style": {"icon": {"name": icon}},
    }


def _floating(sid, kind="bike"):
    return {
        "id": sid,
        "lat": 47.49,
        "lon": 19.07,
        "objectType": "station",
        "name": sid,
        "code": "BIKE",
        "type": kind,
        "bikes": 1,
        "spaces": 999,
        "style": {"icon": {"name": st.FLOATING_ICON}},
    }


def _write_raw(tmp_path, records):
    path = tmp_path / "futar_bicycle_rental_test.json"
    path.write_text(json.dumps({"data": {"list": records}}), encoding="utf-8")
    return path


def test_selections_agree_and_table_is_written(tmp_path):
    records = [
        _station("9161", "Podmaniczky u. 5."),
        _station("9042", "Baross utca 86.", icon="vehicle-rental/mol-bubi-empty"),
        _floating("82195"),
        _floating("90846", kind="ebike"),
    ]
    out = tmp_path / "processed" / "stations.parquet"
    df, report = st.build_stations_table(_write_raw(tmp_path, records), out)

    assert report["agree"] and report["by_type"] == report["by_icon"] == 2
    assert list(df.columns) == ["station_id", "name", "lat", "lon"]
    assert list(df["station_id"]) == ["9042", "9161"]  # sorted, ids are strings
    stored = pd.read_parquet(out)
    StationsSchema.validate(stored)
    assert len(stored) == 2


def test_disagreement_writes_nothing(tmp_path):
    odd = _station("1111", "Odd one", icon=st.FLOATING_ICON)  # virtual but floating icon
    records = [_station("9161", "Podmaniczky u. 5."), odd]
    out = tmp_path / "stations.parquet"
    df, report = st.build_stations_table(_write_raw(tmp_path, records), out)

    assert df is None
    assert not report["agree"]
    assert report["only_by_type"] == ["1111"]
    assert not out.exists()


def test_invalid_coordinates_are_rejected():
    with pytest.raises(Exception):
        st.to_stations_frame([_station("1", "Outside", lat=10.0)])


def test_latest_raw_snapshot_ignores_meta_files(tmp_path):
    (tmp_path / "futar_bicycle_rental_20261018T100000Z.json").write_text("{}")
    (tmp_path / "futar_bicycle_rental_20261018T100000Z.meta.json").write_text("{}")
    (tmp_path / "futar_bicycle_rental_20261018T110000Z.meta.json").write_text("{}")
    assert st.latest_raw_snapshot(tmp_path).name == "futar_bicycle_rental_20261018T100000Z.json"
