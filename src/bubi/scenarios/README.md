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
Tabular summary view comparing edge volumes, corridor ranks, and robustness status.

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
