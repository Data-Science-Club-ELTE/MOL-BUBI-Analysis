"""Bike-lane gap detection, edge scoring, and corridor merging."""

import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd

from bubi.contracts.schemas import EdgeScoresSchema

VOLUME_INPUT_COLUMNS = ("scenario", "edges", "trip_count")
VOLUME_OUTPUT_COLUMNS = ["scenario", "edge_id", "volume"]

GAP_EDGE_COLUMNS = ("edge_id", "length_m", "has_dedicated_lane")
GAP_VOLUME_COLUMNS = ("scenario", "edge_id", "volume")
EDGE_SCORE_COLUMNS = ["scenario", "edge_id", "volume", "score", "rank"]

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


def _empty_edge_scores() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "scenario": pd.Series(dtype="object"),
            "edge_id": pd.Series(dtype="object"),
            "volume": pd.Series(dtype="float64"),
            "score": pd.Series(dtype="float64"),
            "rank": pd.Series(dtype="int64"),
        }
    )


def _check_gap_edges(gdf_edges: pd.DataFrame) -> None:
    missing = [c for c in GAP_EDGE_COLUMNS if c not in gdf_edges.columns]
    if missing:
        raise ValueError(f"edges is missing required column(s): {missing}")
    if gdf_edges["edge_id"].isna().any():
        raise ValueError("edges.edge_id contains null values")
    duplicated = gdf_edges.loc[gdf_edges["edge_id"].duplicated(), "edge_id"]
    if not duplicated.empty:
        raise ValueError(
            "edges.edge_id must be unique (one row per directed edge); "
            f"duplicates: {duplicated.unique()[:5].tolist()}"
        )
    lane = gdf_edges["has_dedicated_lane"]
    # A string such as "False" would count as True, so only real booleans are accepted.
    if not pd.api.types.is_bool_dtype(lane) or lane.isna().any():
        raise ValueError("edges.has_dedicated_lane must be boolean with no null values")
    length = pd.to_numeric(gdf_edges["length_m"], errors="coerce")
    if length.isna().any() or (length <= 0).any():
        raise ValueError("edges.length_m must be numeric and greater than 0")


def _check_gap_volumes(df_volumes: pd.DataFrame) -> pd.Series:
    missing = [c for c in GAP_VOLUME_COLUMNS if c not in df_volumes.columns]
    if missing:
        raise ValueError(f"volumes is missing required column(s): {missing}")
    if df_volumes["scenario"].isna().any() or df_volumes["edge_id"].isna().any():
        raise ValueError("volumes.scenario and volumes.edge_id must not contain null values")
    volume = pd.to_numeric(df_volumes["volume"], errors="coerce")
    if volume.isna().any():
        raise ValueError("volumes.volume must be numeric with no null values")
    if (volume < 0).any():
        raise ValueError("volumes.volume must be non-negative")
    duplicated = df_volumes.duplicated(subset=["scenario", "edge_id"])
    if duplicated.any():
        examples = df_volumes.loc[duplicated, ["scenario", "edge_id"]].head(5)
        raise ValueError(
            "volumes must have one row per (scenario, edge_id); "
            f"duplicates: {examples.to_dict('records')}"
        )
    return volume


def detect_gaps_and_score_edges(
    gdf_edges: gpd.GeoDataFrame,
    df_volumes: pd.DataFrame,
    scenario: str | None = None,
    continuity_factor: float = 1.0,
) -> pd.DataFrame:
    """Score the used road directions that have no dedicated bike lane (decision D3).

    Args:
        gdf_edges: Table following ``EdgesSchema``. Only ``edge_id``, ``length_m``
            and ``has_dedicated_lane`` are read. One row per *directed* edge, so
            ``u-v-key`` and ``v-u-key`` each carry their own lane flag.
        df_volumes: Output of ``calculate_edge_route_volumes`` (``scenario``,
            ``edge_id``, ``volume``), one row per (scenario, edge_id).
        scenario: Score only this scenario. ``None`` (default) scores every
            scenario found in ``df_volumes``.
        continuity_factor: Multiplier rewarding connected gaps. Fixed at 1.0
            until its definition is agreed in week 4 (design doc section 7.1).

    Returns:
        pd.DataFrame validated by ``EdgeScoresSchema`` with columns
        ``scenario``, ``edge_id``, ``volume``, ``score``, ``rank``.

    Rules:
        1. Direction: an edge is excluded only if it has a dedicated lane in
           *its own* direction. A road with a lane in one direction and none in
           the other keeps only the missing direction.
        2. Only edges with ``volume > 0`` are scored; unused edges are not gaps
           worth ranking.
        3. ``score = volume * gap length (m) * continuity_factor``. The gap length
           is the edge's ``length_m``: the whole edge lacks a lane in that direction.
        4. ``rank`` restarts at 1 in every scenario, highest score first. Ties are
           broken by higher volume, then by ``edge_id``, so ranks are unique
           and repeatable.
        5. Output is sorted by scenario, then rank.

    Raises:
        ValueError: if required columns are missing or malformed, edge IDs are
            duplicated, ``continuity_factor`` is negative, or ``df_volumes``
            contains an edge that is not in ``gdf_edges`` (routes and edges
            must come from the same frozen graph).
    """
    if continuity_factor < 0 or not np.isfinite(continuity_factor):
        raise ValueError("continuity_factor must be a finite, non-negative number")
    _check_gap_edges(gdf_edges)
    volume = _check_gap_volumes(df_volumes)

    work = pd.DataFrame(
        {
            "scenario": df_volumes["scenario"].astype(str).to_numpy(),
            "edge_id": df_volumes["edge_id"].astype(str).to_numpy(),
            "volume": volume.to_numpy(dtype="float64"),
        }
    )
    if scenario is not None:
        work = work[work["scenario"] == scenario]

    edges = pd.DataFrame(
        {
            "edge_id": gdf_edges["edge_id"].astype(str).to_numpy(),
            "length_m": pd.to_numeric(gdf_edges["length_m"]).to_numpy(dtype="float64"),
            "has_dedicated_lane": gdf_edges["has_dedicated_lane"].to_numpy(dtype=bool),
        }
    )
    unknown = work.loc[~work["edge_id"].isin(edges["edge_id"]), "edge_id"]
    if not unknown.empty:
        raise ValueError(
            "volumes contain edge IDs that are not in the edges table "
            "(routes and edges must use the same frozen graph); "
            f"examples: {unknown.unique()[:5].tolist()}"
        )

    # Rules 1 and 2: keep used directions with no lane in that direction.
    work = work[work["volume"] > 0].merge(edges, on="edge_id", how="left", validate="m:1")
    work = work[~work["has_dedicated_lane"]]
    if work.empty:
        return EdgeScoresSchema.validate(_empty_edge_scores())

    # Rule 3.
    work["score"] = work["volume"] * work["length_m"] * float(continuity_factor)

    # Rules 4 and 5.
    work = work.sort_values(
        ["scenario", "score", "volume", "edge_id"],
        ascending=[True, False, False, True],
        kind="mergesort",
        ignore_index=True,
    )
    work["rank"] = work.groupby("scenario").cumcount() + 1

    return EdgeScoresSchema.validate(work[EDGE_SCORE_COLUMNS])


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
