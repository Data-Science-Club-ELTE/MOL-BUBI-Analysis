"""Tests for the dashboard skeleton: data loading, error messages and a headless app run."""

import io
import json
import math
import shutil
from dataclasses import replace
from pathlib import Path

import folium
import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString
from streamlit.testing.v1 import AppTest

from bubi.dashboard.app import (
    LANE_COLOR,
    NO_LANE_COLOR,
    ROUTE_FIELDS,
    ROUTE_WEIGHTS,
    LaneStatusLayer,
    MapLegend,
    RouteVolumeLayer,
    Settings,
    build_map,
    compass_headings,
    export_csv,
    lane_status_geojson,
    legend_html,
    map_bounds,
    offset_line,
    route_volume_layer,
    route_volume_per_edge,
    shift_right,
    volume_classes,
)
from bubi.dashboard.data import (
    DATA_DIR_ENV,
    OPTIONAL_TABLES,
    REQUIRED_TABLES,
    DashboardDataError,
    as_id_list,
    cell_center,
    fixture_notes,
    for_scenario,
    load_config,
    load_dashboard_data,
    proposed_stations,
    resolve_table_paths,
)

APP_PATH = Path(__file__).resolve().parents[1] / "src" / "bubi" / "dashboard" / "app.py"


@pytest.fixture
def fixture_copy(tmp_path: Path, fixtures_dir: Path) -> Path:
    """A throwaway copy of the fixtures that tests can break."""
    target = tmp_path / "fixtures"
    shutil.copytree(fixtures_dir, target)
    return target


# ---------------------------------------------------------------- loader


def test_loads_all_fixture_tables(fixtures_dir: Path):
    data = load_dashboard_data(fixtures_dir)
    assert data.source == "fixtures"
    assert set(data.tables) == set(REQUIRED_TABLES) | set(OPTIONAL_TABLES)
    assert data.warnings == []
    assert len(data.get("stations")) > 0


def test_missing_required_table_gives_clear_error(fixture_copy: Path):
    (fixture_copy / "sample_stations.parquet").unlink()
    with pytest.raises(DashboardDataError) as err:
        load_dashboard_data(fixture_copy)
    message = str(err.value)
    assert "`stations` table is missing" in message
    assert "make fixtures" in message


def test_missing_optional_table_only_warns(fixture_copy: Path):
    (fixture_copy / "sample_corridors.parquet").unlink()
    data = load_dashboard_data(fixture_copy)
    assert "corridors" not in data.tables
    assert any("`corridors`" in w for w in data.warnings)


def test_invalid_table_names_the_contract(fixture_copy: Path):
    bad = pd.DataFrame([{"station_id": "x", "name": "Out of Budapest", "lat": 10.0, "lon": 19.0}])
    bad.to_parquet(fixture_copy / "sample_stations.parquet", index=False)
    with pytest.raises(DashboardDataError, match="does not match its data contract"):
        load_dashboard_data(fixture_copy)


def test_each_table_falls_back_to_fixtures_on_its_own(
    monkeypatch, tmp_path: Path, fixtures_dir: Path
):
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    processed = tmp_path / "processed"
    processed.mkdir()
    shutil.copy(fixtures_dir / "sample_stations.parquet", processed / "stations.parquet")

    paths = resolve_table_paths(processed_dir=processed, fixtures_dir=fixtures_dir)

    assert paths["stations"] == (processed / "stations.parquet", "processed")
    assert paths["edges"] == (fixtures_dir / "sample_edges.parquet", "fixtures")


def test_fixture_notes_name_every_test_table(fixtures_dir: Path):
    data = load_dashboard_data(fixtures_dir)
    data.sources["stations"] = "processed"
    notes = fixture_notes(data)
    assert data.source == "mixed"
    assert len(notes) == len(data.tables) - 1
    assert not any("`stations`" in note for note in notes)
    assert any("`edges`" in note and "sample_edges.parquet" in note for note in notes)


