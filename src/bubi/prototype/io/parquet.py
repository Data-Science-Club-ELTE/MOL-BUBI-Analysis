"""Prototype Parquet I/O with native and optional PyArrow support.

Supports reading fixtures and datasets in lightweight environments.
"""

from __future__ import annotations

import os
import struct
from typing import Any, Dict, Iterator, List, Union

# Parquet physical type constants
PARQUET_TYPE_BOOLEAN = 0
PARQUET_TYPE_INT32 = 1
PARQUET_TYPE_INT64 = 2
PARQUET_TYPE_FLOAT = 4
PARQUET_TYPE_DOUBLE = 5
PARQUET_TYPE_BYTE_ARRAY = 6

CONVERTED_TYPE_UTF8 = 0
FIELD_REP_REQUIRED = 0


class Table:
    """Lightweight table structure representing tabular data."""

    def __init__(self, data: Dict[str, List[Any]]):
        self._data = {str(k): list(v) for k, v in data.items()}
        if self._data:
            first_len = len(next(iter(self._data.values())))
            for col, vals in self._data.items():
                if len(vals) != first_len:
                    raise ValueError(
                        f"Column '{col}' length {len(vals)} does not match {first_len}"
                    )
            self._length = first_len
        else:
            self._length = 0

    @property
    def columns(self) -> List[str]:
        return list(self._data.keys())

    def __len__(self) -> int:
        return self._length

    def __getitem__(self, key: Union[str, int]) -> Any:
        if isinstance(key, str):
            return self._data[key]
        if isinstance(key, int):
            return {k: self._data[k][key] for k in self.columns}
        raise KeyError(f"Unsupported key: {key}")

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        for i in range(self._length):
            yield {k: self._data[k][i] for k in self.columns}

    def to_dict(self, orient: str = "list") -> Union[Dict[str, List[Any]], List[Dict[str, Any]]]:
        if orient == "records":
            return list(self)
        return {k: list(v) for k, v in self._data.items()}

    def to_records(self) -> List[Dict[str, Any]]:
        return list(self)

    def to_dataframe(self):
        """Convert to pandas DataFrame if pandas is installed."""
        try:
            import pandas as pd

            return pd.DataFrame(self._data)
        except ImportError:
            return self

    def __repr__(self) -> str:
        return f"Table(rows={self._length}, cols={self.columns})"


class CompactProtocolWriter:
    """Thrift Compact Protocol serializer."""

    STOP = 0
    BOOLEAN_TRUE = 1
    BOOLEAN_FALSE = 2
    BYTE = 3
    I16 = 4
    I32 = 5
    I64 = 6
    DOUBLE = 7
    BINARY = 8
    LIST = 9
    SET = 10
    MAP = 11
    STRUCT = 12

    def __init__(self):
        self.buf = bytearray()
        self.last_id_stack = []

    def get_bytes(self) -> bytes:
        return bytes(self.buf)

    def write_varint(self, n: int) -> None:
        while True:
            b = n & 0x7F
            n >>= 7
            if n:
                self.buf.append(b | 0x80)
            else:
                self.buf.append(b)
                break

    def write_zigzag(self, n: int, bits: int = 64) -> None:
        z = (n << 1) ^ (n >> (bits - 1))
        self.write_varint(z)

    def write_byte(self, b: int) -> None:
        self.buf.append(b & 0xFF)

    def struct_begin(self) -> None:
        self.last_id_stack.append(0)

    def struct_end(self) -> None:
        self.last_id_stack.pop()
        self.write_byte(self.STOP)

    def write_field_header(self, field_id: int, wire_type: int) -> None:
        last_id = self.last_id_stack[-1]
        delta = field_id - last_id
        if 0 < delta <= 15:
            self.write_byte((delta << 4) | wire_type)
        else:
            self.write_byte(wire_type)
            self.write_zigzag(field_id, bits=16)
        self.last_id_stack[-1] = field_id

    def write_i32(self, field_id: int, value: int) -> None:
        self.write_field_header(field_id, self.I32)
        self.write_zigzag(value, bits=32)

    def write_i64(self, field_id: int, value: int) -> None:
        self.write_field_header(field_id, self.I64)
        self.write_zigzag(value, bits=64)

    def write_binary(self, field_id: int, data: Union[str, bytes]) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.write_field_header(field_id, self.BINARY)
        self.write_varint(len(data))
        self.buf.extend(data)

    def write_raw_binary(self, data: Union[str, bytes]) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.write_varint(len(data))
        self.buf.extend(data)

    def write_raw_i32(self, value: int) -> None:
        self.write_zigzag(value, bits=32)

    def write_struct_field_begin(self, field_id: int) -> None:
        self.write_field_header(field_id, self.STRUCT)
        self.struct_begin()

    def write_list_field_begin(self, field_id: int, size: int, elem_wire_type: int) -> None:
        self.write_field_header(field_id, self.LIST)
        if size < 15:
            self.write_byte((size << 4) | elem_wire_type)
        else:
            self.write_byte(0xF0 | elem_wire_type)
            self.write_varint(size)


