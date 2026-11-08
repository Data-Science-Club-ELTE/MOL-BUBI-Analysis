"""Interactive Streamlit + Folium dashboard for MOL Bubi recommendations.

The layout follows ``WIREFRAME.md``. It reads the contract tables through
:mod:`bubi.dashboard.data` (pipeline outputs or sample fixtures, never an external
API) and shows a clear message instead of crashing when data is missing or invalid.
Week 2 draws the whole Budapest street network as one GeoJSON layer coloured by
per-direction lane status, with a legend.

Run with ``make dashboard``.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, replace
from html import escape

import folium
import geopandas as gpd
import h3
import numpy as np
import pandas as pd
import shapely
import streamlit as st
from branca.element import Element, MacroElement, Template
from streamlit_folium import st_folium

from bubi.corridors.scoring import calculate_edge_route_volumes
from bubi.dashboard.data import (
    BUDAPEST_CENTER,
    DATA_DIR_ENV,
    SCENARIOS,
    DashboardData,
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

LANE_COLOR = "#2b8a3e"  # lane exists in this direction
NO_LANE_COLOR = "#adb5bd"  # no lane in this direction
GAP_COLOR = "#e8590c"  # priority corridor (gap)
STATION_COLOR = "#1c7ed6"
PROPOSED_COLOR = "#2b8a3e"
POPULATION_COLOR = "#f08c00"

# Route volume is a magnitude, so one hue from light to dark. Violet stays clear of the
# station blue, lane green/grey and corridor orange; every step keeps >= 2.6:1 contrast
# on both basemaps, so the lightest class is still visible.
ROUTE_RAMP = ("#9775fa", "#7950f2", "#5f3dc4", "#4527a0")
ROUTE_WEIGHTS = (2.5, 4.0, 5.5, 7.5)
# Further out than the lane lines (LANE_OFFSET_M) so a route never hides the lane colour.
ROUTE_OFFSET_M = 10.0
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
ROUTE_FIELDS = ("id", "volume", "heading", "lane", "step", "coords")
EMPTY_ROUTE_DATA = json.dumps(dict.fromkeys(ROUTE_FIELDS, []))

LANE_WEIGHT = 4
NO_LANE_WEIGHT = 2.5
# Both directions of a street share one geometry; each is drawn this far to the
# right of its direction of travel so the two sit side by side.
LANE_OFFSET_M = 4.0
METRIC_CRS = "EPSG:32634"  # UTM zone 34N, metres, covers Budapest
SIMPLIFY_M = 1.0
# About 1 m. Rounding coordinates keeps the city-wide layer small enough to load quickly.
COORD_PRECISION = 1e-5

# Colours are picked in the browser, so the page carries no per-edge style data.
LANE_STYLE_JS = (
    "function (feature) {\n"
    '  var lane = feature.properties.lane === "yes";\n'
    "  return {\n"
    f'    color: lane ? "{LANE_COLOR}" : "{NO_LANE_COLOR}",\n'
    f"    weight: lane ? {LANE_WEIGHT} : {NO_LANE_WEIGHT},\n"
    "    opacity: 0.85\n"
    "  };\n"
    "}"
)

# CartoDB basemaps now need an API key; both of these work without one.
BASEMAPS = {
    "OpenStreetMap": {"tiles": "OpenStreetMap"},
    "Light grey (Esri)": {
        "tiles": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
            "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        ),
        "attr": "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
        # tiles stop at zoom 16; Leaflet scales them up beyond that
        "max_native_zoom": 16,
        "max_zoom": 19,
    },
}

# Required by the source licences; see docs/source_inventory.md.
DATA_ATTRIBUTION = (
    "Data source: BKK Zrt., "
    "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). "
    "Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright) (ODbL). "
    "Population: WorldPop R2025A v1, constrained, 2026 (ODbL)."
)

SCENARIO_HELP = {
    "baseline": "Existing Futár stations only.",
    "lane_aware": "Existing + proposed stations scored by population × lane connectivity.",
    "population_only": "Existing + proposed stations scored by population only.",
}


@dataclass
class Settings:
    scenario: str
    basemap: str
    show_stations: bool
    show_proposed: bool
    show_population: bool
    show_lanes: bool
    show_routes: bool
    show_corridors: bool
    top_n: int


# ---------------------------------------------------------------- data access


@st.cache_data(show_spinner="Loading data tables…")
def _cached_load(data_dir_override: str | None, files_changed_at: float) -> DashboardData:
    """Cached per data folder; ``files_changed_at`` makes the cache reload after data changes."""
    return load_dashboard_data()


@st.cache_resource(show_spinner="Preparing the street layer…")
def _cached_lane_geojson(data_dir_override: str | None, files_changed_at: float) -> str:
    return lane_status_geojson(_cached_load(data_dir_override, files_changed_at).get("edges"))


@st.cache_resource(show_spinner="Preparing the route-volume layer…")
def _cached_route_layer(
    data_dir_override: str | None, files_changed_at: float, scenario: str
) -> RouteLayer:
    """Built once per scenario, so toggling layers or switching back is instant."""
    data = _cached_load(data_dir_override, files_changed_at)
    return route_volume_layer(data.get("edges"), for_scenario(data.get("routes"), scenario))


def _latest_change() -> float:
    paths = [path for path, _ in resolve_table_paths().values() if path.exists()]
    return max((path.stat().st_mtime for path in paths), default=0.0)


def edge_ids_of_corridors(corridors: pd.DataFrame) -> set[str]:
    ids: set[str] = set()
    for value in corridors.get("edge_ids", []):
        ids.update(as_id_list(value))
    return ids


def route_volume_per_edge(routes: pd.DataFrame) -> pd.Series:
    """Total trips crossing each directed edge in the given routes (one scenario).

    Uses the corridor module's counting rules, so the map shows the same volumes that
    corridor scoring ranks: a route that passes an edge twice counts once.

    Raises:
        ValueError: if the routes table is malformed (see ``calculate_edge_route_volumes``).
    """
    if routes.empty:
        return pd.Series(dtype=float)
    volumes = calculate_edge_route_volumes(routes)
    return volumes.groupby("edge_id")["volume"].sum()


# ---------------------------------------------------------------- map helpers


def offset_line(
    coords: list[tuple[float, float]], meters: float = 4.0
) -> list[tuple[float, float]]:
    """Shift a (lon, lat) line a few metres to its right and return (lat, lon) points.

    Both directions of a street share one geometry, so without the shift the
    reverse direction would be drawn exactly on top of the forward one.
    """
    if len(coords) < 2:
        return [(lat, lon) for lon, lat in coords]
    (lon0, lat0), (lon1, lat1) = coords[0], coords[-1]
    lat_m = 111_320.0
    lon_m = 111_320.0 * math.cos(math.radians((lat0 + lat1) / 2))
    dx, dy = (lon1 - lon0) * lon_m, (lat1 - lat0) * lat_m
    length = math.hypot(dx, dy) or 1.0
    # right-hand normal of the direction of travel
    off_lon, off_lat = (dy / length) * meters / lon_m, (-dx / length) * meters / lat_m
    return [(lat + off_lat, lon + off_lon) for lon, lat in coords]


def shift_right(lines: np.ndarray, distance: float) -> np.ndarray:
    """Move every vertex of each line ``distance`` to the right of travel.

    ``lines`` are LineStrings in a metric CRS. Each vertex moves along the average
    right-hand normal of the segments next to it. On sharp bends the shift is a little
    shorter than ``distance``, which is invisible at a few metres. This is about ten
    times faster than ``shapely.offset_curve`` on a city-wide network.
    """
    coords, line_index = shapely.get_coordinates(lines, return_index=True)
    segments = np.diff(coords, axis=0)
    lengths = np.hypot(segments[:, 0], segments[:, 1])
    # Skip the step from one line's last point to the next line's first, and repeated points.
    real = (line_index[1:] == line_index[:-1]) & (lengths > 0)
    unit = np.zeros_like(segments)
    unit[real] = segments[real] / lengths[real, None]
    right = np.column_stack([unit[:, 1], -unit[:, 0]])  # (dx, dy) turned 90° clockwise

    normals = np.zeros_like(coords)
    normals[:-1] += right  # each segment pushes its start point
    normals[1:] += right  # and its end point
    norms = np.hypot(normals[:, 0], normals[:, 1])
    normals[norms > 0] /= norms[norms > 0, None]
    # A point touching only zero-length segments takes the direction of its nearest
    # neighbour on the same line; a line that is a single repeated point stays put.
    normals[norms == 0] = np.nan
    by_line = pd.DataFrame(normals).groupby(line_index)
    normals = by_line.ffill().groupby(line_index).bfill().fillna(0.0).to_numpy()
    return shapely.linestrings(coords + distance * normals, indices=line_index)


def lane_status_geojson(edges: gpd.GeoDataFrame | None) -> str:
    """Every directed edge as GeoJSON text, grouped by lane status.

    The result is a FeatureCollection with at most two features: ``{"lane": "yes"}`` holds
    every direction that has a dedicated lane and ``{"lane": "no"}`` every direction that
    has none, each as one MultiLineString. Two features instead of one per edge keep the
    page small and let the browser draw the whole city at once.

    Each edge (a LineString) is moved ``LANE_OFFSET_M`` to the right of travel so both
    directions of a street stay visible, simplified to ``SIMPLIFY_M`` and rounded to
    about 1 m.
    """
    features = []
    if edges is not None and not edges.empty:
        source = gpd.GeoSeries(edges.geometry.values, crs=edges.crs or "EPSG:4326")
        simplified = source.to_crs(METRIC_CRS).simplify(SIMPLIFY_M)
        shifted = shift_right(simplified.to_numpy(), LANE_OFFSET_M)
        lines = (
            gpd.GeoSeries(shifted, crs=METRIC_CRS)
            .to_crs("EPSG:4326")
            .set_precision(COORD_PRECISION, mode="pointwise")
            .to_numpy()
        )
        has_lane = edges["has_dedicated_lane"].to_numpy(dtype=bool)
        for lane, mask in (("yes", has_lane), ("no", ~has_lane)):
            if not mask.any():
                continue
            geometry = shapely.to_geojson(shapely.multilinestrings(lines[mask]))
            features.append(
                f'{{"type":"Feature","properties":{{"lane":"{lane}"}},"geometry":{geometry}}}'
            )
    return '{"type":"FeatureCollection","features":[' + ",".join(features) + "]}"


@dataclass
class RouteLayer:
    """Everything the map needs to draw route volumes for one scenario."""

    data: str  # compact JSON, see route_volume_layer()
    legend: list[tuple[str, str]]  # (swatch HTML, label), lowest volume first
    label: str  # what kind of routes these are, shown on the layer (D5)
    notes: list[str]
    n_edges: int = 0


def volume_classes(volumes: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Split volumes into up to four classes at their quartiles.

    Returns the class of each volume (0 = lowest) and one label per class giving the
    smallest and largest volume actually in it. Ties at a quartile, or quartiles with no
    volume between them, give fewer classes.
    """
    breaks = np.unique(np.quantile(volumes, [0.25, 0.5, 0.75]))
    classes = np.searchsorted(breaks, volumes, side="left")
    present, classes = np.unique(classes, return_inverse=True)
    labels = []
    for c in range(len(present)):
        lo, hi = volumes[classes == c].min(), volumes[classes == c].max()
        labels.append(_volume_text(lo) if lo == hi else f"{_volume_text(lo)}–{_volume_text(hi)}")
    return classes, labels


