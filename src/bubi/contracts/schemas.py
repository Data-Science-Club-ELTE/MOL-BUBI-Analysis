"""Pandera schemas for the 7 core data contract tables plus trip matrix interface."""

import pandera.geopandas as pa_geo
from pandera.pandas import Check, Column, DataFrameSchema

# 1. Stations table (Section 5)
StationsSchema = DataFrameSchema(
    columns={
        "station_id": Column(str, nullable=False, unique=True, coerce=True),
        "name": Column(str, nullable=False, coerce=True),
        "lat": Column(float, Check.in_range(47.0, 48.0), nullable=False, coerce=True),
        "lon": Column(float, Check.in_range(18.0, 20.0), nullable=False, coerce=True),
    },
    strict=True,
    coerce=True,
)


# 2. Population table (Section 5)
PopulationSchema = DataFrameSchema(
    columns={
        "cell_id": Column(str, nullable=False, unique=True, coerce=True),
        "population": Column(
            float, Check.greater_than_or_equal_to(0.0), nullable=False, coerce=True
        ),
    },
    strict=True,
    coerce=True,
)


# 3. Edges table (Section 5) - GeoDataFrame
EdgesSchema = pa_geo.GeoDataFrameSchema(
    columns={
        "edge_id": pa_geo.Column(str, nullable=False, unique=True, coerce=True),
        "osm_way_id": pa_geo.Column(int, nullable=False, coerce=True),
        "length_m": pa_geo.Column(float, Check.greater_than(0.0), nullable=False, coerce=True),
        "has_dedicated_lane": pa_geo.Column(bool, nullable=False, coerce=True),
        "geometry": pa_geo.Column("geometry", nullable=False),
    },
    strict=False,  # Allow optional attributes like u, v, grade
    coerce=True,
)


# 4. Station candidates table (Section 5)
StationCandidatesSchema = DataFrameSchema(
    columns={
        "scenario": Column(
            str, Check.isin(["lane_aware", "population_only"]), nullable=False, coerce=True
        ),
        "cell_id": Column(str, nullable=False, coerce=True),
        "population": Column(
            float, Check.greater_than_or_equal_to(0.0), nullable=False, coerce=True
        ),
        "lane_connectivity": Column(
            float, Check.greater_than_or_equal_to(0.0), nullable=True, coerce=True
        ),
        "score": Column(float, Check.greater_than_or_equal_to(0.0), nullable=False, coerce=True),
        # nullable integer: unselected candidates have rank <NA>
        "rank": Column("Int64", Check.greater_than(0), nullable=True, coerce=True),
    },
    strict=True,
    coerce=True,
)


# 5. Routes table (Section 5)
RoutesSchema = DataFrameSchema(
    columns={
        "scenario": Column(
            str,
            Check.isin(["baseline", "lane_aware", "population_only"]),
            nullable=False,
            coerce=True,
        ),
        "start_station_id": Column(str, nullable=False, coerce=True),
        "end_station_id": Column(str, nullable=False, coerce=True),
        "route_type": Column(
            str, Check.isin(["synthetic", "observed"]), nullable=False, coerce=True
        ),
        "edges": Column(object, nullable=False),  # list or json string of edge_ids
        "trip_count": Column(float, Check.greater_than(0.0), nullable=False, coerce=True),
    },
    strict=True,
    coerce=True,
)


# 6. Edge scores table (Section 5)
EdgeScoresSchema = DataFrameSchema(
    columns={
        "scenario": Column(
            str,
            Check.isin(["baseline", "lane_aware", "population_only"]),
            nullable=False,
            coerce=True,
        ),
        "edge_id": Column(str, nullable=False, coerce=True),
        "volume": Column(float, Check.greater_than_or_equal_to(0.0), nullable=False, coerce=True),
        "score": Column(float, Check.greater_than_or_equal_to(0.0), nullable=False, coerce=True),
        "rank": Column(int, Check.greater_than(0), nullable=False, coerce=True),
    },
    strict=True,
    coerce=True,
)


# 7. Corridors table (Section 5)
CorridorsSchema = DataFrameSchema(
    columns={
        "scenario": Column(
            str,
            Check.isin(["baseline", "lane_aware", "population_only"]),
            nullable=False,
            coerce=True,
        ),
        "corridor_id": Column(str, nullable=False, coerce=True),
        "edge_ids": Column(object, nullable=False),  # list or json string of edge_ids
        "score": Column(float, Check.greater_than_or_equal_to(0.0), nullable=False, coerce=True),
        "rank": Column(int, Check.greater_than(0), nullable=False, coerce=True),
    },
    strict=True,
    coerce=True,
)


# Generator-to-route-engine hand-off interface (Section 5)
TripMatrixSchema = DataFrameSchema(
    columns={
        "scenario": Column(str, nullable=False, coerce=True),
        "start_station_id": Column(str, nullable=False, coerce=True),
        "end_station_id": Column(str, nullable=False, coerce=True),
        "trip_count": Column(float, Check.greater_than(0.0), nullable=False, coerce=True),
    },
    strict=True,
    coerce=True,
)
