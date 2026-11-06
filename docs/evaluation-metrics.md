# Evaluation Metrics - Draft List

Issue: #4 · Module: `src/bubi/profiling` · Owner: Aizirek Muradylova (BA / Data Analysis)
Status: **DRAFT v0.1** (Week 1) · Last updated: 2026-10-18

These metrics define how the three scenarios (`baseline`, `lane_aware`, `population_only`) and
their recommendations are judged. Metrics marked **[DRAFT]** still need a formal definition or
parameter agreed with the team.

All metrics are computed per scenario and reported as a difference versus `baseline` where it
makes sense. Distances and areas are computed in EPSG:23700.

---

## 1. Coverage — newly served population

| ID | Metric | Definition | Inputs | Status |
|---|---|---|---|---|
| M1 | **Newly served population** | Σ population of H3 cells within the walking threshold (350 m) of a *proposed* station and **not** within it for any existing station. Each cell counted once. | `population`, `stations`, `station_candidates` (rank not null) | Defined |
| M2 | Share of city population served | (served population) / (total Budapest population), baseline vs expansion | `population`, `stations`, `station_candidates` | Defined |
| M3 | Newly served population per new station | M1 / N | M1, `scoring.candidate_n` | Defined |
| M4 | Walking distance used for "served" | Network walking distance vs straight-line buffer | `network` walk graph | **[DRAFT]** — choose network vs Euclidean |

## 2. Corridors — length and efficiency

| ID | Metric | Definition | Inputs | Status |
|---|---|---|---|---|
| M5 | **Recommended corridor length (km)** | Σ `length_m` of edges in the top-K corridors / 1000 | `corridors`, `edges` | **[DRAFT]** — K not fixed (dashboard slider) |
| M6 | **Newly served population per km of corridor** | M1 / M5 (named in `scenarios` README) | M1, M5 | Defined (once K fixed) |
| M7 | Route volume covered per km | Σ volume on top-K corridor edges / M5 — "how much riding the new lanes would carry per km built" | `edge_scores`, M5 | **[DRAFT]** |
| M8 | Gap share of trips | Share of synthetic trip-km travelled on edges without a dedicated lane in that direction | `routes`, `edges`, `edge_scores` | **[DRAFT]** |
| M9 | Corridor continuity | Mean number of edges / mean length per corridor | `corridors`, `edges` | **[DRAFT]** — depends on continuity factor (week 4) |

## 3. Demand

| ID | Metric | Definition | Inputs | Status |
|---|---|---|---|---|
| M10 | Total synthetic trips | Σ `trip_count`; expansion scenarios should exceed baseline (D10) | `trip_matrix` / `routes` | Defined |
| M11 | Trips per newly served person | (trips_scenario − trips_baseline) / M1 | M10, M1 | Defined |
| M12 | Unroutable / dropped trips | Count and share of station pairs the router could not connect | routing log | Defined — data-quality check |

## 4. Result stability (robustness)

| ID | Metric | Definition | Inputs | Status |
|---|---|---|---|---|
| M13 | **Robust corridor share** | Share of top-K corridors that are top-K in all 3 scenarios ("Robust" vs "Station-dependent", `scenarios` README) | `corridors` per scenario | Defined (once K fixed) |
| M14 | **Top-K overlap between scenarios** | Jaccard index of top-K edge/corridor sets for each scenario pair | `edge_scores`, `corridors` | **[DRAFT]** |
| M15 | **Parameter sensitivity** | Rank correlation (Spearman) and top-K overlap when re-running with walk threshold 300 vs 400 m, α ± 50 %, β ± 50 % | full pipeline reruns | **[DRAFT]** — parameter grid to agree |
| M16 | Station siting stability | Share of selected new stations unchanged under the M15 parameter changes | `station_candidates` | **[DRAFT]** |

---

## 5. Open questions

1. Value of K (number of corridors evaluated) — needed for M5, M6, M13, M14.
2. Network-based vs straight-line walking distance for "served" (M4).
3. Which parameters and ranges the sensitivity test (M15) should cover.
4. Whether M7–M9 add enough over M5–M6 to show on the dashboard.

## 6. Where each metric is shown

| Metric | Dashboard area (PR #8 wireframe) |
|---|---|
| M1, M5, M10 | Area 5 — Key metrics |
| M6, M11, M13 | Area 8 — Scenario comparison |
| M7, M9 | Area 7 — Selected recommendation |
| M12, M15, M16 | Report appendix (methodology) |