def test_proposed_stations_skip_unranked_candidates(fixtures_dir: Path):
    data = load_dashboard_data(fixtures_dir)
    candidates = data.tables["station_candidates"].copy()
    candidates["rank"] = candidates["rank"].astype("Int64")
    candidates.loc[candidates.index[0], "rank"] = pd.NA
    data.tables["station_candidates"] = candidates

    scenario = candidates.iloc[0]["scenario"]
    proposed = proposed_stations(data, scenario)
    assert len(proposed) == len(for_scenario(candidates, scenario)) - 1
    assert proposed["rank"].notna().all()


def test_corrupt_file_gives_clear_error(fixture_copy: Path):
    (fixture_copy / "sample_edges.parquet").write_bytes(b"not a parquet file")
    with pytest.raises(DashboardDataError, match="could not be read"):
        load_dashboard_data(fixture_copy)


# ---------------------------------------------------------------- helpers


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("n1-n3-0", ["n1-n3-0"]),
        ("n1-n3-0, n3-n4-0", ["n1-n3-0", "n3-n4-0"]),
        ('["a", "b"]', ["a", "b"]),
        (["a", "b"], ["a", "b"]),
        (None, []),
    ],
)
def test_as_id_list(value, expected):
    assert as_id_list(value) == expected


def test_cell_center_rejects_invalid_ids():
    assert cell_center("not-a-cell") is None
    lat, lon = cell_center("891e037aacfffff")  # Deák Ferenc tér, res 9
    assert 47.4 < lat < 47.6 and 19.0 < lon < 19.1


def test_for_scenario_handles_missing_table():
    assert for_scenario(None, "baseline").empty


def test_offset_line_separates_directions():
    forward = [(19.05, 47.49), (19.06, 47.50)]
    there = offset_line(forward)
    back = offset_line(list(reversed(forward)))
    assert there[0] != back[-1]  # the two directions no longer overlap


def test_route_volume_per_edge(sample_routes):
    volumes = route_volume_per_edge(sample_routes[sample_routes["scenario"] == "baseline"])
    assert volumes["n1-n3-0"] == 210.0


# ---------------------------------------------------------------- week 2: baseline map

ALL_LAYERS = Settings(
    scenario="baseline",
    basemap="OpenStreetMap",
    show_stations=True,
    show_proposed=True,
    show_population=False,
    show_lanes=True,
    show_routes=False,
    show_corridors=True,
    top_n=10,
)


def two_way_street(lane_forward: bool, lane_back: bool) -> gpd.GeoDataFrame:
    """One east-west street near Deák tér, stored as two directed edges."""
    line = LineString([(19.050, 47.497), (19.060, 47.497)])
    return gpd.GeoDataFrame(
        {
            "edge_id": ["a-b-0", "b-a-0"],
            "osm_way_id": [1, 1],
            "length_m": [750.0, 750.0],
            "has_dedicated_lane": [lane_forward, lane_back],
        },
        geometry=[line, line.reverse()],
        crs="EPSG:4326",
    )


def layers_of(fmap: folium.Map, kind: type) -> list:
    return [child for child in fmap._children.values() if isinstance(child, kind)]


def all_children(element) -> list:
    found = []
    for child in element._children.values():
        found.append(child)
        found.extend(all_children(child))
    return found


def lines_by_status(geojson_text: str) -> dict[str, list]:
    """Parse lane_status_geojson output into {"yes"/"no": list of line coordinate lists}."""
    geojson = json.loads(geojson_text)
    assert geojson["type"] == "FeatureCollection"
    return {f["properties"]["lane"]: f["geometry"]["coordinates"] for f in geojson["features"]}


def test_lane_geojson_groups_directions_by_their_own_lane_status():
    lines = lines_by_status(lane_status_geojson(two_way_street(lane_forward=True, lane_back=False)))

    # One feature per status, each holding one line per directed edge.
    assert set(lines) == {"yes", "no"}
    assert len(lines["yes"]) == 1 and len(lines["no"]) == 1


