# Module: Network & Lane Model (`src/bubi/network`)

**Owner**: Geoinformatics MSc  
**Collaborators**: CS 2 (Routing Engine), CS 3 (Corridor Scoring), CS 5 (Station Scoring)

---

## 1. Objective

1. Download Budapest street and walking networks using `OSMnx`.
2. Extract **per-direction** dedicated bike-lane status:
   - Handle tags relative to way direction (`cycleway:left/right`, `cycleway=lane|track`, `oneway:bicycle`).
   - Identify parallel cycleways.
   - Define exact OSM tag rules for what counts as a *dedicated bike lane* (per Decision D3).
3. Bind elevation data (DEM) to graph nodes and compute grade/slope per directed edge.
4. Freeze the graph version and persist `edges` table matching `EdgesSchema`.

---

## 2. Data Contracts

### Output: `edges` table
GeoParquet file saved to `data/processed/edges.parquet` (tested against `tests/fixtures/sample_edges.parquet`).

| Field | Type | Description |
|---|---|---|
| `edge_id` | `str` | Unique directed edge identifier formatted as `u-v-key` |
| `osm_way_id` | `int` | Original OpenStreetMap way ID |
| `length_m` | `float` | Edge length in meters (computed in EPSG:23700) |
| `has_dedicated_lane` | `bool` | True if dedicated lane exists in this direction |
| `geometry` | `LineString` | LineString in EPSG:4326 |

---

## 3. How to Develop Independently

You can develop the tag-parsing and graph-building logic without waiting for any other team member.

1. Test your tag extraction on a small local OSM polygon (e.g., District V).
2. Validate output against `EdgesSchema`:
   ```python
   import geopandas as gpd
   from bubi.contracts.schemas import EdgesSchema

   # Validate sample fixture:
   gdf = gpd.read_parquet("tests/fixtures/sample_edges.parquet")
   EdgesSchema.validate(gdf)
   ```
3. Run tests:
   ```bash
   pytest tests/test_contracts.py -k edges
   ```

---

## 4. Key Open Decisions (Weeks 1–2)
- **DEM source**: Choose between Copernicus DEM (30m) or local open elevation data.
- **Edge granularity**: Decide whether to split OSM edges where lane tags change or apply a majority rule.
- **Frozen graph**: Freeze graph snapshot file in `data/raw/` so edge IDs remain deterministic.