def _volume_text(volume: float) -> str:
    """Whole trips from 10 up; one decimal below, so a small volume never reads as 0."""
    if volume >= 10:
        return f"{volume:,.0f}"
    return f"{volume:.1f}".removesuffix(".0")


def compass_headings(lines: np.ndarray) -> np.ndarray:
    """Eight-point compass heading from the first to the last point of each metric line."""
    start, end = shapely.get_point(lines, 0), shapely.get_point(lines, -1)
    dx = shapely.get_x(end) - shapely.get_x(start)
    dy = shapely.get_y(end) - shapely.get_y(start)
    bearing = np.degrees(np.arctan2(dx, dy)) % 360
    return np.array(COMPASS)[np.round(bearing / 45).astype(int) % len(COMPASS)]


def route_layer_label(routes: pd.DataFrame) -> str:
    kinds = set(routes["route_type"]) if "route_type" in routes else {"synthetic"}
    if kinds == {"synthetic"}:
        return "Synthetic demo data (D5): not observed cycling"
    if kinds == {"observed"}:
        return "Observed routes"
    return "Synthetic + observed routes"


def _flat_coords(lines: np.ndarray) -> list[list[float]]:
    """Each line's coordinates as one flat ``[lon, lat, lon, lat, …]`` list.

    Rounding to 5 decimals (about 1 m) also keeps the numbers short in JSON.
    """
    coords, line_index = shapely.get_coordinates(lines, return_index=True)
    starts = np.flatnonzero(np.diff(line_index)) + 1
    return [part.ravel().tolist() for part in np.split(np.round(coords, 5), starts)]


