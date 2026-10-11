# Module: Population Grid (`src/bubi/population`)

**Owner**: CS 5  
**Collaborators**: Geoinformatics MSc (CRS & raster handling), BA / Data Science (data dictionary)

---

## 1. Objective

1. Evaluate WorldPop vs. GHSL gridded population rasters for Budapest (100m resolution).
2. Clip the raster to the Budapest study bounding box (`config.spatial.study_area_bbox`).
3. Aggregate raster pixel populations into H3 resolution 9 hexagon cells via zonal statistics.
4. Persist the output matching `PopulationSchema`.

---

## 2. Data Contracts

### Output: `population` table
Parquet file saved to `data/processed/population.parquet` (tested against `tests/fixtures/sample_population.parquet`).

| Field | Type | Description |
|---|---|---|
| `cell_id` | `str` | H3 resolution-9 index (15-character hex string) |
| `population` | `float` | Estimated resident count inside cell (>= 0.0) |

---

## 3. How to Develop Independently

You can develop the raster-to-H3 conversion on any sample GeoTIFF or synthetic raster.

1. Test zonal aggregation logic using `h3` and `geopandas` / `rasterio`.
2. Validate output against `PopulationSchema`:
   ```python
   import pandas as pd
   from bubi.contracts.schemas import PopulationSchema

   df = pd.read_parquet("tests/fixtures/sample_population.parquet")
   PopulationSchema.validate(df)
   ```
3. Run tests:
   ```bash
   pytest tests/test_contracts.py -k population
   ```

---

## 4. Key Open Decisions (Week 1–2)
- **Source selection**: Choose WorldPop (constrained/unconstrained 2020/2026) vs. GHSL.
- Check data licensing and attribution terms for report appendix.
