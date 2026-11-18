"""Per-direction bike-lane tests built from the OpenStreetMap wiki tables.

Every tagging combination listed in the examples on
https://wiki.openstreetmap.org/wiki/Bicycle (read 2026-11-18) gets its own
test: L1a, L1b, L2, M1, M2a-M2d, M3a, M3b, M4, M5, T1-T4, S1-S8, B1-B6.
Where the table lists alternatives, each combination is a separate case, and
every way of a multi-way example is asserted on its own. The arrows in each
example's diagram give the expected direction. The wiki tables assume
right-hand traffic, as Budapest uses.

The test tags keep the wiki values ("oneway=yes", not a boolean). The fixture
adds the mirror edge the way OSMnx does, including reversed=False/True, so the
cases contain no two-way flag that the wiki does not have.

Every case also runs through OSMnx's XML parser (test_osm_xml_lane_tags),
which is the only way to catch its boolean oneway, node order, and tag
filtering. oneway=-1 is characterised, not fixed: OSMnx reverses the node
order and drops the raw value, so a side lane can end up on the traffic edge
or its mirror (see test_osm_xml_oneway_minus_one).
"""

import sys
from pathlib import Path

import networkx as nx
import osmnx as ox
import pytest
from pyproj import Transformer
from shapely.geometry import LineString

from bubi.contracts.schemas import EdgesSchema
from bubi.network.graph import (
    REQUIRED_WAY_TAGS,
    _has_dedicated_lane,
    build_street_network,
    extract_per_direction_edges,
    postprocess_graph,
)

WIKI = "https://wiki.openstreetmap.org/wiki/Bicycle"
FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_OSM = FIXTURES / "lane_tags.osm"
FIXTURE_README = FIXTURES / "lane_tags.md"

CY = {"highway": "cycleway"}
SIDEPATH = {"bicycle": "use_sidepath"}