def _ramp_steps(n_classes: int) -> list[int]:
    """Which ``ROUTE_RAMP`` step each volume class uses, spread from lightest to darkest.

    A single class takes the darkest step so it stands out on the map.
    """
    last = len(ROUTE_RAMP) - 1
    if n_classes == 1:
        return [last]
    return np.round(np.linspace(0, last, n_classes)).astype(int).tolist()


def route_volume_layer(edges: gpd.GeoDataFrame, routes: pd.DataFrame) -> RouteLayer:
    """Route volume per directed edge for one scenario's routes, ready to draw.

    One line per edge that any route uses, shifted ``ROUTE_OFFSET_M`` to the right of
    travel (the same convention as the lane layer), coloured and sized by volume class.
    ``RouteLayer.data`` is compact JSON with one array per field, index-aligned:
    ``id``, ``volume``, ``heading`` (compass point), ``lane`` (1 = lane in this
    direction), ``step`` (index into ``ROUTE_RAMP``/``ROUTE_WEIGHTS``) and ``coords``
    (flat ``[lon, lat, lon, lat, …]`` per edge). City-wide, GeoJSON with per-feature
    properties was about three times larger. Problems with the routes table become
    notes instead of errors.
    """
    label = route_layer_label(routes)
    try:
        volumes = route_volume_per_edge(routes)
    except ValueError as err:
        notes = [f"Route volumes could not be computed: {err}"]
        return RouteLayer(EMPTY_ROUTE_DATA, [], label, notes)

    notes = []
    used = edges[edges["edge_id"].isin(volumes.index)]
    unknown = len(volumes) - len(used)
    if unknown:
        notes.append(f"{unknown} edge(s) used by routes are not in the edges table and not drawn.")
    if used.empty:
        return RouteLayer(EMPTY_ROUTE_DATA, [], label, notes)

    volume = volumes.reindex(used["edge_id"]).to_numpy(dtype=float)
    metric = gpd.GeoSeries(used.geometry.values, crs=edges.crs or "EPSG:4326").to_crs(METRIC_CRS)
    headings = compass_headings(metric.to_numpy())
    shifted = shift_right(metric.simplify(SIMPLIFY_M).to_numpy(), ROUTE_OFFSET_M)
    lines = gpd.GeoSeries(shifted, crs=METRIC_CRS).to_crs("EPSG:4326").to_numpy()
    classes, class_labels = volume_classes(volume)
    steps = _ramp_steps(len(class_labels))

    rounded = np.round(volume, 1)
    data = {
        "id": used["edge_id"].astype(str).tolist(),
        "volume": [int(v) if v.is_integer() else v for v in rounded.tolist()],
        "heading": headings.tolist(),
        "lane": used["has_dedicated_lane"].to_numpy(dtype=int).tolist(),
        "step": np.asarray(steps)[classes].tolist(),
        "coords": _flat_coords(lines),
    }
    legend = [
        (_line_swatch(ROUTE_RAMP[step], ROUTE_WEIGHTS[step]), f"{text} trips")
        for step, text in zip(steps, class_labels)
    ]
    return RouteLayer(json.dumps(data, separators=(",", ":")), legend, label, notes, len(used))


