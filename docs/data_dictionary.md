# Data Dictionary — v1

Source of truth: `src/bubi/contracts/schemas.py` (Pandera schemas).
This document explains every contract table, its columns, and which modules produce and consume it.

**Common rules for all tables**
- `coerce=True`: values are converted to the listed type when validated.
- `strict=True`: no extra columns are allowed (exception: `edges`).
- "Not null" means the value must always be present.
- Allowed `scenario` values: `baseline`, `lane_aware`, `population_only` (see each table for exceptions).

Producer/consumer modules are taken from the README module table. Entries marked *(to confirm)* should be checked with the module owner.

---

## 1. `stations` — `StationsSchema`

Current MOL Bubi docking stations.

| Column | Type | Meaning | Constraints |
|---|---|---|---|
| `station_id` | string | Unique ID of a Bubi station | Not null, **unique** |
| `name` | string | Station name | Not null |
| `lat` | float | Latitude (WGS84, degrees) | Not null, between 47.0 and 48.0 |
| `lon` | float | Longitude (WGS84, degrees) | Not null, between 18.0 and 20.0 |

- **Key:** `station_id`
- **Producer:** Station Ingestion (`src/bubi/ingestion/`)
- **Consumers:** Demand Generator, Routing Engine, Dashboard *(to confirm)*

## 2. `population` — `PopulationSchema`

Residential population aggregated to H3 hexagon cells.

| Column | Type | Meaning | Constraints |
|---|---|---|---|
| `cell_id` | string | H3 cell index, resolution 9 | Not null, **unique** |
| `population` | float | Estimated number of residents in the cell | Not null, ≥ 0 |

- **Key:** `cell_id`
- **Producer:** Population (`src/bubi/population/`)
- **Consumers:** Demand Generator, Station Scoring

## 3. `edges` — `EdgesSchema` (GeoDataFrame)

Street network segments from OpenStreetMap, one row per directed edge.

| Column | Type | Meaning | Constraints |
|---|---|---|---|
| `edge_id` | string | Edge ID in `u-v-key` format (start node, end node, key) | Not null, **unique** |
| `osm_way_id` | integer | ID of the source OSM way | Not null (not unique: one way can produce several edges) |
| `length_m` | float | Edge length in metres | Not null, > 0 |
| `has_dedicated_lane` | boolean | True if this direction has a dedicated bike lane | Not null |
| `geometry` | LineString | Shape of the edge | Not null |

- **Key:** `edge_id`
- **Extra columns allowed** (`strict=False`), e.g. `u`, `v`, `grade` (slope).
- **Producer:** Network & Lanes (`src/bubi/network/`)
- **Consumers:** Routing Engine, Corridor Scoring, Station Scoring, Dashboard *(to confirm)*
- **Open question:** CRS of `geometry` is not fixed in the schema (assumed EPSG:4326). *(to confirm)*

## 4. `station_candidates` — `StationCandidatesSchema`

Possible locations for new stations, scored per scenario.

| Column | Type | Meaning | Constraints |
|---|---|---|---|
| `scenario` | string | Scenario name | Not null; only `lane_aware` or `population_only` |
| `cell_id` | string | H3 cell of the candidate | Not null |
| `population` | float | Population of the cell | Not null, ≥ 0 |
| `lane_connectivity` | float | How well the cell connects to bike lanes | ≥ 0, **may be null** |
| `score` | float | Overall candidate score | Not null, ≥ 0 |
| `rank` | nullable integer (`Int64`) | Rank among selected candidates (1 = best) | > 0; **null = not selected** |

- **Key:** (`scenario`, `cell_id`)
- **References:** `cell_id` → `population.cell_id`
- **Producer:** Station Scoring (`src/bubi/stations/`)
- **Consumers:** Scenario Runner, Dashboard
- **Note:** `baseline` is not allowed here, unlike the other scenario tables.

## 5. `routes` — `RoutesSchema`

Trips between stations and the street path they take.

