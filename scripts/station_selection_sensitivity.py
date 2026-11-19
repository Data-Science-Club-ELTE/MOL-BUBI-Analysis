"""Sweep station selection using real population and stations with fixture bike lanes."""

import argparse
import sys
from itertools import product
from pathlib import Path

import h3
import networkx as nx
import pandas as pd
import yaml

# Allow direct execution from a checkout without requiring the package to be
# installed in the active environment.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
for import_root in (PROJECT_ROOT / "src", PROJECT_ROOT):
    if import_root.exists() and str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from bubi.contracts.io import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    export_csv,
    load_contract_table,
)
from bubi.profiling.catchment import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    aggregate_to_parent,
    nearest_station_distance_m,
)
from bubi.stations.selector import (  # noqa: E402  # pyright: ignore[reportMissingImports]
    compute_lane_connectivity,
    filter_candidate_cells,
    select_proposed_stations,
)

SCENARIOS = ("population_only", "lane_aware")
POPULATION_RESOLUTION = 9
RESOLUTIONS = (8, POPULATION_RESOLUTION)
STATION_COUNTS = (5, 10, 15)
SPACINGS_M = (300.0, 400.0, 500.0)
MATCH_DISTANCE_M = 200.0


def match_station_count(default: list[str], selected: list[str]) -> int:
    """Count one-to-one station matches within a fixed distance of the default picks."""
    default_nodes = [("default", cell) for cell in default]
    selected_nodes = [("selected", cell) for cell in selected]
    graph = nx.Graph()
    graph.add_nodes_from(default_nodes)
    graph.add_nodes_from(selected_nodes)
    centers = {cell: h3.cell_to_latlng(cell) for cell in set(default) | set(selected)}
    for left, right in product(default_nodes, selected_nodes):
        distance = h3.great_circle_distance(centers[left[1]], centers[right[1]], unit="m")
        if distance <= MATCH_DISTANCE_M:
            graph.add_edge(left, right)
    matches = nx.bipartite.maximum_matching(graph, top_nodes=default_nodes)
    return len(matches) // 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/default_config.yaml"))
    parser.add_argument("--population", default="data/processed/population.parquet")
    parser.add_argument("--stations", default="data/processed/stations.parquet")
    parser.add_argument("--edges", default="tests/fixtures/sample_edges.parquet")
    parser.add_argument("--out", default="outputs/exports/station_selection_sensitivity.csv")
    args = parser.parse_args()

    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    scoring = config["station_scoring"]
    walk_m = scoring["walk_coverage_threshold_m"]
    base_n, base_spacing = scoring["candidate_n"], scoring["min_spacing_m"]
    base_resolution = config["spatial"]["h3_resolution"]
    if base_resolution != POPULATION_RESOLUTION:
        parser.error(f"the default run must use H3 resolution {POPULATION_RESOLUTION}")

    population = load_contract_table("population", args.population)
    if set(population["cell_id"].map(h3.get_resolution)) != {POPULATION_RESOLUTION}:
        parser.error(f"--population must contain H3 resolution {POPULATION_RESOLUTION} cells")
    stations = load_contract_table("stations", args.stations)
    edges = load_contract_table("edges", args.edges)

    cell_population = population["population"].to_numpy()
    outside_existing = nearest_station_distance_m(population["cell_id"], stations) > walk_m
    counts = sorted({*STATION_COUNTS, base_n})
    spacings = sorted({*SPACINGS_M, base_spacing})
    base_area = h3.average_hexagon_area(base_resolution, unit="km^2")
    rows = []
    for resolution in RESOLUTIONS:
        pop_grid = (
            population
            if resolution == base_resolution
            else aggregate_to_parent(population, resolution)
        )
        # Keep the implied density cutoff comparable when the cell area changes.
        area_ratio = h3.average_hexagon_area(resolution, unit="km^2") / base_area
        min_population = config["demand"]["population_threshold_per_cell"] * area_ratio
        candidates = filter_candidate_cells(pop_grid, stations, walk_m, min_population)
        connectivity = compute_lane_connectivity(
            candidates["cell_id"].tolist(), edges, stations, reach_m=scoring["R"]
        )
        candidates["lane_connectivity"] = candidates["cell_id"].map(connectivity)

        for scenario, n_stations, spacing_m in product(SCENARIOS, counts, spacings):
            scored = select_proposed_stations(candidates, scenario, n_stations, spacing_m)
            selected = scored.loc[scored["rank"].notna()].sort_values("rank")
            cells = selected["cell_id"].tolist()
            proposed = pd.DataFrame(
                [h3.cell_to_latlng(cell) for cell in cells], columns=["lat", "lon"]
            )
            nearby = nearest_station_distance_m(population["cell_id"], proposed) <= walk_m
            rows.append(
                {
                    "scenario": scenario,
                    "h3_resolution": resolution,
                    "requested_n": n_stations,
                    "min_spacing_m": spacing_m,
                    "min_population_per_cell": min_population,
                    "candidate_count": len(scored),
                    "positive_score_count": int(scored["score"].gt(0).sum()),
                    "selected_n": len(cells),
                    "shortfall": n_stations - len(cells),
                    "additional_residents": round(cell_population[outside_existing & nearby].sum()),
                    "is_default": (resolution, n_stations, spacing_m)
                    == (base_resolution, base_n, base_spacing),
                    "selected_cells": cells,
                }
            )

    defaults = {row["scenario"]: row["selected_cells"] for row in rows if row["is_default"]}
    for row in rows:
        cells = row["selected_cells"]
        default_cells = defaults[row["scenario"]]
        row["default_selected_n"] = len(default_cells)
        row["default_matches_within_200m"] = match_station_count(default_cells, cells)
        row["selected_cells"] = " ".join(cells)

    out = export_csv(pd.DataFrame(rows), args.out)
    print(f"Saved {len(rows)} settings to {out}")


if __name__ == "__main__":
    main()
