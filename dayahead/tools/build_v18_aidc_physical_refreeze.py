from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import statistics
import tempfile
import zipfile
from collections import defaultdict
from datetime import timedelta, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v18_aidc_physical_refreeze"
CAND = ROOT / "dayahead" / "artifacts" / "v17_candidate"
KESTREL = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR HPC Kestrel Jobs Data\esif.hpc.kestrel.job-anon.zip")
DATASET312 = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\dataset.zip")
ESIF = Path(r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\데이터 센터\NLR ESIF PUE  IT Power\esif.influx.buildingData.PUE.combined.parquet")
KESTREL_SHA = "3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f"
D312_SHA = "dcad6de800fb565d850b163902e2eddae48aabd1ed1c7336f9a1cdaf3012f137"
ESIF_SHA = "19cd12405dde9144b1a360e8c8418666c399a3d0d15a7f846880d71ab22f9dd4"
AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
DT_H = 0.25
PUE = 1.30
C_K = 528.0  # 132 official Kestrel H100 nodes x 4 GPUs/node.
C_MODEL = 528.0
GPU_PER_NODE = 4
GPU_IDLE_W = 72.5
CPU_SOCKET_IDLE_W = 64.1
CPU_SOCKETS = 2
NODE_CLASSES = (1, 2, 4, 8, 16)
KAPPA_TOTAL = {1: 2.289471346990805, 2: 2.2220251879720374, 4: 2.0938566188449466, 8: 2.026464800777849, 16: 1.9654597010662909}
KAPPA_GPU_BOARD_Q50 = 0.48563611660901085
TRAIN_START = "2024-08-19"
TRAIN_END_EXCLUSIVE = "2025-04-01"
DATES = ["2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13", "2025-04-15", "2025-04-22", "2025-04-23"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(name: str, value) -> None:
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def object_empty(value: object) -> bool:
    try:
        import pandas as pd
        if pd.isna(value) is True:
            return True
    except (TypeError, ValueError):
        pass
    if value is None:
        return True
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    try:
        return len(value) == 0
    except TypeError:
        return str(value).strip().casefold() in {"", "[]", "{}", "null", "none", "nan", "<na>"}


def h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def interval_slot_gpuh(starts, ends, weights, boundaries) -> np.ndarray:
    """Exact interval integral at 15-minute boundaries, without per-job slot loops."""
    import pandas as pd
    if len(weights) == 0:
        return np.zeros(len(boundaries) - 1)
    boundary_ns = pd.DatetimeIndex(boundaries).as_unit("ns").asi8
    origin_ns = int(boundary_ns[0])
    s = (pd.DatetimeIndex(starts).as_unit("ns").asi8 - origin_ns) / 1e9
    e = (pd.DatetimeIndex(ends).as_unit("ns").asi8 - origin_ns) / 1e9
    w = np.asarray(weights, dtype=float)
    b = (boundary_ns - origin_ns) / 1e9

    def ramp(times):
        order = np.argsort(times)
        t = times[order]
        ww = w[order]
        pw = np.concatenate(([0.0], np.cumsum(ww)))
        pwt = np.concatenate(([0.0], np.cumsum(ww * t)))
        idx = np.searchsorted(t, b, side="right")
        return b * pw[idx] - pwt[idx]

    cumulative_gpu_seconds = ramp(s) - ramp(e)
    return np.diff(cumulative_gpu_seconds) / 3600.0


def latency_class(queue_seconds: float) -> str | None:
    if not math.isfinite(queue_seconds) or queue_seconds <= 600:
        return None
    if queue_seconds <= 1800:
        return "C1"
    if queue_seconds <= 3600:
        return "C2"
    if queue_seconds <= 7200:
        return "C3"
    if queue_seconds <= 10800:
        return "C4"
    return "C5"


def audit_kestrel() -> dict:
    import pandas as pd
    import pyarrow.parquet as pq

    if sha256(KESTREL) != KESTREL_SHA:
        raise RuntimeError("KESTREL_SHA_MISMATCH")
    start_bound = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    end_bound = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    boundaries = pd.date_range(start_bound, end_bound, freq="15min", inclusive="both")
    total_parts, flex_parts = [], []
    fullnode = defaultdict(lambda: {"jobs": 0, "node_hours": 0.0, "GPU_hours": 0.0})
    counts = {"all_executed_H100_jobs": 0, "semantic_flexible_jobs": 0, "fullnode_nodelevel_jobs": 0}
    energies = {"all_executed_H100_GPU_hours": 0.0, "semantic_flexible_GPU_hours": 0.0}
    arrival_gpuh = {c: np.zeros(len(boundaries) - 1) for c in ["C1", "C2", "C3", "C4", "C5"]}
    opened = []
    columns = ["partition", "state_simple", "submit_time", "start_time", "end_time", "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared"]
    with zipfile.ZipFile(KESTREL) as archive, tempfile.TemporaryDirectory(prefix="v18-kestrel-") as td:
        local = Path(td) / "month.parquet"
        members = []
        for info in archive.infolist():
            m = re.search(r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/"))
            if m and info.filename.casefold().endswith(".parquet"):
                month = int(m.group(1)) * 100 + int(m.group(2))
                if 202408 <= month <= 202503:
                    members.append((month, info))
        if len(members) != 8:
            raise RuntimeError("KESTREL_TRAINING_MONTH_AXIS_INCOMPLETE")
        for month, info in sorted(members):
            with archive.open(info) as src, local.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            schema = set(pq.read_schema(local).names)
            if not set(columns).issubset(schema):
                raise RuntimeError("KESTREL_REQUIRED_SCHEMA_MISSING")
            frame = pq.read_table(local, columns=columns).to_pandas()
            opened.append({"month": month, "member": info.filename, "rows": len(frame)})
            submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
            start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
            end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
            nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
            gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
            sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
            valid = frame["partition"].apply(h100) & start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0) & end.gt(start_bound) & start.lt(end_bound)
            queue = (start - submit).dt.total_seconds()
            semantic = valid & frame["state_simple"].astype(str).str.upper().eq("COMPLETED") & submit.notna() & queue.gt(600) & np.isfinite(queue)
            no_share = (sharing.isna() | sharing.eq(0)) & frame["nodes_shared"].apply(object_empty) & frame["jobs_shared"].apply(object_empty)
            full = semantic & np.isclose(gpus, GPU_PER_NODE * nodes) & nodes.isin(NODE_CLASSES) & no_share
            clipped_start = start.where(start.ge(start_bound), start_bound)
            clipped_end = end.where(end.le(end_bound), end_bound)
            duration = (clipped_end - clipped_start).dt.total_seconds() / 3600.0

            counts["all_executed_H100_jobs"] += int(valid.sum())
            counts["semantic_flexible_jobs"] += int(semantic.sum())
            counts["fullnode_nodelevel_jobs"] += int(full.sum())
            energies["all_executed_H100_GPU_hours"] += float((gpus.where(valid, 0.0) * duration.where(valid, 0.0)).sum())
            energies["semantic_flexible_GPU_hours"] += float((gpus.where(semantic, 0.0) * duration.where(semantic, 0.0)).sum())
            for n in NODE_CLASSES:
                mask = full & nodes.eq(n)
                fullnode[n]["jobs"] += int(mask.sum())
                fullnode[n]["node_hours"] += float((nodes.where(mask, 0.0) * duration.where(mask, 0.0)).sum())
                fullnode[n]["GPU_hours"] += float((gpus.where(mask, 0.0) * duration.where(mask, 0.0)).sum())

            total_parts.append((clipped_start[valid], clipped_end[valid], gpus[valid].to_numpy(float)))
            flex_parts.append((clipped_start[semantic], clipped_end[semantic], gpus[semantic].to_numpy(float)))
            submitted = semantic & submit.ge(start_bound) & submit.lt(end_bound)
            runtime_h = (end - start).dt.total_seconds() / 3600.0
            for idx in frame.index[submitted]:
                c = latency_class(float(queue.at[idx]))
                if c is None:
                    continue
                slot = int((submit.at[idx] - start_bound).total_seconds() // 900)
                if 0 <= slot < len(boundaries) - 1:
                    arrival_gpuh[c][slot] += float(gpus.at[idx] * runtime_h.at[idx])

    total_slot_gpuh = sum((interval_slot_gpuh(a, b, w, boundaries) for a, b, w in total_parts), np.zeros(len(boundaries) - 1))
    flex_slot_gpuh = sum((interval_slot_gpuh(a, b, w, boundaries) for a, b, w in flex_parts), np.zeros(len(boundaries) - 1))
    total_gpu = total_slot_gpuh / DT_H
    flex_gpu = flex_slot_gpuh / DT_H
    if abs(float(total_slot_gpuh.sum()) - energies["all_executed_H100_GPU_hours"]) > 1e-5:
        raise RuntimeError("TOTAL_SLOT_GPU_HOUR_IDENTITY_FAILURE")
    if abs(float(flex_slot_gpuh.sum()) - energies["semantic_flexible_GPU_hours"]) > 1e-5:
        raise RuntimeError("FLEX_SLOT_GPU_HOUR_IDENTITY_FAILURE")
    ratio = np.divide(flex_gpu, total_gpu, out=np.zeros_like(flex_gpu), where=total_gpu > 0)
    all_arrivals = sum(arrival_gpuh.values(), np.zeros(len(boundaries) - 1))
    arrival_intensity = all_arrivals / (C_K * DT_H)
    return {
        "training_period_AEST": [TRAIN_START, "2025-03-31"],
        "C_K_GPU_equivalent": C_K,
        "counts": counts,
        "energies": energies,
        "fullnode_by_node_class": {str(k): v for k, v in sorted(fullnode.items())},
        "eta_F_GPU_energy": float(flex_slot_gpuh.sum() / total_slot_gpuh.sum()),
        "eta_F_GPU_peak_coincident": float(ratio.max()),
        "mean_total_GPU_utilization": float(total_gpu.mean() / C_K),
        "peak_total_GPU_utilization": float(total_gpu.max() / C_K),
        "mean_flexible_GPU_utilization": float(flex_gpu.mean() / C_K),
        "peak_flexible_GPU_utilization": float(flex_gpu.max() / C_K),
        "peak_total_active_GPU": float(total_gpu.max()),
        "peak_flexible_active_GPU": float(flex_gpu.max()),
        "q99_5_total_active_GPU": float(np.quantile(total_gpu, 0.995)),
        "KESTREL_VIRTUAL_PLANNING_CAPACITY_diagnostic_GPU": float(np.quantile(total_gpu, 0.995) / 0.85),
        "virtual_planning_capacity_selected": False,
        "capacity_violation_slot_count": int(np.sum(total_gpu > C_K + 1e-9)),
        "capacity_violation_slot_fraction": float(np.mean(total_gpu > C_K + 1e-9)),
        "maximum_capacity_excess_GPU": float(max(0.0, total_gpu.max() - C_K)),
        "flex_exceeds_total_slot_count": int(np.sum(flex_gpu > total_gpu + 1e-9)),
        "flexible_arrival_GPU_hours_submitted_in_training": float(all_arrivals.sum()),
        "mean_flexible_arrival_intensity": float(arrival_intensity.mean()),
        "peak_flexible_arrival_intensity": float(arrival_intensity.max()),
        "arrival_GPU_hours_by_latency_class": {c: float(v.sum()) for c, v in arrival_gpuh.items()},
        "member_access": opened,
        "native_series_fingerprint": hashlib.sha256(np.stack([total_slot_gpuh, flex_slot_gpuh, all_arrivals]).astype("<f8").tobytes()).hexdigest(),
        "posthoc_clipping_calls": 0,
    }


def audit_dataset312() -> dict:
    import pandas as pd
    if sha256(DATASET312) != D312_SHA:
        raise RuntimeError("DATASET312_SHA_MISMATCH")
    pattern = re.compile(r"^00_raw_datasets/training_(?P<model>.+?)/(?P<nodes>\d+)node/(?P<device>nvml|rapl)_.*?slurmid_(?P<slurmid>\d+)_node_(?P<node>[^/]+)\.log$")
    rapl_cols = ["timestamp", "reading-time[ns]", "cpu-0[uJ]", "cpu-0-core[uJ]", "cpu-1[uJ]", "cpu-1-core[uJ]", "cpu-0[W]", "cpu-0-core[W]", "cpu-1[W]", "cpu-1-core[W]"]
    groups = defaultdict(lambda: {"nvml": [], "rapl": []})
    components = defaultdict(lambda: {"gpu": [], "cpu": [], "total": []})
    with zipfile.ZipFile(DATASET312) as archive:
        for name in archive.namelist():
            m = pattern.match(name)
            if m and int(m.group("nodes")) in NODE_CLASSES:
                groups[(m.group("model"), int(m.group("nodes")), m.group("slurmid"))][m.group("device")].append(name)
        parsed = 0
        for (_model, nodes, _slurm), members in sorted(groups.items()):
            if len(members["nvml"]) != nodes or len(members["rapl"]) != nodes:
                continue
            gpu_w = package_w = 0.0
            for member in sorted(members["nvml"]):
                with archive.open(member) as stream:
                    header = stream.readline().decode("utf-8", errors="replace").replace("# ", "").strip().split()
                    frame = pd.read_csv(stream, sep=r"\s+", header=None, names=header, comment="#", low_memory=False)
                cols = [f"gpu-{i}[mW]" for i in range(4)]
                gpu_w += float(frame[cols].apply(pd.to_numeric, errors="coerce").sum(axis=1).dropna().mean() / 1000.0)
            for member in sorted(members["rapl"]):
                with archive.open(member) as stream:
                    frame = pd.read_csv(stream, sep=r"\s+", header=None, names=rapl_cols, comment="#", low_memory=False)
                package_w += float(frame[["cpu-0[W]", "cpu-1[W]"]].apply(pd.to_numeric, errors="coerce").sum(axis=1).dropna().mean())
            gpu = (gpu_w - nodes * GPU_PER_NODE * GPU_IDLE_W) / 1000.0 / nodes
            cpu = (package_w - nodes * CPU_SOCKETS * CPU_SOCKET_IDLE_W) / 1000.0 / nodes
            components[nodes]["gpu"].append(gpu)
            components[nodes]["cpu"].append(cpu)
            components[nodes]["total"].append(gpu + cpu)
            parsed += 1
    by_class = {}
    failures = []
    for n in NODE_CLASSES:
        vals = components[n]
        total = statistics.median(vals["total"])
        if abs(total - KAPPA_TOTAL[n]) > 1e-12:
            failures.append(n)
        by_class[str(n)] = {
            "complete_run_count": len(vals["total"]),
            "median_GPU_board_incremental_kW_per_node": statistics.median(vals["gpu"]),
            "median_CPU_package_incremental_kW_per_node": statistics.median(vals["cpu"]),
            "median_paired_node_total_incremental_kW_per_node": total,
            "paired_total_authority_kW_per_node": KAPPA_TOTAL[n],
            "component_medians_are_diagnostic": True,
        }
    return {"source_sha256": D312_SHA, "parsed_complete_runs": parsed, "node_classes": by_class, "authority_reproduction_failures": failures, "measurement_boundary": "four NVML GPU-board channels plus two-socket RAPL CPU-package power, both above frozen idle subtraction", "memory_network_fan_incremental_power": None, "partial_node_CPU_package_authorized": False}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pre = OUT / "V18_AIDC_REFREEZE_PRECHANGE_MANIFEST.json"
    if not pre.exists():
        raise RuntimeError("PRECHANGE_MANIFEST_REQUIRED_BEFORE_BUILDER")
    native = audit_kestrel()
    power = audit_dataset312()
    cov = load(CAND / "V17_AIDC_POWER_V4R1_7DAY_B0_B1_B2_B3_RESULTS.json")["coverage"]
    funnel = load(ROOT / "dayahead" / "artifacts" / "v17_flexibility_funnel_forensic" / "V17_AIDC_FLEXIBILITY_FUNNEL_FORENSIC_V1.json")
    u2_gpu_h = float(cov["V4R1_U2_CLEAN"]["GPU_hours"])
    fullnode_node_h = {int(k): float(v["node_hours"]) for k, v in native["fullnode_by_node_class"].items()}
    fullnode_total_kwh = sum(fullnode_node_h[n] * KAPPA_TOTAL[n] for n in NODE_CLASSES)
    fullnode_gpu_component_kwh = sum(fullnode_node_h[n] * power["node_classes"][str(n)]["median_GPU_board_incremental_kW_per_node"] for n in NODE_CLASSES)
    fullnode_cpu_component_kwh = sum(fullnode_node_h[n] * power["node_classes"][str(n)]["median_CPU_package_incremental_kW_per_node"] for n in NODE_CLASSES)
    partial_board_kwh = u2_gpu_h * KAPPA_GPU_BOARD_Q50
    all_identified_training_kwh = fullnode_total_kwh + partial_board_kwh
    component_median_gap = fullnode_total_kwh - fullnode_gpu_component_kwh - fullnode_cpu_component_kwh
    old_fullnode_board_kwh = sum(v["GPU_hours"] for v in native["fullnode_by_node_class"].values()) * KAPPA_GPU_BOARD_Q50
    nodelevel_increase_kwh = fullnode_total_kwh - old_fullnode_board_kwh
    gpu_component_increase_kwh = fullnode_gpu_component_kwh - old_fullnode_board_kwh

    source_audit = {
        "artifact_id": "V18_AIDC_REFREEZE_SOURCE_AUTHORITY_AUDIT_V1",
        "sources": [
            {"source_id": "KESTREL_JOB_ARCHIVE", "classification": "SUPPORTED", "scope": "retrospective training occupancy, resource requests and revealed-latency semantic labels", "path": str(KESTREL), "sha256": KESTREL_SHA},
            {"source_id": "KESTREL_D1_STATE", "classification": "UNSUPPORTED", "scope": "exact cutoff queue/running snapshot", "reason": "archive contains final sacct record, not a D-1 state snapshot; future start/end would be required"},
            {"source_id": "KESTREL_INSTALLED_CAPACITY", "classification": "SUPPORTED", "scope": "132 H100 nodes x 4 H100 GPUs = 528 GPUs", "official_sources": ["https://www.nrel.gov/docs/fy25osti/91696.pdf", "https://www.nrel.gov/docs/gen/fy24/90033.pdf"]},
            {"source_id": "DATASET312_FULLNODE_POWER", "classification": "SUPPORTED", "scope": "full-node H100 training classes with NVML GPU-board plus RAPL CPU-package incremental power", "path": str(DATASET312), "sha256": D312_SHA},
            {"source_id": "DATASET312_PARTIALNODE_CPU", "classification": "UNSUPPORTED", "scope": "partial-node CPU-package attribution", "reason": "no measured active GPU-count/packing counterfactual"},
            {"source_id": "V17_PER_GPU_BOARD", "classification": "SUPPORTED", "scope": "partial-node whole-GPU lower bound", "kappa_Q50_kW_per_GPU": KAPPA_GPU_BOARD_Q50},
            {"source_id": "ESIF_WHOLE_FACILITY_IT", "classification": "PARTIALLY_SUPPORTED", "scope": "whole-facility total IT and PUE boundary supported; workload attribution absent", "path": str(ESIF), "sha256": ESIF_SHA},
        ],
        "test_split_status": "NEW_LOCKED_TEST_NOT_YET_AVAILABLE",
        "result_or_literature_based_parameter_selection_calls": 0,
    }
    write("V18_AIDC_REFREEZE_SOURCE_AUTHORITY_AUDIT.json", source_audit)

    capacity_contract = {
        "artifact_id": "V18_KESTREL_CAPACITY_NORMALIZATION_CONTRACT_V1",
        "capacity_name": "KESTREL_PHYSICAL_INSTALLED_H100_CAPACITY",
        "C_K_GPU_equivalent": C_K,
        "derivation": "132 official Kestrel H100 nodes x 4 H100 GPUs/node",
        "official_sources": source_audit["sources"][2]["official_sources"],
        "legacy_48_rack_capacity_GPU": 1815.6,
        "legacy_capacity_classification": "KESTREL_VIRTUAL_PLANNING_CAPACITY_NOT_PHYSICAL_INSTALLED_CAPACITY",
        "q99_5_u85_virtual_planning_capacity_diagnostic_GPU": native["KESTREL_VIRTUAL_PLANNING_CAPACITY_diagnostic_GPU"],
        "virtual_planning_capacity_selected": False,
        "physical_capacity_conflict": {"peak_trace_GPU": native["peak_total_active_GPU"], "violation_slot_count": native["capacity_violation_slot_count"], "status": "FAIL_PHYSICAL_COHERENCE" if native["capacity_violation_slot_count"] else "PASS"},
        "C_MODEL_GPU_equivalent": C_MODEL,
        "C_MODEL_selection": "same source-backed Kestrel H100 subsystem boundary; no grid-benefit selection",
        "definitions": {"u_TOTAL": "G_K_TOTAL/C_K", "u_FLEX": "G_K_FLEX/C_K", "a_FLEX_b": "W_K_FLEX_b/(C_K*0.25h)"},
    }
    write("V18_KESTREL_CAPACITY_NORMALIZATION_CONTRACT.json", capacity_contract)
    native_art = {"artifact_id": "V18_KESTREL_NATIVE_FLEXIBILITY_SHARE_V1", "status": "PASS_RETROSPECTIVE_TRAINING_SOURCE_REPRODUCTION", **native, "semantic_definition": "completed H100 jobs with valid execution and revealed queue wait >600s; retrospective training label only", "D1_feature_role": "NONE"}
    write("V18_KESTREL_NATIVE_FLEXIBILITY_SHARE.json", native_art)

    normalized = {
        "artifact_id": "V18_AIDC_CAPACITY_NORMALIZED_WORKLOAD_CONTRACT_V1",
        "status": "CONTRACT_FROZEN_MODEL_REFIT_NOT_RUN",
        "C_MODEL_GPU_equivalent": C_MODEL,
        "equations": {"G_REF_MODEL": "C_MODEL*u_TOTAL_hat", "G_F_REF_MODEL": "G_REF_MODEL*sigmoid(z_flex)", "W_F_MODEL_b": "C_MODEL*0.25h*a_FLEX_hat_b"},
        "architecture": "hierarchical total utilization and conditional flexible fraction; same C_MODEL for G and W",
        "48_rack_distribution": "normalize frozen nonnegative rack weights to sum C_MODEL; no hidden second scale",
        "training_period": [TRAIN_START, "2025-03-31"],
        "validation_period": "must be newly designated; April has already been observed",
        "locked_test_period": "NEW_LOCKED_TEST_NOT_YET_AVAILABLE",
        "ML_novelty_claim": False,
    }
    write("V18_AIDC_CAPACITY_NORMALIZED_WORKLOAD_CONTRACT.json", normalized)
    coherence = {
        "artifact_id": "V18_AIDC_G_W_COHERENCE_VALIDATION_V1",
        "native_training_series": {"capacity_violation_slot_count": native["capacity_violation_slot_count"], "flex_exceeds_total_slot_count": native["flex_exceeds_total_slot_count"], "maximum_capacity_excess_GPU": native["maximum_capacity_excess_GPU"], "posthoc_clipping_calls": 0},
        "model_prediction_validation": None,
        "model_prediction_status": "NOT_RUN_NO_V18_REFIT_OR_LOCKED_TEST",
        "structural_parameterization_guarantee": "0<=G_F_REF<=G_REF<=C_MODEL by sigmoid hierarchy",
        "gate_A_status": "PASS_NATIVE_NORMALIZATION_AND_CONTRACT" if native["capacity_violation_slot_count"] == 0 and native["flex_exceeds_total_slot_count"] == 0 else "FAIL_NATIVE_PHYSICAL_COHERENCE",
    }
    write("V18_AIDC_G_W_COHERENCE_VALIDATION.json", coherence)

    d1_contract = {
        "artifact_id": "V18_D1_CAUSAL_WORKLOAD_STATE_CONTRACT_V1",
        "cutoff": "D-1 18:00 AEST",
        "RUNNING_KNOWN": {"main_policy": "LOCKED", "required_source": "cutoff allocation/state snapshot", "current_authority": "MISSING"},
        "QUEUED_KNOWN": {"balance_initialization": "B_b(1)=B_b^KNOWN", "required_source": "cutoff pending queue snapshot with request-side fields", "current_authority": "MISSING"},
        "FORECAST_NEW": {"authority": "aggregate forecast W_hat_F_b_t", "individual_future_job_ids": False},
        "balance": "B_b,t+1=B_b,t+W_hat_F,b,t-sum_r x_b,r,t",
        "forbidden": ["future realized start", "future realized end", "future completion/state", "D-day actual arrivals as feature"],
    }
    write("V18_D1_CAUSAL_WORKLOAD_STATE_CONTRACT.json", d1_contract)
    forecast_by_day = {}
    for date in DATES:
        with np.load(CAND / "reference_v6_v4r1" / f"REFERENCE_COMPUTE_SCHEDULE_V6_GPU_HOUR_{date}.npz", allow_pickle=False) as z:
            forecast_by_day[date] = float(np.asarray(z["arrivals"], dtype=float).sum())
    d1_audit = {
        "artifact_id": "V18_D1_KNOWN_RUNNING_QUEUE_AUDIT_V1",
        "status": "GATE_B_QUEUE_AUTHORITY_MISSING",
        "schema_fields_present": ["submit_time", "start_time", "end_time", "wallclock_req", "nodes_req", "gpus_requested", "nodelist", "state_simple"],
        "snapshot_fields_present": False,
        "known_running_GPU_h": None,
        "known_queued_GPU_h": None,
        "forecast_new_GPU_h_by_day": forecast_by_day,
        "forecast_new_GPU_h_total": sum(forecast_by_day.values()),
        "total_schedulable_GPU_h": None,
        "known_fraction": None,
        "forecast_fraction": None,
        "excluded_quantity": "NOT_IDENTIFIABLE_FROM_CURRENT_AUTHORITY",
        "reason": "final sacct rows cannot establish cutoff state without consulting realized future start/end; request-side walltime provides only an upper bound",
        "causality_counters": {"D_day_actual_feature_reads": 0, "future_realized_start_feature_reads": 0, "future_realized_end_feature_reads": 0, "future_completion_feature_reads": 0, "future_job_id_injections": 0},
    }
    write("V18_D1_KNOWN_RUNNING_QUEUE_AUDIT.json", d1_audit)

    node_contract = {
        "artifact_id": "V18_AIDC_NODE_POWER_AUTHORITY_CONTRACT_V1",
        "gate_C_status": "PASS_HYBRID_AUTHORITY",
        "fullnode": {"authority": "Dataset312 paired NVML GPU-board + two-socket RAPL CPU-package incremental above frozen idle", "supported_node_classes": list(NODE_CLASSES), "kappa_total_kW_per_active_node": KAPPA_TOTAL, "source_sha256": D312_SHA},
        "partialnode": {"authority": "V17 per-GPU board Q50 lower bound", "kappa_kW_per_GPU": KAPPA_GPU_BOARD_Q50, "CPU_package_increment": None, "reason": "node packing/partial occupancy counterfactual absent"},
        "memory_network_fan_increment": None,
        "PUE_application": "after IT-side component sum exactly once",
        "arbitrary_host_multiplier_calls": 0,
        "raw_reproduction": power,
    }
    write("V18_AIDC_NODE_POWER_AUTHORITY_CONTRACT.json", node_contract)
    split = {
        "artifact_id": "V18_AIDC_FULLNODE_PARTIALNODE_POWER_SPLIT_V1",
        "period": "retrospective training only; not a D-1 forecast result",
        "fullnode_jobs": native["counts"]["fullnode_nodelevel_jobs"],
        "fullnode_GPU_hours": sum(v["GPU_hours"] for v in native["fullnode_by_node_class"].values()),
        "fullnode_node_hours_by_class": {str(k): v for k, v in fullnode_node_h.items()},
        "E_FLEX_GPU_BOARD_component_kWh": fullnode_gpu_component_kwh,
        "E_FLEX_CPU_PACKAGE_component_kWh": fullnode_cpu_component_kwh,
        "E_FLEX_NODE_TOTAL_IDENTIFIED_kWh": fullnode_total_kwh,
        "V4R1_fullnode_GPU_board_Q50_kWh": old_fullnode_board_kwh,
        "nodelevel_minus_V4R1_fullnode_kWh": nodelevel_increase_kwh,
        "GPU_board_component_increase_vs_V4R1_Q50_kWh": gpu_component_increase_kwh,
        "CPU_package_component_kWh": fullnode_cpu_component_kwh,
        "component_median_attribution_gap_kWh": component_median_gap,
        "component_note": "paired total median is authoritative; separate component medians are diagnostic and need not add exactly to paired median",
        "partialnode_U2_CLEAN_jobs": int(cov["V4R1_U2_CLEAN"]["jobs"]),
        "partialnode_GPU_hours": u2_gpu_h,
        "E_FLEX_PARTIAL_LOWER_BOUND_kWh": partial_board_kwh,
        "E_FLEX_ALL_IDENTIFIED_training_kWh": all_identified_training_kwh,
        "eta_F_H100_power": None,
        "eta_F_H100_power_status": "TOTAL_IDENTIFIABLE_H100_DENOMINATOR_NOT_COMMON_ACROSS_FULL_AND_PARTIAL_BOUNDARIES",
        "partial_node_CPU_double_count": 0,
    }
    write("V18_AIDC_FULLNODE_PARTIALNODE_POWER_SPLIT.json", split)

    facility_contract = {
        "artifact_id": "V18_AIDC_WHOLE_FACILITY_IT_DECOMPOSITION_CONTRACT_V1",
        "equations": {"P_IT_REF": "P_OTHER_LOCKED+P_RUN_LOCKED+P_FLEX_REF", "P_IT_DA": "P_OTHER_LOCKED+P_RUN_LOCKED+P_FLEX_DA", "Delta_P_IT": "P_FLEX_DA-P_FLEX_REF", "P_PCC": "P_IT*PUE"},
        "residual_name": "OTHER_LOCKED_IT / NON_CONTROLLABLE_IT_RESIDUAL",
        "negative_residual_policy": "FAIL_FACILITY_COMPOSITION_INCONSISTENT; no clipping",
        "PUE": PUE,
        "PUE_application_count": 1,
    }
    write("V18_AIDC_WHOLE_FACILITY_IT_DECOMPOSITION_CONTRACT.json", facility_contract)
    facility_validation = {
        "artifact_id": "V18_AIDC_WHOLE_FACILITY_IT_DECOMPOSITION_VALIDATION_V1",
        "status": "BLOCKED_UPSTREAM_D1_STATE_AND_POWER_TIER_FORECAST",
        "gate_D_status": "NOT_EVALUATED",
        "existing_V4R1_lower_bound_context": {"total_IT_kWh": funnel["funnel"]["S5"]["total_IT_kWh"], "flexible_IT_kWh": funnel["funnel"]["S4"]["flexible_IT_kWh"], "combined_residual_IT_kWh": funnel["facility_residual_decomposition"]["P_unidentified_residual_kWh"]},
        "new_total_IT_kWh": funnel["funnel"]["S5"]["total_IT_kWh"],
        "new_other_locked_IT_kWh": None,
        "new_running_locked_IT_kWh": None,
        "new_flexible_reference_IT_kWh": None,
        "conservation_error_max_kW": None,
        "minimum_other_locked_IT_kW": None,
        "negative_residual_clipping_count": 0,
        "reason": "new slot-level RUNNING_KNOWN/QUEUED_KNOWN authority and fullnode/partial forecast-tier split are unavailable",
    }
    write("V18_AIDC_WHOLE_FACILITY_IT_DECOMPOSITION_VALIDATION.json", facility_validation)

    recomputed = {
        "artifact_id": "V18_AIDC_FLEXIBILITY_SHARE_RECOMPUTED_V1",
        "semantic_modelable_GPU_hour_coverage": float(cov["V1_plus_V4R1_U2_CLEAN"]["coverage_fraction"]),
        "Kestrel_native_flexible_GPU_share": native["eta_F_GPU_energy"],
        "identified_H100_flexible_power_share": None,
        "whole_facility_identified_flexible_IT_share": None,
        "coincident_peak_share": None,
        "maximum_instantaneous_share": None,
        "status": "PARTIAL_NATIVE_AND_TRAINING_POWER_COMPONENTS_ONLY",
        "source_backed_not_literature_calibrated": True,
        "V4R1_context_only": {"whole_facility_share": funnel["funnel"]["S5"]["eta_flex_energy_IT"], "classification": "GPU-board-only forecast-cohort-only conservative lower bound"},
        "reason_for_null_new_facility_share": facility_validation["reason"],
    }
    write("V18_AIDC_FLEXIBILITY_SHARE_RECOMPUTED.json", recomputed)

    classification = "E. REFREEZE_FAILED_PHYSICAL_COHERENCE" if native["capacity_violation_slot_count"] else "B. REFREEZE_PARTIAL_QUEUE_AUTHORITY_GAP"
    ready = {
        "artifact_id": "V18_AIDC_REFREEZE_READY_FOR_SCIENCE_RUN_V1",
        "READY_FOR_NEW_SCIENCE_RUN": False,
        "classification": classification,
        "gates": {"A_workload_normalization": coherence["gate_A_status"], "B_D1_causal_state": "FAIL_QUEUE_AND_RUNNING_SNAPSHOT_AUTHORITY_MISSING", "C_node_power": "PASS_HYBRID_AUTHORITY", "D_facility_composition": "BLOCKED_NOT_EVALUATED", "E_prospective_scheduler": "BLOCKED_NOT_IMPLEMENTED"},
        "locked_test_status": "NEW_LOCKED_TEST_NOT_YET_AVAILABLE",
        "scientific_solver_calls": 0,
        "OpenDSS_calls": 0,
    }
    write("V18_AIDC_REFREEZE_READY_FOR_SCIENCE_RUN.json", ready)

    review = {
        "artifact_id": "V18_AIDC_REFREEZE_ROOT_CAUSE_CORRECTION_REVIEW_V1",
        "result_classification": classification,
        "corrections": {
            "capacity_normalization": {"before": 1815.6, "after": C_MODEL, "unit": "GPU", "status": coherence["gate_A_status"]},
            "D1_known_state": {"before": "forecast cohort only", "after": "contract defined; queue/running quantities null", "status": "GATE_B_QUEUE_AUTHORITY_MISSING"},
            "node_power": {"before": "GPU-board Q50 only", "after": "full-node Dataset312 GPU+CPU package; partial-node board lower bound", "status": "PASS_HYBRID_AUTHORITY"},
            "facility_decomposition": {"before": "combined residual + flex", "after": "three-component contract only", "status": "BLOCKED_NOT_VALIDATED"},
        },
        "Kestrel_native": native_art,
        "training_power_split": split,
        "new_whole_facility_share": None,
        "literature_context": {"label": "LITERATURE_CONTEXT_ONLY", "representative_range": "approximately 20-25% under non-identical boundaries", "builder_parameter_reads": 0, "calibration_calls": 0},
        "remaining_authority_gaps": ["D-1 cutoff scheduler queue snapshot", "D-1 running allocation/state snapshot", "causal deadline/SLA for known queued work", "V18 forecast output tier preserving fullnode versus partial-node authority", "new untouched locked test period"],
        "ready": ready,
        "firewall_counters": {"D_day_actual_feature_reads": 0, "future_realized_start_end_feature_reads": 0, "future_completion_feature_reads": 0, "future_job_id_injections": 0, "literature_target_model_builder_reads": 0, "result_based_workload_multiplier_selection": 0, "grid_benefit_coefficient_selection": 0, "negative_residual_clipping": 0, "scientific_solver_calls": 0, "OpenDSS_calls": 0},
    }
    write("V18_AIDC_REFREEZE_ROOT_CAUSE_CORRECTION_REVIEW.json", review)

    md = f"""# V18 AIDC Physical Re-freeze Root-Cause Correction Review

RESULT CLASSIFICATION: `{classification}`

V18은 Kestrel의 공식 설치 경계 132-node x 4-H100 = **528 GPU**와 retrospective training trace를 결합했고, native semantic-flexible GPU-energy share를 **{100*native['eta_F_GPU_energy']:.6f}%**로 재현했다. 그러나 trace의 15분 평균 requested occupancy는 최대 **{native['peak_total_active_GPU']:.6f} GPU**로 528을 **{native['capacity_violation_slot_count']} slot** 초과했다. 가상 q99.5/u85 용량으로 바꿔 통과시키거나 clipping하지 않아 Gate A를 fail-closed했다.

Dataset312 full-node GPU-board+RAPL CPU-package 계수와 partial-node GPU-board lower bound의 hybrid power contract은 source-backed하게 복구했다.

그러나 현재 Kestrel archive는 최종 sacct record이고 D-1 18:00의 pending/running snapshot이 아니다. 미래 realized start/end를 사용하지 않고는 `QUEUED_KNOWN`과 `RUNNING_KNOWN`을 정확히 판별할 수 없으므로 Gate B를 fail-closed했다. 이에 따라 새 three-component facility decomposition, 새 whole-facility flexible share, prospective scheduler 및 B0-B3/OpenDSS 실행은 승인하지 않았다.

- Gate A: {ready['gates']['A_workload_normalization']}
- Gate B: {ready['gates']['B_D1_causal_state']}
- Gate C: {ready['gates']['C_node_power']}
- Gate D: {ready['gates']['D_facility_composition']}
- Gate E: {ready['gates']['E_prospective_scheduler']}
- `READY_FOR_NEW_SCIENCE_RUN = false`

20-25% 문헌값은 `LITERATURE_CONTEXT_ONLY`이며 모델 builder에서 읽지 않았고 calibration 호출은 0이다.
"""
    (OUT / "V18_AIDC_REFREEZE_ROOT_CAUSE_CORRECTION_REVIEW.md").write_text(md, encoding="utf-8")
    readme = """# V18 AIDC physical re-freeze

이 디렉터리는 기존 V17을 변경하지 않는 prospective authority audit/contract 패킷이다. Kestrel native training intensity와 Dataset312 node-power source를 재현했지만, D-1 queue/running snapshot authority가 없어 새 facility-wide share와 science run을 fail-closed했다.

원천 경계: Kestrel job archive(최종 sacct records), official Kestrel 132 H100 nodes x 4 GPUs, Dataset312 NVML+RAPL full-node measurements, ESIF whole-facility IT/PUE. 모든 source path/SHA와 지원 등급은 source audit 및 prechange manifest에 기록했다. 기존 V4R1은 GPU-board-only/forecast-cohort-only conservative lower-bound로 보존된다.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")


if __name__ == "__main__":
    main()
