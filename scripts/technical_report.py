"""Write docs/technical_report.md and docs/quality_report_final.md (issue #74).

One command, from the repository root after `make install`:

    .venv/bin/python scripts/technical_report.py

Real tables are read from data/processed/; a table that is missing there is read from
tests/fixtures/ and labelled "fixture" everywhere it appears.
"""

import argparse
import subprocess
from pathlib import Path

import pandas as pd

from bubi.contracts.io import load_contract_table
from bubi.demand.gravity import assign_catchment_population, demand_weighted_mean_trip_distance
from bubi.profiling import profile_dataset
from bubi.profiling.catchment import aggregate_to_parent, catchment_table
from bubi.profiling.report import (
    APPENDIX_PATH,
    FIXTURE,
    REAL,
    SYNTHETIC,
    Source,
    build_quality_report_final,
    build_technical_report,
    markdown_table,
)
from bubi.scenarios.runner import build_scenario_comparison_view
from bubi.stations.selector import filter_candidate_cells, select_proposed_stations

COMMAND = ".venv/bin/python scripts/technical_report.py"
PROCESSED = Path("data/processed")
FIXTURES = Path("tests/fixtures")
TABLES = [
    "stations",
    "population",
    "edges",
    "station_candidates",
    "routes",
    "edge_scores",
    "corridors",
    "trip_matrix",
]
# Tables a model computes from real inputs: synthetic, not observed.
MODELLED = {"trip_matrix", "routes", "edge_scores", "corridors", "station_candidates"}
DISTANCES = (300.0, 350.0, 400.0)
WALK_M, FLOOR, N, SPACING = 350.0, 100.0, 10, 400.0  # config/default_config.yaml


def locate(table: str) -> Source:
    real = PROCESSED / f"{table}.parquet"
    if real.exists():
        return Source(table, str(real), SYNTHETIC if table in MODELLED else REAL)
    return Source(table, str(FIXTURES / f"sample_{table}.parquet"), FIXTURE)


def commit_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="docs/technical_report.md")
    parser.add_argument("--quality", default="docs/quality_report_final.md")
    args = parser.parse_args()

    sources = {t: locate(t) for t in TABLES}
    data = {t: load_contract_table(t, s.path, validate=False) for t, s in sources.items()}
    st, pop = sources["stations"], sources["population"]
    stations, population = data["stations"], data["population"]
    commit = commit_hash()

    # ---------------------------------------------------------- quality profile
    profiles = [
        (profile_dataset(df, name, validate_schema=True), sources[name])
        for name, df in data.items()
    ]
    quality = build_quality_report_final(profiles, COMMAND, commit)

    # ------------------------------------------------------------------ results
    results = {}

    results["Inputs"] = (
        markdown_table(
            pd.DataFrame(
                [
                    {"measure": "Existing stations", "value": len(stations)},
                    {"measure": "Population cells (H3 res 9)", "value": len(population)},
                    {
                        "measure": "Residents in the study area",
                        "value": float(population["population"].sum()),
                    },
                    {
                        "measure": f"Cells with ≥ {FLOOR:.0f} residents",
                        "value": int((population["population"] >= FLOOR).sum()),
                    },
                ]
            ),
            {"value": "{:,.0f}"},
        ),
        [st, pop],
        "The study area is the bounding box in config, not the city boundary.",
    )

    coverage = catchment_table(
        {8: aggregate_to_parent(population, 8), 9: population}, stations, DISTANCES
    )
    results["Population covered by existing stations"] = (
        markdown_table(
            coverage[
                [
                    "resolution",
                    "distance_m",
                    "covered_population",
                    "covered_share",
                    "covered_area_km2",
                    "outside_cells_at_floor",
                ]
            ],
            {
                "distance_m": "{:.0f}",
                "covered_population": "{:,.0f}",
                "covered_share": "{:.1%}",
                "covered_area_km2": "{:.1f}",
                "outside_cells_at_floor": "{:,}",
            },
        ),
        [st, pop],
        "Straight-line distance: an upper bound on walking coverage (appendix §3). "
        "Resolution 8 is summed from resolution 9.",
    )

    catchments = assign_catchment_population(stations, population, WALK_M)
    trips, tm = data["trip_matrix"], sources["trip_matrix"]
    demand = pd.DataFrame(
        [
            {
                "measure": "Stations with residents within 350 m",
                "value": int((catchments["catchment_population"] > 0).sum()),
            },
            {
                "measure": "Residents in station catchments",
                "value": float(catchments["catchment_population"].sum()),
            },
            {"measure": "Directed station pairs with trips", "value": len(trips)},
            {"measure": "Total synthetic trips", "value": float(trips["trip_count"].sum())},
            {
                "measure": "Demand-weighted mean trip distance (m)",
                "value": demand_weighted_mean_trip_distance(trips, stations),
            },
        ]
    )
    results["Synthetic demand (gravity model)"] = (
        markdown_table(demand, {"value": "{:,.1f}"}),
        [st, pop, tm],
        "Demonstration only (appendix §1.1): trips are invented by the model, not observed.",
    )

    candidates = filter_candidate_cells(population, stations, WALK_M, FLOOR)
    picked = select_proposed_stations(candidates, "population_only", N, SPACING)
    top = picked[picked["rank"].notna()].sort_values("rank")
    results["Proposed stations, population_only"] = (
        [f"{len(candidates):,} candidate cells; {len(top)} selected.", ""]
        + markdown_table(
            top[["rank", "cell_id", "population", "score"]],
            {"population": "{:,.0f}", "score": "{:.3f}"},
        ),
        [st, pop],
        "Real inputs; candidate filter uses straight-line distance (appendix §3).",
    )

    sc = sources["station_candidates"]
    la = data["station_candidates"]
    la = la[(la["scenario"] == "lane_aware") & la["rank"].notna()].sort_values("rank")
    results["Proposed stations, lane_aware"] = (
        markdown_table(
            la[["rank", "cell_id", "population", "lane_connectivity", "score"]],
            {"population": "{:,.0f}", "lane_connectivity": "{:,.0f}", "score": "{:.3f}"},
        ),
        [sc],
        "Lane connectivity needs real edges, which do not exist yet.",
    )

    es, co = sources["edge_scores"], sources["corridors"]
    corridors = data["corridors"].copy()
    corridors["edges"] = corridors["edge_ids"].map(len)
    results["Top corridors per scenario"] = (
        markdown_table(
            corridors[corridors["rank"] <= 5][
                ["scenario", "rank", "corridor_id", "edges", "score"]
            ],
            {"score": "{:,.0f}"},
        ),
        [co, es],
        "Demonstration only: synthetic routes on test edges.",
    )

    view = build_scenario_comparison_view(data["edge_scores"], data["corridors"], top_k=10)
    counts = view.groupby(["level", "label"]).size().reset_index(name="items")
    results["Robust vs station-dependent (top 10)"] = (
        markdown_table(counts),
        [es, co],
        "Demonstration only; the scenario runner does not exist yet (appendix §4, row 7).",
    )

    appendix = Path(APPENDIX_PATH)
    report = build_technical_report(
        results,
        list(sources.values()),
        appendix.read_text(encoding="utf-8") if appendix.exists() else None,
        COMMAND,
        commit,
    )

    for path, text in ((args.report, report), (args.quality, quality)):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8")
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
