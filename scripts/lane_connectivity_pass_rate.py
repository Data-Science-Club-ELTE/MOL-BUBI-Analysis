#!/usr/bin/env python3
"""Run the lane-connectivity pass-rate test.

Defaults to the mock fixtures; point it at real tables once they exist:
  python scripts/lane_connectivity_pass_rate.py \
      --stations data/processed/stations.parquet \
      --population data/processed/population.parquet \
      --edges data/processed/edges.parquet
"""

import argparse
from pathlib import Path

from bubi.contracts.io import load_contract_table
from bubi.stations.diagnostics import lane_connectivity_pass_rate

FIX = Path("tests/fixtures")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stations", default=FIX / "sample_stations.parquet")
    ap.add_argument("--population", default=FIX / "sample_population.parquet")
    ap.add_argument("--edges", default=FIX / "sample_edges.parquet")
    ap.add_argument("--out", default="outputs/exports/lane_connectivity_pass_rate.csv")
    a = ap.parse_args()

    res = lane_connectivity_pass_rate(
        load_contract_table("population", a.population),
        load_contract_table("stations", a.stations),
        load_contract_table("edges", a.edges),
    )
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(a.out, index=False)
    print(res.to_string(index=False))
    print(f"\nSaved to {a.out}")
