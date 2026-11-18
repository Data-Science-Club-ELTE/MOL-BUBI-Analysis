# Dedicated bike lanes: the per-direction rule

Audience: teammates and BKK reviewers who read or populate `edges.has_dedicated_lane`. No
OpenStreetMap (OSM) background is assumed; the tagging terms are defined where they first appear.

Decision D3 in the technical design asks one question per directed street edge: does this edge,
travelled in its own direction, have a bike lane or track set aside for cyclists? This note is the
rule the network module implements in `src/bubi/network/graph.py`. It matches the diagrams on the
OSM wiki [Bicycle](https://wiki.openstreetmap.org/wiki/Bicycle) page, which is the reference for the
tests in `tests/test_network_lane_tags.py`.

## Direction convention

An OSM **way** is an ordered list of nodes, from node A to node B. The rule uses two signs:

- `+` edge: travels A to B, the way direction.
- `-` edge: travels B to A, against the way direction.

Left and right are the sides seen while travelling A to B. Budapest drives on the right, so on a
two-way road the right side carries `+` and the left side carries `-`. A left-hand traffic city
would swap the two.

## What counts as dedicated

A directed edge is covered when at least one of these holds in the edge direction:

| Tagging | Direction it serves |
|---|---|
| `cycleway=lane` or `track` | Both sides on a two-way road. On a one-way road, see the defaults below. |
| `cycleway:left` or `cycleway:right` = `lane` or `track` | That side. |
| `cycleway:both` = `lane` or `track` | Both sides. |
| `cycleway:S:oneway` = `yes`, `no`, or `-1` | Overrides the side default: `+`, both, or `-`. |
| `cycleway=opposite_lane` or `opposite_track` | `-`, the legacy contraflow forms. |
| `highway=cycleway` | Its own `oneway` value; both directions when absent. |
| `highway=path` or `footway` plus `bicycle=designated` | Its own `oneway` value, like a cycleway. |
| `bicycle:lanes` with a `designated` entry | The side that entry sits on, see below. |

A **lane** is paint inside the carriageway. A **track** is a separate path next to it. Both count;
the module does not keep the distinction in the output.

An advisory lane (`cycleway:right=lane` plus `cycleway:right:lane=advisory`) counts like any other
lane. A lane shared with buses or taxis (`share_busway`) does not.

## What does not count

- `shared_lane`: a pictogram lane shared with motor traffic.
- `share_busway`: a bus lane bicycles may use.
- `cyclestreet=yes` and `bicycle_road=yes`: shared carriageway, no lane set aside.
- `highway=pedestrian` plus `bicycle=yes`, and `highway=footway` plus `bicycle=yes`: cycling is
  allowed, but no dedicated facility is mapped. Only `bicycle=designated` on a path or footway
  counts.
- Plain `highway=path` and `highway=track`, with no `bicycle=designated`.
- `bicycle=*` on its own, including `use_sidepath`, `permissive`, `destination`, and `dismount`.
  `use_sidepath` points to a separate way; it is not a lane on this one.

## Direction defaults

Unless `cycleway:S:oneway` is written, the side and the road type decide:

| Road | Left side | Right side |
|---|---|---|
| Two-way road | `-` | `+` |
| One-way road, bicycles one-way too | `+` | `+` |
| One-way road, `oneway:bicycle=no`, painted lane | `-` (contraflow) | `+` |
| One-way road, `oneway:bicycle=no`, track | Both | Both |

The third row is wiki case M1: the left lane is the contraflow lane, the right lane flows with the
cars. The fourth row is wiki case T3: the track is bidirectional while the carriageway stays
one-way. On a plain one-way road both sides flow with the traffic, so a left-side lane still serves
`+` (wiki case M2b).

Precedence for one side is `cycleway:S` first, then `cycleway:both`, then `cycleway`. An explicit
`no` or `separate` on one side blocks the fallback: `cycleway:right=no` plus `cycleway=lane` leaves
the right side uncovered.

## Lanes tagged with `:lanes`

Wiki case B1, a no-consensus proposal, gives the layout lane by lane:
`bicycle:lanes=designated|yes|yes|designated|yes` with `lanes:forward=2`. The values run left to
right in the way direction, so the last `lanes:forward` values are the right side and the rest are
the left side. Any `designated` entry covers its side. On a one-way road any `designated` entry
covers the `+` edge.

If the same way also has a `cycleway*` tag for a side, that tag wins and `:lanes` is ignored for the
side. A bus lane can be counted if a mapper marks it `designated` for bicycles as well.

## Which ways are downloaded

Two filters matter before any tag is read:

- The bike network keeps ways where cycling is allowed and drops excluded classes.
- OSMnx 2.1.1's bike preset excludes `highway=footway`. Because a designated footway counts as
  dedicated, `build_street_network` adds
  `["highway"="footway"]["bicycle"="designated"]` to the bike filter. Set
  `include_designated_footways=False` to keep the stock filter.

The graph is downloaded with `simplify=False`, so each edge carries the tags of one OSM way
segment and no edge mixes two ways.

## Output

`extract_per_direction_edges` returns one row per directed edge, matching `EdgesSchema`:

| Column | Meaning |
|---|---|
| `edge_id` | `u-v-key`, unique per directed edge |
| `osm_way_id` | Source OSM way |
| `length_m` | Length in metres, computed in EPSG:23700 |
| `has_dedicated_lane` | The boolean this note defines |
| `geometry` | LineString in EPSG:4326 |

## Known limitation

`oneway=-1` is not handled correctly when a side lane or `oneway:bicycle` is also present. OSMnx
reverses the node order and stores `oneway` as a boolean, so the raw `-1` is lost and the
left/right tags are no longer tied to the stored direction. On a plain `oneway=-1` way the
direction flag is still usable; in combination with a side lane it can land on the wrong edge.
Fixing it needs the raw way tags, not the graph. `tests/test_network_lane_tags.py` pins the current
behaviour so a future fix is visible.

## Tests

`tests/test_network_lane_tags.py` covers every tagging combination on the wiki page, including the
alternatives ("or" rows), plus the extra sections. Each case runs twice: once on a hand-built graph
and once through OSMnx's OSM XML parser, which is where boolean `oneway` values, node order, and tag
filtering are exercised.

```bash
pytest tests/test_network_lane_tags.py
```

The output contract is unchanged: the same five columns and `EdgesSchema` as before.
