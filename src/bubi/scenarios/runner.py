"""Scenario orchestration and comparative analysis."""

from typing import Any

import pandas as pd


def run_all_scenarios(config: dict[str, Any]) -> dict[str, Any]:
    """Execute pipeline for baseline, lane_aware, and population_only scenarios.

    Ensures identical parameters (seed, N, walk distance, decay beta).
    """
    raise NotImplementedError("Scenario runner not implemented yet.")


def build_scenario_comparison_view(
    df_edge_scores: pd.DataFrame,
    df_corridors: pd.DataFrame,
    top_k: int = 10,
) -> pd.DataFrame:
    """Compare corridors across scenarios and flag robust vs. station-dependent corridors.

    Classification:
        - 'robust': Ranked in top_k in all 3 scenarios.
        - 'station_dependent': Ranked in top_k only under proposed station sets.
    """
    raise NotImplementedError("Scenario comparison view not implemented yet.")
