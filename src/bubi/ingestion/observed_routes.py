"""Convert real trip and GPS data into ``routes`` rows with ``route_type = "observed"``.

No real trip or GPS data has arrived yet. The input format is an assumption, written
down in ``src/bubi/ingestion/README.md`` (section 8) so it can be compared with the real
files when they come. Only the reading side should need to change then; the output is
the frozen ``routes`` contract, so nothing downstream changes.

Assumed input
- trips: ``trip_id``, ``start_station_id``, ``end_station_id``, ``start_time``, ``end_time``
- GPS points: ``trip_id``, ``timestamp``, ``lat``, ``lon`` (EPSG:4326)

Timestamps are ISO 8601. Values with an offset (``+02:00``, ``Z``) are used as given;
values without one are read as Europe/Budapest local time. Everything is stored in UTC.
Europe/Budapest is used again only to bin trips by local hour of day.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable

import pandas as pd

from bubi.contracts.schemas import RoutesSchema
from bubi.corridors.scoring import calculate_edge_route_volumes

LOCAL_TZ = "Europe/Budapest"
# Real trips can only use stations that exist today, which is the baseline scenario.
OBSERVED_SCENARIO = "baseline"
ROUTE_TYPE = "observed"

TRIP_COLUMNS = ("trip_id", "start_station_id", "end_station_id", "start_time", "end_time")
GPS_COLUMNS = ("trip_id", "timestamp", "lat", "lon")
ROUTE_COLUMNS = (
    "scenario",
    "start_station_id",
    "end_station_id",
    "route_type",
    "edges",
    "trip_count",
)
TOTALS_COLUMNS = ["scenario", "route_type", "routes", "trips", "edges", "volume"]
SAMPLE_SIZE = 10

_OFFSET_SUFFIX = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")

MapMatcher = Callable[[pd.DataFrame], list[str]]


class ConversionError(ValueError):
    """Raised when the input does not have the assumed structure."""


def map_match_trace(points: pd.DataFrame) -> list[str]:
    """PLACEHOLDER: map-match one GPS trace to an ordered list of directed ``edge_id`` s.

    To be completed by CS 2 following the geoinformatics member's map-matching plan.
    Contract with the converter (``src/bubi/ingestion/README.md`` section 8.1):

    - ``points`` holds one trip's valid GPS points, sorted by ``timestamp_utc``, with
      columns ``trip_id``, ``timestamp``, ``lat``, ``lon``, ``timestamp_utc`` and a
      0-based index.
    - The result lists directed ``edges.edge_id`` values (``u-v-key``) in travel order.
    - An empty list means the trace could not be matched; the converter counts the trip
      under ``unmatched_trace``. Exceptions are not caught and stop the conversion.
    """
    raise NotImplementedError(
        "Map-matching is a placeholder: CS 2 implements it with the geoinformatics plan."
    )


def to_utc(values: pd.Series) -> pd.Series:
    """Parse ISO 8601 timestamps into UTC.

    Values without an offset are Europe/Budapest local time. Unparseable values and
    local times that are ambiguous or do not exist (daylight-saving switches) become NaT.
    """
    text = values.astype("string").str.strip()
    has_offset = text.str.contains(_OFFSET_SUFFIX, na=False)
    result = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns, UTC]")
    if has_offset.any():
        result[has_offset] = pd.to_datetime(
            text[has_offset], format="ISO8601", utc=True, errors="coerce"
        )
    naive = ~has_offset & text.notna()
    if naive.any():
        local = pd.to_datetime(text[naive], format="ISO8601", errors="coerce")
        result[naive] = local.dt.tz_localize(
            LOCAL_TZ, ambiguous="NaT", nonexistent="NaT"
        ).dt.tz_convert("UTC")
    return result


def normalize_trips(trips: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return trips with UTC timestamps and a local hour bin, dropping invalid times.

    Adds ``start_time_utc``, ``end_time_utc`` and ``start_hour_local`` (0-23, in
    Europe/Budapest). A trip is invalid if a timestamp cannot be resolved or it ends
    before it starts.
    """
    _require_columns(trips, TRIP_COLUMNS, "trips")
    df = trips.copy()
    df["trip_id"] = df["trip_id"].astype(str)
    duplicated = df["trip_id"].duplicated()
    if duplicated.any():
        raise ConversionError(f"Duplicate trip_id values: {_sample(df.loc[duplicated, 'trip_id'])}")
    for column in ("start_station_id", "end_station_id"):
        df[column] = df[column].astype(str)

    df["start_time_utc"] = to_utc(df["start_time"])
    df["end_time_utc"] = to_utc(df["end_time"])
    invalid = (
        df["start_time_utc"].isna()
        | df["end_time_utc"].isna()
        | (df["end_time_utc"] < df["start_time_utc"])
    )
    report = {
        "invalid_time": int(invalid.sum()),
        "invalid_time_ids": _sample(df.loc[invalid, "trip_id"]),
    }

    df = df.loc[~invalid].drop(columns=["start_time", "end_time"]).reset_index(drop=True)
    df["start_hour_local"] = df["start_time_utc"].dt.tz_convert(LOCAL_TZ).dt.hour.astype(int)
    return df, report


