"""Data contracts and schema validators for MOL Bubi.

Conforms to Technical Design Document (Section 5) and task specifications.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


class SchemaError(ValueError):
    """Raised when data fails schema validation against contracts."""

    pass


def _normalize_records(data: Any) -> List[Dict[str, Any]]:
    """Convert supported table representations into a list of record dicts.

    Supports:
    - List of dicts
    - Dict of lists / sequences
    - Objects with `to_dict(orient='records')` (e.g. pandas DataFrame)
    - Custom Table objects
    """
    if hasattr(data, "to_dict"):
        # pandas DataFrame or similar
        try:
            return list(data.to_dict(orient="records"))
        except TypeError:
            records = data.to_dict()
            if isinstance(records, dict):
                return _normalize_dict_of_lists(records)

    if hasattr(data, "to_records"):
        return list(data.to_records())

    if isinstance(data, list):
        if not data:
            return []
        if isinstance(data[0], dict):
            return [dict(row) for row in data]
        raise SchemaError(f"Unsupported list item type: {type(data[0])}")

    if isinstance(data, dict):
        return _normalize_dict_of_lists(data)

    raise SchemaError(f"Unsupported data type for schema validation: {type(data)}")


def _normalize_dict_of_lists(col_dict: Dict[str, Sequence[Any]]) -> List[Dict[str, Any]]:
    """Convert column-oriented dict into a list of row dicts."""
    if not col_dict:
        return []
    keys = list(col_dict.keys())
    row_count = len(col_dict[keys[0]])
    for k in keys:
        if len(col_dict[k]) != row_count:
            raise SchemaError(
                f"Column length mismatch: '{k}' has length {len(col_dict[k])}, expected {row_count}"
            )
    records = []
    for i in range(row_count):
        records.append({k: col_dict[k][i] for k in keys})
    return records


class EdgesSchema:
    """Schema validator for the 'edges' data contract.

    Contract specification (Section 5):
    - edge_id (str): Unique edge identifier ('u-v-key')
    - osm_way_id (int): OpenStreetMap way identifier
    - length_m (float): Physical length of edge in meters (must be >= 0)
    - has_dedicated_lane (bool): Whether a dedicated bike lane exists in this direction
    - geometry (str/bytes): Geometry representation (e.g. WKT, GeoJSON, or WKB)

    Graph routing extensions (optional in contract, required for graph building):
    - u (str/int): Source node
    - v (str/int): Target node
    - grade (float): Signed slope/grade (rise/run)
    - key (int): Parallel edge key
    """

    REQUIRED_FIELDS: Dict[str, type | tuple[type, ...]] = {
        "edge_id": (str,),
        "osm_way_id": (int,),
        "length_m": (int, float),
        "has_dedicated_lane": (bool,),
        "geometry": (str, bytes),
    }

    OPTIONAL_FIELDS: Dict[str, type | tuple[type, ...]] = {
        "u": (int, str),
        "v": (int, str),
        "key": (int,),
        "grade": (int, float),
    }

    @classmethod
    def validate(cls, data: Any) -> Any:
        """Validate input data against EdgesSchema.

        Returns the validated data as provided if valid, or raises SchemaError.
        """
        records = _normalize_records(data)
        if not records:
            raise SchemaError("Edges table is empty. At least one edge is required.")

        for idx, row in enumerate(records):
            for field, expected_types in cls.REQUIRED_FIELDS.items():
                if field not in row:
                    raise SchemaError(
                        f"Row {idx} missing required field '{field}'. Row content: {row}"
                    )
                val = row[field]
                if val is None:
                    raise SchemaError(f"Row {idx} field '{field}' cannot be null.")
                # bool is subclass of int in Python, check bool explicitly
                if bool in expected_types:
                    if not isinstance(val, bool):
                        raise SchemaError(
                            f"Row {idx} field '{field}' expected bool, got {type(val).__name__}"
                        )
                else:
                    if isinstance(val, bool) or not isinstance(val, expected_types):
                        type_names = ", ".join(t.__name__ for t in expected_types)
                        raise SchemaError(
                            f"Row {idx} field '{field}' expected {type_names}, got {type(val).__name__}"
                        )

            # Specific constraints
            if not str(row["edge_id"]).strip():
                raise SchemaError(f"Row {idx} 'edge_id' cannot be blank.")
            if float(row["length_m"]) < 0.0:
                raise SchemaError(
                    f"Row {idx} 'length_m' must be non-negative, got {row['length_m']}"
                )

            # Check optional fields if present
            for opt_field, opt_types in cls.OPTIONAL_FIELDS.items():
                if opt_field in row and row[opt_field] is not None:
                    val = row[opt_field]
                    if bool not in opt_types and isinstance(val, bool):
                        raise SchemaError(
                            f"Row {idx} optional field '{opt_field}' got bool, expected {opt_types}"
                        )
                    if not isinstance(val, opt_types):
                        type_names = ", ".join(t.__name__ for t in opt_types)
                        raise SchemaError(
                            f"Row {idx} field '{opt_field}' expected {type_names}, got {type(val).__name__}"
                        )

        return data


class RoutesSchema:
    """Schema validator for the 'routes' data contract.

    Contract specification (Section 5):
    - scenario (str): Scenario name (e.g. 'baseline', 'lane_aware', 'population_only', 'prototype')
    - start_station_id (str): Origin station ID
    - end_station_id (str): Destination station ID
    - route_type (str): Either 'synthetic' or 'observed'
    - edges (list[str]): Ordered list of edge_ids traversed
    - trip_count (int/float): Volume of trips assigned to this route (must be >= 0)
    """

    VALID_ROUTE_TYPES = {"synthetic", "observed"}

    REQUIRED_FIELDS: Dict[str, type | tuple[type, ...]] = {
        "scenario": (str,),
        "start_station_id": (str,),
        "end_station_id": (str,),
        "route_type": (str,),
        "edges": (list, tuple),
        "trip_count": (int, float),
    }

    @classmethod
    def validate(cls, data: Any) -> Any:
        """Validate input data against RoutesSchema.

        Returns the validated data as provided if valid, or raises SchemaError.
        """
        records = _normalize_records(data)
        if not records:
            # An empty route table can be valid if no routes were found,
            # but if columns are provided they must match.
            return data

        for idx, row in enumerate(records):
            for field, expected_types in cls.REQUIRED_FIELDS.items():
                if field not in row:
                    raise SchemaError(
                        f"Row {idx} missing required field '{field}'. Row content: {row}"
                    )
                val = row[field]
                if val is None:
                    raise SchemaError(f"Row {idx} field '{field}' cannot be null.")
                if isinstance(val, bool) or not isinstance(val, expected_types):
                    type_names = ", ".join(t.__name__ for t in expected_types)
                    raise SchemaError(
                        f"Row {idx} field '{field}' expected {type_names}, got {type(val).__name__}"
                    )

            if row["route_type"] not in cls.VALID_ROUTE_TYPES:
                raise SchemaError(
                    f"Row {idx} invalid 'route_type': '{row['route_type']}'. "
                    f"Must be one of {cls.VALID_ROUTE_TYPES}"
                )

            if float(row["trip_count"]) < 0.0:
                raise SchemaError(
                    f"Row {idx} 'trip_count' must be non-negative, got {row['trip_count']}"
                )

            # Check edges is a list of strings
            edges_list = row["edges"]
            for edge_idx, edge_item in enumerate(edges_list):
                if not isinstance(edge_item, str) or not edge_item.strip():
                    raise SchemaError(
                        f"Row {idx} edge index {edge_idx} must be a non-empty string, got {edge_item}"
                    )

        return data
