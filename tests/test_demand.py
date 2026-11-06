"""Tests for gravity demand generation and distance calibration."""

from pathlib import Path

import h3
import pandas as pd
import pytest
import yaml

from bubi.contracts.schemas import TripMatrixSchema
from bubi.demand.gravity import (
    DEFAULT_BETA_DECAY,
    assign_catchment_population,
    demand_weighted_mean_trip_distance,
    generate_synthetic_trips,
)

TARGET_MEAN_DISTANCE_M = 3_000.0


def test_fixture_trip_matrix_has_reportable_mean(sample_stations, sample_population):
    trips = generate_synthetic_trips(sample_stations, sample_population)

    TripMatrixSchema.validate(trips)
    assert not trips.empty
    assert trips["trip_count"].sum() == pytest.approx(
        0.05 * assign_catchment_population(sample_stations, sample_population)[
            "catchment_population"
        ].sum()
    )
    assert demand_weighted_mean_trip_distance(trips, sample_stations) == pytest.approx(
        1_160.637, abs=0.01
    )


def test_calibrated_beta_achieves_target_mean_on_2d_city_grid():
    stations_data = []
    population_data = []
    grid_size = 17
    center = (grid_size - 1) / 2
    latitude_step = 1_000 / 111_000
    longitude_step = 1_000 / (111_000 * 0.675)

    for row in range(grid_size):
        for column in range(grid_size):
            latitude = 47.5 + (row - center) * latitude_step
            longitude = 19.0 + (column - center) * longitude_step
            cell_id = h3.latlng_to_cell(latitude, longitude, 9)
            cell_latitude, cell_longitude = h3.cell_to_latlng(cell_id)
            station_id = f"station_{row}_{column}"
            stations_data.append(
                {
                    "station_id": station_id,
                    "name": station_id,
                    "lat": cell_latitude,
                    "lon": cell_longitude,
                }
            )
            population_data.append({"cell_id": cell_id, "population": 1.0})

    stations = pd.DataFrame(stations_data)
    population = pd.DataFrame(population_data)
    trips = generate_synthetic_trips(
        stations,
        population,
        k_scaling=1.0,
        beta_decay=DEFAULT_BETA_DECAY,
    )

    assert demand_weighted_mean_trip_distance(trips, stations) == pytest.approx(
        TARGET_MEAN_DISTANCE_M, abs=250.0
    )


def test_config_beta_matches_calibrated_default():
    config_path = Path(__file__).parents[1] / "config" / "default_config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert config["demand"]["gravity_beta"] == DEFAULT_BETA_DECAY
