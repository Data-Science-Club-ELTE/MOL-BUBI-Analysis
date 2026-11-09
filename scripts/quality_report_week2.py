"""Write docs/quality_report_week2.md: quality checks for stations, population and edges (#17).

Run from the repository root after `make install`:

    .venv/bin/python scripts/quality_report_week2.py

Tables that do not exist yet are listed as "not available" instead of failing.
Pass --official-population once an official Budapest figure has been agreed.
"""

import argparse
from pathlib import Path

from bubi.contracts.io import load_contract_table
from bubi.profiling import build_quality_report, profile_dataset

# Futár snapshot 2026-10-18: 925 records, of which 704 are fixed ("virtual") stations.
# Source: docs/ingestion_notes.md sections 4 and 8.
FUTAR_STATION_COUNT = 704


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stations", default="data/processed/stations.parquet")
    parser.add_argument("--population", default="data/processed/population.parquet")
    parser.add_argument("--edges", default="data/processed/edges.parquet")
    parser.add_argument("--futar-count", type=int, default=FUTAR_STATION_COUNT)
    parser.add_argument("--official-population", type=float, default=None)
    parser.add_argument("--out", default="docs/quality_report_week2.md")
    args = parser.parse_args()

    options = {
        "stations": {"reference_count": args.futar_count},
        "population": {"reference_total": args.official_population},
        "edges": {},
    }
    paths = {"stations": args.stations, "population": args.population, "edges": args.edges}

    profiles, notes = [], []
    for name, path in paths.items():
        if not Path(path).exists():
            notes.append(f"`{name}`: not available yet (no file at `{path}`), not checked.")
            continue
        df = load_contract_table(name, path, validate=False)
        profiles.append(profile_dataset(df, name, validate_schema=True, **options[name]))
        notes.append(f"`{name}`: checked `{path}`.")

    notes.append(
        f"Futár reference count: {args.futar_count} fixed stations "
        "(snapshot 2026-10-18, docs/ingestion_notes.md §4 and §8)."
    )
    report = build_quality_report(profiles, title="Data Quality Report: Week 2", notes=notes)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