class CompactProtocolReader:
    """Thrift Compact Protocol deserializer."""

    STOP = 0
    BOOLEAN_TRUE = 1
    BOOLEAN_FALSE = 2
    BYTE = 3
    I16 = 4
    I32 = 5
    I64 = 6
    DOUBLE = 7
    BINARY = 8
    LIST = 9
    STRUCT = 12

    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos
        self.last_id_stack = []

    def read_byte(self) -> int:
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_varint(self) -> int:
        res = 0
        shift = 0
        while True:
            b = self.read_byte()
            res |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        return res

    def read_zigzag(self, bits: int = 64) -> int:
        n = self.read_varint()
        return (n >> 1) ^ -(n & 1)

    def struct_begin(self) -> None:
        self.last_id_stack.append(0)

    def struct_end(self) -> None:
        self.last_id_stack.pop()

    def read_field_header(self) -> tuple[int, int]:
        b = self.read_byte()
        if b == self.STOP:
            return 0, self.STOP
        wire_type = b & 0x0F
        delta = (b >> 4) & 0x0F
        if delta == 0:
            field_id = self.read_zigzag(bits=16)
        else:
            field_id = self.last_id_stack[-1] + delta
        self.last_id_stack[-1] = field_id
        return field_id, wire_type

    def read_binary(self) -> bytes:
        length = self.read_varint()
        data = self.data[self.pos : self.pos + length]
        self.pos += length
        return data

    def read_string(self) -> str:
        return self.read_binary().decode("utf-8")

    def read_i32(self) -> int:
        return self.read_zigzag(bits=32)

    def read_i64(self) -> int:
        return self.read_zigzag(bits=64)

    def read_list_header(self) -> tuple[int, int]:
        b = self.read_byte()
        elem_type = b & 0x0F
        size = (b >> 4) & 0x0F
        if size == 0x0F:
            size = self.read_varint()
        return size, elem_type

    def skip(self, wire_type: int) -> None:
        if wire_type in (self.BOOLEAN_TRUE, self.BOOLEAN_FALSE):
            pass
        elif wire_type == self.BYTE:
            self.pos += 1
        elif wire_type in (self.I16, self.I32, self.I64):
            self.read_varint()
        elif wire_type == self.DOUBLE:
            self.pos += 8
        elif wire_type == self.BINARY:
            length = self.read_varint()
            self.pos += length
        elif wire_type == self.STRUCT:
            self.struct_begin()
            while True:
                _, stype = self.read_field_header()
                if stype == self.STOP:
                    break
                self.skip(stype)
            self.struct_end()
        elif wire_type == self.LIST:
            size, elem_type = self.read_list_header()
            for _ in range(size):
                self.skip(elem_type)


