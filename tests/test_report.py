"""Tests for the technical-report builders (issue #74)."""

import pandas as pd

from bubi.profiling.report import (
    FIXTURE,
    REAL,
    RERUN_CHECKLIST,
    Source,
    appendix_sections,
    build_quality_report_final,
    build_technical_report,
    markdown_table,
    provenance,
)

APPENDIX = """# Methodology appendix

## 1. What is real

Intro.

### 1.1 In our own words

Trips are invented.

---

## 3. Straight-line distance

Lower bound.

## 4. Limitations

| # | Limitation |
| --- | --- |
| 1 | Synthetic |

## 5. Claims

1. No forecast.

## 6. Parameters
"""


def test_provenance_marks_fixture_scale():
    real = Source("stations", "data/processed/stations.parquet", REAL)
    fixture = Source("edges", "tests/fixtures/sample_edges.parquet", FIXTURE)
    assert provenance([real]).endswith("Real-scale.*")
    line = provenance([real, fixture], "Note.")
    assert "`tests/fixtures/sample_edges.parquet` (fixture)" in line
    assert "Fixture-scale.*" in line and line.endswith("*Note.*")


def test_markdown_table_formats_and_dashes():
    df = pd.DataFrame({"a": [1234.5, None], "b": ["x|y", "z"]})
    assert markdown_table(df, {"a": "{:,.0f}"}) == [
        "| a | b |",
        "|---|---|",
        "| 1,234 | x/y |",
        "| — | z |",
    ]


def test_appendix_sections_are_verbatim():
    sections = appendix_sections(APPENDIX)
    assert sections["1.1"] == "Trips are invented."
    assert sections["3"] == "Lower bound."
    assert sections["4"] == "| # | Limitation |\n| --- | --- |\n| 1 | Synthetic |"
    assert sections["5"] == "1. No forecast."
    assert "6" not in appendix_sections(APPENDIX, ["1.1"])


def test_technical_report_structure_and_limitations():
    src = Source("stations", "data/processed/stations.parquet", REAL)
    report = build_technical_report(
        {"Inputs": (["| m |", "|---|", "| 1 |"], [src], None)},
        [src],
        APPENDIX,
        "cmd",
        "abc1234",
    )
    headings = [line for line in report.splitlines() if line.startswith("## ")]
    assert headings == [
        "## 1. Question",
        "## 2. Data",
        "## 3. Method",
        "## 4. Results",
        "## 5. Limitations",
        "## 6. Reproduction",
    ]
    assert "Trips are invented." in report and "| 1 | Synthetic |" in report
    assert "*Source: `data/processed/stations.parquet` (real). Real-scale.*" in report
    assert all(f"- [ ] {item}" in report for item in RERUN_CHECKLIST)


def test_technical_report_flags_missing_appendix():
    report = build_technical_report({}, [], None, "cmd", "abc")
    assert "**Missing:** `docs/methodology_appendix.md` was not found" in report


def test_quality_report_lists_every_table_and_failures():
    good = {"rows": 2, "columns": ["a"], "null_counts": {"a": 0}, "checks": []}
    bad = {
        "rows": 3,
        "columns": ["b"],
        "null_counts": {"b": 1},
        "checks": [{"check": "No duplicates", "status": "fail", "detail": "2 rows"}],
    }
    text = build_quality_report_final(
        [
            (good, Source("stations", "data/processed/stations.parquet", REAL)),
            (bad, Source("edges", "tests/fixtures/sample_edges.parquet", FIXTURE)),
        ],
        "cmd",
        "abc",
    )
    assert "| `stations` | `data/processed/stations.parquet` | real | 2 | 0 |" in text
    assert "| `edges` | `tests/fixtures/sample_edges.parquet` | fixture | 3 | 1 |" in text
    assert "- `edges` (fixture): No duplicates" in text
    assert "Missing values: {'b': 1}" in text