def test_lane_geojson_draws_each_direction_on_its_right_side():
    lines = lines_by_status(lane_status_geojson(two_way_street(True, False)))

    # a-b-0 (lane) runs east, so its right-hand side is south; b-a-0 (no lane) runs west.
    east_lat = lines["yes"][0][0][1]
    west_lat = lines["no"][0][0][1]
    assert east_lat < 47.497 < west_lat
    gap_m = (west_lat - east_lat) * 111_320
    assert 7.0 < gap_m < 9.0  # 4 m each side, within the ~1 m rounding


def test_lane_geojson_rounds_coordinates_to_about_one_metre():
    lines = lines_by_status(lane_status_geojson(two_way_street(True, True)))
    for lon, lat in lines["yes"][0]:
        assert round(lon, 5) == lon and round(lat, 5) == lat


def test_lane_geojson_of_no_edges_is_empty():
    empty = two_way_street(True, True).iloc[0:0]
    assert json.loads(lane_status_geojson(empty)) == {"type": "FeatureCollection", "features": []}


def test_shift_right_moves_a_line_to_the_right_of_travel():
    east = LineString([(0, 0), (10, 0), (20, 0)])
    north = LineString([(0, 0), (0, 10)])

    shifted_east, shifted_north = shift_right(np.array([east, north]), 4.0)

    assert list(shifted_east.coords) == [(0, -4), (10, -4), (20, -4)]
    assert list(shifted_north.coords) == [(4, 0), (4, 10)]


def test_shift_right_keeps_repeated_points_in_place_of_crashing():
    line = LineString([(0, 0), (0, 0), (10, 0)])
    (shifted,) = shift_right(np.array([line]), 2.0)
    assert list(shifted.coords) == [(0, -2), (0, -2), (10, -2)]


def test_edges_are_one_geojson_layer_not_one_line_per_edge(fixtures_dir: Path):
    data = load_dashboard_data(fixtures_dir)
    settings = replace(ALL_LAYERS, show_stations=False, show_proposed=False, show_corridors=False)

    fmap, _ = build_map(data, settings)

    lane_layers = layers_of(fmap, LaneStatusLayer)
    assert len(lane_layers) == 1
    lines = lines_by_status(lane_layers[0].geojson)
    assert sum(len(parts) for parts in lines.values()) == len(data.get("edges"))
    assert not any(isinstance(c, folium.PolyLine) for c in all_children(fmap))
    assert "L.geoJson(" in fmap.get_root().render()


def test_stations_are_one_geojson_layer(fixtures_dir: Path):
    data = load_dashboard_data(fixtures_dir)
    settings = replace(ALL_LAYERS, show_lanes=False, show_proposed=False, show_corridors=False)

    fmap, _ = build_map(data, settings)

    station_layers = layers_of(fmap, folium.GeoJson)
    assert len(station_layers) == 1
    assert len(station_layers[0].data["features"]) == len(data.get("stations"))
    assert not any(isinstance(c, folium.CircleMarker) for c in all_children(fmap))


def test_lane_colours_are_chosen_in_the_browser(fixtures_dir: Path):
    fmap, _ = build_map(load_dashboard_data(fixtures_dir), ALL_LAYERS)
    html = fmap.get_root().render()

    # No per-edge style table in the page: one JS function picks the colour.
    assert "_styler" not in html
    assert LANE_COLOR in html and NO_LANE_COLOR in html
    assert "preferCanvas" in html


def test_legend_explains_the_lane_colours(fixtures_dir: Path):
    fmap, _ = build_map(load_dashboard_data(fixtures_dir), ALL_LAYERS)

    legends = layers_of(fmap, MapLegend)
    assert len(legends) == 1
    html = legends[0].html
    assert "Bike lane in this direction" in html and LANE_COLOR in html
    assert "No bike lane in this direction" in html and NO_LANE_COLOR in html
    assert "right-hand side of travel" in html
    assert "Existing station" in html


def test_legend_lists_only_layers_that_are_shown(fixtures_dir: Path):
    settings = replace(ALL_LAYERS, show_lanes=False, show_proposed=False, show_corridors=False)
    fmap, _ = build_map(load_dashboard_data(fixtures_dir), settings)

    html = layers_of(fmap, MapLegend)[0].html
    assert "Existing station" in html
    assert "bike lane" not in html.lower()


