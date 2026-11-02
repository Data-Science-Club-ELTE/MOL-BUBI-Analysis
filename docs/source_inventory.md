# Data Source & Licensing Inventory — v1

Unconfirmed items are marked **UNRESOLVED** rather than assumed.

| Source | Used for | Licence | Attribution required | Access | Status |
|---|---|---|---|---|---|
| OpenStreetMap (via OSMnx) | `edges` | ODbL 1.0 | Yes | Free, no key | Confirmed |
| WorldPop | `population` | CC BY 4.0 | Yes | Free, no key | Confirmed |
| GHSL GHS-POP (EC JRC) | `population` | CC BY 4.0 | Yes | Free, no key | Confirmed |
| BKK FUTÁR API | `stations` | **UNRESOLVED** | **UNRESOLVED** | Free API key required | Partly unresolved |

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
- **Licence / terms of use:** **UNRESOLVED.** Not confirmed. Check the terms on https://opendata.bkk.hu.
- **Attribution:** **UNRESOLVED**
- **Access:** Requires registering at https://opendata.bkk.hu and requesting a free API key. The key must **not** be committed to the repo (use an environment variable or a git-ignored config file).
- **Open questions:**
  - Key approval: the key was requested on 2026-10-18 and works, but the portal says it may be used only after BKK approval, which has not arrived. BKK was asked by email on 2026-10-26. **UNRESOLVED** (details: `docs/ingestion_notes.md` §1)
  - Can raw API responses or snapshots be stored and shared in the repo? **UNRESOLVED**
  - Rate limits? **UNRESOLVED**
  - Does the API still include MOL Bubi station data? **UNRESOLVED**

## 5. Real GPS route data (`route_type = observed`)

- **Used by:** Station Ingestion → `routes` (README mentions "real GPS route conversion")
- **Source, licence, attribution, access:** **UNRESOLVED.** Source not identified.
- **Privacy:** If it contains individual trips, check whether it is personal data (GDPR) before storing or sharing it. **UNRESOLVED**

---

## Required attribution text (draft, for the dashboard / README)

> Map data © OpenStreetMap contributors (ODbL). Population data: WorldPop (CC BY 4.0) and/or GHSL GHS-POP, European Commission JRC (CC BY 4.0). Station data: BKK FUTÁR (terms UNRESOLVED).
