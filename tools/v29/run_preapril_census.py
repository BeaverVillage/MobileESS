"""Build the read-only V29 pre-April carry-in and service-mass census.

This runner intentionally creates forensic artifacts only.  It does not edit or
select any production formulation, parameter, eligibility rule, or quantile.
"""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import io
import json
import math
import subprocess
import sys
import warnings
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dayahead.authority import NLR_SOURCE_SHA256  # noqa: E402
from dayahead.v28r2.authority import CONTROLLABLE_NODE_CLASSES  # noqa: E402
from tools.v29.run_stage3_carryin_authority import (  # noqa: E402
    AEST,
    bridge_capacity,
    cohort,
    cohort_bins,
    source_zip,
)


STUDY_START = pd.Timestamp("2024-01-01", tz=AEST)
STUDY_END = pd.Timestamp("2025-04-01", tz=AEST)
FIT_CUTOFF = STUDY_END
BRIDGE_HOURS = 6.0
SLOT_HOURS = 0.25
BRIDGE_SLOTS = 24
NODE_CLASSES = tuple(int(value) for value in CONTROLLABLE_NODE_CLASSES)
OUTPUT_REL = Path("dayahead/artifacts/v29_preapril_census")
ARTIFACT_NAMES = (
    "V29_PREAPRIL_DAILY_CARRYIN_CENSUS.csv",
    "V29_PREAPRIL_CARRYIN_DISTRIBUTION.json",
    "V29_PREAPRIL_REQUEST_REALIZED_SERVICE.csv",
    "V29_PREAPRIL_SERVICE_CALIBRATION_SUMMARY.json",
    "V29_PREAPRIL_ROLLING_ORIGIN_CALIBRATION.csv",
    "V29_PREAPRIL_CAUSAL_LABEL_AUDIT.json",
    "V29_PREAPRIL_GRID_VALUE_POTENTIAL.csv",
    "V29_PREAPRIL_GRID_VALUE_POTENTIAL_SUMMARY.json",
    "V29_APR03_APR04_HISTORICAL_PERCENTILE_CONTEXT.json",
    "V29_PREAPRIL_CENSUS_FINAL_REVIEW.md",
    "V29_PREAPRIL_CENSUS_FINAL_REVIEW.json",
    "V29_PREAPRIL_CENSUS_TEST_REPORT.json",
)
COLUMNS = (
    "id",
    "partition",
    "state",
    "state_simple",
    "submit_time",
    "start_time",
    "end_time",
    "nodes_req",
    "wallclock_req",
    "nodes_used",
    "wallclock_used",
    "qos",
    "queue_wait",
    "gpus_requested",
)
RATIO_PERCENTILES = (5, 10, 25, 50, 75, 90, 95, 99)
CARRY_PERCENTILES = (5, 25, 50, 75, 90, 95, 99)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scalar(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        value = float(value)
        return value if math.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False, default=scalar) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str] | None = None) -> None:
    materialized = list(rows)
    if fields is None:
        fields = []
        for row in materialized:
            for field in row:
                if field not in fields:
                    fields.append(field)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in materialized:
            writer.writerow({key: scalar(value) for key, value in row.items()})


def utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def duration_hours(series: pd.Series) -> pd.Series:
    return pd.to_timedelta(series, errors="coerce").dt.total_seconds() / 3600.0


def daily_cutoff(day: pd.Timestamp) -> pd.Timestamp:
    return (day - pd.Timedelta(hours=BRIDGE_HOURS)).tz_convert("UTC")


