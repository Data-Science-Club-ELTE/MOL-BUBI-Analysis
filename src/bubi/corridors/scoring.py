"""Bike-lane gap detection, edge scoring, and corridor merging."""

import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd

VOLUME_INPUT_COLUMNS = ("scenario", "edges", "trip_count")
VOLUME_OUTPUT_COLUMNS = ["scenario", "edge_id", "volume"]

# Directed edge ID "u-v-key": two node IDs without dashes or spaces, then an integer key.
_EDGE_ID_PATTERN = re.compile(r"[^\s-]+-[^\s-]+-\d+")


def _empty_volumes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "scenario": pd.Series(dtype="object"),
            "edge_id": pd.Series(dtype="object"),
            "volume": pd.Series(dtype="float64"),
        }
    )


def _parse_edge_list(value: object) -> list[str]:
    """Turn one ``routes.edges`` cell into a list of edge IDs.

    Accepted forms (RoutesSchema allows a list or a JSON string):
    a list/tuple/numpy array, a JSON array string such as '["a-b-0", "b-c-0"]',
    or a single edge ID string such as "a-b-0".
    """
    if isinstance(value, (list, tuple, np.ndarray)):
        return [str(edge_id) for edge_id in value]
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError(f"routes.edges JSON must be a list, got {value!r}")
            return [str(edge_id) for edge_id in parsed]
        return [text] if text else []
    raise ValueError(
        f"routes.edges must be a list or JSON string of edge IDs, got {type(value).__name__}"
    )


def calculate_edge_route_volumes(
    df_routes: pd.DataFrame,
) -> pd.DataFrame:
    """Aggregate total trip volume passing through each directed edge.

    Args:
        df_routes: Table following ``RoutesSchema``. Only ``scenario``, ``edges``
            and ``trip_count`` are read.

    Returns:
        pd.DataFrame with columns:
            - ``scenario`` (str): copied from the routes.
            - ``edge_id`` (str): directed edge ID ``u-v-key``.
            - ``volume`` (float): total ``trip_count`` of the routes that traverse
              the edge in that direction.
        One row per (scenario, edge_id) with volume > 0, sorted by scenario,
        then volume (highest first), then edge_id.

    Counting rules:
        1. Direction: ``u-v-key`` and ``v-u-key`` are different edges and are
           counted separately. Edge IDs are never normalised.
        2. Repeated use: a route adds its ``trip_count`` once to each *distinct*
           edge it uses. A route passing the same directed edge twice (possible in
           map-matched GPS traces) still counts once, so volume is the number of
           trips using the edge in that direction (design doc section 7.1).
        3. Scenarios are aggregated independently.
        4. ``synthetic`` and ``observed`` routes of one scenario are summed
           together; filter ``route_type`` beforehand if only one is wanted.
        5. Routes with no edges or ``trip_count == 0`` contribute nothing.

    The result holds the ``scenario``, ``edge_id`` and ``volume`` fields of
    ``EdgeScoresSchema``; ``score`` and ``rank`` are added by
    ``detect_gaps_and_score_edges``.

    Raises:
        ValueError: if required columns are missing, ``trip_count`` is null,
            non-numeric or negative, or an ``edges`` value or edge ID is malformed.
    """
    missing = [c for c in VOLUME_INPUT_COLUMNS if c not in df_routes.columns]
    if missing:
        raise ValueError(f"routes is missing required column(s): {missing}")
    if df_routes["scenario"].isna().any():
        raise ValueError("routes.scenario contains null values")
    if df_routes["trip_count"].isna().any():
        raise ValueError("routes.trip_count contains null values")
    trip_count = pd.to_numeric(df_routes["trip_count"], errors="coerce")
    if trip_count.isna().any():
        raise ValueError("routes.trip_count must be numeric")
    if (trip_count < 0).any():
        raise ValueError("routes.trip_count must be non-negative")

    if df_routes.empty:
        return _empty_volumes()

    work = pd.DataFrame(
        {
            "route_row": np.arange(len(df_routes)),
            "scenario": df_routes["scenario"].to_numpy(),
            "edge_id": [_parse_edge_list(cell) for cell in df_routes["edges"]],
            "trip_count": trip_count.to_numpy(dtype="float64"),
        }
    )
    work = work[work["trip_count"] > 0]

    # One row per (route, edge traversal); empty edge lists become NaN and are dropped.
    work = work.explode("edge_id", ignore_index=True).dropna(subset=["edge_id"])
    if work.empty:
        return _empty_volumes()

    bad_ids = work.loc[~work["edge_id"].str.fullmatch(_EDGE_ID_PATTERN), "edge_id"]
    if not bad_ids.empty:
        raise ValueError(
            "edge IDs must be directed 'u-v-key' IDs; "
            f"invalid examples: {bad_ids.unique()[:5].tolist()}"
        )

    # Counting rule 2: each route counts once per distinct directed edge.
    work = work.drop_duplicates(subset=["route_row", "edge_id"])

    volumes = (
        work.groupby(["scenario", "edge_id"], as_index=False, sort=False)["trip_count"]
        .sum()
        .rename(columns={"trip_count": "volume"})
    )
    volumes = volumes.sort_values(
        ["scenario", "volume", "edge_id"],
        ascending=[True, False, True],
        kind="mergesort",
        ignore_index=True,
    )
    return volumes[VOLUME_OUTPUT_COLUMNS]


def detect_gaps_and_score_edges(
    gdf_edges: gpd.GeoDataFrame,
    df_volumes: pd.DataFrame,
    scenario: str = "baseline",
    continuity_factor: float = 1.0,
) -> pd.DataFrame:
    """Filter for missing-lane edges in given direction and score priority.

    Formula:
        score = volume * missing_gap_length_m * continuity_factor

    Returns:
        pd.DataFrame adhering to EdgeScoresSchema.
    """
    raise NotImplementedError("Gap scoring not implemented yet.")


def merge_edges_into_corridors(
    gdf_edges: gpd.GeoDataFrame,
    df_edge_scores: pd.DataFrame,
    scenario: str = "baseline",
) -> pd.DataFrame:
    """Merge contiguous directed gap edges into readable corridors and rank.

    Returns:
        pd.DataFrame adhering to CorridorsSchema.
    """
    raise NotImplementedError("Corridor merging not implemented yet.")
