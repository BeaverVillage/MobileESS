from __future__ import annotations

import gzip
import io
import math
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd


@dataclass
class BurstResult:
    trace_5min_site: pd.DataFrame
    inventory: pd.DataFrame
    schema_audit: pd.DataFrame
    group_summary: pd.DataFrame


def _norm(s: str) -> str:
    return re.sub(r"_+", "_", str(s).strip().lower().replace("-", "_").replace(" ", "_"))


def _find(columns, candidates):
    mapping = {_norm(c): c for c in columns}
    for c in candidates:
        if _norm(c) in mapping:
            return mapping[_norm(c)]
    for k, v in mapping.items():
        for c in candidates:
            if _norm(c) in k:
                return v
    return None


def _detect(columns):
    return {
        "timestamp": _find(columns, ["timestamp", "time", "arrival_time", "request_time"]),
        "model": _find(columns, ["model", "model_name"]),
        "request_tokens": _find(columns, ["request_tokens", "input_tokens", "prompt_tokens"]),
        "response_tokens": _find(columns, ["response_tokens", "output_tokens", "completion_tokens"]),
        "total_tokens": _find(columns, ["total_tokens", "tokens"]),
        "log_type": _find(columns, ["log_type", "type"]),
        "status": _find(columns, ["status", "success", "result"]),
    }


def _iter_csv(source, chunk_rows: int):
    yield from pd.read_csv(source, chunksize=chunk_rows, low_memory=False)


def iter_tables(path: Path, chunk_rows: int) -> Iterator[tuple[str, pd.DataFrame]]:
    lower = path.name.lower()
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            members = [m for m in z.infolist() if not m.is_dir() and Path(m.filename).suffix.lower() in {".csv", ".parquet"}]
            for m in members:
                with z.open(m) as f:
                    if m.filename.lower().endswith(".csv"):
                        yield from ((f"{path}::{m.filename}", c) for c in _iter_csv(f, chunk_rows))
                    else:
                        import pyarrow.parquet as pq
                        yield f"{path}::{m.filename}", pq.read_table(f).to_pandas()
        return
    if lower.endswith(".csv.gz"):
        with gzip.open(path, "rb") as f:
            yield from ((str(path), c) for c in _iter_csv(f, chunk_rows))
        return
    if path.suffix.lower() == ".csv":
        yield from ((str(path), c) for c in _iter_csv(path, chunk_rows))
        return
    if path.suffix.lower() == ".parquet":
        yield str(path), pd.read_parquet(path)
        return
    raise ValueError(f"Unsupported BurstGPT source: {path}")




def _stable_site_numbers(local_rows: np.ndarray, seed: int, file_idx: int, idc_count: int) -> np.ndarray:
    """Deterministically spread consecutive request rows across every virtual IDC.

    The previous LCG multiplier shared a factor with 12, so one file could reach
    only four residue classes.  Choose a multiplier coprime to the requested
    site count; then consecutive row indices cycle through all sites uniformly.
    """
    if idc_count <= 0:
        raise ValueError("idc_count must be positive")
    multiplier = 1103515245
    while math.gcd(multiplier, idc_count) != 1:
        multiplier += 2
    offset = (int(seed) + int(file_idx) * 2654435761) % idc_count
    rows = np.asarray(local_rows, dtype=np.uint64)
    return ((rows * np.uint64(multiplier) + np.uint64(offset)) % np.uint64(idc_count)).astype(np.int16) + 1

def _trace_number(path: Path) -> int:
    s = path.name.lower()
    m = re.search(r"burstgpt[^0-9]*([123])(?:[^0-9]|$)", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:^|[_ -])([123])(?:[_ .-]|$)", s)
    return int(m.group(1)) if m else 0


def _trace_group(path: Path) -> str:
    n = _trace_number(path)
    return "burstgpt12" if n in {1, 2} else ("burstgpt3" if n == 3 else f"other_{path.stem}")


def _success_mask(frame: pd.DataFrame, col: str | None) -> pd.Series:
    if col is None:
        return pd.Series(True, index=frame.index)
    x = frame[col].astype(str).str.lower().str.strip()
    return ~(x.str.contains(r"fail|error|cancel|timeout|reject", regex=True, na=False) | x.isin({"false", "0", "no"}))


