# Module: Network & Lane Model (`src/bubi/network`)

**Owner**: Geoinformatics MSc  
**Collaborators**: CS 2 (Routing Engine), CS 3 (Corridor Scoring), CS 5 (Station Scoring)

---

## 1. Objective

1. Load Budapest street and walking networks from the clipped Geofabrik extract, with an OSMnx
   download as fallback.
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

### Frozen network artefacts

The build reads a Geofabrik PBF from the project Drive and needs `osmium-tool` on `PATH`. Nothing
under `data/raw/` is committed.

```bash
.venv/bin/python scripts/build_network.py --pbf data/raw/hungary-261121.osm.pbf
```

It clips the PBF to `spatial.study_area_bbox`, keeps ways with a `highway` tag, and writes:

| Artefact | Path | Committed |
|---|---|---|
| Bike graph | `data/raw/budapest_osm_20261121-bike.graphml.gz` | no, in the project Drive |
| Walk graph | `data/raw/budapest_osm_20261121-walk.graphml.gz` | no, in the project Drive |
| Edges table | `data/processed/edges.parquet` | yes |
| Provenance | `data/processed/network_metadata.json` | yes |

The current freeze is `budapest_osm_20261121`, extract date 2026-11-21. The metadata records the
PBF SHA-256, both graph SHA-256 values, node and edge counts, and the dedicated-lane share.

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
- **DEM source**: Decided: Copernicus DEM GLO-30, 2021 release (`docs/dem_source.md`).
- **Dedicated lane rule**: Decided, see [`docs/lane_tags.md`](../../../docs/lane_tags.md). It covers
  counted tags, direction defaults, the footway filter, and the `oneway=-1` side swap.
- **Edge granularity**: Decided: OSMnx splits edges where tags change, and `simplify=False` keeps one
  OSM way per edge, so no mixed-tag majority rule is needed.
- **Frozen graph**: The clipped OSM extract and the frozen graph live in the project Drive, not in
  git (`data/raw/` is ignored). Edge IDs stay deterministic because the extract is fixed.
