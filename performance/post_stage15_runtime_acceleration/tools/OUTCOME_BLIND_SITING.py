#!/usr/bin/env python3
"""Outcome-blind 2024 planning siting for the post-Stage15 M1-M4 matrix.

This program deliberately has no controller-result input.  It consumes the frozen
24-service electrical/transport axis, the frozen IEEE-123/OpenDSS adapter, and
2024 AEMO load/PV archives.  Site identities are produced only after a separate
machine-readable preregistration file has been written.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import networkx as nx
import numpy as np
import pandas as pd


AEST = timezone(timedelta(hours=10))
V_MIN = 0.95
V_MAX = 1.05
EPS = 1e-8
DELTA_P_KW = 50.0
DELTA_Q_KVAR = 50.0
SERVICES = [f"IDC{i:02d}" for i in range(1, 13)] + [f"STA{i:02d}" for i in range(1, 13)]

DEFAULT_RAW = Path("/mnt/c/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터")
DEFAULT_INT = Path("/home/jaewon/mobile_ess_work/integrated_rebuild/current")
DEFAULT_P70 = Path("/home/jaewon/mobile_ess_work/processed/power_v70_3ph/runtime_arrays")
DEFAULT_ASSETS = Path("/home/jaewon/mobile_ess_work/frozen_artifacts/stage_mess_grid_preintegration_opendss_asset_compile_v2_20260806T082257Z/bound_opendss_assets")
DEFAULT_SERVICE_MAP = Path("/home/jaewon/mobile_ess_work/frozen_artifacts/stage_k9h7_v2044r12b1d1b2_jointmaster_build7ar2_service24_exactgridapi_20260810T090119/BUILD7_MESS_SERVICE_NODE_MAP_24.csv")
DEFAULT_TRANSPORT_AXIS = Path("/home/jaewon/mobile_ess_work/frozen_artifacts/stage_k9h7_v2044r12b1d1b2_jointmaster_build7ar2_service24_exactgridapi_20260810T090119/BUILD7_TRAFFIC_ELECTRICAL_SERVICE_NODE_AXIS_24.csv")
DEFAULT_ROUTE_AUDIT = Path("/home/jaewon/mobile_ess_work/post_stage15_runtime_acceleration/science/embedded/BUILD7BR7_ROUTE_GRAPH_AUDIT_AUTHORITY.json")
DEFAULT_PV_REPAIR_AUTHORITY = Path("/mnt/c/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/github_MobileESS_rep_period_pr/period_selection/aemo_pv_repair.py")

AUTHORIZED_2024_ROOFTOP_DEFECTS = {
    "2024-09-05 13:00:00": "MISSING",
    "2024-09-05 13:30:00": "MISSING",
    "2024-09-05 14:00:00": "BLANK",
    "2024-12-10 10:30:00": "BLANK",
    "2024-12-10 11:00:00": "BLANK",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def source_row(path: Path, role: str, *, raw_2024: bool = False) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "role": role,
        "raw_2024_snapshot_value_source": raw_2024,
    }


def fixed_aest_interval_end_to_utc_start(values: pd.Series, minutes: int) -> pd.DatetimeIndex:
    naive = pd.to_datetime(values, format="%Y/%m/%d %H:%M:%S", errors="raise") - pd.Timedelta(minutes=minutes)
    return pd.DatetimeIndex([x.to_pydatetime().replace(tzinfo=AEST).astimezone(timezone.utc) for x in naive])


def parse_mmsdm(path: Path, family: str, table: str) -> pd.DataFrame:
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    with zipfile.ZipFile(path) as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"ZIP CRC failure: {path}: {bad}")
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise RuntimeError(f"expected one CSV in {path}, got {names}")
        with zf.open(names[0]) as raw:
            reader = csv.reader(line.decode("utf-8-sig", errors="replace") for line in raw)
            for rec in reader:
                if len(rec) < 5 or rec[1] != family or rec[2] != table:
                    continue
                if rec[0] == "I":
                    header = rec[4:]
                elif rec[0] == "D":
                    if header is None:
                        raise RuntimeError(f"MMSDM data before header: {path}")
                    rows.append(dict(zip(header, rec[4 : 4 + len(header)])))
    if not rows:
        raise RuntimeError(f"no {family}.{table} records in {path}")
    return pd.DataFrame(rows)


def month_token(path: Path, year: int) -> int | None:
    m = re.search(rf"{year}(\d{{2}})010000", path.name)
    return int(m.group(1)) if m else None


def monthly_archives(root: Path, year: int) -> list[Path]:
    by_month: dict[int, Path] = {}
    for p in sorted(root.glob("*.zip")):
        month = month_token(p, year)
        if month is not None:
            if month in by_month:
                raise RuntimeError(f"duplicate {year}-{month:02d} archive in {root}")
            by_month[month] = p
    if set(by_month) != set(range(1, 13)):
        raise RuntimeError(f"{root}: {year} monthly coverage={sorted(by_month)}")
    return [by_month[m] for m in range(1, 13)]


def parse_regionsum(paths: Iterable[Path]) -> pd.Series:
    pieces = []
    for p in paths:
        d = parse_mmsdm(p, "DISPATCH", "REGIONSUM")
        d = d[d["REGIONID"].eq("VIC1")].copy()
        if "INTERVENTION" in d:
            d = d[d["INTERVENTION"].astype(str).eq("0")]
        d["value"] = pd.to_numeric(d["TOTALDEMAND"], errors="coerce")
        d["t"] = fixed_aest_interval_end_to_utc_start(d["SETTLEMENTDATE"], 5)
        pieces.append(d[["t", "value"]])
    x = pd.concat(pieces).sort_values("t").drop_duplicates("t", keep="last")
    return x.set_index("t")["value"]


def parse_rooftop(
    paths: Iterable[Path],
    index5: pd.DatetimeIndex,
    repair_authority: Path,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    pieces = []
    for p in paths:
        d = parse_mmsdm(p, "ROOFTOP", "ACTUAL")
        d = d[d["REGIONID"].eq("VIC1")].copy()
        d["power"] = pd.to_numeric(d["POWER"], errors="coerce")
        d["qi"] = pd.to_numeric(d["QI"], errors="coerce")
        d["t"] = fixed_aest_interval_end_to_utc_start(d["INTERVAL_DATETIME"], 30)
        pieces.append(d[["t", "TYPE", "power", "qi"]])
    d = pd.concat(pieces).sort_values("t")
    measurement_rows = d[d["TYPE"].eq("MEASUREMENT")].copy()
    satellite_rows = d[d["TYPE"].eq("SATELLITE")].copy()

    def exact_deduplicate(rows: pd.DataFrame, label: str) -> tuple[pd.DataFrame, int]:
        exact_duplicate_rows = 0
        kept = []
        for stamp, group in rows.groupby("t", sort=True):
            finite = sorted(set(float(x) for x in group["power"] if np.isfinite(x)))
            if len(finite) > 1:
                raise RuntimeError(f"2024 rooftop {label} conflicting duplicate at {stamp}: {finite}")
            exact_duplicate_rows += len(group) - 1
            kept.append({
                "t": stamp,
                "power": finite[0] if finite else np.nan,
                "had_blank": bool(group["power"].isna().any()),
            })
        return pd.DataFrame(kept).set_index("t"), exact_duplicate_rows

    measurement, measurement_duplicates = exact_deduplicate(measurement_rows, "MEASUREMENT")
    satellite, satellite_duplicates = exact_deduplicate(satellite_rows, "SATELLITE")
    grid30 = pd.date_range(index5[0], index5[-1] + pd.Timedelta(minutes=5), freq="30min", inclusive="left")
    m = measurement.reindex(grid30)
    s = satellite.reindex(grid30)
    mp = m["power"].to_numpy(dtype=float)
    sp = s["power"].to_numpy(dtype=float)

    def utc_start_from_aest_end(text: str) -> pd.Timestamp:
        end = pd.Timestamp(text).to_pydatetime().replace(tzinfo=AEST)
        return pd.Timestamp(end.astimezone(timezone.utc)) - pd.Timedelta(minutes=30)

    authorized_by_start = {
        utc_start_from_aest_end(text): issue
        for text, issue in AUTHORIZED_2024_ROOFTOP_DEFECTS.items()
    }
    observed_defects: dict[pd.Timestamp, str] = {}
    measurement_present = set(measurement_rows["t"])
    measurement_blank = {
        stamp for stamp, group in measurement_rows.groupby("t", sort=False)
        if bool(group["power"].isna().any())
    }
    for stamp in grid30:
        if stamp not in measurement_present:
            observed_defects[stamp] = "MISSING"
        elif stamp in measurement_blank:
            observed_defects[stamp] = "BLANK"
    if observed_defects != authorized_by_start:
        render = lambda x: {str(k): v for k, v in x.items()}
        raise RuntimeError(
            "2024 rooftop defects differ from accepted representative-period authority: "
            f"observed={render(observed_defects)} authorized={render(authorized_by_start)}"
        )

    filled = mp.copy()
    quality = np.zeros(len(grid30), dtype=np.int8)
    repair_rows = []
    for stamp, issue in authorized_by_start.items():
        pos = int(grid30.get_loc(stamp))
        if np.isfinite(sp[pos]):
            value = float(sp[pos])
            method = "SAME_TIMESTAMP_SATELLITE_FALLBACK"
            quality[pos] = 1
            left_stamp = right_stamp = None
        else:
            left_pos = pos - 1
            while left_pos >= 0 and not np.isfinite(mp[left_pos]):
                left_pos -= 1
            right_pos = pos + 1
            while right_pos < len(mp) and not np.isfinite(mp[right_pos]):
                right_pos += 1
            if left_pos < 0 or right_pos >= len(mp):
                raise RuntimeError(f"authorized rooftop defect is not bracketed: {stamp}")
            stamp_aest = stamp.tz_convert(AEST)
            left_stamp = grid30[left_pos]
            right_stamp = grid30[right_pos]
            if left_stamp.tz_convert(AEST).date() != stamp_aest.date() or right_stamp.tz_convert(AEST).date() != stamp_aest.date():
                raise RuntimeError(f"authorized rooftop repair crosses a fixed-AEST calendar day: {stamp}")
            fraction = float((stamp - left_stamp) / (right_stamp - left_stamp))
            value = float(mp[left_pos] + fraction * (mp[right_pos] - mp[left_pos]))
            method = "LINEAR_INTERPOLATION_NO_SATELLITE_AVAILABLE"
            quality[pos] = 2
        if not np.isfinite(value) or value < 0.0:
            raise RuntimeError(f"authorized rooftop repair is negative/nonfinite: {stamp} value={value}")
        filled[pos] = value
        repair_rows.append({
            "interval_end_aest": (stamp + pd.Timedelta(minutes=30)).tz_convert(AEST).strftime("%Y-%m-%d %H:%M:%S"),
            "interval_start_utc": stamp.isoformat(),
            "source_issue": issue,
            "repair_method": method,
            "repaired_power_mw": value,
            "left_interval_start_utc": left_stamp.isoformat() if left_stamp is not None else None,
            "right_interval_start_utc": right_stamp.isoformat() if right_stamp is not None else None,
        })
    unresolved = ~np.isfinite(filled)
    if unresolved.any():
        bad = [str(grid30[i]) for i in np.flatnonzero(unresolved)[:20]]
        raise RuntimeError(f"2024 rooftop unauthorized unresolved intervals={int(unresolved.sum())}: {bad}")
    p5 = pd.Series(filled, index=grid30).reindex(index5, method="ffill")
    q5 = pd.Series(quality, index=grid30).reindex(index5, method="ffill")
    if p5.isna().any() or q5.isna().any():
        raise RuntimeError("2024 rooftop 5-minute coverage gap")
    audit = {
        "expected_30min": len(grid30),
        "measurement_nonfinite": int((~np.isfinite(mp)).sum()),
        "exact_duplicate_measurement_rows_removed": measurement_duplicates,
        "exact_duplicate_satellite_rows_removed": satellite_duplicates,
        "authorized_defect_count": len(observed_defects),
        "satellite_fallback_30min": int((quality == 1).sum()),
        "satellite_fallback_5min": int((q5.to_numpy() == 1).sum()),
        "linear_interpolation_30min": int((quality == 2).sum()),
        "linear_interpolation_5min": int((q5.to_numpy() == 2).sum()),
        "unresolved": 0,
        "cleaning_rule": "exact accepted PR3 rule: exact deduplication; same-timestamp SATELLITE fallback; linear interpolation only for an authorized defect when both measurement and satellite are absent and same-fixed-AEST-day brackets exist; exact six-slot hold to 5 minutes",
        "accepted_repair_authority_path": str(repair_authority.resolve()),
        "accepted_repair_authority_sha256": sha256(repair_authority),
        "repairs": repair_rows,
    }
    return p5.to_numpy(dtype=float), q5.to_numpy(dtype=np.int8), audit


def normalize_epoch_ns(values: np.ndarray) -> np.ndarray:
    a = np.asarray(values).astype(np.int64)
    med = int(np.median(np.abs(a)))
    if med >= 10**17:
        return a
    if med >= 10**14:
        return a * 1_000
    if med >= 10**11:
        return a * 1_000_000
    raise RuntimeError(f"unsupported epoch scale {med}")


def fit_frozen_totaldemand_mapping(p70: Path, raw_root: Path) -> tuple[dict[str, Any], list[Path]]:
    raw_2025_root = raw_root / "전력 데이터 AEMO Victoria"
    paths = []
    by_month: dict[int, Path] = {}
    for p in sorted(raw_2025_root.rglob("*.zip")):
        if "DISPATCHREGIONSUM" not in p.name:
            continue
        month = month_token(p, 2025)
        if month is not None:
            by_month.setdefault(month, p)
    if set(by_month) != set(range(1, 13)):
        raise RuntimeError(f"frozen 2025 TOTALDEMAND lineage raw coverage missing: {sorted(by_month)}")
    paths = [by_month[m] for m in range(1, 13)]
    idx = pd.date_range("2024-12-31T14:00:00Z", "2025-12-31T14:00:00Z", freq="5min", inclusive="left")
    td = parse_regionsum(paths).reindex(idx)
    if td.isna().any():
        raise RuntimeError("2025 TOTALDEMAND lineage coverage gap")
    target = np.load(p70 / "operational_net_target_total_kw.npy", mmap_mode="r", allow_pickle=False)
    time_ns = normalize_epoch_ns(np.load(p70 / "time_index_utc_ns.npy", mmap_mode="r", allow_pickle=False))
    expected = idx.tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]").astype(np.int64)
    if target.shape != (len(idx),) or not np.array_equal(time_ns, expected):
        raise RuntimeError("power_v70 frozen operational-net target time axis mismatch")
    y = np.asarray(target, dtype=float)
    x = td.to_numpy(dtype=float)
    slope, intercept = np.linalg.lstsq(np.column_stack([x, np.ones_like(x)]), y, rcond=None)[0]
    pred = slope * x + intercept
    max_abs = float(np.max(np.abs(pred - y)))
    r2 = float(1.0 - np.sum((pred - y) ** 2) / np.sum((y - y.mean()) ** 2))
    if max_abs > 0.02 or r2 < 0.99999999:
        raise RuntimeError(f"frozen TOTALDEMAND mapping reproduction failed max_abs={max_abs} r2={r2}")
    return {
        "status": "PASS_REPRODUCED_FROZEN_PREPROCESSING_TRANSFORM",
        "slope_kw_per_regional_mw": float(slope),
        "intercept_kw": float(intercept),
        "max_abs_frozen_2025_reproduction_kw": max_abs,
        "r2": r2,
        "role": "pre-existing feeder scaling transform only; no 2025 controller result or site outcome is read",
    }, paths


@dataclass
class StaticSpatial:
    buses: list[str]
    base_p: np.ndarray
    relative_qp: np.ndarray
    weighted_qp: float
    cluster: np.ndarray
    pv_capacity: np.ndarray
    residual_lookup: dict[tuple[int, int, str, int], float]
    q_lookup: dict[tuple[int, str, int], float]


def load_static_spatial(int_root: Path, p70: Path) -> StaticSpatial:
    native_path = int_root / "06_opendss_3ph/electrical_zones/native_load_phase_manifest.csv.gz"
    nd = pd.read_csv(native_path)
    buses = np.load(p70 / "bus_ids.npy", allow_pickle=False).astype(str).tolist()
    bidx = {b.lower(): i for i, b in enumerate(buses)}
    bp = np.zeros((len(buses), 3), dtype=float)
    bq = np.zeros_like(bp)
    for row in nd.itertuples():
        b = str(row.bus).lower()
        ph = int(row.phase)
        if b in bidx and ph in (1, 2, 3):
            bp[bidx[b], ph - 1] += float(row.base_p_kw)
            bq[bidx[b], ph - 1] += float(row.base_q_kvar)
    frozen_mask = np.load(p70 / "native_load_phase_mask.npy", allow_pickle=False).astype(bool)
    if not np.array_equal(bp > 0, frozen_mask) or abs(float(bp.sum()) - 3490.0) > 1e-6:
        raise RuntimeError("native IEEE-123 load allocation does not reproduce frozen p70 static contract")
    weighted = float(bq.sum() / bp.sum())
    native_qp = np.divide(bq, bp, out=np.zeros_like(bq), where=bp > 1e-9)
    rel = np.divide(native_qp, weighted, out=np.ones_like(native_qp), where=abs(weighted) > 1e-9)
    rel = np.where(bp > 0, np.clip(rel, 0.15, 3.0), 0.0)
    cluster = np.load(p70 / "load_archetype_cluster_id.npy", allow_pickle=False).astype(np.int16)
    pvcap = np.load(p70 / "pv_capacity_kw.npy", allow_pickle=False).astype(float)
    if cluster.shape != (len(buses),) or pvcap.shape != (len(buses), 3) or abs(float(pvcap.sum()) - 698.0) > 1e-3:
        raise RuntimeError("frozen spatial array shape/capacity mismatch")
    rl_path = int_root / "02_power_preprocess/jemena_feeders/jemena_cluster_residual_lookup.csv.gz"
    ql_path = int_root / "02_power_preprocess/jemena_mvar/jemena_q_over_p_lookup.csv.gz"
    rl = pd.read_csv(rl_path)
    ql = pd.read_csv(ql_path)
    residual = {(int(r.cluster_id), int(r.month), str(r.day_type), int(r.slot_30min)): float(r.residual) for r in rl.itertuples()}
    qlookup = {(int(r.month), str(r.day_type), int(r.slot_30min)): float(r.q_variation_factor) for r in ql.itertuples()}
    return StaticSpatial(buses, bp, rel, weighted, cluster, pvcap, residual, qlookup)


def spatial_snapshot(spatial: StaticSpatial, timestamp: pd.Timestamp, gross_kw: float, pv_profile: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, float]]:
    local = timestamp.tz_convert("Australia/Melbourne")
    day_type = "weekday" if local.dayofweek < 5 else "weekend"
    slot = int(local.hour * 2 + local.minute // 30)
    raw = np.empty_like(spatial.base_p)
    for b, c in enumerate(spatial.cluster):
        raw[b, :] = spatial.base_p[b, :] * spatial.residual_lookup[(int(c), int(local.month), day_type, slot)]
    alpha = gross_kw / float(raw.sum())
    p = raw * alpha
    q_raw = p * spatial.relative_qp
    q_target = gross_kw * spatial.weighted_qp * spatial.q_lookup[(int(local.month), day_type, slot)]
    q = q_raw * (q_target / float(q_raw.sum()))
    pv = spatial.pv_capacity * pv_profile
    return p, q, pv, {
        "background_p_conservation_kw": abs(float(p.sum()) - gross_kw),
        "background_q_conservation_kvar": abs(float(q.sum()) - q_target),
        "pv_conservation_kw": abs(float(pv.sum()) - float(spatial.pv_capacity.sum()) * pv_profile),
    }


def select_snapshots(frame: pd.DataFrame) -> list[dict[str, Any]]:
    used: set[pd.Timestamp] = set()
    selected: list[tuple[str, pd.Timestamp]] = []

    def take(name: str, ordered: pd.Series | pd.Index) -> None:
        for t in list(ordered):
            ts = pd.Timestamp(t)
            if ts not in used:
                used.add(ts)
                selected.append((name, ts))
                return
        raise RuntimeError(f"no unused timestamp for snapshot rule {name}")

    take("ANNUAL_MAX_NET_LOAD", frame.sort_values(["net_kw"], ascending=[False], kind="mergesort").index)
    take("ANNUAL_MAX_GROSS_LOAD", frame.sort_values(["gross_kw"], ascending=[False], kind="mergesort").index)
    med_net = float(frame["net_kw"].median())
    take("HIGH_PV_LOW_NET", frame[frame["net_kw"] <= med_net].sort_values(["pv_kw"], ascending=[False], kind="mergesort").index)
    low_pv = float(frame["pv_kw"].quantile(0.20))
    take("HIGH_LOAD_LOW_PV", frame[frame["pv_kw"] <= low_pv].sort_values(["net_kw"], ascending=[False], kind="mergesort").index)
    take("MAX_UP_30MIN_RAMP", frame.sort_values(["ramp_30_kw"], ascending=[False], kind="mergesort").index)
    take("MAX_DOWN_30MIN_RAMP", frame.sort_values(["ramp_30_kw"], ascending=[True], kind="mergesort").index)
    take("ANNUAL_MIN_NET_LOAD", frame.sort_values(["net_kw"], ascending=[True], kind="mergesort").index)
    cols = ["net_kw", "gross_kw", "pv_kw", "ramp_30_kw"]
    dist = np.zeros(len(frame), dtype=float)
    for col in cols:
        med = float(frame[col].median())
        iqr = float(frame[col].quantile(0.75) - frame[col].quantile(0.25))
        dist += np.abs(frame[col].to_numpy() - med) / max(iqr, EPS)
    median_order = frame.assign(_distance=dist).sort_values(["_distance"], ascending=[True], kind="mergesort").index
    take("MULTIVARIATE_MEDIAN", median_order)
    seasons = {"SUMMER": [12, 1, 2], "AUTUMN": [3, 4, 5], "WINTER": [6, 7, 8], "SPRING": [9, 10, 11]}
    local_month = frame.index.tz_convert("Australia/Melbourne").month
    for name, months in seasons.items():
        sub = frame[np.isin(local_month, months)]
        q90 = float(sub["net_kw"].quantile(0.90))
        order = sub.assign(_distance=np.abs(sub["net_kw"] - q90)).sort_values(["_distance"], ascending=[True], kind="mergesort").index
        take(f"{name}_NET_Q90", order)
    if len(selected) != 12:
        raise RuntimeError(f"snapshot count {len(selected)} !=12")
    rows = []
    for order, (rule, t) in enumerate(selected, 1):
        r = frame.loc[t]
        rows.append({
            "snapshot_order": order,
            "rule": rule,
            "timestamp_utc": t.isoformat(),
            "timestamp_fixed_aest": t.tz_convert(AEST).isoformat(),
            "regional_totaldemand_mw": float(r.regional_totaldemand_mw),
            "rooftop_pv_mw": float(r.rooftop_pv_mw),
            "operational_net_target_kw": float(r.net_kw),
            "feeder_pv_target_kw": float(r.pv_kw),
            "gross_background_target_kw": float(r.gross_kw),
            "net_ramp_30min_kw": float(r.ramp_30_kw),
        })
    return rows


def dss_cmd(odd: Any, command: str) -> None:
    odd.Text.Command(command)
    number = int(odd.Error.Number() or 0)
    if number:
        raise RuntimeError(f"OpenDSS command failed {command}: {number} {odd.Error.Description()}")


def set_load(odd: Any, name: str, kw: float, kvar: float) -> None:
    if name.lower() not in {str(x).lower() for x in odd.Loads.AllNames()}:
        raise RuntimeError(f"missing Load.{name}")
    odd.Loads.Name(name)
    odd.Loads.kW(float(kw))
    odd.Loads.kvar(float(kvar))


def set_generator(odd: Any, name: str, kw: float, kvar: float) -> None:
    if name.lower() not in {str(x).lower() for x in odd.Generators.AllNames()}:
        raise RuntimeError(f"missing Generator.{name}")
    odd.Generators.Name(name)
    odd.Generators.kW(float(kw))
    odd.Generators.kvar(float(kvar))


def apply_background(
    odd: Any,
    p: np.ndarray,
    q: np.ndarray,
    pv: np.ndarray,
    contract: Path,
    phase_mask_path: Path,
) -> dict[str, float]:
    adapter = json.loads((contract / "opendss_runtime_adapter.json").read_text(encoding="utf-8"))
    mask = np.load(phase_mask_path, allow_pickle=False).astype(bool)
    native_p = np.asarray(adapter["native_bus_p_kw"], dtype=float)
    native_q = np.asarray(adapter["native_bus_q_kvar"], dtype=float)
    recon_p = np.zeros((131, 3), dtype=float)
    recon_q = np.zeros_like(recon_p)
    for row in adapter["loads"]:
        bi = int(row["bus_index"])
        phases = [int(x) for x in row["phases"]]
        target_p = float(p[bi].sum())
        target_q = float(q[bi].sum())
        if abs(native_p[bi]) < 1e-12:
            kw = 0.0
            if abs(target_p) > 1e-8:
                raise RuntimeError(f"nonzero P on zero-native bus {bi}")
        else:
            kw = float(row["base_p_kw"]) * target_p / native_p[bi]
        if abs(native_q[bi]) < 1e-12:
            kvar = 0.0
            if abs(target_q) > 1e-8:
                raise RuntimeError(f"nonzero Q on zero-native bus {bi}")
        else:
            kvar = float(row["base_q_kvar"]) * target_q / native_q[bi]
        set_load(odd, str(row["load_name"]), kw, kvar)
        for ph in phases:
            recon_p[bi, ph - 1] += kw / len(phases)
            recon_q[bi, ph - 1] += kvar / len(phases)
    recon_pv = np.zeros_like(recon_p)
    for row in adapter["pv_generators"]:
        bi, pi = int(row["bus_index"]), int(row["phase_index"])
        set_generator(odd, str(row["generator_name"]), float(pv[bi, pi]), 0.0)
        recon_pv[bi, pi] += float(pv[bi, pi])
    residual = {
        "p_kw": float(np.max(np.abs(recon_p - p))),
        "q_kvar": float(np.max(np.abs(recon_q - q))),
        "pv_kw": float(np.max(np.abs(recon_pv - pv))),
    }
    if residual["p_kw"] > 0.01 + EPS or residual["q_kvar"] > 0.01 + EPS or residual["pv_kw"] > EPS:
        raise RuntimeError(f"OpenDSS adapter reconstruction failed {residual}")
    if np.any(np.abs(p[~mask]) > EPS) or np.any(np.abs(q[~mask]) > EPS) or np.any(np.abs(pv[~mask]) > EPS):
        raise RuntimeError("nonzero source on nonexistent compiled phase")
    return residual


def compile_exact(
    odd: Any,
    assets: Path,
    contract: Path,
    phase_mask_path: Path,
    p: np.ndarray,
    q: np.ndarray,
    pv: np.ndarray,
) -> dict[str, float]:
    odd.Basic.ClearAll()
    dss_cmd(odd, f'Compile "{assets / "IEEE123Master.dss"}"')
    dss_cmd(odd, "MakeBusList")
    if int(odd.Circuit.NumBuses()) != 132:
        raise RuntimeError(f"base bus count {odd.Circuit.NumBuses()} !=132")
    dss_cmd(odd, f'Redirect "{assets / "Generated_ThreePhase_PCC_v3.dss"}"')
    dss_cmd(odd, "MakeBusList")
    dss_cmd(odd, "CalcVoltageBases")
    if int(odd.Circuit.NumBuses()) != 168:
        raise RuntimeError(f"augmented bus count {odd.Circuit.NumBuses()} !=168")
    dss_cmd(odd, f'Redirect "{assets / "Generated_Planning_Line_Ratings_u080.dss"}"')
    dss_cmd(odd, f'Redirect "{contract / "Generated_PhasePV.dss"}"')
    residual = apply_background(odd, p, q, pv, contract, phase_mask_path)
    for i in range(1, 13):
        set_load(odd, f"IDC_IDC{i:02d}", 0.0, 0.0)
    for name in list(odd.Generators.AllNames()):
        if str(name).lower().startswith("mess_dis_"):
            set_generator(odd, str(name), 0.0, 0.0)
    for name in list(odd.Loads.AllNames()):
        if str(name).lower().startswith("mess_chg_"):
            set_load(odd, str(name), 0.0, 0.0)
    return residual


def solve_exact(odd: Any) -> None:
    for command in ["Set Mode=Snapshot", "Set ControlMode=Static", "Set MaxControlIter=100", "Set MaxIterations=100", "Set Tolerance=0.0001"]:
        dss_cmd(odd, command)
    odd.Solution.Solve()
    if int(odd.Error.Number() or 0) != 0 or not bool(odd.Solution.Converged()):
        raise RuntimeError(f"Fresh Exact OpenDSS solve failure: {odd.Error.Number()} {odd.Error.Description()}")


def bus_key(value: str) -> str:
    return str(value).split(".")[0].strip().lower()


def build_electrical_graph(odd: Any) -> tuple[nx.Graph, dict[str, dict[str, Any]]]:
    graph = nx.Graph()
    edge_rows: dict[str, dict[str, Any]] = {}
    for name in odd.Lines.AllNames():
        odd.Lines.Name(name)
        if not bool(odd.CktElement.Enabled()):
            continue
        a, b = bus_key(odd.Lines.Bus1()), bus_key(odd.Lines.Bus2())
        length = float(odd.Lines.Length())
        r = abs(float(odd.Lines.R1()) * length)
        x = abs(float(odd.Lines.X1()) * length)
        z = math.hypot(r, x)
        row = {"element": f"line.{name}".lower(), "bus1": a, "bus2": b, "r_ohm": r, "x_ohm": x, "z_ohm": z, "kind": "line"}
        graph.add_edge(a, b, weight=max(z, 1e-12), **row)
        edge_rows[row["element"]] = row
    for name in odd.Transformers.AllNames():
        if str(name).lower().startswith(("mess_", "idc_")):
            continue
        odd.Transformers.Name(name)
        buses = [bus_key(x) for x in odd.CktElement.BusNames()]
        if len(buses) < 2 or buses[0] == buses[1]:
            continue
        odd.Transformers.Wdg(1)
        kva = float(odd.Transformers.kVA())
        kv = float(odd.Transformers.kV())
        r_pct = abs(float(odd.Transformers.R()))
        x_pct = abs(float(odd.Transformers.Xhl()))
        zbase = (kv * kv * 1000.0 / kva) if kva > 0 else 0.0
        r = r_pct / 100.0 * zbase
        x = x_pct / 100.0 * zbase
        z = math.hypot(r, x)
        row = {"element": f"transformer.{name}".lower(), "bus1": buses[0], "bus2": buses[1], "r_ohm": r, "x_ohm": x, "z_ohm": z, "kind": "transformer"}
        graph.add_edge(buses[0], buses[1], weight=max(z, 1e-12), **row)
        edge_rows[row["element"]] = row
    return graph, edge_rows


def lexicographic_dijkstra_tree(graph: nx.Graph, root: str) -> tuple[dict[str, str | None], dict[str, float]]:
    import heapq

    root = root.lower()
    heap: list[tuple[float, tuple[str, ...], str, str | None]] = [(0.0, (root,), root, None)]
    parent: dict[str, str | None] = {}
    distance: dict[str, float] = {}
    while heap:
        dist, path, node, prev = heapq.heappop(heap)
        if node in distance:
            continue
        distance[node] = dist
        parent[node] = prev
        for nxt in sorted(graph.neighbors(node)):
            if nxt in distance:
                continue
            weight = float(graph.edges[node, nxt]["weight"])
            heapq.heappush(heap, (dist + weight, path + (nxt,), nxt, node))
    return parent, distance


def node_path(parent: dict[str, str | None], node: str) -> list[str]:
    node = node.lower()
    if node not in parent:
        raise RuntimeError(f"electrical host {node} disconnected from source")
    out = []
    while node is not None:
        out.append(node)
        node = parent[node]
    return list(reversed(out))


def path_metrics(graph: nx.Graph, path: list[str]) -> dict[str, Any]:
    r = x = 0.0
    elements = []
    for a, b in zip(path, path[1:]):
        e = graph.edges[a, b]
        r += float(e["r_ohm"])
        x += float(e["x_ohm"])
        elements.append(str(e["element"]).lower())
    return {"r_path_ohm": r, "x_path_ohm": x, "z_path_ohm": math.hypot(r, x), "path_buses": path, "path_elements": elements}


def children_from_parent(parent: dict[str, str | None]) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {k: [] for k in parent}
    for node, p in parent.items():
        if p is not None:
            children.setdefault(p, []).append(node)
    for row in children.values():
        row.sort()
    return children


def descendants(children: dict[str, list[str]], root: str) -> set[str]:
    out: set[str] = set()
    stack = [root.lower()]
    while stack:
        x = stack.pop()
        if x in out:
            continue
        out.add(x)
        stack.extend(children.get(x, []))
    return out


def collect_metrics(odd: Any) -> dict[str, Any]:
    voltages: dict[str, list[float]] = {}
    for bus in odd.Circuit.AllBusNames():
        key = bus_key(bus)
        if key.startswith(("mess_", "idc_")):
            continue
        odd.Circuit.SetActiveBus(bus)
        vals = list(odd.Bus.puVmagAngle())
        nodes = list(odd.Bus.Nodes())
        if len(vals) != 2 * len(nodes):
            raise RuntimeError(f"voltage vector mismatch at {bus}")
        voltages[key] = [float(vals[2 * i]) for i in range(len(nodes))]
    line_loading: dict[str, float] = {}
    for name in odd.Lines.AllNames():
        odd.Lines.Name(name)
        norm = float(odd.Lines.NormAmps())
        vals = list(odd.CktElement.CurrentsMagAng())
        mags = [float(vals[i]) for i in range(0, len(vals), 2)]
        line_loading[f"line.{name}".lower()] = max(mags, default=0.0) / norm if norm > 0 else float("inf")
    tx_loading: dict[str, float] = {}
    for name in odd.Transformers.AllNames():
        odd.Transformers.Name(name)
        odd.Transformers.Wdg(1)
        kva = float(odd.Transformers.kVA())
        vals = [float(x) for x in odd.CktElement.Powers()]
        nc, nt = int(odd.CktElement.NumConductors()), int(odd.CktElement.NumTerminals())
        max_s = 0.0
        for t in range(nt):
            p = q = 0.0
            for c in range(nc):
                k = 2 * (t * nc + c)
                if k + 1 < len(vals):
                    p += vals[k]
                    q += vals[k + 1]
            max_s = max(max_s, math.hypot(p, q))
        tx_loading[f"transformer.{name}".lower()] = max_s / kva if kva > 0 else float("inf")
    losses = list(odd.Circuit.Losses())
    return {
        "voltages": voltages,
        "loading": {**line_loading, **tx_loading},
        "network_loss_kw": float(losses[0]) / 1000.0,
        "global_voltage_deviation_mean": float(np.mean([abs(v - 1.0) for row in voltages.values() for v in row])),
        "global_max_thermal_loading_pu": max([*line_loading.values(), *tx_loading.values()], default=0.0),
    }


def region_metrics(metrics: dict[str, Any], region_buses: set[str], region_elements: set[str]) -> dict[str, float]:
    volts = [v for b, row in metrics["voltages"].items() if b in region_buses for v in row]
    if not volts:
        raise RuntimeError("candidate region has no energized voltage nodes")
    loads = [v for e, v in metrics["loading"].items() if e in region_elements]
    return {
        "voltage_deviation_mean": float(np.mean(np.abs(np.asarray(volts) - 1.0))),
        "voltage_deviation_max": float(np.max(np.abs(np.asarray(volts) - 1.0))),
        "minimum_voltage_margin": float(min(min(v - V_MIN, V_MAX - v) for v in volts)),
        "thermal_max_loading_pu": max(loads, default=0.0),
        "voltage_node_count": len(volts),
        "thermal_element_count": len(loads),
    }


def solve_case(odd: Any, assets: Path, contract: Path, phase_mask_path: Path, arrays: tuple[np.ndarray, np.ndarray, np.ndarray], service: str | None = None, p_kw: float = 0.0, q_kvar: float = 0.0) -> tuple[dict[str, Any], dict[str, float]]:
    residual = compile_exact(odd, assets, contract, phase_mask_path, *arrays)
    if service is not None:
        set_generator(odd, f"MESS_DIS_{service}", max(p_kw, 0.0), max(q_kvar, 0.0))
        set_load(odd, f"MESS_CHG_{service}", max(-p_kw, 0.0), max(-q_kvar, 0.0))
    solve_exact(odd)
    return collect_metrics(odd), residual


def percentile(values: Iterable[float], q: float) -> float:
    a = np.asarray(list(values), dtype=float)
    return float(np.quantile(a, q))


def inventory_raw(root: Path, used: set[Path]) -> dict[str, Any]:
    rows = []
    total_bytes = 0
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        size = p.stat().st_size
        total_bytes += size
        row = {"path": str(p.resolve()), "relative_path": str(p.relative_to(root)), "bytes": size, "used_by_siting": p.resolve() in used}
        if row["used_by_siting"]:
            row["sha256"] = sha256(p)
        rows.append(row)
    return {
        "schema_version": "mobileess.post_stage15.raw_data_inventory.v1",
        "root": str(root.resolve()),
        "file_count": len(rows),
        "total_bytes": total_bytes,
        "sha_policy": "all files inventoried; SHA-256 included for every file actually read by the siting computation",
        "files": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-root", type=Path, required=True)
    ap.add_argument("--preregistration", type=Path, required=True)
    ap.add_argument("--raw-root", type=Path, default=DEFAULT_RAW)
    ap.add_argument("--integrated-root", type=Path, default=DEFAULT_INT)
    ap.add_argument("--p70", type=Path, default=DEFAULT_P70)
    ap.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    ap.add_argument("--service-map", type=Path, default=DEFAULT_SERVICE_MAP)
    ap.add_argument("--transport-axis", type=Path, default=DEFAULT_TRANSPORT_AXIS)
    ap.add_argument("--route-audit", type=Path, default=DEFAULT_ROUTE_AUDIT)
    ap.add_argument("--pv-repair-authority", type=Path, default=DEFAULT_PV_REPAIR_AUTHORITY)
    args = ap.parse_args()

    out = args.output_root.resolve()
    out.mkdir(parents=True, exist_ok=True)
    prereg = json.loads(args.preregistration.read_text(encoding="utf-8"))
    if prereg.get("status") != "FROZEN_BEFORE_SITE_IDENTITY_COMPUTATION":
        raise RuntimeError("siting preregistration is not frozen")
    prereg_sha = sha256(args.preregistration)
    frozen_prereg = out / "FIXED_ESS_SITING_PREREGISTRATION.json"
    if frozen_prereg.resolve() != args.preregistration.resolve():
        frozen_prereg.write_bytes(args.preregistration.read_bytes())

    raw_2024_load = monthly_archives(args.raw_root / "2024 DISPATCHREGIONSUM", 2024)
    raw_2024_pv = monthly_archives(args.raw_root / "2024 ROOFTOP_PV_ACTUAL", 2024)
    idx = pd.date_range("2023-12-31T14:00:00Z", "2024-12-31T14:00:00Z", freq="5min", inclusive="left")
    demand = parse_regionsum(raw_2024_load).reindex(idx)
    if demand.isna().any() or len(demand) != 105408:
        raise RuntimeError(f"2024 TOTALDEMAND coverage failure missing={int(demand.isna().sum())} rows={len(demand)}")
    rooftop_mw, rooftop_quality, pv_cleaning = parse_rooftop(raw_2024_pv, idx, args.pv_repair_authority)
    mapping, raw_2025_lineage = fit_frozen_totaldemand_mapping(args.p70, args.raw_root)
    p70 = args.p70
    spatial = load_static_spatial(args.integrated_root, p70)
    pv_ref_npz = args.integrated_root / "02_power_preprocess/aemo_rooftop/aemo_rooftop_pv_2025_measurement_5min.npz"
    ref = np.load(pv_ref_npz, allow_pickle=False)
    reference_max_mw = float(np.max(ref["power_mw"]))
    pv_profile = rooftop_mw / reference_max_mw
    if not np.isfinite(pv_profile).all() or float(np.max(pv_profile)) > 1.0 + 1e-12:
        raise RuntimeError(f"2024 rooftop profile exceeds frozen physical reference: max={float(np.max(pv_profile))}")
    net_kw = mapping["slope_kw_per_regional_mw"] * demand.to_numpy(dtype=float) + mapping["intercept_kw"]
    if np.any(net_kw < 0):
        raise RuntimeError("negative 2024 feeder operational target")
    pv_kw = pv_profile * float(spatial.pv_capacity.sum())
    gross_kw = net_kw + pv_kw
    frame = pd.DataFrame({
        "regional_totaldemand_mw": demand.to_numpy(dtype=float),
        "rooftop_pv_mw": rooftop_mw,
        "net_kw": net_kw,
        "pv_kw": pv_kw,
        "gross_kw": gross_kw,
    }, index=idx)
    frame["ramp_30_kw"] = frame["net_kw"].diff(6).fillna(0.0)
    snapshots = select_snapshots(frame)

    mapping_csv = args.integrated_root / "06_opendss_3ph/power_side_p4f_hardening_v1/rating_contract_all_transformers/service_node_electrical_mapping_v1.csv"
    adapter = args.integrated_root / "06_opendss_3ph/power_side_p4f_hardening_v1/runtime_adapter_full_scan/opendss_runtime_adapter.json"
    contract = adapter.parent
    candidate_rows = read_csv(args.service_map)
    transport_rows = read_csv(args.transport_axis)
    frozen_mapping_rows = read_csv(mapping_csv)
    by_sid = {r["service_id"]: r for r in candidate_rows}
    by_transport = {r["service_id"]: r for r in transport_rows}
    by_electrical = {r["service_node_id"]: r for r in frozen_mapping_rows}
    if set(by_sid) != set(SERVICES) or set(by_transport) != set(SERVICES) or set(by_electrical) != set(SERVICES):
        raise RuntimeError("24-service candidate authority identity mismatch")
    route_audit = json.loads(args.route_audit.read_text(encoding="utf-8"))
    if route_audit.get("status") != "PASS" or int(route_audit.get("service_nodes", 0)) != 24:
        raise RuntimeError("frozen 24-service route graph authority is not PASS")

    import opendssdirect as odd

    # Electrical topology is frozen before snapshot/candidate ranking.
    dummy_p = np.zeros((131, 3), dtype=float)
    dummy_q = np.zeros_like(dummy_p)
    dummy_pv = np.zeros_like(dummy_p)
    phase_mask_path = p70 / "compiled_bus_phase_mask.npy"
    compile_exact(odd, args.assets, contract, phase_mask_path, dummy_p, dummy_q, dummy_pv)
    graph, edge_rows = build_electrical_graph(odd)
    parent, root_distance = lexicographic_dijkstra_tree(graph, "149")
    children = children_from_parent(parent)
    distances: dict[str, dict[str, Any]] = {}
    regions: dict[str, set[str]] = {}
    region_elements: dict[str, set[str]] = {}
    for sid in SERVICES:
        host = bus_key(by_sid[sid]["upstream_bus"])
        path = node_path(parent, host)
        pm = path_metrics(graph, path)
        region = descendants(children, host)
        elements = set(pm["path_elements"])
        for node in region:
            p = parent.get(node)
            if p is not None:
                elements.add(str(graph.edges[p, node]["element"]).lower())
        lateral = path[1] if len(path) > 1 else path[0]
        distances[sid] = {"service_id": sid, "electrical_host_bus": host, "source_root_bus": "149", "lateral_identity": lateral, **pm}
        regions[sid] = region
        region_elements[sid] = elements

    snapshot_arrays: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    snapshot_conservation = []
    for row in snapshots:
        t = pd.Timestamp(row["timestamp_utc"])
        p, q, pv, cons = spatial_snapshot(spatial, t, row["gross_background_target_kw"], row["feeder_pv_target_kw"] / float(spatial.pv_capacity.sum()))
        if max(cons.values()) > 0.01:
            raise RuntimeError(f"snapshot spatial conservation failure {row['rule']} {cons}")
        snapshot_arrays[row["rule"]] = (p, q, pv)
        snapshot_conservation.append({"rule": row["rule"], **cons})

    base_metrics: dict[str, dict[str, Any]] = {}
    base_residuals = []
    for row in snapshots:
        metric, residual = solve_case(odd, args.assets, contract, phase_mask_path, snapshot_arrays[row["rule"]])
        base_metrics[row["rule"]] = metric
        base_residuals.append({"rule": row["rule"], **residual})

    feasibility = []
    all_generators = {str(x).lower() for x in odd.Generators.AllNames()}
    all_loads = {str(x).lower() for x in odd.Loads.AllNames()}
    all_tx = {str(x).lower() for x in odd.Transformers.AllNames()}
    for sid in SERVICES:
        m = by_sid[sid]
        checks = {
            "service_map_exists": sid in by_sid,
            "transport_axis_exists": sid in by_transport,
            "electrical_mapping_exists": sid in by_electrical,
            "host_bus_energized": bus_key(m["upstream_bus"]) in parent,
            "mess_transformer_exists": m["transformer"].lower() in all_tx,
            "mess_generator_exists": f"mess_dis_{sid}".lower() in all_generators,
            "mess_charge_load_exists": f"mess_chg_{sid}".lower() in all_loads,
            "three_phase_pcc_kva_750": abs(float(m["kva_limit"]) - 750.0) <= EPS,
            "base_snapshots_converged": len(base_metrics) == 12,
            "route_graph_24service_pass": True,
        }
        feasibility.append({"service_id": sid, "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks})
    feasible = [r["service_id"] for r in feasibility if r["status"] == "PASS"]
    if len(feasible) < 4:
        raise RuntimeError(f"fewer than four feasible PCCs: {feasible}")

    vulnerability: dict[str, dict[str, Any]] = {}
    for sid in feasible:
        per_snapshot = []
        all_devs = []
        all_margins = []
        all_loads = []
        for row in snapshots:
            rm = region_metrics(base_metrics[row["rule"]], regions[sid], region_elements[sid])
            per_snapshot.append({"rule": row["rule"], **rm})
            all_devs.extend([abs(v - 1.0) for b, vals in base_metrics[row["rule"]]["voltages"].items() if b in regions[sid] for v in vals])
            all_margins.extend([min(v - V_MIN, V_MAX - v) for b, vals in base_metrics[row["rule"]]["voltages"].items() if b in regions[sid] for v in vals])
            all_loads.append(rm["thermal_max_loading_pu"])
        vulnerability[sid] = {
            "service_id": sid,
            "voltage_deviation_p95": percentile(all_devs, 0.95),
            "minimum_voltage_margin": min(all_margins),
            "thermal_loading_p95": percentile(all_loads, 0.95),
            "local_downstream_loading_risk": percentile([r["thermal_max_loading_pu"] for r in per_snapshot], 0.95),
            "per_snapshot": per_snapshot,
        }

    sensitivities: dict[str, dict[str, Any]] = {}
    for sid in feasible:
        cases = []
        for row in snapshots:
            rule = row["rule"]
            base = base_metrics[rule]
            base_region = region_metrics(base, regions[sid], region_elements[sid])
            solved = {}
            for label, p_kw, q_kvar in [
                ("PLUS_P", DELTA_P_KW, 0.0),
                ("MINUS_P", -DELTA_P_KW, 0.0),
                ("PLUS_Q", 0.0, DELTA_Q_KVAR),
                ("MINUS_Q", 0.0, -DELTA_Q_KVAR),
            ]:
                metric, _ = solve_case(odd, args.assets, contract, phase_mask_path, snapshot_arrays[rule], sid, p_kw, q_kvar)
                solved[label] = {"global": metric, "region": region_metrics(metric, regions[sid], region_elements[sid])}
            plus_p = solved["PLUS_P"]
            minus_p = solved["MINUS_P"]
            plus_q = solved["PLUS_Q"]
            minus_q = solved["MINUS_Q"]
            cases.append({
                "rule": rule,
                "base_region_voltage_deviation_mean": base_region["voltage_deviation_mean"],
                "plus_p_region_voltage_improvement": base_region["voltage_deviation_mean"] - plus_p["region"]["voltage_deviation_mean"],
                "plus_q_region_voltage_improvement": base_region["voltage_deviation_mean"] - plus_q["region"]["voltage_deviation_mean"],
                "plus_p_global_voltage_improvement": base["global_voltage_deviation_mean"] - plus_p["global"]["global_voltage_deviation_mean"],
                "plus_q_global_voltage_improvement": base["global_voltage_deviation_mean"] - plus_q["global"]["global_voltage_deviation_mean"],
                "plus_p_global_thermal_change": plus_p["global"]["global_max_thermal_loading_pu"] - base["global_max_thermal_loading_pu"],
                "plus_q_global_thermal_change": plus_q["global"]["global_max_thermal_loading_pu"] - base["global_max_thermal_loading_pu"],
                "d_region_voltage_deviation_dP": (plus_p["region"]["voltage_deviation_mean"] - minus_p["region"]["voltage_deviation_mean"]) / (2.0 * DELTA_P_KW),
                "d_region_voltage_deviation_dQ": (plus_q["region"]["voltage_deviation_mean"] - minus_q["region"]["voltage_deviation_mean"]) / (2.0 * DELTA_Q_KVAR),
                "d_network_loss_kw_dP": (plus_p["global"]["network_loss_kw"] - minus_p["global"]["network_loss_kw"]) / (2.0 * DELTA_P_KW),
                "d_network_loss_kw_dQ": (plus_q["global"]["network_loss_kw"] - minus_q["global"]["network_loss_kw"]) / (2.0 * DELTA_Q_KVAR),
            })
        p_region = float(np.mean([x["plus_p_region_voltage_improvement"] for x in cases]))
        q_region = float(np.mean([x["plus_q_region_voltage_improvement"] for x in cases]))
        p_global = float(np.mean([x["plus_p_global_voltage_improvement"] for x in cases]))
        q_global = float(np.mean([x["plus_q_global_voltage_improvement"] for x in cases]))
        p_thermal = float(np.mean([x["plus_p_global_thermal_change"] for x in cases]))
        q_thermal = float(np.mean([x["plus_q_global_thermal_change"] for x in cases]))
        p_pass = p_region > EPS and p_global >= -EPS and p_thermal <= EPS
        q_pass = q_region > EPS and q_global >= -EPS and q_thermal <= EPS
        sensitivities[sid] = {
            "service_id": sid,
            "plus_p_mean_region_voltage_improvement": p_region,
            "plus_q_mean_region_voltage_improvement": q_region,
            "plus_p_mean_global_voltage_improvement": p_global,
            "plus_q_mean_global_voltage_improvement": q_global,
            "plus_p_mean_global_thermal_change": p_thermal,
            "plus_q_mean_global_thermal_change": q_thermal,
            "positive_support_pass": bool(p_pass or q_pass),
            "positive_support_mode": "PLUS_P" if p_pass and (not q_pass or p_region >= q_region) else ("PLUS_Q" if q_pass else "NONE"),
            "per_snapshot": cases,
        }

    # Frozen staged selection.  No weighted sum is formed.
    z_median = float(np.median([distances[s]["z_path_ohm"] for s in feasible]))
    peripheral = [s for s in feasible if distances[s]["z_path_ohm"] + EPS >= z_median]
    vulnerability_order = sorted(
        peripheral,
        key=lambda s: (
            vulnerability[s]["minimum_voltage_margin"],
            -vulnerability[s]["voltage_deviation_p95"],
            -vulnerability[s]["local_downstream_loading_risk"],
            s,
        ),
    )
    vulnerability_rank = {s: i + 1 for i, s in enumerate(vulnerability_order)}
    screened = vulnerability_order[:8]
    support_eligible = [s for s in screened if sensitivities[s]["positive_support_pass"]]
    if len(support_eligible) < 4:
        raise RuntimeError(f"siting preregistration fails closed: positive support eligible={support_eligible}")
    support_order = sorted(
        support_eligible,
        key=lambda s: (
            -max(sensitivities[s]["plus_p_mean_region_voltage_improvement"], sensitivities[s]["plus_q_mean_region_voltage_improvement"]),
            -max(sensitivities[s]["plus_p_mean_global_voltage_improvement"], sensitivities[s]["plus_q_mean_global_voltage_improvement"]),
            s,
        ),
    )
    support_rank = {s: i + 1 for i, s in enumerate(support_order)}

    def pair_tree_metrics(a: str, b: str) -> tuple[float, float]:
        pa = distances[a]["path_buses"]
        pb = distances[b]["path_buses"]
        common = []
        for xa, xb in zip(pa, pb):
            if xa != xb:
                break
            common.append(xa)
        common_z = path_metrics(graph, common)["z_path_ohm"] if len(common) > 1 else 0.0
        za, zb = distances[a]["z_path_ohm"], distances[b]["z_path_ohm"]
        tree_z = za + zb - 2.0 * common_z
        overlap = common_z / max(min(za, zb), EPS)
        return tree_z, overlap

    combo_rows = []
    for combo in itertools.combinations(sorted(support_eligible), 4):
        pairs = [pair_tree_metrics(a, b) for a, b in itertools.combinations(combo, 2)]
        combo_rows.append({
            "sites": list(combo),
            "minimum_pairwise_tree_z_ohm": min(x[0] for x in pairs),
            "maximum_common_path_overlap_ratio": max(x[1] for x in pairs),
            "sorted_vulnerability_ranks": sorted(vulnerability_rank[s] for s in combo),
            "sorted_support_ranks": sorted(support_rank[s] for s in combo),
            "sorted_source_z_desc": sorted([distances[s]["z_path_ohm"] for s in combo], reverse=True),
        })
    combo_rows.sort(
        key=lambda r: (
            -r["minimum_pairwise_tree_z_ohm"],
            r["maximum_common_path_overlap_ratio"],
            tuple(r["sorted_vulnerability_ranks"]),
            tuple(r["sorted_support_ranks"]),
            tuple(-x for x in r["sorted_source_z_desc"]),
            tuple(r["sites"]),
        )
    )
    winner = combo_rows[0]
    selected = sorted(
        winner["sites"],
        key=lambda s: (vulnerability_rank[s], support_rank[s], -distances[s]["z_path_ohm"], s),
    )
    assignment = {f"MESS{i + 1:02d}": sid for i, sid in enumerate(selected)}

    used_raw = {p.resolve() for p in [*raw_2024_load, *raw_2024_pv, *raw_2025_lineage]}
    write_json(out / "RAW_DATA_INVENTORY.json", inventory_raw(args.raw_root, used_raw))
    source_files = []
    source_files.extend(source_row(p, "2024 VIC1 DISPATCHREGIONSUM.TOTALDEMAND", raw_2024=True) for p in raw_2024_load)
    source_files.extend(source_row(p, "2024 VIC1 ROOFTOP_PV_ACTUAL", raw_2024=True) for p in raw_2024_pv)
    source_files.extend(source_row(p, "pre-existing frozen TOTALDEMAND-to-feeder transform reproduction only", raw_2024=False) for p in raw_2025_lineage)
    for p, role in [
        (args.assets / "IEEE123Master.dss", "frozen exact IEEE-123 master"),
        (args.assets / "IEEE123Loads.DSS", "frozen exact IEEE-123 native loads"),
        (args.assets / "IEEELineCodes.DSS", "frozen exact IEEE-123 line impedance codes"),
        (args.assets / "Generated_ThreePhase_PCC_v3.dss", "frozen 24-service PCC definitions"),
        (args.assets / "Generated_Planning_Line_Ratings_u080.dss", "frozen line ratings"),
        (mapping_csv, "frozen service-electrical mapping"),
        (args.service_map, "frozen BUILD7 service/traffic/electrical mapping"),
        (args.transport_axis, "frozen BUILD7 transport/electrical axis"),
        (args.route_audit, "frozen 24-service route graph PASS"),
        (args.pv_repair_authority, "accepted PR3 rooftop-PV defect and repair authority"),
        (adapter, "frozen OpenDSS load/PV runtime adapter"),
        (contract / "Generated_PhasePV.dss", "frozen phase-resolved PV elements"),
        (p70 / "compiled_bus_phase_mask.npy", "frozen compiled bus-phase mask"),
        (p70 / "bus_ids.npy", "frozen power bus axis"),
        (p70 / "native_load_phase_mask.npy", "frozen native-load phase mask"),
        (p70 / "load_archetype_cluster_id.npy", "frozen bus archetype assignment"),
        (p70 / "pv_capacity_kw.npy", "frozen 698-kW feeder PV placement"),
        (pv_ref_npz, "frozen rooftop-PV normalization reference"),
        (args.integrated_root / "02_power_preprocess/jemena_feeders/jemena_cluster_residual_lookup.csv.gz", "frozen calendar feeder diversity lookup"),
        (args.integrated_root / "02_power_preprocess/jemena_mvar/jemena_q_over_p_lookup.csv.gz", "frozen calendar Q/P lookup"),
        (args.integrated_root / "06_opendss_3ph/electrical_zones/native_load_phase_manifest.csv.gz", "frozen IEEE-123 native spatial allocation"),
        (p70 / "operational_net_target_total_kw.npy", "frozen feeder operational-net target used to reproduce the pre-existing scaling transform"),
        (p70 / "time_index_utc_ns.npy", "frozen transform time-axis verification"),
    ]:
        source_files.append(source_row(p, role))
    write_json(out / "SITING_SOURCE_MANIFEST.json", {
        "schema_version": "mobileess.post_stage15.siting_source_manifest.v1",
        "status": "PASS",
        "preregistration_sha256": prereg_sha,
        "2024_controller_campaign_run": False,
        "2025_controller_outcomes_used": False,
        "files": source_files,
        "frozen_totaldemand_transform": mapping,
        "rooftop_cleaning_2024": pv_cleaning,
    })
    candidate_authority = []
    for sid in SERVICES:
        candidate_authority.append({
            "service_id": sid,
            "type": by_sid[sid]["service_type"],
            "transport_node": by_sid[sid]["traffic_node"],
            "ieee123_electrical_host_bus": by_sid[sid]["upstream_bus"],
            "pcc_bus": by_sid[sid]["pcc_bus"],
            "transformer": by_sid[sid]["transformer"],
            "phase_mapping": "three-phase .1.2.3, 4.16-kV host to 0.48-kV wye PCC",
            "transformer_kva": float(by_sid[sid]["kva_limit"]),
            "road_route_graph_connected": True,
            "source_paths": [str(args.service_map.resolve()), str(args.transport_axis.resolve()), str(mapping_csv.resolve())],
        })
    write_json(out / "SERVICE_PCC_CANDIDATE_AUTHORITY.json", {"status": "PASS_EXACT_24", "candidate_count": 24, "candidates": candidate_authority})
    write_json(out / "SITING_FEASIBILITY_SCREEN.json", {"status": "PASS" if len(feasible) == 24 else "PASS_WITH_EXCLUSIONS", "feasible_count": len(feasible), "candidates": feasibility})
    write_json(out / "ELECTRICAL_DISTANCE_AUDIT.json", {"status": "PASS", "source_root": "149", "path_rule": "deterministic lexicographic shortest accumulated |Z| on energized exact topology", "candidates": [distances[s] for s in SERVICES], "topology_edges": list(edge_rows.values())})
    write_json(out / "SITING_2024_SNAPSHOT_AUTHORITY.json", {
        "status": "PASS_12_OUTCOME_BLIND_SNAPSHOTS",
        "preregistration_sha256": prereg_sha,
        "snapshot_count": len(snapshots),
        "snapshots": snapshots,
        "spatial_conservation": snapshot_conservation,
        "opendss_adapter_residuals": base_residuals,
        "rooftop_cleaning": pv_cleaning,
    })
    write_json(out / "BASE_GRID_VULNERABILITY_2024.json", {"status": "PASS", "base_grid_has_controller_ess_dispatch": False, "candidates": [vulnerability[s] for s in feasible]})
    write_json(out / "ESS_PQ_SUPPORT_SENSITIVITY_2024.json", {"status": "PASS", "delta_p_kw": DELTA_P_KW, "delta_q_kvar": DELTA_Q_KVAR, "dispatch_optimized": False, "candidates": [sensitivities[s] for s in feasible]})
    write_json(out / "SITING_TRANSPORT_FEASIBILITY.json", {
        "status": "PASS",
        "route_graph_audit_sha256": sha256(args.route_audit),
        "route_graph_audit": route_audit,
        "candidates": [{"service_id": s, "transport_node": by_transport[s]["traffic_node"], "connected": True} for s in SERVICES],
    })
    write_json(out / "FOUR_SITE_ELECTRICAL_DISPERSION_AUDIT.json", {
        "status": "PASS",
        "eligible_sites": support_eligible,
        "evaluated_combination_count": len(combo_rows),
        "winner": winner,
        "selected_sites_in_assignment_order": selected,
        "pairwise": [
            {"site_a": a, "site_b": b, "electrical_tree_z_ohm": pair_tree_metrics(a, b)[0], "common_path_overlap_ratio": pair_tree_metrics(a, b)[1]}
            for a, b in itertools.combinations(selected, 2)
        ],
        "candidate_combination_trace": combo_rows,
    })
    final_sites = []
    for mid, sid in assignment.items():
        final_sites.append({
            "mess_id": mid,
            "service_id": sid,
            "service_type": by_sid[sid]["service_type"],
            "ieee123_electrical_host_bus": by_sid[sid]["upstream_bus"],
            "transport_node": by_sid[sid]["traffic_node"],
            "lateral_identity": distances[sid]["lateral_identity"],
            "electrical_distance": distances[sid],
            "vulnerability_2024": {k: v for k, v in vulnerability[sid].items() if k != "per_snapshot"},
            "pq_support_2024": {k: v for k, v in sensitivities[sid].items() if k != "per_snapshot"},
            "vulnerability_rank_within_peripheral": vulnerability_rank[sid],
            "support_rank_within_eligible": support_rank[sid],
            "transport_feasible": True,
        })
    write_json(out / "FIXED_ESS_FINAL_SITE_AUTHORITY.json", {
        "schema_version": "mobileess.post_stage15.fixed_ess_final_site_authority.v1",
        "status": "PASS_EXACTLY_FOUR_SITES",
        "preregistration_sha256": prereg_sha,
        "selection_trace": {
            "feasible": feasible,
            "median_source_path_z_ohm": z_median,
            "peripheral": peripheral,
            "vulnerability_top8": screened,
            "positive_support_eligible": support_eligible,
            "winning_combination": winner,
        },
        "assignment": assignment,
        "sites": final_sites,
        "outcome_blind_declarations": {
            "2025_controller_outcome_used": False,
            "W02_outcome_used": False,
            "post_result_optimization": False,
            "random_selection": False,
            "manual_favorable_override": False,
        },
        "scientific_term": "outcome-blind electrically peripheral, grid-support-relevant staging PCCs",
        "globally_optimal_stationary_siting_claimed": False,
        "full_12_week_campaign_authorized": False,
    })
    print(json.dumps({"status": "PASS", "selected_assignment": assignment, "output_root": str(out), "preregistration_sha256": prereg_sha}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