| Column | Type | Meaning | Constraints |
|---|---|---|---|
| `scenario` | string | Scenario name | Not null; `baseline`, `lane_aware`, `population_only` |
| `start_station_id` | string | Origin station | Not null |
| `end_station_id` | string | Destination station | Not null |
| `route_type` | string | Where the route comes from | Not null; `synthetic` (model) or `observed` (real GPS) |
| `edges` | list / JSON string | Ordered list of `edge_id`s on the route | Not null |
| `trip_count` | float | Number of trips on this route | Not null, > 0 |

- **Key:** (`scenario`, `start_station_id`, `end_station_id`, `route_type`) *(to confirm)*
- **References:** `start_station_id`, `end_station_id` → `stations.station_id`; each item in `edges` → `edges.edge_id`
- **Producer:** Routing Engine (`src/bubi/routing/`); observed routes from Station Ingestion *(to confirm)*
- **Consumers:** Corridor Scoring
- **Note:** `edges` format is not fixed (list or JSON string). Pick one format. *(to confirm)*

## 6. `edge_scores` — `EdgeScoresSchema`

Trip volume and priority score per street edge.

| Column | Type | Meaning | Constraints |
|---|---|---|---|
| `scenario` | string | Scenario name | Not null; `baseline`, `lane_aware`, `population_only` |
| `edge_id` | string | Street edge | Not null |
| `volume` | float | Total trips passing over the edge | Not null, ≥ 0 |
| `score` | float | Priority score for a new lane | Not null, ≥ 0 |
| `rank` | integer | Rank (1 = highest priority) | Not null, > 0 |

- **Key:** (`scenario`, `edge_id`)
- **References:** `edge_id` → `edges.edge_id`
- **Producer:** Corridor Scoring (`src/bubi/corridors/`)
- **Consumers:** Dashboard, Scenario Runner *(to confirm)*

## 7. `corridors` — `CorridorsSchema`

Groups of connected edges recommended as bike-lane corridors.

| Column | Type | Meaning | Constraints |
|---|---|---|---|
| `scenario` | string | Scenario name | Not null; `baseline`, `lane_aware`, `population_only` |
| `corridor_id` | string | Corridor ID | Not null |
| `edge_ids` | list / JSON string | `edge_id`s forming the corridor | Not null |
| `score` | float | Corridor priority score | Not null, ≥ 0 |
| `rank` | integer | Rank (1 = highest priority) | Not null, > 0 |

- **Key:** (`scenario`, `corridor_id`)
- **References:** each item in `edge_ids` → `edges.edge_id`
- **Producer:** Corridor Scoring (`src/bubi/corridors/`)
- **Consumers:** Scenario Runner, Dashboard

---

## Interface table: `trip_matrix` — `TripMatrixSchema`

Hand-off from the Demand Generator to the Routing Engine (not one of the 7 core tables).

| Column | Type | Meaning | Constraints |
|---|---|---|---|
| `scenario` | string | Scenario name | Not null (no allowed-values check) |
| `start_station_id` | string | Origin station | Not null |
| `end_station_id` | string | Destination station | Not null |
| `trip_count` | float | Estimated trips | Not null, > 0 |

- **Producer:** Demand Generator (`src/bubi/demand/`)
- **Consumer:** Routing Engine

---

## Cross-table links (for the traceability check)

| From | To |
|---|---|
| `routes.start_station_id`, `routes.end_station_id` | `stations.station_id` |
| `routes.edges[*]` | `edges.edge_id` |
| `edge_scores.edge_id` | `edges.edge_id` |
| `corridors.edge_ids[*]` | `edges.edge_id` |
| `station_candidates.cell_id` | `population.cell_id` |
| `trip_matrix.start/end_station_id` | `stations.station_id` |

## Open questions found in the schemas

1. `trip_matrix.scenario` has no allowed-values check, unlike the other tables.
2. `routes.edges` and `corridors.edge_ids` accept either a list or a JSON string; one format should be chosen.
3. `edges.geometry` CRS is not specified.
4. `rank` is nullable `Int64` in `station_candidates` but non-null `int` in `edge_scores` and `corridors`. Intentional? (The code comment says yes for candidates.)
5. No uniqueness check on composite keys (e.g. `scenario` + `edge_id` in `edge_scores`).
