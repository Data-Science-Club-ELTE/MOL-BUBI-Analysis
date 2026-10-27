"""Gravity-style synthetic trip demand generator."""

import math

import h3
import pandas as pd

from bubi.contracts.schemas import PopulationSchema, StationsSchema, TripMatrixSchema

EARTH_RADIUS_M = 6_371_000.0
DEFAULT_BETA_DECAY = 0.0006666667


def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine))

def assign_catchment_population(
    df_stations: pd.DataFrame,
    df_population: pd.DataFrame,
    walk_threshold_m: float = 350.0,
) -> pd.DataFrame:
    """Assign H3 population cells to their nearest station within the walk threshold.

    Returns:
        pd.DataFrame with columns: station_id, catchment_population
    """
    stations = StationsSchema.validate(df_stations)
    population = PopulationSchema.validate(df_population)
    if not math.isfinite(walk_threshold_m) or walk_threshold_m < 0:
        raise ValueError("walk_threshold_m must be a finite non-negative value")

    totals = dict.fromkeys(stations["station_id"], 0.0)
    station_rows = stations[["station_id", "lat", "lon"]].to_dict("records")
    for cell_id, cell_population in population[["cell_id", "population"]].itertuples(
        index=False, name=None
    ):
        cell_lat, cell_lon = h3.cell_to_latlng(cell_id)
        nearest_station = min(
            station_rows,
            key=lambda station: _haversine_distance_m(
                cell_lat, cell_lon, station["lat"], station["lon"]
            ),
            default=None,
        )
        if nearest_station is not None:
            distance_m = _haversine_distance_m(
                cell_lat,
                cell_lon,
                nearest_station["lat"],
                nearest_station["lon"],
            )
            if distance_m <= walk_threshold_m:
                totals[nearest_station["station_id"]] += float(cell_population)

    return pd.DataFrame(
        {
            "station_id": list(totals),
            "catchment_population": list(totals.values()),
        }
    )


def generate_synthetic_trips(
    df_stations: pd.DataFrame,
    df_population: pd.DataFrame,
    scenario: str = "baseline",
    k_scaling: float = 0.05,
    beta_decay: float = DEFAULT_BETA_DECAY,
    random_seed: int = 42,
) -> pd.DataFrame:
    """Generate station-to-station synthetic trip demand using a gravity model.

    Demand equation:
        trips(i -> j) proportional to P_i * P_j * exp(-beta * d_ij)
        Total demand = k * sum(P_i)

    Args:
        df_stations: Stations table adhering to StationsSchema.
        df_population: Population table adhering to PopulationSchema.
        scenario: 'baseline', 'lane_aware', or 'population_only'.
        k_scaling: Global demand scaling factor.
        beta_decay: Exponential distance decay parameter.
        random_seed: Seed for reproducibility.

    Returns:
        pd.DataFrame adhering to TripMatrixSchema.
    """
    stations = StationsSchema.validate(df_stations)
    if not math.isfinite(k_scaling) or k_scaling < 0:
        raise ValueError("k_scaling must be a finite non-negative value")
    if not math.isfinite(beta_decay) or beta_decay <= 0:
        raise ValueError("beta_decay must be a finite positive value")

    catchments = assign_catchment_population(df_stations, df_population)
    station_data = stations.merge(catchments, on="station_id", validate="one_to_one")
    station_data = station_data[station_data["catchment_population"] > 0].reset_index(drop=True)
    empty = pd.DataFrame(
        columns=["scenario", "start_station_id", "end_station_id", "trip_count"]
    )
    if len(station_data) < 2:
        return empty

    population = station_data["catchment_population"].tolist()
    station_rows = station_data[["station_id", "lat", "lon"]].to_dict("records")
    weighted_pairs = []
    for origin_index, origin in enumerate(station_rows):
        for destination_index, destination in enumerate(station_rows):
            if origin_index == destination_index:
                continue
            distance_m = _haversine_distance_m(
                origin["lat"], origin["lon"], destination["lat"], destination["lon"]
            )
            weight = (
                population[origin_index]
                * population[destination_index]
                * math.exp(-beta_decay * distance_m)
            )
            if weight > 0:
                weighted_pairs.append(
                    (origin["station_id"], destination["station_id"], distance_m, weight)
                )

    total_weight = sum(pair[3] for pair in weighted_pairs)
    total_demand = k_scaling * sum(population)
    if total_weight <= 0 or total_demand <= 0:
        return empty

    result = pd.DataFrame(
        [
            {
                "scenario": scenario,
                "start_station_id": origin_id,
                "end_station_id": destination_id,
                "trip_count": total_demand * weight / total_weight,
            }
            for origin_id, destination_id, _, weight in weighted_pairs
        ]
    )
    return TripMatrixSchema.validate(result)


def demand_weighted_mean_trip_distance(
    df_trips: pd.DataFrame, df_stations: pd.DataFrame
) -> float:
    """Return the trip-count-weighted mean straight-line distance in metres."""
    trips = TripMatrixSchema.validate(df_trips)
    stations = StationsSchema.validate(df_stations)
    if trips.empty or trips["trip_count"].sum() <= 0:
        raise ValueError("cannot compute mean distance for an empty trip matrix")

    coordinates = stations.set_index("station_id")[["lat", "lon"]]
    weighted_distance = 0.0
    for origin_id, destination_id, trip_count in trips[
        ["start_station_id", "end_station_id", "trip_count"]
    ].itertuples(index=False, name=None):
        try:
            origin = coordinates.loc[origin_id]
            destination = coordinates.loc[destination_id]
        except KeyError as error:
            raise ValueError(f"trip matrix references unknown station: {error.args[0]}") from error
        distance_m = _haversine_distance_m(
            origin["lat"], origin["lon"], destination["lat"], destination["lon"]
        )
        weighted_distance += float(trip_count) * distance_m

    return weighted_distance / float(trips["trip_count"].sum())
