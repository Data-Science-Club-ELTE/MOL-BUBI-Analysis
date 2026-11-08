"""Data profiling, quality checks, and requirements traceability matrix."""

from pathlib import Path
from typing import Any, Optional

import pandas as pd

# Same box as `spatial.study_area_bbox` in config/default_config.yaml:
# (min_lon, min_lat, max_lon, max_lat).
BUDAPEST_BBOX: tuple[float, float, float, float] = (18.92, 47.35, 19.33, 47.61)
H3_RESOLUTION = 9

# Check outcomes used in every check result.
PASS = "pass"
FAIL = "fail"
INFO = "info"
UNRESOLVED = "unresolved"


def profile_dataset(
    df: pd.DataFrame,
    dataset_name: str,
    *,
    bbox: tuple[float, float, float, float] = BUDAPEST_BBOX,
    reference_count: Optional[int] = None,
    reference_total: Optional[float] = None,
    total_tolerance: float = 0.10,
    validate_schema: bool = False,
) -> dict[str, Any]:
    """Generate summary data quality metrics and table-specific quality checks.

    Args:
        df: Table to profile.
        dataset_name: Contract table name ("stations", "population", "edges", ...).
        bbox: Study-area box (min_lon, min_lat, max_lon, max_lat) for station coordinates.
        reference_count: Station count reported by the source (Futár), if known.
        reference_total: Official population total for the study area, if known.
        total_tolerance: Allowed relative difference between our total and reference_total.
        validate_schema: Also validate the table against its Pandera contract schema.

    Returns:
        Summary dict with "dataset", "rows", "columns", "null_counts" and "checks".
        Each check is a dict with "check", "status" (pass/fail/info/unresolved) and "detail".
    """
    checks: list[dict[str, str]] = []
    if validate_schema:
        checks.append(_check_schema(df, dataset_name))

    if dataset_name == "stations":
        checks += _check_stations(df, bbox, reference_count)
    elif dataset_name == "population":
        checks += _check_population(df, reference_total, total_tolerance)
    elif dataset_name == "edges":
        checks += _check_edges(df)

    return {
        "dataset": dataset_name,
        "rows": len(df),
        "columns": list(df.columns),
        "null_counts": df.isnull().sum().to_dict(),
        "checks": checks,
    }


def build_quality_report(
    profiles: list[dict[str, Any]],
    title: str = "Data Quality Report",
    notes: Optional[list[str]] = None,
) -> str:
    """Render profile_dataset() results as a Markdown report."""
    lines = [f"# {title}", ""]
    if notes:
        lines += [f"- {note}" for note in notes] + [""]

    problems: list[str] = []
    for profile in profiles:
        name = profile["dataset"]
        nulls = {col: n for col, n in profile["null_counts"].items() if n}
        lines += [
            f"## {name}",
            "",
            f"- Rows: {profile['rows']}",
            f"- Columns: {', '.join(f'`{c}`' for c in profile['columns'])}",
            f"- Missing values: {nulls if nulls else 'none'}",
            "",
            "| Check | Result | Details |",
            "|---|---|---|",
        ]
        for check in profile["checks"]:
            lines.append(f"| {check['check']} | {check['status'].upper()} | {check['detail']} |")
            if check["status"] == FAIL:
                problems.append(f"`{name}`: {check['check']} ({check['detail']})")
        lines.append("")

    lines += ["## Problems to report to table owners", ""]
    lines += [f"- {p}" for p in problems] if problems else ["- None found."]
    lines.append("")
    return "\n".join(lines)


def generate_traceability_report(outputs_dir: Path) -> str:
    """Generate a Markdown report auditing decision traceability from raw inputs to scored corridors."""
    raise NotImplementedError("Traceability report generator not implemented yet.")


# --------------------------------------------------------------------------- helpers
def _result(check: str, status: str, detail: str) -> dict[str, str]:
    return {"check": check, "status": status, "detail": detail}


def _examples(values: pd.Series, limit: int = 5) -> str:
    items = [str(v) for v in values.head(limit)]
    return f" (e.g. {', '.join(items)})" if items else ""


def _check_schema(df: pd.DataFrame, dataset_name: str) -> dict[str, str]:
    from bubi.contracts.io import SCHEMA_REGISTRY, validate_table

    if dataset_name not in SCHEMA_REGISTRY:
        return _result("Contract schema", INFO, f"no schema registered for '{dataset_name}'")
    try:
        validate_table(df, dataset_name)
    except Exception as exc:  # pandera raises SchemaError / SchemaErrors
        message = str(exc).splitlines()[0][:200]
        return _result("Contract schema", FAIL, message.replace("|", "/"))
    return _result("Contract schema", PASS, "valid")


