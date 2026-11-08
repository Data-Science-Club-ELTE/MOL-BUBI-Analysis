# Map-matching plan: GPS traces to edges of the frozen graph

Plan for [#52](https://github.com/Data-Science-Club-ELTE/MOL-BUBI-Analysis/issues/52). It defines how one trip's GPS points become an ordered list of directed `edge_id`s, so that the placeholder `map_match_trace` in `src/bubi/ingestion/observed_routes.py` has a method behind it. The implementation belongs to routing ([#58](https://github.com/Data-Science-Club-ELTE/MOL-BUBI-Analysis/issues/58)).

**Status:** draft. No real trip or GPS data exists yet, and the frozen street graph is not built yet ([#15](https://github.com/Data-Science-Club-ELTE/MOL-BUBI-Analysis/issues/15)). Every numeric default below is an assumption to be checked against real data (§7).

Map matching here means: given GPS points sampled along a bicycle trip, find the sequence of street-graph edges the cyclist rode.

## 1. Method

### 1.1 Chosen method: corridor-constrained shortest path

For one trip:

1. **Clean the trace.**
   - Drop points outside the study bounding box (`spatial.study_area_bbox` in `config/default_config.yaml`).
   - Keep the rest in time order.
   - If fewer than 2 points remain, return no match.
2. **Check for gaps.** If two consecutive points are more than `max_gap_m` apart in a straight line, return no match. Points too far apart leave the corridor without the streets the cyclist used.
3. **Build the corridor.** Join the points into a line, in time order, and buffer it by `buffer_m`. Work in EPSG:23700, so distances are in metres.
4. **Select candidate edges.** Take every edge of the frozen `edges` table whose geometry intersects the corridor. Use a `shapely.STRtree` built once per matcher, not once per trip.
5. **Snap the endpoints.**
   - Start node: the node of a candidate edge nearest to the first point.
   - End node: the node of a candidate edge nearest to the last point.
   - Node positions come from the edge geometries, as in `src/bubi/routing/snapping.py`.
6. **Route.** Find the shortest path by `length_m` from the start node to the end node, on the directed graph built from the candidate edges only.
7. **Retry once.** If no path exists, repeat steps 3–6 once with `2 × buffer_m`. If there is still no path, return no match.
8. **Return** the path's `edge_id`s in travel order.

Routing uses length only, with no slope penalty. Map matching should recover the route that was ridden, not the route the model would prefer.

### 1.2 Why this method

- **Simple.** It reuses what the project already has: `shapely` for the corridor, and the directed graph and Dijkstra search that routing already uses (`src/bubi/routing/router.py`). No new dependency is needed.
- **Common in cycling studies.** Buffering the trace and taking the shortest path inside the buffer is a common way to derive ridden routes in bicycle route-choice studies. A Bologna study of bicycle GPS traces (Schweizer, Bernardi & Rupi 2016, *IET Intelligent Transport Systems* 10(4)) reports that its buffer-based algorithm recovered route length better than a topology-based algorithm from the literature and coped with signal loss.
- **Satisfies the project's constraints.** It runs locally on the frozen graph with no external service (decision D7), and it returns edge IDs of that graph directly (§3).
- **Easy to diagnose.** Each failure has one cause, and each cause is counted (§4).

### 1.3 Alternatives considered

| Method | Why not chosen now |
| --- | --- |
| Nearest edge per point, then a continuity check | In dense street grids, nearby parallel streets make single-point snapping pick the wrong street. It cannot fill the streets between two distant points. |
| Hidden Markov model (HMM) with Viterbi decoding (Newson & Krumm 2009) | More robust to noise and sparse sampling, but more code. It is the documented upgrade path (§6). |
| OSRM or Valhalla map matching | Needs a separate routing server and its own OSM import, which conflicts with D7, and it returns IDs of a different graph. |
| `mappymatch` (LCSS matcher) | Its examples download the network from OSM at run time, while this plan needs the frozen graph. The matcher is described as best for high-resolution traces. |
| `LeuvenMapMatching` (HMM) | Last release December 2022. Its map stores edges as node pairs, so the `key` part of `u-v-key` (parallel edges) would be lost. |

### 1.4 Parameters

| Parameter | Default | Basis |
| --- | --- | --- |
| `buffer_m` | 50 m | Assumption: wider than typical urban GPS error, narrower than most Budapest blocks. Tune on real data (§7). |
| Retry buffer | `2 × buffer_m` | Assumption; one retry only, so a bad trace cannot grow the corridor without limit |
| `max_gap_m` | 250 m | Assumption: about one minute of riding at 15 km/h. Newson & Krumm report their HMM still performing well at 30 s sampling, and a corridor method needs denser points than an HMM. |
| Study area | `spatial.study_area_bbox` | From config |
| Distance CRS | EPSG:23700 | Project analysis CRS, as in `snapping.py` |

The defaults belong in `config/default_config.yaml` under a `map_matching` key when the matcher is implemented, so they are tuned in one place.

## 2. Inputs

- **GPS points of one trip.** These are passed by `convert_observed_routes` after its own checks, as defined in `src/bubi/ingestion/README.md` §8.1: columns `trip_id`, `timestamp`, `lat`, `lon` (WGS 84, EPSG:4326) and `timestamp_utc`, sorted by `timestamp_utc`, with a 0-based index.
- **The `edges` table** of the frozen graph, `data/processed/edges.parquet`, validated by `EdgesSchema`.
- **The study bounding box** from config.

## 3. Candidate edges come from the frozen graph only

- **No downloads.** The matcher never downloads OSM data. It receives the `edges` table once, when it is constructed, and draws every candidate from it.
- **Edge IDs match the pipeline.** Returned IDs are `edges.edge_id` values in `u-v-key` form, so they match `routes`, `edge_scores` and the volume step without conversion.
- **Graph version recorded.** The report records the graph version the edges came from, `network.frozen_graph_version` in config, currently `budapest_osm_2026w1`, so an observed route can always be traced back to the graph it was matched on.
- **Defence in depth.** Pass the same `edges` table to the converter as well (`convert_observed_routes(..., edges=edges)`). Any returned ID missing from it is then dropped and counted under `unknown_edge`, as already implemented.

## 4. Failure handling

Every trip ends in exactly one outcome. Converted plus dropped trips must equal the input trips, as the converter already guarantees for its own checks.

| Reason | Where it is detected | Counted as |
| --- | --- | --- |
| Start or end station ID not in the Futár station list | Converter (implemented) | `unmatched_station` |
| Unparseable or daylight-saving-ambiguous time, or the trip ends before it starts | Converter (implemented) | `invalid_time` |
| Trip has no GPS points | Converter (implemented) | `no_gps` |
| Fewer than 2 points left after removing points outside the study area | Matcher | `outside_study_area` |
| Two consecutive points more than `max_gap_m` apart | Matcher | `gap` |
| No path inside the corridor, even after the retry | Matcher | `no_path_in_corridor` |
| Matched route uses an ID missing from `edges` | Converter (implemented) | `unknown_edge` |

The converter counts every matcher failure under `unmatched_trace`, because the matcher returns an empty list. The matcher keeps its own count per reason (§5). The two totals must agree: `outside_study_area + gap + no_path_in_corridor == unmatched_trace`.

**Quality flag, not a drop.** For each matched trip, compare the matched route length with the length of the GPS line. A ratio outside 0.8–1.5 (assumption) marks the match as suspect. Suspect matches are kept, counted as `suspect_length_ratio`, and listed by trip ID so they can be inspected on a map.

## 5. Handoff contract for #58

**Location:** `src/bubi/routing/map_matching.py`, the entry point that #58 exposes for map matching.

```python
from collections import Counter

import geopandas as gpd
import pandas as pd


class CorridorMatcher:
    """Map-match one GPS trace to edges of the frozen graph (docs/map_matching_plan.md)."""

    drops: Counter[str]  # outside_study_area, gap, no_path_in_corridor
    suspect: list[str]  # trip IDs with a suspect length ratio

    def __call__(self, points: pd.DataFrame) -> list[str]: ...


def make_corridor_matcher(
    edges: gpd.GeoDataFrame,
    study_area_bbox: tuple[float, float, float, float],
    buffer_m: float = 50.0,
    max_gap_m: float = 250.0,
) -> CorridorMatcher: ...
```

**Input of `__call__`:** one trip's points, exactly as in `src/bubi/ingestion/README.md` §8.1.

**Output of `__call__`:** directed `edge_id`s in travel order, or `[]` when the trace cannot be matched. Exceptions are reserved for programming errors and stop the conversion, as §8.1 states.

**Wiring in the ingestion layer:**

```python
matcher = make_corridor_matcher(edges, config["spatial"]["study_area_bbox"])
routes, report = convert_observed_routes(trips, gps, stations, matcher=matcher, edges=edges)
report["match_drops"] = dict(matcher.drops)
report["suspect_length_ratio"] = len(matcher.suspect)
report["frozen_graph_version"] = config["network"]["frozen_graph_version"]
```

The converter's signature does not change. The per-reason counts travel with the converter's existing report.

**Tests the implementation needs.** The fixture `tests/fixtures/mock_gps_points.csv` has 1–3 points per trip, several minutes apart. That is enough for the converter's contract tests but would be rejected under `gap` by this method. The matcher's unit tests therefore need synthetic dense traces: points interpolated along a known path of `tests/fixtures/sample_edges.parquet`, with added noise. Each test checks that the known path comes back, and each failure reason needs at least one test.

## 6. Upgrade path: hidden Markov model

Switch to an HMM matcher (Newson & Krumm 2009) if real data shows either of these:

- The median interval between GPS points is much longer than the corridor method can bridge, so `gap` drops a large share of trips.
- Visual checks (§7) find wrong parallel streets in the corridor matches.

An HMM keeps the same contract (§5), so the converter and the rest of the pipeline do not change. Starting values from the paper, which were measured on vehicle GPS:

- Candidate edges within 200 m of a point.
- Gaussian GPS noise with σ = 4.07 m.
- Transition probability based on the difference between route distance and straight-line distance.
- Trace split at breaks longer than 180 s.

The paper reports good results down to 30 s sampling. Bicycle and phone data in a dense city is likely noisier, so σ and the transition parameter should be re-estimated from the real data, as the paper does.

## 7. Validation once real data arrives

1. **Measure the sampling interval and GPS noise** of the real traces, then set `buffer_m` and `max_gap_m` from them. Record the values and their basis in this document.
2. **Run the converter** with the matcher and report every count in §4.
3. **Draw 20 random matched trips** over their GPS points on a map and check the streets by eye. Include suspect-ratio trips. Record how many are correct.
4. **Decide.** If the visual checks or the drop counts are poor, switch to the HMM (§6).

The map-matching implementation itself is out of scope for this plan. It is done under #58 and a follow-up implementation issue.

## 8. What stays synthetic, and labels for the dashboard (D5)

Decision D5: synthetic trips, routes and corridor rankings are an algorithm demonstration, labelled as such, never evidence of real cyclist behaviour.

- **Without real data**, nothing changes: all trips and routes stay synthetic (`route_type = synthetic`) and the dashboard keeps its demonstration label.
- **With real data:**
  - Observed routes exist only for the `baseline` scenario, because only existing stations have real trips.
  - The `lane_aware` and `population_only` scenarios keep synthetic trips and routes for the proposed stations, because nobody has ridden from a station that does not exist.
- **Dashboard requirements** when observed routes are present:
  - Show route volume by source (`route_type`), or label clearly which layer is synthetic and which is observed. `volume_totals_by_route_type` already gives the per-source totals.
  - Label observed routes "map-matched GPS traces". Keep the "algorithm demonstration" label on every synthetic layer.
  - Show the match rate: matched trips out of input trips, with the drop counts from §4.
  - Show the frozen graph version the routes were matched on.

## 9. Open points

- **Frozen graph (#15).** The plan assumes `edges` uses `u-v-key` IDs and EPSG:4326 geometry, as the contract and fixtures do today. If #15 changes either, §3 and §5 must follow.
- **Real data format.** It is still the assumption in `src/bubi/ingestion/README.md` §8, not confirmed by the data provider.
- **Parameter defaults.** `buffer_m`, `max_gap_m` and the 0.8–1.5 ratio band are assumptions until §7 is done.
- **Wrong-way riding.** The directed graph has no path for a cyclist who rode against a one-way street without a contraflow tag. Such trips end as `no_path_in_corridor`, and their share should be watched in §7.
- **Footpaths and parks.** Cyclists also ride on paths that may not be in the bike network, which can also cause `no_path_in_corridor`. The Bologna study notes the same problem.

## References

- Newson, P. and Krumm, J. (2009). Hidden Markov Map Matching Through Noise and Sparseness. ACM SIGSPATIAL GIS 2009. <https://www.microsoft.com/en-us/research/publication/hidden-markov-map-matching-noise-sparseness/>
- Schweizer, J., Bernardi, S. and Rupi, F. (2016). Map-matching algorithm applied to bicycle global positioning system traces in Bologna. *IET Intelligent Transport Systems*, 10(4), 244–250. DOI 10.1049/iet-its.2015.0135
- `src/bubi/ingestion/README.md` §8 and §8.1: input format and matcher contract
- `bubi-technical-design.md`: decisions D5 and D7