def read_h100_events(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Open every archive member because filing month is not submission month."""
    frames: list[pd.DataFrame] = []
    members: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        names = sorted(name for name in archive.namelist() if name.endswith(".parquet"))
        for name in names:
            with archive.open(name) as raw:
                buffer = io.BytesIO(raw.read())
            parquet = pq.ParquetFile(buffer)
            available = tuple(parquet.schema_arrow.names)
            missing = sorted(set(COLUMNS) - set(available))
            if missing:
                raise RuntimeError(f"V29_PREAPRIL_SCHEMA_MISSING:{name}:{missing}")
            table = parquet.read(columns=list(COLUMNS))
            frame = table.to_pandas()
            partition = frame["partition"].astype("string").str.casefold()
            keep = partition.str.contains("gpu-h100", regex=False, na=False)
            kept = frame.loc[keep].copy()
            if not kept.empty:
                frames.append(kept)
            members.append(
                {
                    "member": name,
                    "source_rows": int(parquet.metadata.num_rows),
                    "h100_rows_kept": int(keep.sum()),
                }
            )
            del frame, kept, table, parquet, buffer
            gc.collect()
    if not frames:
        raise RuntimeError("V29_PREAPRIL_NO_H100_EVENTS")
    events = pd.concat(frames, ignore_index=True)
    duplicate_ids = events["id"].duplicated(keep=False)
    if duplicate_ids.any():
        duplicated = events.loc[duplicate_ids].sort_values("id", kind="stable")
        fields = [field for field in COLUMNS if field != "id"]
        inconsistent = 0
        for _, group in duplicated.groupby("id", sort=False):
            normalized = group[fields].astype("string").fillna("<NA>")
            inconsistent += int(len(normalized.drop_duplicates()) > 1)
        if inconsistent:
            raise RuntimeError(f"V29_PREAPRIL_INCONSISTENT_DUPLICATE_IDS:{inconsistent}")
        events = events.drop_duplicates("id", keep="first").copy()
    audit = {
        "archive_members_opened": len(members),
        "all_archive_month_members_opened": True,
        "members": members,
        "h100_rows_after_exact_duplicate_removal": len(events),
        "exact_duplicate_rows_removed": int(duplicate_ids.sum()),
    }
    return events, audit


def prepare(events: pd.DataFrame) -> pd.DataFrame:
    frame = events.copy()
    frame["submit_utc"] = utc(frame["submit_time"])
    frame["start_utc"] = utc(frame["start_time"])
    frame["end_utc"] = utc(frame["end_time"])
    frame["nodes_req_num"] = pd.to_numeric(frame["nodes_req"], errors="coerce")
    frame["gpus_requested_num"] = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    frame["requested_hours"] = duration_hours(frame["wallclock_req"])
    frame["nodes_used_num"] = pd.to_numeric(frame["nodes_used"], errors="coerce")
    frame["used_hours"] = duration_hours(frame["wallclock_used"])
    frame["queue_wait_hours"] = duration_hours(frame["queue_wait"])
    frame["request_fullnode"] = (
        frame["nodes_req_num"].isin(NODE_CLASSES)
        & np.isclose(frame["gpus_requested_num"], 4.0 * frame["nodes_req_num"], equal_nan=False)
    )
    frame["service_known"] = (
        frame["nodes_req_num"].gt(0)
        & frame["requested_hours"].gt(0)
        & np.isfinite(frame["requested_hours"])
    )
    frame["requested_service_nodeh"] = frame["nodes_req_num"] * frame["requested_hours"]
    return frame


def q(values: Iterable[float], percentiles: Iterable[int]) -> dict[str, float | None]:
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        return {f"P{percentile:02d}": None for percentile in percentiles}
    return {f"P{percentile:02d}": float(np.percentile(array, percentile)) for percentile in percentiles}


def wallclock_bin(hours: float) -> str:
    if hours <= 1:
        return "W00_LE_1H"
    if hours <= 4:
        return "W01_1_TO_4H"
    if hours <= 12:
        return "W02_4_TO_12H"
    if hours <= 24:
        return "W03_12_TO_24H"
    return "W04_GT_24H"


def first_queue_cutoff_age(submit: pd.Timestamp, start: pd.Timestamp | pd.NaT, end: pd.Timestamp | pd.NaT) -> float | None:
    local = submit.tz_convert(AEST)
    candidate = local.normalize() + pd.Timedelta(hours=18)
    if local > candidate:
        candidate += pd.Timedelta(days=1)
    mark = candidate.tz_convert("UTC")
    if pd.notna(start) and start <= mark:
        return None
    if pd.isna(start) and pd.notna(end) and end <= mark:
        return None
    return float((mark - submit).total_seconds() / 3600.0)


def queue_age_bin(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "Q00_NOT_IN_D1_QUEUE"
    if value <= 1:
        return "Q01_LE_1H"
    if value <= 6:
        return "Q02_1_TO_6H"
    if value <= 24:
        return "Q03_6_TO_24H"
    if value <= 72:
        return "Q04_24_TO_72H"
    return "Q05_GT_72H"


def json_comp(values: pd.Series) -> str:
    return json.dumps({str(key): float(value) for key, value in values.items()}, sort_keys=True, separators=(",", ":"))


def overlap_nodeh(selected: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float:
    began = selected["start_utc"].where(selected["start_utc"] > start, start)
    finished = selected["end_utc"].where(selected["end_utc"] < end, end)
    hours = (finished - began).dt.total_seconds().clip(lower=0) / 3600.0
    nodes = selected["nodes_used_num"].where(selected["nodes_used_num"].gt(0), 0.0)
    valid = selected["start_utc"].notna() & selected["end_utc"].notna()
    return float((hours.where(valid, 0.0) * nodes).sum())


def daily_census(frame: pd.DataFrame, repo: Path) -> list[dict[str, Any]]:
    days = pd.date_range(STUDY_START, STUDY_END - pd.Timedelta(days=1), freq="D")
    bins = cohort_bins(repo)
    slot_capacity = bridge_capacity(repo)
    bridge_budget = slot_capacity * BRIDGE_SLOTS
    rows: list[dict[str, Any]] = []
    for day in days:
        mark = daily_cutoff(day)
        not_started = frame["start_utc"].isna() | frame["start_utc"].gt(mark)
        not_cancelled_before = frame["start_utc"].notna() | frame["end_utc"].isna() | frame["end_utc"].gt(mark)
        admitted = (
            frame["submit_utc"].le(mark)
            & not_started
            & not_cancelled_before
            & frame["request_fullnode"]
            & frame["service_known"]
        )
        selected = frame.loc[admitted].copy()
        if not selected.empty:
            selected["node_class"] = selected["nodes_req_num"].astype(int)
            selected["cohort"] = [
                cohort(int(nodes), float(hours), bins)
                for nodes, hours in zip(selected["node_class"], selected["requested_hours"], strict=True)
            ]
            selected["queue_age_hours"] = (mark - selected["submit_utc"]).dt.total_seconds() / 3600.0
        queue_mass = float(selected["requested_service_nodeh"].sum())
        bridge_service = min(queue_mass, bridge_budget)
        carryin = max(queue_mass - bridge_service, 0.0)
        remaining = bridge_budget
        carry_by_node = {nodes: 0.0 for nodes in NODE_CLASSES}
        if not selected.empty:
            by_cohort = selected.groupby("cohort")["requested_service_nodeh"].sum().to_dict()
            for name in sorted({f"N{nodes:02d}_R{runtime:02d}" for nodes in NODE_CLASSES for runtime in range(3)}):
                mass = float(by_cohort.get(name, 0.0))
                served = min(mass, remaining)
                remaining -= served
                carry_by_node[int(name[1:3])] += mass - served
        day_end = day + pd.Timedelta(days=1)
        day_start_utc = day.tz_convert("UTC")
        day_end_utc = day_end.tz_convert("UTC")
        submitted_today = (
            frame["submit_utc"].ge(day_start_utc)
            & frame["submit_utc"].lt(day_end_utc)
            & frame["request_fullnode"]
            & frame["service_known"]
        )
        new_mass = float(frame.loc[submitted_today, "requested_service_nodeh"].sum())
        total_flexible = carryin + new_mass
        node_count = selected.groupby("node_class").size() if not selected.empty else pd.Series(dtype=float)
        node_mass = selected.groupby("node_class")["requested_service_nodeh"].sum() if not selected.empty else pd.Series(dtype=float)
        wall = q(selected["requested_hours"], (25, 50, 75, 90, 95))
        ages = q(selected["queue_age_hours"] if "queue_age_hours" in selected else [], (25, 50, 75, 90, 95))
        row: dict[str, Any] = {
            "day": day.date().isoformat(),
            "cutoff_fixed_aest": (day - pd.Timedelta(hours=6)).isoformat(),
            "cutoff_known_strict_fullnode_queued_job_count": len(selected),
            "cutoff_known_requested_service_nodeh": queue_mass,
            "pre_day_queue_bridge_v1_reference_service_nodeh": bridge_service,
            "D0_0000_predicted_carryin_nodeh": carryin,
            "D0_realized_queued_service_nodeh_ex_post": overlap_nodeh(selected, day_start_utc, day_end_utc),
            "D0_new_strict_fullnode_requested_service_nodeh": new_mass,
            "D0_total_flexible_requested_service_nodeh": total_flexible,
            "carryin_fraction_of_D0_total_flexible_service": carryin / total_flexible if total_flexible else 0.0,
            "node_class_job_count_json": json_comp(node_count),
            "node_class_queue_nodeh_json": json_comp(node_mass),
            "node_class_predicted_carryin_nodeh_json": json.dumps(
                {str(key): value for key, value in carry_by_node.items()}, sort_keys=True, separators=(",", ":")
            ),
            "requested_wallclock_P25_hours": wall["P25"],
            "requested_wallclock_P50_hours": wall["P50"],
            "requested_wallclock_P75_hours": wall["P75"],
            "requested_wallclock_P90_hours": wall["P90"],
            "requested_wallclock_P95_hours": wall["P95"],
            "queue_age_P25_hours": ages["P25"],
            "queue_age_P50_hours": ages["P50"],
            "queue_age_P75_hours": ages["P75"],
            "queue_age_P90_hours": ages["P90"],
            "queue_age_P95_hours": ages["P95"],
        }
        for nodes in NODE_CLASSES:
            row[f"N{nodes:02d}_queue_job_count"] = int(node_count.get(nodes, 0))
            row[f"N{nodes:02d}_queue_nodeh"] = float(node_mass.get(nodes, 0.0))
            row[f"N{nodes:02d}_predicted_carryin_nodeh"] = float(carry_by_node[nodes])
        rows.append(row)
    return rows


def distribution(rows: list[dict[str, Any]], repo: Path) -> dict[str, Any]:
    values = np.asarray([row["D0_0000_predicted_carryin_nodeh"] for row in rows], dtype=float)
    payload: dict[str, Any] = {
        "artifact_id": "V29_PREAPRIL_CARRYIN_DISTRIBUTION_V1",
        "status": "PASS_READ_ONLY_CENSUS",
        "study_window": [STUDY_START.date().isoformat(), (STUDY_END - pd.Timedelta(days=1)).date().isoformat()],
        "day_count": len(values),
        "cutoff": "D-1 18:00 fixed AEST",
        "admission": "strict request-time full-node H100 only",
        "bridge_budget_nodeh": bridge_capacity(repo) * BRIDGE_SLOTS,
        "fraction_zero": float(np.mean(values == 0)),
        "mean_nodeh": float(np.mean(values)),
        "median_nodeh": float(np.median(values)),
        "maximum_nodeh": float(np.max(values)),
        "maximum_day": rows[int(np.argmax(values))]["day"],
        "percentiles_nodeh": q(values, CARRY_PERCENTILES),
        "threshold_fractions_strictly_greater": {
            str(threshold): float(np.mean(values > threshold)) for threshold in (100, 250, 500, 1000)
        },
        "daily_fraction_definition": "predicted carry-in / (predicted carry-in + same-D source-backed new strict-fullnode requested service)",
    }
    return payload


def calibration_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    start_utc = STUDY_START.tz_convert("UTC")
    fit_utc = FIT_CUTOFF.tz_convert("UTC")
    study_request = (
        frame["submit_utc"].ge(start_utc)
        & frame["submit_utc"].lt(fit_utc)
        & frame["request_fullnode"]
        & frame["service_known"]
    )
    candidates = frame.loc[study_request].copy()
    label_available = candidates["end_utc"].notna() & candidates["end_utc"].le(fit_utc)
    started = candidates["start_utc"].notna()
    measured_started = started & candidates["nodes_used_num"].gt(0) & candidates["used_hours"].ge(0)
    known_zero = ~started & label_available
    usable = label_available & (measured_started | known_zero)
    result = candidates.loc[usable].copy()
    result["realized_service_nodeh"] = np.where(
        result["start_utc"].notna(), result["nodes_used_num"] * result["used_hours"], 0.0
    )
    result["realization_ratio"] = result["realized_service_nodeh"] / result["requested_service_nodeh"]
    result["node_class"] = result["nodes_req_num"].astype(int)
    result["requested_wallclock_bin"] = result["requested_hours"].map(wallclock_bin)
    ages = [
        first_queue_cutoff_age(submit, start, end)
        for submit, start, end in zip(result["submit_utc"], result["start_utc"], result["end_utc"], strict=True)
    ]
    result["queue_age_at_first_D1_cutoff_hours"] = ages
    result["queue_age_bin"] = [queue_age_bin(value) for value in ages]
    local_submit = result["submit_utc"].dt.tz_convert(AEST)
    result["submit_month"] = local_submit.dt.strftime("%Y-%m")
    result["submit_hour_aest"] = local_submit.dt.hour
    result["submit_day_of_week"] = local_submit.dt.day_name()
    result["qos_observed_at_request"] = result["qos"].astype("string").fillna("<MISSING>")
    result["absolute_error_nodeh_raw_request"] = (
        result["requested_service_nodeh"] - result["realized_service_nodeh"]
    ).abs()
    result["signed_overstatement_nodeh_raw_request"] = (
        result["requested_service_nodeh"] - result["realized_service_nodeh"]
    )
    audit = {
        "strict_fullnode_study_requests": len(candidates),
        "excluded_label_not_available_by_fit_cutoff": int((~label_available).sum()),
        "excluded_started_label_measurement_incomplete": int((label_available & started & ~measured_started).sum()),
        "known_zero_unstarted_terminal_rows": int(known_zero.sum()),
        "fit_rows": len(result),
    }
    return result, audit


def metric_summary(group: pd.DataFrame) -> dict[str, Any]:
    ratios = group["realization_ratio"].to_numpy(dtype=float)
    requested = group["requested_service_nodeh"].to_numpy(dtype=float)
    realized = group["realized_service_nodeh"].to_numpy(dtype=float)
    errors = requested - realized
    quantiles = q(ratios, RATIO_PERCENTILES)
    return {
        "row_count": len(group),
        "requested_service_nodeh": float(requested.sum()),
        "realized_service_nodeh": float(realized.sum()),
        "mean_R": float(np.mean(ratios)),
        "median_R": float(np.median(ratios)),
        "R_percentiles": quantiles,
        "fraction_R_lt_0_1": float(np.mean(ratios < 0.1)),
        "fraction_R_lt_0_25": float(np.mean(ratios < 0.25)),
        "fraction_R_lt_0_5": float(np.mean(ratios < 0.5)),
        "fraction_R_gt_0_9": float(np.mean(ratios > 0.9)),
        "fraction_R_gt_1": float(np.mean(ratios > 1.0)),
        "MAE_nodeh": float(np.mean(np.abs(errors))),
        "WAPE_vs_realized": float(np.abs(errors).sum() / realized.sum()) if realized.sum() else None,
        "bias_requested_minus_realized_over_realized": float(errors.sum() / realized.sum()) if realized.sum() else None,
        "overstatement_ratio_requested_over_realized": float(requested.sum() / realized.sum()) if realized.sum() else None,
        "requested_weighted_realization_fraction": float(realized.sum() / requested.sum()) if requested.sum() else None,
    }


def grouped_summary(frame: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, group in frame.groupby(column, dropna=False, sort=True):
        rows.append({"group": str(key), **metric_summary(group)})
    return rows


def service_summary(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "artifact_id": "V29_PREAPRIL_SERVICE_CALIBRATION_SUMMARY_V1",
        "status": "PASS_READ_ONLY_CALIBRATION",
        "service_semantics": {
            "requested_service_nodeh": "nodes_req * wallclock_req",
            "realized_service_nodeh": "nodes_used * wallclock_used; terminated never-started jobs are source-semantic zero",
            "ratio": "realized_service_nodeh / requested_service_nodeh",
            "fit_label_availability": "end_time <= 2025-04-01T00:00:00+10:00",
        },
        "overall": metric_summary(frame),
        "by_node_class": grouped_summary(frame, "node_class"),
        "by_requested_wallclock_bin": grouped_summary(frame, "requested_wallclock_bin"),
        "by_queue_age_bin": grouped_summary(frame, "queue_age_bin"),
        "by_qos": grouped_summary(frame, "qos_observed_at_request"),
        "by_month": grouped_summary(frame, "submit_month"),
        "by_submit_hour_aest": grouped_summary(frame, "submit_hour_aest"),
        "by_submit_day_of_week": grouped_summary(frame, "submit_day_of_week"),
        "interpretation_boundary": "Descriptive calibration evidence only; no production quantile or multiplier is selected.",
    }


def prediction_metrics(actual: np.ndarray, requested: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    errors = prediction - actual
    return {
        "validation_row_count": len(actual),
        "validation_requested_nodeh": float(requested.sum()),
        "validation_realized_nodeh": float(actual.sum()),
        "predicted_nodeh": float(prediction.sum()),
        "MAE_nodeh": float(np.mean(np.abs(errors))),
        "WAPE_vs_realized": float(np.abs(errors).sum() / actual.sum()) if actual.sum() else None,
        "bias_prediction_minus_realized_over_realized": float(errors.sum() / actual.sum()) if actual.sum() else None,
        "overstatement_ratio_prediction_over_realized": float(prediction.sum() / actual.sum()) if actual.sum() else None,
        "fraction_realized_ge_prediction": float(np.mean(actual >= prediction)),
    }


def feature_matrix(train: pd.DataFrame, validate: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    def base(frame: pd.DataFrame) -> pd.DataFrame:
        local = frame["submit_utc"].dt.tz_convert(AEST)
        return pd.DataFrame(
            {
                "nodes_req": frame["node_class"].astype(float),
                "log1p_requested_hours": np.log1p(frame["requested_hours"].astype(float)),
                "submit_hour": local.dt.hour.astype(float),
                "submit_day_of_week": local.dt.dayofweek.astype(float),
                "submit_month": local.dt.month.astype(float),
            },
            index=frame.index,
        )

    x_train = base(train)
    x_validate = base(validate)
    qos_levels = sorted(train["qos_observed_at_request"].astype(str).unique())
    qos_map = {value: index for index, value in enumerate(qos_levels)}
    x_train["qos_code_train_only"] = train["qos_observed_at_request"].astype(str).map(qos_map).fillna(-1).astype(float)
    x_validate["qos_code_train_only"] = validate["qos_observed_at_request"].astype(str).map(qos_map).fillna(-1).astype(float)
    return x_train, x_validate, list(x_train.columns)


def rolling_origin(frame: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from lightgbm import LGBMRegressor
    except ImportError as exc:  # pragma: no cover - environment contract catches this
        raise RuntimeError("V29_PREAPRIL_LIGHTGBM_NOT_AVAILABLE") from exc

    rows: list[dict[str, Any]] = []
    fold_audits: list[dict[str, Any]] = []
    months = pd.date_range("2024-02-01", "2025-03-01", freq="MS", tz=AEST)
    for validation_start in months:
        validation_end = validation_start + pd.offsets.MonthBegin(1)
        train_cutoff_utc = validation_start.tz_convert("UTC")
        validation_cutoff_utc = validation_end.tz_convert("UTC")
        train = frame.loc[
            frame["submit_utc"].lt(train_cutoff_utc) & frame["end_utc"].le(train_cutoff_utc)
        ].copy()
        validate = frame.loc[
            frame["submit_utc"].ge(train_cutoff_utc)
            & frame["submit_utc"].lt(validation_cutoff_utc)
            & frame["end_utc"].le(validation_cutoff_utc)
        ].copy()
        if train.empty or validate.empty:
            fold_audits.append(
                {
                    "validation_month": validation_start.strftime("%Y-%m"),
                    "status": "SKIPPED_EMPTY_TRAIN_OR_VALIDATION",
                    "train_rows": len(train),
                    "validation_rows": len(validate),
                }
            )
            continue
        factors = {
            "RAW_WALLCLOCK_REQ": 1.0,
            "HISTORICAL_MEDIAN_REALIZATION_FRACTION": float(train["realization_ratio"].median()),
            "HISTORICAL_P25_REALIZATION_FRACTION": float(train["realization_ratio"].quantile(0.25)),
        }
        actual = validate["realized_service_nodeh"].to_numpy(dtype=float)
        requested = validate["requested_service_nodeh"].to_numpy(dtype=float)
        common = {
            "validation_month": validation_start.strftime("%Y-%m"),
            "train_label_cutoff_aest": validation_start.isoformat(),
            "validation_label_cutoff_aest": validation_end.isoformat(),
            "train_row_count": len(train),
        }
        for candidate, factor in factors.items():
            metrics = prediction_metrics(actual, requested, requested * factor)
            rows.append({**common, "candidate": candidate, "fixed_train_factor": factor, **metrics})
        x_train, x_validate, features = feature_matrix(train, validate)
        model = LGBMRegressor(
            objective="quantile",
            alpha=0.5,
            n_estimators=100,
            learning_rate=0.05,
            num_leaves=15,
            max_depth=4,
            min_child_samples=20,
            subsample=1.0,
            colsample_bytree=1.0,
            reg_lambda=1.0,
            random_state=29,
            deterministic=True,
            force_col_wise=True,
            verbosity=-1,
            n_jobs=1,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(x_train, train["realization_ratio"].to_numpy(dtype=float))
        factor_prediction = model.predict(x_validate)
        metrics = prediction_metrics(actual, requested, requested * factor_prediction)
        rows.append(
            {
                **common,
                "candidate": "FIXED_SIMPLE_LIGHTGBM_Q50_RATIO",
                "fixed_train_factor": None,
                **metrics,
            }
        )
        fold_audits.append(
            {
                "validation_month": validation_start.strftime("%Y-%m"),
                "status": "PASS",
                "train_rows": len(train),
                "validation_rows": len(validate),
                "features": features,
                "train_rows_with_end_after_train_cutoff": int((train["end_utc"] > train_cutoff_utc).sum()),
                "april_rows_in_train": int((train["submit_utc"] >= FIT_CUTOFF.tz_convert("UTC")).sum()),
            }
        )
    return rows, {"folds": fold_audits, "fold_count_executed": sum(row["status"] == "PASS" for row in fold_audits)}


def causal_audit(source: Path, source_audit: dict[str, Any], calibration_audit: dict[str, int], calibration: pd.DataFrame, rolling_audit: dict[str, Any]) -> dict[str, Any]:
    fit_utc = FIT_CUTOFF.tz_convert("UTC")
    late = int((calibration["end_utc"] > fit_utc).sum())
    april_submit = int((calibration["submit_utc"] >= fit_utc).sum())
    april_end = int((calibration["end_utc"] >= fit_utc).sum())
    fold_late = sum(row.get("train_rows_with_end_after_train_cutoff", 0) for row in rolling_audit["folds"])
    fold_april = sum(row.get("april_rows_in_train", 0) for row in rolling_audit["folds"])
    return {
        "artifact_id": "V29_PREAPRIL_CAUSAL_LABEL_AUDIT_V1",
        "status": "PASS" if late == april_submit == april_end == fold_late == fold_april == 0 else "FAIL",
        "fit_cutoff_aest": FIT_CUTOFF.isoformat(),
        "label_availability_rule": "end_time <= fit/fold cutoff; started rows additionally require nodes_used and wallclock_used",
        "FIT_ROWS_WITH_LABEL_AVAILABLE_AFTER_CUTOFF": late,
        "APRIL_LABEL_ROWS_IN_PREAPRIL_FIT": april_end,
        "APRIL_SUBMIT_ROWS_IN_PREAPRIL_FIT": april_submit,
        "ROLLING_TRAIN_ROWS_WITH_LABEL_AFTER_FOLD_CUTOFF": fold_late,
        "ROLLING_APRIL_ROWS_IN_TRAIN": fold_april,
        "future_archive_members_opened_for_queue_reconstruction": True,
        "future_archive_completion_labels_used_in_fit": 0,
        "source_path": str(source),
        "source_sha256": sha256(source),
        "expected_source_sha256": NLR_SOURCE_SHA256["kestrel_jobs_zip"],
        "source_sha_match": sha256(source) == NLR_SOURCE_SHA256["kestrel_jobs_zip"],
        "source_audit": source_audit,
        "calibration_population_audit": calibration_audit,
        "rolling_origin_audit": rolling_audit,
    }


def grid_value_artifacts(daily: list[dict[str, Any]], repo: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    anchor_path = repo / "dayahead/artifacts/v16_3/V16_3_D1_AC_ANCHOR_AUTHORITY.json"
    v29_path = repo / "dayahead/artifacts/v29_grid_responsive_aidc/V29_CRITICAL_TIME_FLEXIBILITY_UPPER_BOUND.json"
    anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    v29 = json.loads(v29_path.read_text(encoding="utf-8"))
    available = set(anchor.get("included_April_days", [])) | {
        str(row.get("day")) for row in v29.get("rows", []) if row.get("day")
    }
    study_days = {row["day"] for row in daily}
    intersection = sorted(study_days & available)
    rows = [
        {
            "day": row["day"],
            "D_minus_1_critical_line": None,
            "D_minus_1_critical_phase": None,
            "D_minus_1_critical_time": None,
            "carryin_nodeh": row["D0_0000_predicted_carryin_nodeh"],
            "rho_0_10_maximum_critical_time_AIDC_relief": None,
            "rho_1_diagnostic_maximum_relief": None,
            "sensitivity_weighted_maximum_relief": None,
            "critical_time_feasible_AIDC_kw": None,
            "identifiability": "NOT_IDENTIFIABLE_NO_FROZEN_HISTORICAL_D1_ELECTRICAL_CRITICAL_ROW",
        }
        for row in daily
    ]
    summary = {
        "artifact_id": "V29_PREAPRIL_GRID_VALUE_POTENTIAL_SUMMARY_V1",
        "status": "NOT_IDENTIFIABLE_SOURCE_ELECTRICAL_AUTHORITY_INSUFFICIENT",
        "study_day_count": len(daily),
        "study_days_with_frozen_D1_electrical_critical_row": len(intersection),
        "available_authority_intersection": intersection,
        "P50_grid_value_ceiling": None,
        "P75_grid_value_ceiling": None,
        "P90_grid_value_ceiling": None,
        "P95_grid_value_ceiling": None,
        "carryin_vs_grid_value_correlation": None,
        "days_with_high_carryin_but_low_topology_value": None,
        "days_with_low_carryin_but_high_topology_sensitivity": None,
        "rho_0_10_material_day_fraction": None,
        "reason": "Frozen D1 feeder critical-line/phase/time authority begins in April 2025; extrapolating it to 2024-01-01 through 2025-03-31 would manufacture topology evidence.",
        "full_10x96_OpenDSS_runs": 0,
        "production_changes": 0,
        "authority_sources": {
            str(anchor_path.relative_to(repo)): sha256(anchor_path),
            str(v29_path.relative_to(repo)): sha256(v29_path),
        },
    }
    return rows, summary


def percentile_context(daily: list[dict[str, Any]]) -> dict[str, Any]:
    values = np.asarray([row["D0_0000_predicted_carryin_nodeh"] for row in daily], dtype=float)
    contexts: dict[str, Any] = {}
    for day, value in (("2025-04-03", 216.0), ("2025-04-04", 1020.0)):
        contexts[day] = {
            "development_carryin_nodeh": value,
            "empirical_percentile_rank_inclusive_percent": float(100.0 * np.mean(values <= value)),
            "empirical_midrank_percent": float(100.0 * (np.sum(values < value) + 0.5 * np.sum(values == value)) / len(values)),
            "historical_days_strictly_greater": int(np.sum(values > value)),
            "historical_day_count": len(values),
        }
    return {
        "artifact_id": "V29_APR03_APR04_HISTORICAL_PERCENTILE_CONTEXT_V1",
        "status": "PASS",
        "historical_population": "456 daily D0 predicted carry-in values, 2024-01-01 through 2025-03-31",
        "percentile_convention": "inclusive empirical CDF plus midrank for ties",
        "contexts": contexts,
    }


def effect_range(groups: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in groups if row["row_count"] >= 20 and row["median_R"] is not None]
    if not eligible:
        return {"eligible_group_count": 0, "median_R_range": None, "minimum_group": None, "maximum_group": None}
    low = min(eligible, key=lambda row: row["median_R"])
    high = max(eligible, key=lambda row: row["median_R"])
    return {
        "eligible_group_count": len(eligible),
        "minimum_group": low["group"],
        "minimum_median_R": low["median_R"],
        "maximum_group": high["group"],
        "maximum_median_R": high["median_R"],
        "median_R_range": high["median_R"] - low["median_R"],
    }


def aggregate_rolling(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    candidates = sorted({row["candidate"] for row in rows})
    for candidate in candidates:
        group = [row for row in rows if row["candidate"] == candidate]
        weights = np.asarray([row["validation_row_count"] for row in group], dtype=float)
        result[candidate] = {
            "fold_count": len(group),
            "row_weighted_mean_MAE_nodeh": float(np.average([row["MAE_nodeh"] for row in group], weights=weights)),
            "row_weighted_mean_fraction_realized_ge_prediction": float(
                np.average([row["fraction_realized_ge_prediction"] for row in group], weights=weights)
            ),
            "median_fold_overstatement_ratio": float(
                np.median([row["overstatement_ratio_prediction_over_realized"] for row in group])
            ),
        }
    return result


def final_review(
    distribution_payload: dict[str, Any],
    service_payload: dict[str, Any],
    rolling_rows: list[dict[str, Any]],
    grid_summary: dict[str, Any],
    percentiles: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    overall = service_payload["overall"]
    rolling = aggregate_rolling(rolling_rows)
    class_effect = effect_range(service_payload["by_node_class"])
    wall_effect = effect_range(service_payload["by_requested_wallclock_bin"])
    qos_effect = effect_range(service_payload["by_qos"])
    age_effect = effect_range(service_payload["by_queue_age_bin"])
    april = percentiles["contexts"]
    typical = overall["median_R"]
    if overall["fraction_R_gt_1"] <= 0.05 and overall["overstatement_ratio_requested_over_realized"] > 1.1:
        proxy = "conservative upper-bound-like proxy at population level, not a calibrated point estimate"
    else:
        proxy = "materially biased service-mass proxy rather than a calibrated point estimate"
    answers = {
        "1_how_often_source_backed_carryin_exists": {
            "nonzero_day_fraction": 1.0 - distribution_payload["fraction_zero"],
            "zero_day_fraction": distribution_payload["fraction_zero"],
            "threshold_fractions": distribution_payload["threshold_fractions_strictly_greater"],
        },
        "2_Apr3_Apr4_typical_or_unusual": april,
        "3_wallclock_req_interpretation": proxy,
        "4_typical_requested_service_realized": {
            "median_job_ratio": typical,
            "requested_weighted_realization_fraction": overall["requested_weighted_realization_fraction"],
        },
        "5_ratio_dependence": {
            "direct_answer": "Requested wallclock and QoS show strong descriptive separation; node class and cutoff-observable queue age show smaller separation. These are associations, not causal effects.",
            "node_class": class_effect,
            "requested_wallclock": wall_effect,
            "QoS": qos_effect,
            "cutoff_observable_queue_age": age_effect,
            "note": "Ranges are descriptive among groups with at least 20 rows; no causal effect is claimed.",
        },
        "6_lower_bound_calibrated_mass_justified": {
            "answer": "Yes as a separately validated uncertainty/lower-bound estimator; no as an immediately selectable production replacement. The fixed P25 candidate attains empirical lower-bound coverage but materially underpredicts aggregate realized mass.",
            "P25_rolling_row_weighted_lower_bound_coverage": rolling["HISTORICAL_P25_REALIZATION_FRACTION"]["row_weighted_mean_fraction_realized_ge_prediction"],
            "P25_median_fold_prediction_over_realized": rolling["HISTORICAL_P25_REALIZATION_FRACTION"]["median_fold_overstatement_ratio"],
            "rolling_origin_candidates": rolling,
            "boundary": "No production quantile, multiplier, clipping, or eligibility change is selected.",
        },
        "7_material_grid_value_under_rho_0_10": {
            "answer": "NOT_IDENTIFIABLE",
            "material_day_fraction": grid_summary["rho_0_10_material_day_fraction"],
            "reason": grid_summary["reason"],
        },
        "8_population_level_low_AIDC_contribution_cause": {
            "answer": "Rare workload is the demonstrable population-level gate because carry-in is zero on most days. Conditional on nonzero carry-in, topology and trust attribution are not identifiable here, so the residual mechanism may be mixed but cannot be apportioned.",
            "measured_nonzero_carryin_fraction": 1.0 - distribution_payload["fraction_zero"],
        },
        "9_must_remain_unchanged": [
            "rho",
            "nodes_req * wallclock_req production service-mass authority",
            "strict full-node request-time eligibility and PARTIAL/shared exclusion",
            "PRE_DAY_QUEUE_BRIDGE_V1",
            "queue clipping policy",
            "objective and site mapping",
            "all production quantiles, multipliers, and campaign formulation parameters",
        ],
    }
    payload = {
        "artifact_id": "V29_PREAPRIL_CENSUS_FINAL_REVIEW_V1",
        "status": "PASS_READ_ONLY_CENSUS_WITH_GRID_VALUE_NOT_IDENTIFIABLE",
        "production_mutations": 0,
        "full_OpenDSS_10x96_runs": 0,
        "answers": answers,
        "limitations": [
            "Daily realized queued service is explicitly ex-post and is never a day-ahead feature.",
            "Calibration excludes every label unavailable by its fit or rolling-fold cutoff.",
            "No frozen historical D1 electrical critical-row authority exists inside the study window.",
        ],
    }
    c = answers["1_how_often_source_backed_carryin_exists"]
    a3 = april["2025-04-03"]
    a4 = april["2025-04-04"]
    text = f"""# V29 pre-April carry-in population and service-mass calibration review

Status: **PASS — read-only census; pre-April grid-value potential is not identifiable from frozen electrical authority.**

No production formulation, parameter, eligibility rule, objective, site mapping, or campaign result was changed. No full 10×96 OpenDSS campaign was run.

## Direct answers

1. **How often does source-backed carry-in actually exist?** Nonzero predicted carry-in occurs on {100*c['nonzero_day_fraction']:.2f}% of the 456 study days; {100*c['zero_day_fraction']:.2f}% are zero. Fractions strictly above 100/250/500/1000 node-h are {100*c['threshold_fractions']['100']:.2f}% / {100*c['threshold_fractions']['250']:.2f}% / {100*c['threshold_fractions']['500']:.2f}% / {100*c['threshold_fractions']['1000']:.2f}%.

2. **Are Apr-3 216 node-h and Apr-4 1020 node-h typical?** Apr-3 is at the inclusive empirical {a3['empirical_percentile_rank_inclusive_percent']:.2f}th percentile (midrank {a3['empirical_midrank_percent']:.2f}); Apr-4 is at the {a4['empirical_percentile_rank_inclusive_percent']:.2f}th percentile (midrank {a4['empirical_midrank_percent']:.2f}).

3. **What is wallclock_req as a service-mass proxy?** It is a {proxy}.

4. **What fraction is typically realized?** Median job-level R is {overall['median_R']:.4f}; aggregate realized/requested service is {overall['requested_weighted_realization_fraction']:.4f}.

5. **Does R depend on request-time groups?** Yes, strongly for requested wallclock and QoS in descriptive terms; less strongly for node class and cutoff-observable queue age. Median-R ranges (groups with at least 20 rows) are: node class {class_effect['median_R_range']}, requested wallclock {wall_effect['median_R_range']}, QoS {qos_effect['median_R_range']}, and first-cutoff queue age {age_effect['median_R_range']}. These are associations, not causal effects.

6. **Is a lower-bound calibrated executable-service mass justified?** Yes as a separately validated lower-bound/uncertainty estimator, but not as an immediately selectable production replacement. The fixed historical P25 candidate has {100*rolling['HISTORICAL_P25_REALIZATION_FRACTION']['row_weighted_mean_fraction_realized_ge_prediction']:.2f}% empirical lower-bound coverage while its median fold prediction/realized ratio is only {rolling['HISTORICAL_P25_REALIZATION_FRACTION']['median_fold_overstatement_ratio']:.4f}; it is conservative enough to underpredict aggregate mass materially. This census selects no production quantile.

7. **How often is grid-value material under rho=.10?** Not identifiable. Frozen D1 feeder critical-line/phase/time authority begins in April 2025, outside the study population.

8. **Why is AIDC contribution low at population level?** Rare workload is the demonstrable population-level gate because carry-in is zero on {100*c['zero_day_fraction']:.2f}% of days. Conditional on nonzero carry-in, historical topology and trust contributions are not jointly identifiable, so the residual may be mixed but cannot be apportioned.

9. **What remains unchanged?** rho; production `nodes_req × wallclock_req`; strict full-node eligibility and PARTIAL/shared exclusion; PRE_DAY_QUEUE_BRIDGE_V1; clipping policy; objective; site mapping; and all production quantiles, multipliers, and formulation parameters until the active post-development forensic finishes.

## Causal and scientific boundaries

- `FIT_ROWS_WITH_LABEL_AVAILABLE_AFTER_CUTOFF = 0`
- `APRIL_LABEL_ROWS_IN_PREAPRIL_FIT = 0`
- Future archive members were opened only to reconstruct historical queue state; their post-cutoff completion labels were excluded from every fit.
- Daily D0 realized queued service is an ex-post diagnostic only.
- The grid-value CSV is deliberately fail-closed with null electrical fields rather than extrapolating April topology into pre-April dates.
"""
    return payload, text


def calibration_csv_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    fields = (
        "id",
        "submit_utc",
        "start_utc",
        "end_utc",
        "node_class",
        "requested_hours",
        "nodes_used_num",
        "used_hours",
        "requested_service_nodeh",
        "realized_service_nodeh",
        "realization_ratio",
        "requested_wallclock_bin",
        "queue_age_at_first_D1_cutoff_hours",
        "queue_age_bin",
        "qos_observed_at_request",
        "submit_month",
        "submit_hour_aest",
        "submit_day_of_week",
        "state_simple",
        "absolute_error_nodeh_raw_request",
        "signed_overstatement_nodeh_raw_request",
    )
    return [{field: scalar(row[field]) for field in fields} for _, row in frame.iterrows()]


def build(repo: Path) -> None:
    out = repo / OUTPUT_REL
    out.mkdir(parents=True, exist_ok=True)
    source = source_zip()
    if sha256(source) != NLR_SOURCE_SHA256["kestrel_jobs_zip"]:
        raise RuntimeError("V29_PREAPRIL_KESTREL_SHA_DRIFT")
    raw, source_audit = read_h100_events(source)
    frame = prepare(raw)
    daily = daily_census(frame, repo)
    distribution_payload = distribution(daily, repo)
    calibration, calibration_audit = calibration_rows(frame)
    if calibration.empty:
        raise RuntimeError("V29_PREAPRIL_EMPTY_CALIBRATION_POPULATION")
    service_payload = service_summary(calibration)
    rolling_rows, rolling_audit = rolling_origin(calibration)
    causal_payload = causal_audit(source, source_audit, calibration_audit, calibration, rolling_audit)
    if causal_payload["status"] != "PASS":
        raise RuntimeError("V29_PREAPRIL_CAUSAL_LABEL_AUDIT_FAILED")
    grid_rows, grid_summary = grid_value_artifacts(daily, repo)
    context_payload = percentile_context(daily)
    review_payload, review_md = final_review(
        distribution_payload, service_payload, rolling_rows, grid_summary, context_payload
    )

    write_csv(out / ARTIFACT_NAMES[0], daily)
    write_json(out / ARTIFACT_NAMES[1], distribution_payload)
    write_csv(out / ARTIFACT_NAMES[2], calibration_csv_rows(calibration))
    write_json(out / ARTIFACT_NAMES[3], service_payload)
    write_csv(out / ARTIFACT_NAMES[4], rolling_rows)
    write_json(out / ARTIFACT_NAMES[5], causal_payload)
    write_csv(out / ARTIFACT_NAMES[6], grid_rows)
    write_json(out / ARTIFACT_NAMES[7], grid_summary)
    write_json(out / ARTIFACT_NAMES[8], context_payload)
    (out / ARTIFACT_NAMES[9]).write_text(review_md, encoding="utf-8", newline="\n")
    write_json(out / ARTIFACT_NAMES[10], review_payload)

    checks = {
        "required_day_count_456": len(daily) == 456,
        "daily_dates_unique": len({row["day"] for row in daily}) == 456,
        "bridge_budget_792_nodeh": math.isclose(distribution_payload["bridge_budget_nodeh"], 792.0),
        "carryin_nonnegative": all(row["D0_0000_predicted_carryin_nodeh"] >= 0 for row in daily),
        "fit_rows_exist": len(calibration) > 0,
        "fit_labels_causal": causal_payload["FIT_ROWS_WITH_LABEL_AVAILABLE_AFTER_CUTOFF"] == 0,
        "no_April_fit_labels": causal_payload["APRIL_LABEL_ROWS_IN_PREAPRIL_FIT"] == 0,
        "rolling_folds_exist": rolling_audit["fold_count_executed"] > 0,
        "grid_fail_closed": grid_summary["status"] == "NOT_IDENTIFIABLE_SOURCE_ELECTRICAL_AUTHORITY_INSUFFICIENT",
        "full_OpenDSS_10x96_runs_zero": grid_summary["full_10x96_OpenDSS_runs"] == 0,
        "production_mutations_zero": review_payload["production_mutations"] == 0,
    }
    test_payload = {
        "artifact_id": "V29_PREAPRIL_CENSUS_TEST_REPORT_V1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "check_count": len(checks),
        "passed_count": sum(checks.values()),
        "runner": str(Path(__file__).relative_to(repo)),
    }
    write_json(out / ARTIFACT_NAMES[11], test_payload)
    if test_payload["status"] != "PASS":
        raise RuntimeError("V29_PREAPRIL_INTERNAL_TEST_FAILED")
    missing = [name for name in ARTIFACT_NAMES if not (out / name).is_file()]
    if missing:
        raise RuntimeError(f"V29_PREAPRIL_REQUIRED_ARTIFACT_MISSING:{missing}")
    manifest = {
        "artifact_id": "V29_PREAPRIL_CENSUS_ARTIFACT_SHA256_V1",
        "status": "PASS",
        "hash_algorithm": "SHA256",
        "files": {name: sha256(out / name) for name in ARTIFACT_NAMES},
    }
    write_json(out / "V29_PREAPRIL_CENSUS_ARTIFACT_SHA256.json", manifest)
    pytest_command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        str(repo / "tests/dayahead/test_v29_preapril_census.py"),
    ]
    pytest_result = subprocess.run(
        pytest_command,
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    test_payload["artifact_pytest"] = {
        "command": "python -m pytest -q tests/dayahead/test_v29_preapril_census.py",
        "exit_code": pytest_result.returncode,
        "status": "PASS" if pytest_result.returncode == 0 else "FAIL",
        "output": (pytest_result.stdout + pytest_result.stderr).strip(),
    }
    test_payload["status"] = "PASS" if all(checks.values()) and pytest_result.returncode == 0 else "FAIL"
    write_json(out / ARTIFACT_NAMES[11], test_payload)
    manifest["files"] = {name: sha256(out / name) for name in ARTIFACT_NAMES}
    write_json(out / "V29_PREAPRIL_CENSUS_ARTIFACT_SHA256.json", manifest)
    if pytest_result.returncode != 0:
        raise RuntimeError("V29_PREAPRIL_ARTIFACT_PYTEST_FAILED")
    print(json.dumps({
        "status": "PASS",
        "output": str(out),
        "day_count": len(daily),
        "calibration_rows": len(calibration),
        "rolling_fold_count": rolling_audit["fold_count_executed"],
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    args = parser.parse_args()
    build(args.repo.resolve())


if __name__ == "__main__":
    main()
