# Module: Data Profiling & Traceability (`src/bubi/profiling`)

**Owner**: BA / Data Science & BA / Data Analysis  
**Collaborators**: Project Leader, Geoinformatics MSc, Data Science MSc

---

## 1. Objective

1. **Data Dictionary**: Document descriptions, units, coordinate systems, and nullability constraints for all 7 contract tables.
2. **Quality Profiling**: Check station coordinate sanity (Budapest bounding box), H3 resolution conformity, duplicate edge geometries, and null values.
3. **Traceability Auditing**: Validate Section 9 requirements: ensure every corridor and station recommendation can be traced to its input demand and scoring formulas.
4. **Deliverables**: Technical report appendix, data profiling notebook/script, executive summary slides.

---

## 2. How to Develop Independently

1. Profile sample fixtures in `tests/fixtures/`:
   ```python
   from bubi.contracts.io import load_contract_table
   from bubi.profiling.profiler import profile_dataset

   df_stations = load_contract_table("stations", "tests/fixtures/sample_stations.parquet")
   report = profile_dataset(df_stations, "stations")
   print(report)
   ```
2. Build validation assertions into `tests/test_profiling.py`.
