Objective

Prototype Dijkstra routing on the sample graph using compute_edge_weight, including the effect of a slope penalty.
3. Data Contracts

    Input Tables: tests/fixtures/sample_edges.parquet
    Output Tables: A fixture route result or test output; no new persistent standard table is required for the prototype
    Schema Checked: EdgesSchema for input edges; RoutesSchema if the prototype emits a route table conforming to that contract

4. Acceptance Criteria

    The prototype loads the sample edge fixture and builds a traversable graph
    Dijkstra returns a route between a connected fixture pair
    Edge costs are calculated using compute_edge_weight
    A test demonstrates that the slope penalty affects route cost or route choice
    An unreachable pair is handled without crashing, if covered by the fixture or a focused test
    Unit tests are added under tests/ and pass locally
    Code is formatted and linted with make lint
    The prototype and tests are merged into develop via PR

