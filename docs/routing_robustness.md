# Routing Robustness and Map-Matching Integration

**Module:** `src/bubi/routing/router.py` · **Tests:** `tests/test_routing.py` · **Contract:** `RoutesSchema`

## 1. Purpose

The synthetic route engine computes slope-penalized shortest paths across Budapest's street network using OpenStreetMap (OSM) data and elevation rasters (Digital Elevation Models, or DEM). In real-world urban networks, routing engines face several practical failure modes:

1. **Disconnected network components:** River barriers, pedestrianized zones, or boundary cuts can partition the directed graph into disjoint subgraphs.
2. **False elevation slopes:** DEM rasters sample terrain or water surfaces rather than elevated structures. Bridges over the Danube or tunnels beneath Gellért Hill register artificial vertical drops or steep climbs.
3. **Parallel edge ambiguity:** Multiple roadway segments connecting the same pair of nodes (e.g., dual carriageways or segregated cycleways) can produce non-deterministic route selections if ties are not handled explicitly.
4. **Degenerate trip inputs:** Single-station networks, zero-trip demand matrices, or stations placed outside graph boundaries must not crash the pipeline.
5. **Observed route ingestion seam:** A clean interface is required to turn map-matched Global Positioning System (GPS) traces into `RoutesSchema` rows without altering synthetic routing logic.

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

## 3. Map-Matching Seam: `routes_from_matched_edges`

The ingestion pipeline converts real trip records and GPS coordinates into observed routes (`route_type = "observed"`). To allow map-matching implementations to plug directly into the routes contract without modifying the synthetic routing engine, `bubi.routing` exposes:

```python
def routes_from_matched_edges(
    matched: list[dict[str, Any]],
    scenario: str = "baseline",
    route_type: str = "observed",
) -> pd.DataFrame:
```

### Input Specification

The function accepts a list of dictionaries, one per matched trip:

| Key | Type | Description |
|---|---|---|
| `start_station_id` | `str` | Origin Futár station identifier |
| `end_station_id` | `str` | Destination Futár station identifier |
| `edges` | `list[str]` or `str` | Ordered list of directed `edge_id`s (`u-v-key`) traversed |
| `trip_count` | `float` (optional) | Number of trips represented (default: `1.0`) |

### Output

Returns a `pandas.DataFrame` conforming strictly to `RoutesSchema`:
- Groups identical routes sharing `(scenario, start_station_id, end_station_id, route_type, edges)` and sums their `trip_count`.
- Serializes `edges` into comma-delimited strings for downstream parquet serialization.
- Validates against `RoutesSchema` with `strict=True`.

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
| `test_routes_from_matched_edges_*` | Validates observed routes ingestion seam, duplicate route aggregation, and schema conformity |
