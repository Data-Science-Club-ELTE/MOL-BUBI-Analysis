# Routing Robustness and Map-Matching Integration

**Module:** `src/bubi/routing` · **Tests:** `tests/test_routing.py` · **Contract:** `RoutesSchema`

## 1. Purpose

The synthetic route engine computes slope-penalized shortest paths across Budapest's street network using OpenStreetMap (OSM) data and elevation rasters (Digital Elevation Models, or DEM). In real-world urban networks, routing engines face several practical failure modes:

1. **Disconnected network components:** River barriers, pedestrianized zones, or boundary cuts can partition the directed graph into disjoint subgraphs.
2. **False elevation slopes:** DEM rasters sample terrain or water surfaces rather than elevated structures. Bridges over the Danube or tunnels beneath Gellért Hill register artificial vertical drops or steep climbs.
3. **Parallel edge ambiguity:** Multiple roadway segments connecting the same pair of nodes (e.g., dual carriageways or segregated cycleways) can produce non-deterministic route selections if ties are not handled explicitly.
4. **Degenerate trip inputs:** Single-station networks, zero-trip demand matrices, or stations placed outside graph boundaries must not crash the pipeline.
5. **Observed route ingestion seam:** A clean interface is required to connect map-matched Global Positioning System (GPS) traces into the ingestion converter without duplicating route-building logic or altering the synthetic router.

This document describes how `src/bubi/routing` addresses each of these robustness requirements.

---

## 2. Robustness Mechanisms

### 2.1 Disconnected Subgraphs and Island Nodes

When origin and destination stations snap to disconnected components of the street graph, Dijkstra's algorithm cannot find a path (`networkx.NetworkXNoPath`).

- **Handling:** The router checks reachability through `bubi.routing.report.unroutable_report()` before running shortest-path searches. Any unreachable pair is logged, aggregated, and excluded from the output without raising unhandled exceptions.
- **Reporting:** Every execution returns a routing report dictionary containing:
  - `total_pairs`: Total station pairs submitted in the trip matrix.
  - `routed_pairs`: Successfully routed pairs.
  - `unroutable_pairs`: Count of pairs where no directed path exists or stations failed to snap.
  - `dropped_trips`: Sum of trip demand lost due to unroutable pairs.
  - `pairs_computed` and `pairs_cached`: Execution efficiency metrics.

### 2.2 Bridge and Tunnel Elevation Interpolation

Budapest bridges (such as the Chain Bridge, Margaret Bridge, or Liberty Bridge) span the Danube, where DEM terrain cells reflect river-level elevation (~96 m above Baltic sea level) rather than the bridge deck (~106–110 m). Raw elevation sampling assigns bridges severe false downhill plunges and uphill climbs (e.g., ±15% to ±50% grade).

- **Handling:** The function `interpolate_bridge_grade(grade, is_bridge=False, is_tunnel=False)` zeroes the effective slope for bridge and tunnel edges:
  $$\text{effective\_grade} = 0.0 \quad \text{if } (\text{is\_bridge} \lor \text{is\_tunnel}) \text{ else } \text{raw\_grade}$$
- **Integration:** When `build_graph()` reads an edges `GeoDataFrame` with `is_bridge` or `is_tunnel` columns, it replaces raw slope values with interpolated zero-grade values before evaluating `compute_edge_weight()`. Flat bridge decks are therefore never falsely penalized by the uphill cost factor $\alpha$.

### 2.3 Deterministic Parallel Edge Resolution

In NetworkX `MultiDiGraph` structures, two nodes $u$ and $v$ can be connected by multiple directed edges indexed by integer keys (e.g., `u-v-0`, `u-v-1`).

- **Handling:** `_shortest_path_edges()` extracts the minimum-weight edge between consecutive nodes along the shortest path.
- **Tie-Breaking:** If parallel edges share identical weights, ties are resolved deterministically by iterating keys in sorted ascending order (`sorted(graph[a][b])`). Repeated executions on the same input graph always return identical route paths.

### 2.4 Degenerate Inputs

The router gracefully handles edge cases:

