"""First authorized May/June input release under the committed V16.3 protocol."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import shutil
import tempfile
import zipfile
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from .aidc_ml_backend import HPOCandidate, build_transformer, set_deterministic_seed
from .aidc_ml_data import AEST, NODE_CLASSES, _add_interval_average, _find_exact, _h100, _load_esif, calendar_features
from .authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from .final_science_protocol_v16_3 import EVALUATION_PERIODS
from .reproduce_nlr_authority import object_empty


FIXED_AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
LOOKBACK = 1344
QUANTILES = (0.1, 0.5, 0.9)
FORECAST_NAMESPACE = "V16_3_FINAL_OUT_OF_SAMPLE"
MODEL_NAME = "Proposed AIDC RC-MQT"


def _dt(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y/%m/%d %H:%M:%S").replace(tzinfo=FIXED_AEST)


def _archive_rows(path: Path) -> Iterable[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
        if len(members) != 1:
            raise RuntimeError(f"FINAL_AEMO_MEMBER_COUNT_NOT_ONE:{path.name}")
        with archive.open(members[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            header: list[str] | None = None
            for row in reader:
                if row and row[0] == "I":
                    header = row
                elif row and row[0] == "D" and header is not None:
                    yield dict(zip(header, row, strict=False))


def _candidate_days() -> dict[str, tuple[str, ...]]:
    result = {}
    for period, bounds in EVALUATION_PERIODS.items():
        start = date.fromisoformat(bounds["start"])
        end = date.fromisoformat(bounds["end"])
        result[period] = tuple((start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1))
    return result


def _target_day(timestamp: datetime) -> str:
    # AEMO target axes end at 00:00 of the following day.
    return (timestamp - timedelta(seconds=1)).date().isoformat()


def select_month_vintages(
    *, demand_path: Path, pv_path: Path, days: Sequence[str], expected_shas: Mapping[str, str]
) -> tuple[dict[str, dict[str, object]], dict[str, list[str]]]:
    if sha256_file(demand_path) != expected_shas["demand"] or sha256_file(pv_path) != expected_shas["pv"]:
        raise RuntimeError("FINAL_AEMO_SOURCE_SHA_DRIFT")
    day_set = set(days)
    targets = {
        day: tuple(
            datetime.combine(date.fromisoformat(day), time.min, FIXED_AEST) + timedelta(minutes=30 * (i + 1))
            for i in range(48)
        )
        for day in days
    }
    target_sets = {day: set(values) for day, values in targets.items()}
    demand_groups: dict[tuple[str, str, str], dict[datetime, tuple[float, datetime]]] = defaultdict(dict)
    for row in _archive_rows(demand_path):
        if row.get("REGIONID") != "VIC1" or not row.get("DATETIME"):
            continue
        target = _dt(row["DATETIME"])
        day = _target_day(target)
        if day not in day_set or target not in target_sets[day]:
            continue
        required = ("PREDISPATCHSEQNO", "RUNNO", "LASTCHANGED", "TOTALDEMAND")
        if any(not row.get(key) for key in required):
            continue
        demand_groups[(day, row["PREDISPATCHSEQNO"], row["RUNNO"])][target] = (
            float(row["TOTALDEMAND"]), _dt(row["LASTCHANGED"])
        )
    pv_groups: dict[tuple[str, str], dict[datetime, float]] = defaultdict(dict)
    for row in _archive_rows(pv_path):
        if row.get("REGIONID") != "VIC1" or not row.get("INTERVAL_DATETIME"):
            continue
        target = _dt(row["INTERVAL_DATETIME"])
        day = _target_day(target)
        if day not in day_set or target not in target_sets[day]:
            continue
        if not row.get("VERSION_DATETIME") or not row.get("POWERMEAN"):
            continue
        pv_groups[(day, row["VERSION_DATETIME"])][target] = float(row["POWERMEAN"])

    selected: dict[str, dict[str, object]] = {}
    failures: dict[str, list[str]] = {}
    for day in days:
        operating = date.fromisoformat(day)
        cutoff = datetime.combine(operating - timedelta(days=1), time(18), FIXED_AEST)
        demand_candidates = []
        for (group_day, seq, run), values in demand_groups.items():
            if group_day != day or set(values) != target_sets[day]:
                continue
            issues = {record[1] for record in values.values()}
            if len(issues) == 1 and next(iter(issues)) <= cutoff:
                demand_candidates.append((next(iter(issues)), (seq, run), values))
        pv_candidates = []
        for (group_day, version), values in pv_groups.items():
            issue = _dt(version)
            if group_day == day and set(values) == target_sets[day] and issue <= cutoff:
                pv_candidates.append((issue, version, values))
        reasons = []
        if not demand_candidates:
            reasons.append("NO_COMPLETE_CAUSAL_AEMO_DEMAND_VINTAGE")
        if not pv_candidates:
            reasons.append("NO_COMPLETE_CAUSAL_AEMO_PV_VINTAGE")
        if reasons:
            failures[day] = reasons
            continue
        d_issue, d_identity, d_values = max(demand_candidates, key=lambda row: (row[0], row[1]))
        p_issue, p_version, p_values = max(pv_candidates, key=lambda row: (row[0], row[1]))
        selected[day] = {
            "demand_mw_96": tuple(value for target in targets[day] for value in (d_values[target][0], d_values[target][0])),
            "pv_mw_96": tuple(value for target in targets[day] for value in (p_values[target], p_values[target])),
            "timestamps_96": tuple(
                (datetime.combine(operating, time.min, FIXED_AEST) + timedelta(minutes=15 * (i + 1))).isoformat()
                for i in range(96)
            ),
            "cutoff_fixed_aest": cutoff.isoformat(),
            "demand_identity": {"PREDISPATCHSEQNO": d_identity[0], "RUNNO": d_identity[1]},
            "demand_issue": d_issue.isoformat(),
            "pv_identity": {"VERSION_DATETIME": p_version},
            "pv_issue": p_issue.isoformat(),
            "demand_source_sha256": expected_shas["demand"],
            "pv_source_sha256": expected_shas["pv"],
        }
    return selected, failures


def _load_kestrel_final(path: Path, timestamps, frozen_bins: Mapping[int, tuple[float, float]]):
    import pandas as pd
    import pyarrow.parquet as pq

    required = {
        "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared",
    }
    retained = []
    opened = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="aidc-final-") as temporary:
        local = Path(temporary) / "month.parquet"
        for info in archive.infolist():
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/"))
            if not info.filename.casefold().endswith(".parquet") or not match:
                continue
            month = int(match.group(1)) * 100 + int(match.group(2))
            if month < 202408 or month > 202506:
                continue
            opened.append(info.filename)
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            schema = set(pq.ParquetFile(local).schema_arrow.names)
            if not required.issubset(schema):
                raise RuntimeError(f"FINAL_KESTREL_SCHEMA_MISSING:{sorted(required-schema)}")
            retained.append(pq.read_table(local, columns=sorted(required)).to_pandas())
    frame = pd.concat(retained, ignore_index=True)
    submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
    start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
    end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
    nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
    gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
    valid = (
        frame["partition"].apply(_h100) & frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
        & submit.notna() & start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0)
    )
    jobs = frame.loc[valid, ["nodes_shared", "jobs_shared"]].copy()
    jobs["submit_utc"] = submit[valid]; jobs["start_utc"] = start[valid]; jobs["end_utc"] = end[valid]
    jobs["nodes"] = nodes[valid]; jobs["gpus"] = gpus[valid]; jobs["share"] = sharing[valid]
    jobs["runtime_hours"] = (jobs["end_utc"] - jobs["start_utc"]).dt.total_seconds() / 3600.0
    no_share = (
        (jobs["share"].isna() | jobs["share"].eq(0))
        & jobs["nodes_shared"].apply(object_empty) & jobs["jobs_shared"].apply(object_empty)
    )
    flexible = jobs.loc[
        jobs["nodes"].isin(NODE_CLASSES) & np.isclose(jobs["gpus"], 4.0 * jobs["nodes"])
        & jobs["runtime_hours"].gt(0) & no_share
    ].copy()
    cohort_ids = tuple(f"N{nodes:02d}_R{runtime_bin:02d}" for nodes in NODE_CLASSES for runtime_bin in range(3))
    cohort_index = {value: index for index, value in enumerate(cohort_ids)}
    origin = timestamps[0].tz_convert("UTC").timestamp()
    difference = np.zeros(len(timestamps) + 1); partial = np.zeros(len(timestamps))
    for row in jobs.itertuples(index=False):
        _add_interval_average(difference, partial, start_seconds=row.start_utc.timestamp()-origin,
                              end_seconds=row.end_utc.timestamp()-origin, magnitude=float(row.gpus)/4.0,
                              slot_count=len(timestamps))
    gpu_nodes = partial + np.cumsum(difference[:-1])
    workload = np.zeros((len(timestamps), len(cohort_ids)))
    for row in flexible.itertuples(index=False):
        slot = int((row.submit_utc.timestamp() - origin) // 900)
        if 0 <= slot < len(timestamps):
            nodes_i = int(row.nodes); q1, q2 = frozen_bins[nodes_i]
            runtime_bin = 0 if float(row.runtime_hours) <= q1 else 1 if float(row.runtime_hours) <= q2 else 2
            workload[slot, cohort_index[f"N{nodes_i:02d}_R{runtime_bin:02d}"]] += nodes_i * float(row.runtime_hours)
    return gpu_nodes, workload, cohort_ids, opened, {"valid_jobs": len(jobs), "eligible_jobs": len(flexible)}


def build_final_forecast(raw_root: Path, repo: Path, days: Sequence[str], cache_path: Path) -> dict[str, object]:
    import pandas as pd
    import torch
    from .aidc_ml_data import AccessAudit

    config = json.loads((repo / "dayahead/artifacts/v16/AIDC_PRODUCTION_CONFIG.json").read_text(encoding="utf-8"))
    cohort = json.loads((repo / "dayahead/artifacts/v16/AIDC_COHORT_CONTRACT.json").read_text(encoding="utf-8"))
    scales = np.asarray([float(config["target_scales"][name]) for name in config["targets"]], dtype=float)
    bins = {int(nodes): (float(row["q33_hours"]), float(row["q67_hours"]))
            for nodes, row in cohort["runtime_bins_hours_by_node_class"].items()}
    axis_end = (date.fromisoformat(max(days)) + timedelta(days=1)).isoformat()
    timestamps = pd.date_range(pd.Timestamp("2024-08-01", tz=AEST), pd.Timestamp(axis_end, tz=AEST),
                               freq="15min", inclusive="left")
    esif = _find_exact(raw_root, "esif.influx.buildingData.PUE.combined.parquet", NLR_SOURCE_SHA256["esif_parquet"])
    kestrel = _find_exact(raw_root, "esif.hpc.kestrel.job-anon.zip", NLR_SOURCE_SHA256["kestrel_jobs_zip"])
    audit_stub = AccessAudit()
    p_it, p_observed = _load_esif(esif, timestamps, audit_stub)
    gpu, workload, cohort_ids, opened, counts = _load_kestrel_final(kestrel, timestamps, bins)
    target_names = ("P_IT_REF", "G_REF", *(f"W_F::{name}" for name in cohort_ids))
    if tuple(config["targets"]) != target_names:
        raise RuntimeError("FINAL_RC_MQT_TARGET_AXIS_DRIFT")
    values = np.column_stack((p_it, gpu, workload))
    scaled = values / scales
    calendar = calendar_features(timestamps)
    features = np.column_stack((scaled, np.asarray(p_observed, dtype=np.float32)[:, None], calendar)).astype(np.float32)
    index = {timestamp: i for i, timestamp in enumerate(timestamps)}
    past = []; future = []; eligible = []; failures = {}
    for day in days:
        start = pd.Timestamp(day, tz=AEST); cutoff = start - pd.Timedelta(hours=6)
        first = index.get(cutoff - pd.Timedelta(minutes=15 * LOOKBACK)); last = index.get(cutoff)
        target = index.get(start)
        reasons = []
        if first is None or last is None or target is None:
            reasons.append("FROZEN_RC_MQT_DIRECT96_INPUT_OR_OUTPUT_INCOMPLETE")
        else:
            x = features[first:last]; f = calendar[target:target+96]
            if x.shape != (LOOKBACK, features.shape[1]) or f.shape != (96, 6) or not np.isfinite(x).all():
                reasons.append("FROZEN_RC_MQT_DIRECT96_INPUT_OR_OUTPUT_INCOMPLETE")
        if reasons:
            failures[day] = reasons
        else:
            eligible.append(day); past.append(x); future.append(f)
    candidate = HPOCandidate(**config["candidate"])
    set_deterministic_seed(int(config["seed"]))
    model = build_transformer(candidate, feature_count=len(config["feature_schema"]),
                              target_count=len(target_names), proposed=True)
    weights_path = repo / "dayahead/artifacts/v16/AIDC_RC_MQT_PRODUCTION_SEED20260828.pt"
    saved = torch.load(weights_path, map_location="cpu", weights_only=False)
    model.load_state_dict(saved["state_dict"], strict=True); model.eval()
    with torch.no_grad():
        prediction = model(torch.as_tensor(np.stack(past)), torch.as_tensor(np.stack(future))).cpu().numpy()
    prediction = prediction * scales[None, None, :, None]
    if prediction.shape != (len(eligible), 96, len(target_names), 3) or not np.isfinite(prediction).all():
        raise RuntimeError("FINAL_RC_MQT_DIRECT96_OUTPUT_INVALID")
    if np.any(prediction[..., 0] > prediction[..., 1]) or np.any(prediction[..., 1] > prediction[..., 2]):
        raise RuntimeError("FINAL_RC_MQT_QUANTILE_ORDER_FAIL")
    rows = [
        {"model": MODEL_NAME, "namespace": FORECAST_NAMESPACE, "forecast_day": day,
         "slot": slot, "target": target, "quantile": quantile, "prediction": float(prediction[d, slot, t, q])}
        for d, day in enumerate(eligible) for slot in range(96) for t, target in enumerate(target_names)
        for q, quantile in enumerate(QUANTILES)
    ]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(cache_path, index=False)
    return {
        "eligible_days": eligible, "failures": failures, "forecast_rows": len(rows),
        "forecast_path": str(cache_path.resolve()), "forecast_sha256": sha256_file(cache_path),
        "weights_sha256": sha256_file(weights_path), "source_sha256": {"esif": sha256_file(esif), "kestrel": sha256_file(kestrel)},
        "access_audit": {"PRIMARY_2025MAY": 1, "REPLICATION_2025JUN01_25": 1,
                         "max_kestrel_month_opened": 202506, "kestrel_members_opened": opened,
                         "d1_expost_eligibility_field_access_count": 0,
                         "esif_returned_max_timestamp": audit_stub.esif_returned_max_timestamp},
        "job_counts": counts,
    }
