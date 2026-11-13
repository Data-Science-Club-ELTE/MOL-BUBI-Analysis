"""Scenario orchestration and comparative analysis."""

import json
import math
import numbers
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from bubi.contracts.schemas import CorridorsSchema, EdgeScoresSchema

SCENARIOS = ("baseline", "lane_aware", "population_only")

# Top-k cut-off proposed in docs/evaluation_metrics.md section 5.
DEFAULT_TOP_K = 10

# Parameters that must be identical in all three scenario runs, with where each lives in
# config/default_config.yaml. Only the station set may differ between scenarios.
COMPARABILITY_PARAMS = {
    "random_seed": ("project", "random_seed"),
    "candidate_n": ("station_scoring", "candidate_n"),
    "min_spacing_m": ("station_scoring", "min_spacing_m"),
    "walk_coverage_threshold_m": ("station_scoring", "walk_coverage_threshold_m"),
    "gravity_beta": ("demand", "gravity_beta"),
}

LABEL_ROBUST = "robust"
LABEL_STATION_DEPENDENT = "station_dependent"

VIEW_COLUMNS = [
    "level",
    "item_id",
    "label",
    "n_scenarios_top_k",
    "scenarios_top_k",
    *[f"rank_{s}" for s in SCENARIOS],
    *[f"volume_{s}" for s in SCENARIOS],
    "corridor_key",
    "corridor_label",
    "edge_ids",
]


class ScenarioComparabilityError(ValueError):
    """Raised when scenario runs used different parameters and cannot be compared."""


def run_all_scenarios(config: dict[str, Any]) -> dict[str, Any]:
    """Execute pipeline for baseline, lane_aware, and population_only scenarios.

    Ensures identical parameters (seed, N, walk distance, decay beta).
    """
    raise NotImplementedError("Scenario runner not implemented yet.")


