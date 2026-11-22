"""OSM Street & Walking network extraction and per-direction bike-lane model."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString, MultiLineString, box
from shapely.geometry.base import BaseGeometry

REQUIRED_WAY_TAGS = (
    "bicycle",
    "bicycle:lanes",
    "cycleway",
    "cycleway:left",
    "cycleway:right",
    "cycleway:both",
    "cycleway:left:oneway",
    "cycleway:right:oneway",
    "cycleway:both:oneway",
    "highway",
    "lanes:forward",
    "oneway",
    "oneway:bicycle",
)
DESIGNATED_FOOTWAY_FILTER = '["highway"="footway"]["bicycle"="designated"]'
# Values OSMnx reverses the node order for, see OSMnx `_is_path_reversed`.
REVERSED_ONEWAY_VALUES = {"-1", "reverse", "T"}
SIDE_TAG_PAIRS = (
    ("cycleway:left", "cycleway:right"),
    ("cycleway:left:oneway", "cycleway:right:oneway"),
)
# Tags the local-file network filter reads. They are not needed for the
# Overpass path, which filters server-side.
FILTER_WAY_TAGS = (
    "foot",
    "sidewalk",
    "sidewalk:both",
    "sidewalk:left",
    "sidewalk:right",
)
# Same exclusions as OSMnx's Overpass presets, applied here because a local
# extract arrives unfiltered.
BIKE_HIGHWAY_EXCLUDED = re.compile(
    r"abandoned|bus_guideway|construction|corridor|elevator|escalator|footway|motor|no|"
    r"planned|platform|proposed|raceway|razed|rest_area|services|steps"
)
WALK_HIGHWAY_EXCLUDED = re.compile(
    r"abandoned|bus_guideway|construction|cycleway|motor|no|planned|platform|"
    r"proposed|raceway|razed|rest_area|services"
)
WALK_SEPARATE_SIDEWALKS = ("sidewalk", "sidewalk:both", "sidewalk:left", "sidewalk:right")


def _keep_way(data: dict, network_type: str, include_designated_footways: bool) -> bool:
    """Whether a way belongs to the requested OSMnx network preset."""
    highway = _dict_tag(data, "highway")
    if not highway:
        return False

    if network_type == "bike":
        is_designated_footway = (
            include_designated_footways
            and highway == "footway"
            and _dict_tag(data, "bicycle") == "designated"
        )
        if is_designated_footway:
            return True
        return not (
            BIKE_HIGHWAY_EXCLUDED.search(highway)
            or _dict_tag(data, "area") == "yes"
            or _dict_tag(data, "access") == "private"
            or _dict_tag(data, "bicycle") == "no"
            or _dict_tag(data, "service") == "private"
        )

    if network_type == "walk":
        return not (
            WALK_HIGHWAY_EXCLUDED.search(highway)
            or _dict_tag(data, "area") == "yes"
            or _dict_tag(data, "access") == "private"
            or _dict_tag(data, "foot") == "no"
            or _dict_tag(data, "service") == "private"
            or any(_dict_tag(data, key) == "separate" for key in WALK_SEPARATE_SIDEWALKS)
        )

    raise ValueError(f"Unsupported network_type for a local extract: {network_type}")


def _filter_graph_to_network(
    graph: nx.MultiDiGraph,
    network_type: str,
    include_designated_footways: bool = True,
) -> nx.MultiDiGraph:
    """Drop ways outside the requested preset after reading a local extract."""
    drop = [
        (u, v, key)
        for u, v, key, data in graph.edges(keys=True, data=True)
        if not _keep_way(data, network_type, include_designated_footways)
    ]
    graph.remove_edges_from(drop)
    graph.remove_nodes_from(list(nx.isolates(graph)))
    return graph


def _local_network(
    path: Path,
    bbox: tuple[float, float, float, float],
    network_type: str,
    include_designated_footways: bool = True,
) -> nx.MultiDiGraph:
    """Load, filter and clip a local extract in one step."""
    graph = load_osm_graph(path, network_type=network_type)
    graph = _filter_graph_to_network(graph, network_type, include_designated_footways)
    return ox.truncate.truncate_graph_polygon(graph, box(*bbox))


def build_street_network(
    bbox: tuple[float, float, float, float],
    network_type: str = "bike",
    elevation_dem_path: Optional[Path] = None,
    include_designated_footways: bool = True,
    source_path: Optional[Path] = None,
) -> tuple[nx.MultiDiGraph, gpd.GeoDataFrame]:
    """Build the Budapest street network and its per-direction lane model.

    Args:
        bbox: (min_lon, min_lat, max_lon, max_lat)
        network_type: "bike" or "all"
        elevation_dem_path: Optional path to elevation raster (DEM) to add grades.
        include_designated_footways: Keep highway=footway + bicycle=designated
            ways in the bike network, where OSMnx's bike filter drops them.
        source_path: Local OSM XML extract to read instead of downloading.
            Supported for network_type="bike"; use build_walk_network for the
            walking graph. OSMnx cannot read PBF, so clip the Geofabrik
            extract with `osmium` first.

    Returns:
        Tuple of (NetworkX directed graph, GeoDataFrame adhering to EdgesSchema).
    """

    if source_path is not None:
        if network_type != "bike":
            raise ValueError("source_path is supported for network_type='bike' only")
        path = Path(source_path)
        graph = _local_network(path, bbox, network_type, include_designated_footways)
        return postprocess_graph(graph, reversed_way_ids=_reversed_way_ids(path))

    custom_filter = None
    if network_type == "bike" and include_designated_footways:
        # The bike preset drops highway=footway, so ask for the shared paths
        # it would lose. The filter list is a union, not an intersection.
        from osmnx._overpass import _get_network_filter

        custom_filter = [_get_network_filter("bike"), DESIGNATED_FOOTWAY_FILTER]

    original_tags = ox.settings.useful_tags_way
    ox.settings.useful_tags_way = list(dict.fromkeys([*original_tags, *REQUIRED_WAY_TAGS]))
    try:
        G = ox.graph.graph_from_bbox(
            bbox=bbox,
            network_type=network_type,
            simplify=False,
            retain_all=True,
            custom_filter=custom_filter,
        )
    finally:
        ox.settings.useful_tags_way = original_tags

    return postprocess_graph(G)


def build_walk_network(
    bbox: tuple[float, float, float, float],
    source_path: Optional[Path] = None,
) -> nx.MultiDiGraph:
    """Build the walking network, preferring a local extract over a download."""
    if source_path is not None:
        return _local_network(Path(source_path), bbox, "walk")

    return ox.graph.graph_from_bbox(
        bbox=bbox,
        network_type="walk",
        simplify=False,
        retain_all=True,
    )


def load_osm_graph(path: Path, network_type: str = "bike") -> nx.MultiDiGraph:
    """Read a local OSM XML extract with the tags the network filters need."""
    if path.suffix.lower() not in {".osm", ".xml"}:
        raise ValueError(
            f"{path} is not OSM XML. OSMnx cannot read PBF; clip the Geofabrik "
            "extract with `osmium extract --bbox ... -o extract.osm` first."
        )

    extra_tags = (*REQUIRED_WAY_TAGS, *FILTER_WAY_TAGS)
    original_tags = ox.settings.useful_tags_way
    ox.settings.useful_tags_way = list(dict.fromkeys([*original_tags, *extra_tags]))
    try:
        return ox.graph.graph_from_xml(
            str(path),
            bidirectional=network_type == "walk",
            simplify=False,
            retain_all=True,
        )
    finally:
        ox.settings.useful_tags_way = original_tags


def _reversed_way_ids(path: Path) -> set[int]:
    """Way ids whose node order OSMnx flips (`oneway=-1`, `reverse`, `T`)."""
    way_ids: set[int] = set()
    for _, element in ET.iterparse(str(path), events=("end",)):
        if element.tag == "way":
            oneway = next(
                (tag.get("v", "") for tag in element.findall("tag") if tag.get("k") == "oneway"),
                "",
            )
            if oneway.strip() in REVERSED_ONEWAY_VALUES:
                way_ids.add(int(element.get("id")))
            element.clear()
        elif element.tag in {"node", "relation"}:
            # Keep tag children until their parent is read, then free them.
            element.clear()
    return way_ids


def _remap_way_sides(graph: nx.MultiDiGraph, way_ids: set[int]) -> None:
    """Swap left/right tags on ways OSMnx reversed.

    OSMnx flips the node order so the edge runs in the traffic direction, but
    `cycleway:left` and `cycleway:right` still describe the drawn way. Swapping
    them makes the tags relative to the edge the rest of the parser sees.
    """
    if not way_ids:
        return
    for _, _, _, data in graph.edges(keys=True, data=True):
        osmids = data.get("osmid")
        if isinstance(osmids, list):
            matches = any(osmid in way_ids for osmid in osmids)
        else:
            matches = osmids in way_ids
        if not matches:
            continue
        for left, right in SIDE_TAG_PAIRS:
            left_value = data.pop(left, None)
            right_value = data.pop(right, None)
            if left_value is not None:
                data[right] = left_value
            if right_value is not None:
                data[left] = right_value


def postprocess_graph(
    graph: nx.MultiDiGraph,
    reversed_way_ids: Optional[set[int]] = None,
) -> tuple[nx.MultiDiGraph, gpd.GeoDataFrame]:
    """Add contraflow bicycle edges and extract the per-direction edges table."""
    _remap_way_sides(graph, reversed_way_ids or set())
    _add_bicycle_reverse_edges(graph)
    return graph, extract_per_direction_edges(graph)


def extract_per_direction_edges(graph: nx.MultiDiGraph) -> gpd.GeoDataFrame:
    """Extract directed edges with per-direction has_dedicated_lane flag."""

    # Convert graph edges to a GeoDataFrame.
    edges = ox.convert.graph_to_gdfs(
        graph,
        nodes=False,
        edges=True,
        fill_edge_geometry=True,
    )

    if edges.empty:
        raise ValueError("No street edges found within the bounding box.")

    # Move u, v and key from the MultiIndex into regular columns.
    edges = edges.reset_index()

    # Construct unique directed edge identifiers.
    edges["edge_id"] = (
        edges["u"].astype(str) + "-" + edges["v"].astype(str) + "-" + edges["key"].astype(str)
    )

    # Extract the original OSM way ID.
    # simplify=False ensures one OSM way per edge.
    edges["osm_way_id"] = edges["osmid"].map(int).astype("int64")

    # Calculate edge lengths in the projected CRS.
    # The original geometry remains in EPSG:4326.
    edges_metric = edges.to_crs(epsg=23700)
    edges["length_m"] = edges_metric.geometry.length.astype("float64")

    # Evaluate dedicated lane availability for each directed edge.
    edges["has_dedicated_lane"] = edges.apply(
        lambda edge: bool(_has_dedicated_lane(edge)),
        axis=1,
    )

    # Keep only the requested fields.
    output_columns = [
        "edge_id",
        "osm_way_id",
        "length_m",
        "has_dedicated_lane",
        "geometry",
    ]

    result = gpd.GeoDataFrame(
        edges[output_columns].copy(),
        geometry="geometry",
        crs="EPSG:4326",
    )

    return result


def _get_tag(edge: pd.Series, key: str) -> str:
    """Get and normalize an OSM tag from an edge Series."""
    value = edge.get(key)

    if value is None or pd.isna(value):
        return ""

    return str(value).strip().lower()


DEDICATED = {"lane", "track"}
LEGACY_CONTRAFLOW = {"opposite_lane", "opposite_track"}
ONEWAY_VALUES = {"true", "yes", "1"}


def _side_facility(edge: pd.Series, side: str) -> str:
    """First tag that decides this side, in precedence order.

    A side-specific value wins even when it is `no`: that is what stops an
    explicit `cycleway:right=no` from falling back to `cycleway=lane`.
    """
    for key in (f"cycleway:{side}", "cycleway:both", "cycleway"):
        value = _get_tag(edge, key)
        if value:
            return value
    return ""


def _lanes_designated(edge: pd.Series, side: str) -> bool:
    """True when bicycle:lanes marks a designated lane on this side.

    B1 packs the layout into :lanes. The values run left to right, so the last
    lanes:forward values are the right side; the rest belong to the left side.
    """
    raw = _get_tag(edge, "bicycle:lanes")
    if not raw:
        return False
    values = [value.strip() for value in raw.split("|")]
    if _get_tag(edge, "oneway") in ONEWAY_VALUES:
        return side == "right" and "designated" in values
    forward = _get_tag(edge, "lanes:forward")
    if not forward.isdigit():
        return False
    split = len(values) - int(forward)
    if split <= 0:
        return False
    window = values[split:] if side == "right" else values[:split]
    return "designated" in window


def _side_serves(edge: pd.Series, side: str, value: str, oneway: bool) -> str:
    """Direction a side facility serves: `+`, `-`, `both`, or `` for none."""
    if value in LEGACY_CONTRAFLOW:
        return "-"
    side_oneway = _get_tag(edge, f"cycleway:{side}:oneway")
    if side_oneway in {"yes", "1"}:
        return "+"
    if side_oneway == "no":
        return "both"
    if side_oneway == "-1":
        return "-"
    if oneway:
        if _get_tag(edge, "oneway:bicycle") == "no":
            # M1: the left lane is the contraflow lane. T3: the track itself
            # is bidirectional while the carriageway stays one-way.
            if value == "track":
                return "both"
            return "-" if side == "left" else "+"
        # Both sides of a one-way street flow with the traffic direction (M2b).
        return "+"
    return "+" if side == "right" else "-"


def _has_dedicated_lane(edge: pd.Series) -> bool:
    """True when this directed edge has a dedicated lane or track.

    `reversed` is OSMnx's marker for the mirror edge of a two-way way, and for
    the contraflow edge this module adds. Every other edge runs with the way.
    """
    direction = "-" if _get_tag(edge, "reversed") == "true" else "+"
    oneway = _get_tag(edge, "oneway") in ONEWAY_VALUES
    highway = _get_tag(edge, "highway")
    if highway == "cycleway" or (
        highway in {"path", "footway"} and _get_tag(edge, "bicycle") == "designated"
    ):
        return direction == "+" or not oneway or _get_tag(edge, "oneway:bicycle") == "no"

    for side in ("left", "right"):
        value = _side_facility(edge, side)
        if value in DEDICATED or value in LEGACY_CONTRAFLOW:
            serves = _side_serves(edge, side, value, oneway)
        elif not value and _lanes_designated(edge, side):
            serves = _side_serves(edge, side, "lane", oneway)
        else:
            continue
        if serves in {direction, "both"}:
            return True
    return False


"""
For adding missing cycling edges
"""


CONTRAFLOW_FACILITY = LEGACY_CONTRAFLOW | {"opposite"}


def _dict_tag(data: dict, key: str) -> str:
    value = data.get(key)
    return "" if value is None else str(value).strip().lower()


def _allows_bicycle_contraflow(data: dict) -> bool:
    """Whether cyclists may travel against a one-way way and need the reverse edge."""
    if _dict_tag(data, "oneway:bicycle") == "no":
        return True
    if any(
        _dict_tag(data, f"cycleway:{side}:oneway") == "-1" for side in ("left", "right", "both")
    ):
        return True
    return any(
        _dict_tag(data, key) in CONTRAFLOW_FACILITY
        for key in ("cycleway", "cycleway:left", "cycleway:right", "cycleway:both")
    )


def _is_oneway(value: object) -> bool:
    """Handle both OSM tag strings and OSMnx boolean values."""
    return value is True or str(value).strip().lower() in {"yes", "true", "1"}


def _same_osm_way(osmid_1: int | None, osmid_2: int | None) -> bool:
    """Check whether two edges belong to the same OSM way."""
    if osmid_1 is None or osmid_2 is None:
        return False
    else:
        return osmid_1 == osmid_2


def _reverse_geometry(geom: BaseGeometry | None) -> BaseGeometry | None:
    """Reverse the coordinate order of an edge geometry."""
    if geom is None:
        return geom

    if geom.geom_type == "LineString":
        return LineString(list(geom.coords)[::-1])

    if geom.geom_type == "MultiLineString":
        return MultiLineString(
            [LineString(list(line.coords)[::-1]) for line in reversed(geom.geoms)]
        )

    return geom


def _add_bicycle_reverse_edges(G: nx.MultiDiGraph):
    """
    Add the missing reverse edge when a one-way way still lets cyclists ride
    against the traffic: oneway:bicycle=no, a contraflow side lane, or the
    legacy opposite_lane/opposite_track/opposite values.

    Returns the number of edges added.
    """

    edges_to_add = []

    # Make a snapshot because we will modify the graph afterwards.
    for u, v, key, data in list(G.edges(keys=True, data=True)):
        # Check the OSM one-way and bicycle-specific tags.
        if not _is_oneway(data.get("oneway")):
            continue

        if not _allows_bicycle_contraflow(data):
            continue

        # Check whether the reverse edge for this same OSM way exists.
        reverse_edges = G.get_edge_data(v, u, default={})

        already_exists = any(
            _same_osm_way(data.get("osmid"), reverse_data.get("osmid"))
            for reverse_data in reverse_edges.values()
        )

        if already_exists:
            continue

        # Copy the original edge attributes.
        reverse_data = data.copy()

        # The reverse edge runs in the opposite direction of the OSM way.
        reverse_data["reversed"] = not bool(data.get("reversed", False))

        # Reverse geometry if it is already present.
        if reverse_data.get("geometry") is not None:
            reverse_data["geometry"] = _reverse_geometry(reverse_data["geometry"])

        # Queue the new edge for insertion.
        edges_to_add.append((v, u, reverse_data))

    # Add the edges after iteration.
    for u, v, data in edges_to_add:
        G.add_edge(u, v, **data)

    return len(edges_to_add)
