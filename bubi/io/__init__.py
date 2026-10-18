"""I/O utilities for parquet tables and datasets."""

from bubi.io.parquet import Table, read_parquet, write_parquet

__all__ = ["read_parquet", "write_parquet", "Table"]
