# Dedicated bike lanes in OSM: the per-direction tag rule

Decision note for [#1](https://github.com/Data-Science-Club-ELTE/MOL-BUBI-Analysis/issues/1), decided
2026-11-15. It defines the OpenStreetMap (OSM) tags that populate `edges.has_dedicated_lane` for decision
D3 in the technical design: a road direction is covered when it has a dedicated cycle lane or track in
that direction. It is the rule the `src/bubi/network` module will implement.

The short answer: count `cycleway=lane`, `cycleway=track`, `cycleway:left/right/both=lane|track`,
the legacy `opposite_lane` and `opposite_track`, and separate `highway=cycleway` ways. Do not count
`shared_lane`, `share_busway`, `shoulder`, `no`, `separate`, or `oneway:bicycle=no` on its own.
The rest of this note defines direction, precedence, and the Budapest evidence.

## 1. Decision

A directed edge is covered when at least one of these conditions holds in its direction:

- the OSM way carries `cycleway=lane` or `cycleway=track`;
- the way carries `cycleway:left`, `cycleway:right`, or `cycleway:both` with value `lane` or `track`;
- the way carries the legacy `cycleway=opposite_lane` or `opposite_track` on the contraflow side;
- the direction is served by a separate `highway=cycleway` way, either directly on that way's own edge
  or through the parallel match in section 6.

A directed edge is not covered by any of these on their own:

- `cycleway=shared_lane`: a pictogram lane shared with motor traffic, not a lane set aside for bicycles.
- `cycleway=share_busway`: a bus lane that bicycles may use.
- `cycleway=shoulder`, `cycleway=no`, `cycleway=separate`, `cycleway=crossing`, `cycleway=sidewalk`,
  `cycleway=link`, `cycleway=proposed`, `cycleway=opposite`.
- `oneway:bicycle=no` on its own. It is a legal permission, not a facility.
- `bicycle=use_sidepath` on its own. It points to a parallel way, not to a lane on this way.
- `highway=path` or `highway=footway` with `bicycle=designated`. These are shared paths; section 8
  records this as a sensitivity, not a silent inclusion.
- `cyclestreet=yes` and `bicycle_road=yes`. The whole carriageway is shared, so there is no dedicated lane.

Table 1 lists the counted tags and the direction each one covers by default. Section 3 gives the exact
precedence and the cases where an explicit side tag overrides the default.

| Tag on the road way | Meaning | Direction by default |
| --- | --- | --- |
| `cycleway=lane` | Painted lane, part of the carriageway. | Both sides on a two-way road; the traffic-direction side on a one-way road. |
| `cycleway=track` | Physically separated track, still mapped on the road. | Same as `lane`. |
| `cycleway:left=lane` or `track` | Facility left of the way direction. | The `-` edge (against way direction). |
| `cycleway:right=lane` or `track` | Facility right of the way direction. | The `+` edge (with way direction). |
| `cycleway:both=lane` or `track` | Same facility on both sides. | `+` and `-`. |
| `cycleway:left:oneway=-1` or `cycleway:right:oneway=-1` | That side is contraflow. | The `-` edge. |
| `cycleway:left:oneway=no` or `cycleway:right:oneway=no` | That side is bidirectional. | `+` and `-`. |
| `cycleway=opposite_lane` or `opposite_track` | Legacy contraflow lane or track. | The `-` edge. |
| `highway=cycleway` | Separate cycleway or track, usually its own OSM way. | Its own `oneway` value; bidirectional when absent. |

The side defaults in Table 1 assume a two-way road. Table 2 overrides them on a one-way road: both sides
follow the permitted direction, except that a left-side facility on a street that is two-way for bicycles
is treated as contraflow.

## 2. Terms

- **OSM way direction**: the node order of the OSM way, from node A to node B.
- **Left and right**: left and right when looking along the way direction A to B. `cycleway:left` and
  `cycleway:right` use this sense, not the compass and not the direction of motor traffic.
- **Lane**: a painted strip inside the carriageway. **Track**: a physically separated path next to the
  carriageway. Both count as dedicated for D3; the distinction is recorded, not used to filter.
- **`+` edge**: the directed edge that follows the way direction A to B. **`-` edge**: the directed edge
  B to A. Using signs avoids confusing OSM's `forward` and `backward` with the direction of travel.
- **RHT**: right-hand traffic. Budapest is an RHT city, so the left side of a two-way road carries the
  `-` direction. A left-hand-traffic city would reverse the two defaults in section 3.2.

## 3. Per-direction rule

### 3.1 Which sides have a facility

Evaluate each side separately. For side `S` in `left`, `right`, take the first key that exists:

1. `cycleway:S` (the side-specific tag);
2. `cycleway:both`;
3. `cycleway` (the unsuffixed shortcut).

This order matters. An explicit `cycleway:right=no` must suppress a generic `cycleway=lane` on the right
side, and `cycleway:right=separate` must not be read as a lane just because `cycleway=track` is also
present. In the central Budapest bounding box (47.44 to 47.56 N, 18.98 to 19.12 E) used for this note,
`cycleway:both=no` appears on 3,070 ways, so the explicit `no` case is common, not theoretical.

Values that create a facility on that side: `lane` and `track`, plus the legacy `opposite_lane` and
`opposite_track`. Values that do not: `shared_lane`, `share_busway`, `shoulder`, `no`, `separate`,
`crossing`, `sidewalk`, `link`, `proposed`, `opposite`, and any unknown value. An unknown value is
logged and treated as absent, not guessed.

The unsuffixed `cycleway=lane` and `cycleway=track` are a shortcut, so which sides they fill depends on
the way:

| Way | Sides filled by the unsuffixed shortcut |
| --- | --- |
| Two-way road | Both sides. |
| One-way road, one-way for bicycles too | The right side only. This is the lane in the traffic direction. |
| One-way road with `oneway:bicycle=no` | Both sides. This is the wiki's M1 case: two-way cycling on a one-way street with a lane on each side. |

### 3.2 Direction of a side facility

Apply the first matching row in Table 2. `S` is the side and `+` and `-` are the way-direction signs from
section 2.

**Table 2. Direction of a side facility.**

| Order | Condition | Facility direction |
| --- | --- | --- |
| 1 | `cycleway:S:oneway=yes` or `1` | `+` |
| 2 | `cycleway:S:oneway=no` | Both |
| 3 | `cycleway:S:oneway=-1` | `-` |
| 4 | The value is legacy `opposite_lane` or `opposite_track` | `-` |
| 5 | The way is one-way for bicycles in the `+` direction: `oneway=yes` and `oneway:bicycle` is absent, `yes`, or `1` | `+` on both sides |
| 6 | The way is one-way for bicycles in the `-` direction: `oneway:bicycle=-1` | `-` on both sides |
| 7 | Otherwise: two-way for bicycles, either a two-way road or a motor one-way with `oneway:bicycle=no` | `+` on the right, `-` on the left |

Rows 1 to 4 are explicit data and always win. Row 5 is the wiki's implicit default for a one-way road:
both sides flow with the permitted direction unless the mapper writes a side `oneway` value. Row 6
covers the rarer case where bicycles may only travel against the way direction. Row 7 is the project
convention for the remaining cases; on a two-way road it is also the wiki default, with a left-side
facility facing `-` and a right-side facility facing `+`.

The one deliberate departure from the narrowest reading of the wiki is row 7 on a motor one-way street
with `oneway:bicycle=no`. The wiki says a left-side facility on `oneway=yes` is assumed to flow with
traffic unless `cycleway:left:oneway=-1` is written. We treat it as contraflow when the street is
two-way for bicycles, because the left-side facility otherwise has no legal forward user: forward
cyclists use the right side, and `oneway:bicycle=no` is exactly the tag that makes the backward trip
legal. Wiki example M1 (`oneway=yes` + `oneway:bicycle=no` + `cycleway=lane`) describes lanes on both
sides of such a street, and a forward-only left lane would contradict that picture. The case is small in
practice (a handful of ways in central Budapest) and is listed in the data-quality checks in section 9.
An explicit `cycleway:left:oneway=yes` still overrides the convention.

### 3.3 Directed edges

For a selected way, build the directed edges that cyclists may actually use:

- A two-way way has a `+` and a `-` edge.
- A one-way way without `oneway:bicycle=no` has only the permitted edge. The opposite edge is absent, not
  false.
- A one-way way with `oneway:bicycle=no` has both edges, because cyclists may travel both ways.
- A way with `oneway:bicycle=-1` has only the `-` edge, because bicycles may travel only against the
  way direction.

For a `highway=cycleway` way, the same oneway rules apply to the way itself: `oneway=yes` gives the
`+` edge, `oneway=-1` gives the `-` edge, and an absent or `no` value gives both. `oneway:bicycle=no`
restores the second edge on an otherwise one-way cycleway.

Then set the boolean:

- `+` edge: true when any side facility has direction `+` or both.
- `-` edge: true when any side facility has direction `-` or both.
- No facility on a side means false for that side, never a fallback to the generic tag that was already
  overridden by an explicit `no`.

A two-way road with only `cycleway:right=lane` therefore has `+` true and `-` false. Cyclists may still
ride the `-` direction in the carriageway, but they have no dedicated lane there.

### 3.4 `oneway=-1`

Normalize before applying the rule. Reverse the way's node order, swap the `cycleway:left*` and
`cycleway:right*` keys, and reverse the numeric side `oneway` values: `yes` becomes `-1`, `-1` becomes
`yes`, and `no` stays `no`. After that the way reads as `oneway=yes` and Tables 1 and 2 apply
unchanged. Handle `oneway:bicycle=-1` with Table 2 row 6 instead; it describes a bicycle direction, not
a way-geometry problem.

## 4. Worked Budapest examples

All tags below were read from the live OSM API on 2026-11-15. `+` and `-` are relative to each way's
node order.

### 4.1 Üllői út: tracks on both sides of a two-way road

Way [55055048](https://www.openstreetmap.org/way/55055048), `highway=secondary`, no `oneway`, `lanes=3`,
`cycleway:both=track`.

- Both sides get a facility from `cycleway:both`.
- The way is two-way for bicycles, so row 7 applies: right is `+`, left is `-`.
- Result: `+` true, `-` true.
- The tracks are tagged on the road here. Where the same street is split and the track is a separate
  `highway=cycleway` way, that way's own edge is true as well; section 6 covers the duplicate.

### 4.2 Dózsa György út: one lane, one direction

Way [5584188](https://www.openstreetmap.org/way/5584188), `highway=secondary`, `oneway=yes`, `lanes=3`,
`cycleway:left=no`, `cycleway:right=lane`, `cycleway:right:lane=exclusive`.

- Right side: a lane. Left side: explicit `no`.
- The way is one-way for bicycles in the `+` direction, so row 5 gives the right-side lane the `+`
  direction.
- Result: `+` true. The `-` edge is absent because `oneway=yes` and `oneway:bicycle` is not `no`.
- The `exclusive` sub-tag records the paint style. An `advisory` lane would still count as `lane`.

### 4.3 Akadémia utca: a contraflow lane and a shared lane on the other side

Way [24034846](https://www.openstreetmap.org/way/24034846), `highway=residential`, `oneway=yes`, `lanes=1`,
`oneway:bicycle=no`, `cycleway:left=lane`, `cycleway:left:oneway=-1`,
`cycleway:right=shared_lane`, `cycleway:right:lane=pictogram`.

- Left side: a lane with explicit `-1`, so it covers the `-` edge.
- Right side: `shared_lane`, which is excluded. Forward cyclists share the carriageway, so there is no
  dedicated lane in the `+` direction.
- Result: `+` false, `-` true. Both edges exist because `oneway:bicycle=no` makes the street two-way for
  bicycles.
- This example is why `shared_lane` must not be counted: treating it as a lane would flip the forward
  result to true and hide a real gap on the right side of the street.

### 4.4 Bem rakpart: a parallel cycleway, not a lane on the road

Way [549685953](https://www.openstreetmap.org/way/549685953), `highway=tertiary`, `oneway=yes`,
`cycleway:left=no`, `cycleway:right=separate`, `bicycle=use_sidepath`.

- `separate` and `use_sidepath` are pointers. They do not put a facility on the road way.
- The parallel way is [386360862](https://www.openstreetmap.org/way/386360862) (`highway=cycleway`,
  `oneway=yes`) and [386360870](https://www.openstreetmap.org/way/386360870) (`highway=cycleway`, no
  `oneway`). They run within about 30 m of the road edge.
- Direct reading: the road edges are false; the cycleway edges are true in their own directions.
- If the project transfers parallel coverage to the road edge (section 6), the `+` road edge becomes true
  through the match, and the road edge carries `lane_source=parallel`.
- `bicycle=use_sidepath` also means cyclists must not use the road edge when the cycleway is usable.
  Routing should prefer the cycleway edge, so the false road edge does not create a gap in practice.

## 5. Precedence and conflicts

Use this order whenever several tags could describe the same side:

1. The side-specific value, including `no` and `separate`.
2. `cycleway:both`.
3. The unsuffixed `cycleway`.

Two consequences are worth stating explicitly:

- `cycleway:right=separate` plus `cycleway=track` does not mean a track on the right of the road. The
  right side is a separate way; only the left side can fall back to the unsuffixed track.
- `cycleway:right=no` plus `cycleway=lane` leaves the left side covered by the shortcut and the right side
  empty. The explicit `no` wins.

A sub-tag such as `cycleway:right:lane=exclusive` or `advisory` describes the marking, not the kind. It
does not change a `lane` into something else and it is not required for the boolean. `pictogram` normally
accompanies `shared_lane` and is excluded with it.

## 6. Parallel cycleways

A parallel cycleway appears in two forms:

- `cycleway:left=separate` or `cycleway:right=separate` on the road way;
- `bicycle=use_sidepath`, `bicycle:forward=use_sidepath`, or `bicycle:backward=use_sidepath` on the road
  way. The direction-specific forms say that only that direction must use the sidepath.

These tags are pointers. Do not set `has_dedicated_lane` on the road way from `separate` alone, and do
not count `use_sidepath` as a lane. The parallel `highway=cycleway` way is a true edge on its own, and
its `oneway` value gives its direction. That is enough for routing.

For D3 coverage, which is judged per road direction, option 1 is the default:

1. **Match and transfer (default for D3).** Match the parallel cycleway to the road edge and transfer
   coverage. Require a counted way from section 1 within 30 m, normally `highway=cycleway`, roughly
   parallel (bearing difference below 30 degrees), with a compatible direction, overlapping at least half
   of the road edge. Use the side named by `separate`, or either side when only `use_sidepath` is
   present. Record `lane_source=parallel` so the duplicate with the cycleway's own edge is visible.
2. **Leave the road edge false (fallback).** Tag the road edge `bicycle_access=use_sidepath` and exclude
   it from gap candidates. The cycleway edge carries the true. Use this only if the network module
   defines cycleway edges as the coverage unit.

Do not do both silently. Pick one at the edge-granularity decision and apply it everywhere. The examples
in section 4 report the direct road-edge reading and the parallel match separately.

## 7. Mixed tags along one edge

The rule above is per OSM way. One directed edge can still contain more than one way after OSMnx
simplification, and a way can change its cycleway tags at a node. A single boolean cannot represent a
partly covered edge. This is the open question for the edge-granularity decision, not something this note
settles.

The options, in order of preference:

- **Split at every tag change.** Each edge gets one tag set and one boolean. This keeps `osm_way_id`
  meaningful and makes the result reproducible. It increases the edge count.
- **Length-weighted majority.** Keep one edge and set the boolean from the share of its length with a
  facility. Record `lane_fraction` as an extra column. A threshold of 0.5 is the simplest choice.
- **Any true wins.** Set the edge true if any part is covered. This is the most optimistic and hides gaps;
  use it only if the analysis is about "is there any infrastructure along this corridor", not about gap
  detection.

Do not OR the tags of different ways silently. If the edge is not split, record the fraction and the
method in the output so a reader can tell a fully covered edge from a partly covered one.

Asymmetric tags on one way are not a mixed edge. `cycleway:left=track` plus `cycleway:right=lane` is a
normal case and is evaluated side by side. `cycleway:left=separate` plus `cycleway:right=lane` is also
normal: the left side is a parallel way and the right side is an on-road lane.

## 8. Scope and sensitivity

- **`highway=cycleway` with pedestrians.** A cycleway tagged `foot=designated` or `segregated=no` still
  counts. It is a cycleway by its main tag, even when pedestrians may use it. If the project wants
  exclusive-only coverage, add a `shared_with_pedestrians` flag and report both totals; do not change the
  boolean silently. In the full Budapest extract (47.35 to 47.61 N, 18.90 to 19.33 E), 453
  `highway=cycleway` ways have `segregated=no`, so this choice is visible in the results.
- **Shared paths mapped as `highway=path` or `highway=footway`.** These are excluded by default. The
  full Budapest extract has 35 `highway=path` and 18 `highway=footway` ways with
  `bicycle=designated`; a sensitivity run can include them as a separate class.
- **Cycle streets and bicycle roads.** `cyclestreet=yes` and `bicycle_road=yes` are shared carriageways,
  not dedicated lanes. They are excluded from the boolean. They can be a separate flag for a friendlier
  street, but they do not answer D3.
- **Crossings.** `highway=cycleway` plus `cycleway=crossing` is still a cycleway edge. Crossings are short
  and do not drive corridor scores. If a cleaner lane-only view is needed, exclude `cycleway=crossing`
  in a later layer, not in this rule.

## 9. Implementation notes

- Read the raw OSM way tags. OSMnx, the Python library that downloads and simplifies OSM street
  networks, keeps most `cycleway:*` keys on edges, but simplification can merge ways. Keep `osm_way_id`
  and split before the boolean is assigned.
- Normalize `oneway=-1` once, as described in section 3.4.
- Compute a side facility and its direction, then assign the two directed edges. Do not write two
  independent code paths for lanes and tracks; the kind is recorded but the direction logic is identical.
- Extra columns allowed by `EdgesSchema` (`strict=False`) make the decision auditable:
  `lane_kind` (`lane`, `track`, `cycleway`, none), `lane_source` (`on_way`, `parallel`, none),
  `bicycle_access` (`use_sidepath` or empty), and `lane_fraction` when an edge is not split.
- Data-quality flags to log, not silently repair:
  - a left-side or `both` facility on a motor one-way street with `oneway:bicycle=no` and no
    `cycleway:left:oneway`, where section 3.2 row 7 makes the contraflow assumption;
  - unsuffixed `cycleway=track` on a one-way road, where the wiki describes `track` as both sides but
    the shortcut table takes the traffic-direction side;
  - legacy `opposite_lane` or `opposite_track` on a one-way road without `oneway:bicycle=no`, where
    the tag claims a contraflow facility but the graph has no `-` edge;
  - `separate` or `use_sidepath` with no `highway=cycleway` within 30 m;
  - unknown `cycleway` values;
  - `cycleway:right=lane` and `cycleway:right=track` style conflicts that cannot occur in one tag set
    but can appear after a bad merge.
- Tests: one fixture per row of Table 2, plus the four examples in section 4. The expected booleans are
  in those examples.

## 10. How this note meets #1

| Acceptance criterion | Where it is covered |
| --- | --- |
| Covers `cycleway=lane` and `cycleway=track` | Section 1 and Table 1; side rules in section 3.1. |
| Covers `cycleway:left` and `cycleway:right` | Section 3.1, Table 2, and the precedence in section 5. |
| Covers `oneway:bicycle` | Table 2 rows 5 to 7 and the Akadémia utca example in section 4.3. |
| Covers parallel cycleways | Section 6 and the Bem rakpart example in section 4.4. |
| Defines availability relative to the OSM way direction | Sections 2, 3.2, and 3.4. |
| Demonstrated on three real Budapest examples | Sections 4.1, 4.2, 4.3, plus a fourth in 4.4. |
| Documents mixed tags for the edge-granularity decision | Section 7. |
| Merged into `develop` via pull request | Pending review of this note's pull request. |

## 11. Sources

- OSM Wiki, [Bicycle](https://wiki.openstreetmap.org/wiki/Bicycle): lane versus track, the L, M, T and S
  examples, and the `use_sidepath` convention.
- OSM Wiki, [Key:cycleway](https://wiki.openstreetmap.org/wiki/Key:cycleway): the shortcut and the
  requirement that the key is used on a `highway=*` way.
- OSM Wiki, [Key:cycleway:left](https://wiki.openstreetmap.org/wiki/Key:cycleway:left) and
  [Key:cycleway:right](https://wiki.openstreetmap.org/wiki/Key:cycleway:right): side values and the
  `separate` pointer.
- OSM Wiki, [Key:cycleway:right:oneway](https://wiki.openstreetmap.org/wiki/Key:cycleway:right:oneway):
  the implicit direction defaults for right-hand and left-hand traffic.
- OSM Wiki, [Tag:cycleway=lane](https://wiki.openstreetmap.org/wiki/Tag:cycleway%3Dlane) and
  [Tag:cycleway=track](https://wiki.openstreetmap.org/wiki/Tag:cycleway%3Dtrack): the one-way and
  contraflow cases.
- OSM Wiki, [Tag:highway=cycleway](https://wiki.openstreetmap.org/wiki/Tag:highway%3Dcycleway): separate
  ways for cyclists.
- OSM Wiki, [Key:oneway:bicycle](https://wiki.openstreetmap.org/wiki/Key:oneway:bicycle): the permission
  is not a facility.