def aggregate(paths: list[Path], cfg: dict, logger) -> BurstResult:
    interval = int(cfg["analysis"]["interval_minutes"])
    idc_count = int(cfg["analysis"]["idc_count"])
    chunk_rows = int(cfg["burstgpt"]["chunk_rows"])
    seed = int(cfg["burstgpt"]["stable_partition_seed"])
    out_weight = float(cfg["power"]["output_token_compute_weight"])

    grouped: defaultdict[tuple, np.ndarray] = defaultdict(lambda: np.zeros(6, dtype=np.float64))
    model_grouped: defaultdict[tuple, np.ndarray] = defaultdict(lambda: np.zeros(4, dtype=np.float64))
    inventory = []
    schemas = []
    group_offsets: dict[str, float] = defaultdict(float)
    group_last: dict[str, float] = {}

    ordered = sorted(paths, key=lambda p: (_trace_group(p), _trace_number(p), str(p).lower()))
    for file_idx, path in enumerate(ordered):
        group = _trace_group(path)
        file_rows = kept = 0
        first_raw = None
        last_adjusted = None
        median_gap_samples = []
        row_offset = 0
        current_offset = group_offsets[group]
        schema_seen = set()
        for source, chunk in iter_tables(path, chunk_rows):
            if chunk.empty:
                continue
            d = _detect(chunk.columns)
            if d["timestamp"] is None:
                raise ValueError(f"BurstGPT timestamp column missing in {source}: {list(chunk.columns)}")
            key = (source, tuple(chunk.columns))
            if key not in schema_seen:
                schemas.append({"source": source, **d, "columns": "|".join(map(str, chunk.columns))})
                schema_seen.add(key)
            raw = pd.to_numeric(chunk[d["timestamp"]], errors="coerce")
            if raw.notna().mean() < 0.8:
                parsed = pd.to_datetime(chunk[d["timestamp"]], errors="coerce", utc=True)
                raw = (parsed - parsed.min()).dt.total_seconds()
            valid = raw.notna() & _success_mask(chunk, d["status"])
            file_rows += len(chunk)
            if not valid.any():
                row_offset += len(chunk)
                continue
            rv = raw[valid].to_numpy(float)
            if first_raw is None:
                first_raw = float(np.nanmin(rv))
                if group in group_last:
                    # Preserve an already-continuous axis; otherwise append after the prior file.
                    if first_raw <= group_last[group]:
                        current_offset = group_last[group] + interval * 60 - first_raw
                    else:
                        current_offset = 0.0
            adj = rv + current_offset
            order = np.argsort(adj)
            if len(adj) > 2:
                dif = np.diff(adj[order])
                dif = dif[(dif > 0) & np.isfinite(dif)]
                if len(dif):
                    median_gap_samples.append(float(np.median(dif)))
            last_adjusted = float(np.nanmax(adj)) if last_adjusted is None else max(last_adjusted, float(np.nanmax(adj)))
            kept += len(adj)

            sub = chunk.loc[valid].copy()
            req = pd.to_numeric(sub[d["request_tokens"]], errors="coerce").fillna(0).clip(lower=0) if d["request_tokens"] else pd.Series(0.0, index=sub.index)
            resp = pd.to_numeric(sub[d["response_tokens"]], errors="coerce").fillna(0).clip(lower=0) if d["response_tokens"] else pd.Series(0.0, index=sub.index)
            if d["total_tokens"]:
                total = pd.to_numeric(sub[d["total_tokens"]], errors="coerce").fillna(req + resp).clip(lower=0)
            else:
                total = req + resp
            weighted = req + out_weight * resp
            fallback = weighted <= 0
            weighted = weighted.mask(fallback, total).mask((weighted <= 0), 1.0)
            model = sub[d["model"]].astype(str) if d["model"] else pd.Series("unknown", index=sub.index)
            log_type = sub[d["log_type"]].astype(str) if d["log_type"] else pd.Series("unknown", index=sub.index)
            local_rows = np.arange(row_offset, row_offset + len(chunk), dtype=np.uint64)[valid.to_numpy()]
            # Stable, uniform assignment across every configured virtual IDC.
            site = _stable_site_numbers(local_rows, seed, file_idx, idc_count)
            slot = np.floor(adj / (interval * 60)).astype(np.int64)
            tmp = pd.DataFrame({
                "trace_group": group,
                "trace_slot": slot,
                "idc_num": site,
                "request_tokens": req.to_numpy(float),
                "response_tokens": resp.to_numpy(float),
                "total_tokens": total.to_numpy(float),
                "weighted_tokens": weighted.to_numpy(float),
                "model": model.to_numpy(str),
                "log_type": log_type.to_numpy(str),
            })
            agg = tmp.groupby(["trace_group", "trace_slot", "idc_num"], sort=False).agg(
                request_count=("weighted_tokens", "size"), request_tokens=("request_tokens", "sum"),
                response_tokens=("response_tokens", "sum"), total_tokens=("total_tokens", "sum"),
                weighted_tokens=("weighted_tokens", "sum")
            ).reset_index()
            for r in agg.itertuples(index=False):
                a = grouped[(r.trace_group, int(r.trace_slot), int(r.idc_num))]
                a[:] += [r.request_count, r.request_tokens, r.response_tokens, r.total_tokens, r.weighted_tokens, 1]
            magg = tmp.groupby(["trace_group", "model", "log_type"], sort=False).agg(request_count=("weighted_tokens", "size"), total_tokens=("total_tokens", "sum"), weighted_tokens=("weighted_tokens", "sum")).reset_index()
            for r in magg.itertuples(index=False):
                a = model_grouped[(r.trace_group, str(r.model), str(r.log_type))]
                a[:] += [r.request_count, r.total_tokens, r.weighted_tokens, 1]
            row_offset += len(chunk)
        if last_adjusted is not None:
            group_last[group] = last_adjusted
            group_offsets[group] = current_offset
        inventory.append({
            "path": str(path), "trace_number": _trace_number(path), "trace_group": group,
            "raw_rows": file_rows, "kept_rows": kept, "first_raw_seconds": first_raw,
            "last_adjusted_seconds": last_adjusted, "applied_offset_seconds": current_offset,
            "median_positive_gap_seconds": float(np.median(median_gap_samples)) if median_gap_samples else np.nan,
        })
        logger.info("BurstGPT %s group=%s kept=%d", path.name, group, kept)

    rows = []
    for (group, slot, site), a in grouped.items():
        rows.append({
            "trace_group": group, "trace_slot": slot, "idc_id": f"dc{site:02d}",
            "request_count": int(round(a[0])), "request_tokens": a[1], "response_tokens": a[2],
            "total_tokens": a[3], "weighted_tokens": a[4],
        })
    trace = pd.DataFrame(rows)
    if trace.empty:
        raise ValueError("BurstGPT aggregation produced no rows")
    trace["trace_timestamp"] = pd.Timestamp("2000-01-01", tz="UTC") + pd.to_timedelta(trace.trace_slot * interval, unit="m")
    trace.sort_values(["trace_group", "trace_slot", "idc_id"], inplace=True)
    summaries = []
    for group, g in trace.groupby("trace_group"):
        summaries.append({
            "trace_group": group, "slot_min": int(g.trace_slot.min()), "slot_max": int(g.trace_slot.max()),
            "duration_days_inclusive": (int(g.trace_slot.max()) - int(g.trace_slot.min()) + 1) * interval / 1440,
            "request_count": int(g.request_count.sum()), "total_tokens": float(g.total_tokens.sum()),
            "response_tokens": float(g.response_tokens.sum()), "site_count": int(g.idc_id.nunique()),
        })
    model_rows = []
    for (group, model, log_type), a in model_grouped.items():
        model_rows.append({"trace_group": group, "model": model, "log_type": log_type, "request_count": int(a[0]), "total_tokens": a[1], "weighted_tokens": a[2]})
    model_summary = pd.DataFrame(model_rows)
    group_summary = pd.DataFrame(summaries)
    if not model_summary.empty:
        # Attach compact model/log-type coverage as a JSON-like string per trace group.
        coverage = model_summary.groupby("trace_group").apply(lambda x: "; ".join(f"{r.model}|{r.log_type}:{int(r.request_count)}" for r in x.sort_values("request_count", ascending=False).head(20).itertuples()), include_groups=False)
        group_summary = group_summary.merge(coverage.rename("top_model_log_types"), on="trace_group", how="left")
    bad = group_summary.loc[group_summary.site_count.astype(int).ne(idc_count), ["trace_group", "site_count"]]
    if not bad.empty:
        raise ValueError(f"BurstGPT virtual-IDC coverage failure: expected {idc_count} sites per trace group, got {bad.to_dict(orient='records')}")
    return BurstResult(trace, pd.DataFrame(inventory), pd.DataFrame(schemas), group_summary)


