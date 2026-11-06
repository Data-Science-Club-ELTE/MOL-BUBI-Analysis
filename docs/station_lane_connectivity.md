# Lane connectivity: definition draft and pass-rate test (Task #16)

**Code:** `src/bubi/stations/selector.py`, `diagnostics.py` · **Script:** `scripts/lane_connectivity_pass_rate.py`

## 1. Candidate cells
An H3-9 cell is a candidate if (a) population >= 100 and (b) its centre is > 350 m from every existing station
(straight-line, a lower bound on walking distance; replace with the walking graph later).

## 2. Lane connectivity (continuous, metres)
For candidate cell c:

    lane_connectivity(c) = length of dedicated-lane segments within reach R of c's centre
                           that lie in a lane network touching an existing station

- R = 400 m (config to add; tested 200-600).
- "Dedicated lane" = `has_dedicated_lane == True` (tag rules owned by network module, D3).
- Lane in either direction counts; reverse duplicates are collapsed.
- Lane segments are joined into connected components via shared endpoints. A component "touches" a station if any of
  its segments is within 200 m of the station.
- Segments are clipped to the R-circle, so the measure is continuous. No qualifying lane gives exactly 0.

## 3. Scores
`norm(x) = log1p(x) / log1p(max over candidates)`, so 0 stays 0.
- `lane_aware`: score = norm(population) * norm(lane_connectivity)
- `population_only`: score = norm(population)
Greedy pick by score, skip cells closer than 400 m to an already picked cell, stop at N = 10 or when score is 0.
Picked cells get rank 1..N, others rank `<NA>`.

## 4. Pass-rate test
Question: used as a hard filter (connectivity > threshold) how many candidates survive?
`lane_connectivity_pass_rate` reports, for reach in {200,300,400,600} m and min lane in {0,100,250} m,
with and without the station-connected condition: share of cells and share of candidate population.

Proposed decision rule (to be agreed with the team): if the pass rate at R = 400 m, min lane = 100 m is below 50 %
of candidates or of candidate population, keep connectivity as a continuous score (as designed), not a filter.

**Status:** only run on the 8-cell mock fixture (1 of 3 candidates passes). That says nothing about Budapest.
Re-run on real `edges.parquet` and `population.parquet` once the network and population modules deliver them.

## 5. Contract change
`StationCandidatesSchema.rank` now uses nullable `Int64`; the previous `int` could not hold the unselected `<NA>` ranks
that the README promises.