def scenario_run_params_from_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Read the parameters that all three scenarios must share from a loaded config dict."""
    params: dict[str, Any] = {}
    for name, path in COMPARABILITY_PARAMS.items():
        node: Any = config
        for key in path:
            if not isinstance(node, Mapping) or key not in node:
                raise ValueError(f"config is missing {'.'.join(path)} (needed for {name})")
            node = node[key]
        params[name] = node
    return params


def _same_value(first: Any, second: Any) -> bool:
    if isinstance(first, bool) or isinstance(second, bool):
        return first == second
    if isinstance(first, numbers.Real) and isinstance(second, numbers.Real):
        return math.isclose(first, second, rel_tol=1e-12, abs_tol=0.0)
    return first == second


def check_scenarios_comparable(run_params: Mapping[str, Mapping[str, Any]]) -> None:
    """Fail loudly if the three scenario runs did not use identical parameters.

    Args:
        run_params: One mapping per scenario name (``baseline``, ``lane_aware``,
            ``population_only``), each holding every key of ``COMPARABILITY_PARAMS``:
            random seed, number of proposed stations N, minimum spacing, walk coverage
            distance and gravity beta. Extra keys are ignored.

    Raises:
        ScenarioComparabilityError: if a scenario or parameter is missing, a scenario name
            is unknown, or any parameter differs between scenarios. The message lists every
            problem with the value each scenario used, so the cause is visible at once.
    """
    problems = []
    unknown = sorted(set(run_params) - set(SCENARIOS))
    if unknown:
        problems.append(f"unknown scenario name(s) {unknown}")
    absent = [s for s in SCENARIOS if s not in run_params]
    if absent:
        problems.append(f"no run parameters for scenario(s) {absent}")
    present = [s for s in SCENARIOS if s in run_params]

    for name in COMPARABILITY_PARAMS:
        lacking = [s for s in present if name not in run_params[s]]
        if lacking:
            problems.append(f"{name} is missing for {lacking}")
            continue
        if len(present) < 2:
            continue
        reference = run_params[present[0]][name]
        if any(not _same_value(reference, run_params[s][name]) for s in present[1:]):
            used = ", ".join(f"{s}={run_params[s][name]!r}" for s in present)
            problems.append(f"{name} differs ({used})")

    if problems:
        raise ScenarioComparabilityError("scenarios are not comparable: " + "; ".join(problems))


def _as_edge_list(value: object) -> list[str]:
    """``corridors.edge_ids`` cell (list, array or JSON array string) as a list of IDs."""
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, (list, tuple, np.ndarray)):
        raise ValueError(f"corridors.edge_ids must be a list or JSON list, got {value!r}")
    return [str(edge_id) for edge_id in value]


def _check_view_inputs(
    edge_scores: pd.DataFrame, corridors: pd.DataFrame, top_k: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if isinstance(top_k, bool) or not isinstance(top_k, (int, np.integer)) or top_k < 1:
        raise ValueError(f"top_k must be a positive integer, got {top_k!r}")
    edge_scores = EdgeScoresSchema.validate(edge_scores)
    corridors = CorridorsSchema.validate(corridors)
    for name, table in (("edge_scores", edge_scores), ("corridors", corridors)):
        absent = [s for s in SCENARIOS if s not in set(table["scenario"])]
        if absent:
            raise ValueError(f"{name} has no rows for scenario(s) {absent}; all three are required")
    if edge_scores.duplicated(["scenario", "edge_id"]).any():
        raise ValueError("edge_scores must have one row per (scenario, edge_id)")
    if corridors.duplicated(["scenario", "corridor_id"]).any():
        raise ValueError("corridors must have one row per (scenario, corridor_id)")
    return edge_scores, corridors


def _label(n_scenarios: int) -> str:
    return LABEL_ROBUST if n_scenarios == len(SCENARIOS) else LABEL_STATION_DEPENDENT


def _scenarios_text(in_top: Sequence[bool]) -> str:
    return "+".join(s for s, flag in zip(SCENARIOS, in_top, strict=True) if flag)


def _group_corridors(corridors: pd.DataFrame, top_k: int) -> list[dict[str, Any]]:
    """Match the top-k corridors of different scenarios that share a directed edge.

    Corridor IDs restart in every scenario, so the same road stretch has a different ID in
    each. Two top-k corridors are treated as the same stretch when they share at least one
    directed edge; chains of such matches form one group. Each group reports, per scenario,
    the best rank of any corridor of that scenario touching the group's edges.
    """
    parent: dict[int, int] = {}

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    edge_lists = {i: _as_edge_list(v) for i, v in corridors["edge_ids"].items()}
    top = corridors[corridors["rank"] <= top_k]
    owner: dict[str, int] = {}
    for i in top.index:
        parent[i] = i
    for i in top.index:
        for edge_id in edge_lists[i]:
            if edge_id in owner:
                parent[find(i)] = find(owner[edge_id])
            else:
                owner[edge_id] = i

    members: dict[int, list[int]] = {}
    for i in top.index:
        members.setdefault(find(i), []).append(i)

    best_rank: dict[tuple[str, str], int] = {}
    for i, row in corridors.iterrows():
        for edge_id in edge_lists[i]:
            key = (row["scenario"], edge_id)
            best_rank[key] = min(best_rank.get(key, int(row["rank"])), int(row["rank"]))

    groups = []
    for member_ids in members.values():
        edge_ids = sorted({e for i in member_ids for e in edge_lists[i]})
        ranks = {}
        for scenario in SCENARIOS:
            found = [best_rank[(scenario, e)] for e in edge_ids if (scenario, e) in best_rank]
            ranks[scenario] = min(found) if found else None
        in_top = [ranks[s] is not None and ranks[s] <= top_k for s in SCENARIOS]
        groups.append({"edge_ids": edge_ids, "ranks": ranks, "in_top": in_top})

    groups.sort(
        key=lambda g: (
            -sum(g["in_top"]),
            min(r for r in g["ranks"].values() if r is not None),
            g["edge_ids"][0],
        )
    )
    for position, group in enumerate(groups, start=1):
        group["key"] = f"cmp_{position:02d}"
        group["label"] = _label(sum(group["in_top"]))
    return groups


def _corridor_rows(groups: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for g in groups:
        row = {
            "level": "corridor",
            "item_id": g["key"],
            "label": g["label"],
            "n_scenarios_top_k": sum(g["in_top"]),
            "scenarios_top_k": _scenarios_text(g["in_top"]),
            "corridor_key": g["key"],
            "corridor_label": g["label"],
            "edge_ids": g["edge_ids"],
        }
        for scenario in SCENARIOS:
            row[f"rank_{scenario}"] = g["ranks"][scenario]
            row[f"volume_{scenario}"] = np.nan
        rows.append(row)
    return pd.DataFrame(rows, columns=VIEW_COLUMNS)


def _edge_rows(edge_scores: pd.DataFrame, groups: list[dict[str, Any]], top_k: int) -> pd.DataFrame:
    ranks = edge_scores.pivot(index="edge_id", columns="scenario", values="rank")
    volumes = edge_scores.pivot(index="edge_id", columns="scenario", values="volume")
    ranks = ranks.reindex(columns=list(SCENARIOS))
    volumes = volumes.reindex(columns=list(SCENARIOS))
    in_top = ranks.le(top_k)
    in_top = in_top[in_top.any(axis=1)]

    group_of_edge = {e: g for g in groups for e in g["edge_ids"]}
    rows = []
    for edge_id, flags in in_top.iterrows():
        group = group_of_edge.get(edge_id)
        row = {
            "level": "edge",
            "item_id": edge_id,
            "label": _label(int(flags.sum())),
            "n_scenarios_top_k": int(flags.sum()),
            "scenarios_top_k": _scenarios_text(list(flags)),
            "corridor_key": group["key"] if group else None,
            "corridor_label": group["label"] if group else None,
            "edge_ids": None,
        }
        for scenario in SCENARIOS:
            rank = ranks.at[edge_id, scenario]
            row[f"rank_{scenario}"] = None if pd.isna(rank) else int(rank)
            row[f"volume_{scenario}"] = volumes.at[edge_id, scenario]
        rows.append(row)
    return pd.DataFrame(rows, columns=VIEW_COLUMNS)


def build_scenario_comparison_view(
    df_edge_scores: pd.DataFrame,
    df_corridors: pd.DataFrame,
    top_k: int = DEFAULT_TOP_K,
    scenario_params: Mapping[str, Mapping[str, Any]] | None = None,
) -> pd.DataFrame:
    """Compare corridors and edges across scenarios and flag robust vs. station-dependent.

    Classification (docs/evaluation_metrics.md, Metric 4):
        - ``robust``: in the top ``top_k`` of all three scenarios.
        - ``station_dependent``: in the top ``top_k`` of at least one scenario but not all
          three. ``scenarios_top_k`` says which ones, so an item that is in exactly two
          scenarios is visible (for example ``lane_aware+population_only`` means it appears
          only once proposed stations exist; ``baseline`` alone means it disappears after
          expansion).

    Top-k cut-off: the default ``top_k = 10`` is the proposal in docs/evaluation_metrics.md
    section 5. It matches the N = 10 proposed stations, fits one dashboard table without
    scrolling, and is a realistic size for one planning cycle. The document asks to test
    k = 5 and k = 20 as well, and marks 10 as awaiting project leader confirmation.

    Both levels are returned in one table because corridor merging can hide an edge: an edge
    can be in the top-k of all three scenarios while its corridor is not, or the other way
    round. ``level`` is ``corridor`` or ``edge``. Corridor IDs restart in every scenario, so
    corridors are matched across scenarios when their top-k corridors share a directed edge;
    each group gets a key ``cmp_01``, ``cmp_02``, ... (best first). Edge rows carry the key
    and label of the corridor group they belong to (``None`` if that corridor is not top-k).

    Args:
        df_edge_scores: Table following ``EdgeScoresSchema`` for all three scenarios.
        df_corridors: Table following ``CorridorsSchema`` for all three scenarios.
        top_k: Highest rank that counts as top-k, a positive integer.
        scenario_params: Optional run parameters per scenario. When given,
            ``check_scenarios_comparable`` runs first and raises if they differ.

    Returns:
        pd.DataFrame with columns ``level``, ``item_id``, ``label``, ``n_scenarios_top_k``,
        ``scenarios_top_k``, ``rank_<scenario>`` (nullable integer, best rank in that
        scenario, missing if the item does not occur there), ``volume_<scenario>`` (edge
        rows only), ``corridor_key``, ``corridor_label`` and ``edge_ids`` (corridor rows
        only, sorted). Only items in the top-k of at least one scenario appear. Rows are
        sorted by level, then by number of scenarios (most first), then best rank.

    Raises:
        ScenarioComparabilityError: if ``scenario_params`` differ between scenarios.
        ValueError: if ``top_k`` is not a positive integer, a table fails its schema, a
            scenario has no rows, or keys are duplicated within a scenario.
    """
    if scenario_params is not None:
        check_scenarios_comparable(scenario_params)
    edge_scores, corridors = _check_view_inputs(df_edge_scores, df_corridors, top_k)

    groups = _group_corridors(corridors.reset_index(drop=True), top_k)
    view = pd.concat(
        [_corridor_rows(groups), _edge_rows(edge_scores, groups, top_k)], ignore_index=True
    )
    for scenario in SCENARIOS:
        view[f"rank_{scenario}"] = view[f"rank_{scenario}"].astype("Int64")
        view[f"volume_{scenario}"] = view[f"volume_{scenario}"].astype("float64")
    view["n_scenarios_top_k"] = view["n_scenarios_top_k"].astype("int64")

    best = view[[f"rank_{s}" for s in SCENARIOS]].min(axis=1)
    order = pd.DataFrame(
        {
            "level": view["level"].map({"corridor": 0, "edge": 1}),
            "n": -view["n_scenarios_top_k"],
            "best": best.fillna(10**9).astype("int64"),
            "item": view["item_id"],
        }
    )
    ordered = order.sort_values(["level", "n", "best", "item"], kind="mergesort").index
    return view.loc[ordered].reset_index(drop=True)