def _check_stations(
    df: pd.DataFrame,
    bbox: tuple[float, float, float, float],
    reference_count: Optional[int],
) -> list[dict[str, str]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    out = []

    outside = ~df["lat"].between(min_lat, max_lat) | ~df["lon"].between(min_lon, max_lon)
    out.append(
        _result(
            "Coordinates inside Budapest bounding box",
            FAIL if outside.any() else PASS,
            f"{int(outside.sum())} of {len(df)} outside {bbox}"
            + _examples(df.loc[outside, "station_id"]),
        )
    )

    dup_ids = df["station_id"].duplicated(keep=False)
    out.append(
        _result(
            "No duplicate station IDs",
            FAIL if dup_ids.any() else PASS,
            f"{int(dup_ids.sum())} rows share an ID"
            + _examples(df.loc[dup_ids, "station_id"].drop_duplicates()),
        )
    )

    # 5 decimal places is about 1 m in Budapest.
    dup_loc = df[["lat", "lon"]].round(5).duplicated(keep=False)
    out.append(
        _result(
            "No duplicate locations (same lat/lon to ~1 m)",
            FAIL if dup_loc.any() else PASS,
            f"{int(dup_loc.sum())} rows share a location"
            + _examples(df.loc[dup_loc, "station_id"]),
        )
    )

    if reference_count is None:
        out.append(
            _result(
                "Station count vs. Futár",
                UNRESOLVED,
                f"ours = {len(df)}; Futár count not provided",
            )
        )
    else:
        diff = len(df) - reference_count
        out.append(
            _result(
                "Station count vs. Futár",
                PASS if diff == 0 else FAIL,
                f"ours = {len(df)}, Futár = {reference_count}, difference = {diff:+d}",
            )
        )
    return out


def _is_h3_cell(cell: Any, resolution: int = H3_RESOLUTION) -> bool:
    import h3

    try:
        return bool(h3.is_valid_cell(str(cell))) and h3.get_resolution(str(cell)) == resolution
    except Exception:
        return False


def _check_population(
    df: pd.DataFrame,
    reference_total: Optional[float],
    tolerance: float,
) -> list[dict[str, str]]:
    out = []

    negative = df["population"] < 0
    out.append(
        _result(
            "No negative population values",
            FAIL if negative.any() else PASS,
            f"{int(negative.sum())} negative cells" + _examples(df.loc[negative, "cell_id"]),
        )
    )

    invalid = ~df["cell_id"].map(_is_h3_cell)
    out.append(
        _result(
            f"Cell IDs are valid H3 resolution {H3_RESOLUTION}",
            FAIL if invalid.any() else PASS,
            f"{int(invalid.sum())} of {len(df)} invalid" + _examples(df.loc[invalid, "cell_id"]),
        )
    )

    total = float(df["population"].sum())
    if reference_total is None:
        out.append(
            _result(
                "Total population vs. official figure",
                UNRESOLVED,
                f"ours = {total:,.0f}; official figure not provided",
            )
        )
    else:
        rel = (total - reference_total) / reference_total
        out.append(
            _result(
                "Total population vs. official figure",
                PASS if abs(rel) <= tolerance else FAIL,
                f"ours = {total:,.0f}, official = {reference_total:,.0f}, "
                f"difference = {rel:+.1%} (allowed ±{tolerance:.0%})",
            )
        )
    return out


def _check_edges(df: pd.DataFrame) -> list[dict[str, str]]:
    out = []

    dup = df["edge_id"].duplicated(keep=False)
    out.append(
        _result(
            "No duplicate edge_id",
            FAIL if dup.any() else PASS,
            f"{int(dup.sum())} rows share an edge_id"
            + _examples(df.loc[dup, "edge_id"].drop_duplicates()),
        )
    )

    bad_length = ~(df["length_m"] > 0)
    out.append(
        _result(
            "No zero or negative lengths",
            FAIL if bad_length.any() else PASS,
            f"{int(bad_length.sum())} edges with length <= 0 or missing"
            + _examples(df.loc[bad_length, "edge_id"]),
        )
    )

    lane = df["has_dedicated_lane"].astype(bool)
    total_length = float(df["length_m"].sum())
    lane_length = float(df.loc[lane, "length_m"].sum())
    length_share = lane_length / total_length if total_length > 0 else 0.0
    out.append(
        _result(
            "Share of directed edges with a dedicated lane",
            INFO,
            f"{int(lane.sum())} of {len(df)} edges ({lane.mean():.1%}); "
            f"{length_share:.1%} of total length",
        )
    )
    out.append(_lane_direction_check(df))
    return out


def _lane_direction_check(df: pd.DataFrame) -> dict[str, str]:
    """Compare both directions of two-way streets (edge_id format `u-v-key`)."""
    name = "Lane per direction on two-way streets"
    parts = df["edge_id"].astype(str).str.split("-", n=2, expand=True)
    if parts.shape[1] != 3 or parts.isnull().any().any():
        return _result(name, UNRESOLVED, "edge_id is not in `u-v-key` format for every row")

    pairs = pd.DataFrame(
        {
            "a": parts[[0, 1]].min(axis=1),
            "b": parts[[0, 1]].max(axis=1),
            "key": parts[2],
            "lane": df["has_dedicated_lane"].astype(bool).to_numpy(),
        }
    )
    grouped = pairs.groupby(["a", "b", "key"])["lane"].agg(["size", "sum"])
    two_way = grouped[grouped["size"] == 2]
    both = int((two_way["sum"] == 2).sum())
    one = int((two_way["sum"] == 1).sum())
    none = int((two_way["sum"] == 0).sum())
    one_way = int((grouped["size"] == 1).sum())
    return _result(
        name,
        INFO,
        f"{len(two_way)} two-way streets: lane in both directions {both}, "
        f"one direction only {one}, none {none}; {one_way} one-way edges",
    )