def annualize(trace: pd.DataFrame, analysis_timestamps: pd.DatetimeIndex, trace_group: str, interval_minutes: int) -> pd.DataFrame:
    g = trace[trace.trace_group == trace_group].copy()
    if g.empty:
        raise ValueError(f"BurstGPT trace group not found: {trace_group}")
    sites = sorted(g.idc_id.unique())
    min_slot = int(g.trace_slot.min())
    max_slot = int(g.trace_slot.max())
    cycle = max_slot - min_slot + 1
    full = pd.MultiIndex.from_product([np.arange(min_slot, max_slot + 1), sites], names=["trace_slot", "idc_id"]).to_frame(index=False)
    cols = ["request_count", "request_tokens", "response_tokens", "total_tokens", "weighted_tokens"]
    full = full.merge(g[["trace_slot", "idc_id"] + cols], on=["trace_slot", "idc_id"], how="left")
    full[cols] = full[cols].fillna(0)
    lookup = {site: full[full.idc_id == site].sort_values("trace_slot")[cols].to_numpy(float) for site in sites}
    n = len(analysis_timestamps)
    idx = np.arange(n) % cycle
    repeat = np.arange(n) // cycle
    frames = []
    for site in sites:
        arr = lookup[site][idx]
        f = pd.DataFrame(arr, columns=cols)
        f.insert(0, "idc_id", site)
        f.insert(0, "timestamp_utc", analysis_timestamps)
        f["trace_group"] = trace_group
        f["trace_slot"] = min_slot + idx
        f["repeat_cycle_id"] = repeat
        f["is_repeated_trace"] = repeat > 0
        frames.append(f)
    return pd.concat(frames, ignore_index=True)
