"""Tests for the scenario comparison view and comparability check (Task #73)."""

from pathlib import Path

import pandas as pd
import pytest
import yaml

from bubi.scenarios import build_scenario_comparison_view
from bubi.scenarios.runner import (
    SCENARIOS,
    ScenarioComparabilityError,
    check_scenarios_comparable,
    scenario_run_params_from_config,
)

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "default_config.yaml"


def _edge_scores(rows):
    """rows: (scenario, edge_id, rank); volume and score follow the rank."""
    return pd.DataFrame(
        [
            {
                "scenario": s,
                "edge_id": e,
                "volume": 100.0 - r,
                "score": 1000.0 - r,
                "rank": r,
            }
            for s, e, r in rows
        ]
    )


def _corridors(rows):
    """rows: (scenario, corridor_id, edge_ids, rank)."""
    return pd.DataFrame(
        [
            {"scenario": s, "corridor_id": c, "edge_ids": ids, "score": 1000.0 - r, "rank": r}
            for s, c, ids, r in rows
        ]
    )


def _single_edge_frames():
    """Hand-built frames with one-edge corridors. With top_k = 2:

    e1 is in the top 2 of all three scenarios,
    e2 only in baseline, e4 in exactly two (lane_aware and population_only),
    e3 and e5 (rank 3) are outside the top 2 everywhere.
    """
    ranks = [
        ("baseline", "a-b-0", 1),
        ("baseline", "b-c-0", 2),
        ("baseline", "c-d-0", 3),
        ("lane_aware", "a-b-0", 1),
        ("lane_aware", "e-f-0", 2),
        ("lane_aware", "b-c-0", 3),
        ("population_only", "a-b-0", 1),
        ("population_only", "e-f-0", 2),
        ("population_only", "g-h-0", 3),
    ]
    corridors = [(s, f"corr_{s}_{r}", [e], r) for s, e, r in ranks]
    return _edge_scores(ranks), _corridors(corridors)


def _row(view, level, item_id):
    match = view[(view["level"] == level) & (view["item_id"] == item_id)]
    assert len(match) == 1, f"expected one {level} row for {item_id}"
    return match.iloc[0]


def test_robust_means_top_k_in_all_three_scenarios():
    edge_scores, corridors = _single_edge_frames()
    view = build_scenario_comparison_view(edge_scores, corridors, top_k=2)

    robust_edge = _row(view, "edge", "a-b-0")
    assert robust_edge["label"] == "robust"
    assert robust_edge["n_scenarios_top_k"] == 3
    assert robust_edge["scenarios_top_k"] == "baseline+lane_aware+population_only"
    assert list(view.loc[view["label"] == "robust", "level"]) == ["corridor", "edge"]


def test_item_in_exactly_two_scenarios_is_station_dependent_and_named():
    edge_scores, corridors = _single_edge_frames()
    view = build_scenario_comparison_view(edge_scores, corridors, top_k=2)

    two = _row(view, "edge", "e-f-0")
    assert two["label"] == "station_dependent"
    assert two["n_scenarios_top_k"] == 2
    assert two["scenarios_top_k"] == "lane_aware+population_only"
    assert pd.isna(two["rank_baseline"])
    assert (two["rank_lane_aware"], two["rank_population_only"]) == (2, 2)

    one = _row(view, "edge", "b-c-0")
    assert one["scenarios_top_k"] == "baseline"
    assert one["rank_lane_aware"] == 3  # rank is still reported when it is outside the top-k


def test_items_outside_top_k_everywhere_are_not_listed():
    edge_scores, corridors = _single_edge_frames()
    view = build_scenario_comparison_view(edge_scores, corridors, top_k=2)
    assert set(view.loc[view["level"] == "edge", "item_id"]) == {"a-b-0", "b-c-0", "e-f-0"}