def stations_geojson(stations: pd.DataFrame) -> dict:
    """Stations as GeoJSON points with ``station_id`` and ``name``."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"station_id": str(station_id), "name": str(name)},
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            }
            for station_id, name, lat, lon in zip(
                stations["station_id"], stations["name"], stations["lat"], stations["lon"]
            )
        ],
    }


def map_bounds(
    stations: pd.DataFrame | None, edges: gpd.GeoDataFrame | None
) -> list[list[float]] | None:
    """South-west and north-east corners covering every station and edge, or None."""
    lats: list[float] = []
    lons: list[float] = []
    if stations is not None and not stations.empty:
        lats += [float(stations["lat"].min()), float(stations["lat"].max())]
        lons += [float(stations["lon"].min()), float(stations["lon"].max())]
    if edges is not None and not edges.empty:
        lonlat = edges if edges.crs is None else edges.to_crs("EPSG:4326")
        min_lon, min_lat, max_lon, max_lat = lonlat.total_bounds
        lats += [float(min_lat), float(max_lat)]
        lons += [float(min_lon), float(max_lon)]
    if not lats:
        return None
    return [[min(lats), min(lons)], [max(lats), max(lons)]]


# ---------------------------------------------------------------- legend


def _line_swatch(color: str, weight: float) -> str:
    return (
        f'<span style="display:inline-block;width:22px;border-top:{weight}px solid {color};'
        'vertical-align:middle"></span>'
    )


def _dot_swatch(color: str) -> str:
    return (
        '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
        f"background:{color};border:1.5px solid #fff;box-shadow:0 0 0 1px {color};"
        'vertical-align:middle"></span>'
    )


def _hexagon_swatch(color: str) -> str:
    return f'<span style="color:{color};font-size:15px;vertical-align:middle">&#11042;</span>'


def _area_swatch(color: str) -> str:
    return (
        f'<span style="display:inline-block;width:14px;height:10px;background:{color}66;'
        f'border:1px solid {color};vertical-align:middle"></span>'
    )


def legend_html(entries: list[tuple[str, str]], note: str = "") -> str:
    """HTML for the map legend: one row per (swatch HTML, label) pair, then an optional note."""
    rows = "".join(
        f'<div style="display:flex;align-items:center;gap:8px;margin:3px 0">'
        f'<span style="width:22px;text-align:center">{swatch}</span>{escape(label)}</div>'
        for swatch, label in entries
    )
    note_html = (
        f'<div style="margin-top:6px;max-width:220px;color:#495057">{escape(note)}</div>'
        if note
        else ""
    )
    return (
        '<div style="background:#fff;color:#212529;padding:8px 10px;border-radius:6px;'
        'box-shadow:0 1px 4px rgba(0,0,0,.3);font:12px/1.35 system-ui,sans-serif">'
        f'<div style="font-weight:600;margin-bottom:4px">Legend</div>{rows}{note_html}</div>'
    )


class MapLegend(MacroElement):
    """A Leaflet control in the map's bottom-right corner holding :func:`legend_html`."""

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = L.control({position: "bottomright"});
        {{ this.get_name() }}.onAdd = function () {
            var div = L.DomUtil.create("div");
            div.innerHTML = {{ this.html|tojson }};
            L.DomEvent.disableScrollPropagation(div);
            return div;
        };
        {{ this.get_name() }}.addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, html: str) -> None:
        super().__init__()
        self._name = "MapLegend"
        self.html = html


