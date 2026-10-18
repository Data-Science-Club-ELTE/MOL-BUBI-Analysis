"""Test suite for Pandera data contracts."""

import geopandas as gpd
import pandas as pd
import pandera.errors as pa_errors
import pytest

from bubi.contracts.schemas import (
    CorridorsSchema,
    EdgeScoresSchema,
    EdgesSchema,
    PopulationSchema,
    RoutesSchema,
    StationCandidatesSchema,
    StationsSchema,
    TripMatrixSchema,
)


def test_stations_contract_valid(sample_stations):
    validated = StationsSchema.validate(sample_stations)
    assert len(validated) > 0
    assert "station_id" in validated.columns
    assert validated["lat"].between(47.0, 48.0).all()


def test_stations_contract_invalid_lat():
    bad_df = pd.DataFrame(
        [{"station_id": "bad_01", "name": "Out of bounds", "lat": 10.0, "lon": 19.0}]
    )
    with pytest.raises(pa_errors.SchemaError):
        StationsSchema.validate(bad_df)


def test_population_contract_valid(sample_population):
    validated = PopulationSchema.validate(sample_population)
    assert len(validated) > 0
    assert (validated["population"] >= 0).all()


def test_edges_contract_valid(sample_edges):
    validated = EdgesSchema.validate(sample_edges)
    assert len(validated) > 0
    assert isinstance(validated, gpd.GeoDataFrame)
    assert "has_dedicated_lane" in validated.columns
    assert (validated["length_m"] > 0).all()


def test_station_candidates_contract_valid(sample_candidates):
    validated = StationCandidatesSchema.validate(sample_candidates)
    assert set(validated["scenario"].unique()).issubset({"lane_aware", "population_only"})


def test_routes_contract_valid(sample_routes):
    validated = RoutesSchema.validate(sample_routes)
    assert len(validated) > 0
    assert (validated["trip_count"] > 0).all()


def test_edge_scores_contract_valid(sample_edge_scores):
    validated = EdgeScoresSchema.validate(sample_edge_scores)
    assert len(validated) > 0
    assert (validated["rank"] > 0).all()


def test_corridors_contract_valid(sample_corridors):
    validated = CorridorsSchema.validate(sample_corridors)
    assert len(validated) > 0
    assert "corridor_id" in validated.columns


def test_trip_matrix_contract_valid(sample_trip_matrix):
    validated = TripMatrixSchema.validate(sample_trip_matrix)
    assert len(validated) > 0
    assert (validated["trip_count"] > 0).all()
