# Population source: WorldPop 2026 (constrained)

Decision note for [#9](https://github.com/Data-Science-Club-ELTE/MOL-BUBI-Analysis/issues/9). Decided 2026-11-08; unblocks the `population` module ([#23](https://github.com/Data-Science-Club-ELTE/MOL-BUBI-Analysis/issues/23)).

## 1. Decision

Use **WorldPop 2026 constrained** (`hun_pop_2026_CN_100m_R2025A_v1`) as the single source for the `population` table. GHSL GHS-POP R2023A was evaluated with the identical method and is retained as the documented alternative, not as a second input.

Three findings drive the choice. WorldPop reproduces the national census total to within 0.02% and the Budapest total to within 2%, while GHSL puts 12% more people into Budapest than the census supports. At the H3 resolution-9 catchment scale the pipeline uses, the two products rank places identically, so the choice costs nothing spatially. And WorldPop's 2026 epoch is the year `config/default_config.yaml` already names.

| Property | Value |
| --- | --- |
| Product | WorldPop, Individual countries 2015–2030 (100 m), **R2025A v1**, Hungary, **constrained** |
| Epoch used | 2026 |
| Grid | 3 arc-second geographic (EPSG:4326); a cell is ~92 m north–south by ~63 m east–west at 47.5°N, about 5,777 m² |
| Units | people per cell, not density |
| Download | `https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/HUN/v1/100m/constrained/hun_pop_2026_CN_100m_R2025A_v1.tif` (16.6 MiB) |
| DOI | `10.5258/SOTON/WP00839` |
| Produced | 2025-09-01 |
| Checksum of the country file | `e13123be2f47f7d56337e41b7a1c80f7f26270c4a06d05b0789134e9a982f5fd` (`hun_pop_2026_CN_100m_R2025A_v1.tif`, 17,380,869 bytes) |
| Checksum of the study clip | `7f8bd47f06da7eb18bc944a968091ab831a530c4c8726f78244b9755eb6a0c8f` (`data/raw/worldpop2026_density.tif`) |
| Licence | ODbL 1.0 — see §8 |

The study clip is a plain window of the country file: the same window in the country file sums to 1,918,669, exactly what the clip sums to, so no pixel was resampled or dropped.

> **The checksum matters.** R2025A is an alpha release and WorldPop states the product "may change over the coming year". Every figure in this note was computed from the file with the checksum above; a later download with a different checksum is a different input and must be re-evaluated.

## 2. What was compared

| | WorldPop 2026 | GHSL 2025 |
| --- | --- | --- |
| File | `data/raw/worldpop2026_density.tif` | `data/raw/ghs_2025.tif` |
| Upstream | `hun_pop_2026_CN_100m_R2025A_v1.tif` | `GHS_POP_E2025_GLOBE_R2023A_4326_3ss_V1_0_R5_C20.tif` |
| Epoch | 2026 | 2025 |
| Grid | 3 arcsec, EPSG:4326 | 3 arcsec, EPSG:4326 |
| Release | WorldPop R2025A v1, constrained | GHSL R2023A |
| Nodata | `-99999`, 24.8% of pixels (outside settlements) | none set; 29% of pixels are genuine zeros |

Both files are the same nominal resolution, which is why they look comparable on screen. Two details make a naive pixel comparison wrong. The grids differ in phase by exactly 1.5 arc seconds (half a pixel), so subtracting one array from the other misaligns the city: correlation is 0.882 index-aligned but 0.911 once the grids are realigned. And WorldPop's `-99999` is not missing data — 95.2% of those pixels sit on GHSL cells that are exactly zero, i.e. outside mapped settlement — so it means "no population", not "unknown".

## 3. Method

1. Clip both rasters to the study bounding box `[18.92, 47.35, 19.33, 47.61]` (EPSG:4326, min lon, min lat, max lon, max lat).
2. Take the Budapest administrative polygon from OpenStreetMap (Nominatim, 2026-11-08) and generate the H3 resolution-9 cells covering it: 4,936 cells, about 515 km².
3. Sum each raster into a cell by **area-weighted overlap**: every raster cell that intersects the H3 polygon contributes `value × (intersected area / raster cell area)`. Areas are computed in an equal-area CRS (ESRI:54009), never in degrees.
4. Compare totals against the KSH 2022 census for Budapest, 1,685,342 (reference date 2022-10-01).
5. Compare the two H3 tables against each other, and at catchment scale (each cell plus its 1–3 rings), which is the scale station scoring and the gravity model actually see.

This is the aggregation core, runnable as printed against the two files above:

```python
import json
import h3, numpy as np, rasterio as rio, shapely
from pyproj import Transformer
from shapely.geometry import Polygon


def aggregate(raster_path, geometry, resolution=9):
    """Population per H3 cell, weighted by the share of each raster cell inside it."""
    src = rio.open(raster_path)
    a = src.read(1).astype("float64")
    if src.nodata is not None:  # constrained product: nodata = no settlement
        a = np.where(a == src.nodata, 0.0, a)
    tr = src.transform
    to_src = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
    out = {}
    for cell in h3.geo_to_cells(geometry, resolution):
        ring = [(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]
        gx, gy = to_src.transform(*np.array(ring).T)
        poly = Polygon(np.column_stack([gx, gy]))
        minx, miny, maxx, maxy = poly.bounds
        i0 = max(0, int((minx - tr.c) // tr.a))
        i1 = min(src.width - 1, int((maxx - tr.c) // tr.a))
        j0 = max(0, int((maxy - tr.f) // tr.e))
        j1 = min(src.height - 1, int((miny - tr.f) // tr.e))
        xs = tr.c + np.arange(i0, i1 + 1) * tr.a
        ys = tr.f + np.arange(j0, j1 + 1) * tr.e
        boxes = shapely.box(xs[None, :], ys[:, None], xs[None, :] + tr.a, ys[:, None] + tr.e)
        w = np.clip(shapely.area(shapely.intersection(poly, boxes)) / abs(tr.a * tr.e), 0, 1)
        out[cell] = float((a[j0 : j1 + 1, i0 : i1 + 1] * w).sum())
    return out


# Nominatim: /search?q=Budapest&format=json&polygon_geojson=1&limit=1
boundary = json.load(open("budapest.geojson"))[0]["geojson"]  # Nominatim output
print(sum(aggregate("data/raw/worldpop2026_density.tif", boundary).values()))
```

Run on the two files, this prints totals of **1,658,627** (WorldPop) and **1,854,395** (GHSL). The census comparison below multiplies boundary cells by the share of their area inside the polygon, which removes the spill-over of edge cells and gives 1,655,192 and 1,851,018 — a 0.2% difference, and the reason the headline figures are lower than the raw sums.

### Sample output

`scripts/population_h3_sample.py` turns the snippet above into a command: it aggregates a bounding box, validates the result against `PopulationSchema`, and writes Parquet.

```bash
python scripts/population_h3_sample.py \
    --raster data/raw/worldpop2026_density.tif \
    --output data/processed/population_h3_sample.parquet
```

On the default sample area (Deák Ferenc tér ± 0.01°, 32 cells at resolution 9):

```text
32 cells at H3 resolution 9
total population 40,179
range 34.9 - 2,325.7
validated against PopulationSchema, written to data/processed/population_h3_sample.parquet
```

| cell_id | population |
| --- | --- |
| 891e037aa0bffff | 2,137.9 |
| 891e037aa0fffff | 2,325.7 |
| 891e037aa1bffff | 2,132.3 |
| 891e037aa17ffff | 1,975.6 |
| 891e037aa13ffff | 1,690.7 |

The Parquet file is a build output and stays out of the commit, as pipeline tables in `data/processed` generally do; rerun the command after downloading the raster described in §1. The script prints a short message instead of a traceback when the raster is absent.

The same command on `data/raw/ghs_2025.tif` gives **54,359** people over the same 32 cells — 35% more than WorldPop. That is §6's density effect concentrated in the innermost districts, where GHSL's built-up volume allocation assigns the most people.

## 4. National calibration

Both products are calibrated to the same national population, so the choice is about *where* people are placed, not *how many* exist.

| Test | Result |
| --- | --- |
| WorldPop 2026, Hungary, summed inside the OSM national boundary | 9,601,674 |
| KSH 2022 census, Hungary | 9,603,634 |
| Difference | **−0.02%** |
| GHSL 2025 vs WorldPop 2026, summed over identical ground | ratio **1.003** |
| Same ground, Budapest removed | ratio **0.965** |
| Same ground, Budapest only | ratio **1.118** |

The GHSL national total could not be summed directly: tile `R5_C20` stops at 19.99°E, which covers about 60% of Hungary. The identical-ground test therefore uses the intersection of the national boundary with that tile.

## 5. City totals against the census

| Source | Budapest total | vs census 1,685,342 |
| --- | --- | --- |
| WorldPop 2026 | 1,655,192 | **−1.8%** |
| GHSL 2025 | 1,851,018 | **+9.8%** |

WorldPop's −1.8% is the expected sign and size for a 2026 estimate of a city that has been shrinking since 2011. GHSL's +9.8% is not: the same boundary applied to the native-grid GHSL clip gives 1,854,172, so the excess belongs to the product, not to the clip or the epoch.

## 6. Agreement at H3 resolution 9

4,724 cells lie fully inside the city. Over those cells WorldPop and GHSL have Pearson **0.926**, Spearman **0.969**, a median relative difference of **23%**, and 84% of cells agree within 50% (12% differ by more than 2×).

The population floor of 100 people per cell, which decides which cells can host a station, gives an almost identical set: **2,958** cells pass on both, 106 only on GHSL, 76 only on WorldPop.

GHSL is the spikier field. Its cells are zero in 5.1% of cases against 4.3% for WorldPop, its top 1% of cells hold 7.3% of the city total against 6.2%, and the ratio between the products falls as density rises:

| people per cell | 1–100 | 100–500 | 500–1k | 1k–2k | 2k–4k | >4k |
| --- | --- | --- | --- | --- | --- | --- |
| WorldPop / GHSL | 0.98 | 0.92 | 0.93 | 0.87 | 0.72 | 0.46 |

GHSL assigns progressively more people to the densest cells, which is what built-up *volume* disaggregation does in central Budapest. For a gravity model that multiplies two station catchments, this is the one difference that could matter after calibration.

## 7. Agreement at catchment scale

Summing each cell with its neighbours, which is what station scoring (350 m walk threshold) and the gravity model consume:

| neighbourhood | Spearman | top-10 catchments shared | top-100 catchments shared |
| --- | --- | --- | --- |
| 1 ring | 0.981 | 10/10 | 100/100 |
| 2 rings | 0.988 | 10/10 | 100/100 |
| 3 rings | 0.991 | 10/10 | 100/100 |

The two sources produce the same ranking of every catchment the pipeline would consider. Station siting will therefore be driven by the lane-connectivity term, not by which population raster was chosen.

## 8. Licence and attribution

**WorldPop R2025A constrained is ODbL, not plain CC BY 4.0.** The dataset page states CC BY 4.0 and then carves out a condition: datasets derived from OpenStreetMap, Microsoft Building Footprints or Microsoft Roads Detection are published under the ODbL. The [R2025A release statement](https://data.worldpop.org/repo/prj/Global_2015_2030/R2025A/doc/Global2_Release_Statement_R2025A_v1.pdf) shows which camp this product falls in — the built-settlement model that constrains the random forest combines GHSL BUILT-S/BUILT-V with rasterised **Google Open Buildings V3 and Microsoft Building Footprints**, added "to enable refined mapping of buildings where these were missed in GHSL".

Consequences for this repository, which publishes derived tables and fixtures:

- The `population` table is a Derivative Database and must be offered under ODbL, with attribution.
- The same obligation already covers `edges`, which is derived from OpenStreetMap, so the combined database was ODbL-bound before this decision (see `docs/source_inventory.md` §1).
- Code in this repository is unaffected; ODbL covers the database, not the software.

Required attribution string for the dashboard, README and any exported table:

> Population: WorldPop R2025A v1, constrained, 2026 (ODbL 1.0). Bondarenko M., Priyatikanto R., Tejedor-Garavito N., Zhang W., McKeen T., Cunningham A., Woods T., Hilton J., Cihan D., Nosatiuk B., Brinkhoff T., Tatem A., Sorichetta A. (2025). Constrained estimates of 2015–2030 total number of people per grid square at a resolution of 3 arc (approximately 100m at the equator), R2025A v1. WorldPop, University of Southampton. DOI: 10.5258/SOTON/WP00839.

GHSL is the alternative precisely because it is **CC BY 4.0** with no share-alike clause (its built-up layers come from satellite imagery, and its totals from GPWv4.11 and UN World Population Prospects 2022). If a deliverable must stay CC BY-only, take GHSL and document the +9.8% Budapest offset from §5.

## 9. Consequences for the `population` module

- `aggregate_population_to_h3` should take a raster path, an H3 resolution and a study area, and stay source-agnostic; the choice of product belongs in config, not in the function. `scripts/population_h3_sample.py` is the reference implementation to lift it from.
- Treat WorldPop nodata as zero population. It marks settlement extent, not missing measurements.
- Use area weights, never centroids and never nearest-neighbour resampling. A half-pixel phase shift between the two products is enough to change a pixel comparison by three correlation points.
- The `population_source` label `worldpop_2026_100m` in `config/default_config.yaml` now resolves to this exact product; record the checksum beside it when the module starts reading the config.
- The dashboard attribution (`DATA_ATTRIBUTION` in `src/bubi/dashboard/app.py`) carries the licence strings.

## 10. Unresolved

- **Per-country licence confirmation.** WorldPop publishes one rule, not a per-country table, so "ODbL" is inferred from that rule plus the release statement. If the exact status becomes material to BKK or to a publication, ask WorldPop to confirm in writing.
- **Alpha release drift.** R2025A may be superseded. Re-check the checksum on every re-download and re-run this note's numbers if it changes.
- **GHSL national total.** Confirm with tile `R5_C21` if a full-country GHSL comparison is ever needed.
- **Test coverage.** `scripts/population_h3_sample.py` is a CLI demonstration; a tested `aggregate_population_to_h3` with unit tests belongs to the `population` module in #23. The comparison script behind the figures in §4–§7 is not in the repository either.
