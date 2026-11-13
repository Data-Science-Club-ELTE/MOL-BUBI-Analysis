"""Bike-lane gap detection, edge scoring, and corridor merging."""

import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd

from bubi.contracts.schemas import CorridorsSchema, EdgeScoresSchema

VOLUME_INPUT_COLUMNS = ("scenario", "edges", "trip_count")
VOLUME_OUTPUT_COLUMNS = ["scenario", "edge_id", "volume"]

GAP_EDGE_COLUMNS = ("edge_id", "length_m", "has_dedicated_lane")
GAP_VOLUME_COLUMNS = ("scenario", "edge_id", "volume")
EDGE_SCORE_COLUMNS = ["scenario", "edge_id", "volume", "score", "rank"]
CORRIDOR_SCORE_COLUMNS = ("scenario", "edge_id", "score")
CORRIDOR_COLUMNS = ["scenario", "corridor_id", "edge_ids", "score", "rank"]
CONTINUITY_INPUT_COLUMNS = ("scenario", "edge_id", "base_score")
CONTINUITY_WEIGHT = 0.25
# Corridor IDs follow the sample fixture: corr_<scenario code>_<rank>, e.g. corr_bl_01.
SCENARIO_CODES = {"baseline": "bl", "lane_aware": "la", "population_only": "po"}

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


def _normalized_score_percentiles(scores: np.ndarray) -> np.ndarray:
    percentiles = np.zeros(len(scores), dtype="float64")
    positive = scores > 0
    positive_count = int(positive.sum())
    if positive_count == 1 and len(scores) > 1:
        percentiles[positive] = 1.0
    elif positive_count > 1:
        ranks = pd.Series(scores[positive]).rank(method="average").to_numpy()
        percentiles[positive] = (ranks - 1.0) / (positive_count - 1.0)
    return percentiles


def calculate_continuity_factors(df_gap_scores: pd.DataFrame) -> pd.Series:
    """Calculate bounded continuity multipliers for scored directed gap edges.

    ``df_gap_scores`` contains one row per scenario and edge, with ``base_score``
    equal to route volume times gap length. A neighbour is another scored gap edge
    that can follow or precede the edge in travel direction; a reverse U-turn is
    not a connection. Neighbour percentiles are averaged, so intersections do not
    accumulate a larger lift merely because they have more branches.

    Returns a dimensionless Series aligned to the input index. Isolated edges and
    edges in a single-edge graph receive a factor of 1.0.
    """
    missing = [column for column in CONTINUITY_INPUT_COLUMNS if column not in df_gap_scores]
    if missing:
        raise ValueError(f"gap scores are missing required column(s): {missing}")
    if df_gap_scores[["scenario", "edge_id"]].isna().any().any():
        raise ValueError("gap scores scenario and edge_id must not contain null values")
    if df_gap_scores.duplicated(["scenario", "edge_id"]).any():
        raise ValueError("gap scores must have one row per (scenario, edge_id)")
    base_score = pd.to_numeric(df_gap_scores["base_score"], errors="coerce")
    if base_score.isna().any() or not np.isfinite(base_score).all() or (base_score < 0).any():
        raise ValueError("gap scores base_score must be finite and non-negative")

    gaps = df_gap_scores.reset_index(drop=True)
    ends = {edge_id: _edge_ends(edge_id) for edge_id in gaps["edge_id"]}
    factors = np.ones(len(gaps), dtype="float64")

    for _, group_indices in gaps.groupby("scenario", sort=False).groups.items():
        indices = np.asarray(list(group_indices), dtype=int)
        scores = base_score.iloc[indices].to_numpy(dtype="float64")
        percentiles = _normalized_score_percentiles(scores)

        starts_at: dict[str, list[int]] = {}
        ends_at: dict[str, list[int]] = {}
        for index in indices:
            start_node, end_node = ends[gaps.at[index, "edge_id"]]
            starts_at.setdefault(start_node, []).append(index)
            ends_at.setdefault(end_node, []).append(index)

        percentile_by_index = dict(zip(indices, percentiles, strict=True))
        for index in indices:
            edge_id = gaps.at[index, "edge_id"]
            start_node, end_node = ends[edge_id]
            neighbours = set(ends_at.get(start_node, ())) | set(starts_at.get(end_node, ()))
            neighbours.discard(index)
            neighbours = {
                neighbour
                for neighbour in neighbours
                if ends[gaps.at[neighbour, "edge_id"]] != (end_node, start_node)
            }
            if neighbours:
                # Summed in value order, not row order: float addition is not associative, so
                # reordering the input rows could otherwise flip a tie in the final ranking.
                neighbour_mean = np.mean(sorted(percentile_by_index[n] for n in neighbours))
                factors[index] = 1.0 + CONTINUITY_WEIGHT * neighbour_mean

    return pd.Series(factors, index=df_gap_scores.index, name="continuity_factor")