class _InlineDataLayer(MacroElement):
    """A layer whose (possibly multi-megabyte) JSON text is written into the page as is.

    ``folium.GeoJson`` would parse and re-serialise it on every Streamlit rerun, which
    takes seconds for a city-wide network.
    """

    def render(self, **kwargs) -> None:
        # MacroElement.render wraps the finished script in a new Jinja template, which
        # means re-parsing megabytes of coordinates on every rerun. Insert it as data.
        script = Element("{{ this.code }}")
        script.code = self._template.module.script(self, kwargs)
        self.get_root().script.add_child(script, name=self.get_name())


class LaneStatusLayer(_InlineDataLayer):
    """One Leaflet GeoJSON layer with every directed edge, coloured by lane status.

    Takes the text from :func:`lane_status_geojson`. The layer does not react to the
    mouse: checking 100,000+ lines on every mouse move makes the map lag.
    """

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = L.geoJson({{ this.geojson }}, {
            style: {{ this.style }},
            interactive: false
        }).addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, geojson: str, name: str = "Bike-lane status") -> None:
        super().__init__()
        self._name = "LaneStatusLayer"
        self.layer_name = name
        self.geojson = geojson
        self.style = LANE_STYLE_JS


class RouteVolumeLayer(_InlineDataLayer):
    """Route volume per directed edge, from :func:`route_volume_layer`.

    Colour and width come from each edge's volume class, and hovering shows the layer
    label (synthetic or observed), edge ID, direction, volume and lane status. The
    tooltip text is built only when hovered, so the page carries no per-edge text.
    """

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = (function () {
            var d = {{ this.data }};
            var colors = {{ this.colors|tojson }}, weights = {{ this.weights|tojson }};
            var label = {{ this.label|tojson }};
            var esc = function (s) {
                return String(s).replace(/[&<>"']/g, function (c) {
                    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
                });
            };
            var tooltip = function (line) {
                var i = line.bubiIndex, id = String(d.id[i]), parts = id.split("-");
                var nodes = parts.length === 3 ? "node " + parts[0] + " → " + parts[1] + ", " : "";
                return "<b>" + esc(label) + "</b><br>" +
                    "Edge " + esc(id) + "<br>" +
                    "Direction: " + esc(nodes + "heading " + d.heading[i]) + "<br>" +
                    "Trips: " + esc(d.volume[i].toLocaleString()) + "<br>" +
                    "Bike lane in this direction: " + (d.lane[i] ? "yes" : "no");
            };
            var group = L.featureGroup();
            for (var i = 0; i < d.id.length; i++) {
                var c = d.coords[i], points = [];
                for (var j = 0; j < c.length; j += 2) points.push([c[j + 1], c[j]]);
                var line = L.polyline(points, {
                    color: colors[d.step[i]], weight: weights[d.step[i]], opacity: 0.85
                });
                line.bubiIndex = i;
                line.bindTooltip(tooltip, {sticky: true});
                group.addLayer(line);
            }
            return group;
        })().addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    def __init__(self, layer: RouteLayer, name: str = "Route volume") -> None:
        super().__init__()
        self._name = "RouteVolumeLayer"
        self.layer_name = name
        self.data = layer.data
        self.label = layer.label
        self.colors = list(ROUTE_RAMP)
        self.weights = list(ROUTE_WEIGHTS)


# ---------------------------------------------------------------- map


