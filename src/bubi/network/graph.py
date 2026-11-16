"""OSM Street & Walking network extraction and per-direction bike-lane model."""

from pathlib import Path
from typing import Optional

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString, MultiLineString
from shapely.geometry.base import BaseGeometry


def build_street_network(
    bbox: tuple[float, float, float, float],
    network_type: str = "bike",
    elevation_dem_path: Optional[Path] = None,
) -> tuple[nx.MultiDiGraph, gpd.GeoDataFrame]:
    """Download Budapest street network via OSMnx and build per-direction lane model.

    Args:
        bbox: (min_lon, min_lat, max_lon, max_lat)
        network_type: "bike" or "all"
        elevation_dem_path: Optional path to elevation raster (DEM) to add grades.

    Returns:
        Tuple of (NetworkX directed graph, GeoDataFrame adhering to EdgesSchema).
    """

    # Ensure that relevant OSM tags are downloaded and retained.
    required_tags = [
        "lanes",
        "lanes:forward",
        "lanes:backward",
        "oneway",
        "oneway:bicycle",
        "bicycle",
        "cycleway",
        "cycleway:left",
        "cycleway:right",
        "cycleway:both",
        "cycleway:left:oneway",
        "cycleway:right:oneway",
        "cycleway:both:oneway",
        "oneway:bicycle",
        "bicycle",
        "bicycle_road",
        "cyclestreet",
    ]

    original_tags = ox.settings.useful_tags_way

    ox.settings.useful_tags_way = list(dict.fromkeys([
        *original_tags,
        *required_tags,
    ]))

    try:
        # Download directed street network.
        G = ox.graph.graph_from_bbox(
            bbox=bbox,
            network_type=network_type,
            simplify=False,
            retain_all=True,
        )
    finally:
        # Restore global OSMnx settings.
        ox.settings.useful_tags_way = original_tags

    # add missing cycling edges
    n_added = _add_bicycle_reverse_edges(G)
    print(f"Added {n_added} reverse bicycle edges.")

    edges = extract_per_direction_edges(G)


    return (G, edges)



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
        edges["u"].astype(str)
        + "-"
        + edges["v"].astype(str)
        + "-"
        + edges["key"].astype(str)
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


def _is_dedicated(value: str) -> bool:
    return value in {"lane", "track"}

def _has_dedicated_lane(edge: pd.Series) -> bool:
    """
    Return True if dedicated cycling infrastructure exists
    in the direction of this directed graph edge.
    """

    # WARNING: this implementation is insanely ugly.
    # If you want to know why or want to make it nicer (you can't) look at this page: https://wiki.openstreetmap.org/wiki/Bicycle

    # getting important tag values
    highway = _get_tag(edge, "highway")
    is_reversed_edge = edge.get("reversed", False)
    oneway = _get_tag(edge, "oneway")
    bicycle = _get_tag(edge, "bicycle")

    cycleway = _get_tag(edge, "cycleway")
    cycleway_both = _get_tag(edge, "cycleway:both")

    # If the cycling track is a separate OSM way:
    if highway == "cycleway" or (highway in {"footway", "path"} and bicycle == "designated"):    # could be path or footway with bicycle=designated, not just cycleway
        # the original tag has "oneway"="yes" but we check for "true" instead of "yes", because OSMnx stores oneway as boolean
        if oneway == "true":
            return not is_reversed_edge
        else:
            return True

    # in this special case we can return True now
    if _is_dedicated(cycleway_both):
        return True

    # if not separate OSM way but oneway road (this matters because if the road is oneway the cycleway is also oneway by default)
    if oneway == "true":
        # this means cycling infra in only oneway
        if _is_dedicated(cycleway):
            return not is_reversed_edge

        if not is_reversed_edge:
            return _is_dedicated_right_side_forward(edge) or _is_dedicated_left_side_forward(edge)
        else:
            return _is_dedicated_right_side_backward(edge) or _is_dedicated_left_side_backward(edge)
    else:
        # this means cycling infra both ways
        if _is_dedicated(cycleway) or _is_dedicated(cycleway_both):
            return True

        if not is_reversed_edge:
            return _is_dedicated_right_side_forward(edge) or _is_dedicated_left_side_forward(edge)
        else:
            return _is_dedicated_right_side_backward(edge) or _is_dedicated_left_side_backward(edge)

def _is_dedicated_right_side_forward(edge: pd.Series) -> bool:
    cycleway_right = _get_tag(edge, "cycleway:right")
    cycleway_right_oneway = _get_tag(edge, "cycleway:right:oneway")

    if _is_dedicated(cycleway_right) and cycleway_right_oneway != "-1":
        return True
    return False

def _is_dedicated_right_side_backward(edge: pd.Series) -> bool:
    cycleway_right = _get_tag(edge, "cycleway:right")
    cycleway_right_oneway = _get_tag(edge, "cycleway:right:oneway")

    if _is_dedicated(cycleway_right) and (cycleway_right_oneway == "-1" or cycleway_right_oneway == "no"):
        return True
    return False

def _is_dedicated_left_side_backward(edge: pd.Series) -> bool:
    cycleway_left = _get_tag(edge, "cycleway:left")
    cycleway_left_oneway = _get_tag(edge, "cycleway:left:oneway")

    if _is_dedicated(cycleway_left) and cycleway_left_oneway != "-1":
        return True
    return False

def _is_dedicated_left_side_forward(edge: pd.Series) -> bool:
    cycleway_left = _get_tag(edge, "cycleway:left")
    cycleway_left_oneway = _get_tag(edge, "cycleway:left:oneway")

    if _is_dedicated(cycleway_left) and (cycleway_left_oneway == "-1" or cycleway_left_oneway == "no"):
        return True
    return False



'''
For adding missing cycling edges
'''

def _is_oneway(value: object) -> bool:
    """Handle both OSM tag strings and OSMnx boolean values."""
    return (
        value is True
        or str(value).strip().lower() in {"yes", "true", "1"}
    )


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
        return MultiLineString([
            LineString(list(line.coords)[::-1])
            for line in reversed(geom.geoms)
        ])

    return geom


def _add_bicycle_reverse_edges(G: nx.MultiDiGraph):
    """
    Add missing reverse edges when:
      - oneway = yes (or OSMnx's equivalent boolean True)
      - oneway:bicycle = no

    Returns the number of edges added.
    """

    edges_to_add = []

    # Make a snapshot because we will modify the graph afterwards.
    for u, v, key, data in list(G.edges(keys=True, data=True)):

        # Check the OSM one-way and bicycle-specific tags.
        if not _is_oneway(data.get("oneway")):
            continue

        if str(data.get("oneway:bicycle", "")).strip().lower() != "no":
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
            reverse_data["geometry"] = _reverse_geometry(
                reverse_data["geometry"]
            )

        # Queue the new edge for insertion.
        edges_to_add.append((v, u, reverse_data))

    # Add the edges after iteration.
    for u, v, data in edges_to_add:
        G.add_edge(u, v, **data)

    return len(edges_to_add)