def test_cut_off_changes_labels():
    edge_scores, corridors = _single_edge_frames()
    k1 = build_scenario_comparison_view(edge_scores, corridors, top_k=1)
    k3 = build_scenario_comparison_view(edge_scores, corridors, top_k=3)
    assert _row(k1, "edge", "a-b-0")["label"] == "robust"
    assert _row(k3, "edge", "b-c-0")["n_scenarios_top_k"] == 2  # baseline 2, lane_aware 3
    assert _row(k3, "edge", "b-c-0")["label"] == "station_dependent"
    assert len(k1) < len(k3)


def test_corridors_are_matched_across_scenarios_by_shared_edges():
    edge_scores = _edge_scores(
        [
            ("baseline", "a-b-0", 1),
            ("baseline", "b-c-0", 2),
            ("lane_aware", "b-c-0", 1),
            ("lane_aware", "c-d-0", 2),
            ("population_only", "z-y-0", 1),
        ]
    )
    corridors = _corridors(
        [
            ("baseline", "corr_bl_01", ["a-b-0", "b-c-0"], 1),
            ("lane_aware", "corr_la_01", ["b-c-0", "c-d-0"], 1),
            ("population_only", "corr_po_01", ["z-y-0"], 1),
        ]
    )
    view = build_scenario_comparison_view(edge_scores, corridors, top_k=5)
    shared = view[view["level"] == "corridor"].iloc[0]
    assert shared["scenarios_top_k"] == "baseline+lane_aware"
    assert shared["edge_ids"] == ["a-b-0", "b-c-0", "c-d-0"]
    assert len(view[view["level"] == "corridor"]) == 2  # the shared stretch and z-y-0


def test_edge_level_can_be_robust_while_its_corridor_is_not():
    """Merging hides an edge: x-y-0 is the top edge everywhere, but in population_only a
    three-edge corridor outscores the corridor that holds it."""
    edge_scores = _edge_scores(
        [
            ("baseline", "x-y-0", 1),
            ("lane_aware", "x-y-0", 1),
            ("population_only", "x-y-0", 1),
            ("population_only", "p-q-0", 2),
            ("population_only", "q-r-0", 3),
            ("population_only", "r-s-0", 4),
        ]
    )
    corridors = _corridors(
        [
            ("baseline", "corr_bl_01", ["x-y-0"], 1),
            ("lane_aware", "corr_la_01", ["x-y-0"], 1),
            ("population_only", "corr_po_01", ["p-q-0", "q-r-0", "r-s-0"], 1),
            ("population_only", "corr_po_02", ["x-y-0"], 2),
        ]
    )
    view = build_scenario_comparison_view(edge_scores, corridors, top_k=1)

    edge = _row(view, "edge", "x-y-0")
    assert edge["label"] == "robust"
    assert edge["corridor_label"] == "station_dependent"
    assert edge["scenarios_top_k"] == "baseline+lane_aware+population_only"
    group = view[
        (view["level"] == "corridor")
        & view["edge_ids"].apply(lambda e: isinstance(e, list) and "x-y-0" in e)
    ]
    assert group.iloc[0]["scenarios_top_k"] == "baseline+lane_aware"
    assert group.iloc[0]["rank_population_only"] == 2


def test_json_string_edge_ids_are_accepted():
    edge_scores, corridors = _single_edge_frames()
    as_json = corridors.assign(
        edge_ids=corridors["edge_ids"].apply(lambda e: str(e).replace("'", '"'))
    )
    expected = build_scenario_comparison_view(edge_scores, corridors, top_k=2)
    actual = build_scenario_comparison_view(edge_scores, as_json, top_k=2)
    pd.testing.assert_frame_equal(actual, expected)


def test_result_does_not_depend_on_input_row_order():
    edge_scores, corridors = _single_edge_frames()
    expected = build_scenario_comparison_view(edge_scores, corridors, top_k=2)
    shuffled = build_scenario_comparison_view(
        edge_scores.sample(frac=1, random_state=3),
        corridors.sample(frac=1, random_state=4),
        top_k=2,
    )
    pd.testing.assert_frame_equal(shuffled, expected)


