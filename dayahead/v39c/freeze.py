"""Materialize and freeze the V39C capacity before any May evaluation read."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Any, Mapping

import pandas as pd
import pyarrow.parquet as pq

from .contracts import (
    ARTIFACT_ROOT,
    BRANCH,
    CAPACITY_SEMANTICS,
    CLASSIFICATION,
    EXPECTED_GPU_CAPACITY,
    EXPECTED_NODE_CAPACITY,
    EXPECTED_TOP_SEVEN,
    EXPECTED_WEIGHT_ORDER,
    EXTRA_BLOCK_GPU,
    EXTRA_BLOCK_NODES,
    GPU_PER_NODE,
    GPU_TOTAL,
    IMPLEMENTATION_ID,
    LEGACY_CAPACITY_SOURCE_SHA256,
    LEGACY_GPU_CAPACITY,
    LEGACY_MAPPING_PATH,
    LEGACY_MAPPING_SHA256,
    LEGACY_PROVENANCE_PATH,
    LEGACY_RACK_CONTRACT_PATH,
    MINIMUM_GPU_PER_SITE,
    MINIMUM_NODES_PER_SITE,
    NODE_TOTAL,
    PREMAY_CUTOFF,
    PREMAY_NORMALIZED_HISTORY,
    PREMAY_NORMALIZED_HISTORY_SHA256,
    START_HEAD,
    V22_WEIGHT_PATH,
    V22_WEIGHT_SHA256,
    V39A_FINGERPRINT,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(
        path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
    )
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    for attempt in range(300):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 299:
                raise
            time.sleep(0.1)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=repo, text=True, encoding="utf-8"
    ).strip()


def load_facility_prior(repo: Path) -> tuple[dict[str, float], list[dict[str, str]]]:
    path = repo / V22_WEIGHT_PATH
    if sha256_file(path) != V22_WEIGHT_SHA256:
        raise RuntimeError("V39C_V22SR1_WEIGHT_SHA_DRIFT")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    weights = {str(row["site_id"]): float(row["capacity_weight"]) for row in rows}
    if len(weights) != 12 or not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12):
        raise RuntimeError("V39C_V22SR1_WEIGHT_AXIS_OR_SUM")
    return weights, rows


def construct_capacity(weights: Mapping[str, float]) -> dict[str, Any]:
    """Apply the specified base-plus-gang-block rule, independently of May."""

    order = tuple(
        sorted(weights, key=lambda site: (-float(weights[site]), int(site[4:])))
    )
    nodes = {site: MINIMUM_NODES_PER_SITE for site in sorted(weights)}
    base_nodes = len(nodes) * MINIMUM_NODES_PER_SITE
    remaining_nodes = NODE_TOTAL - base_nodes
    full_blocks, residual_nodes = divmod(remaining_nodes, EXTRA_BLOCK_NODES)
    for site in order[:full_blocks]:
        nodes[site] += EXTRA_BLOCK_NODES
    nodes[order[0]] += residual_nodes
    gpu = {site: value * GPU_PER_NODE for site, value in nodes.items()}
    result = {
        "facility_weight_order": list(order),
        "top_full_block_recipients": list(order[:full_blocks]),
        "base_nodes": base_nodes,
        "base_GPU": base_nodes * GPU_PER_NODE,
        "remaining_nodes": remaining_nodes,
        "remaining_GPU": remaining_nodes * GPU_PER_NODE,
        "full_32GPU_blocks": full_blocks,
        "residual_nodes": residual_nodes,
        "residual_GPU": residual_nodes * GPU_PER_NODE,
        "residual_recipient": order[0],
        "site_nodes": nodes,
        "site_GPU": gpu,
        "host_positions_32GPU": sum(value // 32 for value in gpu.values()),
    }
    if order != EXPECTED_WEIGHT_ORDER:
        raise RuntimeError("V39C_FACILITY_WEIGHT_ORDER_DRIFT")
    if tuple(order[:full_blocks]) != EXPECTED_TOP_SEVEN:
        raise RuntimeError("V39C_TOP_SEVEN_DRIFT")
    if nodes != EXPECTED_NODE_CAPACITY or gpu != EXPECTED_GPU_CAPACITY:
        raise RuntimeError("V39C_CAPACITY_CONSTRUCTION_DRIFT")
    if sum(nodes.values()) != NODE_TOTAL or sum(gpu.values()) != GPU_TOTAL:
        raise RuntimeError("V39C_CAPACITY_CONSERVATION")
    if any(value < MINIMUM_GPU_PER_SITE or value % GPU_PER_NODE for value in gpu.values()):
        raise RuntimeError("V39C_CAPACITY_GRANULARITY")
    if result["host_positions_32GPU"] != 19:
        raise RuntimeError("V39C_32GPU_HOST_POSITION_DRIFT")
    return result


def _legacy_audit(repo: Path, rule_commit: str) -> dict[str, Any]:
    mapping_path = repo / LEGACY_MAPPING_PATH
    if sha256_file(mapping_path) != LEGACY_MAPPING_SHA256:
        raise RuntimeError("V39C_LEGACY_MAPPING_SHA_DRIFT")
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    provenance_path = repo / LEGACY_PROVENANCE_PATH
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if mapping["source_sha256"] != LEGACY_CAPACITY_SOURCE_SHA256:
        raise RuntimeError("V39C_LEGACY_SOURCE_SHA_DRIFT")
    recovered = {row["AIDC_id"]: int(row["C_GPU"]) for row in mapping["rows"]}
    if recovered != LEGACY_GPU_CAPACITY:
        raise RuntimeError("V39C_LEGACY_CAPACITY_VECTOR_DRIFT")
    return {
        "implementation_id": IMPLEMENTATION_ID,
        "artifact_id": "V39C_LEGACY_GPU_CAPACITY_PROVENANCE_AUDIT_V1",
        "status": "PASS",
        "source_HEAD": START_HEAD,
        "capacity_rule_source_commit": rule_commit,
        "legacy_source_paths": [
            LEGACY_MAPPING_PATH.as_posix(),
            LEGACY_RACK_CONTRACT_PATH.as_posix(),
            LEGACY_PROVENANCE_PATH.as_posix(),
            provenance["exact_capacity_authority"]["authority_file"],
        ],
        "source_SHAs": {
            LEGACY_MAPPING_PATH.as_posix(): sha256_file(mapping_path),
            LEGACY_RACK_CONTRACT_PATH.as_posix(): sha256_file(
                repo / LEGACY_RACK_CONTRACT_PATH
            ),
            LEGACY_PROVENANCE_PATH.as_posix(): sha256_file(provenance_path),
            "external_legacy_capacity_source": LEGACY_CAPACITY_SOURCE_SHA256,
        },
        "legacy_capacity": recovered,
        "original_weights": {
            row["AIDC_id"]: float(row["gamma"]) for row in mapping["rows"]
        },
        "original_weight_basis": "sum of 48 synthetic logical-Rack deliverable_active_gpu_capacity rows by AIDC",
        "conversion_rule": "largest-remainder allocation of total 624 equivalent GPUs",
        "installed_GPU_measurement_found": "NO",
        "measured_site_GPU_claim_authorized": "NO",
        "real_facility_capacity_claim_authorized": "NO",
        "final_classification": "SYNTHETIC_EQUIVALENT_GPU_ALLOCATION_FROM_LEGACY_LOGICAL_RACK_SPATIAL_WEIGHTS",
        "legacy_provenance_classification": provenance["classification"],
        "preserved_not_overwritten": True,
        "production_mutation_count": 0,
        "future_read_count": 0,
        "MAY_STARTED": "NO",
    }


def _premay_audit(rule_commit: str) -> dict[str, Any]:
    path = PREMAY_NORMALIZED_HISTORY
    if not path.is_file() or sha256_file(path) != PREMAY_NORMALIZED_HISTORY_SHA256:
        raise RuntimeError("V39C_PREMAY_HISTORY_MISSING_OR_CHANGED")
    columns = [
        "job_id", "submit_time", "end_time", "runtime_seconds", "num_gpus_req"
    ]
    frame = pq.read_table(path, columns=columns).to_pandas()
    cutoff = pd.Timestamp(PREMAY_CUTOFF).tz_convert("UTC")
    eligible = frame.loc[
        frame["end_time"].lt(cutoff)
        & frame["num_gpus_req"].notna()
        & frame["num_gpus_req"].gt(0)
        & frame["runtime_seconds"].notna()
        & frame["runtime_seconds"].ge(0)
    ].copy()
    eligible["requested_GPU"] = eligible["num_gpus_req"].astype(int)
    eligible["GPU_hours"] = (
        eligible["requested_GPU"] * eligible["runtime_seconds"] / 3600.0
    )
    grouped = eligible.groupby("requested_GPU", sort=True).agg(
        job_count=("job_id", "count"), GPU_hours=("GPU_hours", "sum")
    )
    requested_sizes = sorted(set(grouped.index) | {1, 2, 4, 8, 16, 32, 60})
    rows = []
    for gpu in requested_sizes:
        count = int(grouped.loc[gpu, "job_count"]) if gpu in grouped.index else 0
        gpu_hours = float(grouped.loc[gpu, "GPU_hours"]) if gpu in grouped.index else 0.0
        rows.append({
            "requested_GPU": gpu,
            "job_count": count,
            "GPU_hours": gpu_hours,
            "frequency": count / len(eligible),
        })
    return {
        "implementation_id": IMPLEMENTATION_ID,
        "artifact_id": "V39C_PREMAY_JOB_GANG_SIZE_AUDIT_V1",
        "status": "PASS",
        "source_HEAD": START_HEAD,
        "capacity_rule_source_commit": rule_commit,
        "source_path": str(path),
        "source_SHA256": PREMAY_NORMALIZED_HISTORY_SHA256,
        "strict_causal_cutoff": PREMAY_CUTOFF,
        "selection": "completed end_time strictly before cutoff; positive requested GPU; known nonnegative runtime",
        "eligible_job_count": len(eligible),
        "total_GPU_hours": float(eligible["GPU_hours"].sum()),
        "observed_requested_GPU_sizes": sorted(int(value) for value in grouped.index),
        "maximum_requested_GPU": int(eligible["requested_GPU"].max()),
        "gang_size_statistics": rows,
        "32GPU_gang_job_count": int(grouped.loc[32, "job_count"]),
        "32GPU_gang_repeatedly_observed": bool(grouped.loc[32, "job_count"] > 1),
        "60GPU_gang_job_count": int(
            grouped.loc[60, "job_count"] if 60 in grouped.index else 0
        ),
        "60GPU_frequency_classification": (
            "RARE" if 60 in grouped.index and grouped.loc[60, "job_count"] > 0
            else "NOT_OBSERVED_IN_STRICT_PREMAY_AUTHORITY"
        ),
        "engineering_interpretation": (
            "The audit supports 4-GPU node granularity and recurrent 32-GPU service blocks; "
            "it does not fit capacity to May outcomes or claim all historical gangs fit one site."
        ),
        "May_rows": 0,
        "May_result_reads": 0,
        "Fresh_reads": 0,
        "grid_reads": 0,
        "Actual_reads": 0,
        "production_mutation_count": 0,
        "future_read_count": 0,
        "MAY_STARTED": "NO",
    }


def _authority_payload(
    weights: Mapping[str, float], construction: Mapping[str, Any], rule_commit: str
) -> dict[str, Any]:
    table = [
        {
            "AIDC": site,
            "facility_size_soft_prior": float(weights[site]),
            "equivalent_H100_nodes": int(construction["site_nodes"][site]),
            "synthetic_H100_equivalent_GPU_capacity": int(
                construction["site_GPU"][site]
            ),
            "received_extra_32GPU_block": site in construction[
                "top_full_block_recipients"
            ],
            "received_16GPU_residual": site == construction["residual_recipient"],
        }
        for site in sorted(weights)
    ]
    core = {
        "classification": CLASSIFICATION,
        "capacity_semantics": CAPACITY_SEMANTICS,
        "total_nodes": NODE_TOTAL,
        "total_GPUs": GPU_TOTAL,
        "GPU_per_node": GPU_PER_NODE,
        "minimum_nodes_per_site": MINIMUM_NODES_PER_SITE,
        "minimum_GPU_per_site": MINIMUM_GPU_PER_SITE,
        "V22SR1_prior_source": V22_WEIGHT_PATH.as_posix(),
        "V22SR1_prior_SHA256": V22_WEIGHT_SHA256,
        "V22SR1_prior_role": "MELBOURNE_FACILITY_SIZE_SOFT_PRIOR",
        "allocation_rule": {
            "base": "8 equivalent H100 nodes to each of 12 modeled AIDC sites",
            "residual_full_blocks": "one 8-node/32-GPU block to each of the seven highest-weight sites",
            "final_residual": "four nodes/16 GPU to the highest-weight site AIDC05",
            "tie_break": "AIDC numeric ID ascending",
        },
        "facility_weight_order": construction["facility_weight_order"],
        "top_full_block_recipients": construction["top_full_block_recipients"],
        "residual_recipient": construction["residual_recipient"],
        "site_table": table,
        "canonical_node_vector": [construction["site_nodes"][site] for site in sorted(weights)],
        "canonical_GPU_vector": [construction["site_GPU"][site] for site in sorted(weights)],
        "32GPU_host_position_count": construction["host_positions_32GPU"],
        "total_conservation": True,
        "four_GPU_granularity": True,
        "measured_GPU_claim": False,
        "modeled_AIDC_sites": True,
        "May_outcome_used_in_numeric_allocation": False,
        "capacity_rule_source_commit": rule_commit,
    }
    return {
        "implementation_id": IMPLEMENTATION_ID,
        "artifact_id": "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY_V1",
        "status": "PASS_FROZEN",
        "source_HEAD": START_HEAD,
        **core,
        "canonical_SHA256": canonical_sha256(core),
        "numeric_construction_May_reads": 0,
        "numeric_construction_Fresh_grid_reads": 0,
        "production_mutation_count": 0,
        "future_read_count": 0,
        "MAY_STARTED": "NO",
    }


def freeze(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    if _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V39C_BRANCH_MISMATCH")
    if _git(repo, "merge-base", "HEAD", START_HEAD) != START_HEAD:
        raise RuntimeError("V39C_START_HEAD_ANCESTRY")
    rule_commit = _git(repo, "rev-parse", "HEAD")
    weights, _source_rows = load_facility_prior(repo)
    construction = construct_capacity(weights)
    root = repo / ARTIFACT_ROOT
    root.mkdir(parents=True, exist_ok=True)
    legacy = _legacy_audit(repo, rule_commit)
    premay = _premay_audit(rule_commit)
    authority = _authority_payload(weights, construction, rule_commit)
    authority_path = root / "V39C_H100_EQUIVALENT_SITE_CAPACITY_AUTHORITY.json"
    atomic_json(root / "V39C_LEGACY_GPU_CAPACITY_PROVENANCE_AUDIT.json", legacy)
    atomic_json(root / "V39C_PREMAY_JOB_GANG_SIZE_AUDIT.json", premay)
    atomic_json(authority_path, authority)
    authority_file_sha = sha256_file(authority_path)
    certificate = {
        "implementation_id": IMPLEMENTATION_ID,
        "artifact_id": "V39C_CAPACITY_FREEZE_CERTIFICATE_V1",
        "status": "PASS_FROZEN_BEFORE_MAY_EVALUATION",
        "source_HEAD": START_HEAD,
        "capacity_rule_source_commit": rule_commit,
        "capacity_authority_path": ARTIFACT_ROOT.joinpath(
            authority_path.name
        ).as_posix(),
        "capacity_authority_file_SHA256": authority_file_sha,
        "capacity_canonical_SHA256": authority["canonical_SHA256"],
        "CAPACITY_RULE_FROZEN_BEFORE_V39C_MAY_FEASIBILITY": "YES",
        "May_schedule_reads_before_freeze": 0,
        "May_feasibility_result_reads_before_freeze": 0,
        "Fresh_grid_result_reads_before_freeze": 0,
        "capacity_mutations_after_freeze": 0,
        "V39A_fingerprint_preserved": V39A_FINGERPRINT,
        "production_mutation_count": 0,
        "future_read_count": 0,
        "MAY_STARTED": "NO",
    }
    atomic_json(root / "V39C_CAPACITY_FREEZE_CERTIFICATE.json", certificate)
    return {
        "status": "CAPACITY_FROZEN",
        "capacity_rule_source_commit": rule_commit,
        "capacity_authority_file_SHA256": authority_file_sha,
        "capacity_canonical_SHA256": authority["canonical_SHA256"],
        "canonical_GPU_vector": authority["canonical_GPU_vector"],
        "May_reads": 0,
        "MAY_STARTED": "NO",
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(freeze(args.repo), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "atomic_json", "canonical_sha256", "construct_capacity", "freeze",
    "load_facility_prior", "sha256_file",
]
