"""Training-only Kestrel native-energy and U2 identifiability audit."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from .aidc_ml_data import AEST, NODE_CLASSES, TRAIN_START
from .authority import sha256_file
from .reproduce_nlr_authority import object_empty
from .v17_external_h100_identifiability import (
    GPU_PER_NODE,
    KESTREL_SHA256,
    TRAIN_END_EXCLUSIVE,
    _as_sequence,
    _h100,
    _training_members,
    audit_kestrel_u2,
)
from .v17_v3r1_zenodo_identifiability import _u2_aggregate_coverage
from .v17_v3r2_eagle_forensic import write_json, zero_counters


DATACARD_SHA256 = "0139b75b80cd3029e0af54e22fc0dbad3080e92a8a7a602f1bd62cd7a36f62e9"


def _base(schema: str, status: str) -> dict[str, Any]:
    return {"schema": schema, "status": status, **zero_counters()}


def _energy_counts(kestrel: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    import pandas as pd
    import pyarrow.parquet as pq

    train_start = pd.Timestamp(TRAIN_START, tz=AEST).tz_convert("UTC")
    train_end = pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST).tz_convert("UTC")
    columns = [
        "id", "job_id", "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared",
        "nodelist", "consumed_energy_joules", "consumed_energy_raw_joules",
        "consumed_energy_raw_watt_hours",
    ]
    counts = {
        "U2_jobs": 0,
        "energy_null": 0,
        "energy_zero": 0,
        "energy_negative": 0,
        "energy_positive": 0,
        "multi_gpu_node": 0,
        "multi_nodelist": 0,
        "multi_shared_node": 0,
    }
    max_wh_error = 0.0
    members: list[dict[str, Any]] = []
    with zipfile.ZipFile(kestrel) as archive, tempfile.TemporaryDirectory(prefix="v17-v3r2-energy-") as temp:
        local = Path(temp) / "month.parquet"
        for month, info in _training_members(archive):
            with archive.open(info) as origin, local.open("wb") as target:
                shutil.copyfileobj(origin, target)
            frame = pq.read_table(local, columns=columns).to_pandas()
            members.append({"month": month, "member": info.filename, "rows": len(frame)})
            submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
            start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
            end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
            nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
            gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
            sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
            valid = start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0)
            overlap = end.gt(train_start) & start.lt(train_end)
            queue = (start - submit).dt.total_seconds()
            semantic = (
                frame["partition"].apply(_h100) & valid & overlap & submit.notna()
                & queue.ge(0) & np.isfinite(queue) & queue.gt(600.0)
                & frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
            )
            no_share = (
                (sharing.isna() | sharing.eq(0))
                & frame["nodes_shared"].apply(object_empty)
                & frame["jobs_shared"].apply(object_empty)
            )
            modelable = semantic & np.isclose(gpus, GPU_PER_NODE * nodes) & nodes.isin(NODE_CLASSES) & no_share
            u2 = semantic & ~modelable & ~no_share
            energy = pd.to_numeric(frame["consumed_energy_raw_joules"], errors="coerce")
            wh = pd.to_numeric(frame["consumed_energy_raw_watt_hours"], errors="coerce")
            counts["U2_jobs"] += int(u2.sum())
            counts["energy_null"] += int((u2 & energy.isna()).sum())
            counts["energy_zero"] += int((u2 & energy.eq(0)).sum())
            counts["energy_negative"] += int((u2 & energy.lt(0)).sum())
            counts["energy_positive"] += int((u2 & energy.gt(0)).sum())
            counts["multi_gpu_node"] += int((u2 & nodes.gt(1)).sum())
            counts["multi_nodelist"] += int(sum(u2.at[i] and len(_as_sequence(frame.at[i, "nodelist"])) > 1 for i in frame.index))
            counts["multi_shared_node"] += int(sum(u2.at[i] and len(_as_sequence(frame.at[i, "nodes_shared"])) > 1 for i in frame.index))
            valid_energy = u2 & energy.notna() & wh.notna()
            if valid_energy.any():
                max_wh_error = max(max_wh_error, float((energy[valid_energy] / 3600.0 - wh[valid_energy]).abs().max()))
    counts["null_fraction"] = counts["energy_null"] / max(counts["U2_jobs"], 1)
    counts["zero_fraction"] = counts["energy_zero"] / max(counts["U2_jobs"], 1)
    counts["positive_fraction"] = counts["energy_positive"] / max(counts["U2_jobs"], 1)
    counts["joule_to_wh_max_abs_error"] = max_wh_error
    return counts, members


def build(repo: Path, kestrel: Path, datacard: Path, output: Path) -> list[Path]:
    if sha256_file(kestrel) != KESTREL_SHA256:
        raise RuntimeError("V17_V3R2_KESTREL_SOURCE_SHA_MISMATCH")
    actual_datacard_sha = sha256_file(datacard)
    if actual_datacard_sha != DATACARD_SHA256:
        raise RuntimeError("V17_V3R2_KESTREL_DATACARD_SHA_MISMATCH")
    prior = json.loads((output / "V17_AIDC_UNMODELED_COHORT_DECOMPOSITION.json").read_text(encoding="utf-8"))
    cohort, u2_prior = audit_kestrel_u2(kestrel, prior)
    coverage = _u2_aggregate_coverage(kestrel)
    counts, members = _energy_counts(kestrel)
    groups = {row["group"]: row for row in cohort["groups"]}
    u2 = groups["U2_SHARED_PARTIAL_OR_SHARED_NODE"]
    if counts["U2_jobs"] != u2["jobs"] or counts["energy_positive"] != 0:
        raise RuntimeError("V17_V3R2_KESTREL_ENERGY_REPRODUCTION_MISMATCH")

    energy_audit = {
        **_base("V17_KESTREL_NATIVE_ENERGY_FIELD_AUDIT_V1", "PASS_FIELD_AUDIT_FAIL_CLOSED_NO_POSITIVE_U2_ENERGY"),
        "source": {"path": str(kestrel.resolve()), "sha256": KESTREL_SHA256},
        "datacard": {"path": str(datacard.resolve()), "sha256": actual_datacard_sha},
        "training_window": [TRAIN_START, "2025-03-31"],
        "fields": {
            "consumed_energy_joules": {"Slurm_field": "ConsumedEnergy", "unit": "J", "type": "formatted string"},
            "consumed_energy_raw_joules": {"Slurm_field": "ConsumedEnergyRaw", "unit": "J", "type": "double"},
            "consumed_energy_raw_watt_hours": {"source": "ConsumedEnergyRaw / 3600", "unit": "Wh", "type": "derived double"},
        },
        "source_semantics": "Slurm-reported energy from node-level power monitoring; public datacard does not document shared-job attribution or expose per-node time series",
        "U2_statistics": counts,
        "multi_node_semantics": "single scalar per parent Slurm row; no per-node energy array, reset trace, or allocation record is exposed",
        "reset_or_wrap_audit": "NO_NEGATIVE_VALUES_BUT_NULL_ZERO_ONLY_CANNOT_VALIDATE_COUNTER_BEHAVIOR_FOR_U2",
        "direct_job_power_authorized": False,
        "direct_node_interval_power_authorized": False,
        "classification": "KESTREL_NODE_ENERGY_NOT_IDENTIFIABLE",
        "training_members_opened": members,
    }
    reproduction = {
        **_base("V17_V3R2_KESTREL_U2_REPRODUCTION_V1", "PASS_EXACT_TRAINING_ONLY_REPRODUCTION"),
        "source_path": str(kestrel.resolve()),
        "source_sha256": KESTREL_SHA256,
        "training_window": [TRAIN_START, "2025-03-31"],
        "semantic_flexible": cohort["semantic_flexible"],
        "V1_modelable": cohort["V1_modelable"],
        "U1": groups["U1_EXCLUSIVE_PARTIAL_NODE"],
        "U2": u2,
        "U3": groups["U3_FULL_NODE_BUT_UNSUPPORTED_NODE_COUNT"],
        "U4": groups["U4_OTHER_POWER_UNMODELED"],
        "prior_reproduction_identity": cohort["reproduction_identity"],
        "U2_observables": u2_prior["observables"],
        "training_members_opened": cohort["source"]["members_opened"],
    }
    interval_manifest = {
        **_base("V17_V3R2_KESTREL_U2_NODE_INTERVALS_MANIFEST_V1", "PASS_REPRODUCIBLE_EX_POST_INTERVAL_MANIFEST_NOT_POWER_AUTHORITY"),
        "source_sha256": KESTREL_SHA256,
        "reconstruction_rule": coverage["reconstruction_rule"],
        "source_observable_fields": [
            "physical node", "start/end", "concurrent job IDs", "concurrent job count",
            "sum requested GPUs", "requested CPUs/memory when present", "state", "overlap duration",
        ],
        "forbidden_inferences": ["GPU device assignment", "MIG", "time-slice fraction", "GPU utilization"],
        "U2_jobs": coverage["U2_jobs"],
        "U2_node_equivalent_hours": coverage["U2_node_equivalent_hours"],
        "fully_reconstructable_ex_post_jobs": coverage["fully_reconstructable_ex_post_jobs"],
        "fully_reconstructable_ex_post_node_equivalent_hours": coverage["fully_reconstructable_ex_post_node_equivalent_hours"],
        "failure_counts": coverage["failure_counts"],
        "future_physical_node_assignment_available_D1": False,
        "compact_artifact_policy": "manifest plus frozen source SHA and deterministic reconstruction rule; no 67,874-row scientific-authority copy",
    }
    identifiability = {
        **_base("V17_V3R2_KESTREL_U2_ENERGY_IDENTIFIABILITY_V1", "FAIL_CLOSED_U2_NATIVE_ENERGY_NOT_IDENTIFIABLE"),
        "classification": "KESTREL_NODE_ENERGY_NOT_IDENTIFIABLE",
        "U2_jobs": u2["jobs"],
        "U2_node_equivalent_hours": u2["node_equivalent_hours"],
        "reconstructable_ex_post_jobs": coverage["fully_reconstructable_ex_post_jobs"],
        "reconstructable_ex_post_node_equivalent_hours": coverage["fully_reconstructable_ex_post_node_equivalent_hours"],
        "native_energy_positive_observations": counts["energy_positive"],
        "native_energy_null_observations": counts["energy_null"],
        "native_energy_zero_observations": counts["energy_zero"],
        "reason": "All training-only U2 ConsumedEnergyRaw values are null or zero, and the public source supplies no shared-node attribution/timeseries semantics; reconstructed scheduler intervals therefore have no measurable Kestrel power label.",
        "P_job_equals_energy_over_runtime_authorized": False,
        "bounded_node_interval_energy_authorized": False,
        "active_power_model_changes": 0,
    }
    payloads = {
        "V17_KESTREL_NATIVE_ENERGY_FIELD_AUDIT.json": energy_audit,
        "V17_V3R2_KESTREL_U2_REPRODUCTION.json": reproduction,
        "V17_V3R2_KESTREL_U2_NODE_INTERVALS_MANIFEST.json": interval_manifest,
        "V17_V3R2_KESTREL_U2_ENERGY_IDENTIFIABILITY.json": identifiability,
    }
    paths: list[Path] = []
    for name, payload in payloads.items():
        path = output / name
        write_json(path, payload)
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--kestrel", type=Path, required=True)
    parser.add_argument("--datacard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for path in build(args.repo, args.kestrel, args.datacard, args.output):
        print(path)


if __name__ == "__main__":
    main()