# Each case lists OSM ways and the expected flag per (way index, direction).
# A direction missing from expect must have no edge at all.
CASES = [
    # --- Cycle lanes in bidirectional carriageways ---
    {
        "id": "L1a-1",
        "ref": "L1a, cycleway=lane",
        "ways": [{"cycleway": "lane"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "L1a-2",
        "ref": "L1a, cycleway:left=lane + cycleway:right=lane",
        "ways": [{"cycleway:left": "lane", "cycleway:right": "lane"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "L1a-3",
        "ref": "L1a, cycleway:both=lane",
        "ways": [{"cycleway:both": "lane"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "L1b-1",
        "ref": "L1b, cycleway:right=lane + cycleway:right:oneway=no",
        "ways": [{"cycleway:right": "lane", "cycleway:right:oneway": "no"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "L1b-2",
        "ref": "L1b, cycleway=lane (indistinguishable from L1a)",
        "ways": [{"cycleway": "lane"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "L2",
        "ref": "L2, cycleway:right=lane",
        "ways": [{"cycleway:right": "lane"}],
        "expect": {(0, "+"): True, (0, "-"): False},
    },
    # --- Cycle lanes in oneway carriageways ---
    {
        "id": "M1-1",
        "ref": "M1, oneway=yes + cycleway=lane + oneway:bicycle=no",
        "ways": [{"oneway": "yes", "cycleway": "lane", "oneway:bicycle": "no"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "M1-2",
        "ref": "M1, oneway=yes + side lanes + oneway:bicycle=no",
        "ways": [
            {
                "oneway": "yes",
                "cycleway:left": "lane",
                "cycleway:right": "lane",
                "oneway:bicycle": "no",
            }
        ],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "M2a-1",
        "ref": "M2a, oneway=yes + cycleway:right=lane",
        "ways": [{"oneway": "yes", "cycleway:right": "lane"}],
        "expect": {(0, "+"): True},
    },
    {
        "id": "M2a-2",
        "ref": "M2a, oneway=yes + cycleway=lane",
        "ways": [{"oneway": "yes", "cycleway": "lane"}],
        "expect": {(0, "+"): True},
    },
    {
        "id": "M2b-1",
        "ref": "M2b, oneway=yes + cycleway:left=lane",
        "ways": [{"oneway": "yes", "cycleway:left": "lane"}],
        "expect": {(0, "+"): True},
    },
    {
        "id": "M2b-2",
        "ref": "M2b, oneway=yes + cycleway=lane",
        "ways": [{"oneway": "yes", "cycleway": "lane"}],
        "expect": {(0, "+"): True},
    },
    {
        "id": "M2c",
        "ref": "M2c, oneway=yes + lanes=2 + cycleway=lane",
        "ways": [{"oneway": "yes", "lanes": "2", "cycleway": "lane"}],
        "expect": {(0, "+"): True},
    },
    {
        "id": "M2d",
        "ref": "M2d, bidirectional left lane",
        "ways": [
            {
                "oneway": "yes",
                "oneway:bicycle": "no",
                "cycleway:left": "lane",
                "cycleway:left:oneway": "no",
            }
        ],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "M3a",
        "ref": "M3a, contraflow left lane",
        "ways": [
            {
                "oneway": "yes",
                "oneway:bicycle": "no",
                "cycleway:left": "lane",
                "cycleway:left:oneway": "-1",
            }
        ],
        "expect": {(0, "+"): False, (0, "-"): True},
    },
    {
        "id": "M3b",
        "ref": "M3b, contraflow right lane",
        "ways": [
            {
                "oneway": "yes",
                "oneway:bicycle": "no",
                "cycleway:right": "lane",
                "cycleway:right:oneway": "-1",
            }
        ],
        "expect": {(0, "+"): False, (0, "-"): True},
    },
    {
        "id": "M4-1",
        "ref": "M4, two one-way carriageways, each as M2a",
        "ways": [
            {"oneway": "yes", "cycleway:right": "lane"},
            {"oneway": "yes", "cycleway:right": "lane"},
        ],
        "expect": {(0, "+"): True, (1, "+"): True},
    },
    {
        "id": "M4-2",
        "ref": "M4, alternative single way as L1a",
        "ways": [{"cycleway": "lane"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "M5-1",
        "ref": "M5, Way A as M2a, Way B oneway=yes",
        "ways": [
            {"oneway": "yes", "cycleway:right": "lane"},
            {"oneway": "yes"},
        ],
        "expect": {(0, "+"): True, (1, "+"): False},
    },
    {
        "id": "M5-2",
        "ref": "M5, alternative Way A as L2",
        "ways": [{"cycleway:right": "lane"}],
        "expect": {(0, "+"): True, (0, "-"): False},
    },
    # --- Cycle tracks ---
    {
        "id": "T1-1",
        "ref": "T1, road with use_sidepath and two one-way cycleways",
        "ways": [
            SIDEPATH,
            {**CY, "oneway": "yes"},
            {**CY, "oneway": "yes"},
        ],
        "expect": {
            (0, "+"): False,
            (0, "-"): False,
            (1, "+"): True,
            (2, "+"): True,
        },
    },
    {
        "id": "T1-2",
        "ref": "T1, alternative single way cycleway=track",
        "ways": [{"cycleway": "track"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "T2-1",
        "ref": "T2, road with use_sidepath and a two-way cycleway",
        "ways": [SIDEPATH, {**CY, "oneway": "no"}],
        "expect": {(0, "+"): False, (0, "-"): False, (1, "+"): True, (1, "-"): True},
    },
    {
        "id": "T2-2",
        "ref": "T2, alternative cycleway:right=track + :oneway=no",
        "ways": [{"cycleway:right": "track", "cycleway:right:oneway": "no"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "T3-1",
        "ref": "T3, one-way road with use_sidepath and a two-way cycleway",
        "ways": [{"oneway": "yes", **SIDEPATH}, {**CY, "oneway": "no"}],
        "expect": {(0, "+"): False, (1, "+"): True, (1, "-"): True},
    },
    {
        "id": "T3-2",
        "ref": "T3, alternative one-way road + cycleway:right=track",
        "ways": [{"oneway": "yes", "oneway:bicycle": "no", "cycleway:right": "track"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "T4-1",
        "ref": "T4, bicycle:forward=use_sidepath and a one-way cycleway",
        "ways": [{"bicycle:forward": "use_sidepath"}, {**CY, "oneway": "yes"}],
        "expect": {(0, "+"): False, (0, "-"): False, (1, "+"): True},
    },
    {
        "id": "T4-2",
        "ref": "T4, alternative cycleway:right=track",
        "ways": [{"cycleway:right": "track"}],
        "expect": {(0, "+"): True, (0, "-"): False},
    },
    # --- Miscellaneous ---
    {
        "id": "S1",
        "ref": "S1, oneway=yes + oneway:bicycle=no without a lane",
        "ways": [{"oneway": "yes", "oneway:bicycle": "no"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "S2-1",
        "ref": "S2, right lane with bicycle:backward=use_sidepath, plus a cycleway",
        "ways": [
            {"cycleway:right": "lane", "bicycle:backward": "use_sidepath"},
            {**CY, "oneway": "yes"},
        ],
        "expect": {(0, "+"): True, (0, "-"): False, (1, "+"): True},
    },
    {
        "id": "S2-2",
        "ref": "S2, alternative cycleway:left=track + cycleway:right=lane",
        "ways": [{"cycleway:left": "track", "cycleway:right": "lane"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "S3-1",
        "ref": "S3, cycleway=track + segregated=yes",
        "ways": [{"cycleway": "track", "segregated": "yes"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "S3-2",
        "ref": "S3, separate sidewalk ways, cycleway ways",
        "ways": [SIDEPATH, {**CY, "oneway": "yes"}, {**CY, "oneway": "yes"}],
        "expect": {
            (0, "+"): False,
            (0, "-"): False,
            (1, "+"): True,
            (2, "+"): True,
        },
    },
    {
        "id": "S3-3",
        "ref": "S3, separate path ways with bicycle=designated",
        "ways": [
            SIDEPATH,
            {
                "highway": "path",
                "bicycle": "designated",
                "oneway": "yes",
                "foot": "designated",
                "segregated": "yes",
            },
            {
                "highway": "path",
                "bicycle": "designated",
                "oneway": "yes",
                "foot": "designated",
                "segregated": "yes",
            },
        ],
        "expect": {(0, "+"): False, (0, "-"): False, (1, "+"): True, (2, "+"): True},
    },
    {
        "id": "S3-4",
        "ref": "S3, separate cycleway ways with foot=designated",
        "ways": [
            SIDEPATH,
            {**CY, "oneway": "yes", "foot": "designated", "segregated": "yes"},
            {**CY, "oneway": "yes", "foot": "designated", "segregated": "yes"},
        ],
        "expect": {(0, "+"): False, (0, "-"): False, (1, "+"): True, (2, "+"): True},
    },
    {
        "id": "S4-1",
        "ref": "S4, easiest: cycleway=track + segregated + foot=designated",
        "ways": [{"cycleway": "track", "segregated": "yes", "foot": "designated"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "S4-2",
        "ref": "S4, separate cycleway ways with foot=designated",
        "ways": [
            SIDEPATH,
            {**CY, "oneway": "yes", "foot": "designated", "segregated": "yes"},
            {**CY, "oneway": "yes", "foot": "designated", "segregated": "yes"},
        ],
        "expect": {(0, "+"): False, (0, "-"): False, (1, "+"): True, (2, "+"): True},
    },
    {
        "id": "S4-3",
        "ref": "S4, five-way variant with separate footways",
        "ways": [
            SIDEPATH,
            {**CY, "oneway": "yes"},
            {"highway": "footway"},
            {**CY, "oneway": "yes"},
            {"highway": "footway"},
        ],
        "expect": {
            (0, "+"): False,
            (0, "-"): False,
            (1, "+"): True,
            (2, "+"): False,
            (2, "-"): False,
            (3, "+"): True,
            (4, "+"): False,
            (4, "-"): False,
        },
    },
    {
        "id": "S5-1",
        "ref": "S5, shared path with bicycle=designated",
        "ways": [
            {
                "highway": "path",
                "segregated": "yes",
                "foot": "designated",
                "bicycle": "designated",
                "surface": "paved",
            }
        ],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "S5-2",
        "ref": "S5, separate footway and cycleway",
        "ways": [
            {"highway": "footway", "surface": "paving_stones"},
            {**CY, "surface": "asphalt"},
        ],
        "expect": {
            (0, "+"): False,
            (0, "-"): False,
            (1, "+"): True,
            (1, "-"): True,
        },
    },
    {
        "id": "S6",
        "ref": "S6, steps with a bicycle ramp",
        "ways": [
            {
                "highway": "steps",
                "ramp:bicycle": "yes",
                "ramp:stroller": "yes",
                "ramp:wheelchair": "no",
            }
        ],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "S7-footway",
        "ref": "S7, highway=footway + bicycle=designated + segregated=no",
        "ways": [
            {
                "highway": "footway",
                "bicycle": "designated",
                "foot": "designated",
                "segregated": "no",
                "surface": "paved",
            }
        ],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "S7-cycleway",
        "ref": "S7, highway=cycleway + bicycle=designated + segregated=no",
        "ways": [
            {
                **CY,
                "bicycle": "designated",
                "foot": "designated",
                "segregated": "no",
                "surface": "paved",
            }
        ],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "S7-path",
        "ref": "S7, highway=path + bicycle=designated + segregated=no",
        "ways": [
            {
                "highway": "path",
                "bicycle": "designated",
                "foot": "designated",
                "segregated": "no",
                "surface": "paved",
            }
        ],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "S8",
        "ref": "S8, highway=footway + bicycle=yes",
        "ways": [{"highway": "footway", "bicycle": "yes"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    # --- Cycle lanes and bus/taxi lanes ---
    {
        "id": "B1",
        "ref": "B1, lanes layout with bicycle:lanes=designated on both sides",
        "ways": [
            {
                "lanes": "3",
                "lanes:forward": "2",
                "access:lanes": "no|yes|yes|no|no",
                "bicycle:lanes": "designated|yes|yes|designated|yes",
                "bus:lanes": "no|yes|yes|no|designated",
                "taxi:lanes": "no|yes|yes|no|designated",
            }
        ],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "B2",
        "ref": "B2, bus lane right plus cycleway=lane",
        "ways": [
            {
                "lanes": "3",
                "lanes:forward": "2",
                "lanes:bus:forward": "1",
                "busway:right": "lane",
                "cycleway": "lane",
            }
        ],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "B3",
        "ref": "B3, left lane plus shared busway on the right",
        "ways": [
            {
                "busway:right": "lane",
                "cycleway:left": "lane",
                "cycleway:right": "share_busway",
            }
        ],
        "expect": {(0, "+"): False, (0, "-"): True},
    },
    {
        "id": "B4-1",
        "ref": "B4, bus way with shared busway, road one-way for bicycles",
        "ways": [
            {
                "highway": "service",
                "service": "bus",
                "oneway": "yes",
                "cycleway:right": "share_busway",
            },
            {"oneway:bus": "yes", "oneway:bicycle": "yes"},
        ],
        "expect": {
            (0, "+"): False,
            (1, "+"): False,
            (1, "-"): False,
        },
    },
    {
        "id": "B4-2",
        "ref": "B4, bus way with shared busway, road two-way for bicycles",
        "ways": [
            {
                "highway": "service",
                "service": "bus",
                "oneway": "yes",
                "cycleway:right": "share_busway",
            },
            {},
        ],
        "expect": {
            (0, "+"): False,
            (1, "+"): False,
            (1, "-"): False,
        },
    },
    {
        "id": "B5",
        "ref": "B5, shared busway on the right",
        "ways": [
            {
                "lanes": "4",
                "lanes:bus:forward": "1",
                "busway:right": "lane",
                "cycleway:right": "share_busway",
            }
        ],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "B6-1",
        "ref": "B6, contraflow shared busway, busway=opposite_lane",
        "ways": [
            {
                "oneway": "yes",
                "oneway:bicycle": "no",
                "cycleway:left": "share_busway",
                "cycleway:left:oneway": "-1",
                "busway": "opposite_lane",
            }
        ],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "B6-2",
        "ref": "B6, contraflow shared busway, busway=lane",
        "ways": [
            {
                "oneway": "yes",
                "oneway:bus": "no",
                "oneway:bicycle": "no",
                "cycleway:left": "share_busway",
                "cycleway:left:oneway": "-1",
                "busway": "lane",
            }
        ],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    # --- Contraflow edges without oneway:bicycle=no (review Task 2) ---
    {
        "id": "M3a-no-onewaybicycle",
        "ref": "M3a tagging without oneway:bicycle=no",
        "ways": [{"oneway": "yes", "cycleway:left": "lane", "cycleway:left:oneway": "-1"}],
        "expect": {(0, "+"): False, (0, "-"): True},
    },
    {
        "id": "M3b-no-onewaybicycle",
        "ref": "M3b tagging without oneway:bicycle=no",
        "ways": [{"oneway": "yes", "cycleway:right": "lane", "cycleway:right:oneway": "-1"}],
        "expect": {(0, "+"): False, (0, "-"): True},
    },
    {
        "id": "LEG-opposite-lane",
        "ref": "legacy cycleway=opposite_lane",
        "ways": [{"oneway": "yes", "cycleway": "opposite_lane"}],
        "expect": {(0, "+"): False, (0, "-"): True},
    },
    {
        "id": "LEG-opposite-track-left",
        "ref": "legacy cycleway:left=opposite_track",
        "ways": [{"oneway": "yes", "cycleway:left": "opposite_track"}],
        "expect": {(0, "+"): False, (0, "-"): True},
    },
    {
        "id": "LEG-opposite",
        "ref": "legacy cycleway=opposite, contraflow without a lane",
        "ways": [{"oneway": "yes", "cycleway": "opposite"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    # --- Rest of the wiki page (review Task 6) ---
    {
        "id": "cyclestreet",
        "ref": "cycle street, shared carriageway",
        "ways": [{"cyclestreet": "yes"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "bicycle-road",
        "ref": "bicycle road, cars may be allowed by sign",
        "ways": [{"bicycle_road": "yes"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "pedestrian-street",
        "ref": "highway=pedestrian + bicycle=yes",
        "ways": [{"highway": "pedestrian", "bicycle": "yes"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "path-plain",
        "ref": "off-road highway=path without bicycle=designated",
        "ways": [{"highway": "path"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "track-plain",
        "ref": "off-road highway=track",
        "ways": [{"highway": "track"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "track-designated",
        "ref": "highway=track + bicycle=designated",
        "ways": [{"highway": "track", "bicycle": "designated"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "bicycle-use_sidepath",
        "ref": "bicycle=use_sidepath alone",
        "ways": [{"bicycle": "use_sidepath"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "bicycle-optional_sidepath",
        "ref": "bicycle=optional_sidepath alone",
        "ways": [{"bicycle": "optional_sidepath"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "bicycle-dismount",
        "ref": "bicycle=dismount alone",
        "ways": [{"bicycle": "dismount"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "bicycle-permissive",
        "ref": "bicycle=permissive alone",
        "ways": [{"bicycle": "permissive"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "bicycle-destination",
        "ref": "bicycle=destination alone",
        "ways": [{"bicycle": "destination"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "bicycle-yes",
        "ref": "bicycle=yes alone",
        "ways": [{"bicycle": "yes"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "bicycle-designated-road",
        "ref": "bicycle=designated on a road without a lane",
        "ways": [{"bicycle": "designated"}],
        "expect": {(0, "+"): False, (0, "-"): False},
    },
    {
        "id": "advisory-right",
        "ref": "cycleway:right=lane with an advisory lane",
        "ways": [{"cycleway:right": "lane", "cycleway:right:lane": "advisory"}],
        "expect": {(0, "+"): True, (0, "-"): False},
    },
    {
        "id": "advisory-both",
        "ref": "cycleway:both=lane with an advisory lane",
        "ways": [{"cycleway:both": "lane", "cycleway:both:lane": "advisory"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "shared-cycleway",
        "ref": "highway=cycleway + foot=designated + segregated=no",
        "ways": [{"highway": "cycleway", "foot": "designated", "segregated": "no"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
    {
        "id": "shared-footway",
        "ref": "highway=footway + bicycle=designated + segregated=no",
        "ways": [{"highway": "footway", "bicycle": "designated", "segregated": "no"}],
        "expect": {(0, "+"): True, (0, "-"): True},
    },
]


def _way_nodes(index):
    return 2 * index + 1, 2 * index + 2


def _build_graph(ways):
    graph = nx.MultiDiGraph(crs="epsg:4326")
    for index, way in enumerate(ways):
        u, v = _way_nodes(index)
        lat = 47.45 + 0.01 * index
        pu = (19.0 + 0.001 * index, lat)
        pv = (19.001 + 0.001 * index, lat)
        graph.add_node(u, x=pu[0], y=pu[1])
        graph.add_node(v, x=pv[0], y=pv[1])
        tags = {
            "highway": "secondary",
            "osmid": 1000 + index,
            "length": 100.0,
            **way,
        }
        # OSMnx marks the way-order edge reversed=False and its mirror True.
        graph.add_edge(u, v, 0, **tags, reversed=False, geometry=LineString([pu, pv]))
        if tags.get("oneway") not in {"yes", "1", True}:
            graph.add_edge(v, u, 0, **tags, reversed=True, geometry=LineString([pv, pu]))
    return graph


def _flags(edges, way_count):
    flags = {}
    for _, row in edges.iterrows():
        u, v, _key = row["edge_id"].split("-")
        for index in range(way_count):
            wu, wv = _way_nodes(index)
            direction = (
                "+"
                if (int(u), int(v)) == (wu, wv)
                else "-"
                if (int(u), int(v)) == (wv, wu)
                else None
            )
            if direction is not None:
                flags[(index, direction)] = bool(row["has_dedicated_lane"])
    return flags


def _run(ways):
    graph = _build_graph(ways)
    _, edges = postprocess_graph(graph)
    return graph, edges, _flags(edges, len(ways))


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_wiki_lane_tags(case):
    """Every wiki tagging combination yields the flags its diagram shows."""
    _, _, flags = _run(case["ways"])
    assert flags == case["expect"], (
        f"{case['id']} ({case['ref']}): got {flags}, want {case['expect']}. "
        f"Reference tagging: {WIKI}"
    )


def test_two_way_way_yields_two_directed_rows():
    _, edges, _ = _run([{"cycleway": "lane"}])
    assert set(edges["edge_id"]) == {"1-2-0", "2-1-0"}


def test_one_way_way_yields_one_directed_row():
    _, edges, _ = _run([{"oneway": "yes", "cycleway:right": "lane"}])
    assert set(edges["edge_id"]) == {"1-2-0"}


def test_edges_validate_against_schema():
    _, edges, _ = _run([{"cycleway": "track"}])
    EdgesSchema.validate(edges)


def test_length_is_metres_in_epsg_23700():
    _, edges, _ = _run([{"cycleway": "lane"}])
    transformer = Transformer.from_crs(4326, 23700, always_xy=True)
    pu, pv = (19.0, 47.45), (19.001, 47.45)
    expected = LineString([transformer.transform(*pu), transformer.transform(*pv)]).length
    assert edges["length_m"].between(expected - 0.01, expected + 0.01).all()


def test_empty_graph_raises_value_error():
    graph = nx.MultiDiGraph(crs="epsg:4326")
    graph.add_node(1, x=19.0, y=47.45)
    # The graph-to-EdgeDataFrame conversion rejects an empty graph before the
    # module's own "No street edges" guard can run, so only the type is asserted.
    with pytest.raises(ValueError):
        extract_per_direction_edges(graph)


def _osm_xml(ways):
    """Build a minimal OSM XML file with one way per case way."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<osm version="0.6">']
    for index in range(len(ways)):
        u, v = _way_nodes(index)
        lat = 47.45 + 0.01 * index
        lon_u = 19.0 + 0.001 * index
        lon_v = 19.001 + 0.001 * index
        lines.append(f'  <node id="{u}" lat="{lat}" lon="{lon_u}"/>')
        lines.append(f'  <node id="{v}" lat="{lat}" lon="{lon_v}"/>')
    for index, way in enumerate(ways):
        u, v = _way_nodes(index)
        tags = {"highway": "secondary", **way}
        lines.append(f'  <way id="{1000 + index}">')
        lines.append(f'    <nd ref="{u}"/>')
        lines.append(f'    <nd ref="{v}"/>')
        for key, value in tags.items():
            lines.append(f'    <tag k="{key}" v="{value}"/>')
        lines.append("  </way>")
    lines.append("</osm>")
    return "\n".join(lines)


def _flat_ways():
    """All case ways in fixture order."""
    return [way for case in CASES for way in case["ways"]]


def _case_offsets():
    """First flat way index for each case id."""
    offsets = {}
    index = 0
    for case in CASES:
        offsets[case["id"]] = index
        index += len(case["ways"])
    return offsets


def _fixture_xml():
    return _osm_xml(_flat_ways())


def _fixture_readme():
    lines = [
        "# Lane-tag fixture graph",
        "",
        "lane_tags.osm is the graph used by test_osm_xml_lane_tags. It is generated",
        "from CASES in tests/test_network_lane_tags.py, one way per case way.",
        "",
        "Regenerate both files after editing CASES:",
        "",
        "    PYTHONPATH=src python tests/test_network_lane_tags.py --write-fixture",
        "",
        "Way id is 1000 + flat index; its nodes are 2 * flat index + 1 and",
        "2 * flat index + 2, so no two ways share geometry. Load it with",
        "ox.settings.useful_tags_way extended by REQUIRED_WAY_TAGS, then",
        "ox.graph.graph_from_xml(path, bidirectional=False, simplify=False, retain_all=True).",
        "",
        "| Way | Case | Reference | Tags | + | - |",
        "|---|---|---|---|---|---|",
    ]
    flat_index = 0
    for case in CASES:
        for way_index, way in enumerate(case["ways"]):
            tags = {"highway": "secondary", **way}
            cells = ", ".join(
                f"{key}={str(value).replace(chr(124), chr(92) + chr(124))}"
                for key, value in tags.items()
            )
            plus = case["expect"].get((way_index, "+"), "absent")
            minus = case["expect"].get((way_index, "-"), "absent")
            lines.append(
                f"| {1000 + flat_index} | {case['id']} | {case['ref']} | {cells} | "
                f"{plus} | {minus} |"
            )
            flat_index += 1
    return "\n".join(lines) + "\n"


def _write_xml(ways, tmp_path):
    path = tmp_path / "case.osm"
    path.write_text(_osm_xml(ways), encoding="utf-8")
    return path


def _load_xml(path):
    original_tags = list(ox.settings.useful_tags_way)
    try:
        ox.settings.useful_tags_way = list(dict.fromkeys([*original_tags, *REQUIRED_WAY_TAGS]))
        return ox.graph.graph_from_xml(
            str(path), bidirectional=False, simplify=False, retain_all=True
        )
    finally:
        ox.settings.useful_tags_way = original_tags


@pytest.fixture(scope="module")
def fixture_flags():
    graph = _load_xml(FIXTURE_OSM)
    _, edges = postprocess_graph(graph)
    return _flags(edges, len(_flat_ways()))


def test_fixture_matches_generator():
    """The committed graph and README stay in step with CASES."""
    assert FIXTURE_OSM.read_text(encoding="utf-8") == _fixture_xml()
    assert FIXTURE_README.read_text(encoding="utf-8") == _fixture_readme()


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_osm_xml_lane_tags(case, fixture_flags):
    """The same cases survive OSMnx parsing: booleans, node order, tags."""
    offset = _case_offsets()[case["id"]]
    count = len(case["ways"])
    got = {key: value for key, value in fixture_flags.items() if offset <= key[0] < offset + count}
    expected = {
        (offset + way, direction): value for (way, direction), value in case["expect"].items()
    }
    assert got == expected, (
        f"{case['id']} ({case['ref']}): got {got}, want {expected}. Reference tagging: {WIKI}"
    )


# oneway=-1: OSMnx reverses the node order, so the edge with traffic is 2->1
# and shows up as "-" in this file's node convention. The left/right tags stay
# relative to the drawn way.
XML_ONEWAY_CASES = [
    {
        "id": "oneway-minus1-right-lane",
        "ways": [{"oneway": "-1", "cycleway:right": "lane"}],
        "expect": {(0, "-"): True},
    },
    {
        "id": "oneway-minus1-bicycle-no-left-lane",
        "ways": [{"oneway": "-1", "oneway:bicycle": "no", "cycleway:left": "lane"}],
        # Observed, and known to be wrong: OSMnx reverses the node order and
        # drops the raw -1, so the traffic edge loses the lane and the added
        # contraflow edge gets it. The raw tag is not recoverable here.
        "expect": {(0, "+"): True, (0, "-"): False},
    },
]


@pytest.mark.parametrize("case", XML_ONEWAY_CASES, ids=[case["id"] for case in XML_ONEWAY_CASES])
def test_osm_xml_oneway_minus_one(case, tmp_path):
    """Characterises oneway=-1; left/right is not remapped to traffic direction."""
    graph = _load_xml(_write_xml(case["ways"], tmp_path))
    _, edges = postprocess_graph(graph)
    flags = _flags(edges, len(case["ways"]))
    assert flags == case["expect"], f"{case['id']}: got {flags}"


class _RecordingEdge:
    """Duck-typed edge that records every tag key the module reads."""

    seen: set[str] = set()

    def __init__(self, data):
        self._data = data

    def get(self, key, default=None):
        _RecordingEdge.seen.add(key)
        return self._data.get(key, default)


def test_every_tag_the_logic_reads_is_requested():
    """Fails when the rule starts reading a tag that is never downloaded."""
    _RecordingEdge.seen.clear()
    for case in CASES:
        for way in case["ways"]:
            for reversed_ in (False, True):
                data = {"highway": "secondary", **way, "reversed": reversed_}
                _has_dedicated_lane(_RecordingEdge(data))
    requested = set(REQUIRED_WAY_TAGS) | set(ox.settings.useful_tags_way)
    assert _RecordingEdge.seen - {"reversed"} <= requested


def test_build_requests_lane_tags_and_footways(monkeypatch):
    graph = _build_graph([{"cycleway": "lane"}])
    captured = {}

    def fake_graph_from_bbox(**kwargs):
        captured.update(kwargs)
        captured["useful_tags_way"] = list(ox.settings.useful_tags_way)
        return graph

    monkeypatch.setattr(ox.graph, "graph_from_bbox", fake_graph_from_bbox)
    original_tags = list(ox.settings.useful_tags_way)
    build_street_network((19.0, 47.4, 19.1, 47.5))

    assert "bicycle:lanes" in captured["useful_tags_way"]
    assert ox.settings.useful_tags_way == original_tags
    filters = captured["custom_filter"]
    assert isinstance(filters, list)
    assert any("footway" in part for part in filters)


def test_all_network_keeps_osmnx_filter(monkeypatch):
    graph = _build_graph([{"cycleway": "lane"}])
    captured = {}

    def fake_graph_from_bbox(**kwargs):
        captured.update(kwargs)
        return graph

    monkeypatch.setattr(ox.graph, "graph_from_bbox", fake_graph_from_bbox)
    build_street_network((19.0, 47.4, 19.1, 47.5), network_type="all")

    assert captured["custom_filter"] is None


if __name__ == "__main__":
    if "--write-fixture" not in sys.argv:
        print("use --write-fixture to regenerate tests/fixtures/lane_tags.osm and .md")
    else:
        FIXTURE_OSM.write_text(_fixture_xml(), encoding="utf-8")
        FIXTURE_README.write_text(_fixture_readme(), encoding="utf-8")
        print(f"wrote {FIXTURE_OSM.name} and {FIXTURE_README.name}")