def test_legend_html_escapes_labels():
    assert "&lt;b&gt;" in legend_html([("", "<b>")])


@pytest.mark.parametrize(
    ("toggle", "layer_name"),
    [("show_lanes", "Bike-lane status"), ("show_stations", "Existing stations")],
)
def test_layer_toggles_remove_the_layer(fixtures_dir: Path, toggle: str, layer_name: str):
    data = load_dashboard_data(fixtures_dir)

    shown, _ = build_map(data, ALL_LAYERS)
    hidden, _ = build_map(data, replace(ALL_LAYERS, **{toggle: False}))

    def names(fmap):
        return {getattr(c, "layer_name", None) for c in fmap._children.values()}

    assert layer_name in names(shown)
    assert layer_name not in names(hidden)


def test_proposed_stations_sit_on_the_h3_cell_centre(fixtures_dir: Path):
    data = load_dashboard_data(fixtures_dir)
    fmap, _ = build_map(data, replace(ALL_LAYERS, scenario="lane_aware"))

    markers = [c for c in all_children(fmap) if isinstance(c, folium.RegularPolygonMarker)]
    expected = {
        h3.cell_to_latlng(cell) for cell in proposed_stations(data, "lane_aware")["cell_id"]
    }
    assert markers
    for marker in markers:
        lat, lon = marker.location
        assert any(
            math.isclose(lat, e_lat) and math.isclose(lon, e_lon) for e_lat, e_lon in expected
        )


def test_map_opens_on_every_station_and_edge(fixtures_dir: Path):
    data = load_dashboard_data(fixtures_dir)
    stations, edges = data.get("stations"), data.get("edges")

    (south, west), (north, east) = map_bounds(stations, edges)

    min_lon, min_lat, max_lon, max_lat = edges.total_bounds
    assert south <= min(stations["lat"].min(), min_lat)
    assert north >= max(stations["lat"].max(), max_lat)
    assert west <= min(stations["lon"].min(), min_lon)
    assert east >= max(stations["lon"].max(), max_lon)
    fmap, _ = build_map(data, ALL_LAYERS)
    assert "fitBounds" in fmap.get_root().render()


def test_map_bounds_without_data_is_none():
    assert map_bounds(None, None) is None


# ---------------------------------------------------------------- app


def _run_app(monkeypatch, data_dir: Path | None = None) -> AppTest:
    if data_dir is not None:
        monkeypatch.setenv(DATA_DIR_ENV, str(data_dir))
    return AppTest.from_file(str(APP_PATH), default_timeout=60).run()


def test_app_runs_on_fixtures(monkeypatch, fixtures_dir: Path):
    at = _run_app(monkeypatch, fixtures_dir)
    assert not at.exception
    assert not at.error
    assert len(at.metric) == 4
    assert any("is read from test data" in c.value for c in at.caption)


def test_app_reports_map_preparation_time(monkeypatch, fixtures_dir: Path):
    at = _run_app(monkeypatch, fixtures_dir)
    assert any("directed street edges" in c.value for c in at.caption)


@pytest.mark.parametrize("label", ["Bike-lane coverage", "Existing stations"])
def test_app_layer_toggles_run(monkeypatch, fixtures_dir: Path, label: str):
    at = _run_app(monkeypatch, fixtures_dir)
    toggle = next(box for box in at.sidebar.checkbox if box.label == label)
    toggle.uncheck().run()
    assert not at.exception
    assert not at.error


def test_app_runs_with_light_basemap(monkeypatch, fixtures_dir: Path):
    at = _run_app(monkeypatch, fixtures_dir)
    at.sidebar.selectbox[0].set_value("Light grey (Esri)").run()
    assert not at.exception


@pytest.mark.parametrize("scenario", ["lane_aware", "population_only"])
def test_app_switches_scenario(monkeypatch, fixtures_dir: Path, scenario: str):
    at = _run_app(monkeypatch, fixtures_dir)
    at.sidebar.radio[0].set_value(scenario).run()
    assert not at.exception


