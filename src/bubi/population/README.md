# Module: Population Grid (`src/bubi/population`)

**Owner**: Project Lead (Issue #23)  
**Collaborators**: Geoinformatics MSc (CRS & raster handling), BA / Data Science (data dictionary)

---

## 1. Objective

1. Use the chosen source: WorldPop Hungary 2026 constrained, release R2025A v1, 100 m nominal
   (3 arc-second) raster.
2. Clip the country raster to the Budapest study bounding box (`config.spatial.study_area_bbox`).
3. Aggregate pixel populations into H3 resolution 9 hexagon cells by area weighting.
4. Persist the output matching `PopulationSchema`.

The raster is clipped with GDAL rather than reprojected: the pixels stay on their native
EPSG:4326 grid, so population counts are copied without resampling.

Source selection and licence: WorldPop R2025A v1 constrained, epoch 2026, **ODbL 1.0**.
The comparison, the share-alike consequence and the required attribution string are in
`docs/population_source.md`.

---

## 2. Data Contracts

### Output: `population` table

Parquet file saved to `data/processed/population.parquet` and validated against
`PopulationSchema` before it is written.

| Field | Type | Description |
|---|---|---|
| `cell_id` | `str` | H3 resolution-9 index (15-character hex string) |
| `population` | `float` | Estimated resident count inside cell (>= 0.0) |

Cells with zero population inside the study area are kept, so the table is a complete
res-9 tiling of the bbox interior. The 2026-11-09 build has 8,155 cells, 7,410 of them
populated.

---

## 3. Method

- **Pixel geometry.** 3 arc-second pixels are not square on the ground: at Budapest's
  latitude they measure about 62.7 m east–west and 92.8 m north–south (5,814 m²), not
  100 × 100 m. Overlap areas are therefore computed in EPSG:23700, not in degrees.
- **Area weighting.** A pixel wholly inside a cell contributes its full value; a pixel
  that straddles a cell boundary contributes `value × overlap_area / pixel_area`. This
  assumes people are evenly distributed inside a pixel, which is the resolution limit of
  the source. Every pixel's fractions sum to 1.
- **NoData.** Pixels with value −99999 are excluded before summing.
- **Edge cells.** Only cells wholly inside the study bbox are published. Cells that
  cross the bbox edge are dropped rather than published from truncated coverage; the
  excluded population is reported by the build script (0.89% of the clipped raster total
  in the 2026-11-09 run).
- **CRS.** The raster is read and interpolated in EPSG:4326. EPSG:23700 is used only for
  overlap areas, so no coordinate reprojection is involved.

The clipped raster sums 1,918,669.1 people and the published table 1,901,537.4. The
difference is the dropped edge ring, which is mostly low-density suburban fringe.

---

## 4. How to Reproduce

```bash
make population   # clip data/raw/hun_pop_2026_CN_100m_R2025A_v1.tif, then build the table
make test
make lint
```

```bash
gdal_translate -projwin_srs EPSG:4326 \
  -projwin 18.92 47.61 19.33 47.35 \
  -co COMPRESS=LZW -co PREDICTOR=2 \
  data/raw/hun_pop_2026_CN_100m_R2025A_v1.tif \
  data/raw/pop_2026_budapest_bbox.tif
```

`make population` runs `scripts/clip_population.py` and `scripts/build_population.py`.
Both read `config/default_config.yaml`; no paths are hard-coded beyond the defaults.

---

## 5. Tests

`tests/test_population.py` builds synthetic rasters in a temporary directory and checks:

- a pixel wholly inside a cell contributes exactly its value;
- a zero-population cell is still published;
- NoData pixels are excluded;
- overlap fractions sum to 1 per pixel;
- the output validates against `PopulationSchema`, has unique valid H3 indices, no
  negative values, and never exceeds the raster total.

---

## 6. Out of Scope

- Clipping to the Budapest administrative boundary. The bbox is the study definition; a
  city-boundary table would be a separate issue.
- Wiring the `population` stage into `scripts/run_pipeline.py`. The stage is still
  declared as blocked by #23; adding it needs the pipeline test setup to provide a raster,
  so it is a follow-up change rather than part of this module.
