#!/usr/bin/env python3
"""Report the demand-weighted mean trip distance of the gravity model for several betas.

Defaults to the processed city tables:
  python scripts/gravity_mean_distance.py
  python scripts/gravity_mean_distance.py --betas 0.0006666667 0.0002419675
"""

import argparse
from pathlib import Path

import pandas as pd

from bubi.demand.gravity import (
    DEFAULT_BETA_DECAY,
    assign_catchment_population,
    demand_weighted_mean_trip_distance,
    generate_synthetic_trips,
)

PROCESSED = Path("data/processed")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stations", default=PROCESSED / "stations.parquet")
    parser.add_argument("--population", default=PROCESSED / "population.parquet")
    parser.add_argument(
        "--betas",
        type=float,
        nargs="+",
        default=[0.0015, 2 / 3_000.0, 0.00025, DEFAULT_BETA_DECAY],
    )
    args = parser.parse_args()

    stations = pd.read_parquet(args.stations)
    population = pd.read_parquet(args.population)
    catchment = assign_catchment_population(stations, population)
    print(
        f"stations: {len(stations)}, with residents in catchment: "
        f"{(catchment['catchment_population'] > 0).sum()}, "
        f"residents assigned: {catchment['catchment_population'].sum():,.0f} "
        f"of {population['population'].sum():,.0f}"
    )
    for beta in args.betas:
        trips = generate_synthetic_trips(stations, population, beta_decay=beta)
        mean_m = demand_weighted_mean_trip_distance(trips, stations)
        print(f"beta={beta:.10f}  pairs={len(trips)}  mean trip distance={mean_m:,.1f} m")