def detect_gaps_and_score_edges(
    gdf_edges: gpd.GeoDataFrame,
    df_volumes: pd.DataFrame,
    scenario: str | None = None,
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

    Returns:
        pd.DataFrame validated by ``EdgeScoresSchema`` with columns
        ``scenario``, ``edge_id``, ``volume``, ``score``, ``rank``.

    Rules:
        1. Direction: an edge is excluded only if it has a dedicated lane in
           *its own* direction. A road with a lane in one direction and none in
           the other keeps only the missing direction.
        2. Only edges with ``volume > 0`` are scored; unused edges are not gaps
           worth ranking.
          3. ``score = volume * gap length (m) * continuity_factor``. The continuity
              factor is computed from connected gap edges in the same scenario and is
              bounded by 1.25. The gap length is the whole edge's ``length_m``.
        4. ``rank`` restarts at 1 in every scenario, highest score first. Ties are
           broken by higher volume, then by ``edge_id``, so ranks are unique
           and repeatable.
        5. Output is sorted by scenario, then rank.

    Raises:
        ValueError: if required columns are missing or malformed, edge IDs are
            duplicated, or ``df_volumes`` contains an edge that is not in
            ``gdf_edges`` (routes and edges must come from the same frozen graph).
    """
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

    work["base_score"] = work["volume"] * work["length_m"]
    work["continuity_factor"] = calculate_continuity_factors(work)
    work["score"] = work["base_score"] * work["continuity_factor"]

    # Rules 4 and 5.
    work = work.sort_values(
        ["scenario", "score", "volume", "edge_id"],
        ascending=[True, False, False, True],
        kind="mergesort",
        ignore_index=True,
    )
    work["rank"] = work.groupby("scenario").cumcount() + 1

    return EdgeScoresSchema.validate(work[EDGE_SCORE_COLUMNS])


def _empty_corridors() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "scenario": pd.Series(dtype="object"),
            "corridor_id": pd.Series(dtype="object"),
            "edge_ids": pd.Series(dtype="object"),
            "score": pd.Series(dtype="float64"),
            "rank": pd.Series(dtype="int64"),
        }
    )


def _edge_ends(edge_id: str) -> tuple[str, str]:
    """Start and end node of a directed edge ``u-v-key``."""
    start_node, end_node, _key = edge_id.split("-")
    return start_node, end_node


def _best_match(options: list[str], way: object, way_of: dict[str, object]) -> str | None:
    """The one edge a corridor should continue with, or None if there is no clear one.

    A single option is taken whatever its OSM way. With several (a crossing, fork or
    join), the corridor stays on its own street: it takes the option on the same OSM way
    if exactly one is; otherwise the corridor ends there.
    """
    if len(options) == 1:
        return options[0]
    same_street = [e for e in options if way_of[e] == way]
    return same_street[0] if len(same_street) == 1 else None


def _chain_gap_edges(way_of: dict[str, object]) -> list[list[str]]:
    """Group the gap edges of one scenario into corridors, each in travel order.

    ``way_of`` maps each gap edge ID to its OSM way ID. Edge ``a`` continues into edge
    ``b`` when ``b`` starts where ``a`` ends, ``b`` is not ``a`` driven backwards, and
    each is the other's single best match at that node (see :func:`_best_match`). Every
    edge ends up in exactly one corridor.
    """
    # Sorted once, so every loop below and therefore the result is independent of input order.
    edge_ids = sorted(way_of)
    ends = {edge_id: _edge_ends(edge_id) for edge_id in edge_ids}
    leaving: dict[str, list[str]] = {}
    arriving: dict[str, list[str]] = {}
    for edge_id in edge_ids:
        start_node, end_node = ends[edge_id]
        leaving.setdefault(start_node, []).append(edge_id)
        arriving.setdefault(end_node, []).append(edge_id)

    def is_reverse(first: str, second: str) -> bool:
        return ends[first] == ends[second][::-1]

    next_edge: dict[str, str] = {}
    has_previous: set[str] = set()
    for edge_id in edge_ids:
        node = ends[edge_id][1]
        onward = [e for e in leaving.get(node, []) if e != edge_id and not is_reverse(edge_id, e)]
        candidate = _best_match(onward, way_of[edge_id], way_of)
        if candidate is None:
            continue
        incoming = [
            e for e in arriving.get(node, []) if e != candidate and not is_reverse(candidate, e)
        ]
        if _best_match(incoming, way_of[candidate], way_of) == edge_id:
            next_edge[edge_id] = candidate
            has_previous.add(candidate)

    corridors: list[list[str]] = []
    placed: set[str] = set()

    def follow(first: str) -> None:
        chain = [first]
        placed.add(first)
        while chain[-1] in next_edge and next_edge[chain[-1]] not in placed:
            chain.append(next_edge[chain[-1]])
            placed.add(chain[-1])
        corridors.append(chain)

    # Chains start at an edge nothing leads into; whatever is left forms closed loops,
    # which start at their smallest edge ID.
    for edge_id in edge_ids:
        if edge_id not in has_previous:
            follow(edge_id)
    for edge_id in edge_ids:
        if edge_id not in placed:
            follow(edge_id)
    return corridors


def merge_edges_into_corridors(
    gdf_edges: gpd.GeoDataFrame,
    df_edge_scores: pd.DataFrame,
    scenario: str | None = None,
) -> pd.DataFrame:
    """Merge gap edges that continue one another into corridors, then rank them.

    Args:
        gdf_edges: Table following ``EdgesSchema``. Only ``edge_id``, ``osm_way_id``
            and ``length_m`` are read: IDs to check the scores against, OSM ways to keep
            a corridor on its street at crossings, lengths to break score ties.
        df_edge_scores: Output of ``detect_gaps_and_score_edges`` (``scenario``,
            ``edge_id``, ``score``; other columns are ignored).
        scenario: Merge only this scenario. ``None`` (default) merges every scenario
            found in ``df_edge_scores``.

    Returns:
        pd.DataFrame validated by ``CorridorsSchema`` with columns ``scenario``,
        ``corridor_id``, ``edge_ids``, ``score``, ``rank``.

    Rules:
        1. Edge ``a`` joins edge ``b`` only when ``b`` starts at the node where ``a``
           ends (``u-v-key`` then ``v-w-key``), so a corridor always travels in one
           direction.
        2. An edge is never joined to the same road in the opposite direction
           (``u-v-key`` and ``v-u-key``), so both directions of a street stay separate
           corridors.
        3. Joins happen only where the way on is clear. Not counting the U-turn: if one
           gap edge leaves the node, the corridor continues with it; if several leave (a
           crossing or fork), it continues with the one on the same OSM way as the edge
           it came from, if exactly one is. The same test runs backwards, so at a join
           only the edge on the same OSM way may lead in. Otherwise the corridor ends
           and each branch starts its own. This keeps a corridor on one street through
           crossings with other gap streets, so a reader can name it.
        4. ``edge_ids`` is a list in travel order, so the corridor can be drawn as one
           line. Every gap edge belongs to exactly one corridor; an edge with no
           neighbour is a corridor of one edge, and a closed loop starts at its smallest
           edge ID.
        5. Corridor ``score`` is the sum of its edges' scores, i.e. the total
           volume x gap length x continuity factor along the corridor.
        6. ``rank`` restarts at 1 in every scenario: highest score first, then the longer
           corridor, then the corridor whose first edge ID sorts first.
        7. ``corridor_id`` is ``corr_<scenario code>_<rank>`` (codes ``bl``, ``la``,
           ``po``), the format of the sample fixture. Output is sorted by scenario, then
           rank.

    Raises:
        ValueError: if required columns are missing, scores are null, negative or
            duplicated per (scenario, edge_id), edge IDs are not ``u-v-key``, or a scored
            edge is not in ``gdf_edges``.
    """
    _check_corridor_inputs(gdf_edges, df_edge_scores)
    scores = pd.DataFrame(
        {
            "scenario": df_edge_scores["scenario"].astype(str).to_numpy(),
            "edge_id": df_edge_scores["edge_id"].astype(str).to_numpy(),
            "score": pd.to_numeric(df_edge_scores["score"]).to_numpy(dtype="float64"),
        }
    )
    if scenario is not None:
        scores = scores[scores["scenario"] == scenario]
    if scores.empty:
        return CorridorsSchema.validate(_empty_corridors())

    edge_ids = gdf_edges["edge_id"].astype(str)
    length = dict(zip(edge_ids, pd.to_numeric(gdf_edges["length_m"]).astype(float)))
    way = dict(zip(edge_ids, gdf_edges["osm_way_id"]))
    rows = []
    for scenario_name, group in scores.groupby("scenario", sort=True):
        edge_score = dict(zip(group["edge_id"], group["score"]))
        corridors = [
            (
                sum(edge_score[e] for e in chain),
                sum(length[e] for e in chain),
                chain,
            )
            for chain in _chain_gap_edges({e: way[e] for e in edge_score})
        ]
        # Rule 6: score, then length, both descending; then the first edge ID.
        corridors.sort(key=lambda c: (-c[0], -c[1], c[2][0]))
        code = SCENARIO_CODES.get(scenario_name, scenario_name)
        for rank, (score, _length, chain) in enumerate(corridors, start=1):
            rows.append(
                {
                    "scenario": scenario_name,
                    "corridor_id": f"corr_{code}_{rank:02d}",
                    "edge_ids": chain,
                    "score": score,
                    "rank": rank,
                }
            )
    return CorridorsSchema.validate(pd.DataFrame(rows, columns=CORRIDOR_COLUMNS))


def _check_corridor_inputs(gdf_edges: pd.DataFrame, df_edge_scores: pd.DataFrame) -> None:
    for name, table, columns in (
        ("edges", gdf_edges, ("edge_id", "osm_way_id", "length_m")),
        ("edge scores", df_edge_scores, CORRIDOR_SCORE_COLUMNS),
    ):
        missing = [c for c in columns if c not in table.columns]
        if missing:
            raise ValueError(f"{name} is missing required column(s): {missing}")
    if df_edge_scores[list(CORRIDOR_SCORE_COLUMNS)].isna().any().any():
        raise ValueError("edge scores must not contain null scenario, edge_id or score")
    score = pd.to_numeric(df_edge_scores["score"], errors="coerce")
    if score.isna().any() or (score < 0).any():
        raise ValueError("edge scores must be numeric and non-negative")
    duplicated = df_edge_scores.duplicated(subset=["scenario", "edge_id"])
    if duplicated.any():
        examples = df_edge_scores.loc[duplicated, ["scenario", "edge_id"]].head(5)
        raise ValueError(
            "edge scores must have one row per (scenario, edge_id); "
            f"duplicates: {examples.to_dict('records')}"
        )
    edge_ids = df_edge_scores["edge_id"].astype(str)
    malformed = edge_ids[~edge_ids.str.fullmatch(_EDGE_ID_PATTERN)]
    if not malformed.empty:
        raise ValueError(
            "edge IDs must be directed 'u-v-key' IDs; "
            f"invalid examples: {malformed.unique()[:5].tolist()}"
        )
    unknown = edge_ids[~edge_ids.isin(gdf_edges["edge_id"].astype(str))]
    if not unknown.empty:
        raise ValueError(
            "edge scores contain edge IDs that are not in the edges table "
            "(scores and edges must use the same frozen graph); "
            f"examples: {unknown.unique()[:5].tolist()}"
        )
