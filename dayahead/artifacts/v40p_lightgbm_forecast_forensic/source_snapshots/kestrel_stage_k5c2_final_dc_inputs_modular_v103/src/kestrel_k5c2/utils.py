from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def setup_logger(path: Path) -> logging.Logger:
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("kestrel_k5c2")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def json_default(obj: Any):
    if isinstance(obj, (pd.Timestamp, pd.Timedelta)):
        return str(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    raise TypeError(type(obj).__name__)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def latest_parent_with_file(root: Path, relative: str, stage_token: str | None = None) -> Path | None:
    if not root.exists():
        return None
    matches = []
    for p in root.rglob(Path(relative).name):
        if not p.is_file():
            continue
        try:
            rel_ok = str(p).replace("\\", "/").endswith(relative.replace("\\", "/"))
        except Exception:
            rel_ok = False
        if not rel_ok:
            continue
        parent = p
        for _ in Path(relative).parts:
            parent = parent.parent
        if stage_token and stage_token.lower() not in str(parent).lower():
            continue
        matches.append(parent)
    if not matches:
        return None
    return sorted(set(matches), key=lambda p: (p.stat().st_mtime, str(p)))[-1]


def ensure_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True)


def round_up_multiple(values, multiple: int):
    a = np.asarray(values, dtype=float)
    return (np.ceil(a / multiple) * multiple).astype(int)


def stable_largest_remainder(total: int, shares: np.ndarray, multiple: int = 1) -> np.ndarray:
    shares = np.asarray(shares, dtype=float)
    shares = np.where(np.isfinite(shares) & (shares >= 0), shares, 0)
    if shares.sum() <= 0:
        shares = np.ones_like(shares)
    shares = shares / shares.sum()
    units_total = max(int(round(total / multiple)), len(shares))
    raw = shares * units_total
    base = np.floor(raw).astype(int)
    base = np.maximum(base, 1)
    diff = units_total - int(base.sum())
    frac = raw - np.floor(raw)
    if diff > 0:
        order = np.argsort(-frac, kind="stable")
        for i in range(diff):
            base[order[i % len(order)]] += 1
    elif diff < 0:
        order = np.argsort(frac, kind="stable")
        i = 0
        while diff < 0 and i < len(order) * units_total:
            j = order[i % len(order)]
            if base[j] > 1:
                base[j] -= 1
                diff += 1
            i += 1
    return base * multiple


def create_review_zip(run_dir: Path, review_path: Path, max_mb: float, include_large: bool) -> list[dict]:
    review_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with zipfile.ZipFile(review_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(run_dir.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(run_dir)
            mb = p.stat().st_size / (1024 * 1024)
            included = include_large or mb <= max_mb
            rows.append({"relative_path": str(rel), "size_bytes": p.stat().st_size, "included_in_review": included})
            if included:
                z.write(p, arcname=str(rel))
    return rows


def copy_text_if_exists(src: Path | None, dst: Path) -> None:
    if src and src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def write_parquet_checked(df, path: Path, *, compression: str, index: bool = False) -> None:
    """Write a DataFrame after enforcing a unique-column schema.

    PyArrow rejects duplicate column names. Checking here gives a deterministic,
    stage-specific error before serialization and prevents silent schema corruption.
    """
    duplicate_mask = df.columns.duplicated(keep=False)
    if duplicate_mask.any():
        duplicates = sorted(set(df.columns[duplicate_mask].tolist()))
        raise ValueError(f"Duplicate column names before Parquet write {path}: {duplicates}")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=index, compression=compression)