- **Empty trip matrix:** Returns an empty `DataFrame` matching `RoutesSchema` column specifications with zero counts across all report fields.
- **Single station:** If origin and destination match ($u = v$), an empty edge string (`""`) is emitted with the recorded `trip_count`, representing an intra-station movement. If no trip matrix rows exist, an empty valid table is returned.
- **Station outside the graph:** Stations farther than `max_distance_m` (default 200 m) from any graph node are flagged as `too_far` by `snap_stations()`. Their trips are dropped and counted in `unroutable_report` under the `station_too_far` reason.

---

## 3. Map-Matching Seam: `make_corridor_matcher`

The ingestion pipeline converts real trip records and GPS coordinates into observed routes (`route_type = "observed"`) via `bubi.ingestion.observed_routes.convert_observed_routes()`.

To prevent code duplication and maintain a single source of truth for observed routes, the routing module does not build redundant `routes` rows directly. Instead, per the agreed handoff contract (`docs/map_matching_plan.md` §5), routing exposes the matcher callable:

```python
from bubi.ingestion.observed_routes import convert_observed_routes
from bubi.routing import CorridorMatcher, make_corridor_matcher

# 1. Instantiate the matcher with the frozen street graph and bounding box
matcher = make_corridor_matcher(
    edges=edges,
    study_area_bbox=config["spatial"]["study_area_bbox"],
    buffer_m=50.0,
    max_gap_m=250.0,
)

# 2. Ingestion converter runs the matcher and builds observed routes rows
routes, report = convert_observed_routes(trips, gps, stations, matcher=matcher, edges=edges)
report["match_drops"] = dict(matcher.drops)
report["suspect_length_ratio"] = len(matcher.suspect)
```

### Seam Specification

- **Module:** `src/bubi/routing/map_matching.py`
- **Class:** `CorridorMatcher`
  - Attributes: `drops` (`Counter[str]`), `suspect` (`list[str]`), `edges`, `study_area_bbox`, `buffer_m`, `max_gap_m`.
  - Protocol: `__call__(points: pd.DataFrame) -> list[str]` accepting one trip's GPS points and returning directed `edge_id`s in travel order, or `[]` if unmatchable.
- **Factory:** `make_corridor_matcher(edges, study_area_bbox, buffer_m=50.0, max_gap_m=250.0)` returning a configured `CorridorMatcher`.

---

## 4. Verification and Test Suite

All robustness properties are validated in `tests/test_routing.py`:

| Test Name | Verified Property |
|---|---|
| `test_disconnected_graph_reports_every_unroutable_pair_no_crash` | Partitions graph into components; unroutable pairs reported, dropped trips counted, no crash |
| `test_interpolate_bridge_grade_zeroes_false_slope` | Verifies `interpolate_bridge_grade` sets bridge/tunnel grades to 0.0 |
| `test_bridge_that_would_divert_route_without_interpolation` | Proves synthetic DEM slope diverts path onto detour, while interpolation restores true bridge route |
| `test_build_graph_applies_bridge_interpolation` | Verifies `build_graph` applies grade interpolation when columns are present |
| `test_parallel_edges_deterministic` | Verifies lightest parallel edge is consistently chosen |
| `test_parallel_edges_same_weight_deterministic` | Verifies tie-breaking order across multiple runs |
| `test_same_input_twice_gives_same_route` | End-to-end verification that identical input produces identical output |
| `test_single_station_produces_self_route` | Handles single-node self-trip degenerate case |
| `test_single_station_no_self_trip` | Handles empty trip matrix on single-station graph |
| `test_zero_trip_matrix` | Handles empty DataFrame trip matrix |
| `test_station_outside_the_graph` | Handles unreachable foreign station IDs cleanly |
| `test_make_corridor_matcher_initialization` | Verifies CorridorMatcher initialization with default and custom parameters |
| `test_corridor_matcher_call_raises_not_implemented` | Verifies placeholder status per map-matching plan |
| `test_corridor_matcher_seam_wires_into_convert_observed_routes` | Verifies the handoff contract integration with ingestion's convert_observed_routes |
