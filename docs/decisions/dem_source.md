# DEM source: Copernicus DEM GLO-30

Decision note for [#50](https://github.com/Data-Science-Club-ELTE/MOL-BUBI-Analysis/issues/50), decided 2026-11-08. It unblocks per-edge grades in [#31](https://github.com/Data-Science-Club-ELTE/MOL-BUBI-Analysis/issues/31).

A digital elevation model (DEM) is a raster of ground heights. The pipeline samples one at every node of the frozen street graph, and from those heights computes the signed `grade` of each directed edge. Routing then penalises uphill edges with `cost = length_m × (1 + α · max(0, grade))` (`src/bubi/routing/router.py`, α = 3.0). Until a DEM is attached, every edge is treated as flat.

## 1. Decision

Use **Copernicus DEM GLO-30**, 2021 release, in the copy published on AWS Open Data. The config key is `copernicus_glo30_2021` (`network.elevation_dem_source` in `config/default_config.yaml`). It replaces the placeholder label `copernicus_dem_30m`, which did not name a release or a tile set.

| Property | Value |
| --- | --- |
| Product | Copernicus DEM, instance COP-DEM-GLO-30-F ("Global 30m Full, Free & Open"), format DGED |
| Release | 2021, as distributed in the AWS bucket `copernicus-dem-30m` (the bucket states it is built from the 2021 release) |
| Tiles | `Copernicus_DSM_COG_10_N47_00_E018_00_DEM.tif` and `Copernicus_DSM_COG_10_N47_00_E019_00_DEM.tif` |
| Why two tiles | The study bounding box `[18.92, 47.35, 19.33, 47.61]` crosses 19°E, so its western edge lies in the E018 tile |
| Grid | 1 arc-second, 3600 × 3600 pixels per 1° tile, 32-bit float, about 31 m north–south × 21 m east–west at 47.5°N |
| Model type | Digital surface model (DSM): heights include buildings, bridges and vegetation (§5.4) |
| Horizontal CRS | WGS 84, EPSG:4326 |
| Vertical datum | EGM2008 geoid (EPSG:3855), metres |
| Acquisition | TanDEM-X radar mission, 2011–2015 |
| Stated accuracy | Absolute vertical error below 4 m; relative vertical error below 2 m on slopes up to 20% (both 90% linear error) |
| Size | 43,702,400 and 44,234,408 bytes, so 88 MB for both tiles |
| Access | Free, no account, no key |

The two tiles were downloaded on 2026-11-08. The bucket reports a `Last-Modified` date of 2022-05-09 for both. All figures in §5 come from the files with these checksums:

| File | SHA-256 |
| --- | --- |
| `Copernicus_DSM_COG_10_N47_00_E018_00_DEM.tif` | `7b44e390c85883b602e7f31fb76b5b4daa706d7d250bc195ff5e0dc9c6073801` |
| `Copernicus_DSM_COG_10_N47_00_E019_00_DEM.tif` | `721c200cbe71cb23e8b6769361bb53ef4674a4bb622b60c813c4c0ec277390d7` |

## 2. Candidates compared

| Criterion | Copernicus GLO-30 | SRTM / NASADEM | EU-DEM v1.1 via the Budapest Open Data Atlas | Lechner DDM-5 |
| --- | --- | --- | --- | --- |
| Budapest coverage | Full, 2 tiles | Full, 2 tiles (`N47E018`, `N47E019`) | Full, clipped to roughly the study box | Full, ordered per km² |
| Resolution | 1″, ~31 × 21 m | 1″, ~30 m | 3″ cells, ~93 × 63 m, heights rounded to whole metres | 5 m (10 m also sold) |
| Model type | Surface (DSM) | Surface-like radar heights | Surface (DSM) | Terrain (DTM), from 1:10,000 contour maps |
| Data date | 2011–2015 | February 2000 | EU-DEM source data, not dated by the atlas | Maps from 1979–2000, updated photogrammetrically to 2022 |
| Vertical datum | EGM2008 | EGM96 per the SRTM documentation; not confirmed in this review | Not stated by the atlas | Not stated on the product page |
| Licence | Free, worldwide, redistribution and modification allowed (§3) | Openly shared without restriction (NASA EOSDIS data use policy) | Educational, popular-science and scientific use only; commercial use not allowed | Paid; licence terms not stated on the product page |
| Attribution | Fixed notice (§3) | Citation with DOI | "Bátorfy Attila 2023 … Budapest Open Data Atlasza. Átló/Átlátszó" | Not stated |
| Download size | 88 MB | About 26 MB per uncompressed `.hgt` tile | 15 MB GeoJSON | Priced per km² |
| Ease of sampling onto nodes | GeoTIFF, read directly | HGT raster, read directly | 55,272 polygons; must be rasterised before sampling | GeoTIFF or XYZ, read directly |
| Access | Anonymous HTTPS | NASA Earthdata (the files sit in an LP DAAC "protected" bucket; a login is very likely required, not confirmed) | Google Drive link | Order by e-mail from Lechner Tudásközpont |

The products evaluated are:

- **SRTM:** NASA SRTMGL1 v003 (DOI 10.5067/MEASURES/SRTM/SRTMGL1.003) and its reprocessed successor NASADEM_HGT v001 (DOI 10.5067/MEASURES/NASADEM/NASADEM_HGT.001).
- **Budapest Open Data Atlas:** the "3D domborzati modell" layer of the atlas at <https://atlo.team/boda/>. It was built by Átló, not by BKK.
- **Lechner DDM-5:** the national terrain model of Lechner Tudásközpont, Hungary's state mapping agency (formerly FÖMI).

## 3. Licence and attribution

The licence travels with every tile as `INFO/eula_F.pdf` ("Licence for the use of the Copernicus WorldDEM-30"). It was read in full for this note. Its main terms:

- **Who may use it:** the "General Public", which the licence defines as any natural or legal person. Use is free of charge, worldwide and without time limit (Articles 3 and 5).
- **What users may do:** reproduce the data, distribute it, communicate it to the public, and adapt, modify and combine it with other data (Article 4). Commercial use is not excluded. Delivering to BKK Zrt., a company, is therefore covered.
- **Notice for unmodified data:** distributing or showing the DEM itself requires this notice (Article 6a):

  > © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.

- **Notice for derived data:** node elevations and edge grades are adapted data, so any output that carries them uses the derived-data notice (Article 6b):

  > produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.

- **Liability sentence:** anyone who redistributes the data to the public, modified or not, must add (Article 6c):

  > The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30.

- **No endorsement:** the project must not suggest that Copernicus, ESA or Airbus endorse it (Article 6d).
- **Not share-alike:** unlike ODbL, which already covers the OSM-derived `edges` table, this licence imposes no share-alike condition.

The dashboard does not show elevation or grade yet, so `DATA_ATTRIBUTION` in `src/bubi/dashboard/app.py` is unchanged. Add the derived-data notice there when a layer that depends on grades is shown.

## 4. Why the alternatives were not chosen

**Budapest Open Data Atlas.** The atlas is a good overview map, but its terrain layer cannot feed the pipeline:

- **Too coarse.** It is EU-DEM v1.1 resampled from 25 m to 3″ cells, about 93 m × 63 m, with heights rounded to whole metres. Any edge shorter than a cell can have both end nodes in the same cell, so it reads as flat.
- **Wrong format.** It is a GeoJSON of polygons, not a raster, so it would have to be rasterised again before sampling.
- **Upstream withdrawn.** Copernicus no longer maintains or distributes EU-DEM and points users to the Copernicus DEM at 30 m. The atlas does not document which EU-DEM file or processing steps it used, so #50's requirement to name the exact product and version cannot be met.
- **Licence.** The atlas licence excludes commercial and profit-oriented use, while the project is delivered to BKK Zrt.

The atlas remains useful as an independent visual reference for the spot checks in #31.

**SRTM and NASADEM.** These are the same 30 m grid size as GLO-30, but the data is 11–15 years older. Budapest has built a great deal since February 2000, and in a surface model new buildings change the heights directly. SRTM has no water-body mask and its accuracy is documented less completely. Downloads very likely need a NASA Earthdata account, so a teammate could not reproduce the download anonymously.

**Lechner DDM-5.** This is the technically best open-sky option: a 5 m bare-earth terrain model with ±0.7 m average height reliability. It is paid, though: 1,920 Ft/km² net for 5 m, about 1.3 million Ft including VAT for Budapest's ~525 km² administrative area. A licensed file also could not be shared freely inside the team or with BKK. It is the documented upgrade path if a bare-earth model becomes necessary (§6).

**Mapzen/Tilezen Terrarium tiles on AWS** were also looked at. They mix SRTM, ASTER and GMTED2010 sources with no release version, so they fail the same versioning requirement.

## 5. Sampling constraints for #31

### 5.1 Raster CRS and reprojection

- **CRS:** the tiles are in geographic WGS 84 (EPSG:4326). The graph is measured in EOV (EPSG:23700, the Hungarian national grid).
- **Transform the nodes, not the raster.** Convert node coordinates to EPSG:4326 and sample the tiles in their own CRS. Reprojecting the raster to EOV would resample every height before it is read. This matches #31's criterion that sampling happens after reprojecting to the DEM CRS.
- **Pixel registration:** the GeoTIFF header marks pixels as points (`RasterType = PixelIsPoint`), with the first pixel centred on the tile's whole-degree corner (for example 19.0°E, 48.0°N). Let the raster library read the georeferencing instead of computing pixel positions by hand, or nodes shift by half a pixel, about 15 m.
- **Interpolation:** bilinear interpolation between the four surrounding pixels is the suggested default. Nearest-pixel sampling gives identical heights to nodes that share a pixel, which turns short edges flat. The final choice belongs to #31.
- **Mosaic:** read both tiles as one mosaic (for example a VRT), so that nodes west of 19°E are not dropped.
- **Vertical datum:** heights are relative to EGM2008. Grades use height differences, so the datum offset cancels within this DEM. Do not mix heights from another DEM, such as a Hungarian Baltic-datum product, into the same grade computation.

### 5.2 Nodata, water and the study-area edge

- **No nodata:** the tiles declare no nodata value, and GLO-30 covers all land, so every node inside the two tiles gets a height.
- **Flattened water:** water surfaces are flattened. On two east–west transects across the Danube (47.505°N and 47.470°N) the river reads exactly 98.0 m and 97.0 m on every pixel.
- **Water mask:** each tile ships a water body mask, `AUXFILES/..._WBM.tif`, which marks water pixels. Nodes that fall on water are almost always bridge nodes. Do not use their sampled heights. Handle them with the bridge interpolation below.
- **Outside the tiles:** the study box lies entirely inside the two tiles. If a node still falls outside them, list it as missing with the reason "outside DEM tiles". Do not impute a height.

### 5.3 Bridges and tunnels

The DEM shows the river surface under a bridge, and depending on the pixel it may also show the bridge deck. Either way, a sampled height on a bridge is not the road height. #31 already requires flagging bridge and tunnel ways and interpolating elevation between their end nodes. With this DEM that rule is required, not optional.

### 5.4 Surface-model effects

GLO-30 measures the top reflective surface, not the ground. Observed in the E019 tile:

| Location | Sampled height | Note |
| --- | --- | --- |
| Gellért Hill, Citadella | 233.7 m | The summit is commonly given as 235 m |
| János-hegy, Erzsébet lookout | 529.2 m | Budapest's highest point, commonly given as 527–528 m. The tower and trees may add height |
| Deák Ferenc tér | 107.1 m | Open square |
| Hősök tere | 106.1 m | Open square |
| Built-up Lipótváros at 47.505°N | 114–124 m | Open squares in flat Pest read 106–107 m. The extra height is consistent with roofs |

Coordinates were sampled at the nearest pixel from the checksummed tiles in §1. The reference heights are approximate public figures, not survey data.

Two consequences follow for #31:

- **Narrow streets.** In streets lined with buildings, a 30 m pixel can read roof height instead of street height, which can create false short climbs. The five spot checks in #31 should include at least one dense inner-city street, alongside the hill and river-bank points.
- **Per-pixel error.** The auxiliary height error mask (`HEM`) gives an error estimate per pixel and can help explain outliers.

## 6. Handoff for #31

1. **Download the two tiles** into `data/raw/dem/copernicus_glo30/`. `data/raw/` is git-ignored.

   ```bash
   mkdir -p data/raw/dem/copernicus_glo30
   cd data/raw/dem/copernicus_glo30
   for t in N47_00_E018_00 N47_00_E019_00; do
     f="Copernicus_DSM_COG_10_${t}_DEM.tif"
     curl -fsSO "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_${t}_DEM/${f}"
   done
   sha256sum Copernicus_DSM_COG_10_*_DEM.tif
   ```

2. **Compare the checksums** with the table in §1. A different checksum means a different input: record it and re-run the spot checks.
3. **Optionally download the water mask** for each tile, from the same folder with the `AUXFILES/` prefix:

   ```
   https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N47_00_E019_00_DEM/AUXFILES/Copernicus_DSM_COG_10_N47_00_E019_00_WBM.tif
   ```

4. **Add a raster reader.** No project dependency reads rasters yet: `rasterio` is not in `pyproject.toml`. Adding a reader is part of #31.
5. **Read the config key.** Read `network.elevation_dem_source`. If the module needs the file list or checksums from config, add them next to the key, following the pattern of the `stations` snapshot entry.

## 7. Unresolved

- **Exact sub-release.** The AWS copy is the "2021 release", which Copernicus splits into 2021_1 and 2021_2 (2021_2 is described as a format update for the EEA-10 product, not GLO-30). AWS does not say which sub-release it holds. The checksums in §1 pin the input either way. **UNRESOLVED**
- **Later releases.** The Copernicus Data Space lists releases up to 2024_1. The release notes for 2023_1 and 2024_1 concern Armenia, Azerbaijan, Moldova and Spain. Whether 2022_1 changed any Hungarian tile was not checked, and the newer releases need a Data Space account to download. **UNRESOLVED**
- **SRTM datum and access.** The EGM96 datum and the Earthdata login requirement were not confirmed from primary pages. Neither affects the decision. **UNRESOLVED**
- **DDM-5 datum and licence.** The Lechner product page states neither. This only matters if the project later switches to DDM-5. **UNRESOLVED**
