# Data Source & Licensing Inventory — v1

Unconfirmed items are marked **UNRESOLVED** rather than assumed.

| Source | Used for | Licence | Attribution required | Access | Status |
|---|---|---|---|---|---|
| OpenStreetMap (via OSMnx) | `edges` | ODbL 1.0 | Yes | Free, no key | Confirmed |
| WorldPop (R2025A v1, constrained, epoch 2026) | `population` | ODbL 1.0 | Yes | Free, no key | **Chosen** — `docs/population_source.md` |
| GHSL GHS-POP (EC JRC, R2023A, epoch 2025) | `population` (alternative) | CC BY 4.0 | Yes | Free, no key | Evaluated, not used — `docs/population_source.md` |
| BKK FUTÁR API | `stations` | CC BY 4.0 | Yes | Free API key required (approved) | Confirmed by BKK, 2026-11-04 |
| Copernicus DEM GLO-30 (2021 release) | node elevations, edge `grade` | Copernicus WorldDEM-30 licence (free, redistribution allowed) | Yes | Free, no key | **Chosen** — `docs/decisions/dem_source.md` |

---

## 1. OpenStreetMap

- **Used by:** Network & Lanes → `edges` (street graph, `has_dedicated_lane`, `osm_way_id`)
- **Licence:** Open Database License (ODbL) 1.0
- **Attribution:** "© OpenStreetMap contributors", with a link to https://www.openstreetmap.org/copyright. It must be visible on the dashboard map.
- **Access:** Free; downloaded through OSMnx (Overpass API). Respect Overpass usage limits.
- **Restrictions:** Share-alike. If we publish a modified database derived from OSM, it must also be under ODbL.
- **Open questions:**
  - Which OSM snapshot date is used? Record it for reproducibility. **UNRESOLVED**
  - Does the bike-lane tagging (`cycleway:*` tags) cover Budapest reliably? **UNRESOLVED**

## 2. WorldPop

Chosen source for `population`; the comparison and decision are in `docs/population_source.md`.

- **Dataset:** Individual countries 2015–2030 (100 m), **R2025A v1**, Hungary, **constrained**, epoch **2026** (`hun_pop_2026_CN_100m_R2025A_v1`). Units are people per cell, not density. Grid is 3 arc-second EPSG:4326, about 5,777 m² per cell at Budapest's latitude.
- **Used by:** Population → `population`
- **Licence:** **ODbL 1.0**, not CC BY 4.0. WorldPop releases most data under CC BY 4.0 but states that datasets derived from OpenStreetMap, Microsoft Building Footprints or Microsoft Roads Detection are ODbL. Its R2025A release statement lists Microsoft Building Footprints among the inputs of the built-settlement model that constrains this product, so the exception applies.
- **Restrictions:** Share-alike. A published Derivative Database — including the `population` table, any committed sample of it, and any database combining it with the OSM-derived `edges` — must be offered under ODbL with attribution. Code is unaffected.
- **Attribution:** see the required string at the end of this file.
- **Access:** Free download, no registration: https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/HUN/v1/100m/constrained/hun_pop_2026_CN_100m_R2025A_v1.tif (16.6 MiB). DOI 10.5258/SOTON/WP00839, produced 2025-09-01.
- **Checksum:** `e13123be2f47f7d56337e41b7a1c80f7f26270c4a06d05b0789134e9a982f5fd` (country file, 17,380,869 bytes). Every population figure in `docs/population_source.md` was computed from this file. R2025A is an **alpha** release that WorldPop says may change, so re-check the checksum on any re-download.
- **Open questions:**
  - WorldPop publishes one licence rule, not a per-country table; the ODbL reading above follows from that rule plus the release statement. Ask WorldPop to confirm in writing if the status becomes material to BKK or to a publication. **UNRESOLVED**
  - R2025A may be superseded by a final release; re-run the comparison if the checksum changes. **UNRESOLVED**

## 3. GHSL (Global Human Settlement Layer), EC Joint Research Centre

Evaluated against WorldPop and not adopted; the numbers are in `docs/population_source.md`. It stays the documented fallback if a deliverable must remain CC BY-only.

- **Dataset evaluated:** GHS-POP **R2023A**, epoch **2025**, 3 arc-second product `GHS_POP_E2025_GLOBE_R2023A_4326_3ss_V1_0` (tile R5_C20). Units are people per cell.
- **Used by:** Population → `population` (alternative only)
- **Licence:** **CC BY 4.0** — no share-alike clause. The GHSL FAQ states that the data are provided under the Creative Commons Attribution 4.0 International (CC BY 4.0) licence, and the built-up layers behind it come from satellite imagery rather than OSM.
- **Attribution:** "GHS-POP R2023A – GHS population grid multitemporal (1975–2030). European Commission, Joint Research Centre (JRC). © European Union, 1995–2025." Add the peer-reviewed GHSL release publication, which the FAQ requires for "appropriate credit".
- **Access:** Free download from the JRC GHSL site, no registration.
- **Restrictions:** The native grid is World Mollweide (ESRI:54009); the 3 arc-second distribution is a resampling of it. Tile R5_C20 stops at 19.99°E, so it covers only about 60% of Hungary — fine for Budapest, insufficient for a national GHSL total.
- **Open questions:**
  - A full-country GHSL comparison needs tile R5_C21. **UNRESOLVED** (not needed for the decision)

