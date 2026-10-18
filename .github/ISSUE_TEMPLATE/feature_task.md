---
name: Feature Task
about: Template for assigned weekly member deliverables
title: "[TASK] <Module>: <Short Description>"
labels: ["task"]
assignees: ""
---

## 1. Owner & Assignment
- **Owner**: (e.g. Geoinformatics MSc / CS 2 / Data Science MSc)
- **Module**: `src/bubi/<module>`
- **Target Week**: Week (1-7)

## 2. Objective
Brief description of the feature or analysis to implement this week.

## 3. Data Contracts
- **Input Tables**: (e.g., `tests/fixtures/sample_edges.parquet`)
- **Output Tables**: (e.g., `data/processed/routes.parquet`)
- **Schema Checked**: (e.g., `RoutesSchema`)

## 4. Acceptance Criteria
- [ ] Logic implemented in `src/bubi/<module>/`
- [ ] Output table strictly validates against Pandera schema
- [ ] Unit tests added in `tests/test_<module>.py` passing locally
- [ ] Code formatted and linted with `make lint`
- [ ] PR created against `develop` branch
