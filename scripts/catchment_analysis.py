"""Write docs/catchment_analysis.md and docs/catchment_map.html (issue #33).

One command, from the repository root after `make install`:

    .venv/bin/python scripts/catchment_analysis.py

Population per resolution comes from, in this order:
  - res 9: data/processed/population.parquet (the contract table);
  - res 8: summed exactly from the res-9 table;
  - res 10: only with --raster, via bubi.population.aggregate_population_to_h3
    (a res-9 table cannot be split into finer cells without inventing data).
"""

import argparse
from pathlib import Path

from bubi.contracts.io import load_contract_table
from bubi.profiling.catchment import (
    DEFAULT_DISTANCES_M,
    DEFAULT_RESOLUTIONS,
    aggregate_to_parent,
    build_catchment_report,
    catchment_table,
    resolution_check,
    write_coverage_map,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", default="data/processed/stations.parquet")
    parser.add_argument("--population", default="data/processed/population.parquet")
    parser.add_argument("--raster", default=None, help="Population GeoTIFF for res 8/9/10")
    parser.add_argument("--out", default="docs/catchment_analysis.md")
    parser.add_argument("--map", default="docs/catchment_map.html")
    args = parser.parse_args()

    stations = load_contract_table("stations", args.stations)
    notes = [f"Stations: `{args.stations}` ({len(stations)} stations)."]
    population = {}

    if args.raster:
        from bubi.population.grid import aggregate_population_to_h3

        for res in DEFAULT_RESOLUTIONS:
            population[res] = aggregate_population_to_h3(Path(args.raster), h3_resolution=res)
        notes.append(f"Population: raster `{args.raster}` aggregated to res 8, 9 and 10.")
    elif Path(args.population).exists():
        res9 = load_contract_table("population", args.population)
        population = {8: aggregate_to_parent(res9, 8), 9: res9}
        notes.append(
            f"Population: `{args.population}` (res 9), summed to res 8. "
            "Res 10 not computed: rerun with --raster."
        )
    else:
        notes.append(f"Population: no file at `{args.population}`; coverage not computed.")

    coverage = catchment_table(population, stations)
    map_path = None
    if 9 in population:
        map_path = str(write_coverage_map(population[9], stations, 350.0, args.map))

    report = build_catchment_report(
        coverage, resolution_check(DEFAULT_RESOLUTIONS, DEFAULT_DISTANCES_M), notes, map_path
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
