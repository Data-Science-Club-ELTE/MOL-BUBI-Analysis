# Data Source & Licensing Inventory — v1

Unconfirmed items are marked **UNRESOLVED** rather than assumed.

| Source | Used for | Licence | Attribution required | Access | Status |
|---|---|---|---|---|---|
| OpenStreetMap (via OSMnx) | `edges` | ODbL 1.0 | Yes | Free, no key | Confirmed |
| WorldPop | `population` | CC BY 4.0 | Yes | Free, no key | Confirmed |
| GHSL GHS-POP (EC JRC) | `population` | CC BY 4.0 | Yes | Free, no key | Confirmed |
| BKK FUTÁR API | `stations` | CC BY 4.0 | Yes | Free API key required (approved) | Confirmed by BKK, 2026-11-04 |

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

- **Used by:** Population → `population`
- **Licence:** CC BY 4.0 (free to use and adapt, including commercially, with attribution)
- **Attribution:** Cite WorldPop (www.worldpop.org) and the specific dataset used, with a link to the licence.
- **Access:** Free download, no registration.
- **Restrictions:** WorldPop datasets derived from OpenStreetMap or Microsoft building/road data are under ODbL instead. Check which dataset we use.
- **Open questions:**
  - Which product, year and resolution (e.g. 100 m, constrained or unconstrained)? **UNRESOLVED**
  - Are we using WorldPop, GHSL, or both? **UNRESOLVED**

## 3. GHSL (Global Human Settlement Layer), EC Joint Research Centre

- **Used by:** Population → `population` (alternative or complement to WorldPop)
- **Licence:** CC BY 4.0
- **Attribution:** Cite the dataset, e.g. "GHS-POP R2023A – GHS population grid multitemporal (1975–2030). European Commission, Joint Research Centre (JRC)."
- **Access:** Free download from the JRC GHSL site, no registration.
- **Restrictions:** Default grid is World Mollweide (ESRI:54009); a WGS84 version also exists. The CRS must be converted before H3 aggregation.
- **Open questions:**
  - Which release, epoch (year) and resolution? **UNRESOLVED**

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

## 5. Real GPS route data (`route_type = observed`)

- **Used by:** Station Ingestion → `routes` (README mentions "real GPS route conversion")
- **Source, licence, attribution, access:** **UNRESOLVED.** Source not identified.
- **Privacy:** If it contains individual trips, check whether it is personal data (GDPR) before storing or sharing it. **UNRESOLVED**

---

## Required attribution text (draft, for the dashboard / README)

> Map data © OpenStreetMap contributors (ODbL). Population data: WorldPop (CC BY 4.0) and/or GHSL GHS-POP, European Commission JRC (CC BY 4.0). Data source: BKK Zrt., CC BY 4.0.
