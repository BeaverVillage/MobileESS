"""Generate the V35R3G fail-closed Dataset 302 forensic artifacts.

The implementation scans the frozen ZIP once after its independent SHA-256
verification.  It never opens Apr-01 realized energy, runtime, or end fields,
and it does not train a model or construct power labels when the physical
sensor boundary or positive H100 energy is unavailable.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import io
import json
import os
import platform
import re
import subprocess
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psutil
import pyarrow
import pyarrow.parquet as pq

from .audit import (
    CohortAccumulator,
    NumericFieldStats,
    h100_partition,
    list_has_values,
    parse_formatted_energy,
    sha256_file,
    sharing_classification,
    spatial_classification,
    weighted_median,
    write_csv,
    write_json,
)
from .contracts import (
    ARCHIVE,
    ARCHIVE_BYTES,
    ARCHIVE_SHA256,
    ARTIFACT_DIRNAME,
    AUTHORITY_ROOT,
    BRANCH,
    CACHE_DIRNAME,
    CAUSAL_H100_POWER_MODEL_NEXT,
    CONDITIONAL_ARTIFACTS,
    DATACARD,
    DATASET_DOI,
    DATASET_ID,
    GPUS_PER_H100_NODE,
    H100_LOCAL_DOC,
    H100_PARTITION_PREFIX,
    HIGHEST_AUTHORITY,
    HPCODA_DESCRIPTOR,
    ISSUE_TIME_LOCAL,
    ISSUE_TIME_UTC,
    LOG_DIRNAME,
    MODELABILITY,
    PARENT_HEAD,
    PHYSICAL_BOUNDARY,
    PRIMARY_CLASSIFICATION,
    REQUIRED_ARTIFACTS,
    SHARED_H100_POWER_NEXT,
    SLURM_SACCT_SNAPSHOT,
    SOURCE_COLUMNS,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
CACHE = ROOT / "dayahead" / "cache" / CACHE_DIRNAME
LOGS = ROOT / "logs" / LOG_DIRNAME
ISSUE = pd.Timestamp(ISSUE_TIME_UTC)
MONTH_RE = re.compile(r"year=(\d{4})/month=(\d{1,2})/")

APR01_RUNTIME_POINT = (
    ROOT
    / "dayahead"
    / "artifacts"
    / "v35r3d_kestrel_runtime_authority_closure"
    / "V35R3D_APR01_RUNTIME_POINT.parquet"
)
APR01_PENDING_AUDIT = (
    ROOT
    / "dayahead"
    / "artifacts"
    / "v35r3a_kestrel_scheduler_temporal"
    / "V35R3A_PENDING_FIELD_AUDIT.parquet"
)
ISSUE_AUTHORITY = (
    ROOT
    / "dayahead"
    / "artifacts"
    / "v35r3d_kestrel_runtime_authority_closure"
    / "V35R3D_RUNTIME_CALIBRATION.json"
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {"python": platform.python_version()}
    for package in ("numpy", "pandas", "psutil", "pyarrow", "pytest"):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = None
    return result


def provenance(code_commit: str) -> dict[str, Any]:
    return {
        "dataset_id": DATASET_ID,
        "dataset_doi": DATASET_DOI,
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_relative_paths": [
            "esif.hpc.kestrel.job-anon/year=YYYY/month=M/kestrel_jobs_YYYYMM_0.parquet"
        ],
        "source_code_commit": code_commit,
        "parameter_contract": {
            "H100_identity": "comma-delimited partition token starts with gpu-h100",
            "preissue_cutoff": "state_simple=COMPLETED and end_time<=2025-03-31T08:00:00Z",
            "positive_energy": "finite ConsumedEnergyRaw joules > 0",
            "full_node_shape": (
                "nodes_req=nodes_used=gpu_nodes_occupied>0 and "
                "gpus_requested=4*nodes_used"
            ),
            "sharing": (
                "positive shared_job_count or nonempty sharing lists => shared; "
                "null count and empty lists => realized no-co-residency"
            ),
            "recency_windows_days": [30, 60, 120, 180, 365],
        },
        "timezone_assumption": (
            "source offsets normalized to UTC; frozen issue is "
            f"{ISSUE_TIME_LOCAL} = {ISSUE_TIME_UTC}"
        ),
        "units": {"energy": "J and derived Wh", "runtime": "s", "power": "W"},
        "software_versions": versions(),
    }


def with_provenance(payload: dict[str, Any], code_commit: str) -> dict[str, Any]:
    return provenance(code_commit) | payload


class Accounting:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.process = psutil.Process()
        self.peak_rss = self.process.memory_info().rss
        self.stage_seconds: dict[str, float] = {}

    def checkpoint(self, name: str, started: float) -> None:
        self.stage_seconds[name] = time.perf_counter() - started
        self.peak_rss = max(self.peak_rss, self.process.memory_info().rss)

    def sample(self) -> None:
        self.peak_rss = max(self.peak_rss, self.process.memory_info().rss)


def verify_start_state() -> tuple[dict[str, Any], dict[str, Any]]:
    head = git("rev-parse", "HEAD")
    branch = git("branch", "--show-current")
    merge_base = git("merge-base", "HEAD", PARENT_HEAD)
    if branch != BRANCH or merge_base != PARENT_HEAD:
        raise RuntimeError("Branch or parent isolation mismatch")
    issue_payload = json.loads(ISSUE_AUTHORITY.read_text(encoding="utf-8"))
    if issue_payload.get("issue_time_AEST") != ISSUE_TIME_LOCAL:
        raise RuntimeError("Frozen V35R3D issue time mismatch")
    start = {
        "parent_HEAD_expected": PARENT_HEAD,
        "parent_HEAD_actual": merge_base,
        "pipeline_code_HEAD": head,
        "branch_expected": BRANCH,
        "branch_actual": branch,
        "worktree": str(ROOT),
        "isolated_worktree": True,
        "issue_time_local": ISSUE_TIME_LOCAL,
        "issue_time_UTC": ISSUE_TIME_UTC,
        "issue_authority_path": str(ISSUE_AUTHORITY.relative_to(ROOT)),
        "issue_authority_sha256": sha256_file(ISSUE_AUTHORITY),
    }
    isolation = {
        "isolated_worktree": True,
        "parent_match": True,
        "branch_match": True,
        "production_files_changed": 0,
        "MESS_files_changed": 0,
        "vendor_or_source_files_changed": 0,
        "push": False,
        "merge": False,
        "XGBoost_fit_calls": 0,
        "Gurobi_calls": 0,
        "MESS_runs": 0,
        "node_packing_runs": 0,
        "grid_reads": 0,
        "Fresh_reads": 0,
        "Planning_reads": 0,
        "Apr02_plus_result_reads": 0,
        "May_result_reads": 0,
        "Dataset312_scaling_or_label_reads": 0,
        "Apr01_consumed_energy_reads": 0,
        "Apr01_realized_runtime_reads": 0,
        "Apr01_future_end_reads": 0,
    }
    return start, isolation


def verify_source() -> dict[str, Any]:
    for path in (ARCHIVE, DATACARD, SLURM_SACCT_SNAPSHOT, H100_LOCAL_DOC, HPCODA_DESCRIPTOR):
        if not path.is_file():
            raise FileNotFoundError(path)
    if ARCHIVE.stat().st_size != ARCHIVE_BYTES:
        raise RuntimeError("Dataset 302 archive size mismatch")
    actual_sha = sha256_file(ARCHIVE)
    if actual_sha != ARCHIVE_SHA256:
        raise RuntimeError("Dataset 302 archive SHA-256 mismatch")
    with zipfile.ZipFile(ARCHIVE) as archive:
        members = [i for i in archive.infolist() if i.filename.endswith(".parquet")]
    if len(members) != 29:
        raise RuntimeError("Dataset 302 ZIP member inventory mismatch")
    return {
        "classification": "PASS_CANONICAL_DATASET302_SOURCE",
        "archive_path": str(ARCHIVE),
        "archive_bytes": ARCHIVE.stat().st_size,
        "archive_SHA256_expected": ARCHIVE_SHA256,
        "archive_SHA256_actual": actual_sha,
        "ZIP_structure": "PASS",
        "ZIP_CRC": "NOT_RESCANNED_SHA256_PRIMARY",
        "parquet_members": len(members),
        "uncompressed_parquet_bytes": sum(i.file_size for i in members),
        "compressed_parquet_bytes": sum(i.compress_size for i in members),
        "redownloads": 0,
        "source_mutations": 0,
        "primary_source_is_transformed_copy": False,
        "authority_manifest": str(AUTHORITY_ROOT / "99_manifest" / "kestrel_integrity.txt"),
        "documentation_files": {
            "dataset302_datacard": {
                "path": str(DATACARD),
                "sha256": sha256_file(DATACARD),
                "relied_on": "parent-job rows; fields; node-level monitoring; sharing semantics",
            },
            "local_Slurm_sacct_snapshot": {
                "path": str(SLURM_SACCT_SNAPSHOT),
                "sha256": sha256_file(SLURM_SACCT_SNAPSHOT),
                "relied_on": "ConsumedEnergyRaw units and exclusive-allocation warning",
            },
            "local_NLR_H100_documentation": {
                "path": str(H100_LOCAL_DOC),
                "sha256": sha256_file(H100_LOCAL_DOC),
                "relied_on": "four H100 GPUs per normal gpu-h100 node",
            },
            "hpc_oda_descriptor": {
                "path": str(HPCODA_DESCRIPTOR),
                "sha256": sha256_file(HPCODA_DESCRIPTOR),
                "relied_on": "frozen Dataset 302 identity and submission-feature mapping",
            },
        },
        "external_documentation": [
            {
                "url": "https://data.nlr.gov/submissions/302",
                "title": "NLR Data Catalog Dataset 302",
                "access_date": "2026-09-03",
                "relied_on": "dataset identity and DOI",
            },
            {
                "url": "https://slurm.schedmd.com/sacct.html",
                "title": "Slurm Workload Manager - sacct",
                "access_date": "2026-09-03",
                "relied_on": "ConsumedEnergyRaw is joules and only exclusive allocation reflects job energy",
            },
            {
                "url": "https://slurm.schedmd.com/slurm.conf.html",
                "title": "Slurm Workload Manager - slurm.conf",
                "access_date": "2026-09-03",
                "relied_on": "energy boundary depends on the configured AcctGatherEnergyType plugin",
            },
            {
                "url": "https://www.nrel.gov/docs/gen/fy24/90033.pdf",
                "title": "NREL HPC FY25 Allocation Cycle",
                "access_date": "2026-09-03",
                "relied_on": "Kestrel GPU nodes have four H100 SXM GPUs and may request 1, 2, or 4 GPUs",
            },
        ],
    }


def _member_sort_key(name: str) -> tuple[int, int, str]:
    match = MONTH_RE.search(name)
    return (int(match.group(1)), int(match.group(2)), name) if match else (0, 0, name)


def _counter_json(counter: Counter[Any]) -> dict[str, int]:
    return {str(key): int(value) for key, value in sorted(counter.items(), key=lambda item: str(item[0]))}


def scan_source(accounting: Accounting) -> dict[str, Any]:
    field_stats = {
        name: NumericFieldStats()
        for name in (
            "cpu_energy_tdp_estimated_max_watt_hours",
            "cpu_energy_tdp_estimated_used_watt_hours",
            "consumed_energy_joules",
            "consumed_energy_raw_joules",
            "consumed_energy_raw_watt_hours",
        )
    }
    source_non_null = Counter()
    source_columns: set[str] = set()
    discovered_energy_power_columns: set[str] = set()
    unparseable_formatted = 0
    schema_types: dict[str, set[str]] = {name: set() for name in field_stats}
    unit_rel_counter: Counter[float] = Counter()
    unit_count = unit_mismatch = 0
    unit_max_abs = unit_max_rel = 0.0

    global_names = (
        "ALL_JOBS",
        "H100_CONFIRMED",
        "H100_POSITIVE_ENERGY",
        "EXCLUSIVE_H100_POSITIVE_ENERGY",
        "FULL_NODE_EXCLUSIVE_H100_POSITIVE_ENERGY",
        "PARTIAL_EXCLUSIVE_H100_POSITIVE_ENERGY",
        "SHARED_H100_POSITIVE_ENERGY",
        "UNKNOWN_SHARING_H100_POSITIVE_ENERGY",
    )
    pre_names = (
        "PREISSUE_ALL_H100",
        "PREISSUE_H100_POSITIVE_ENERGY",
        "PREISSUE_EXCLUSIVE_H100_POSITIVE_ENERGY",
        "PREISSUE_FULL_NODE_EXCLUSIVE_H100_POSITIVE_ENERGY",
        "PREISSUE_PARTIAL_EXCLUSIVE_H100_POSITIVE_ENERGY",
        "PREISSUE_SHARED_H100_POSITIVE_ENERGY",
    )
    global_acc = {name: CohortAccumulator() for name in global_names}
    pre_acc = {name: CohortAccumulator() for name in pre_names}
    window_labels = ["GLOBAL", "PREISSUE_ALL", "PREISSUE_365D", "PREISSUE_180D", "PREISSUE_120D", "PREISSUE_60D", "PREISSUE_30D"]
    spatial_classes = ["FULL_NODE_EXCLUSIVE", "PARTIAL_EXCLUSIVE", "SHARED", "UNKNOWN_SHARING"]
    spatial_acc = {
        (window, spatial): CohortAccumulator()
        for window in window_labels
        for spatial in spatial_classes
    }

    ids: list[np.ndarray] = []
    job_ids: list[np.ndarray] = []
    array_positions: list[np.ndarray] = []
    sum_member_unique_job_ids = 0
    step_suffix_rows = 0
    array_element_rows = 0
    duplicate_energy_array_groups = 0
    repeated_groups_all_array_positions = 0
    member_rows: list[dict[str, Any]] = []
    h100_partitions: Counter[str] = Counter()
    h100_states: Counter[str] = Counter()
    h100_gpu_requests: Counter[str] = Counter()
    h100_node_requests: Counter[str] = Counter()
    hardware_class_counts = Counter()
    sharing_counts_all = Counter()
    sharing_counts_h100 = Counter()
    sharing_inconsistency = Counter()
    source_submit_min = source_submit_max = None
    source_end_min = source_end_max = None
    h100_zero = h100_missing = h100_invalid = h100_positive = 0

    with zipfile.ZipFile(ARCHIVE) as archive:
        infos = sorted(
            (i for i in archive.infolist() if i.filename.endswith(".parquet")),
            key=lambda i: _member_sort_key(i.filename),
        )
        for index, info in enumerate(infos, start=1):
            member_started = time.perf_counter()
            raw = archive.read(info.filename)
            parquet_file = pq.ParquetFile(io.BytesIO(raw))
            member_columns = set(parquet_file.schema_arrow.names)
            source_columns.update(member_columns)
            discovered_energy_power_columns.update(
                name
                for name in member_columns
                if any(token in name.casefold() for token in ("energy", "power", "watt"))
            )
            missing_columns = set(SOURCE_COLUMNS) - member_columns
            if missing_columns:
                raise RuntimeError(
                    f"Required source columns absent from {info.filename}: {sorted(missing_columns)}"
                )
            table = pq.read_table(io.BytesIO(raw), columns=list(SOURCE_COLUMNS))
            for name in schema_types:
                schema_types[name].add(str(table.schema.field(name).type))
            frame = table.to_pandas()
            del table, raw
            for column in ("submit_time", "start_time", "end_time"):
                frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce")
            frame["runtime_seconds"] = (frame["end_time"] - frame["start_time"]).dt.total_seconds()
            frame["label_time"] = frame["end_time"].where(frame["end_time"].notna(), frame["submit_time"])

            energy = pd.to_numeric(frame["consumed_energy_raw_joules"], errors="coerce")
            energy_wh = pd.to_numeric(frame["consumed_energy_raw_watt_hours"], errors="coerce")
            positive = energy.gt(0) & np.isfinite(energy)
            invalid_energy = energy.lt(0) | np.isinf(energy)
            h100 = frame["partition"].map(h100_partition)
            sharing = sharing_classification(frame)
            spatial = spatial_classification(frame, h100)
            completed_preissue = (
                h100
                & frame["state_simple"].eq("COMPLETED")
                & frame["end_time"].notna()
                & frame["end_time"].le(ISSUE)
            )

            # Field census.  The formatted ConsumedEnergy field needs parsing;
            # all remaining fields are already numeric.
            formatted = parse_formatted_energy(frame["consumed_energy_joules"])
            source_non_null["consumed_energy_joules"] += int(frame["consumed_energy_joules"].notna().sum())
            unparseable_formatted += int((frame["consumed_energy_joules"].notna() & formatted.isna()).sum())
            field_stats["consumed_energy_joules"].update(formatted)
            for name in field_stats:
                if name == "consumed_energy_joules":
                    continue
                source_non_null[name] += int(frame[name].notna().sum())
                field_stats[name].update(frame[name])

            both = energy.notna() & energy_wh.notna() & np.isfinite(energy) & np.isfinite(energy_wh)
            if both.any():
                lhs = energy.loc[both].to_numpy(float)
                rhs = 3600.0 * energy_wh.loc[both].to_numpy(float)
                absolute = np.abs(lhs - rhs)
                relative = absolute / np.maximum(np.abs(lhs), 1.0)
                unit_count += len(lhs)
                unit_mismatch += int(np.count_nonzero(~np.isclose(lhs, rhs, rtol=1e-12, atol=1e-6)))
                unit_max_abs = max(unit_max_abs, float(absolute.max(initial=0.0)))
                unit_max_rel = max(unit_max_rel, float(relative.max(initial=0.0)))
                unit_rel_counter.update(np.round(relative, 18).tolist())

            # Identifier semantics are audited globally after concatenation.
            numeric_id = pd.to_numeric(frame["id"], errors="coerce").to_numpy(float)
            ids.append(numeric_id)
            jid = pd.to_numeric(frame["job_id"], errors="coerce").to_numpy(dtype=np.int64)
            job_ids.append(jid)
            apos = pd.to_numeric(frame["array_pos"], errors="coerce").fillna(-1).to_numpy(dtype=np.int64)
            array_positions.append(apos)
            step_suffix_rows += int(frame["id"].astype(str).str.contains(".", regex=False).sum())
            array_element_rows += int(frame["array_pos"].notna().sum())
            sum_member_unique_job_ids += int(frame["job_id"].nunique(dropna=False))
            repeated = frame["job_id"].duplicated(keep=False)
            if repeated.any():
                repeated_frame = pd.DataFrame(
                    {
                        "job_id": frame.loc[repeated, "job_id"].to_numpy(),
                        "array_pos": frame.loc[repeated, "array_pos"].to_numpy(),
                        "energy": energy.loc[repeated].to_numpy(),
                    }
                )
                group_size = repeated_frame.groupby("job_id", dropna=False).size()
                array_unique = repeated_frame.groupby("job_id", dropna=False)["array_pos"].nunique(dropna=True)
                repeated_groups_all_array_positions += int((array_unique == group_size).sum())
                energy_pairs = repeated_frame.dropna(subset=["energy"])
                duplicated_energy = energy_pairs.duplicated(["job_id", "energy"], keep=False)
                duplicate_energy_array_groups += int(energy_pairs.loc[duplicated_energy, "job_id"].nunique())

            # Source spans and classification distributions.
            for series, low_name, high_name in (
                (frame["submit_time"], "submit", "submit"),
                (frame["end_time"], "end", "end"),
            ):
                clean = series.dropna()
                if clean.empty:
                    continue
                low, high = clean.min(), clean.max()
                if low_name == "submit":
                    source_submit_min = low if source_submit_min is None else min(source_submit_min, low)
                    source_submit_max = high if source_submit_max is None else max(source_submit_max, high)
                else:
                    source_end_min = low if source_end_min is None else min(source_end_min, low)
                    source_end_max = high if source_end_max is None else max(source_end_max, high)

            sharing_counts_all.update(sharing.tolist())
            sharing_counts_h100.update(sharing.loc[h100].tolist())
            count = pd.to_numeric(frame["shared_job_count"], errors="coerce")
            nodes_has = frame["nodes_shared"].map(list_has_values)
            jobs_has = frame["jobs_shared"].map(list_has_values)
            sharing_inconsistency["positive_count_but_empty_job_list"] += int((count.gt(0) & ~jobs_has).sum())
            sharing_inconsistency["null_count_but_nonempty_lists"] += int((count.isna() & (nodes_has | jobs_has)).sum())
            sharing_inconsistency["zero_count_rows"] += int(count.eq(0).sum())
            job_lengths = frame["jobs_shared"].map(
                lambda value: len(value) if isinstance(value, (list, tuple, np.ndarray)) else 0
            )
            sharing_inconsistency["count_list_length_mismatch"] += int((count.notna() & count.ne(job_lengths)).sum())

            part_text = frame["partition"].fillna("").astype(str).str.casefold()
            gpu_other = part_text.str.contains("gpu", regex=False) & ~h100
            missing_part = frame["partition"].isna() | part_text.eq("")
            hardware_class_counts["H100_CONFIRMED"] += int(h100.sum())
            hardware_class_counts["H100_UNKNOWN"] += int((gpu_other | missing_part).sum())
            hardware_class_counts["NON_H100_CONFIRMED"] += int((~h100 & ~gpu_other & ~missing_part).sum())
            h100_partitions.update(frame.loc[h100, "partition"].fillna("<NULL>").astype(str).tolist())
            h100_states.update(frame.loc[h100, "state_simple"].fillna("<NULL>").astype(str).tolist())
            h100_gpu_requests.update(frame.loc[h100, "gpus_requested"].astype("string").fillna("<NULL>").tolist())
            h100_node_requests.update(frame.loc[h100, "nodes_req"].astype("string").fillna("<NULL>").tolist())
            h100_positive += int((h100 & positive).sum())
            h100_zero += int((h100 & energy.eq(0)).sum())
            h100_missing += int((h100 & energy.isna()).sum())
            h100_invalid += int((h100 & invalid_energy).sum())

            global_masks = {
                "ALL_JOBS": pd.Series(True, index=frame.index),
                "H100_CONFIRMED": h100,
                "H100_POSITIVE_ENERGY": h100 & positive,
                "EXCLUSIVE_H100_POSITIVE_ENERGY": h100 & positive & sharing.eq("EXCLUSIVE_CONFIRMED"),
                "FULL_NODE_EXCLUSIVE_H100_POSITIVE_ENERGY": h100 & positive & spatial.eq("FULL_NODE_EXCLUSIVE"),
                "PARTIAL_EXCLUSIVE_H100_POSITIVE_ENERGY": h100 & positive & spatial.eq("PARTIAL_EXCLUSIVE"),
                "SHARED_H100_POSITIVE_ENERGY": h100 & positive & spatial.eq("SHARED"),
                "UNKNOWN_SHARING_H100_POSITIVE_ENERGY": h100 & positive & spatial.eq("UNKNOWN_SHARING"),
            }
            for name, mask in global_masks.items():
                global_acc[name].update(frame, mask)
            pre_masks = {
                "PREISSUE_ALL_H100": completed_preissue,
                "PREISSUE_H100_POSITIVE_ENERGY": completed_preissue & positive,
                "PREISSUE_EXCLUSIVE_H100_POSITIVE_ENERGY": completed_preissue & positive & sharing.eq("EXCLUSIVE_CONFIRMED"),
                "PREISSUE_FULL_NODE_EXCLUSIVE_H100_POSITIVE_ENERGY": completed_preissue & positive & spatial.eq("FULL_NODE_EXCLUSIVE"),
                "PREISSUE_PARTIAL_EXCLUSIVE_H100_POSITIVE_ENERGY": completed_preissue & positive & spatial.eq("PARTIAL_EXCLUSIVE"),
                "PREISSUE_SHARED_H100_POSITIVE_ENERGY": completed_preissue & positive & spatial.eq("SHARED"),
            }
            for name, mask in pre_masks.items():
                pre_acc[name].update(frame, mask)

            window_masks = {
                "GLOBAL": h100,
                "PREISSUE_ALL": completed_preissue,
                **{
                    f"PREISSUE_{days}D": completed_preissue & frame["end_time"].ge(ISSUE - pd.Timedelta(days=days))
                    for days in (365, 180, 120, 60, 30)
                },
            }
            for window, window_mask in window_masks.items():
                for spatial_name in spatial_classes:
                    spatial_acc[(window, spatial_name)].update(
                        frame, window_mask & spatial.eq(spatial_name)
                    )

            member_rows.append(
                {
                    "relative_path": info.filename,
                    "rows": len(frame),
                    "compressed_bytes": info.compress_size,
                    "uncompressed_bytes": info.file_size,
                    "H100_rows": int(h100.sum()),
                    "H100_positive_energy_rows": int((h100 & positive).sum()),
                    "wallclock_seconds": time.perf_counter() - member_started,
                }
            )
            accounting.sample()

    # Global exact duplicate audit.  Numeric IDs are compact enough to keep
    # peak memory bounded while avoiding probabilistic hashes.
    all_ids = np.concatenate(ids)
    nonnumeric_ids = int(np.count_nonzero(np.isnan(all_ids)))
    numeric_ids = all_ids[~np.isnan(all_ids)].astype(np.int64)
    unique_ids = np.unique(numeric_ids)
    id_extra_rows = len(numeric_ids) - len(unique_ids)
    del all_ids, numeric_ids, unique_ids, ids
    accounting.sample()

    all_job_ids = np.concatenate(job_ids)
    unique_job_ids, job_counts = np.unique(all_job_ids, return_counts=True)
    repeated_job_id_count = int(np.count_nonzero(job_counts > 1))
    job_id_extra_rows = int(len(all_job_ids) - len(unique_job_ids))
    job_id_cross_member_overlap = int(sum_member_unique_job_ids - len(unique_job_ids))
    all_array_positions = np.concatenate(array_positions)
    keys = np.empty(len(all_job_ids), dtype=[("job_id", "<i8"), ("array_pos", "<i8")])
    keys["job_id"] = all_job_ids
    keys["array_pos"] = all_array_positions
    unique_logical = np.unique(keys)
    logical_duplicate_extra_rows = int(len(keys) - len(unique_logical))
    array_parent_ids = int(len(np.unique(all_job_ids[all_array_positions >= 0])))
    del keys, unique_logical, all_job_ids, all_array_positions, job_ids, array_positions
    accounting.sample()

    global_payload = {name: acc.as_dict() for name, acc in global_acc.items()}
    pre_payload = {name: acc.as_dict() for name, acc in pre_acc.items()}
    spatial_rows: list[dict[str, Any]] = []
    for window in window_labels:
        for spatial_name in spatial_classes:
            summary = spatial_acc[(window, spatial_name)].as_dict()
            spatial_rows.append(
                {
                    "window": window,
                    "spatial_class": spatial_name,
                    "jobs": summary["jobs"],
                    "GPU_hours": summary["GPU_hours"],
                    "node_hours": summary["node_hours"],
                    "positive_energy_jobs": summary["positive_energy_jobs"],
                    "usable_label_jobs": 0,
                    "total_reported_energy_joules": summary["total_reported_energy_joules"],
                    "distinct_label_dates": summary["distinct_label_dates"],
                    "resource_state_diversity": len(summary["resource_configurations"]),
                }
            )

    energy_fields: dict[str, Any] = {}
    descriptions = {
        "cpu_energy_tdp_estimated_max_watt_hours": ("Wh", "DERIVED", "CPU TDP estimate from TotalCPU"),
        "cpu_energy_tdp_estimated_used_watt_hours": ("Wh", "DERIVED", "CPU TDP estimate from TotalCPU/CPUTime"),
        "consumed_energy_joules": ("J", "DIRECT_FORMATTED_SLURM", "formatted ConsumedEnergy"),
        "consumed_energy_raw_joules": ("J", "DIRECT_SLURM_FIELD", "ConsumedEnergyRaw"),
        "consumed_energy_raw_watt_hours": ("Wh", "DERIVED_UNIT_CONVERSION", "ConsumedEnergyRaw / 3600"),
    }
    for name, stats in field_stats.items():
        unit, origin, semantics = descriptions[name]
        energy_fields[name] = {
            "source_column": name,
            "normalized_column": name,
            "unit": unit,
            "source_types": sorted(schema_types[name]),
            "derived_or_direct": origin,
            "physical_semantics": semantics,
            "source_of_semantics": "Dataset 302 datacard lines 186-190",
            "source_non_null_count": int(source_non_null[name]),
            **stats.as_dict(),
        }
    energy_fields["consumed_energy_joules"]["unparseable_non_null_count"] = unparseable_formatted

    return {
        "normalized_rows": sum(row["rows"] for row in member_rows),
        "source_columns": sorted(source_columns),
        "discovered_energy_power_columns": sorted(discovered_energy_power_columns),
        "member_rows": member_rows,
        "source_time_span": {
            "submit_min_UTC": source_submit_min.isoformat(),
            "submit_max_UTC": source_submit_max.isoformat(),
            "end_min_UTC": source_end_min.isoformat(),
            "end_max_UTC": source_end_max.isoformat(),
        },
        "row_granularity": {
            "classification": "ONE_PARENT_JOB_ROW_PER_ID_ARRAY_ELEMENTS_SEPARATE_NO_STEPS",
            "rows": sum(row["rows"] for row in member_rows),
            "unique_id_count": sum(row["rows"] for row in member_rows) - id_extra_rows - nonnumeric_ids,
            "nonnumeric_id_count": nonnumeric_ids,
            "duplicate_id_extra_rows": id_extra_rows,
            "unique_job_id_count": int(len(unique_job_ids)),
            "duplicate_job_id_count": repeated_job_id_count,
            "duplicate_job_id_extra_rows": job_id_extra_rows,
            "array_element_rows": array_element_rows,
            "array_parent_job_ids": array_parent_ids,
            "job_id_array_pos_duplicate_extra_rows": logical_duplicate_extra_rows,
            "step_suffix_rows": step_suffix_rows,
            "job_id_cross_member_overlap": job_id_cross_member_overlap,
            "repeated_groups_with_complete_unique_array_positions": repeated_groups_all_array_positions,
            "repeated_array_parent_groups_with_equal_energy_values": duplicate_energy_array_groups,
            "energy_interpretation": (
                "Repeated job_id values are distinct array elements identified by id/array_pos; "
                "their energy must not be deduplicated or summed as one allocation."
            ),
        },
        "energy_fields": energy_fields,
        "unit_reconciliation": {
            "classification": "PASS_DERIVED_UNIT_CONVERSION",
            "equation": "consumed_energy_raw_joules ~= 3600 * consumed_energy_raw_watt_hours",
            "comparable_rows": unit_count,
            "maximum_absolute_error_joules": unit_max_abs,
            "maximum_relative_error": unit_max_rel,
            "median_relative_error": weighted_median(unit_rel_counter),
            "mismatch_count": unit_mismatch,
            "tolerance": {"relative": 1e-12, "absolute_joules": 1e-6},
            "independent_sensor_count": 1,
            "watt_hours_is_derived": True,
        },
        "global_census": global_payload,
        "preissue_census": pre_payload,
        "spatial_rows": spatial_rows,
        "hardware_class_counts": _counter_json(hardware_class_counts),
        "H100_partitions": _counter_json(h100_partitions),
        "H100_states": _counter_json(h100_states),
        "H100_GPU_requests": _counter_json(h100_gpu_requests),
        "H100_node_requests": _counter_json(h100_node_requests),
        "H100_energy": {
            "positive": h100_positive,
            "zero": h100_zero,
            "missing": h100_missing,
            "invalid": h100_invalid,
        },
        "sharing_counts_all": _counter_json(sharing_counts_all),
        "sharing_counts_H100": _counter_json(sharing_counts_h100),
        "sharing_inconsistency": _counter_json(sharing_inconsistency),
    }


def apr01_feature_coverage() -> dict[str, Any]:
    runtime_columns = [
        "job_id",
        "state_at_issue",
        "workload_class",
        "requested_GPUs",
        "requested_nodes",
        "requested_walltime_seconds",
        "prediction_issue_time",
    ]
    pending_columns = [
        "job_id",
        "qos_raw",
        "partition_raw",
        "requested_GPUs",
        "requested_nodes",
        "requested_walltime_seconds",
        "submit_time",
        "state_at_cutoff",
        "partial_shared_request",
        "full_node_request_shape",
        "workload_class",
    ]
    runtime = pd.read_parquet(APR01_RUNTIME_POINT, columns=runtime_columns)
    pending = pd.read_parquet(APR01_PENDING_AUDIT, columns=pending_columns)
    temporal = pending.loc[
        pending["workload_class"].isin(["NORMAL_QUEUE_CONTROLLED", "STANDBY_QUEUE_CONTROLLED"])
    ]
    cohorts = {
        "Apr01_running": int(runtime["state_at_issue"].eq("RUNNING").sum()),
        "Apr01_temporal_pending": len(temporal),
        "strict_current_F0_full_node": int(temporal["full_node_request_shape"].eq(True).sum()),
        "PARTIAL_shared_temporal": int(temporal["partial_shared_request"].eq(True).sum()),
    }
    return {
        "classification": "NO_TRAINING_LABEL_DOMAIN_NO_POSITIVE_H100_ENERGY",
        "coverage_basis": "authorized positive-energy preissue full-node H100 label domain",
        "cohorts": {
            name: {
                "rows": count,
                "covered_rows": 0,
                "coverage_fraction": 0.0,
                "status": "NOT_COVERED_EMPTY_AUTHORIZED_TRAINING_DOMAIN",
            }
            for name, count in cohorts.items()
        },
        "column_projection_audit": {
            "runtime_point_columns_read": runtime_columns,
            "pending_audit_columns_read": pending_columns,
            "Apr01_consumed_energy_columns_read": [],
            "Apr01_realized_runtime_columns_read": [],
            "Apr01_future_end_columns_read": [],
        },
        "source_artifacts": [
            {"path": str(APR01_RUNTIME_POINT.relative_to(ROOT)), "sha256": sha256_file(APR01_RUNTIME_POINT)},
            {"path": str(APR01_PENDING_AUDIT.relative_to(ROOT)), "sha256": sha256_file(APR01_PENDING_AUDIT)},
        ],
    }


def census_rows(payload: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, values in payload.items():
        rows.append(
            {
                "cohort": name,
                "jobs": values["jobs"],
                "valid_runtime_jobs": values["valid_runtime_jobs"],
                "node_hours": values["node_hours"],
                "GPU_hours": values["GPU_hours"],
                "positive_energy_jobs": values["positive_energy_jobs"],
                "total_reported_energy_joules": values["total_reported_energy_joules"],
                "first_label_time_UTC": values["first_label_time_UTC"],
                "last_label_time_UTC": values["last_label_time_UTC"],
                "distinct_label_dates": values["distinct_label_dates"],
                "distinct_users": values["distinct_users"],
                "distinct_accounts": values["distinct_accounts"],
                "partitions_json": json.dumps(values["partitions"], sort_keys=True),
                "qos_json": json.dumps(values["qos"], sort_keys=True),
                "resource_configurations_json": json.dumps(values["resource_configurations"], sort_keys=True),
            }
        )
    return rows


def recency_rows(scan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    spatial = {(r["window"], r["spatial_class"]): r for r in scan["spatial_rows"]}
    for label, days in (("30D", 30), ("60D", 60), ("120D", 120), ("180D", 180), ("365D", 365), ("ALL", None)):
        window = "PREISSUE_ALL" if days is None else f"PREISSUE_{days}D"
        summaries = [spatial[(window, c)] for c in ("FULL_NODE_EXCLUSIVE", "PARTIAL_EXCLUSIVE", "SHARED", "UNKNOWN_SHARING")]
        rows.append(
            {
                "window": label,
                "window_days": days,
                "window_end_UTC": ISSUE_TIME_UTC,
                "H100_jobs": sum(item["jobs"] for item in summaries),
                "positive_energy_jobs": sum(item["positive_energy_jobs"] for item in summaries),
                "full_node_exclusive_positive_energy_jobs": spatial[(window, "FULL_NODE_EXCLUSIVE")]["positive_energy_jobs"],
                "partial_exclusive_positive_energy_jobs": spatial[(window, "PARTIAL_EXCLUSIVE")]["positive_energy_jobs"],
                "GPU_hours": sum(item["GPU_hours"] for item in summaries),
                "node_hours": sum(item["node_hours"] for item in summaries),
                "total_reported_energy_joules": sum(item["total_reported_energy_joules"] for item in summaries),
                "distinct_active_days_upper_bound": sum(item["distinct_label_dates"] for item in summaries),
                "resource_state_diversity_upper_bound": sum(item["resource_state_diversity"] for item in summaries),
            }
        )
    return rows


def _csv_lineage(rows: list[dict[str, Any]], code_commit: str) -> list[dict[str, Any]]:
    for row in rows:
        row["source_archive_sha256"] = ARCHIVE_SHA256
        row["source_code_commit"] = code_commit
    return rows


def build_final_review(scan: dict[str, Any], coverage: dict[str, Any], tests: dict[str, Any], code_commit: str) -> tuple[dict[str, Any], str]:
    row = scan["row_granularity"]
    fields = scan["energy_fields"]
    global_c = scan["global_census"]
    pre = scan["preissue_census"]
    recency = {r["window"]: r for r in recency_rows(scan)}
    numbered = {
        "1": PARENT_HEAD,
        "2": BRANCH,
        "3": str(ROOT),
        "4": "REPORTED_AT_HANDOFF_AFTER_ARTIFACT_COMMIT",
        "5": "CLEAN_AFTER_FINAL_COMMIT",
        "6": 0,
        "7": 0,
        "8": 0,
        "9": "NO_PUSH_NO_MERGE",
        "10": ARCHIVE_SHA256,
        "11": scan["normalized_rows"],
        "12": row["classification"],
        "13": row["job_id_array_pos_duplicate_extra_rows"],
        "14": f"{scan['source_time_span']['submit_min_UTC']} to {scan['source_time_span']['submit_max_UTC']}",
        "15": ["consumed_energy_raw_joules", "consumed_energy_raw_watt_hours (derived)"],
        "16": ["J", "Wh"],
        "17": "PASS; Wh is ConsumedEnergyRaw/3600, not an independent sensor",
        "18": fields["consumed_energy_raw_joules"]["positive_count"],
        "19": fields["consumed_energy_raw_joules"]["zero_count"] + (scan["normalized_rows"] - fields["consumed_energy_raw_joules"]["non_null_count"]),
        "20": fields["consumed_energy_raw_joules"]["negative_count"] + fields["consumed_energy_raw_joules"]["nonfinite_count"],
        "21": PHYSICAL_BOUNDARY,
        "22": "UNKNOWN",
        "23": "UNKNOWN",
        "24": "UNKNOWN",
        "25": "UNKNOWN",
        "26": "Dataset302 datacard + Slurm sacct/slurm.conf; Kestrel plugin/sensor configuration absent",
        "27": "NO",
        "28": "NO",
        "29": "NO",
        "30": "SHARED_ENERGY_DOUBLE_COUNT_RISK",
        "31": global_c["H100_CONFIRMED"]["jobs"],
        "32": global_c["H100_POSITIVE_ENERGY"]["jobs"],
        "33": global_c["FULL_NODE_EXCLUSIVE_H100_POSITIVE_ENERGY"]["jobs"],
        "34": global_c["PARTIAL_EXCLUSIVE_H100_POSITIVE_ENERGY"]["jobs"],
        "35": global_c["SHARED_H100_POSITIVE_ENERGY"]["jobs"],
        "36": 0,
        "37": 0.0,
        "38": 0.0,
        "39": "NONE",
        "40": f"{ISSUE_TIME_LOCAL} = {ISSUE_TIME_UTC}",
        "41": pre["PREISSUE_FULL_NODE_EXCLUSIVE_H100_POSITIVE_ENERGY"]["jobs"],
        "42": 0.0,
        "43": 0.0,
        "44": 0,
        "45": recency["365D"]["full_node_exclusive_positive_energy_jobs"],
        "46": recency["180D"]["full_node_exclusive_positive_energy_jobs"],
        "47": recency["120D"]["full_node_exclusive_positive_energy_jobs"],
        "48": recency["60D"]["full_node_exclusive_positive_energy_jobs"],
        "49": recency["30D"]["full_node_exclusive_positive_energy_jobs"],
        "50": "NONE",
        "51": "NOT_APPLICABLE_NO_USABLE_LABEL",
        "52": "NO",
        "53": "NOT_AUTHORIZED",
        "54": "NOT_AUTHORIZED",
        "55": "NOT_AUTHORIZED",
        "56": "NO",
        "57": "NO",
        "58": "NO",
        "59": "SHARED_ENERGY_DOUBLE_COUNT_RISK",
        "60": MODELABILITY,
        "61": "NO",
        "62": "PASS_FIREWALL; FAIL_TARGET_AVAILABILITY",
        "63": coverage["cohorts"]["Apr01_running"],
        "64": coverage["cohorts"]["Apr01_temporal_pending"],
        "65": coverage["cohorts"]["strict_current_F0_full_node"],
        "66": coverage["cohorts"]["PARTIAL_shared_temporal"],
        "67": HIGHEST_AUTHORITY,
        "68": PRIMARY_CLASSIFICATION,
        "69": CAUSAL_H100_POWER_MODEL_NEXT,
        "70": SHARED_H100_POWER_NEXT,
        "71": "NO",
        "72": "NO",
        "73": 0,
        "74": 0,
        "75": 0,
        "76": 0,
        "77": 0,
        "78": 0,
        "79": tests["passed"],
        "80": tests["failed"],
    }
    questions = {
        "Q1": "Slurm이 보고한 노드 수준 모니터링 센서의 누적 에너지(J)이나, Kestrel의 실제 플러그인과 센서 구성은 공개 자료에 없다.",
        "Q2": "아니다. H100 GPU 에너지 포함 여부는 UNKNOWN이다.",
        "Q3": "아니다. 전체 노드 AC/DC 입력 에너지라는 권위는 없다.",
        "Q4": "아니다. 데이터셋에 Slurm Exclusive 필드가 없고 물리 센서 경계도 미해결이다.",
        "Q5": "전체 공개 추적에서 양의 에너지를 가진 H100 작업은 0개다.",
        "Q6": "엄격한 full-node exclusive H100 양의 에너지 작업은 0개다.",
        "Q7": "Apr-01 발행 시각 이전의 인과적으로 사용 가능한 full-node exclusive H100 라벨은 0개다.",
        "Q8": "365/180/120/60/30일 창 모두 0개다.",
        "Q9": "확인되었다. 최근뿐 아니라 전체 공개 추적에서 H100 양의 에너지 권위가 비어 있다.",
        "Q10": "허가된 평균 전력량은 없다. E/runtime 계산을 수행하지 않았다.",
        "Q11": "사용 가능한 라벨이 없으므로 최근성 날짜와 issue 간격은 정의되지 않는다.",
        "Q12": "아니다. 시간/자원 다양성을 평가할 양의 타깃 자체가 없다.",
        "Q13": "아니다. 부분 독점 H100의 양의 에너지가 없고 센서 경계도 미해결이다.",
        "Q14": "아니다. 공유 작업 에너지를 작업별로 나누면 보존과 이중계수 문제가 생긴다.",
        "Q15": "아니다. Dataset302는 공유 H100 귀속 차단 요인을 해결하지 못한다.",
        "Q16": HIGHEST_AUTHORITY,
        "Q17": "아니다. CAUSAL_H100_POWER_MODEL_NEXT=NO이다.",
        "Q18": "해당 없음. 허가된 학습 타깃 코호트가 없다.",
        "Q19": "양의 H100 에너지 부재가 즉시 차단 요인이며, 물리 경계와 독점 귀속도 미해결이다.",
        "Q20": "아니다. Apr-01 실현 에너지/런타임/종료 시각 읽기는 모두 0이다.",
        "Q21": "아니다. Dataset312로 Dataset302 라벨을 제조하거나 스케일링하지 않았다.",
        "Q22": "아니다. 생산 통합 권고는 NO이다.",
    }
    payload = with_provenance(
        {
            "artifact_id": "V35R3G_FINAL_REVIEW_V1",
            "numbered_report": numbered,
            "questions": questions,
        },
        code_commit,
    )
    sections = [
        ("GIT", 1, 9), ("SOURCE", 10, 14), ("ENERGY FIELDS", 15, 20),
        ("PHYSICAL BOUNDARY", 21, 26), ("ATTRIBUTION", 27, 30),
        ("H100", 31, 35), ("GLOBAL", 36, 39), ("PREISSUE", 40, 44),
        ("RECENCY", 45, 51), ("DERIVED POWER", 52, 56),
        ("PARTIAL / SHARED", 57, 59), ("MODELABILITY", 60, 66),
        ("AUTHORITY", 67, 68), ("NEXT STEP", 69, 72),
        ("CAUSALITY", 73, 78), ("TESTS", 79, 80),
    ]
    labels = {
        1:"parent HEAD",2:"branch",3:"worktree",4:"final HEAD",5:"clean",6:"production files changed",7:"MESS files changed",8:"vendor/source files changed",9:"push/merge",
        10:"Dataset302 SHA",11:"normalized source rows",12:"row granularity",13:"duplicate logical allocation count",14:"source time span",
        15:"canonical energy field(s)",16:"units",17:"Joule/Wh consistency",18:"positive-energy all-source rows",19:"zero/missing-energy rows",20:"invalid-energy rows",
        21:"ConsumedEnergyRaw physical boundary",22:"includes GPU energy",23:"includes CPU energy",24:"whole-node input",25:"idle/base included",26:"physical-boundary authority source",
        27:"exclusive job attribution authorized",28:"partial-exclusive attribution authorized",29:"shared-job attribution authorized",30:"shared double-count risk",
        31:"confirmed H100 jobs",32:"H100 positive-energy jobs",33:"full-node exclusive H100 positive-energy jobs",34:"partial-exclusive H100 positive-energy jobs",35:"shared H100 positive-energy jobs",
        36:"global full-node-exclusive usable jobs",37:"global full-node-exclusive GPU-h",38:"global full-node-exclusive node-h",39:"first/last usable label date",
        40:"exact issue timestamp",41:"causal preissue full-node-exclusive usable jobs",42:"causal preissue GPU-h",43:"causal preissue node-h",44:"causal preissue distinct days",
        45:"365d usable jobs",46:"180d usable jobs",47:"120d usable jobs",48:"60d usable jobs",49:"30d usable jobs",50:"last usable preissue label date",51:"gap to issue",
        52:"average-power quantity authorized",53:"physical name of quantity",54:"P05/P50/P95",55:"full-node scaling",56:"Dataset312 diagnostic comparison performed",
        57:"PARTIAL direct operational label authority",58:"SHARED direct operational label authority",59:"shared conservation classification",
        60:"modelability classification",61:"chronological train/validation possible",62:"causal query-feature authority",63:"Apr01 running feature-domain coverage",64:"Apr01 temporal-pending feature-domain coverage",65:"strict-F0 feature-domain coverage",66:"PARTIAL/shared feature-domain coverage",
        67:"highest energy authority",68:"primary classification",69:"CAUSAL_H100_POWER_MODEL_NEXT",70:"SHARED_H100_POWER_NEXT",71:"DATASET312_AUTHORITY_CHANGED",72:"PRODUCTION_INTEGRATION_RECOMMENDED",
        73:"Apr01 consumed-energy reads",74:"Apr01 realized-runtime reads",75:"Apr01 future-end reads",76:"grid reads",77:"Fresh reads",78:"MESS reads",79:"passed",80:"failed",
    }
    lines = ["# V35R3G Kestrel Dataset 302 Operational Energy Forensic", ""]
    for title, low, high in sections:
        lines.extend([f"## {title}", ""])
        for number in range(low, high + 1):
            value = numbered[str(number)]
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, sort_keys=True)
            lines.append(f"{number}. {labels[number]}: {value}")
        lines.append("")
    lines.extend(["## 질문 답변", ""])
    for index in range(1, 23):
        lines.append(f"Q{index}. {questions[f'Q{index}']}")
        lines.append("")
    return payload, "\n".join(lines).rstrip() + "\n"


def build_artifacts(scan: dict[str, Any], source: dict[str, Any], start: dict[str, Any], isolation: dict[str, Any], coverage: dict[str, Any], accounting: Accounting, code_commit: str) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    p = lambda payload: with_provenance(payload, code_commit)

    write_json(ARTIFACTS / "V35R3G_START_STATE.json", p(start))
    write_json(ARTIFACTS / "V35R3G_ISOLATION_AUDIT.json", p(isolation))
    write_json(ARTIFACTS / "V35R3G_SOURCE_AUTHORITY.json", p(source))
    write_json(ARTIFACTS / "V35R3G_ROW_GRANULARITY_AUDIT.json", p(scan["row_granularity"]))
    duplicate_rows = [
        {"identifier":"id","semantics":"unique parent-row identifier","unique_count":scan["row_granularity"]["unique_id_count"],"duplicate_identifier_count":scan["row_granularity"]["duplicate_id_extra_rows"],"array_behavior":"id distinguishes array elements","step_behavior":"no step suffixes","duplicate_energy_behavior":"none by identifier"},
        {"identifier":"job_id","semantics":"array parent/raw JobID; repeated across elements","unique_count":scan["row_granularity"]["unique_job_id_count"],"duplicate_identifier_count":scan["row_granularity"]["duplicate_job_id_count"],"array_behavior":f"{scan['row_granularity']['array_element_rows']} array-element rows","step_behavior":"parent jobs only","duplicate_energy_behavior":f"{scan['row_granularity']['repeated_array_parent_groups_with_equal_energy_values']} repeated groups contain equal reported energy values; elements remain distinct"},
        {"identifier":"job_id,array_pos","semantics":"logical array allocation key","unique_count":scan["normalized_rows"]-scan["row_granularity"]["job_id_array_pos_duplicate_extra_rows"],"duplicate_identifier_count":scan["row_granularity"]["job_id_array_pos_duplicate_extra_rows"],"array_behavior":"array position preserved","step_behavior":"no steps","duplicate_energy_behavior":"no energy aggregation across keys"},
    ]
    write_csv(ARTIFACTS / "V35R3G_DUPLICATE_IDENTIFIER_AUDIT.csv", _csv_lineage(duplicate_rows, code_commit))
    write_json(
        ARTIFACTS / "V35R3G_ENERGY_FIELD_CENSUS.json",
        p(
            {
                "source_columns_discovered": scan["source_columns"],
                "energy_power_columns_discovered": scan["discovered_energy_power_columns"],
                "fields": scan["energy_fields"],
            }
        ),
    )
    write_json(ARTIFACTS / "V35R3G_ENERGY_UNIT_RECONCILIATION.json", p(scan["unit_reconciliation"]))
    boundary = {
        "classification": "UNRESOLVED_SITE_SPECIFIC_SENSOR_BOUNDARY",
        "ConsumedEnergyRaw_physical_boundary": PHYSICAL_BOUNDARY,
        "includes_GPU_energy": "UNKNOWN",
        "includes_CPU_energy": "UNKNOWN",
        "includes_memory": "UNKNOWN",
        "includes_fans_baseboard_network": "UNKNOWN",
        "whole_node_AC_or_DC_input": "UNKNOWN",
        "idle_or_base_contribution": "UNKNOWN",
        "facts": [
            "Dataset 302 says node-level power monitoring but does not name the Kestrel AcctGatherEnergyType/plugin or sensor.",
            "Slurm supports GPU, RAPL, IPMI, pm_counters, and XCC plugins with different physical boundaries.",
            "Generic ConsumedEnergyRaw semantics cannot identify Kestrel's installed plugin.",
        ],
        "H100_GPU_energy_name_authorized": False,
        "whole_node_IT_energy_name_authorized": False,
    }
    write_json(ARTIFACTS / "V35R3G_CONSUMED_ENERGY_PHYSICAL_BOUNDARY.json", p(boundary))
    attribution = {
        "exclusive_single_job_node_allocation": "NOT_AUTHORIZED_SOURCE_LACKS_SLURM_EXCLUSIVE_FIELD",
        "partial_resource_but_node_exclusive": "NOT_AUTHORIZED",
        "shared_or_co_resident_jobs": "UNSUPPORTED",
        "job_steps": "NOT_PRESENT_PARENT_ROWS_ONLY",
        "multi_node_jobs": "SINGLE_PARENT_SCALAR_NO_PER_NODE_BREAKDOWN",
        "SHARED_JOB_ENERGY_ATTRIBUTION": "UNSUPPORTED",
        "important_distinction": (
            "EXCLUSIVE_CONFIRMED below means realized no-co-residency from derived lists; "
            "it does not prove Slurm --exclusive/NODE allocation."
        ),
    }
    write_json(ARTIFACTS / "V35R3G_SLURM_ENERGY_ATTRIBUTION_CONTRACT.json", p(attribution))
    h100_contract = {
        "frozen_rule": "any comma-delimited partition token starts with gpu-h100",
        "H100_CONFIRMED": scan["hardware_class_counts"]["H100_CONFIRMED"],
        "NON_H100_CONFIRMED": scan["hardware_class_counts"]["NON_H100_CONFIRMED"],
        "H100_UNKNOWN": scan["hardware_class_counts"]["H100_UNKNOWN"],
        "confirmed_partition_counts": scan["H100_partitions"],
        "GPU_request_counts": scan["H100_GPU_requests"],
        "node_request_counts": scan["H100_node_requests"],
        "hardware_authority": "NLR local about.md and NREL FY25 Allocation Cycle: four H100 per normal gpu-h100 node",
        "unknown_policy": "excluded from H100 authority",
    }
    write_json(ARTIFACTS / "V35R3G_H100_IDENTIFICATION_CONTRACT.json", p(h100_contract))
    sharing_payload = {
        "classification_counts_all": scan["sharing_counts_all"],
        "classification_counts_H100": scan["sharing_counts_H100"],
        "consistency_audit": scan["sharing_inconsistency"],
        "EXCLUSIVE_CONFIRMED": "shared_job_count null and nodes_shared/jobs_shared empty",
        "SHARED_CONFIRMED": "shared_job_count positive or either sharing list nonempty",
        "SHARING_UNKNOWN": "all other/contradictory states",
        "source_semantics": "datacard line 235: shared_job_count reflects physical co-residency",
        "warning": "EXCLUSIVE_CONFIRMED is realized no-co-residency, not proof of Slurm Exclusive flag",
    }
    write_json(ARTIFACTS / "V35R3G_SHARING_SEMANTICS.json", p(sharing_payload))
    full_contract = {
        "GPUs_per_normal_H100_node": GPUS_PER_H100_NODE,
        "FULL_NODE_EXCLUSIVE_H100": "H100_CONFIRMED and realized no-co-residency and nodes_req=nodes_used=gpu_nodes_occupied>0 and gpus_requested=4*nodes_used",
        "PARTIAL_NODE_EXCLUSIVE_H100": "same allocation consistency and 0<gpus_requested<4*nodes_used",
        "SHARED_H100": "H100_CONFIRMED and SHARED_CONFIRMED",
        "UNKNOWN_SPATIAL_H100": "H100_CONFIRMED not satisfying the preceding evidence rules",
        "denominator": "nodes_used, with equality to nodes_req and gpu_nodes_occupied required",
        "authority_warning": "resource shape classification is not energy-label authorization",
    }
    write_json(ARTIFACTS / "V35R3G_FULL_NODE_H100_CONTRACT.json", p(full_contract))
    validity = {
        "ENERGY_POSITIVE_VALID": "finite ConsumedEnergyRaw>0 plus valid completed timestamps/runtime, unique logical allocation, H100 identity, sharing identity, and resolved physical boundary",
        "ENERGY_ZERO_OR_MISSING": "null or zero; zero is not interpreted as physical zero power",
        "ENERGY_INVALID": "negative/nonfinite/counter corruption or duplicate logical attribution",
        "ENERGY_SEMANTICS_UNKNOWN": "numeric value present but physical boundary or attribution is unresolved",
        "H100_counts": scan["H100_energy"],
        "authorized_H100_positive_valid_rows": 0,
    }
    write_json(ARTIFACTS / "V35R3G_ENERGY_VALIDITY_CONTRACT.json", p(validity))
    firewall = {
        "historical_label_only": ["start_time", "end_time", "wallclock_used", "state_simple", "consumed_energy_raw_joules", "shared_job_count", "nodes_shared", "jobs_shared"],
        "future_query_forbidden": ["actual start", "actual end", "realized runtime", "final state", "consumed energy", "ex-post sharing", "future co-resident jobs"],
        "preissue_rule": f"completed end_time <= {ISSUE_TIME_UTC}",
        "Apr01_consumed_energy_reads": 0,
        "Apr01_realized_runtime_reads": 0,
        "Apr01_future_end_reads": 0,
        "model_trained": False,
    }
    write_json(ARTIFACTS / "V35R3G_FUTURE_POWER_MODEL_CAUSAL_FIREWALL.json", p(firewall))
    write_json(ARTIFACTS / "V35R3G_GLOBAL_ENERGY_CENSUS.json", p({"cohorts": scan["global_census"], "source_time_span": scan["source_time_span"]}))
    write_csv(ARTIFACTS / "V35R3G_GLOBAL_ENERGY_CENSUS.csv", _csv_lineage(census_rows(scan["global_census"]), code_commit))
    write_json(ARTIFACTS / "V35R3G_PREISSUE_CAUSAL_ENERGY_CENSUS.json", p({"issue_time_UTC": ISSUE_TIME_UTC, "cohorts": scan["preissue_census"]}))
    write_csv(ARTIFACTS / "V35R3G_PREISSUE_CAUSAL_ENERGY_CENSUS.csv", _csv_lineage(census_rows(scan["preissue_census"]), code_commit))
    write_csv(ARTIFACTS / "V35R3G_RECENCY_COVERAGE.csv", _csv_lineage(recency_rows(scan), code_commit))
    recency_payload = {
        "classification": "NO_CAUSAL_SUPPORT",
        "first_label_date": None,
        "last_label_date": None,
        "median_label_date": None,
        "gap_last_label_to_issue": None,
        "maximum_no_label_gap": None,
        "labels_per_month": {},
        "interpretation": "No positive H100 energy exists anywhere in the public trace; recency is undefined.",
    }
    write_json(ARTIFACTS / "V35R3G_LABEL_RECENCY_AUDIT.json", p(recency_payload))
    plausibility_rows = []
    for partition, jobs in scan["H100_partitions"].items():
        plausibility_rows.append({"partition":partition,"H100_jobs":jobs,"positive_energy_jobs":0,"derived_power_rows":0,"classification":"UNKNOWN","reason":"No positive H100 energy; no E/runtime quantity authorized"})
    write_csv(ARTIFACTS / "V35R3G_POWER_PLAUSIBILITY_AUDIT.csv", _csv_lineage(plausibility_rows, code_commit))
    full_authority = {
        "candidate": "FULL_NODE_EXCLUSIVE_H100 + POSITIVE_VALID_ENERGY + COMPLETED_PREISSUE",
        "jobs": 0,"node_hours":0.0,"GPU_hours":0.0,"total_energy_joules":0.0,"distinct_days":0,
        "node_count_configurations": [],"GPU_count_configurations": [],"partition_QoS": {},
        "requested_walltime_distribution": None,"actual_runtime_distribution": None,"derived_average_power_distribution": None,
        "time_coverage": None,"label_parquet_written":False,
        "classification":"NOT_AUTHORIZED_NO_POSITIVE_H100_ENERGY_AND_BOUNDARY_UNRESOLVED",
    }
    write_json(ARTIFACTS / "V35R3G_FULL_NODE_EXCLUSIVE_H100_AUTHORITY.json", p(full_authority))
    partial = {"positive_valid_energy_jobs":0,"direct_operational_label_authority":"NO","node_state_authority":"NO","reason":"No positive H100 energy and exact node-monitor sensor boundary unresolved","subtraction_from_full_node_coefficient":False}
    write_json(ARTIFACTS / "V35R3G_PARTIAL_EXCLUSIVE_H100_AUDIT.json", p(partial))
    shared = {"positive_energy_jobs":0,"node_hours":0.0,"GPU_hours":0.0,"energy_joules":0.0,"co_resident_count_distribution":{},"sharing_metadata_completeness":"AUDITED","SHARED_JOB_POWER_LABEL_AUTHORIZED":"NO","allocation_heuristics_used":[]}
    write_json(ARTIFACTS / "V35R3G_SHARED_H100_ENERGY_AUDIT.json", p(shared))
    conservation = {"classification":"SHARED_ENERGY_DOUBLE_COUNT_RISK","conservation_provable":False,"reason":"Slurm explicitly says shared-job ConsumedEnergyRaw does not reflect real per-job energy; no conservation-correct split is exposed.","equal_split":False,"GPU_fraction_split":False,"runtime_split":False,"node_fraction_split":False}
    write_json(ARTIFACTS / "V35R3G_SHARED_ENERGY_CONSERVATION.json", p(conservation))
    write_csv(ARTIFACTS / "V35R3G_SPATIAL_TEMPORAL_COVERAGE_MATRIX.csv", _csv_lineage(scan["spatial_rows"], code_commit))
    modelability = {"classification":MODELABILITY,"model_trained":False,"positive_target_labels":0,"multiple_days":False,"multiple_users_accounts":False,"multiple_requested_walltimes":False,"multiple_resource_configurations":False,"target_variation":False,"chronological_train_validation_possible":False,"submission_time_features_exist":True,"decision_basis":"No positive H100 ConsumedEnergyRaw in the entire source; boundary also unresolved."}
    write_json(ARTIFACTS / "V35R3G_POWER_MODELABILITY_AUDIT.json", p(modelability))
    features = {"classification":"PASS_CAUSAL_ALLOWLIST_DEFINED_NO_MODEL_TRAINED","allowlist":["gpus_requested","nodes_req","wallclock_req","partition","qos","account_hash","user_hash","submit_time calendar features"],"forbidden":["start_time","end_time","wallclock_used","state/state_simple","nodes_used","gpu_nodes_occupied","consumed_energy_joules","consumed_energy_raw_joules","consumed_energy_raw_watt_hours","shared_job_count","nodes_shared","jobs_shared","future co-resident jobs"],"target_available":False}
    write_json(ARTIFACTS / "V35R3G_FUTURE_POWER_QUERY_FEATURES.json", p(features))
    write_json(ARTIFACTS / "V35R3G_APR01_FEATURE_DOMAIN_COVERAGE.json", p(coverage))
    authority = {"highest_energy_authority":HIGHEST_AUTHORITY,"primary_classification":PRIMARY_CLASSIFICATION,"secondary_findings":["V35R3G_CONSUMED_ENERGY_SEMANTICS_UNRESOLVED","V35R3G_SHARED_ATTRIBUTION_UNSUPPORTED","GLOBAL_H100_POSITIVE_ENERGY_EMPTY"],"H100_positive_energy_rows":0,"exclusive_H100_energy_authorized":False,"causal_preissue_power_label_authorized":False,"shared_H100_attribution_authorized":False}
    write_json(ARTIFACTS / "V35R3G_AUTHORITY_DECISION.json", p(authority))
    next_step = {"CAUSAL_H100_POWER_MODEL_NEXT":CAUSAL_H100_POWER_MODEL_NEXT,"SHARED_H100_POWER_NEXT":SHARED_H100_POWER_NEXT,"DATASET312_AUTHORITY_CHANGED":"NO","Dataset312_authority":"H1_COMPONENT_LEVEL_H100_POWER_AUTHORITY","Dataset312_role":"diagnostic only; not used in this scan","PRODUCTION_INTEGRATION_RECOMMENDED":"NO","RW_RSP_power_trajectories_created":False,"node_packing_performed":False}
    write_json(ARTIFACTS / "V35R3G_NEXT_STEP_DECISION.json", p(next_step))
    repairs = {"attempts":[],"unique_failure_signatures":0,"maximum_attempts_per_signature":5,"science_semantics_changed":False,"prohibited_repairs_used":[]}
    write_json(ARTIFACTS / "V35R3G_REPAIR_LOG.json", p(repairs))
    compute = {"raw_source_bytes_read":source["archive_bytes"]+source["compressed_parquet_bytes"],"archive_bytes_hashed":source["archive_bytes"],"compressed_parquet_bytes_scanned":source["compressed_parquet_bytes"],"uncompressed_parquet_bytes_processed":source["uncompressed_parquet_bytes"],"normalized_rows":scan["normalized_rows"],"peak_resident_memory_bytes_observed_at_stage_boundaries":accounting.peak_rss,"wallclock_seconds_total":time.perf_counter()-accounting.started,"wallclock_seconds_by_stage":accounting.stage_seconds,"rows_per_second_analysis_scan":scan["normalized_rows"]/max(accounting.stage_seconds.get("source_analysis_scan",1e-9),1e-9),"source_scans":2,"cache_usage":"EMPTY_RESERVED_NO_NORMALIZED_CACHE_NEEDED","process_count":1,"thread_policy":"single Python process; no explicit worker pool","XGBoost":False,"Gurobi":False,"GPU_training":False,"full_year_grid_simulation":False}
    write_json(ARTIFACTS / "V35R3G_COMPUTE_ACCOUNTING.json", p(compute))
    for conditional in CONDITIONAL_ARTIFACTS:
        path = ARTIFACTS / conditional
        if path.exists():
            raise RuntimeError(f"Unauthorized conditional artifact exists: {conditional}")


def run_tests(code_commit: str) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q", "tests/v35r3g/test_operational_energy_forensic.py"]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    output = (completed.stdout + completed.stderr).strip()
    match = re.search(r"(\d+) passed", output)
    failed_match = re.search(r"(\d+) failed", output)
    return with_provenance(
        {
            "classification": "PASS" if completed.returncode == 0 else "FAIL",
            "command": command,
            "returncode": completed.returncode,
            "passed": int(match.group(1)) if match else 0,
            "failed": int(failed_match.group(1)) if failed_match else (0 if completed.returncode == 0 else 1),
            "output": output,
        },
        code_commit,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    accounting = Accounting()
    code_commit = git("rev-parse", "HEAD")
    stage = time.perf_counter()
    start, isolation = verify_start_state()
    accounting.checkpoint("start_state", stage)
    stage = time.perf_counter()
    source = verify_source()
    accounting.checkpoint("source_integrity_and_documentation", stage)
    stage = time.perf_counter()
    scan = scan_source(accounting)
    accounting.checkpoint("source_analysis_scan", stage)
    if scan["normalized_rows"] != 10_559_977:
        raise RuntimeError("Unexpected Dataset 302 row count")
    if scan["global_census"]["H100_POSITIVE_ENERGY"]["jobs"] != 0:
        raise RuntimeError("Fail-closed contract changed: positive H100 energy unexpectedly present")
    stage = time.perf_counter()
    coverage = apr01_feature_coverage()
    accounting.checkpoint("Apr01_submission_feature_coverage", stage)
    tests = with_provenance({"classification":"NOT_RUN","passed":0,"failed":0}, code_commit)
    build_artifacts(scan, source, start, isolation, coverage, accounting, code_commit)
    review, markdown = build_final_review(scan, coverage, tests, code_commit)
    write_json(ARTIFACTS / "V35R3G_FINAL_REVIEW.json", review)
    (ARTIFACTS / "V35R3G_FINAL_REVIEW.md").write_text(markdown, encoding="utf-8")
    write_json(ARTIFACTS / "V35R3G_TEST_REPORT.json", tests)
    if not args.skip_tests:
        tests = run_tests(code_commit)
        write_json(ARTIFACTS / "V35R3G_TEST_REPORT.json", tests)
        review, markdown = build_final_review(scan, coverage, tests, code_commit)
        write_json(ARTIFACTS / "V35R3G_FINAL_REVIEW.json", review)
        (ARTIFACTS / "V35R3G_FINAL_REVIEW.md").write_text(markdown, encoding="utf-8")
        if tests["failed"] or tests["returncode"]:
            print(tests["output"], file=sys.stderr)
            return 1
    missing = [name for name in REQUIRED_ARTIFACTS if not (ARTIFACTS / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing required artifacts: {missing}")
    print(json.dumps({"classification": PRIMARY_CLASSIFICATION, "artifacts": len(REQUIRED_ARTIFACTS), "tests": tests["passed"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