def build_map(
    data: DashboardData,
    settings: Settings,
    lane_geojson: str | None = None,
    route_layer: RouteLayer | None = None,
) -> tuple[folium.Map, list[str]]:
    """Draw the enabled layers. Returns the map and notes about anything not drawn.

    ``lane_geojson`` is the output of :func:`lane_status_geojson` and ``route_layer`` of
    :func:`route_volume_layer` for ``settings.scenario``; pass cached copies to avoid
    rebuilding them. The map opens zoomed to every station and edge.
    """
    notes: list[str] = []
    legend: list[tuple[str, str]] = []
    stations = data.get("stations")
    edges = data.get("edges")
    scenario = settings.scenario

    # Canvas draws tens of thousands of lines much faster than one SVG element per line.
    fmap = folium.Map(
        location=BUDAPEST_CENTER, zoom_start=12, prefer_canvas=True, **BASEMAPS[settings.basemap]
    )
    bounds = map_bounds(stations, edges)
    if bounds is not None:
        fmap.fit_bounds(bounds)

    population = data.get("population")
    if settings.show_population and population is not None and not population.empty:
        layer = folium.FeatureGroup(name="Population (H3)")
        max_pop = float(population["population"].max()) or 1.0
        skipped = 0
        for _, row in population.iterrows():
            if cell_center(row["cell_id"]) is None:
                skipped += 1
                continue
            folium.Polygon(
                locations=h3.cell_to_boundary(row["cell_id"]),
                color=POPULATION_COLOR,
                weight=0.5,
                fill=True,
                fill_opacity=0.15 + 0.5 * row["population"] / max_pop,
                tooltip=f"Population: {row['population']:.0f}",
            ).add_to(layer)
        layer.add_to(fmap)
        legend.append((_area_swatch(POPULATION_COLOR), "Population (darker = more people)"))
        if skipped:
            notes.append(f"{skipped} population cell(s) have an invalid H3 id and are not drawn.")

    if settings.show_lanes and not edges.empty:
        geojson = lane_geojson if lane_geojson is not None else lane_status_geojson(edges)
        fmap.add_child(LaneStatusLayer(geojson))
        legend.append((_line_swatch(LANE_COLOR, LANE_WEIGHT), "Bike lane in this direction"))
        legend.append(
            (_line_swatch(NO_LANE_COLOR, NO_LANE_WEIGHT), "No bike lane in this direction")
        )

    routes = for_scenario(data.get("routes"), scenario)
    route_shown = False
    if settings.show_routes and not routes.empty:
        if route_layer is None:
            route_layer = route_volume_layer(edges, routes)
        notes.extend(route_layer.notes)
        if route_layer.legend:
            fmap.add_child(RouteVolumeLayer(route_layer))
            legend.extend(route_layer.legend)
            route_shown = True

    corridors = for_scenario(data.get("corridors"), scenario)
    if settings.show_corridors and not corridors.empty:
        top = corridors.sort_values("rank").head(settings.top_n)
        layer = folium.FeatureGroup(name="Top corridors")
        edges_by_id = edges.set_index("edge_id")
        for _, corridor in top.iterrows():
            for edge_id in as_id_list(corridor["edge_ids"]):
                if edge_id not in edges_by_id.index:
                    notes.append(
                        f"Corridor {corridor['corridor_id']} uses unknown edge `{edge_id}`."
                    )
                    continue
                folium.PolyLine(
                    offset_line(list(edges_by_id.loc[edge_id].geometry.coords)),
                    color=GAP_COLOR,
                    weight=7,
                    opacity=0.9,
                    tooltip=(
                        f"Corridor {corridor['corridor_id']} · rank {corridor['rank']} · "
                        f"edge {edge_id} · score {corridor['score']:.0f}"
                    ),
                ).add_to(layer)
        layer.add_to(fmap)
        legend.append((_line_swatch(GAP_COLOR, 6), "Priority corridor (missing lane)"))

    if settings.show_stations and not stations.empty:
        # One GeoJSON layer: a separate Folium marker per station adds about 1 s per rerun
        # for Budapest's ~700 stations.
        folium.GeoJson(
            stations_geojson(stations),
            name="Existing stations",
            marker=folium.CircleMarker(
                radius=6,
                color="#ffffff",
                weight=1.5,
                fill=True,
                fill_color=STATION_COLOR,
                fill_opacity=0.95,
            ),
            tooltip=folium.GeoJsonTooltip(fields=["name", "station_id"], aliases=["Station", "ID"]),
        ).add_to(fmap)
        legend.append((_dot_swatch(STATION_COLOR), "Existing station"))

    candidates = proposed_stations(data, scenario)
    if settings.show_proposed and not candidates.empty:
        layer = folium.FeatureGroup(name="Proposed stations")
        skipped = 0
        for _, row in candidates.iterrows():
            center = cell_center(row["cell_id"])
            if center is None:
                skipped += 1
                continue
            folium.RegularPolygonMarker(
                location=center,
                number_of_sides=6,
                radius=9,
                color="#ffffff",
                weight=1.5,
                fill_color=PROPOSED_COLOR,
                fill_opacity=0.95,
                tooltip=(
                    f"Proposed new:{row['cell_id']} · rank {row['rank']} · "
                    f"population {row['population']:.0f} · score {row['score']:.2f}"
                ),
            ).add_to(layer)
        layer.add_to(fmap)
        legend.append((_hexagon_swatch(PROPOSED_COLOR), "Proposed station (H3 cell centre)"))
        if skipped:
            notes.append(f"{skipped} proposed station(s) have an invalid H3 id and are not drawn.")

    if legend:
        note = []
        if settings.show_lanes or route_shown:
            note.append(
                "Each direction of a street is drawn on the right-hand side of travel, so a "
                "two-way street shows two lines."
            )
        if route_shown:
            note.append(f"Route volume, darker and wider = more trips. {route_layer.label}.")
        fmap.add_child(MapLegend(legend_html(legend, " ".join(note))))
    return fmap, notes


