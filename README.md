# MOL Bubi Dijkstra Routing Prototype

Prototype Dijkstra routing implementation with slope penalty awareness on sample graph fixtures for the **MOL Bubi Bike-Lane & Station Recommendation Tool**.

## Architecture & Features

This prototype implements the Synthetic Route Engine described in the [Technical Design Document](bubi-technical-design.md) (Section 6.4) and fulfills all acceptance criteria in [task.md](task.md):

1. **Traversable Graph Loader**:
   Loads edge tables conforming to the `EdgesSchema` data contract (e.g. `tests/fixtures/sample_edges.parquet`) and constructs a directed multigraph (`DiGraph`).

2. **Slope-Aware Edge Cost Function (`compute_edge_weight`)**:
   Computes edge impedance using length and signed grade:
   $$\text{cost} = \text{length\_m} \times (1 + \alpha \times \max(0, \text{grade}))$$
   - Flat edges ($\text{grade} = 0$) and downhill edges ($\text{grade} < 0$) receive zero slope penalty ($\max(0, \text{grade}) = 0$).
   - Uphill edges receive a penalty proportional to the tunable multiplier $\alpha$.

3. **Dijkstra Shortest Path Routing (`dijkstra_shortest_path`)**:
   - Computes lowest-cost paths on the directed graph using min-heap priority queues.
   - Evaluates edge costs dynamically using `compute_edge_weight`.
   - Handles unreachable pairs gracefully without crashing (returns `RouteResult(found=False)`).

4. **Synthetic Route Engine (`SyntheticRouteEngine`)**:
   - Manages station-pair routing queries with route caching (shared across scenarios).
   - Generates and merges identical routes by summing `trip_count`.
   - Reports routed pairs, unroutable pairs, and dropped trips in `RouteReport`.
   - Emits route tables conforming to `RoutesSchema`.

5. **Data Contract Validators (`EdgesSchema` & `RoutesSchema`)**:
   - Checks schemas against Section 5 data contracts.
   - Reusable across pandas DataFrames, dictionary records, and custom table objects.

---

## Directory Structure

```text
MOL BUBI/
├── bubi/
│   ├── contracts/
│   │   ├── __init__.py
│   │   └── schemas.py          # EdgesSchema, RoutesSchema, SchemaError
│   ├── io/
│   │   ├── __init__.py
│   │   └── parquet.py          # Parquet reader & writer with Table abstraction
│   ├── routing/
│   │   ├── __init__.py
│   │   ├── cost.py             # compute_edge_weight function
│   │   ├── graph.py            # DiGraph and load_graph_from_edges
│   │   ├── dijkstra.py         # Dijkstra shortest path implementation
│   │   └── engine.py           # SyntheticRouteEngine with caching & report
│   └── __init__.py
├── scripts/
│   └── lint.py                 # Code linter and AST syntax validator
├── tests/
│   ├── fixtures/
│   │   ├── sample_edges.parquet  # Parquet fixture for testing
│   │   ├── sample_edges.json     # Human-readable JSON fixture
│   │   └── generate_sample_edges.py
│   ├── test_cost.py            # Unit tests for compute_edge_weight
│   ├── test_dijkstra.py        # Unit tests for Dijkstra and slope effects
│   ├── test_engine.py          # Unit tests for SyntheticRouteEngine
│   ├── test_fixtures.py        # End-to-end fixture acceptance tests
│   └── test_schemas.py         # Contract validation tests
├── Makefile                    # make test, make lint, make format
├── pyproject.toml              # Build metadata and dev tool configs
├── requirements.txt            # Dependency list
├── task.md                     # Acceptance criteria & task specification
└── README.md
```

---

## Acceptance Criteria Verification

| Criterion | Implementation & Test | Status |
| :--- | :--- | :---: |
| **Loads sample edge fixture and builds traversable graph** | `load_graph_from_edges('tests/fixtures/sample_edges.parquet')` tested in `test_fixtures.py::test_load_graph_builds_traversable_graph` | **PASS** |
| **Dijkstra returns route between connected pair** | `dijkstra_shortest_path` routes $1 \to 2$ in `test_fixtures.py::test_dijkstra_routes_connected_fixture_pair` | **PASS** |
| **Edge costs calculated using `compute_edge_weight`** | Integrated in Dijkstra relaxation and tested in `test_cost.py` & `test_dijkstra.py` | **PASS** |
| **Slope penalty affects route cost or route choice** | When $\alpha=0$, selects steep Path 2 ($[1, 4, 2]$, cost $100$); when $\alpha=10$, flips to flat Path 1 ($[1, 3, 2]$, cost $120 < 175$). Tested in `test_dijkstra.py::test_slope_penalty_affects_route_choice` | **PASS** |
| **Unreachable pair handled without crashing** | Routing to disconnected node $99$ returns `found=False` without exception. Tested in `test_dijkstra.py::test_unreachable_pair_handled_gracefully` | **PASS** |
| **Unit tests under `tests/` pass locally** | 33 comprehensive unit tests across 5 test modules passing locally | **PASS** |
| **Code formatted and linted with `make lint`** | Validated via `make lint` / `python scripts/lint.py` | **PASS** |

---

## Running Locally

### 1. Run Unit Tests
```bash
py -m unittest discover tests
# or
pytest tests
```

### 2. Run Linter
```bash
make lint
# or
py scripts/lint.py
```

### 3. Regenerate Fixtures
```bash
py tests/fixtures/generate_sample_edges.py
```
