from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb


def quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def connect(config: dict[str, Any]) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    temp_directory = Path(config["resources"]["temp_directory"])
    temp_directory.mkdir(parents=True, exist_ok=True)

    connection.execute(f"SET threads={int(config['resources']['threads'])}")
    connection.execute(f"SET memory_limit='{config['resources']['memory_limit']}'")
    connection.execute(f"SET temp_directory='{quote(temp_directory)}'")
    connection.execute("SET preserve_insertion_order=false")
    connection.execute("SET TimeZone='UTC'")

    return connection


def parquet_expr(path: Path) -> str:
    return f"read_parquet('{quote(path)}')"


def copy_query(connection, query: str, target: Path, compression: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    connection.execute(
        f"""COPY ({query})
        TO '{quote(target)}'
        (FORMAT PARQUET, COMPRESSION {compression.upper()})"""
    )
