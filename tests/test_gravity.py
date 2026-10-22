"""Tests for the gravity demand model (Task #2)."""

import numpy as np
import pandas as pd

from bubi.contracts.schemas import TripMatrixSchema
from bubi.demand.gravity import assign_catchment_population, generate_synthetic_trips


def test_catchment_no_double_counting(sample_stations, sample_population):
    c = assign_catchment_population(sample_stations, sample_population, 350.0)
    assert c["catchment_population"].sum() <= sample_population["population"].sum()
    assert len(c) == len(sample_stations)


def test_total_demand_is_k_times_population(sample_stations, sample_population):
    c = assign_catchment_population(sample_stations, sample_population)
    t = generate_synthetic_trips(sample_stations, sample_population, k_scaling=0.05)
    TripMatrixSchema.validate(t)
    assert np.isclose(t["trip_count"].sum(), 0.05 * c["catchment_population"].sum())


def test_no_self_trips_and_symmetric(sample_stations, sample_population):
    t = generate_synthetic_trips(sample_stations, sample_population)
    assert (t["start_station_id"] != t["end_station_id"]).all()
    m = t.pivot(index="start_station_id", columns="end_station_id", values="trip_count")
    assert np.allclose(m.fillna(0).to_numpy(), m.fillna(0).to_numpy().T)


def test_distance_decay(sample_stations, sample_population):
    near = generate_synthetic_trips(sample_stations, sample_population, beta_decay=0.0001)
    far = generate_synthetic_trips(sample_stations, sample_population, beta_decay=0.01)
    assert far["trip_count"].max() > near["trip_count"].max()  # mass concentrates on short pairs


def test_new_station_grows_demand(sample_stations, sample_population):
    import h3

    cell = "891e037aa0bffff"  # unserved fixture cell
    lat, lon = h3.cell_to_latlng(cell)
    new = pd.DataFrame([{"station_id": f"new:{cell}", "name": "proposed", "lat": lat, "lon": lon}])
    both = pd.concat([sample_stations, new], ignore_index=True)
    base = generate_synthetic_trips(sample_stations, sample_population)
    grown = generate_synthetic_trips(both, sample_population, scenario="lane_aware")
    assert grown["trip_count"].sum() > base["trip_count"].sum()  # D10