def test_app_shows_error_instead_of_crashing(monkeypatch, fixture_copy: Path):
    (fixture_copy / "sample_edges.parquet").unlink()
    at = _run_app(monkeypatch, fixture_copy)
    assert not at.exception
    assert at.error and "`edges` table is missing" in at.error[0].value


# ---------------------------------------------------------------- week 3: route volume


def street_routes(forward_trips: float, back_trips: float, **extra) -> pd.DataFrame:
    """Baseline routes along the two directions of two_way_street()."""
    return pd.DataFrame(
        {
            "scenario": ["baseline", "baseline"],
            "start_station_id": ["s1", "s2"],
            "end_station_id": ["s2", "s1"],
            "route_type": ["synthetic", "synthetic"],
            "edges": [["a-b-0"], ["b-a-0"]],
            "trip_count": [forward_trips, back_trips],
            **extra,
        }
    )


def features_by_edge(layer) -> dict[str, dict]:
    """route_volume_layer's column arrays, regrouped into one dict per edge."""
    data = json.loads(layer.data)
    rows = zip(*(data[field] for field in ROUTE_FIELDS))
    return {row[0]: dict(zip(ROUTE_FIELDS, row)) for row in rows}


def test_route_volume_counts_a_repeated_edge_once():
    routes = street_routes(10, 5).assign(edges=[["a-b-0", "a-b-0"], ["b-a-0"]])
    assert route_volume_per_edge(routes)["a-b-0"] == 10.0


def test_volume_classes_split_at_quartiles_and_label_real_ranges():
    classes, labels = volume_classes(np.array([1.0, 2.0, 3.0, 4.0, 100.0]))
    assert classes.tolist() == [0, 0, 1, 2, 3]
    assert labels == ["1–2", "3", "4", "100"]


def test_volume_classes_skip_quartiles_with_no_volume_between_them():
    classes, labels = volume_classes(np.array([20.0, 300.0]))
    assert classes.tolist() == [0, 1]
    assert labels == ["20", "300"]


def test_volume_class_labels_never_round_small_volumes_to_zero():
    _, labels = volume_classes(np.array([0.3, 0.4, 2.0, 2.5, 12.4, 1234.0]))
    assert labels[0].startswith("0.3")
    assert labels[-1].endswith("1,234")


def test_volume_classes_of_one_value_is_one_class():
    classes, labels = volume_classes(np.array([7.0, 7.0]))
    assert classes.tolist() == [0, 0]
    assert labels == ["7"]


def test_route_layer_has_one_feature_per_used_direction():
    layer = route_volume_layer(two_way_street(False, False), street_routes(300, 20))
    features = features_by_edge(layer)
    assert set(features) == {"a-b-0", "b-a-0"}
    assert features["a-b-0"]["volume"] == 300
    assert features["b-a-0"]["volume"] == 20
    assert layer.n_edges == 2


def test_route_layer_colour_and_width_grow_with_volume():
    features = features_by_edge(
        route_volume_layer(two_way_street(False, False), street_routes(300, 20))
    )
    busy, quiet = features["a-b-0"]["step"], features["b-a-0"]["step"]
    assert busy > quiet  # later steps are darker in ROUTE_RAMP and wider in ROUTE_WEIGHTS
    assert ROUTE_WEIGHTS[busy] > ROUTE_WEIGHTS[quiet]


def test_route_layer_draws_each_direction_on_its_right_side():
    features = features_by_edge(
        route_volume_layer(two_way_street(False, False), street_routes(300, 20))
    )
    street_lat = 47.497
    # east-bound a->b sits south of the street, west-bound b->a north of it
    assert all(lat < street_lat for lat in features["a-b-0"]["coords"][1::2])
    assert all(lat > street_lat for lat in features["b-a-0"]["coords"][1::2])


def test_route_tooltip_fields_give_direction_and_lane_status():
    features = features_by_edge(
        route_volume_layer(two_way_street(True, False), street_routes(300, 20))
    )
    forward, back = features["a-b-0"], features["b-a-0"]
    assert (forward["heading"], back["heading"]) == ("E", "W")
    assert (forward["lane"], back["lane"]) == (1, 0)