# ---------------------------------------------------------------- page sections


def render_header(data: DashboardData | None) -> None:
    left, right = st.columns([3, 1])
    left.title("🚲 MOL Bubi Bike-Lane & Station Recommendation Tool")
    if data is None:
        return
    source = {
        "fixtures": "sample fixtures",
        "processed": "pipeline outputs",
        "mixed": "pipeline outputs + sample fixtures",
    }[data.source]
    right.warning(f"**Synthetic demo data** (D5) · {source}")


def render_sidebar(config: dict) -> Settings:
    sidebar = st.sidebar
    sidebar.header("Scenario")
    active = config.get("scenarios", {}).get("active") or list(SCENARIOS)
    scenario = sidebar.radio(
        "Active scenario",
        options=active,
        format_func=lambda s: s,
        help="\n\n".join(f"**{s}**: {SCENARIO_HELP.get(s, '')}" for s in active),
        label_visibility="collapsed",
    )
    sidebar.checkbox("Show difference vs baseline", value=False, disabled=True, help="Week 5")

    sidebar.divider()
    sidebar.header("Map layers")
    settings = Settings(
        scenario=scenario,
        basemap=sidebar.selectbox(
            "Basemap",
            options=list(BASEMAPS),
            help="The light grey basemap makes the lane colours easier to read on a projector.",
        ),
        show_stations=sidebar.checkbox("Existing stations", value=True),
        show_proposed=sidebar.checkbox("Proposed stations", value=True),
        show_population=sidebar.checkbox("Population (H3 cells)", value=False),
        show_lanes=sidebar.checkbox("Bike-lane coverage", value=True),
        show_routes=sidebar.checkbox("Synthetic routes", value=False),
        show_corridors=sidebar.checkbox("Top corridors", value=True),
        top_n=sidebar.slider("Top corridors to show", min_value=1, max_value=50, value=10),
    )

    sidebar.divider()
    sidebar.header("Run parameters")
    sidebar.caption("Read-only, from `config/default_config.yaml`")
    scoring = config.get("station_scoring", {})
    spatial = config.get("spatial", {})
    network = config.get("network", {})
    project = config.get("project", {})
    sidebar.markdown(
        f"- Walk coverage: {scoring.get('walk_coverage_threshold_m', '–')} m\n"
        f"- Proposed stations N: {scoring.get('candidate_n', '–')}\n"
        f"- Min spacing: {scoring.get('min_spacing_m', '–')} m\n"
        f"- Seed: {project.get('random_seed', '–')} · H3 res {spatial.get('h3_resolution', '–')}\n"
        f"- OSM graph: {network.get('frozen_graph_version', '–')}"
    )
    return settings


def render_metrics(data: DashboardData, scenario: str) -> None:
    stations = data.get("stations")
    candidates = proposed_stations(data, scenario)
    corridors = for_scenario(data.get("corridors"), scenario)
    routes = for_scenario(data.get("routes"), scenario)
    edges = data.get("edges")

    corridor_edges = edges[edges["edge_id"].isin(edge_ids_of_corridors(corridors))]
    corridor_km = corridor_edges.loc[~corridor_edges["has_dedicated_lane"], "length_m"].sum() / 1000

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stations (existing + proposed)", f"{len(stations)} + {len(candidates)}")
    c2.metric(
        "Population in proposed cells",
        f"{candidates['population'].sum():,.0f}" if not candidates.empty else "–",
        help="Newly served population is computed in week 5.",
    )
    c3.metric("Corridor km without a lane", f"{corridor_km:.2f} km")
    c4.metric(
        "Synthetic trips",
        f"{routes['trip_count'].sum():,.0f}" if not routes.empty else "–",
    )


def render_detail_panel(map_state: dict | None) -> None:
    st.markdown("#### Selected recommendation")
    clicked = (map_state or {}).get("last_object_clicked_tooltip")
    if clicked:
        st.info(clicked)
    else:
        st.caption("Click a corridor or station on the map.")
    st.caption(
        "Week 4: full score breakdown here (volume × gap length × continuity, or "
        "population × lane connectivity) and the robustness label."
    )


