from __future__ import annotations

from pathlib import Path
from typing import Any


def connect(config: dict[str, Any]):
    import duckdb
    con = duckdb.connect(':memory:')
    con.execute(f"SET threads={int(config['resources']['threads'])}")
    con.execute(f"SET memory_limit='{config['resources']['memory_limit']}'")
    temp = Path(config['resources']['temp_directory'])
    temp.mkdir(parents=True, exist_ok=True)
    escaped = str(temp).replace("'", "''")
    con.execute(f"SET temp_directory='{escaped}'")
    con.execute("SET TimeZone='UTC'")
    return con


def quote_path(path: Path) -> str:
    return str(path).replace("'", "''")


def parquet_expr(path: Path) -> str:
    return f"read_parquet('{quote_path(path)}')"


def copy_query(con, query: str, target: Path, compression: str = 'zstd') -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    escaped = quote_path(target)
    con.execute(
        f"COPY ({query}) TO '{escaped}' (FORMAT PARQUET, COMPRESSION {compression.upper()})"
    )
