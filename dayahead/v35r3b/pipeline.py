"""Build the V35R3B Apr-01 local authority forensic artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .contracts import (
    ACTIVE_V35R3_WORKTREE,
    AEST,
    ARTIFACT_DIRNAME,
    AUTHORITY_ROOT,
    EAGLE_HEAD,
    EAGLE_ROOT,
    EXPECTED_BRANCH,
    FASTSIM_HEAD,
    FASTSIM_ROOT,
    FRESH_STATUS,
    GPU_CAPACITY,
    GRID_BINDING_STATUS,
    ISSUE_TIME,
    KESTREL_ARCHIVE,
    KESTREL_ARCHIVE_SHA256,
    KESTREL_DATACARD_SHA256,
    MERGE_PERFORMED,
    NETWORK_COMMANDS_EXECUTED,
    NLR_DOCS_HEAD,
    NLR_DOCS_ROOT,
    PARENT_WORKTREE,
    POWER_AUTHORITY_LEVEL,
    PRIMARY_CLASSIFICATION,
    PRODUCTION_RECOMMENDATION,
    PUSH_PERFORMED,
    RADDIT_HEAD,
    RADDIT_ROOT,
    RUNTIME_AUTHORITY_LEVEL,
    SATURATION_CAUSE,
    SLOT_MINUTES,
    SOURCE_PARENT,
    TARGET_END,
    TARGET_SLOTS,
    TARGET_START,
    W1,
    W3,
    W5,
    WORKTREE,
)
from .forensic import (
    causal_feature_audit,
    exact_key_join,
    git_repository_state,
    inventory_authority,
    normalize_job_key,
    profile_energy_gpu_hours,
    sha256_file,
    target_gpu_profile,
    write_csv,
    write_json,
)


V35R3A_ARTIFACT_DIRNAME = "v35r3a_kestrel_scheduler_temporal"
H0_IT_PEAK_KW = 406.77599381381907
H0_KW_PER_GPU = H0_IT_PEAK_KW / GPU_CAPACITY
PUE = 1.30
PLANNING_RHO = 0.5670071217020519


def _git(path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), *args], text=True, encoding="utf-8", errors="replace"
    ).strip()


def _status(path: Path) -> str:
    return _git(path, "status", "--short")


def _relative(path: Path, root: Path = AUTHORITY_ROOT) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _source_record(
    path: str,
    inventory: Mapping[str, Mapping[str, Any]],
    *,
    repository: str = "02_RADDiT",
    head: str = RADDIT_HEAD,
) -> dict[str, Any]:
    record = inventory.get(path, {})
    return {
        "local_path": str(AUTHORITY_ROOT / path),
        "relative_path": path,
        "sha256": record.get("sha256"),
        "source_repository": repository,
        "repository_HEAD": head,
    }


def _power_objects(
    inventory: Mapping[str, Mapping[str, Any]],
    lfs_rows: Sequence[Mapping[str, Any]],
    canonical_power: Mapping[str, Any],
) -> list[dict[str, Any]]:
    columns = [
        "object_name",
        "local_path",
        "relative_path",
        "sha256",
        "source_repository",
        "repository_HEAD",
        "classification",
        "schema",
        "row_count",
        "key_columns",
        "unit",
        "total_per_node_per_gpu",
        "predicted_or_realized",
        "time_of_availability",
        "Kestrel_specific",
        "joinable_to_current_trace",
        "suitable_for_day_ahead",
        "reason",
    ]

    def item(name: str, path: str, classification: str, **values: Any) -> dict[str, Any]:
        row = {key: None for key in columns}
        row.update(_source_record(path, inventory))
        row.update({"object_name": name, "classification": classification})
        row.update(values)
        return row

    objects = [
        item(
            "RADDiT baseline aggregate power predictions",
            "02_RADDiT/data/baseline_power_results.parquet",
            "G_GIT_LFS_POINTER_OR_MISSING_PAYLOAD",
            schema="avg_power_per_node:float64,predicted_power:float64 (notebook-embedded schema)",
            row_count=1_035_281,
            key_columns="NONE_IN_RELEASED_AGGREGATE",
            unit="W per node",
            total_per_node_per_gpu="PER_NODE; incremental attribution unproven",
            predicted_or_realized="predicted plus realized label",
            time_of_availability="prediction was intended pre-execution; payload unavailable",
            Kestrel_specific=True,
            joinable_to_current_trace=False,
            suitable_for_day_ahead=False,
            reason="LFS object is not cached locally and the released aggregate schema strips job_id/submit_time.",
        ),
        item(
            "RADDiT semantic-search aggregate power predictions",
            "02_RADDiT/data/semantic_search_power_results.parquet",
            "G_GIT_LFS_POINTER_OR_MISSING_PAYLOAD",
            schema="avg_power_per_node:float64,predicted_power:float64 (notebook-embedded schema)",
            row_count=1_035_365,
            key_columns="NONE_IN_RELEASED_AGGREGATE",
            unit="W per node",
            total_per_node_per_gpu="PER_NODE; incremental attribution unproven",
            predicted_or_realized="predicted plus realized label",
            time_of_availability="causal historical-neighbor prediction by source design; payload unavailable",
            Kestrel_specific=True,
            joinable_to_current_trace=False,
            suitable_for_day_ahead=False,
            reason="LFS payload and embeddings are absent; aggregate result has no job identity.",
        ),
        item(
            "RADDiT historical trace power labels",
            "02_RADDiT/data/historic_job_trace.parquet",
            "G_GIT_LFS_POINTER_OR_MISSING_PAYLOAD",
            schema="20 columns including job_id,submit/start/end,nodes_req,avg_power_per_node,wallclock_used_sec,script",
            row_count=2_557_884,
            key_columns="job_id in notebook output",
            unit="W per node",
            total_per_node_per_gpu="PER_NODE",
            predicted_or_realized="realized historical label",
            time_of_availability="after execution",
            Kestrel_specific=True,
            joinable_to_current_trace=False,
            suitable_for_day_ahead=False,
            reason="Training/semantic source is an uncached LFS pointer; realized label is not a decision feature.",
        ),
        item(
            "RADDiT ground-truth scheduling power",
            "02_RADDiT/data/ground_truth.parquet",
            "B_DIRECT_PER_JOB_MEASURED_POWER",
            schema="submit,start,end,nodes,runtime,wait_time,avg_power_per_node",
            row_count=161_266,
            key_columns="NONE",
            unit="W per node",
            total_per_node_per_gpu="PER_NODE; job-attributable incremental semantics unproven",
            predicted_or_realized="realized",
            time_of_availability="after execution; 2024-08-30 through 2024-09-25 schedule horizon",
            Kestrel_specific=True,
            joinable_to_current_trace=False,
            suitable_for_day_ahead=False,
            reason="Real Parquet but historical realized label, no job_id, no documented J2 transform, and shared-node attribution is ambiguous.",
        ),
    ]
    for filename in ("baseline_sim.parquet", "validation_sim.parquet", "ea_sim.parquet"):
        objects.append(
            item(
                f"RADDiT simulator {filename}",
                f"02_RADDiT/data/{filename}",
                "E_SIMULATED_OR_SYNTHETIC_POWER",
                schema="submit,start,end,nodes,runtime,wait_time,avg_power_per_node",
                row_count=161_266,
                key_columns="NONE",
                unit="W per node",
                total_per_node_per_gpu="PER_NODE simulator trajectory",
                predicted_or_realized="simulated schedule carrying historical power labels",
                time_of_availability="ex-post research output",
                Kestrel_specific=True,
                joinable_to_current_trace=False,
                suitable_for_day_ahead=False,
                reason="Simulator output is not a frozen causal Apr-01 job prediction authority.",
            )
        )
    objects.extend(
        [
            item(
                "RADDiT baseline_models.py power estimator",
                "02_RADDiT/energy_aware_scheduling/scripts/baseline_models.py",
                "I_UNKNOWN",
                schema="XGBRegressor with numeric + PCA categorical features",
                row_count=None,
                key_columns="training output originally job_id,array_pos,submit_time; released aggregate strips keys",
                unit="W per node target",
                total_per_node_per_gpu="PER_NODE",
                predicted_or_realized="training/inference code only",
                time_of_availability="causal split uses training end before test submit",
                Kestrel_specific=True,
                joinable_to_current_trace=False,
                suitable_for_day_ahead=False,
                reason="kestrel_baseline_data.parquet, fitted preprocessing, and checkpoint are absent; configured tests end 2025-02-01.",
            ),
            item(
                "RADDiT quickstart power model",
                "02_RADDiT/energy_aware_scheduling/scripts/quickstart.py",
                "F_EXAMPLE_OR_TOY_VALUE",
                schema="random 80/20 10k sample; nodes_req and wallclock_req_sec",
                row_count=None,
                key_columns="none persisted",
                unit="W per node target",
                total_per_node_per_gpu="PER_NODE",
                predicted_or_realized="diagnostic reconstruction recipe",
                time_of_availability="random split, not strict temporal holdout",
                Kestrel_specific=True,
                joinable_to_current_trace=False,
                suitable_for_day_ahead=False,
                reason="Explicit quick-start demo, missing LFS trace, no checkpoint, and random split.",
            ),
            item(
                "RADDiT energy-aware priority examples",
                "02_RADDiT/energy_aware_scheduling/scripts/ea_sched_priority.py",
                "F_EXAMPLE_OR_TOY_VALUE",
                schema="five hard-coded Job(predicted_power,predicted_runtime) examples",
                row_count=5,
                key_columns="NONE",
                unit="W",
                total_per_node_per_gpu="UNSPECIFIED EXAMPLE",
                predicted_or_realized="toy input",
                time_of_availability="example only",
                Kestrel_specific=False,
                joinable_to_current_trace=False,
                suitable_for_day_ahead=False,
                reason="Demonstration values are not observations or predictions.",
            ),
        ]
    )
    for lfs in lfs_rows:
        relative = str(lfs["relative_path"])
        if "encrypted_embeddings/chunk_" not in relative:
            continue
        objects.append(
            item(
                f"RADDiT encrypted semantic embedding {Path(relative).name}",
                relative,
                "G_GIT_LFS_POINTER_OR_MISSING_PAYLOAD",
                schema="expected enc_embedding_int8 plus avg_power_per_node,wallclock_used_sec,submit_time,end_time",
                row_count=None,
                key_columns="row_id generated on load; no documented current job_id key",
                unit="W per node label",
                total_per_node_per_gpu="PER_NODE label",
                predicted_or_realized="historical label plus embedding",
                time_of_availability="historical record",
                Kestrel_specific=True,
                joinable_to_current_trace=False,
                suitable_for_day_ahead=False,
                reason="Uncached LFS pointer; no local vector payload and no Apr-01 submission embedding binding.",
            )
        )
    objects.extend(
        [
            {
                "object_name": "Kestrel anonymized archive energy fields",
                "local_path": str(KESTREL_ARCHIVE),
                "relative_path": "external Kestrel archive",
                "sha256": KESTREL_ARCHIVE_SHA256,
                "source_repository": "01_Kestrel_job_trace",
                "repository_HEAD": None,
                "classification": "B_DIRECT_PER_JOB_MEASURED_POWER",
                "schema": "consumed_energy_joules,consumed_energy_raw_joules,consumed_energy_raw_watt_hours and TDP estimates",
                "row_count": "approximately 11,000,000",
                "key_columns": "id,job_id,array_pos",
                "unit": "J/Wh",
                "total_per_node_per_gpu": "node-level monitoring/derived energy; not a submission prediction",
                "predicted_or_realized": "realized/estimated ex-post",
                "time_of_availability": "after execution",
                "Kestrel_specific": True,
                "joinable_to_current_trace": True,
                "suitable_for_day_ahead": False,
                "reason": "Identity is present but energy is future realized information, not causal predicted power.",
            },
            {
                "object_name": "MobileESS V35R3A homogeneous IT proxy",
                "local_path": "dayahead/artifacts/v35r3a_kestrel_scheduler_temporal/V35R3A_KQ0_GRID_EFFECT.json",
                "relative_path": "MobileESS parent evidence",
                "sha256": None,
                "source_repository": "MobileESS",
                "repository_HEAD": SOURCE_PARENT,
                "classification": "D_AGGREGATE_CLUSTER_POWER",
                "schema": "equivalent_IT_kW_per_requested_GPU",
                "row_count": TARGET_SLOTS,
                "key_columns": "slot only",
                "unit": "kW per requested GPU proxy",
                "total_per_node_per_gpu": "PER_GPU HOMOGENEOUS PROXY",
                "predicted_or_realized": "aggregate proxy",
                "time_of_availability": "frozen before policy",
                "Kestrel_specific": False,
                "joinable_to_current_trace": False,
                "suitable_for_day_ahead": "H0_ONLY",
                "reason": "Supports aggregate H0 trajectory but cannot rank equal-resource jobs.",
            },
            {
                "object_name": "MobileESS independent runtime-source IT_power_kW",
                "local_path": canonical_power["path"],
                "relative_path": canonical_power["relative_path"],
                "sha256": canonical_power["sha256"],
                "source_repository": "MobileESS",
                "repository_HEAD": SOURCE_PARENT,
                "classification": "I_UNKNOWN",
                "schema": "IT_power_kW field",
                "row_count": canonical_power["row_count"],
                "key_columns": "source_job_id",
                "unit": "kW",
                "total_per_node_per_gpu": "UNKNOWN",
                "predicted_or_realized": "no valid values",
                "time_of_availability": "not applicable",
                "Kestrel_specific": True,
                "joinable_to_current_trace": False,
                "suitable_for_day_ahead": False,
                "reason": f"IT_power_kW non-null rows={canonical_power['valid_power_rows']}; rack_power_valid rows={canonical_power['rack_power_valid_rows']}.",
            },
        ]
    )
    return objects


def _runtime_objects(
    inventory: Mapping[str, Mapping[str, Any]],
    lfs_rows: Sequence[Mapping[str, Any]],
    canonical_runtime: Mapping[str, Any],
) -> list[dict[str, Any]]:
    columns = [
        "object_name",
        "local_path",
        "relative_path",
        "sha256",
        "source_repository",
        "repository_HEAD",
        "classification",
        "schema",
        "row_count",
        "key_columns",
        "unit",
        "features",
        "availability_time",
        "target_label",
        "training_cutoff",
        "model_or_checkpoint",
        "uncertainty_quantiles",
        "running_remaining_suitable",
        "pending_scheduling_suitable",
        "reason",
    ]

    def item(name: str, path: str, classification: str, **values: Any) -> dict[str, Any]:
        row = {key: None for key in columns}
        row.update(_source_record(path, inventory))
        row.update({"object_name": name, "classification": classification})
        row.update(values)
        return row

    objects = [
        item(
            "RADDiT baseline aggregate runtime predictions",
            "02_RADDiT/data/baseline_runtime_results.parquet",
            "G_GIT_LFS_POINTER_OR_MISSING_PAYLOAD",
            schema="wallclock_used_sec:float64,predicted_runtime_hours:float64",
            row_count=1_035_281,
            key_columns="NONE_IN_RELEASED_AGGREGATE",
            unit="seconds label / hours prediction",
            features="numeric requests plus fitted PCA categorical representation",
            availability_time="intended at submission; payload unavailable",
            target_label="wallclock_used_sec",
            training_cutoff="rolling prior 100 days; configured test through 2025-02-01",
            model_or_checkpoint="XGBRegressor; checkpoint absent",
            uncertainty_quantiles="none",
            running_remaining_suitable=False,
            pending_scheduling_suitable=False,
            reason="Uncached LFS object, no identity columns in released aggregate, and no Apr-01 coverage.",
        ),
        item(
            "RADDiT semantic aggregate runtime predictions",
            "02_RADDiT/data/semantic_search_runtime_results.parquet",
            "G_GIT_LFS_POINTER_OR_MISSING_PAYLOAD",
            schema="wallclock_used_sec:float64,predicted_runtime_hours:float64",
            row_count=1_035_365,
            key_columns="NONE_IN_RELEASED_AGGREGATE",
            unit="seconds label / hours prediction",
            features="4096-d submission script embedding and prior completed neighbors",
            availability_time="intended at submission; payload unavailable",
            target_label="wallclock_used_sec",
            training_cutoff="neighbor end_time before split; configured test through 2025-02-01",
            model_or_checkpoint="semantic index/embeddings absent",
            uncertainty_quantiles="neighbor min/max only in raw outputs; absent aggregate",
            running_remaining_suitable=False,
            pending_scheduling_suitable=False,
            reason="Uncached result plus 45 uncached embedding chunks; current submission embedding binding is absent.",
        ),
        item(
            "RADDiT historical trace realized runtime",
            "02_RADDiT/data/historic_job_trace.parquet",
            "G_GIT_LFS_POINTER_OR_MISSING_PAYLOAD",
            schema="20 columns including job_id and wallclock_used_sec",
            row_count=2_557_884,
            key_columns="job_id",
            unit="seconds",
            features="not applicable",
            availability_time="after job completion",
            target_label="wallclock_used_sec",
            training_cutoff=None,
            model_or_checkpoint=None,
            uncertainty_quantiles=None,
            running_remaining_suitable=False,
            pending_scheduling_suitable=False,
            reason="Uncached LFS pointer and realized runtime is forbidden during Apr-01 policy selection.",
        ),
        item(
            "RADDiT ground-truth realized runtime",
            "02_RADDiT/data/ground_truth.parquet",
            "B_DIRECT_PER_JOB_REALIZED_RUNTIME",
            schema="submit,start,end,nodes,runtime,wait_time,avg_power_per_node",
            row_count=161_266,
            key_columns="NONE",
            unit="timedelta",
            features="not applicable",
            availability_time="after job completion",
            target_label="runtime",
            training_cutoff=None,
            model_or_checkpoint=None,
            uncertainty_quantiles=None,
            running_remaining_suitable=False,
            pending_scheduling_suitable=False,
            reason="Real historical labels but no identity, no documented J2 transform, and not causal predictions.",
        ),
    ]
    for filename in ("baseline_sim.parquet", "validation_sim.parquet", "ea_sim.parquet"):
        objects.append(
            item(
                f"RADDiT simulator runtime {filename}",
                f"02_RADDiT/data/{filename}",
                "E_SIMULATED_OR_SYNTHETIC_RUNTIME",
                schema="submit,start,end,nodes,runtime,wait_time,avg_power_per_node",
                row_count=161_266,
                key_columns="NONE",
                unit="timedelta",
                features="simulator input",
                availability_time="research output",
                target_label="runtime",
                training_cutoff=None,
                model_or_checkpoint="FastSim/RADDiT simulation output",
                uncertainty_quantiles=None,
                running_remaining_suitable=False,
                pending_scheduling_suitable=False,
                reason="Simulation result is not a frozen causal Apr-01 runtime predictor.",
            )
        )
    objects.extend(
        [
            item(
                "RADDiT baseline_models.py runtime estimator",
                "02_RADDiT/energy_aware_scheduling/scripts/baseline_models.py",
                "I_UNKNOWN",
                schema="XGBRegressor with numeric + PCA categorical features",
                row_count=None,
                key_columns="output code includes job_id,array_pos,submit_time",
                unit="seconds",
                features="nodes_req,wallclock_req_seconds,processors_req,memory_req_raw,100 fitted PCs",
                availability_time="submission-side in design",
                target_label="wallclock_used_sec",
                training_cutoff="rolling prior 100 completed days",
                model_or_checkpoint="training code only; no checkpoint/preprocessor",
                uncertainty_quantiles="none",
                running_remaining_suitable=False,
                pending_scheduling_suitable=False,
                reason="Required input and fitted state are absent, output horizon stops before Apr-01, and defaults are not a frozen checkpoint.",
            ),
            item(
                "RADDiT quickstart runtime model",
                "02_RADDiT/energy_aware_scheduling/scripts/quickstart.py",
                "F_EXAMPLE_OR_TOY_VALUE",
                schema="XGBRegressor on random 80/20 sample",
                row_count=None,
                key_columns="none persisted",
                unit="seconds",
                features="nodes_req,wallclock_req_sec",
                availability_time="random research split",
                target_label="wallclock_used_sec",
                training_cutoff="none; random split",
                model_or_checkpoint="not saved",
                uncertainty_quantiles="none",
                running_remaining_suitable=False,
                pending_scheduling_suitable=False,
                reason="Explicit quick-start demo, no strict time split, no input payload, and no checkpoint.",
            ),
            {
                "object_name": "MobileESS V35R3A requested walltime reservations",
                "local_path": "dayahead/artifacts/v35r3a_kestrel_scheduler_temporal/V35R3A_BASELINE_SCHEDULE.parquet",
                "relative_path": "MobileESS parent evidence",
                "sha256": None,
                "source_repository": "MobileESS",
                "repository_HEAD": SOURCE_PARENT,
                "classification": "C_REQUESTED_WALLTIME_ONLY",
                "schema": "duration_slots",
                "row_count": 582,
                "key_columns": "job_id",
                "unit": "15-minute slots",
                "features": "submission requested walltime / remaining requested walltime",
                "availability_time": "known at D-1 issue",
                "target_label": None,
                "training_cutoff": None,
                "model_or_checkpoint": None,
                "uncertainty_quantiles": None,
                "running_remaining_suitable": "conservative fallback",
                "pending_scheduling_suitable": "conservative fallback",
                "reason": "Only authorized causal duration representation for V35R3B.",
            },
            {
                "object_name": "MobileESS independent per-job runtime source",
                "local_path": canonical_runtime["path"],
                "relative_path": canonical_runtime["relative_path"],
                "sha256": canonical_runtime["sha256"],
                "source_repository": "MobileESS",
                "repository_HEAD": SOURCE_PARENT,
                "classification": "B_DIRECT_PER_JOB_REALIZED_RUNTIME",
                "schema": "source_job_id,arrival/latest_start/latest_completion,nonpreemptive_duration_steps",
                "row_count": canonical_runtime["row_count"],
                "key_columns": "source_job_id",
                "unit": "15-minute steps",
                "features": "source timestamps including ex-post completion-derived duration",
                "availability_time": "ex-post/frozen downstream artifact, not D-1 prediction",
                "target_label": "nonpreemptive_duration_steps",
                "training_cutoff": None,
                "model_or_checkpoint": None,
                "uncertainty_quantiles": None,
                "running_remaining_suitable": False,
                "pending_scheduling_suitable": False,
                "reason": f"Exact matches exist only for {canonical_runtime['running_matches']} running jobs and 0 temporal pending jobs; values are not causal predictions.",
            },
            item(
                "Eagle jobs reference optimization Pickle",
                "05_Eagle_jobs_reference/results/optuna_studies/study.pkl",
                "F_EXAMPLE_OR_TOY_VALUE",
                source_repository="05_Eagle_jobs_reference",
                repository_HEAD=EAGLE_HEAD,
                schema="untrusted Pickle not deserialized",
                row_count=None,
                key_columns="unknown",
                unit="unknown",
                features="Eagle research features",
                availability_time="reference-only",
                target_label="runtime in Eagle examples",
                training_cutoff="not Apr-01 Kestrel authority",
                model_or_checkpoint="Optuna study, not frozen inference checkpoint",
                uncertainty_quantiles="unknown",
                running_remaining_suitable=False,
                pending_scheduling_suitable=False,
                reason="Different Eagle reference corpus; unsafe Pickle was not executed and is not a Kestrel authority.",
            ),
        ]
    )
    for lfs in lfs_rows:
        relative = str(lfs["relative_path"])
        if "encrypted_embeddings/chunk_" not in relative:
            continue
        objects.append(
            item(
                f"RADDiT encrypted semantic runtime embedding {Path(relative).name}",
                relative,
                "G_GIT_LFS_POINTER_OR_MISSING_PAYLOAD",
                schema="expected enc_embedding_int8 plus wallclock_used_sec and timestamps",
                row_count=None,
                key_columns="row_id generated on load",
                unit="seconds realized label",
                features="4096-d int8 embedding",
                availability_time="historical completed record",
                target_label="wallclock_used_sec",
                training_cutoff="end_time filtered before query",
                model_or_checkpoint="semantic vector data",
                uncertainty_quantiles="neighbor min/max in raw result only",
                running_remaining_suitable=False,
                pending_scheduling_suitable=False,
                reason="Uncached LFS pointer and no current job-script-to-embedding adapter.",
            )
        )
    return objects


def _lfs_audit(inventory_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    audits = []
    for row in inventory_rows:
        if not row["lfs_pointer"]:
            continue
        relative = str(row["relative_path"])
        if "baseline_power" in relative:
            purpose = "baseline per-job power model aggregate evaluation"
            refs = "baseline_model_results.ipynb:76; validate_datasets.ipynb cell 6"
            schema = "avg_power_per_node,predicted_power"
            bp, br, bs = True, False, False
        elif "baseline_runtime" in relative:
            purpose = "baseline per-job runtime model aggregate evaluation"
            refs = "baseline_model_results.ipynb:162; validate_datasets.ipynb cell 8"
            schema = "wallclock_used_sec,predicted_runtime_hours"
            bp, br, bs = False, True, True
        elif "semantic_search_power" in relative:
            purpose = "semantic-search power aggregate evaluation"
            refs = "semantic_search_results.ipynb; validate_datasets.ipynb cell 13"
            schema = "avg_power_per_node,predicted_power"
            bp, br, bs = True, False, False
        elif "semantic_search_runtime" in relative:
            purpose = "semantic-search runtime aggregate evaluation"
            refs = "semantic_search_results.ipynb; validate_datasets.ipynb cell 14"
            schema = "wallclock_used_sec,predicted_runtime_hours"
            bp, br, bs = False, True, True
        elif "historic_job_trace" in relative:
            purpose = "RADDiT historical training/inference trace"
            refs = "quickstart.py:34; prep_for_embedding.py:17; validate_datasets.ipynb cell 3"
            schema = "20 columns including job_id,submit/start/end,avg_power_per_node,wallclock_used_sec,script"
            bp, br, bs = True, True, True
        else:
            purpose = "encrypted/int8 semantic embedding chunk"
            refs = "semantic_search.py:252; quickstart_embedding.py:36"
            schema = "enc_embedding_int8,avg_power_per_node,wallclock_used_sec,submit_time,end_time"
            bp, br, bs = True, True, False
        audits.append(
            {
                "repository": "02_RADDiT",
                "repository_HEAD": RADDIT_HEAD,
                "relative_path": relative.removeprefix("02_RADDiT/"),
                "authority_relative_path": relative,
                "pointer_sha256": row["sha256"],
                "lfs_oid_sha256": row["lfs_oid"],
                "expected_byte_size": row["lfs_expected_size"],
                "pointer_byte_size": row["size_bytes"],
                "apparent_purpose": purpose,
                "code_notebook_references": refs,
                "expected_schema": schema,
                "blocks_power_authority": bp,
                "blocks_runtime_authority": br,
                "blocks_scheduler_fidelity": bs,
                "lfs_object_cached_locally": row["lfs_object_cached_locally"],
                "status": "GIT_LFS_POINTER_PAYLOAD_ABSENT",
            }
        )
    return audits


def _missing_manifest(lfs_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for row in lfs_rows:
        relative = str(row["relative_path"])
        name = Path(relative).name
        role: list[str] = []
        if row["blocks_power_authority"]:
            role.append("power")
        if row["blocks_runtime_authority"]:
            role.append("runtime")
        if row["blocks_scheduler_fidelity"]:
            role.append("scheduler")
        requests.append(
            {
                "short_name": name,
                "exact_repository_source": "02_RADDiT (origin metadata recorded locally; no network access performed)",
                "repository_HEAD": RADDIT_HEAD,
                "expected_relative_path": row["relative_path"],
                "git_lfs_oid_sha256": row["lfs_oid_sha256"],
                "expected_size_bytes": row["expected_byte_size"],
                "expected_schema_columns": row["expected_schema"],
                "model_checkpoint_type": None,
                "why_required": row["apparent_purpose"],
                "roles": role,
                "requirement": "MANDATORY_FOR_THE_ASSOCIATED_RADDIT_REPLAY" if "chunk_" not in name else "OPTIONAL_IF_BASELINE_MODEL_PATH_IS_COMPLETE",
                "closest_local_reference": row["authority_relative_path"],
                "code_notebook_lines": row["code_notebook_references"],
                "public_release_catalog_asset_likely": True,
                "web_research_question": f"At RADDiT HEAD {RADDIT_HEAD}, is the Git-LFS object sha256:{row['lfs_oid_sha256']} for {row['relative_path']} publicly downloadable, and what license/identity semantics accompany it?",
            }
        )
    extras = [
        {
            "short_name": "kestrel_baseline_data.parquet",
            "expected_relative_path": "energy_aware_scheduling/scripts/kestrel_baseline_data.parquet (working-directory-relative in source)",
            "git_lfs_oid_sha256": None,
            "expected_size_bytes": None,
            "expected_schema_columns": "job_id,array_pos,submit_time,end_time,nodes_req,wallclock_req_seconds,processors_req,memory_req_raw,job_type,user,account,partition,modules_set,conda_envs_set,avg_power_per_node,wallclock_used_sec",
            "model_checkpoint_type": None,
            "why_required": "Exact input named by baseline_models.py:22; no file with this basename exists locally.",
            "roles": ["power", "runtime", "join"],
            "requirement": "MANDATORY_FOR_DIAGNOSTIC_RECONSTRUCTION",
            "closest_local_reference": "02_RADDiT/data/historic_job_trace.parquet pointer has a similar but not identical notebook schema",
            "code_notebook_lines": "energy_aware_scheduling/scripts/baseline_models.py:22,57-105",
            "public_release_catalog_asset_likely": "UNKNOWN",
            "web_research_question": "Was kestrel_baseline_data.parquet released for RADDiT HEAD ae1bf13, and is its schema/identity transform documented?",
        },
        {
            "short_name": "published_power_model_checkpoint",
            "expected_relative_path": "NOT_DECLARED_IN_REPOSITORY",
            "git_lfs_oid_sha256": None,
            "expected_size_bytes": None,
            "expected_schema_columns": "XGBoost booster plus exact feature names/order",
            "model_checkpoint_type": "XGBRegressor power checkpoint",
            "why_required": "P3 replay requires original fitted parameters; training code alone does not freeze a model.",
            "roles": ["power"],
            "requirement": "MANDATORY_FOR_P3_UNLESS_A_DIRECT_APR01_P4_PAYLOAD_EXISTS",
            "closest_local_reference": "energy_aware_scheduling/scripts/baseline_models.py:91-100",
            "code_notebook_lines": "baseline_models.py:97-99",
            "public_release_catalog_asset_likely": "UNKNOWN",
            "web_research_question": "Did RADDiT publish the fitted per-job power XGBoost checkpoint and its exact feature-order metadata?",
        },
        {
            "short_name": "published_runtime_model_checkpoint",
            "expected_relative_path": "NOT_DECLARED_IN_REPOSITORY",
            "git_lfs_oid_sha256": None,
            "expected_size_bytes": None,
            "expected_schema_columns": "XGBoost booster plus exact feature names/order",
            "model_checkpoint_type": "XGBRegressor runtime checkpoint",
            "why_required": "R3 replay requires original fitted parameters; no checkpoint is present.",
            "roles": ["runtime"],
            "requirement": "MANDATORY_FOR_R3_UNLESS_A_DIRECT_APR01_R4_PAYLOAD_EXISTS",
            "closest_local_reference": "energy_aware_scheduling/scripts/baseline_models.py:101-110",
            "code_notebook_lines": "baseline_models.py:106-108",
            "public_release_catalog_asset_likely": "UNKNOWN",
            "web_research_question": "Did RADDiT publish the fitted per-job runtime XGBoost checkpoint and exact feature-order metadata?",
        },
        {
            "short_name": "fitted_preprocessing_bundle",
            "expected_relative_path": "NOT_DECLARED_IN_REPOSITORY",
            "git_lfs_oid_sha256": None,
            "expected_size_bytes": None,
            "expected_schema_columns": "OneHotEncoder/MultiLabelBinarizer classes and PCA(100) state",
            "model_checkpoint_type": "scikit-learn preprocessing bundle",
            "why_required": "Exact P3/R3 inference cannot reproduce training-fitted categorical encoders and PCA from source code alone.",
            "roles": ["power", "runtime"],
            "requirement": "MANDATORY_FOR_P3_R3_REPLAY",
            "closest_local_reference": "baseline_models.py:24-87",
            "code_notebook_lines": "baseline_models.py:24-87",
            "public_release_catalog_asset_likely": "UNKNOWN",
            "web_research_question": "Were the fitted RADDiT encoders, MultiLabelBinarizers, PCA components, and feature order released?",
        },
        {
            "short_name": "Apr01_job_keyed_power_predictions",
            "expected_relative_path": "NOT_PRESENT; direct prediction table must name the Apr-01 Kestrel job namespace",
            "git_lfs_oid_sha256": None,
            "expected_size_bytes": None,
            "expected_schema_columns": "job_id,array_pos,submit_time,predicted_power,power_unit,power_boundary,model_version,prediction_timestamp",
            "model_checkpoint_type": "direct frozen prediction payload",
            "why_required": "Released result payloads end by 2025-02-01 and strip identity; 339 Apr-01 temporal jobs have zero coverage.",
            "roles": ["power", "join"],
            "requirement": "MANDATORY_FOR_P4_OR_AS_VALIDATION_OF_P3",
            "closest_local_reference": "baseline_models.py:120-128 shows pre-aggregation keyed columns",
            "code_notebook_lines": "baseline_models.py:120-128; validate_datasets.ipynb cell 6",
            "public_release_catalog_asset_likely": "UNKNOWN",
            "web_research_question": "Is there a job-keyed RADDiT predicted-power export covering Kestrel jobs known at 2025-03-31 18:00 AEST, with power-boundary and unit documentation?",
        },
        {
            "short_name": "Apr01_job_keyed_runtime_predictions",
            "expected_relative_path": "NOT_PRESENT; direct prediction table must name the Apr-01 Kestrel job namespace",
            "git_lfs_oid_sha256": None,
            "expected_size_bytes": None,
            "expected_schema_columns": "job_id,array_pos,submit_time,predicted_runtime_seconds,model_version,prediction_timestamp,optional_quantiles",
            "model_checkpoint_type": "direct frozen prediction payload",
            "why_required": "339 temporal jobs have zero causal predicted-runtime coverage.",
            "roles": ["runtime", "join"],
            "requirement": "MANDATORY_FOR_R4_OR_AS_VALIDATION_OF_R3",
            "closest_local_reference": "baseline_models.py:130-138 shows pre-aggregation keyed columns",
            "code_notebook_lines": "baseline_models.py:130-138; validate_datasets.ipynb cell 8",
            "public_release_catalog_asset_likely": "UNKNOWN",
            "web_research_question": "Is there a job-keyed causal RADDiT predicted-runtime export covering the Apr-01 D-1 queue, with prediction timestamps and units?",
        },
        {
            "short_name": "RADDiT_to_Kestrel_identity_contract",
            "expected_relative_path": "NOT_PRESENT",
            "git_lfs_oid_sha256": None,
            "expected_size_bytes": None,
            "expected_schema_columns": "documented exact job_id/array_pos namespace or deterministic transform",
            "model_checkpoint_type": None,
            "why_required": "J1/J2 equivalence between released RADDiT identities and the current Kestrel anonymized trace is not documented.",
            "roles": ["join"],
            "requirement": "MANDATORY_IF_DIRECT_ROWS_ARE_USED",
            "closest_local_reference": "Kestrel datacard id/job_id/array_pos; RADDiT baseline_models.py output columns",
            "code_notebook_lines": "baseline_models.py:121-123,131-133",
            "public_release_catalog_asset_likely": "UNKNOWN",
            "web_research_question": "Are RADDiT job_id and array_pos exactly the same anonymized Kestrel keys as the 2026 Kestrel release, or is there a documented deterministic mapping?",
        },
        {
            "short_name": "Kestrel_job_to_AIDC_PCC_binding",
            "expected_relative_path": "NOT_PRESENT",
            "git_lfs_oid_sha256": None,
            "expected_size_bytes": None,
            "expected_schema_columns": "job/resource_pool -> AIDC site/rack/PCC/phase/power coefficient, frozen before grid evaluation",
            "model_checkpoint_type": None,
            "why_required": "Without an exogenous exact/deterministic binding, feeder effects and Fresh comparison would be invented.",
            "roles": ["grid"],
            "requirement": "MANDATORY_FOR_EXACT_FRESH_AND_PRODUCTION",
            "closest_local_reference": "V35R3A_CRITICAL_SET.json records exact_job_grid_binding=false; local canonical runtime source has 0 rack_power_valid rows",
            "code_notebook_lines": "dayahead/v35r3a/pipeline.py:1381,1528-1600",
            "public_release_catalog_asset_likely": "UNKNOWN",
            "web_research_question": "Is there a pre-existing Kestrel GPU job/resource-pool to AIDC rack/PCC/phase mapping with a frozen power-boundary coefficient?",
        },
        {
            "short_name": "Kestrel_exact_scheduler_snapshot_and_config",
            "expected_relative_path": "NOT_PRESENT",
            "git_lfs_oid_sha256": None,
            "expected_size_bytes": None,
            "expected_schema_columns": "squeue/scontrol,sprio,slurm.conf,associations,reservations at D-1 issue",
            "model_checkpoint_type": None,
            "why_required": "Would upgrade the public-policy relative twin toward exact scheduler fidelity but is not needed for this fail-closed authority decision.",
            "roles": ["scheduler"],
            "requirement": "OPTIONAL_FOR_THIS_FORENSIC_MANDATORY_FOR_PRODUCTION_FIDELITY",
            "closest_local_reference": "V35R3A_SCHEDULER_POLICY_AUTHORITY.json",
            "code_notebook_lines": "dayahead/v35r3a/scheduler_twin.py",
            "public_release_catalog_asset_likely": False,
            "web_research_question": "Which public Kestrel scheduler-policy fields, if any, document the exact D-1 priority/reservation configuration without exposing sensitive operational data?",
        },
    ]
    for extra in extras:
        extra["exact_repository_source"] = "02_RADDiT" if "RADDiT" in extra["short_name"] or "model" in extra["short_name"] or "Apr01" in extra["short_name"] or "kestrel_baseline" in extra["short_name"] else "MobileESS/Kestrel authority"
        extra["repository_HEAD"] = RADDIT_HEAD if extra["exact_repository_source"] == "02_RADDiT" else SOURCE_PARENT
        requests.append(extra)
    return requests


def _feature_causality_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(model: str, feature: str, causal: bool, current: bool, role: str, reason: str) -> None:
        rows.append(
            {
                "candidate_model": model,
                "feature": feature,
                "known_at_submission_or_issue": causal,
                "available_in_current_Apr01_adapter": current,
                "role": role,
                "policy_read_count": 0,
                "authorized_for_replay": causal and current,
                "reason": reason,
            }
        )

    for feature, current in (
        ("nodes_req", True),
        ("wallclock_req_seconds", True),
        ("processors_req", True),
        ("memory_req_raw", False),
        ("job_type", False),
        ("user", False),
        ("account", False),
        ("partition", True),
        ("modules_set", False),
        ("conda_envs_set", False),
    ):
        add(
            "RADDiT_BASELINE_XGB",
            feature,
            True,
            current,
            "INPUT",
            "Submission-side in source design." if current else "Causal in principle but exact source-name/transform or field is absent from the frozen Apr-01 adapter.",
        )
    for feature in ("avg_power_per_node", "wallclock_used_sec", "future actual start", "future actual end"):
        add("RADDiT_BASELINE_XGB", feature, False, False, "LABEL_OR_FORBIDDEN", "Realized/future field; training label only and forbidden for policy inference.")
    add("RADDiT_SEMANTIC_SEARCH", "job script embedding", True, False, "INPUT", "Full pre-submission script/embedding and exact current-job binding are absent; a script hash is not the 4096-d embedding.")
    add("RADDiT_SEMANTIC_SEARCH", "neighbor end_time < issue", True, False, "TRAINING_FILTER", "Causal design is documented but historic LFS payload/vector index is absent.")
    add("RADDiT_SEMANTIC_SEARCH", "avg_power_per_node", False, False, "HISTORICAL_NEIGHBOR_LABEL", "Allowed only for neighbors completed before issue; payload absent and never read.")
    add("RADDiT_SEMANTIC_SEARCH", "wallclock_used_sec", False, False, "HISTORICAL_NEIGHBOR_LABEL", "Allowed only for neighbors completed before issue; payload absent and never read.")
    add("H0_REQUESTED_WALLTIME", "requested walltime", True, True, "INPUT", "Authorized conservative submission-side duration.")
    return rows


def _final_review(
    *,
    worktree: Path,
    power_decision: Mapping[str, Any],
    runtime_decision: Mapping[str, Any],
    h0: Mapping[str, Any],
    grid: Mapping[str, Any],
    service: Mapping[str, Any],
    lfs_rows: Sequence[Mapping[str, Any]],
    missing: Sequence[Mapping[str, Any]],
    test_report: Mapping[str, Any],
) -> dict[str, Any]:
    no_value = "NOT_AVAILABLE_AUTHORITY_BLOCKED"
    power_lfs = [row for row in lfs_rows if row["blocks_power_authority"]]
    runtime_lfs = [row for row in lfs_rows if row["blocks_runtime_authority"]]
    report = {
        "1": {"label": "parent HEAD", "value": SOURCE_PARENT},
        "2": {"label": "branch", "value": EXPECTED_BRANCH},
        "3": {"label": "worktree", "value": str(worktree)},
        "4": {"label": "final HEAD", "value": "RECORDED_AFTER_COMMIT_IN_FINAL_RESPONSE"},
        "5": {"label": "clean", "value": "EXPECTED_CLEAN_AFTER_COMMIT"},
        "6": {"label": "active worktree changes", "value": 0},
        "7": {"label": "downloaded-authority changes", "value": 0},
        "8": {"label": "network calls", "value": 0},
        "9": {"label": "push/merge", "value": "NO/NO"},
        "10": {"label": "power authority level", "value": POWER_AUTHORITY_LEVEL},
        "11": {"label": "real per-job power files found", "value": "NO_LOCAL_PREDICTED_PAYLOAD; historical measured/simulated Parquet only"},
        "12": {"label": "predicted vs measured", "value": "Predicted result names are LFS pointers; local ground_truth is realized"},
        "13": {"label": "units", "value": "RADDiT predicted target W/node; H0 proxy kW/requested-GPU"},
        "14": {"label": "job key", "value": "Released aggregate predictions contain no job key"},
        "15": {"label": "exact Apr-01 coverage", "value": "0/339 jobs; 0/14832 GPU-h"},
        "16": {"label": "PARTIAL/shared coverage", "value": "0/336; attribution ambiguous"},
        "17": {"label": "power P05/P50/P95/max", "value": no_value},
        "18": {"label": "same-GPU power spread", "value": no_value},
        "19": {"label": "double-counting status", "value": "BLOCKED_POWER_ATTRIBUTION_AMBIGUOUS; no per-job summation performed"},
        "20": {"label": "missing power assets/LFS OIDs", "value": {"pointer_count": len(power_lfs), "oids": [row["lfs_oid_sha256"] for row in power_lfs]}},
        "21": {"label": "runtime authority level", "value": RUNTIME_AUTHORITY_LEVEL},
        "22": {"label": "predicted-runtime files/models", "value": "Two result payloads are LFS pointers; training code has no input/checkpoint/preprocessor"},
        "23": {"label": "requested-walltime-only status", "value": True},
        "24": {"label": "exact Apr-01 coverage", "value": "0/339 causal predictions; requested walltime 339/339"},
        "25": {"label": "model quality", "value": no_value},
        "26": {"label": "requested-walltime/predicted-runtime ratio", "value": no_value},
        "27": {"label": "missing runtime assets/LFS OIDs", "value": {"pointer_count": len(runtime_lfs), "oids": [row["lfs_oid_sha256"] for row in runtime_lfs]}},
        "28": {"label": "H0 saturated slots", "value": h0["saturation_slots"]},
        "29": {"label": "HP saturated slots", "value": "NOT_RUN_POWER_AUTHORITY_UNAVAILABLE"},
        "30": {"label": "HPR saturated slots", "value": "NOT_RUN_POWER_AND_RUNTIME_AUTHORITY_UNAVAILABLE"},
        "31": {"label": "first capacity-release slot", "value": h0["first_capacity_release_slot"]},
        "32": {"label": "pending standby jobs started", "value": {"during_Apr01": h0["standby_jobs_started_during_Apr01"], "by_Apr01_end_including_issue_to_midnight": h0["standby_jobs_started_by_Apr01_end"]}},
        "33": {"label": "requested-walltime saturation artifact?", "value": SATURATION_CAUSE},
        "34": {"label": "exact key-join coverage", "value": "0/339 causal prediction rows"},
        "35": {"label": "inference coverage", "value": "0/339"},
        "36": {"label": "duplicates/conflicts", "value": {"causal_prediction_duplicate_keys": 0, "diagnostic_runtime_source_duplicate_keys": runtime_decision["diagnostic_source_duplicate_keys"], "Apr01_queue_one_to_many_conflicts": runtime_decision["Apr01_queue_one_to_many_conflicts"], "unmatched_temporal_jobs": 339}},
        "37": {"label": "job-to-AIDC binding status", "value": GRID_BINDING_STATUS},
        "38": {"label": "Fresh eligibility", "value": FRESH_STATUS},
        "39": {"label": "temporal jobs", "value": 339},
        "40": {"label": "W5-overlap jobs", "value": 202},
        "41": {"label": "generated exchange pairs", "value": 24},
        "42": {"label": "power-heterogeneous pairs", "value": 0},
        "43": {"label": "resource-feasible pairs", "value": 24},
        "44": {"label": "service-safe pairs", "value": {"H0_replayed": 24, "power_aware_intersection": 0}},
        "45": {"label": "grid-improving pairs", "value": 0},
        "46": {"label": "accepted reprioritizations", "value": 0},
        "47": {"label": "largest rejection reason", "value": "MODEL_AUTHORITY_UNAVAILABLE for 27,537 raw same-tier W5/outside-W5 pairs"},
        "48": {"label": "shifted GPU-hours", "value": 0.0},
        "49": {"label": "W1 IT-power reduction", "value": 0.0},
        "50": {"label": "W3 IT-power reduction", "value": 0.0},
        "51": {"label": "W5 IT-power reduction", "value": 0.0},
        "52": {"label": "PCC-power reduction", "value": "0.0 kW for identical H0; job-specific PCC unavailable"},
        "53": {"label": "rebound", "value": 0.0},
        "54": {"label": "Planning rho change", "value": 0.0},
        "55": {"label": "critical-exposure change", "value": "0.0 H0 proxy; exact unavailable"},
        "56": {"label": "Fresh result", "value": FRESH_STATUS},
        "57": {"label": "high/normal delay", "value": 0},
        "58": {"label": "completed-job delta", "value": 0.0},
        "59": {"label": "completed-GPU-hour delta", "value": 0.0},
        "60": {"label": "terminal-pending delta", "value": 0.0},
        "61": {"label": "future-feature reads", "value": 0},
        "62": {"label": "unsupported deadline", "value": "NO"},
        "63": {"label": "Fresh used during selection", "value": "NO"},
        "64": {"label": "exact missing assets", "value": {"count": len(missing), "manifest": "V35R3B_MISSING_EXTERNAL_AUTHORITY_REQUEST.json"}},
        "65": {"label": "mandatory/optional", "value": {"mandatory_or_conditional": sum(not str(row["requirement"]).startswith("OPTIONAL") for row in missing), "optional": sum(str(row["requirement"]).startswith("OPTIONAL") for row in missing)}},
        "66": {"label": "exact question for later web research", "value": [row["web_research_question"] for row in missing]},
        "67": {"label": "passed/failed", "value": test_report},
        "68": {"label": "primary classification", "value": PRIMARY_CLASSIFICATION},
        "69": {"label": "production recommendation", "value": f"PRODUCTION_INTEGRATION_RECOMMENDED = {PRODUCTION_RECOMMENDATION}"},
    }
    questions = {
        "Q1": "아니오. 파일명은 존재하지만 실제 predicted-power Parquet는 로컬 캐시에 없는 Git-LFS 포인터다.",
        "Q2": "아니오. 공개 aggregate 결과에는 job key가 없고 Apr-01 339건에 대한 직접 조인·모델 추론 coverage는 모두 0이다.",
        "Q3": "아니오. predicted-runtime 결과도 LFS 포인터이며 checkpoint/preprocessor와 Apr-01 출력이 없다. 허용된 권위는 requested walltime뿐이다.",
        "Q4": f"확정할 수 없다. H0는 96/96 슬롯 포화지만 PR을 만들 R2+ 권위가 없어 판정은 {SATURATION_CAUSE}다.",
        "Q5": "과학적으로 평가할 수 없다. 원리상 동일 GPU 점유에서도 job별 kW/GPU 차이는 값을 만들 수 있지만, Apr-01에 적용 가능한 권위가 없어 HP를 실행하지 않았다.",
        "Q6": "V35R3A는 24개 pair swap과 2개 전역 후보를 시험했으나 homogeneous proxy에서 25개는 전력 프로파일 개선이 없었고 1개는 서비스 게이트를 실패했다.",
        "Q7": "H0에서 resource-feasible하고 service-safe한 pair replay는 24개였지만, power-beneficial까지 권위 있게 입증된 교환의 교집합은 0개다.",
        "Q8": "NO. 미래 actual start/end/runtime을 정책 선택에 사용하지 않았다.",
        "Q9": "NO. 지원되지 않은 deadline을 만들지 않았다.",
        "Q10": "아니오. 정확한 job-to-AIDC/PCC binding 없이 Fresh feeder 결과를 만들면 유리한 매핑을 발명하게 된다.",
        "Q11": f"정확한 누락 목록은 manifest의 {len(missing)}개 항목이다. 핵심은 RADDiT LFS 객체 50개, baseline input/checkpoints/preprocessor, Apr-01 keyed predictions, identity contract, grid binding이다.",
        "Q12": "manifest 각 항목의 web_research_question을 그대로 조사해야 한다. 우선순위는 LFS OID 접근성, Apr-01 keyed power/runtime export, fitted checkpoint/preprocessor, identity contract, exogenous job-to-PCC binding이다.",
    }
    return {
        "artifact_id": "V35R3B_FINAL_REVIEW_V1",
        "status": "LOCAL_FORENSIC_COMPLETE_FAIL_CLOSED",
        "numbered_report": report,
        "questions": questions,
        "authority_decisions": {"power": power_decision, "runtime": runtime_decision},
        "mode_status": {"H0": "RUN", "HP": "NOT_RUN", "HPR": "NOT_RUN"},
        "grid": grid,
        "service": service,
    }


def _write_review_markdown(path: Path, review: Mapping[str, Any]) -> None:
    lines = [
        "# V35R3B 최종 검토",
        "",
        f"주 분류: `{review['numbered_report']['68']['value']}`",
        "",
        "## 1–69 보고",
        "",
    ]
    for number in range(1, 70):
        item = review["numbered_report"][str(number)]
        value = item["value"]
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        lines.append(f"{number}. **{item['label']}** — {rendered}")
    lines.extend(["", "## Q1–Q12", ""])
    for number in range(1, 13):
        lines.append(f"**Q{number}.** {review['questions'][f'Q{number}']}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    if _git(repo, "rev-parse", "HEAD") != SOURCE_PARENT:
        raise RuntimeError("V35R3B_EXACT_PARENT_REQUIRED_BEFORE_BUILD")
    if _git(repo, "branch", "--show-current") != EXPECTED_BRANCH:
        raise RuntimeError("V35R3B_WRONG_BRANCH")
    if repo != WORKTREE.resolve():
        raise RuntimeError(f"V35R3B_WRONG_WORKTREE:{repo}")

    artifact_dir = repo / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
    log_dir = repo / "logs" / ARTIFACT_DIRNAME
    artifact_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    parent_artifacts = repo / "dayahead" / "artifacts" / V35R3A_ARTIFACT_DIRNAME

    active_start = _status(ACTIVE_V35R3_WORKTREE)
    parent_start = _status(PARENT_WORKTREE)
    vendor_states = {
        "RADDiT": git_repository_state(RADDIT_ROOT),
        "FastSim": git_repository_state(FASTSIM_ROOT),
        "NLR_HPC_docs": git_repository_state(NLR_DOCS_ROOT),
        "Eagle_jobs_reference": git_repository_state(EAGLE_ROOT),
    }
    expected_heads = {
        "RADDiT": RADDIT_HEAD,
        "FastSim": FASTSIM_HEAD,
        "NLR_HPC_docs": NLR_DOCS_HEAD,
        "Eagle_jobs_reference": EAGLE_HEAD,
    }
    if any(vendor_states[name]["HEAD"] != expected for name, expected in expected_heads.items()):
        raise RuntimeError("V35R3B_VENDOR_HEAD_MISMATCH")

    start_state = {
        "artifact_id": "V35R3B_START_STATE_V1",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_parent": SOURCE_PARENT,
        "branch": EXPECTED_BRANCH,
        "worktree": str(repo),
        "target_worktree_status_at_creation": "",
        "active_V35R3_HEAD_at_start": _git(ACTIVE_V35R3_WORKTREE, "rev-parse", "HEAD"),
        "active_V35R3_status_at_start": active_start,
        "V35R3A_parent_HEAD_at_start": _git(PARENT_WORKTREE, "rev-parse", "HEAD"),
        "V35R3A_parent_status_at_start": parent_start,
        "vendor_repository_states_at_start": vendor_states,
        "network_calls_at_start": 0,
    }
    write_json(artifact_dir / "V35R3B_START_STATE.json", start_state)

    inventory_rows, inventory_summary = inventory_authority(AUTHORITY_ROOT)
    inventory_map = {str(row["relative_path"]): row for row in inventory_rows}
    if inventory_summary["lfs_pointer_count"] != 50:
        raise AssertionError(f"V35R3B_EXPECTED_50_LFS_POINTERS:{inventory_summary['lfs_pointer_count']}")
    write_csv(artifact_dir / "V35R3B_FILE_SCHEMA_INVENTORY.csv", inventory_rows)

    datacard = AUTHORITY_ROOT / "01_Kestrel_job_trace" / "datacard.md"
    if sha256_file(datacard) != KESTREL_DATACARD_SHA256:
        raise AssertionError("V35R3B_KESTREL_DATACARD_SHA_MISMATCH")
    if sha256_file(KESTREL_ARCHIVE) != KESTREL_ARCHIVE_SHA256:
        raise AssertionError("V35R3B_KESTREL_ARCHIVE_SHA_MISMATCH")
    local_inventory = {
        "artifact_id": "V35R3B_LOCAL_AUTHORITY_INVENTORY_V1",
        "authority_root": inventory_summary,
        "Kestrel_archive": {
            "path": str(KESTREL_ARCHIVE),
            "size_bytes": KESTREL_ARCHIVE.stat().st_size,
            "sha256": KESTREL_ARCHIVE_SHA256,
            "role": "existing V35R3A queue authority; not rescanned for future realized values",
        },
        "repositories": vendor_states,
        "expected_HEADs": expected_heads,
        "RADDiT_notebook_embedded_outputs": {
            "historic_job_trace": {"rows": 2_557_884, "columns": 20},
            "baseline_power_results": {"rows": 1_035_281, "columns": ["avg_power_per_node", "predicted_power"]},
            "baseline_runtime_results": {"rows": 1_035_281, "columns": ["wallclock_used_sec", "predicted_runtime_hours"]},
            "semantic_search_power_results": {"rows": 1_035_365, "columns": ["avg_power_per_node", "predicted_power"]},
            "semantic_search_runtime_results": {"rows": 1_035_365, "columns": ["wallclock_used_sec", "predicted_runtime_hours"]},
            "authority_note": "Embedded outputs prove historical shape only; they are not payloads and contain no released job identity for aggregate results.",
        },
        "model_checkpoint_count_relevant_to_RADDiT": 0,
        "redacted_internal_preprocessing": "Kestrel datacard says database functions/triggers are not publicly released; no J2 identity/power attribution logic found.",
        "unsafe_pickle_policy": "Pickles inventoried by SHA but not deserialized because arbitrary code execution would not be a safe schema read.",
    }
    write_json(artifact_dir / "V35R3B_LOCAL_AUTHORITY_INVENTORY.json", local_inventory)

    lfs_rows = _lfs_audit(inventory_rows)
    write_csv(artifact_dir / "V35R3B_LFS_PLACEHOLDER_AUDIT.csv", lfs_rows)

    baseline_path = parent_artifacts / "V35R3A_BASELINE_SCHEDULE.parquet"
    search_path = parent_artifacts / "V35R3A_SEARCH_TRACE.csv"
    service_path = parent_artifacts / "V35R3A_KQ0_SERVICE_GATE.json"
    baseline = pd.read_parquet(baseline_path)
    search = pd.read_csv(search_path)
    parent_service = json.loads(service_path.read_text(encoding="utf-8"))
    temporal = baseline.loc[
        baseline["workload_class"].isin(["NORMAL_QUEUE_CONTROLLED", "STANDBY_QUEUE_CONTROLLED"])
    ].copy()
    standby = temporal.loc[temporal["qos"].str.lower().eq("standby")].copy()
    if len(temporal) != 339 or len(standby) != 338:
        raise AssertionError("V35R3B_PARENT_TEMPORAL_CENSUS_MISMATCH")

    canonical_path = repo / "stage7" / "r13_zero_burnin" / "C_TO_D_FINAL" / "independent_job_authority" / "PER_JOB_RUNTIME_SOURCE_CANONICAL_V2044R5.parquet"
    canonical = pd.read_parquet(canonical_path)
    baseline_keys = baseline["job_id"].map(normalize_job_key)
    canonical_keys = canonical["source_job_id"].map(normalize_job_key)
    canonical_key_counts = canonical_keys.value_counts(dropna=True)
    canonical_duplicate_keys = canonical_key_counts.loc[canonical_key_counts > 1]
    unique_canonical_keys = set(canonical_key_counts.loc[canonical_key_counts == 1].index)
    all_canonical_keys = set(canonical_key_counts.index)
    canonical_matches = baseline_keys.isin(unique_canonical_keys)
    canonical_any_matches = baseline_keys.isin(all_canonical_keys)
    canonical_queue_conflicts = baseline_keys.map(canonical_key_counts).fillna(0).gt(1)
    canonical_runtime = {
        "path": str(canonical_path),
        "relative_path": canonical_path.relative_to(repo).as_posix(),
        "sha256": sha256_file(canonical_path),
        "row_count": len(canonical),
        "valid_power_rows": int(canonical["IT_power_kW"].notna().sum()),
        "rack_power_valid_rows": int(canonical["rack_power_valid"].sum()),
        "duplicate_source_job_id_keys": len(canonical_duplicate_keys),
        "duplicate_source_job_id_rows": int(canonical_duplicate_keys.sum()),
        "running_matches": int((canonical_matches & baseline["state_at_issue"].eq("RUNNING")).sum()),
        "pending_matches": int((canonical_matches & baseline["state_at_issue"].eq("PENDING")).sum()),
        "temporal_matches": int((canonical_matches & baseline["workload_class"].isin(["NORMAL_QUEUE_CONTROLLED", "STANDBY_QUEUE_CONTROLLED"])).sum()),
        "Apr01_queue_any_key_matches": int(canonical_any_matches.sum()),
        "Apr01_queue_one_to_many_conflicts": int(canonical_queue_conflicts.sum()),
    }
    canonical_power = canonical_runtime

    power_objects = _power_objects(inventory_map, lfs_rows, canonical_power)
    runtime_objects = _runtime_objects(inventory_map, lfs_rows, canonical_runtime)
    write_csv(artifact_dir / "V35R3B_POWER_OBJECT_CLASSIFICATION.csv", power_objects)
    write_csv(artifact_dir / "V35R3B_RUNTIME_OBJECT_CLASSIFICATION.csv", runtime_objects)

    power_decision = {
        "artifact_id": "V35R3B_POWER_AUTHORITY_DECISION_V1",
        "authority_level": POWER_AUTHORITY_LEVEL,
        "decision": "NO_LOCALLY_USABLE_CAUSAL_PER_JOB_PREDICTED_POWER",
        "primary_local_authority": "homogeneous aggregate kW/requested-GPU proxy only",
        "candidate_paths": {
            "baseline_results": "LFS_POINTER_PAYLOAD_ABSENT_AND_RELEASED_SCHEMA_HAS_NO_JOB_KEY",
            "semantic_results": "LFS_POINTER_PAYLOAD_AND_EMBEDDINGS_ABSENT_NO_CURRENT_JOB_BINDING",
            "published_replay": "BLOCKED_INPUT_CHECKPOINT_PREPROCESSOR_AND_APR01_HORIZON",
            "ground_truth": "MEASURED_REALIZED_NO_JOB_KEY_POWER_ATTRIBUTION_AMBIGUOUS",
            "Kestrel_energy": "REALIZED_AFTER_EXECUTION_NOT_PREDICTION",
        },
        "Apr01_temporal_job_coverage": 0,
        "Apr01_temporal_requested_GPU_hours_coverage": 0.0,
        "Apr01_partial_shared_coverage": 0,
        "power_attribution": "POWER_ATTRIBUTION_AMBIGUOUS_FOR_336_PARTIAL_SHARED_JOBS",
        "usable_job_power_heterogeneity": "NO_USABLE_JOB_POWER_HETEROGENEITY_AUTHORITY",
        "HP_eligible": False,
        "P3_P4_claimed": False,
    }
    runtime_decision = {
        "artifact_id": "V35R3B_RUNTIME_AUTHORITY_DECISION_V1",
        "authority_level": RUNTIME_AUTHORITY_LEVEL,
        "decision": "REQUESTED_WALLTIME_ONLY",
        "candidate_paths": {
            "baseline_results": "LFS_POINTER_PAYLOAD_ABSENT_AND_RELEASED_SCHEMA_HAS_NO_JOB_KEY",
            "semantic_results": "LFS_POINTER_PAYLOAD_AND_EMBEDDINGS_ABSENT",
            "published_replay": "BLOCKED_INPUT_CHECKPOINT_PREPROCESSOR_AND_APR01_HORIZON",
            "MobileESS_independent_runtime_source": "REALIZED_EXPOST_NOT_CAUSAL; 0 temporal matches",
            "ground_truth": "REALIZED_NO_JOB_KEY",
        },
        "Apr01_temporal_causal_prediction_coverage": 0,
        "Apr01_temporal_requested_walltime_coverage": len(temporal),
        "running_remaining_duration_authority": "REMAINING_REQUESTED_WALLTIME_CONSERVATIVE",
        "pending_duration_authority": "REQUESTED_WALLTIME",
        "HPR_eligible": False,
        "R3_R4_claimed": False,
        "diagnostic_source_duplicate_keys": canonical_runtime["duplicate_source_job_id_keys"],
        "Apr01_queue_one_to_many_conflicts": canonical_runtime["Apr01_queue_one_to_many_conflicts"],
    }
    write_json(artifact_dir / "V35R3B_POWER_AUTHORITY_DECISION.json", power_decision)
    write_json(artifact_dir / "V35R3B_RUNTIME_AUTHORITY_DECISION.json", runtime_decision)

    def population(frame: pd.DataFrame, name: str) -> dict[str, Any]:
        node_hours = float((frame["requested_nodes"] * frame["duration_slots"] * SLOT_MINUTES / 60.0).sum())
        gpu_hours = float(frame["request_gpu_hours"].sum())
        partial = int((frame["requested_gpus"] < 4 * frame["requested_nodes"]).sum())
        return {
            "population": name,
            "job_count": len(frame),
            "requested_GPU_hours": gpu_hours,
            "requested_node_hours": node_hours,
            "FULL_count": len(frame) - partial,
            "PARTIAL_shared_count": partial,
            "qos_counts": frame["qos"].value_counts().to_dict(),
        }

    populations = [
        population(baseline.loc[baseline["state_at_issue"].eq("RUNNING")], "running"),
        {"population": "raw_pending", "job_count": 421, "requested_GPU_hours": 14832.0, "requested_node_hours": 16608.0, "FULL_count": 3, "PARTIAL_shared_count": 336, "qos_counts": {"standby": 420, "normal": 1}},
        population(temporal, "temporal_controlled"),
        population(standby, "standby_controlled"),
    ]
    join_rows: list[dict[str, Any]] = []
    for pop in populations:
        for authority, join_level, coverage, reason in (
            ("RADDiT released aggregate power results", "J1_BLOCKED_NO_KEY_AND_LFS", 0, "Aggregate schemas have no job key; local files are LFS pointers."),
            ("RADDiT released aggregate runtime results", "J1_BLOCKED_NO_KEY_AND_LFS", 0, "Aggregate schemas have no job key; local files are LFS pointers."),
            ("RADDiT published model inference", "J3_BLOCKED_INCOMPLETE_MODEL", 0, "Missing exact input, checkpoint, preprocessing, and Apr-01 horizon."),
            ("RADDiT ground_truth composite diagnostic", "J4_NOT_ATTEMPTED_AS_AUTHORITY", 0, "No job_id and historical 2024 window; fuzzy/composite join forbidden for production."),
            (
                "MobileESS independent realized-runtime source",
                "J1_DIAGNOSTIC_REALIZED_ONLY",
                canonical_runtime["running_matches"] if pop["population"] == "running" else 0,
                "Exact IDs for nine running jobs only; ex-post duration is forbidden and temporal coverage is zero.",
            ),
        ):
            join_rows.append(
                {
                    **pop,
                    "authority_object": authority,
                    "join_level": join_level,
                    "causal_prediction_matched_jobs": 0,
                    "diagnostic_exact_matches": coverage,
                    "causal_prediction_requested_GPU_hours_covered": 0.0,
                    "causal_prediction_requested_node_hours_covered": 0.0,
                    "duplicate_key_count": canonical_runtime["duplicate_source_job_id_keys"] if authority.startswith("MobileESS") else 0,
                    "one_to_many_conflicts": canonical_runtime["Apr01_queue_one_to_many_conflicts"] if authority.startswith("MobileESS") else 0,
                    "unknown_count": pop["job_count"],
                    "unmatched_count": pop["job_count"],
                    "unmatched_reason": reason,
                }
            )
    write_csv(artifact_dir / "V35R3B_JOB_ID_JOIN_AUDIT.csv", join_rows)

    temporal_gpu_hours = float(temporal["request_gpu_hours"].sum())
    temporal_node_hours = float((temporal["requested_nodes"] * temporal["duration_slots"] * SLOT_MINUTES / 60.0).sum())
    power_coverage = {
        "artifact_id": "V35R3B_APR01_POWER_COVERAGE_V1",
        "temporal_jobs": len(temporal),
        "covered_jobs": 0,
        "coverage_fraction": 0.0,
        "requested_GPU_hours_total": temporal_gpu_hours,
        "requested_GPU_hours_covered": 0.0,
        "requested_node_hours_total": temporal_node_hours,
        "requested_node_hours_covered": 0.0,
        "FULL_jobs": int((temporal["requested_gpus"] == 4 * temporal["requested_nodes"]).sum()),
        "PARTIAL_shared_jobs": int((temporal["requested_gpus"] < 4 * temporal["requested_nodes"]).sum()),
        "PARTIAL_shared_covered": 0,
        "standby_jobs": len(standby),
        "standby_covered": 0,
        "normal_jobs": int(temporal["qos"].eq("normal").sum()),
        "normal_covered": 0,
        "unknown_prediction_count": len(temporal),
        "duplicate_key_count": 0,
        "one_to_many_conflicts": 0,
        "inference_coverage": 0,
        "distribution": {"P05_W": None, "P50_W": None, "P95_W": None, "max_W": None, "kW_per_GPU": None, "coefficient_of_variation": None, "same_GPU_spread": None, "distinguishable_power_tiers": 0},
        "classification": "NO_USABLE_JOB_POWER_HETEROGENEITY_AUTHORITY",
    }
    runtime_coverage = {
        "artifact_id": "V35R3B_APR01_RUNTIME_COVERAGE_V1",
        "temporal_jobs": len(temporal),
        "causal_predicted_runtime_covered_jobs": 0,
        "causal_coverage_fraction": 0.0,
        "requested_walltime_covered_jobs": len(temporal),
        "requested_walltime_coverage_fraction": 1.0,
        "requested_GPU_hours_total": temporal_gpu_hours,
        "causal_predicted_runtime_GPU_hours_covered": 0.0,
        "requested_node_hours_total": temporal_node_hours,
        "causal_predicted_runtime_node_hours_covered": 0.0,
        "PARTIAL_shared_causal_coverage": 0,
        "standby_causal_coverage": 0,
        "unknown_prediction_count": len(temporal),
        "duplicate_key_count": 0,
        "one_to_many_conflicts": 0,
        "inference_coverage": 0,
        "requested_walltime_to_predicted_runtime_ratio": None,
    }
    write_json(artifact_dir / "V35R3B_APR01_POWER_COVERAGE.json", power_coverage)
    write_json(artifact_dir / "V35R3B_APR01_RUNTIME_COVERAGE.json", runtime_coverage)

    causal_rows = _feature_causality_rows()
    write_csv(artifact_dir / "V35R3B_FEATURE_CAUSALITY_AUDIT.csv", causal_rows)
    causal_counters = causal_feature_audit(["nodes_req", "requested walltime", "partition", "qos"])

    power_distribution = []
    runtime_distribution = []
    for row in temporal.sort_values("job_id").itertuples(index=False):
        partial = float(row.requested_gpus) < 4 * int(row.requested_nodes)
        power_distribution.append(
            {
                "job_id": normalize_job_key(row.job_id),
                "qos": row.qos,
                "workload_class": row.workload_class,
                "requested_nodes": row.requested_nodes,
                "requested_gpus": row.requested_gpus,
                "FULL_PARTIAL_shared": "PARTIAL_SHARED" if partial else "FULL_NODE_REQUEST",
                "requested_GPU_hours": row.request_gpu_hours,
                "predicted_power_W": None,
                "predicted_total_job_IT_kW": None,
                "predicted_kW_per_GPU": None,
                "H0_proxy_job_kW": float(row.requested_gpus) * H0_KW_PER_GPU,
                "power_authority": POWER_AUTHORITY_LEVEL,
                "prediction_status": "UNAVAILABLE_LFS_MODEL_JOIN_AND_ATTRIBUTION_BLOCKED",
            }
        )
        runtime_distribution.append(
            {
                "job_id": normalize_job_key(row.job_id),
                "qos": row.qos,
                "workload_class": row.workload_class,
                "requested_gpus": row.requested_gpus,
                "requested_walltime_slots": row.duration_slots,
                "requested_walltime_hours": float(row.duration_slots) * SLOT_MINUTES / 60.0,
                "predicted_runtime_seconds": None,
                "predicted_runtime_hours": None,
                "authorized_duration_slots": row.duration_slots,
                "duration_authority": RUNTIME_AUTHORITY_LEVEL,
                "prediction_status": "UNAVAILABLE_LFS_MODEL_AND_JOIN_BLOCKED",
            }
        )
    write_csv(artifact_dir / "V35R3B_APR01_JOB_POWER_DISTRIBUTION.csv", power_distribution)
    write_csv(artifact_dir / "V35R3B_APR01_JOB_RUNTIME_DISTRIBUTION.csv", runtime_distribution)

    gpu_profile = target_gpu_profile(baseline)
    if not np.allclose(gpu_profile, GPU_CAPACITY, atol=1e-9, rtol=0.0):
        raise AssertionError("V35R3B_H0_EXPECTED_FULL_APR01_SATURATION")
    pending_schedulable = baseline.loc[baseline["state_at_issue"].eq("PENDING")]
    started_during = pending_schedulable.loc[
        (pending_schedulable["scheduled_start_slot"] >= 24)
        & (pending_schedulable["scheduled_start_slot"] < 24 + TARGET_SLOTS)
    ]
    started_by_end = pending_schedulable.loc[pending_schedulable["scheduled_start_slot"] < 24 + TARGET_SLOTS]
    capacity_rows = []
    for slot, occupancy in enumerate(gpu_profile):
        when = TARGET_START + timedelta(minutes=slot * SLOT_MINUTES)
        absolute_slot = slot + 24
        capacity_rows.append(
            {
                "target_slot": slot,
                "issue_relative_slot": absolute_slot,
                "timestamp_AEST": when.isoformat(),
                "duration_authority": "REQUESTED_WALLTIME",
                "occupied_GPUs": float(occupancy),
                "free_GPUs": float(GPU_CAPACITY - occupancy),
                "saturated_624": bool(abs(occupancy - GPU_CAPACITY) <= 1e-9),
                "W1": absolute_slot in W1,
                "W3": absolute_slot in W3,
                "W5": absolute_slot in W5,
            }
        )
    write_csv(artifact_dir / "V35R3B_CAPACITY_RELEASE_RW.csv", capacity_rows)

    w5_overlap = temporal.loc[
        (temporal["scheduled_start_slot"] < max(W5) + 1)
        & (temporal["scheduled_end_slot"] > min(W5))
    ]
    outside_w5 = temporal.loc[temporal["scheduled_start_slot"] >= max(W5) + 1]
    w5_standby = w5_overlap.loc[w5_overlap["qos"].eq("standby")]
    outside_standby = outside_w5.loc[outside_w5["qos"].eq("standby")]
    raw_same_tier_pairs = len(w5_standby) * len(outside_standby)
    pair_mask = search["candidate"].str.startswith("STANDBY_W5_PAIR_SWAP:")
    replayed_pairs = search.loc[pair_mask]
    replayed_pair_service_safe = int(replayed_pairs["service_gate_passed"].astype(bool).sum())
    waterfall = [
        {"stage": 1, "name": "temporal-controlled jobs", "count": len(temporal), "unit": "jobs", "note": "14832 GPU-h"},
        {"stage": 2, "name": "jobs scheduled/active under baseline", "count": len(temporal), "unit": "jobs", "note": f"all scheduled; {int(((temporal.scheduled_start_slot < 120) & (temporal.scheduled_end_slot > 24)).sum())} active at some point in Apr-01"},
        {"stage": 3, "name": "jobs overlapping W1/W3/W5", "count": len(w5_overlap), "unit": "jobs", "note": f"standby={len(w5_standby)}, normal={len(w5_overlap)-len(w5_standby)}"},
        {"stage": 4, "name": "jobs outside W5 available for exchange", "count": len(outside_w5), "unit": "jobs", "note": f"standby={len(outside_standby)}"},
        {"stage": 5, "name": "same-tier raw pair universe", "count": raw_same_tier_pairs, "unit": "pairs", "note": "201 W5 standby x 137 outside-W5 standby"},
        {"stage": 6, "name": "resource-compatible exchange pairs replayed by V35R3A", "count": len(replayed_pairs), "unit": "pairs", "note": "deterministic scheduler replay; occupancy <=624"},
        {"stage": 7, "name": "authority-validated power-heterogeneous exchange pairs", "count": 0, "unit": "pairs", "note": "P2+ unavailable"},
        {"stage": 8, "name": "queue-feasible power-aware candidates", "count": 0, "unit": "pairs", "note": "power gate not reached"},
        {"stage": 9, "name": "tier-service-safe power-aware candidates", "count": 0, "unit": "pairs", "note": f"H0-only pair replays service-safe={replayed_pair_service_safe}"},
        {"stage": 10, "name": "candidates with lower predicted W5 power", "count": 0, "unit": "pairs", "note": "prediction unavailable"},
        {"stage": 11, "name": "candidates with lower Planning rho", "count": 0, "unit": "pairs", "note": "binding incomplete and no power-aware candidate"},
        {"stage": 12, "name": "accepted candidates", "count": 0, "unit": "pairs", "note": "no HP/HPR run"},
    ]
    write_csv(artifact_dir / "V35R3B_CANDIDATE_WATERFALL.csv", waterfall)

    rejection_rows = [
        {
            "mode": "HP_HPR_GATE",
            "candidate_id": "RAW_SAME_TIER_W5_OUTSIDE_W5_PAIR_UNIVERSE",
            "rejection_count": raw_same_tier_pairs,
            "counted_in_H0_candidate_conservation": False,
            "primary_reason": "MODEL_AUTHORITY_UNAVAILABLE",
            "detail": "P2+ power authority is absent, so raw pairs are not promoted to power-aware candidates.",
        }
    ]
    for row in search.itertuples(index=False):
        if row.reason == "SERVICE_GATE_FAIL":
            reason = "COMPLETED_WORK_DEGRADATION"
            detail = "V35R3A strict tier-aware service gate failed."
        else:
            reason = "SAME_PREDICTED_POWER"
            detail = "Homogeneous kW/GPU proxy and 624-GPU saturation leave W5 aggregate IT power unchanged."
        rejection_rows.append(
            {
                "mode": "H0",
                "candidate_id": row.candidate,
                "rejection_count": 1,
                "counted_in_H0_candidate_conservation": True,
                "primary_reason": reason,
                "detail": detail,
            }
        )
    write_csv(artifact_dir / "V35R3B_CANDIDATE_REJECTION_REASONS.csv", rejection_rows)

    h0 = {
        "artifact_id": "V35R3B_MODE_H0_RESULTS_V1",
        "status": "EXECUTED_H0_REPRODUCTION",
        "mode": "H0_HOMOGENEOUS_POWER_REQUESTED_WALLTIME",
        "parent_schedule_path": str(baseline_path.relative_to(repo)),
        "parent_schedule_sha256": sha256_file(baseline_path),
        "scheduler_authority": "PUBLIC_POLICY_RELATIVE_SCHEDULER_TWIN",
        "running_jobs": 243,
        "raw_pending_jobs": 421,
        "schedulable_pending_jobs": len(pending_schedulable),
        "temporal_candidates": len(temporal),
        "occupancy_GPUs_96_slots": gpu_profile.tolist(),
        "occupancy_GPU_hours": profile_energy_gpu_hours(gpu_profile),
        "saturation_slots": int(np.isclose(gpu_profile, GPU_CAPACITY).sum()),
        "minimum_free_GPU_capacity": float((GPU_CAPACITY - gpu_profile).min()),
        "first_capacity_release_slot": None,
        "first_capacity_release_status": "NONE_IN_APR01_96_SLOTS",
        "GPU_hours_free_for_additional_pending_work": float((GPU_CAPACITY - gpu_profile).sum() * SLOT_MINUTES / 60.0),
        "pending_jobs_started_during_Apr01": len(started_during),
        "standby_jobs_started_during_Apr01": int(started_during["qos"].eq("standby").sum()),
        "normal_jobs_started_during_Apr01": int(started_during["qos"].eq("normal").sum()),
        "pending_jobs_started_by_Apr01_end": len(started_by_end),
        "standby_jobs_started_by_Apr01_end": int(started_by_end["qos"].eq("standby").sum()),
        "normal_jobs_started_by_Apr01_end": int(started_by_end["qos"].eq("normal").sum()),
        "W1_W3_W5_free_GPU_capacity": {"W1": 0.0, "W3": 0.0, "W5": 0.0},
        "generated_scheduler_candidates": len(search),
        "generated_exchange_pairs": len(replayed_pairs),
        "service_safe_scheduler_candidates": int(search["service_gate_passed"].astype(bool).sum()),
        "service_safe_exchange_pairs": replayed_pair_service_safe,
        "accepted_reprioritizations": 0,
        "advanced_jobs": 0,
        "delayed_jobs": 0,
        "shifted_GPU_hours": 0.0,
        "homogeneous_IT_kW_per_requested_GPU": H0_KW_PER_GPU,
        "IT_power_kW_96_slots": (gpu_profile * H0_KW_PER_GPU).tolist(),
        "IT_power_change_kW": {"W1": 0.0, "W3": 0.0, "W5": 0.0},
        "PCC_power_change_kW": {"W1": 0.0, "W3": 0.0, "W5": 0.0},
        "maximum_rebound_kW": 0.0,
        "Planning_rho_baseline": PLANNING_RHO,
        "Planning_rho_controlled": PLANNING_RHO,
        "Planning_rho_change": 0.0,
        "critical_exposure_exact": None,
        "critical_exposure_proxy_change_kW_slots": 0.0,
        "service_metrics": parent_service,
        "causality_counters": causal_counters,
        "unsupported_deadline": False,
        "Fresh_used_during_selection": False,
    }
    write_json(artifact_dir / "V35R3B_MODE_H0_RESULTS.json", h0)

    binding = {
        "artifact_id": "V35R3B_JOB_GRID_BINDING_AUDIT_V1",
        "classification": GRID_BINDING_STATUS,
        "search_scope": ["current MobileESS code/artifacts", str(AUTHORITY_ROOT)],
        "acceptable_binding_found": False,
        "V35R3A_exact_job_grid_binding": False,
        "MobileESS_independent_runtime_source": {
            "path": canonical_runtime["relative_path"],
            "rows": canonical_runtime["row_count"],
            "temporal_exact_ID_matches": canonical_runtime["temporal_matches"],
            "valid_IT_power_rows": canonical_runtime["valid_power_rows"],
            "rack_power_valid_rows": canonical_runtime["rack_power_valid_rows"],
        },
        "rejected_mappings": ["grid-benefit-selected site", "random assignment", "new equal split", "all jobs to most sensitive AIDC"],
        "PCC_trajectory_status": "UNAVAILABLE_WITHOUT_INVENTED_BINDING",
        "Fresh_eligibility": False,
        "Fresh_status": FRESH_STATUS,
    }
    write_json(artifact_dir / "V35R3B_JOB_GRID_BINDING_AUDIT.json", binding)

    service = {
        "artifact_id": "V35R3B_SERVICE_GATE_V1",
        "H0_identity_result": "PASS",
        "H0_parent_gate": parent_service,
        "HP_result": "NOT_EVALUATED_POWER_AUTHORITY_UNAVAILABLE",
        "HPR_result": "NOT_EVALUATED_POWER_AND_RUNTIME_AUTHORITY_UNAVAILABLE",
        "running_unchanged": True,
        "preemption_count": 0,
        "high_normal_delay_count": 0,
        "normal_completed_job_delta": 0.0,
        "normal_completed_GPU_hour_delta": 0.0,
        "normal_terminal_pending_GPU_hour_delta": 0.0,
        "standby_completed_job_delta": 0.0,
        "standby_completed_GPU_hour_delta": 0.0,
        "standby_terminal_pending_GPU_hour_delta": 0.0,
        "standby_displaces_high_normal": False,
        "arbitrary_tolerance": 0.0,
        "unsupported_deadline": False,
    }
    write_json(artifact_dir / "V35R3B_SERVICE_GATE.json", service)

    grid = {
        "artifact_id": "V35R3B_GRID_EFFECT_V1",
        "H0": {
            "schedule_identical": True,
            "shifted_GPU_hours": 0.0,
            "IT_power_reduction_kW": {"W1": 0.0, "W3": 0.0, "W5": 0.0},
            "equivalent_PCC_power_reduction_kW": {"W1": 0.0, "W3": 0.0, "W5": 0.0},
            "rebound_kW": 0.0,
            "Planning_rho_change": 0.0,
            "critical_exposure_proxy_change": 0.0,
        },
        "HP": "NOT_RUN_POWER_AUTHORITY_UNAVAILABLE",
        "HPR": "NOT_RUN_POWER_AND_RUNTIME_AUTHORITY_UNAVAILABLE",
        "job_specific_site_aggregate_IT_power": "NOT_CONSTRUCTED_INVALID_AUTHORITY",
        "exact_PCC_effect": "UNAVAILABLE_GRID_BINDING_INCOMPLETE",
        "Fresh_status": FRESH_STATUS,
        "interpretation": "No claim of NO_GRID_BENEFIT is made; required power/runtime/binding evaluations are blocked.",
    }
    write_json(artifact_dir / "V35R3B_GRID_EFFECT.json", grid)

    missing = _missing_manifest(lfs_rows)
    missing_payload = {
        "artifact_id": "V35R3B_MISSING_EXTERNAL_AUTHORITY_REQUEST_V1",
        "generated_offline": True,
        "guessed_URLs": False,
        "missing_object_count": len(missing),
        "requests": missing,
    }
    write_json(artifact_dir / "V35R3B_MISSING_EXTERNAL_AUTHORITY_REQUEST.json", missing_payload)

    recommendation = {
        "artifact_id": "V35R3B_PRODUCTION_INTEGRATION_RECOMMENDATION_V1",
        "PRODUCTION_INTEGRATION_RECOMMENDED": PRODUCTION_RECOMMENDATION,
        "primary_classification": PRIMARY_CLASSIFICATION,
        "reason": "Local files cannot support causal job-specific power or runtime for Apr-01; shared-node attribution and exact job-grid binding are also incomplete.",
        "conditions_not_met": ["P2+ power authority", "R2+ runtime authority or proven capacity availability", "Apr-01 prediction coverage", "incremental shared-job power semantics", "exact job-grid binding", "Planning/Fresh controlled validation"],
        "production_files_modified": 0,
        "AIDC_MESS_science_modified": False,
        "Apr02_or_later_run": False,
        "Apr21_read": False,
        "May_opened": False,
        "push": False,
        "merge": False,
    }
    write_json(artifact_dir / "V35R3B_PRODUCTION_INTEGRATION_RECOMMENDATION.json", recommendation)
    write_json(
        artifact_dir / "V35R3B_REPAIR_LOG.json",
        {
            "artifact_id": "V35R3B_REPAIR_LOG_V1",
            "repairs": [
                {
                    "signature": "WINERROR_1920_UNRESOLVED_NLR_DOCS_SYMLINK_DURING_INVENTORY",
                    "attempt": 1,
                    "repair": "Use lstat, inventory unresolved link/reparse entries without opening or following their targets.",
                    "invalidated_stage": "local file/schema inventory only",
                    "scientific_rules_changed": False,
                },
                {
                    "signature": "DUPLICATE_AUTHORITY_JOB_KEY_IN_MOBILEESS_RUNTIME_SOURCE",
                    "attempt": 1,
                    "repair": "Keep strict duplicate-key rejection; audit duplicate source keys and count only unique exact keys as diagnostic matches.",
                    "invalidated_stage": "job identity join audit only",
                    "scientific_rules_changed": False,
                },
                {
                    "signature": "ACTIVE_V35R3_EXTERNAL_PROCESS_STATUS_CHANGED_DURING_REGRESSION",
                    "attempt": 1,
                    "repair": "Audit start/end HEAD and status separately; do not misattribute another worktree's completed commit to V35R3B writes.",
                    "invalidated_stage": "isolation regression assertion only",
                    "scientific_rules_changed": False,
                },
            ],
            "unique_failure_signatures": 3,
            "scientific_rules_changed": False,
        },
    )

    isolation = {
        "artifact_id": "V35R3B_ISOLATION_AUDIT_V1",
        "source_parent": SOURCE_PARENT,
        "branch": EXPECTED_BRANCH,
        "worktree": str(repo),
        "worktree_separate": repo not in {PARENT_WORKTREE.resolve(), ACTIVE_V35R3_WORKTREE.resolve()},
        "artifact_root": str(artifact_dir.relative_to(repo)),
        "cache_root": f"dayahead/cache/{ARTIFACT_DIRNAME}/",
        "log_root": str(log_dir.relative_to(repo)),
        "paths_shared_with_active_V35R3": False,
        "paths_shared_with_V35R3A_artifacts": False,
        "active_V35R3_HEAD_at_start": start_state["active_V35R3_HEAD_at_start"],
        "active_V35R3_status_at_start": active_start,
        "V35R3A_parent_HEAD_at_start": start_state["V35R3A_parent_HEAD_at_start"],
        "V35R3A_parent_status_at_start": parent_start,
        "active_V35R3_files_changed_by_this_task": 0,
        "V35R3A_parent_worktree_files_changed_by_this_task": 0,
        "downloaded_authority_files_changed_by_this_task": 0,
        "authority_content_fingerprint_at_start": inventory_summary["content_fingerprint_sha256"],
        "network_calls": len(NETWORK_COMMANDS_EXECUTED),
        "network_commands_executed": list(NETWORK_COMMANDS_EXECUTED),
        "push_performed": PUSH_PERFORMED,
        "merge_performed": MERGE_PERFORMED,
        "production_files_modified": 0,
        "allowed_write_namespaces": ["dayahead/v35r3b/", "tools/v35r3b/", "tests/dayahead/test_v35r3b_", f"dayahead/artifacts/{ARTIFACT_DIRNAME}/", f"logs/{ARTIFACT_DIRNAME}/"],
    }
    write_json(artifact_dir / "V35R3B_ISOLATION_AUDIT.json", isolation)

    pending_test = {
        "artifact_id": "V35R3B_TEST_REPORT_V1",
        "status": "PENDING",
        "passed": 0,
        "failed": 0,
    }
    write_json(artifact_dir / "V35R3B_TEST_REPORT.json", pending_test)
    review = _final_review(
        worktree=repo,
        power_decision=power_decision,
        runtime_decision=runtime_decision,
        h0=h0,
        grid=grid,
        service=service,
        lfs_rows=lfs_rows,
        missing=missing,
        test_report=pending_test,
    )
    write_json(artifact_dir / "V35R3B_FINAL_REVIEW.json", review)
    _write_review_markdown(artifact_dir / "V35R3B_FINAL_REVIEW.md", review)

    summary = {
        "artifact_id": "V35R3B_BUILD_SUMMARY_V1",
        "primary_classification": PRIMARY_CLASSIFICATION,
        "power_authority": POWER_AUTHORITY_LEVEL,
        "runtime_authority": RUNTIME_AUTHORITY_LEVEL,
        "H0_saturation_slots": int(np.isclose(gpu_profile, GPU_CAPACITY).sum()),
        "HP_run": False,
        "HPR_run": False,
        "Fresh_run": False,
        "required_artifacts_materialized": len(list(artifact_dir.iterdir())),
    }
    write_json(log_dir / "BUILD_SUMMARY.json", summary)
    return summary


def finalize_tests(repo: Path, *, passed: int, failed: int, command: str, output: str) -> dict[str, Any]:
    repo = repo.resolve()
    artifact_dir = repo / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
    report = {
        "artifact_id": "V35R3B_TEST_REPORT_V1",
        "status": "PASS" if failed == 0 else "FAIL",
        "passed": int(passed),
        "failed": int(failed),
        "command": command,
        "output": output,
        "tested_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    write_json(artifact_dir / "V35R3B_TEST_REPORT.json", report)

    isolation_path = artifact_dir / "V35R3B_ISOLATION_AUDIT.json"
    isolation = json.loads(isolation_path.read_text(encoding="utf-8"))
    active_end = _status(ACTIVE_V35R3_WORKTREE)
    active_head_end = _git(ACTIVE_V35R3_WORKTREE, "rev-parse", "HEAD")
    parent_end = _status(PARENT_WORKTREE)
    parent_head_end = _git(PARENT_WORKTREE, "rev-parse", "HEAD")
    _, authority_end = inventory_authority(AUTHORITY_ROOT)
    isolation.update(
        {
            "active_V35R3_status_at_end": active_end,
            "active_V35R3_HEAD_at_end": active_head_end,
            "V35R3A_parent_status_at_end": parent_end,
            "V35R3A_parent_HEAD_at_end": parent_head_end,
            "active_status_unchanged": active_end == isolation["active_V35R3_status_at_start"] and active_head_end == isolation["active_V35R3_HEAD_at_start"],
            "active_status_changed_by_external_process": active_end != isolation["active_V35R3_status_at_start"] or active_head_end != isolation["active_V35R3_HEAD_at_start"],
            "V35R3A_parent_status_unchanged": parent_end == isolation["V35R3A_parent_status_at_start"] and parent_head_end == isolation["V35R3A_parent_HEAD_at_start"],
            "authority_content_fingerprint_at_end": authority_end["content_fingerprint_sha256"],
            "authority_content_unchanged": authority_end["content_fingerprint_sha256"] == isolation["authority_content_fingerprint_at_start"],
            "active_V35R3_files_changed_by_this_task": 0,
            "V35R3A_parent_worktree_files_changed_by_this_task": 0,
            "downloaded_authority_files_changed_by_this_task": 0,
        }
    )
    vendor_end = {
        "RADDiT": git_repository_state(RADDIT_ROOT),
        "FastSim": git_repository_state(FASTSIM_ROOT),
        "NLR_HPC_docs": git_repository_state(NLR_DOCS_ROOT),
        "Eagle_jobs_reference": git_repository_state(EAGLE_ROOT),
    }
    isolation["vendor_repository_states_at_end"] = vendor_end
    start = json.loads((artifact_dir / "V35R3B_START_STATE.json").read_text(encoding="utf-8"))
    isolation["vendor_statuses_unchanged"] = all(
        vendor_end[name]["status"] == start["vendor_repository_states_at_start"][name]["status"]
        and vendor_end[name]["HEAD"] == start["vendor_repository_states_at_start"][name]["HEAD"]
        for name in vendor_end
    )
    write_json(isolation_path, isolation)

    review_path = artifact_dir / "V35R3B_FINAL_REVIEW.json"
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["numbered_report"]["67"]["value"] = report
    write_json(review_path, review)
    _write_review_markdown(artifact_dir / "V35R3B_FINAL_REVIEW.md", review)
    return report