## 4. BKK FUTÁR API (Budapest public transport / Bubi station data)

- **Used by:** Station Ingestion → `stations` (station snapshot)
- **Licence / terms of use:** CC BY 4.0, confirmed by BKK Customer Service on 2026-11-04 (reference 0038/0050538/2026). Data and results from the BKK OpenData API may be used, shared, processed and built into applications and research if the source is acknowledged. Terms: https://opendata.bkk.hu/data-sources.
- **Attribution:** "Data source: BKK Zrt., CC BY 4.0", with a link to https://creativecommons.org/licenses/by/4.0/. It must be visible on the dashboard.
- **Access:** Requires registering at https://opendata.bkk.hu and requesting a free API key. The key must **not** be committed to the repo (use an environment variable or a git-ignored config file).
- **Open questions:**
  - Key approval: approved automatically when requested on 2026-10-18; confirmed by BKK on 2026-11-04. **Resolved** (details: `docs/ingestion_notes.md` §1)
  - Can raw API responses or snapshots be stored and shared? CC BY 4.0 permits sharing with attribution. Keeping raw snapshots out of git is now a team choice (size, reproducibility), not a licence requirement. **Resolved**
  - Rate limits? None officially published; BKK says one request every 5 seconds or less often is acceptable, and keys used abusively may be disabled. **Resolved**
  - Does the API still include MOL Bubi station data? Yes: the 2026-10-18 snapshot has 925 station records, and BKK says no other public MOL Bubi source exists. **Resolved**

## 5. Copernicus DEM GLO-30

Chosen elevation source for per-edge grades; the comparison and sampling rules are in `docs/decisions/dem_source.md`.

- **Dataset:** Copernicus DEM, instance COP-DEM-GLO-30-F, 2021 release as published in the AWS bucket `copernicus-dem-30m`; tiles `N47_00_E018_00` and `N47_00_E019_00`. It is a surface model (buildings and vegetation included), 1 arc-second grid, EPSG:4326, heights in metres above the EGM2008 geoid.
- **Used by:** Network & Lanes → node elevations and the `grade` column on `edges` (#31)
- **Licence:** "Licence for the use of the Copernicus WorldDEM-30", shipped with each tile as `INFO/eula_F.pdf`. It is free and worldwide for any natural or legal person, and allows reproduction, distribution, modification and combination with other data. There is no share-alike clause.
- **Attribution:** derived outputs such as grades carry the "produced using Copernicus WorldDEM-30" notice at the end of this file. Redistributing the DEM itself also requires the liability sentence in `docs/decisions/dem_source.md` §3.
- **Access:** free download, no registration, from `https://copernicus-dem-30m.s3.amazonaws.com/`.
- **Checksums:** `7b44e390c85883b602e7f31fb76b5b4daa706d7d250bc195ff5e0dc9c6073801` (E018 tile) and `721c200cbe71cb23e8b6769361bb53ef4674a4bb622b60c813c4c0ec277390d7` (E019 tile), downloaded 2026-11-08.
- **Open questions:**
  - AWS does not say whether its copy is sub-release 2021_1 or 2021_2; the checksums pin the input either way. **UNRESOLVED**

## 6. Real GPS route data (`route_type = observed`)

- **Used by:** Station Ingestion → `routes` (README mentions "real GPS route conversion")
- **Source, licence, attribution, access:** **UNRESOLVED.** Source not identified.
- **Privacy:** If it contains individual trips, check whether it is personal data (GDPR) before storing or sharing it. **UNRESOLVED**

---

## Required attribution text (for the dashboard, README and exported tables)

> Map data © OpenStreetMap contributors (ODbL). Population: WorldPop R2025A v1, constrained, 2026 (ODbL 1.0). Data source: BKK Zrt., CC BY 4.0.

Once elevation or grade data is shown or exported, add the derived-data notice for the DEM:

> produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved.

The full WorldPop citation that must travel with the `population` table:

> Bondarenko M., Priyatikanto R., Tejedor-Garavito N., Zhang W., McKeen T., Cunningham A., Woods T., Hilton J., Cihan D., Nosatiuk B., Brinkhoff T., Tatem A., Sorichetta A. (2025). Constrained estimates of 2015–2030 total number of people per grid square at a resolution of 3 arc (approximately 100m at the equator), R2025A v1. WorldPop, University of Southampton. DOI: 10.5258/SOTON/WP00839. Licence: ODbL 1.0.
