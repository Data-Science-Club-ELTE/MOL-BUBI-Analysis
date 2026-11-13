# Module: Scenarios & Comparison (`src/bubi/scenarios`)

**Owner**: CS 5 & Data Science MSc  
**Collaborators**: CS 4 (Dashboard), BA / Data Analysis (Metrics narrative)

---

## 1. Objective

1. **Run 3 Scenarios**:
   - `baseline`: Existing stations only.
   - `lane_aware`: Existing + $N$ proposed stations (sited using $\text{pop} \times \text{lane\_conn}$).
   - `population_only`: Existing + $N$ proposed stations (sited using $\text{pop}$ only).
2. **Parameter Parity**: Ensure identical random seeds, decay parameter $\beta$, candidate $N$, and walk distance across all runs.
3. **Robustness Classification**:
   - Classify top corridors:
     - **Robust**: Appears in top recommendations across all 3 scenarios.
     - **Station-dependent**: High priority only when specific expansion stations are introduced.
4. **Efficiency Metrics**:
   - Total newly served population.
   - Population newly served per km of recommended bike-lane corridor.

---

## 2. Data Contracts

### Inputs
Pre-computed scenario outputs for `edge_scores`, `corridors`, and `station_candidates`.

### Output: Comparison View

`build_scenario_comparison_view(df_edge_scores, df_corridors, top_k=10, scenario_params=None)` returns one table. Each row is a corridor group (`level == "corridor"`) or a single directed edge (`level == "edge"`) that is in the top `top_k` of at least one scenario.

| Column | Meaning |
|---|---|
| `level`, `item_id` | `corridor` with a key such as `cmp_01`, or `edge` with the `u-v-key` edge ID |
| `label` | `robust` if in the top `top_k` of all three scenarios, otherwise `station_dependent` |
| `n_scenarios_top_k`, `scenarios_top_k` | How many scenarios, and which ones (for example `lane_aware+population_only`) |
| `rank_<scenario>` | Best rank in that scenario; missing if the item does not occur there |
| `volume_<scenario>` | Route volume, edge rows only |
| `corridor_key`, `corridor_label` | The corridor group an edge belongs to and that group's label |
| `edge_ids` | Edges of the corridor group, corridor rows only |

Corridor IDs restart in every scenario (`corr_bl_01`, `corr_la_01`), so top-k corridors of different scenarios are matched when they share a directed edge. The edge rows are there because merging can hide an edge: an edge can be in the top `top_k` of all three scenarios while its corridor is not.

The default `top_k = 10` is the proposal in `docs/evaluation_metrics.md` section 5, awaiting project leader confirmation.

### Comparability check

`check_scenarios_comparable(run_params)` raises `ScenarioComparabilityError` if the random seed, N (`candidate_n`), minimum spacing, walk coverage distance or gravity beta differ between the three scenario runs, or if a scenario or parameter is missing. Build each scenario's parameters from the loaded config with `scenario_run_params_from_config(config)`. Passing them as `scenario_params` makes the comparison view run the check first.

---

## 3. How to Develop Independently

1. Load sample edge scores and corridors:
   ```python
   import pandas as pd

   df_edge_scores = pd.read_parquet("tests/fixtures/sample_edge_scores.parquet")
   df_corridors = pd.read_parquet("tests/fixtures/sample_corridors.parquet")
   ```
2. Build comparative logic joining tables on `edge_id` across `scenario`.
3. Verify that baseline vs. expansion deltas match expectations.

```python
from bubi.scenarios import build_scenario_comparison_view

view = build_scenario_comparison_view(df_edge_scores, df_corridors, top_k=10)
print(view[["level", "item_id", "label", "scenarios_top_k"]])
```

`run_all_scenarios` is still a stub; the comparison view and the comparability check work on any three-scenario `edge_scores` and `corridors` tables.
