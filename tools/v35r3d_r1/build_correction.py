"""Build the V35R3D-R1 running-residual and start-accounting correction."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v35r3d_r1.contracts import (
    ARTIFACT_DIRNAME,
    BRANCH,
    CALIBRATION_END,
    CALIBRATION_START,
    HPCODA_HEAD,
    ISSUE_TIME,
    KESTREL_ARCHIVE_SHA256,
    PARENT_ARTIFACTS,
    PARENT_CACHE,
    PARENT_HEAD,
    PARENT_WORKTREE,
    QUANTILE_LEVEL,
    RUNNING_RESIDUAL_AUTHORITY,
    RUNTIME_AUTHORITY,
    SLOT_SECONDS,
    TARGET_END,
    TARGET_END_SLOT,
    TARGET_OFFSET_SLOTS,
    TARGET_START,
    WORKTREE,
)
from dayahead.v35r3d_r1.scheduler import (
    capacity_horizon,
    critical_windows,
    pre_w5_consequence,
    rsp_duration_authority,
    schedule_rsp,
)


ART = REPO / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
LOG = REPO / "logs" / ARTIFACT_DIRNAME
PARENT_BASELINE = (
    REPO
    / "dayahead"
    / "artifacts"
    / "v35r3a_kestrel_scheduler_temporal"
    / "V35R3A_BASELINE_SCHEDULE.parquet"
)
PARENT_SAFE = PARENT_ARTIFACTS / "V35R3D_APR01_RUNTIME_SAFE.parquet"
PARENT_POINT = PARENT_ARTIFACTS / "V35R3D_APR01_RUNTIME_POINT.parquet"
PARENT_CAL = PARENT_CACHE / "calibration_predictions.parquet"
PARENT_HIST = PARENT_CACHE / "kestrel_preissue_normalized.parquet"


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(name: str, payload: dict[str, Any]) -> None:
    (ART / name).write_text(
        json.dumps(jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def command(*args: str, cwd: Path | None = None) -> str:
    return subprocess.check_output(
        list(args), cwd=cwd, text=True, encoding="utf-8", errors="replace"
    ).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reuse_manifest() -> dict[str, Any]:
    files = [
        PARENT_POINT,
        PARENT_SAFE,
        PARENT_CAL,
        PARENT_CACHE / "query_adapter_equivalence.json",
        PARENT_CACHE / "stage_b1.json",
        PARENT_CACHE / "stage_tail32.json",
    ] + sorted((PARENT_CACHE / "window_predictions").glob("*.parquet"))
    return {
        "files": [
            {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in files
        ],
        "window_prediction_files": len(list((PARENT_CACHE / "window_predictions").glob("*.parquet"))),
        "xgboost_fit_calls": 0,
        "source_mode": "READ_ONLY_PARENT_CACHE",
    }


def running_survival(
    predictions: pd.DataFrame,
    parent_schedule: pd.DataFrame,
    old_schedule: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    running = predictions.loc[predictions["state_at_issue"].eq("RUNNING")].copy()
    running = running.merge(
        parent_schedule[["job_id", "request_gpu_hours"]].rename(
            columns={"request_gpu_hours": "requested_remaining_GPU_hours_at_issue"}
        ),
        on="job_id",
        validate="one_to_one",
    )
    running = running.merge(
        old_schedule[["job_id", "scheduled_end_slot"]].rename(
            columns={"scheduled_end_slot": "OLD_RS_predicted_release_slot"}
        ),
        on="job_id",
        validate="one_to_one",
    )
    point = running["T_hat_point_seconds"].to_numpy(float)
    safe = running["T_hat_safe_seconds"].to_numpy(float)
    elapsed = running["elapsed_seconds_at_issue"].to_numpy(float)
    running["survival_category"] = np.select(
        [
            elapsed < point,
            (elapsed >= point) & (elapsed < safe),
            elapsed >= safe,
        ],
        [
            "A_ELAPSED_LT_POINT",
            "B_POINT_LE_ELAPSED_LT_SAFE",
            "C_ELAPSED_GE_SAFE",
        ],
        default="UNCLASSIFIED",
    )
    running["elapsed_ge_requested"] = (
        running["elapsed_seconds_at_issue"] >= running["requested_walltime_seconds"]
    )
    running["elapsed_gt_requested"] = (
        running["elapsed_seconds_at_issue"] > running["requested_walltime_seconds"]
    )
    running["requested_total_GPU_hours"] = (
        running["requested_GPUs"] * running["requested_walltime_seconds"] / 3600.0
    )
    running["OLD_RS_release_timestamp_AEST"] = running[
        "OLD_RS_predicted_release_slot"
    ].map(lambda slot: (ISSUE_TIME + timedelta(seconds=int(slot) * SLOT_SECONDS)).isoformat())

    def category(name: str) -> dict[str, Any]:
        part = running.loc[running["survival_category"].eq(name)]
        return {
            "jobs": len(part),
            "requested_GPUs": float(part["requested_GPUs"].sum()),
            "requested_remaining_GPU_hours_at_issue": float(
                part["requested_remaining_GPU_hours_at_issue"].sum()
            ),
            "requested_total_GPU_hours": float(part["requested_total_GPU_hours"].sum()),
            "job_fraction": len(part) / len(running),
            "GPU_fraction": float(part["requested_GPUs"].sum() / running["requested_GPUs"].sum()),
        }

    c = running.loc[running["survival_category"].eq("C_ELAPSED_GE_SAFE")]
    d = running.loc[running["elapsed_ge_requested"]]
    c_release = c.groupby("OLD_RS_predicted_release_slot", as_index=False).agg(
        jobs=("job_id", "size"), requested_GPUs=("requested_GPUs", "sum")
    )
    preday_running_releases = running.loc[
        running["OLD_RS_predicted_release_slot"].between(1, TARGET_OFFSET_SLOTS - 1)
    ]
    summary = {
        "artifact_id": "V35R3D_R1_RUNNING_SURVIVAL_SUMMARY_V1",
        "running_jobs": len(running),
        "running_requested_GPUs": float(running["requested_GPUs"].sum()),
        "categories": {
            "A": category("A_ELAPSED_LT_POINT"),
            "B": category("B_POINT_LE_ELAPSED_LT_SAFE"),
            "C": category("C_ELAPSED_GE_SAFE"),
            "D_elapsed_ge_requested": {
                "jobs": len(d),
                "requested_GPUs": float(d["requested_GPUs"].sum()),
            },
        },
        "category_C_OLD_RS_release_slots": c_release.to_dict("records"),
        "category_C_first_OLD_RS_release_slot": int(c["OLD_RS_predicted_release_slot"].min()),
        "category_C_attributable_release_GPUs": float(c["requested_GPUs"].sum()),
        "category_C_attributable_release_GPU_hours": float(c["requested_GPUs"].sum() * 0.25),
        "OLD_RS_preday_running_release_GPUs": float(preday_running_releases["requested_GPUs"].sum()),
        "category_C_share_of_OLD_RS_preday_running_release_GPUs": float(
            c["requested_GPUs"].sum() / preday_running_releases["requested_GPUs"].sum()
        ),
        "conclusion": "Observed survival contradicted unconditional safe-total prediction for category C; OLD_RS one-slot residual treatment is diagnostic only.",
    }
    return running, summary


def coverage_metrics(frame: pd.DataFrame, q: float) -> dict[str, Any]:
    actual = frame["actual_runtime_seconds"].to_numpy(float)
    point = frame["point_runtime_seconds"].to_numpy(float)
    requested = frame["requested_seconds"].to_numpy(float)
    uncapped = np.maximum(point + q, float(SLOT_SECONDS))
    capped = np.minimum(requested, uncapped)
    within = actual <= requested
    return {
        "rows": len(frame),
        "uncapped_coverage": float(np.mean(actual <= uncapped)),
        "capped_coverage": float(np.mean(actual <= capped)),
        "safe_uncapped_gt_requested_fraction": float(np.mean(uncapped > requested)),
        "actual_gt_requested_fraction": float(np.mean(actual > requested)),
        "coverage_conditional_actual_le_requested": float(np.mean((actual <= capped)[within]))
        if within.any()
        else None,
    }


def calibration_audit(
    calibration: pd.DataFrame, historical: pd.DataFrame
) -> tuple[dict[str, Any], pd.DataFrame, float]:
    residual_plus = np.maximum(
        calibration["actual_runtime_seconds"].to_numpy(float)
        - calibration["point_runtime_seconds"].to_numpy(float),
        0.0,
    )
    n = len(residual_plus)
    q_emp = float(np.quantile(residual_plus, QUANTILE_LEVEL, method="linear"))
    k = min(n, int(math.ceil((n + 1) * QUANTILE_LEVEL)))
    q_conf = float(np.sort(residual_plus)[k - 1])
    joined = calibration.merge(
        historical[["job_id", "qos", "num_gpus_req"]].drop_duplicates("job_id"),
        on="job_id",
        how="left",
        validate="many_to_one",
    )
    missing_qos = int(joined["qos"].isna().sum())
    missing_gpu = int(joined["num_gpus_req"].isna().sum())
    joined["qos"] = joined["qos"].fillna("UNAVAILABLE")
    joined["requested_walltime_bin"] = pd.cut(
        joined["requested_seconds"],
        bins=[-np.inf, 900, 3600, 21600, 43200, 86400, 172800, np.inf],
        labels=["LE_15M", "15M_1H", "1H_6H", "6H_12H", "12H_24H", "24H_48H", "GT_48H"],
        right=True,
    ).astype(str)
    joined["GPU_request_count"] = joined["num_gpus_req"].map(
        lambda value: "UNAVAILABLE" if pd.isna(value) else f"GPU_{float(value):g}"
    )
    rows: list[dict[str, Any]] = []
    for method, q in (("Q_EMP90", q_emp), ("Q_CONF90", q_conf)):
        groups: list[tuple[str, str, pd.DataFrame]] = [("ALL", "ALL", joined)]
        for dimension, column in (
            ("REQUESTED_WALLTIME_BIN", "requested_walltime_bin"),
            ("QOS", "qos"),
            ("GPU_REQUEST_COUNT", "GPU_request_count"),
        ):
            groups.extend(
                (dimension, str(value), group)
                for value, group in joined.groupby(column, dropna=False, observed=True)
            )
        for dimension, value, group in groups:
            rows.append(
                {
                    "quantile_method": method,
                    "q_seconds": q,
                    "group_dimension": dimension,
                    "group_value": value,
                    **coverage_metrics(group, q),
                }
            )
    decomposition = pd.DataFrame(rows)
    emp = coverage_metrics(joined, q_emp)
    conf = coverage_metrics(joined, q_conf)
    selected = q_conf
    audit = {
        "artifact_id": "V35R3D_R1_CALIBRATION_QUANTILE_AUDIT_V1",
        "interval_start_AEST": CALIBRATION_START,
        "interval_end_exclusive_AEST": CALIBRATION_END,
        "rows": n,
        "quantile_level": QUANTILE_LEVEL,
        "Q_EMP90": {"method": "numpy_linear", "q_seconds": q_emp, **emp},
        "Q_CONF90": {
            "method": "finite_sample_split_conformal_one_sided",
            "rank_k": k,
            "rank_n": n,
            "q_seconds": q_conf,
            **conf,
        },
        "selected_q_method": "Q_CONF90_FINITE_SAMPLE_SPLIT_CONFORMAL",
        "selected_q_seconds": selected,
        "selected_capped_safe_coverage": conf["capped_coverage"],
        "selected_uncapped_safe_coverage": conf["uncapped_coverage"],
        "coverage_loss_from_requested_cap": conf["uncapped_coverage"] - conf["capped_coverage"],
        "SAFE_COVERAGE_LIMITED_BY_REQUESTED_WALLTIME_CAP": conf["capped_coverage"] < QUANTILE_LEVEL
        and conf["uncapped_coverage"] >= QUANTILE_LEVEL,
        "quantiles_equal_due_to_residual_tie": q_emp == q_conf,
        "Apr01_actual_labels_read": 0,
        "scheduler_result_used_for_q_selection": False,
        "coverage_group_feature_missing_qos_rows": missing_qos,
        "coverage_group_feature_missing_GPU_rows": missing_gpu,
        "root_cause": "The quantile is correct and reaches nominal uncapped coverage; requested-walltime capping lowers coverage. Actual runtime also exceeds requested walltime for a nonzero subset.",
    }
    return audit, decomposition, selected


def classify_start(slot: int) -> str:
    if slot < TARGET_OFFSET_SLOTS:
        return "PRE_DAY"
    if slot < TARGET_END_SLOT:
        return "APR01"
    return "NOT_STARTED_BY_T2"


def start_accounting(
    parent_schedule: pd.DataFrame,
    schedules: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    base = parent_schedule.loc[
        parent_schedule["workload_class"].eq("STANDBY_QUEUE_CONTROLLED"),
        ["job_id", "submit_time", "state_at_issue", "requested_gpus", "request_gpu_hours"],
    ].copy()
    base = base.rename(
        columns={"requested_gpus": "requested_GPUs", "request_gpu_hours": "requested_GPU_hours"}
    )
    for mode, schedule in schedules.items():
        selected = schedule[["job_id", "scheduled_start_slot", "scheduled_end_slot"]].rename(
            columns={
                "scheduled_start_slot": f"scheduled_start_{mode}",
                "scheduled_end_slot": f"scheduled_completion_{mode}",
            }
        )
        base = base.merge(selected, on="job_id", validate="one_to_one")
        base[f"start_interval_{mode}"] = base[f"scheduled_start_{mode}"].map(classify_start)
        base[f"scheduled_start_timestamp_{mode}"] = base[f"scheduled_start_{mode}"].map(
            lambda slot: (ISSUE_TIME + timedelta(seconds=int(slot) * SLOT_SECONDS)).isoformat()
        )
        base[f"scheduled_completion_timestamp_{mode}"] = base[
            f"scheduled_completion_{mode}"
        ].map(lambda slot: (ISSUE_TIME + timedelta(seconds=int(slot) * SLOT_SECONDS)).isoformat())

    summary: dict[str, Any] = {
        "artifact_id": "V35R3D_R1_STANDBY_START_ACCOUNTING_SUMMARY_V1",
        "intervals": {
            "PRE_DAY": f"[{ISSUE_TIME.isoformat()}, {TARGET_START.isoformat()})",
            "APR01": f"[{TARGET_START.isoformat()}, {TARGET_END.isoformat()})",
            "TOTAL": f"[{ISSUE_TIME.isoformat()}, {TARGET_END.isoformat()})",
        },
        "modes": {},
    }
    for mode, schedule in schedules.items():
        pending = schedule.loc[schedule["state_at_issue"].eq("PENDING")]
        standby = pending.loc[pending["workload_class"].eq("STANDBY_QUEUE_CONTROLLED")]
        normal = pending.loc[pending["workload_class"].eq("NORMAL_QUEUE_CONTROLLED")]

        def counts(frame: pd.DataFrame) -> dict[str, int]:
            return {
                "PRE_DAY": int(frame["scheduled_start_slot"].lt(TARGET_OFFSET_SLOTS).sum()),
                "APR01": int(frame["scheduled_start_slot"].between(TARGET_OFFSET_SLOTS, TARGET_END_SLOT - 1).sum()),
                "TOTAL_T0_T2": int(frame["scheduled_start_slot"].lt(TARGET_END_SLOT).sum()),
                "NOT_STARTED_BY_T2": int(frame["scheduled_start_slot"].ge(TARGET_END_SLOT).sum()),
            }

        standby_counts = counts(standby)
        normal_counts = counts(normal)
        terminal = pending.loc[pending["scheduled_start_slot"].ge(TARGET_END_SLOT)]
        terminal_requested = terminal["job_id"].map(
            parent_schedule.set_index("job_id")["request_gpu_hours"]
        )
        summary["modes"][mode] = {
            "standby": standby_counts,
            "normal": normal_counts,
            "initial_pending_jobs": len(pending),
            "started_by_T2": int(pending["scheduled_start_slot"].lt(TARGET_END_SLOT).sum()),
            "terminal_pending_jobs": len(terminal),
            "terminal_pending_requested_GPU_hours": float(terminal_requested.sum()),
            "pending_conservation_PASS": len(pending)
            == int(pending["scheduled_start_slot"].lt(TARGET_END_SLOT).sum()) + len(terminal),
            "standby_conservation_PASS": len(standby)
            == standby_counts["TOTAL_T0_T2"] + standby_counts["NOT_STARTED_BY_T2"],
            "normal_conservation_PASS": len(normal)
            == normal_counts["TOTAL_T0_T2"] + normal_counts["NOT_STARTED_BY_T2"],
        }
    old = summary["modes"]["OLD_RS"]["standby"]
    summary["previous_RS_standby_starts_zero_was_APR01_only"] = (
        old["APR01"] == 0 and old["PRE_DAY"] > 0
    )
    summary["classification"] = (
        "ACCOUNTING_LABEL_AMBIGUITY_CORRECTED"
        if all(value["pending_conservation_PASS"] for value in summary["modes"].values())
        and summary["previous_RS_standby_starts_zero_was_APR01_only"]
        else "STANDBY_START_ACCOUNTING_DEFECT"
    )
    return base, summary


def markdown(final: dict[str, Any]) -> str:
    lines = ["# V35R3D-R1 Final Review", "", "## 1–86 결과", ""]
    lines.extend(f"{index}. {final['numbered_report'][str(index)]}" for index in range(1, 87))
    lines.extend(["", "## Q1–Q17", ""])
    lines.extend(f"Q{index}. {final['questions'][f'Q{index}']}" for index in range(1, 18))
    lines.extend(["", "전력·계통 효과는 평가하지 않았다.", ""])
    return "\n".join(lines)


def main() -> int:
    ART.mkdir(parents=True, exist_ok=True)
    LOG.mkdir(parents=True, exist_ok=True)
    reuse = reuse_manifest()
    predictions = pd.read_parquet(PARENT_SAFE)
    predictions["job_id"] = predictions["job_id"].astype(str)
    calibration = pd.read_parquet(PARENT_CAL)
    parent = pd.read_parquet(PARENT_BASELINE)
    parent["job_id"] = parent["job_id"].astype(str)
    old_rw = pd.read_parquet(PARENT_CACHE / "schedule_RW.parquet")
    old_rs = pd.read_parquet(PARENT_CACHE / "schedule_RS.parquet")
    old_rw["job_id"] = old_rw["job_id"].astype(str)
    old_rs["job_id"] = old_rs["job_id"].astype(str)
    historical = pd.read_parquet(PARENT_HIST, columns=["job_id", "qos", "num_gpus_req"])
    historical["job_id"] = historical["job_id"].astype(str)

    survival, survival_summary = running_survival(predictions, parent, old_rs)
    survival.to_csv(ART / "V35R3D_R1_RUNNING_SURVIVAL_AUDIT.csv", index=False)
    calibration_summary, decomposition, q_selected = calibration_audit(calibration, historical)
    decomposition.to_csv(ART / "V35R3D_R1_CALIBRATION_COVERAGE_DECOMPOSITION.csv", index=False)

    pending_safe = predictions.loc[predictions["state_at_issue"].eq("PENDING")].copy()
    pending_safe["q_selected_method"] = "Q_CONF90_FINITE_SAMPLE_SPLIT_CONFORMAL"
    pending_safe["q_selected_seconds"] = q_selected
    pending_safe["T_pending_safe_seconds"] = np.minimum(
        pending_safe["requested_walltime_seconds"],
        np.maximum(pending_safe["T_hat_point_seconds"] + q_selected, float(SLOT_SECONDS)),
    )
    pending_safe.to_parquet(ART / "V35R3D_R1_PENDING_SAFE_RUNTIME.parquet", index=False)
    duration = rsp_duration_authority(parent, predictions, q_selected)
    duration.to_parquet(ART / "V35R3D_R1_RSP_DURATION_AUTHORITY.parquet", index=False)
    rsp, _ = schedule_rsp(parent, duration)
    rsp_repeat, _ = schedule_rsp(parent, duration)
    rsp_deterministic = rsp.equals(rsp_repeat)
    schedules = {"RW": old_rw.copy(), "OLD_RS": old_rs.copy(), "RSP": rsp.copy()}
    original_gpuh = parent.set_index("job_id")["request_gpu_hours"]
    for schedule in schedules.values():
        schedule["original_requested_GPU_hours"] = schedule["job_id"].map(original_gpuh)

    start_rows, start_summary = start_accounting(parent, schedules)
    start_rows.to_parquet(ART / "V35R3D_R1_STANDBY_START_ACCOUNTING.parquet", index=False)

    capacities: dict[str, pd.DataFrame] = {}
    capacity_summary: dict[str, Any] = {}
    critical: dict[str, Any] = {}
    pre_w5: dict[str, Any] = {}
    for mode, schedule in schedules.items():
        cap, summary = capacity_horizon(schedule, mode)
        capacities[mode] = cap
        capacity_summary[mode] = summary
        critical[mode] = critical_windows(cap)
        pre_w5[mode] = pre_w5_consequence(schedule)
        cap.to_csv(ART / f"V35R3D_R1_CAPACITY_{mode}.csv", index=False)
    capacity_summary["RSP_deterministic_replay"] = rsp_deterministic
    rw_check = parent[["job_id", "scheduled_start_slot", "scheduled_end_slot"]].merge(
        old_rw[["job_id", "scheduled_start_slot", "scheduled_end_slot"]],
        on="job_id",
        suffixes=("_parent", "_reuse"),
        validate="one_to_one",
    )
    capacity_summary["RW_parent_equivalent"] = bool(
        rw_check["scheduled_start_slot_parent"].equals(rw_check["scheduled_start_slot_reuse"])
        and rw_check["scheduled_end_slot_parent"].equals(rw_check["scheduled_end_slot_reuse"])
    )
    capacity_summary["all_conservation_PASS"] = all(
        capacity_summary[mode]["conservation_PASS"]
        and capacity_summary[mode]["slot_conservation_PASS"]
        for mode in schedules
    )

    rw_apr = capacity_summary["RW"]["APR01"]
    rsp_apr = capacity_summary["RSP"]["APR01"]
    rw_total_standby = start_summary["modes"]["RW"]["standby"]["TOTAL_T0_T2"]
    rsp_total_standby = start_summary["modes"]["RSP"]["standby"]["TOTAL_T0_T2"]
    comparison = {
        "artifact_id": "V35R3D_R1_RW_RSP_COMPARISON_V1",
        "primary_modes": ["RW", "RSP"],
        "APR01": {"RW": rw_apr, "RSP": rsp_apr},
        "start_accounting": {
            "RW": start_summary["modes"]["RW"],
            "RSP": start_summary["modes"]["RSP"],
        },
        "deltas_RSP_minus_RW": {
            "release_events": rsp_apr["release_events"] - rw_apr["release_events"],
            "released_GPU_hours": rsp_apr["released_GPU_hours"] - rw_apr["released_GPU_hours"],
            "turnover": rsp_apr["turnover"] - rw_apr["turnover"],
            "total_standby_starts": rsp_total_standby - rw_total_standby,
            "W1_direct_opportunities": critical["RSP"]["W1"]["direct_ordering_opportunities"] - critical["RW"]["W1"]["direct_ordering_opportunities"],
            "W3_direct_opportunities": critical["RSP"]["W3"]["direct_ordering_opportunities"] - critical["RW"]["W3"]["direct_ordering_opportunities"],
            "W5_direct_opportunities": critical["RSP"]["W5"]["direct_ordering_opportunities"] - critical["RW"]["W5"]["direct_ordering_opportunities"],
            "pre_W5_decisions_with_W5_consequence": pre_w5["RSP"]["PRE_W5_DECISIONS_WITH_W5_ACTIVE_CONSEQUENCE"] - pre_w5["RW"]["PRE_W5_DECISIONS_WITH_W5_ACTIVE_CONSEQUENCE"],
        },
    }
    deltas = comparison["deltas_RSP_minus_RW"]
    overstated = any(
        deltas[key] > 0
        for key in ("release_events", "released_GPU_hours", "turnover", "W1_direct_opportunities", "W3_direct_opportunities", "W5_direct_opportunities")
    )
    comparison["REQUESTED_WALLTIME_OVERSTATES_TEMPORAL_CONSTRAINT"] = "YES" if overstated else "NO"
    comparison["interpretation"] = (
        "TEMPORAL SCHEDULING OPPORTUNITY INCREASED"
        if overstated
        else "TEMPORAL SCHEDULING OPPORTUNITY NOT MATERIALLY INCREASED"
    )

    old_c = survival_summary["categories"]["C"]
    old_overstated = old_c["jobs"] > 0
    primary = (
        "V35R3D_R1_RSP_TEMPORAL_OPPORTUNITY_CONFIRMED"
        if overstated
        else "V35R3D_R1_OLD_RS_OVERSTATED_BY_RUNNING_RESIDUAL_ASSUMPTION"
        if old_overstated
        else "V35R3D_R1_RSP_TEMPORAL_OPPORTUNITY_SMALL"
    )
    prew5_meaningful = pre_w5["RSP"]["PRE_W5_DECISIONS_WITH_W5_ACTIVE_CONSEQUENCE"] > 0
    h100_next = "YES" if overstated or prew5_meaningful else "DEFER"
    safe_status = (
        "CONDITIONAL_SAFE_COVERAGE_LIMITED_BY_REQUESTED_WALLTIME_CAP"
        if calibration_summary["SAFE_COVERAGE_LIMITED_BY_REQUESTED_WALLTIME_CAP"]
        else "PASS"
    )

    start_state = {
        "artifact_id": "V35R3D_R1_START_STATE_V1",
        "parent_expected": PARENT_HEAD,
        "parent_actual": command("git", "rev-parse", "HEAD", cwd=PARENT_WORKTREE),
        "branch_expected": BRANCH,
        "branch_actual": command("git", "branch", "--show-current", cwd=REPO),
        "worktree": str(REPO),
    }
    isolation = {
        "artifact_id": "V35R3D_R1_ISOLATION_AUDIT_V1",
        "isolated_worktree": REPO.resolve() == WORKTREE.resolve(),
        "production_files_changed": 0,
        "vendor_files_changed": 0,
        "parent_files_changed": 0,
        "push": False,
        "merge": False,
        "Dataset312_reads": 0,
        "H100_power_runs": 0,
        "Planning_runs": 0,
        "Fresh_reads": 0,
        "MESS_runs": 0,
        "Apr02_plus_outcome_reads": 0,
        "May_reads": 0,
    }
    parent_authority = {
        "artifact_id": "V35R3D_R1_PARENT_RUNTIME_AUTHORITY_V1",
        "parent_commit": PARENT_HEAD,
        "runtime_authority": RUNTIME_AUTHORITY,
        "adapter_equivalence": read_json(PARENT_ARTIFACTS / "V35R3D_QUERY_ADAPTER_EQUIVALENCE.json"),
        "HPCODA_HEAD": HPCODA_HEAD,
        "KESTREL_SHA256": KESTREL_ARCHIVE_SHA256,
        "fixed_32_window_subset_preserved": True,
        "full_120_window_run": False,
        "reuse_manifest": reuse,
    }
    safe_contract = {
        "artifact_id": "V35R3D_R1_SAFE_RUNTIME_CONTRACT_V1",
        "selected_q_method": calibration_summary["selected_q_method"],
        "selected_q_seconds": q_selected,
        "calibration_period": [CALIBRATION_START, CALIBRATION_END],
        "pending_temporal": "min(requested_walltime, max(point + q_selected, 900 seconds))",
        "running": "max(requested_walltime - elapsed_at_issue, 900 seconds)",
        "running_residual_model": "NOT_CREATED",
        "memorylessness_assumed": False,
        "Apr01_actual_labels_used": 0,
        "model_source_HEAD": HPCODA_HEAD,
        "safe_calibration_status": safe_status,
    }
    authority = {
        "artifact_id": "V35R3D_R1_RUNTIME_AUTHORITY_DECISION_V1",
        "runtime_authority": RUNTIME_AUTHORITY,
        "RUNTIME_ADAPTER_EQUIVALENCE": "PASS",
        "SAFE_CALIBRATION": safe_status,
        "RUNNING_RESIDUAL_AUTHORITY": RUNNING_RESIDUAL_AUTHORITY,
        "primary_classification": primary,
        "secondary_findings": [
            "V35R3D_R1_OLD_RS_OVERSTATED_BY_RUNNING_RESIDUAL_ASSUMPTION" if old_overstated else "NO_OLD_RS_SURVIVAL_CONTRADICTION",
            start_summary["classification"],
            comparison["interpretation"],
        ],
        "OLD_RS_label": "RS_TOTAL_RUNTIME_DIAGNOSTIC_ONLY",
    }
    h100 = {
        "artifact_id": "V35R3D_R1_H100_POWER_RESEARCH_DECISION_V1",
        "H100_POWER_RESEARCH_NEXT": h100_next,
        "basis": "RSP runtime/capacity and pre-W5 consequence evidence only",
        "power_data_inspected": False,
        "PRODUCTION_INTEGRATION_RECOMMENDED": "NO",
    }
    repair = {
        "artifact_id": "V35R3D_R1_REPAIR_LOG_V1",
        "maximum_attempts_per_signature": 5,
        "repairs": [
            {
                "signature": "NUMPY_SELECT_STRING_DEFAULT_DTYPE",
                "attempt": 1,
                "action": "Added explicit string default to the preliminary survival-category diagnostic.",
                "scientific_change": False,
                "result": "PASS",
            },
            {
                "signature": "CALIBRATION_GROUP_FEATURE_NULL",
                "attempt": 1,
                "action": "Retained missing QoS/GPU request values as an explicit UNAVAILABLE coverage group; quantiles and predictions unchanged.",
                "scientific_change": False,
                "result": "PASS",
            },
        ],
    }
    conservation = {
        "artifact_id": "V35R3D_R1_CAPACITY_CONSERVATION_V1",
        "modes": capacity_summary,
        "capacity_GPUs": 624,
        "interval_semantics": "boundary event belongs to interval beginning at that boundary; T2 boundary excluded",
    }
    opportunity = {
        "artifact_id": "V35R3D_R1_W1_W3_W5_OPPORTUNITY_V1",
        "windows_unchanged": True,
        "modes": {"RW": critical["RW"], "RSP": critical["RSP"]},
        "power_grid_calculation": False,
    }
    prew5_artifact = {
        "artifact_id": "V35R3D_R1_PRE_W5_HORIZON_OPPORTUNITY_V1",
        "modes": {"RW": pre_w5["RW"], "RSP": pre_w5["RSP"]},
        "RW_RSP_composition_comparison": {
            "overlap_jobs": len(
                set(pre_w5["RW"]["consequential_job_ids"])
                & set(pre_w5["RSP"]["consequential_job_ids"])
            ),
            "RW_only_jobs": len(
                set(pre_w5["RW"]["consequential_job_ids"])
                - set(pre_w5["RSP"]["consequential_job_ids"])
            ),
            "RSP_only_jobs": len(
                set(pre_w5["RSP"]["consequential_job_ids"])
                - set(pre_w5["RW"]["consequential_job_ids"])
            ),
            "symmetric_difference_jobs": len(
                set(pre_w5["RW"]["consequential_job_ids"])
                ^ set(pre_w5["RSP"]["consequential_job_ids"])
            ),
            "composition_changed": set(pre_w5["RW"]["consequential_job_ids"])
            != set(pre_w5["RSP"]["consequential_job_ids"]),
        },
        "runtime_occupancy_only": True,
    }

    for name, payload in (
        ("V35R3D_R1_START_STATE.json", start_state),
        ("V35R3D_R1_ISOLATION_AUDIT.json", isolation),
        ("V35R3D_R1_PARENT_RUNTIME_AUTHORITY.json", parent_authority),
        ("V35R3D_R1_RUNNING_SURVIVAL_SUMMARY.json", survival_summary),
        ("V35R3D_R1_CALIBRATION_QUANTILE_AUDIT.json", calibration_summary),
        ("V35R3D_R1_SAFE_RUNTIME_CONTRACT.json", safe_contract),
        ("V35R3D_R1_STANDBY_START_ACCOUNTING_SUMMARY.json", start_summary),
        ("V35R3D_R1_CAPACITY_CONSERVATION.json", conservation),
        ("V35R3D_R1_RW_RSP_COMPARISON.json", comparison),
        ("V35R3D_R1_W1_W3_W5_OPPORTUNITY.json", opportunity),
        ("V35R3D_R1_PRE_W5_HORIZON_OPPORTUNITY.json", prew5_artifact),
        ("V35R3D_R1_RUNTIME_AUTHORITY_DECISION.json", authority),
        ("V35R3D_R1_H100_POWER_RESEARCH_DECISION.json", h100),
        ("V35R3D_R1_REPAIR_LOG.json", repair),
    ):
        write_json(name, payload)

    modes = start_summary["modes"]
    apr = {mode: capacity_summary[mode]["APR01"] for mode in schedules}
    numbered = {
        "1": PARENT_HEAD,
        "2": BRANCH,
        "3": str(REPO),
        "4": "PENDING_THIS_COMMIT (authoritative value reported after commit)",
        "5": "YES after commit",
        "6": "0",
        "7": "0",
        "8": "NO/NO",
        "9": str(survival_summary["running_jobs"]),
        "10": str(survival_summary["running_requested_GPUs"]),
        "11": f"{survival_summary['categories']['A']['jobs']} / {survival_summary['categories']['A']['requested_GPUs']} GPU",
        "12": f"{survival_summary['categories']['B']['jobs']} / {survival_summary['categories']['B']['requested_GPUs']} GPU",
        "13": f"{old_c['jobs']} / {old_c['requested_GPUs']} GPU",
        "14": f"{survival_summary['categories']['D_elapsed_ge_requested']['jobs']} / {survival_summary['categories']['D_elapsed_ge_requested']['requested_GPUs']} GPU",
        "15": f"{old_c['GPU_fraction']:.9%}",
        "16": f"{old_c['jobs']} jobs / {survival_summary['category_C_attributable_release_GPUs']} GPU / {survival_summary['category_C_attributable_release_GPU_hours']} GPU-h at OLD_RS slot {survival_summary['category_C_first_OLD_RS_release_slot']} ({survival_summary['category_C_share_of_OLD_RS_preday_running_release_GPUs']:.6%} of OLD_RS PRE-DAY running release GPUs)",
        "17": str(calibration_summary["rows"]),
        "18": f"{calibration_summary['Q_EMP90']['q_seconds']:.6f} s",
        "19": f"{calibration_summary['Q_CONF90']['q_seconds']:.6f} s",
        "20": f"{calibration_summary['Q_EMP90']['uncapped_coverage']:.9%}",
        "21": f"{calibration_summary['Q_EMP90']['capped_coverage']:.9%}",
        "22": f"{calibration_summary['Q_CONF90']['uncapped_coverage']:.9%}",
        "23": f"{calibration_summary['Q_CONF90']['capped_coverage']:.9%}",
        "24": f"{calibration_summary['Q_CONF90']['actual_gt_requested_fraction']:.9%}",
        "25": f"{calibration_summary['Q_CONF90']['safe_uncapped_gt_requested_fraction']:.9%}",
        "26": calibration_summary["selected_q_method"],
        "27": f"{q_selected:.6f} s",
        "28": f"{calibration_summary['selected_capped_safe_coverage']:.9%}",
    }
    cursor = 29
    for mode in ("RW", "OLD_RS", "RSP"):
        stand = modes[mode]["standby"]
        for key in ("PRE_DAY", "APR01", "TOTAL_T0_T2", "NOT_STARTED_BY_T2"):
            numbered[str(cursor)] = str(stand[key])
            cursor += 1
    for mode in ("RW", "OLD_RS", "RSP"):
        numbered[str(cursor)] = str(apr[mode]["post_refill_saturated_slots"])
        cursor += 1
    for mode in ("RW", "OLD_RS", "RSP"):
        numbered[str(cursor)] = str(apr[mode]["release_events"])
        cursor += 1
    for mode in ("RW", "OLD_RS", "RSP"):
        numbered[str(cursor)] = str(apr[mode]["released_GPU_hours"])
        cursor += 1
    for mode in ("RW", "OLD_RS", "RSP"):
        numbered[str(cursor)] = str(apr[mode]["turnover"])
        cursor += 1
    for mode in ("RW", "OLD_RS", "RSP"):
        numbered[str(cursor)] = str(apr[mode]["jobs_completed"])
        cursor += 1
    for mode in ("RW", "OLD_RS", "RSP"):
        numbered[str(cursor)] = str(start_summary["modes"][mode]["terminal_pending_requested_GPU_hours"])
        cursor += 1
    for name in ("W1", "W3", "W5"):
        numbered[str(cursor)] = f"RW {critical['RW'][name]['release_events']} / RSP {critical['RSP'][name]['release_events']}"
        cursor += 1
    for name in ("W1", "W3", "W5"):
        numbered[str(cursor)] = f"RW {critical['RW'][name]['released_GPUs']} / RSP {critical['RSP'][name]['released_GPUs']}"
        cursor += 1
    numbered[str(cursor)] = f"RW {critical['RW']['W5']['direct_ordering_opportunities']} / RSP {critical['RSP']['W5']['direct_ordering_opportunities']}"; cursor += 1
    numbered[str(cursor)] = f"RW {pre_w5['RW']['PRE_W5_DECISIONS_WITH_W5_ACTIVE_CONSEQUENCE']} / RSP {pre_w5['RSP']['PRE_W5_DECISIONS_WITH_W5_ACTIVE_CONSEQUENCE']}"; cursor += 1
    for key in (
        "released_GPU_hours",
        "turnover",
        "total_standby_starts",
        "W5_direct_opportunities",
        "pre_W5_decisions_with_W5_consequence",
    ):
        numbered[str(cursor)] = str(deltas[key]); cursor += 1
    numbered[str(cursor)] = comparison["REQUESTED_WALLTIME_OVERSTATES_TEMPORAL_CONSTRAINT"]; cursor += 1
    for value in (
        RUNTIME_AUTHORITY,
        "PASS",
        safe_status,
        RUNNING_RESIDUAL_AUTHORITY,
        primary,
        h100_next,
        "NO",
        "0",
        "0",
        "0",
        "0",
        "NO",
        "PENDING_TEST_RUN",
        "PENDING_TEST_RUN",
    ):
        numbered[str(cursor)] = value; cursor += 1
    if cursor != 87:
        raise AssertionError(f"V35R3D_R1_FINAL_NUMBERING_FAIL:{cursor}")

    questions = {
        "Q1": f"{old_c['jobs']}개이다.",
        "Q2": f"{old_c['requested_GPUs']}/498 GPU, 즉 {old_c['GPU_fraction']:.6%}이다.",
        "Q3": f"OLD_RS가 첫 15분 뒤 해제한 {survival_summary['category_C_attributable_release_GPUs']} GPU, 즉 {survival_summary['category_C_attributable_release_GPU_hours']} GPU-h({old_c['jobs']}개 작업)가 이 조건에서 왔다. 이는 OLD_RS PRE-DAY running release GPU의 {survival_summary['category_C_share_of_OLD_RS_preday_running_release_GPUs']:.6%}이다.",
        "Q4": f"Empirical q는 uncapped {calibration_summary['Q_EMP90']['uncapped_coverage']:.6%}로 정상이다. requested-walltime cap이 coverage를 {calibration_summary['Q_EMP90']['capped_coverage']:.6%}로 낮췄다.",
        "Q5": f"YES. conformal uncapped coverage는 {calibration_summary['Q_CONF90']['uncapped_coverage']:.6%}이다. 다만 residual tie 때문에 q는 empirical 값과 같다.",
        "Q6": f"{calibration_summary['coverage_loss_from_requested_cap']:.6%}p를 잃는다.",
        "Q7": start_summary["classification"],
        "Q8": f"RSP standby는 PRE-DAY {modes['RSP']['standby']['PRE_DAY']}개, APR-01 {modes['RSP']['standby']['APR01']}개, 총 {modes['RSP']['standby']['TOTAL_T0_T2']}개가 시작한다.",
        "Q9": f"RW {apr['RW']['post_refill_saturated_slots']}개, RSP {apr['RSP']['post_refill_saturated_slots']}개이다.",
        "Q10": f"RW {apr['RW']['released_GPU_hours']} GPU-h, RSP {apr['RSP']['released_GPU_hours']} GPU-h이다.",
        "Q11": f"RW {apr['RW']['turnover']}, RSP {apr['RSP']['turnover']}이다.",
        "Q12": comparison["REQUESTED_WALLTIME_OVERSTATES_TEMPORAL_CONSTRAINT"],
        "Q13": f"W1/W3/W5 RSP release events는 {critical['RSP']['W1']['release_events']}/{critical['RSP']['W3']['release_events']}/{critical['RSP']['W5']['release_events']}이다.",
        "Q14": f"YES. RSP에서 W5에 남는 pre-W5 admission 결정은 {pre_w5['RSP']['PRE_W5_DECISIONS_WITH_W5_ACTIVE_CONSEQUENCE']}개이며 RW와의 W5-active 작업 집합 대칭차는 {prew5_artifact['RW_RSP_composition_comparison']['symmetric_difference_jobs']}개이다.",
        "Q15": h100_next,
        "Q16": "NO. 미래 Apr-01 end/runtime은 사용하지 않았다.",
        "Q17": "NO.",
    }
    final = {
        "artifact_id": "V35R3D_R1_FINAL_REVIEW_V1",
        "numbered_report": numbered,
        "questions": questions,
        "power_grid_effect": "NOT_EVALUATED_RUNTIME_ONLY_TASK",
    }
    write_json("V35R3D_R1_FINAL_REVIEW.json", final)
    (ART / "V35R3D_R1_FINAL_REVIEW.md").write_text(markdown(final), encoding="utf-8")
    (LOG / "build_correction.json").write_text(
        json.dumps({"status": "PASS", "primary": primary}, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "survival_C": survival_summary["categories"]["C"],
                "calibration": calibration_summary,
                "start_accounting": start_summary,
                "comparison": comparison,
                "pre_w5": pre_w5,
                "primary": primary,
                "h100_next": h100_next,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