@pytest.mark.parametrize("bad_k", [0, -1, 2.5, True, "10"])
def test_top_k_must_be_a_positive_integer(bad_k):
    edge_scores, corridors = _single_edge_frames()
    with pytest.raises(ValueError, match="top_k"):
        build_scenario_comparison_view(edge_scores, corridors, top_k=bad_k)


def test_missing_scenario_or_duplicates_fail_loudly():
    edge_scores, corridors = _single_edge_frames()
    with pytest.raises(ValueError, match="no rows for scenario"):
        build_scenario_comparison_view(
            edge_scores[edge_scores["scenario"] != "lane_aware"], corridors, top_k=2
        )
    with pytest.raises(ValueError, match="one row per"):
        build_scenario_comparison_view(
            pd.concat([edge_scores, edge_scores.iloc[[0]]]), corridors, top_k=2
        )


def test_repo_fixtures_give_two_of_three_labels(sample_edge_scores, sample_corridors):
    view = build_scenario_comparison_view(sample_edge_scores, sample_corridors)
    assert (view["label"] == "robust").sum() == 0
    top = _row(view, "edge", "n1-n5-0")
    assert top["scenarios_top_k"] == "baseline+population_only"
    assert _row(view, "edge", "n1-n3-0")["scenarios_top_k"] == "baseline+lane_aware"
    assert _row(view, "edge", "n2-n1-0")["scenarios_top_k"] == "baseline"


def _config_params():
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    return {s: scenario_run_params_from_config(config) for s in SCENARIOS}


def test_identical_config_parameters_are_comparable():
    check_scenarios_comparable(_config_params())


@pytest.mark.parametrize(
    ("name", "other"),
    [
        ("random_seed", 7),
        ("candidate_n", 5),
        ("min_spacing_m", 300.0),
        ("walk_coverage_threshold_m", 400.0),
        ("gravity_beta", 0.0015),
    ],
)
def test_any_differing_parameter_fails_loudly(name, other):
    params = _config_params()
    params["lane_aware"][name] = other
    with pytest.raises(ScenarioComparabilityError, match=name):
        check_scenarios_comparable(params)


def test_error_lists_every_problem_and_the_values_used():
    params = _config_params()
    params["population_only"]["random_seed"] = 7
    params["lane_aware"]["gravity_beta"] = 0.0015
    with pytest.raises(ScenarioComparabilityError) as error:
        check_scenarios_comparable(params)
    message = str(error.value)
    assert "random_seed" in message and "population_only=7" in message
    assert "gravity_beta" in message and "lane_aware=0.0015" in message


def test_missing_scenario_unknown_scenario_or_missing_key_fails():
    params = _config_params()
    with pytest.raises(ScenarioComparabilityError, match="population_only"):
        check_scenarios_comparable({k: v for k, v in params.items() if k != "population_only"})
    with pytest.raises(ScenarioComparabilityError, match="unknown scenario"):
        check_scenarios_comparable({**params, "typo": dict(params["baseline"])})
    del params["baseline"]["min_spacing_m"]
    with pytest.raises(ScenarioComparabilityError, match="min_spacing_m is missing"):
        check_scenarios_comparable(params)


def test_tiny_float_noise_is_not_a_difference():
    params = _config_params()
    params["lane_aware"]["gravity_beta"] *= 1 + 1e-14
    check_scenarios_comparable(params)


def test_view_refuses_to_compare_runs_with_different_parameters(
    sample_edge_scores, sample_corridors
):
    params = _config_params()
    params["population_only"]["random_seed"] = 99
    with pytest.raises(ScenarioComparabilityError, match="random_seed"):
        build_scenario_comparison_view(sample_edge_scores, sample_corridors, scenario_params=params)
    view = build_scenario_comparison_view(
        sample_edge_scores, sample_corridors, scenario_params=_config_params()
    )
    assert not view.empty


def test_params_from_config_names_the_missing_key():
    with pytest.raises(ValueError, match="station_scoring.min_spacing_m"):
        scenario_run_params_from_config(
            {
                "project": {"random_seed": 1},
                "station_scoring": {"candidate_n": 10},
                "demand": {"gravity_beta": 0.1},
            }
        )