def match_stations(trips: pd.DataFrame, stations: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Keep trips whose start and end stations are both in the Futár station list."""
    known = set(stations["station_id"].astype(str))
    start_known = trips["start_station_id"].isin(known)
    end_known = trips["end_station_id"].isin(known)
    unmatched = ~(start_known & end_known)
    unknown_ids = set(trips.loc[~start_known, "start_station_id"]) | set(
        trips.loc[~end_known, "end_station_id"]
    )
    report = {
        "unmatched_station": int(unmatched.sum()),
        "unmatched_station_trip_ids": _sample(trips.loc[unmatched, "trip_id"]),
        "unknown_station_ids": sorted(unknown_ids)[:SAMPLE_SIZE],
    }
    return trips.loc[~unmatched].reset_index(drop=True), report


def merge_identical_routes(rows: pd.DataFrame) -> pd.DataFrame:
    """Merge rows with the same scenario, station pair, route type and edge list."""
    keyed = rows.assign(_edges_key=rows["edges"].map(tuple))
    keys = ["scenario", "start_station_id", "end_station_id", "route_type", "_edges_key"]
    merged = keyed.groupby(keys, sort=True, as_index=False)["trip_count"].sum()
    merged["edges"] = merged["_edges_key"].map(list)
    return merged[list(ROUTE_COLUMNS)]


def convert_observed_routes(
    trips: pd.DataFrame,
    gps_points: pd.DataFrame,
    stations: pd.DataFrame,
    matcher: MapMatcher = map_match_trace,
    edges: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Convert trips and GPS points into observed ``routes`` rows.

    Steps: normalize timestamps, match station IDs to the Futár list, map-match each
    remaining trip's GPS trace with ``matcher``, then merge identical routes by summing
    ``trip_count``. Each dropped trip is counted in the report under the step that
    dropped it.

    If ``edges`` is given, a trip whose matched route uses an ``edge_id`` missing from
    it is dropped and counted under ``unknown_edge``. The volume step only checks the
    ``u-v-key`` form, so without this check such IDs would reach the volumes unnoticed.

    Returns:
        (routes validated by ``RoutesSchema`` with ``edges`` as lists, report dict)
    """
    _require_columns(gps_points, GPS_COLUMNS, "gps_points")
    normalized, time_report = normalize_trips(trips)
    matched, station_report = match_stations(normalized, stations)

    points = gps_points.copy()
    points["trip_id"] = points["trip_id"].astype(str)
    points["timestamp_utc"] = to_utc(points["timestamp"])
    invalid_points = points["timestamp_utc"].isna()
    points = points.loc[~invalid_points].sort_values(["trip_id", "timestamp_utc"], kind="stable")
    traces = {trip_id: group for trip_id, group in points.groupby("trip_id", sort=False)}
    known_edges = None
    if edges is not None:
        _require_columns(edges, ("edge_id",), "edges")
        known_edges = set(edges["edge_id"].astype(str))

    rows = []
    converted_hours: list[int] = []
    no_gps: list[str] = []
    unmatched_trace: list[str] = []
    unknown_edge: list[str] = []
    unknown_edge_ids: set[str] = set()
    for trip in matched.itertuples(index=False):
        trace = traces.get(trip.trip_id)
        if trace is None:
            no_gps.append(trip.trip_id)
            continue
        route_edges = [str(edge_id) for edge_id in matcher(trace.reset_index(drop=True))]
        if not route_edges:
            unmatched_trace.append(trip.trip_id)
            continue
        if known_edges is not None:
            missing = set(route_edges) - known_edges
            if missing:
                unknown_edge.append(trip.trip_id)
                unknown_edge_ids |= missing
                continue
        rows.append(
            {
                "scenario": OBSERVED_SCENARIO,
                "start_station_id": trip.start_station_id,
                "end_station_id": trip.end_station_id,
                "route_type": ROUTE_TYPE,
                "edges": route_edges,
                "trip_count": 1.0,
            }
        )
        converted_hours.append(trip.start_hour_local)

    if rows:
        routes = merge_identical_routes(pd.DataFrame(rows))
    else:
        routes = pd.DataFrame({column: [] for column in ROUTE_COLUMNS})
    routes = RoutesSchema.validate(routes)

    report = {
        "input_trips": len(trips),
        **time_report,
        **station_report,
        "no_gps": len(no_gps),
        "no_gps_trip_ids": no_gps[:SAMPLE_SIZE],
        "unmatched_trace": len(unmatched_trace),
        "unmatched_trace_trip_ids": unmatched_trace[:SAMPLE_SIZE],
        "unknown_edge": len(unknown_edge),
        "unknown_edge_trip_ids": unknown_edge[:SAMPLE_SIZE],
        "unknown_edge_ids": sorted(unknown_edge_ids)[:SAMPLE_SIZE],
        "invalid_gps_points": int(invalid_points.sum()),
        "converted_trips": len(converted_hours),
        "routes": len(routes),
        "trips_by_local_hour": dict(sorted(Counter(converted_hours).items())),
    }
    return routes, report


def volume_totals_by_route_type(routes: pd.DataFrame) -> pd.DataFrame:
    """Total trips and edge volume per scenario and route type.

    The volume step sums synthetic and observed routes of one scenario together, so it
    is run here on each (scenario, route type) group to keep the two sources apart.

    Returns:
        One row per (scenario, route_type) with ``routes`` (row count), ``trips`` (sum
        of ``trip_count``), ``edges`` (directed edges with volume) and ``volume`` (sum of
        edge volumes), sorted by scenario and route type.
    """
    rows = []
    for (scenario, route_type), group in routes.groupby(["scenario", "route_type"], sort=True):
        volumes = calculate_edge_route_volumes(group)
        rows.append(
            {
                "scenario": scenario,
                "route_type": route_type,
                "routes": len(group),
                "trips": float(group["trip_count"].sum()),
                "edges": len(volumes),
                "volume": float(volumes["volume"].sum()),
            }
        )
    return pd.DataFrame(rows, columns=TOTALS_COLUMNS)


def _require_columns(df: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ConversionError(f"{name} is missing columns: {missing}")


def _sample(values: pd.Series) -> list[str]:
    return [str(value) for value in values.head(SAMPLE_SIZE)]