def write_parquet(
    file_path: str, data: Union[Dict[str, List[Any]], List[Dict[str, Any]], Any]
) -> None:
    """Write table data to a Parquet file."""
    # Normalize input into column-dict
    if hasattr(data, "to_dict"):
        col_dict = data.to_dict(orient="list")
    elif isinstance(data, list):
        if not data:
            raise ValueError("Cannot write empty records list to Parquet")
        cols = list(data[0].keys())
        col_dict = {c: [r[c] for r in data] for c in cols}
    elif isinstance(data, dict):
        col_dict = {k: list(v) for k, v in data.items()}
    elif isinstance(data, Table):
        col_dict = data.to_dict(orient="list")
    else:
        raise ValueError(f"Unsupported data format for write_parquet: {type(data)}")

    col_names = list(col_dict.keys())
    num_rows = len(col_dict[col_names[0]]) if col_names else 0

    file_buf = bytearray(b"PAR1")

    schema_elements = [{"name": "schema", "num_children": len(col_names)}]
    col_chunks = []
    total_uncompressed = 0

    for name in col_names:
        values = col_dict[name]
        sample = values[0] if values else None

        if isinstance(sample, bool):
            ptype = PARQUET_TYPE_BOOLEAN
            ctype = None
            raw = bytearray()
            curr = 0
            bit_count = 0
            for v in values:
                if v:
                    curr |= 1 << bit_count
                bit_count += 1
                if bit_count == 8:
                    raw.append(curr)
                    curr = 0
                    bit_count = 0
            if bit_count > 0:
                raw.append(curr)
            page_data = bytes(raw)
        elif isinstance(sample, int):
            ptype = PARQUET_TYPE_INT64
            ctype = None
            page_data = b"".join(struct.pack("<q", int(v)) for v in values)
        elif isinstance(sample, float):
            ptype = PARQUET_TYPE_DOUBLE
            ctype = None
            page_data = b"".join(struct.pack("<d", float(v)) for v in values)
        else:
            ptype = PARQUET_TYPE_BYTE_ARRAY
            ctype = CONVERTED_TYPE_UTF8
            raw = bytearray()
            for v in values:
                b = str(v).encode("utf-8")
                raw.extend(struct.pack("<I", len(b)))
                raw.extend(b)
            page_data = bytes(raw)

        schema_elements.append(
            {
                "type": ptype,
                "repetition_type": FIELD_REP_REQUIRED,
                "name": name,
                "converted_type": ctype,
            }
        )

        # PageHeader
        w = CompactProtocolWriter()
        w.struct_begin()
        w.write_i32(1, 0)  # DATA_PAGE
        w.write_i32(2, len(page_data))
        w.write_i32(3, len(page_data))
        w.write_struct_field_begin(5)
        w.write_i32(1, num_rows)
        w.write_i32(2, 0)  # PLAIN
        w.write_i32(3, 3)  # RLE
        w.write_i32(4, 3)  # RLE
        w.struct_end()
        w.struct_end()
        page_header_bytes = w.get_bytes()

        data_page_offset = len(file_buf)
        file_buf.extend(page_header_bytes)
        file_buf.extend(page_data)

        total_size = len(page_header_bytes) + len(page_data)
        total_uncompressed += total_size

        col_chunks.append(
            {
                "file_offset": data_page_offset,
                "meta_data": {
                    "type": ptype,
                    "encodings": [0],
                    "path_in_schema": [name],
                    "codec": 0,
                    "num_values": num_rows,
                    "total_uncompressed_size": total_size,
                    "total_compressed_size": total_size,
                    "data_page_offset": data_page_offset,
                },
            }
        )

    row_groups = [
        {
            "columns": col_chunks,
            "total_byte_size": total_uncompressed,
            "num_rows": num_rows,
        }
    ]

    # FileMetaData
    w = CompactProtocolWriter()
    w.struct_begin()
    w.write_i32(1, 1)  # version
    w.write_list_field_begin(2, len(schema_elements), w.STRUCT)
    for elem in schema_elements:
        w.struct_begin()
        if "type" in elem:
            w.write_i32(1, elem["type"])
        if "repetition_type" in elem:
            w.write_i32(3, elem["repetition_type"])
        w.write_binary(4, elem["name"])
        if "num_children" in elem:
            w.write_i32(5, elem["num_children"])
        if elem.get("converted_type") is not None:
            w.write_i32(6, elem["converted_type"])
        w.struct_end()
    w.write_i64(3, num_rows)
    w.write_list_field_begin(4, len(row_groups), w.STRUCT)
    for rg in row_groups:
        w.struct_begin()
        w.write_list_field_begin(1, len(rg["columns"]), w.STRUCT)
        for col in rg["columns"]:
            w.struct_begin()
            w.write_i64(2, col["file_offset"])
            w.write_struct_field_begin(3)
            cmd = col["meta_data"]
            w.write_i32(1, cmd["type"])
            w.write_list_field_begin(2, len(cmd["encodings"]), w.I32)
            for enc in cmd["encodings"]:
                w.write_raw_i32(enc)
            w.write_list_field_begin(3, len(cmd["path_in_schema"]), w.BINARY)
            for p in cmd["path_in_schema"]:
                w.write_raw_binary(p)
            w.write_i32(4, cmd["codec"])
            w.write_i64(5, cmd["num_values"])
            w.write_i64(6, cmd["total_uncompressed_size"])
            w.write_i64(7, cmd["total_compressed_size"])
            w.write_i64(9, cmd["data_page_offset"])
            w.struct_end()
            w.struct_end()
        w.write_i64(2, rg["total_byte_size"])
        w.write_i64(3, rg["num_rows"])
        w.struct_end()
    w.write_binary(6, "bubi-prototype")
    w.struct_end()

    meta_bytes = w.get_bytes()
    file_buf.extend(meta_bytes)
    file_buf.extend(struct.pack("<I", len(meta_bytes)))
    file_buf.extend(b"PAR1")

    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(file_buf)