def test_compass_headings():
    lines = np.array(
        [
            LineString([(0, 0), (0, 10)]),
            LineString([(0, 0), (10, 10)]),
            LineString([(0, 0), (0, -10)]),
            LineString([(0, 0), (-10, 0)]),
        ]
    )
    assert compass_headings(lines).tolist() == ["N", "NE", "S", "W"]


def test_route_layer_is_labelled_synthetic():
    layer = route_volume_layer(two_way_street(False, False), street_routes(300, 20))
    assert "Synthetic" in layer.label and "D5" in layer.label


def test_route_layer_labels_observed_routes_honestly():
    routes = street_routes(300, 20).assign(route_type=["observed", "synthetic"])
    layer = route_volume_layer(two_way_street(False, False), routes)
    assert layer.label == "Synthetic + observed routes"


def test_route_layer_notes_edges_missing_from_the_network():
    routes = street_routes(300, 20).assign(edges=[["a-b-0"], ["x-y-0"]])
    layer = route_volume_layer(two_way_street(False, False), routes)
    assert set(features_by_edge(layer)) == {"a-b-0"}
    assert any("1 edge(s)" in note for note in layer.notes)


def test_route_layer_turns_bad_routes_into_a_note():
    layer = route_volume_layer(two_way_street(False, False), street_routes(-5, 20))
    assert layer.legend == []
    assert any("could not be computed" in note for note in layer.notes)


def test_route_layer_on_the_map_shows_label_tooltip_and_legend(fixtures_dir: Path):
    data = load_dashboard_data(fixtures_dir)
    fmap, _ = build_map(data, replace(ALL_LAYERS, show_routes=True))
    assert len(layers_of(fmap, RouteVolumeLayer)) == 1
    html = fmap.get_root().render()
    assert "bindTooltip" in html
    assert "Synthetic demo data (D5)" in html
    for field in ("Edge ", "Direction: ", "Trips: ", "Bike lane in this direction: "):
        assert field in html
    assert "trips" in layers_of(fmap, MapLegend)[0].html


def test_route_toggle_removes_the_layer(fixtures_dir: Path):
    data = load_dashboard_data(fixtures_dir)
    fmap, _ = build_map(data, replace(ALL_LAYERS, show_routes=False))
    assert layers_of(fmap, RouteVolumeLayer) == []


def test_app_route_layer_toggle_runs(monkeypatch, fixtures_dir: Path):
    at = _run_app(monkeypatch, fixtures_dir)
    toggle = next(box for box in at.sidebar.checkbox if box.label == "Synthetic routes")
    toggle.check().run()
    assert not at.exception
    assert not at.error
    toggle.uncheck().run()
    assert not at.exception


@pytest.mark.parametrize(
    "edge_ids",
    [np.array(["a-b-0", "b-c-0"]), ["a-b-0", "b-c-0"], '["a-b-0", "b-c-0"]', "a-b-0,b-c-0"],
)
def test_export_csv_writes_edge_ids_as_a_json_array(edge_ids):
    table = pd.DataFrame({"corridor_id": ["c1"], "edge_ids": [edge_ids], "rank": [1]})
    exported = pd.read_csv(io.BytesIO(export_csv(table)))
    assert json.loads(exported.loc[0, "edge_ids"]) == ["a-b-0", "b-c-0"]


def test_export_csv_keeps_tables_without_edge_ids():
    table = pd.DataFrame({"cell_id": ["891e037aacfffff"], "rank": [1]})
    assert export_csv(table) == table.to_csv(index=False).encode("utf-8")


def test_missing_config_falls_back_to_defaults(tmp_path: Path):
    assert load_config(tmp_path / "missing.yaml") == {}


@pytest.mark.parametrize("text", ["scenarios: [unclosed", "- just\n- a list\n"])
def test_broken_config_is_reported_not_ignored(tmp_path: Path, text: str):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(DashboardDataError, match="Using default settings"):
        load_config(path)