def render_scenario_comparison(data: DashboardData, settings: Settings) -> None:
    st.subheader("Scenario comparison")
    st.caption(
        "One map per scenario with the layers selected in the sidebar, except the street "
        "network and route volume: drawing them four times would slow the page down, so they "
        "appear on the main map only. Week 5 adds demand per newly served person, people served per km "
        "of new corridor, and robust vs station-dependent corridors. Counts below come from the "
        "loaded tables."
    )
    for column, scenario in zip(st.columns(len(SCENARIOS)), SCENARIOS):
        with column:
            st.markdown(f"**{scenario}**")
            fmap, _ = build_map(
                data, replace(settings, scenario=scenario, show_lanes=False, show_routes=False)
            )
            st_folium(
                fmap,
                height=300,
                use_container_width=True,
                returned_objects=[],
                key=f"comparison_map_{scenario}",
            )

    rows = []
    for scenario in SCENARIOS:
        corridors = for_scenario(data.get("corridors"), scenario)
        routes = for_scenario(data.get("routes"), scenario)
        rows.append(
            {
                "scenario": scenario,
                "proposed stations": len(proposed_stations(data, scenario)),
                "corridors": len(corridors),
                "synthetic trips": float(routes["trip_count"].sum()) if not routes.empty else 0.0,
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def export_csv(table: pd.DataFrame) -> bytes:
    """A table as UTF-8 CSV for download.

    ``edge_ids`` is written as a JSON array, the contract's string form. A list read
    back from Parquet is a NumPy array, and pandas would otherwise write it as
    ``['a-b-0' 'b-c-0']``, which spreadsheets and other tools cannot parse.
    """
    if "edge_ids" in table:
        table = table.assign(edge_ids=table["edge_ids"].map(lambda v: json.dumps(as_id_list(v))))
    return table.to_csv(index=False).encode("utf-8")


def render_tables(data: DashboardData, scenario: str) -> None:
    corridors = for_scenario(data.get("corridors"), scenario)
    candidates = for_scenario(data.get("station_candidates"), scenario)
    tab1, tab2, tab3 = st.tabs(["Top corridors", "Station candidates", "Methodology & limitations"])

    with tab1:
        if corridors.empty:
            st.write("No corridors for this scenario.")
        else:
            table = corridors.sort_values("rank")
            st.dataframe(table, hide_index=True, width="stretch")
            st.download_button(
                "📥 Export corridors (CSV)",
                export_csv(table),
                f"corridors_{scenario}.csv",
                "text/csv",
            )

    with tab2:
        if candidates.empty:
            st.write("No proposed stations in this scenario.")
        else:
            table = candidates.sort_values("rank")
            st.caption("Candidates without a rank were not selected as new stations.")
            st.dataframe(table, hide_index=True, width="stretch")
            st.download_button(
                "📥 Export station candidates (CSV)",
                export_csv(table),
                f"station_candidates_{scenario}.csv",
                "text/csv",
            )

    with tab3:
        st.markdown(
            "- Synthetic trips, routes and corridor rankings are an algorithm demonstration, "
            "not evidence of real cyclist behaviour (D5).\n"
            "- Demand is driven by population only, with no time-of-day effects (D8).\n"
            "- Routing prefers flat and downhill roads and ignores traffic and existing lanes (D2).\n"
            "- Station scores ignore legal, land-use and construction feasibility (D4).\n"
            "- Scenario results are a comparison, not a forecast.\n\n"
            "The full methodology appendix is added in week 6."
        )


# ---------------------------------------------------------------- entry point


def main() -> None:
    st.set_page_config(
        page_title="MOL Bubi Bike-Lane & Station Recommender",
        page_icon="🚲",
        layout="wide",
    )
    try:
        config = load_config()
    except DashboardDataError as err:
        st.warning(str(err))
        config = {}
    settings = render_sidebar(config)

    cache_key = (os.environ.get(DATA_DIR_ENV), _latest_change())
    try:
        data = _cached_load(*cache_key)
    except DashboardDataError as err:
        render_header(None)
        st.error(f"**The dashboard cannot start because of a data problem.**\n\n{err}")
        st.stop()

    render_header(data)
    for warning in data.warnings:
        st.warning(warning)

    render_metrics(data, settings.scenario)

    started = time.perf_counter()
    lane_geojson = _cached_lane_geojson(*cache_key) if settings.show_lanes else None
    route_layer = (
        _cached_route_layer(*cache_key, settings.scenario) if settings.show_routes else None
    )
    fmap, notes = build_map(data, settings, lane_geojson, route_layer)
    map_state = st_folium(
        fmap,
        height=560,
        use_container_width=True,
        returned_objects=["last_object_clicked_tooltip"],
    )
    st.caption(
        f"{len(data.get('edges')):,} directed street edges · map prepared on the server in "
        f"{time.perf_counter() - started:.1f} s (the browser needs extra time to draw it)."
    )
    st.caption(DATA_ATTRIBUTION)
    for note in fixture_notes(data) + notes:
        st.caption(f"⚠️ {note}")
    render_detail_panel(map_state)

    render_scenario_comparison(data, settings)
    render_tables(data, settings.scenario)


if __name__ == "__main__":
    main()