def _read_native_parquet(file_path: str) -> Table:
    """Read the subset of Parquet supported by the lightweight native reader."""
    with open(file_path, "rb") as f:
        data = f.read()

    if data[:4] != b"PAR1" or data[-4:] != b"PAR1":
        raise ValueError(f"File '{file_path}' is not a valid Parquet file (magic bytes missing).")

    meta_len = struct.unpack("<I", data[-8:-4])[0]
    meta_start = len(data) - 8 - meta_len
    r = CompactProtocolReader(data, meta_start)
    r.struct_begin()

    schema = []
    row_groups = []

    while True:
        fid, ftype = r.read_field_header()
        if ftype == 0:
            break
        if fid == 1:
            r.read_i32()
        elif fid == 2:  # schema
            size, _ = r.read_list_header()
            for _ in range(size):
                r.struct_begin()
                se = {}
                while True:
                    sfid, sftype = r.read_field_header()
                    if sftype == 0:
                        break
                    if sfid == 1:
                        se["type"] = r.read_i32()
                    elif sfid == 3:
                        se["repetition_type"] = r.read_i32()
                    elif sfid == 4:
                        se["name"] = r.read_string()
                    elif sfid == 5:
                        se["num_children"] = r.read_i32()
                    elif sfid == 6:
                        se["converted_type"] = r.read_i32()
                    else:
                        r.skip(sftype)
                r.struct_end()
                schema.append(se)
        elif fid == 3:
            r.read_i64()
        elif fid == 4:  # row_groups
            rg_size, _ = r.read_list_header()
            for _ in range(rg_size):
                r.struct_begin()
                rg = {"columns": []}
                while True:
                    rfid, rftype = r.read_field_header()
                    if rftype == 0:
                        break
                    if rfid == 1:  # columns
                        col_size, _ = r.read_list_header()
                        for _ in range(col_size):
                            r.struct_begin()
                            col = {}
                            while True:
                                cfid, cftype = r.read_field_header()
                                if cftype == 0:
                                    break
                                if cfid == 3:  # meta_data
                                    r.struct_begin()
                                    meta = {}
                                    while True:
                                        mfid, mftype = r.read_field_header()
                                        if mftype == 0:
                                            break
                                        if mfid == 1:
                                            meta["type"] = r.read_i32()
                                        elif mfid == 3:
                                            psize, _ = r.read_list_header()
                                            meta["path_in_schema"] = [
                                                r.read_string() for _ in range(psize)
                                            ]
                                        elif mfid == 5:
                                            meta["num_values"] = r.read_i64()
                                        elif mfid == 6:
                                            meta["total_uncompressed_size"] = r.read_i64()
                                        elif mfid == 9:
                                            meta["data_page_offset"] = r.read_i64()
                                        else:
                                            r.skip(mftype)
                                    r.struct_end()
                                    col["meta_data"] = meta
                                else:
                                    r.skip(cftype)
                            r.struct_end()
                            rg["columns"].append(col)
                    elif rfid == 3:
                        rg["num_rows"] = r.read_i64()
                    else:
                        r.skip(rftype)
                r.struct_end()
                row_groups.append(rg)
        else:
            r.skip(ftype)
    r.struct_end()

    # Read data pages
    result: Dict[str, List[Any]] = {}
    for rg in row_groups:
        for col in rg["columns"]:
            meta = col["meta_data"]
            col_name = meta["path_in_schema"][0]
            offset = meta["data_page_offset"]
            col_type = meta["type"]
            n_vals = meta["num_values"]

            pr = CompactProtocolReader(data, offset)
            pr.struct_begin()
            uncompressed_page_size = 0
            while True:
                pfid, pftype = pr.read_field_header()
                if pftype == 0:
                    break
                if pfid == 2:
                    uncompressed_page_size = pr.read_i32()
                else:
                    pr.skip(pftype)
            pr.struct_end()

            data_start = pr.pos
            page_data = data[data_start : data_start + uncompressed_page_size]

            if col_type == PARQUET_TYPE_BOOLEAN:
                res = []
                bidx = 0
                bit = 0
                for _ in range(n_vals):
                    b = page_data[bidx]
                    res.append(bool(b & (1 << bit)))
                    bit += 1
                    if bit == 8:
                        bit = 0
                        bidx += 1
                result.setdefault(col_name, []).extend(res)
            elif col_type == PARQUET_TYPE_INT64:
                vals = list(struct.unpack(f"<{n_vals}q", page_data))
                result.setdefault(col_name, []).extend(vals)
            elif col_type == PARQUET_TYPE_DOUBLE:
                vals = list(struct.unpack(f"<{n_vals}d", page_data))
                result.setdefault(col_name, []).extend(vals)
            elif col_type == PARQUET_TYPE_BYTE_ARRAY:
                res = []
                dpos = 0
                for _ in range(n_vals):
                    vlen = struct.unpack("<I", page_data[dpos : dpos + 4])[0]
                    dpos += 4
                    res.append(page_data[dpos : dpos + vlen].decode("utf-8"))
                    dpos += vlen
                result.setdefault(col_name, []).extend(res)

    return Table(result)


def read_parquet(file_path: str) -> Table:
    """Read a Parquet file and return a Table.

    Use PyArrow when available to support standard Parquet encodings and binary
    columns; fall back to the lightweight reader in minimal environments.
    """
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return _read_native_parquet(file_path)

    arrow_table = pq.read_table(file_path)
    return Table({column: arrow_table[column].to_pylist() for column in arrow_table.column_names})
