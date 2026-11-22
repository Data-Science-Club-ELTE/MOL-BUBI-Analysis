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

## Separate cycleways

When a track is mapped as its own way (`highway=cycleway`), the road beside it usually carries
`cycleway:S=separate` or `bicycle=use_sidepath` (wiki case T1). Those tags are pointers, not lanes,
so the road edge is `False` for that side. The cycleway edge is `True` in its own direction.

The module does not match the two ways and transfer coverage. One facility has two representations,
and the cycleway edge is the one cyclists ride. Routing uses that edge, and the lane-connectivity
score and gap scoring read its flag. Gap scores only count edges with route volume, so a road edge
beside a track does not appear as a gap unless a route actually uses that road edge.

This is deliberate, not a gap in the rule. A geometric match (distance, bearing, overlap) has no
consumer in the project, and it would risk counting the same track twice in lane kilometres. If
observed GPS routes later report gaps on roads that clearly have a track beside them, the fix
belongs in map matching, which should snap the ride to the cycleway edge.

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

## `oneway=-1`

OSMnx reverses the node order of ways tagged `oneway=-1`, `oneway=reverse`, or `oneway=T`, then
stores `oneway` as a boolean. The left and right tags still describe the drawn way, so
`cycleway:left` would point at the wrong side of the stored edge. The builder reads those way ids
from the source file and swaps `cycleway:left` with `cycleway:right`, and the `:oneway`
variants, before evaluating the lane. This needs the local extract: OSMnx discards the raw value,
so the Overpass download path cannot recover it.

## OSM data quality

The lane flag is only as good as the tags behind it. A missing `cycleway` tag hides a lane that exists,
a stale tag claims one that does not, and a crossing mapped as `highway=footway` with
`bicycle=dismount` breaks the line at a junction even when paint continues.

The Soroksári út / Kvassay Jenő út junction is an example. The two separate cycleway ways,
`60472279` and `59313979`, end 32 m apart, and only footways tagged `bicycle=dismount` connect
them. The bike filter drops those footways, so the dashboard shows a gap that matches OSM but not
the paint on the ground.

We do not edit OSM. Treat the dashboard as evidence for where to look, not as a replacement for
verification, and check every suggested new lane against recent satellite imagery and a site visit
before it enters a plan.

## Tests

`tests/test_network_lane_tags.py` covers every tagging combination on the wiki page, including the
alternatives ("or" rows), plus the extra sections. Each case runs twice: once on a hand-built graph
and once through OSMnx's OSM XML parser, which is where boolean `oneway` values, node order, and tag
filtering are exercised.

```bash
pytest tests/test_network_lane_tags.py
```

The output contract is unchanged: the same five columns and `EdgesSchema` as before.
