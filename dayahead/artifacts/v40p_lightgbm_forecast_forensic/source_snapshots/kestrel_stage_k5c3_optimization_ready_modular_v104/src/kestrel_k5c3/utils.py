from __future__ import annotations
import hashlib, json, logging, zipfile
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd


def setup_logger(path: Path) -> logging.Logger:
    logger = logging.getLogger(f"k5c3:{path}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setFormatter(fmt); logger.addHandler(fh)
    sh = logging.StreamHandler(); sh.setFormatter(fmt); logger.addHandler(sh)
    return logger


def write_json(path: Path, obj: Any) -> None:
    def conv(x):
        if isinstance(x, Path): return str(x)
        if isinstance(x, (pd.Timestamp, np.datetime64)): return str(x)
        if isinstance(x, (np.integer,)): return int(x)
        if isinstance(x, (np.floating,)): return float(x)
        if isinstance(x, (np.bool_,)): return bool(x)
        if isinstance(x, np.ndarray): return x.tolist()
        raise TypeError(type(x).__name__)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=conv), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_parquet_checked(df: pd.DataFrame, path: Path, *, compression: str="zstd") -> None:
    dup = df.columns[df.columns.duplicated()].tolist()
    if dup: raise ValueError(f"Duplicate columns for {path.name}: {dup}")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False, compression=compression)


def sha256_file(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""): h.update(b)
    return h.hexdigest()


def latest_parent_with_file(root: Path, relative: str, token: str|None=None) -> Path|None:
    candidates=[]
    if not root.exists(): return None
    for p in root.rglob(Path(relative).name):
        try: rel=p.relative_to(root)
        except ValueError: continue
        if not str(rel).endswith(relative): continue
        parent=p
        for _ in Path(relative).parts: parent=parent.parent
        if token and token.lower() not in parent.name.lower(): continue
        candidates.append(parent)
    if not candidates: return None
    return max(candidates, key=lambda p:p.stat().st_mtime)


def create_review_zip(run_dir: Path, review: Path, max_mb: float, include_large: bool) -> list[dict]:
    review.parent.mkdir(parents=True, exist_ok=True)
    rows=[]
    with zipfile.ZipFile(review, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(run_dir.rglob("*")):
            if not p.is_file() or p == review: continue
            mb=p.stat().st_size/1024**2
            include=include_large or mb<=max_mb
            rows.append({"relative_path":str(p.relative_to(run_dir)),"size_bytes":p.stat().st_size,"included":include})
            if include: z.write(p, p.relative_to(run_dir))
    return rows


def round_up_multiple(value: float, multiple: int) -> int:
    return int(np.ceil(value / multiple) * multiple)


def allocate_integer_capacity(total: int, shares: np.ndarray, multiple: int, minimum_each: int) -> np.ndarray:
    n=len(shares)
    base=np.full(n, minimum_each, dtype=int)
    if base.sum()>total: raise ValueError("Total capacity is smaller than pool minimum")
    rem=total-base.sum()
    units=rem//multiple
    s=np.asarray(shares,float); s=np.maximum(s,0); s=s/s.sum()
    raw=s*units; flo=np.floor(raw).astype(int); left=units-flo.sum()
    order=np.argsort(-(raw-flo), kind="stable")
    flo[order[:left]]+=1
    return base+flo*multiple


def capped_proportional_allocation(total: float, weights: np.ndarray, caps: np.ndarray, tol: float=1e-10) -> np.ndarray:
    w=np.asarray(weights,float).copy(); c=np.asarray(caps,float).copy()
    if total<0 or total>c.sum()+1e-8: raise ValueError("Allocation total outside capacity")
    out=np.zeros_like(c)
    active=np.ones(len(c),dtype=bool)
    remaining=float(total)
    while remaining>tol and active.any():
        wa=w[active]
        if wa.sum()<=0: wa=np.ones_like(wa)
        proposal=remaining*wa/wa.sum()
        idx=np.where(active)[0]
        hit=proposal>=c[idx]-out[idx]-tol
        if not hit.any():
            out[idx]+=proposal; remaining=0; break
        for j, h in zip(idx,hit):
            if h:
                add=c[j]-out[j]; out[j]+=add; remaining-=add; active[j]=False
        if remaining<tol: break
    if remaining>1e-6: raise RuntimeError(f"Unallocated capacity remains: {remaining}")
    return out
