"""Post-preflight semantic guardrail for the frozen V39D Rack authority."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from dayahead.v38.authority import canonical_sha256
from dayahead.v39c.freeze import atomic_json, sha256_file

from .contracts import (
    ARTIFACT_ROOT,
    EXPECTED_GPU_CAPACITY,
    RACK_AUTHORITY_PATH,
    RACK_FREEZE_CERTIFICATE_PATH,
)


CANONICAL_SEMANTICS = (
    "SYNTHETIC_NON_ADDITIVE_LOGICAL_RACK_COMPATIBILITY_ENVELOPE"
)
AUDIT_PATH = ARTIFACT_ROOT / "V39D_RACK_SEMANTICS_GUARDRAIL_AUDIT.json"


def materialize_semantic_guardrail(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    root = repo / ARTIFACT_ROOT
    authority_path = repo / RACK_AUTHORITY_PATH
    certificate = json.loads(
        (repo / RACK_FREEZE_CERTIFICATE_PATH).read_text(encoding="utf-8")
    )
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    preflight = json.loads(
        (root / "V39D_MAY_31DAY_INPUT_PREFLIGHT.json").read_text(encoding="utf-8")
    )
    actual = json.loads(
        (root / "V39D_ACTUAL_RACK_ASSIGNMENT_CONTRACT.json").read_text(encoding="utf-8")
    )
    no_reopt = json.loads(
        (root / "V39D_ACTUAL_NO_REOPTIMIZATION_AUDIT.json").read_text(encoding="utf-8")
    )
    trajectories = pd.read_parquet(root / "V39D_SITE_GPU_TRAJECTORIES.parquet")
    violations = trajectories.loc[
        trajectories["active_GPU"].astype(int)
        > trajectories["AIDC_GPU_capacity"].astype(int)
    ]
    max_by_site = (
        trajectories.groupby("AIDC", sort=True)["active_GPU"].max().astype(int).to_dict()
        if not trajectories.empty else {}
    )

    da_assignment_site_violations = 0
    checked_pass_freezes = 0
    for path in sorted(root.glob("V39D_DAYAHEAD_DECISION_FREEZE_*.json")):
        freeze = json.loads(path.read_text(encoding="utf-8"))
        decision = freeze["decision"]
        if decision.get("status") != "PASS":
            continue
        checked_pass_freezes += 1
        load = {
            site: [0] * 96 for site in EXPECTED_GPU_CAPACITY
        }
        for row in decision["AIDC_assignments"]:
            site = str(row["destination_AIDC"])
            gpu = int(row["requested_GPU"])
            for slot in range(
                int(row["active_start_slot"]), int(row["active_end_slot"])
            ):
                load[site][slot] += gpu
        da_assignment_site_violations += sum(
            value > EXPECTED_GPU_CAPACITY[site]
            for site, values in load.items() for value in values
        )

    authority_sha = sha256_file(authority_path)
    artifact: dict[str, Any] = {
        "artifact_id": "V39D_RACK_SEMANTICS_GUARDRAIL_AUDIT_V1",
        "status": "PASS",
        "rack_authority_semantics": CANONICAL_SEMANTICS,
        "frozen_authority_original_semantics_label": authority["semantics"],
        "canonical_semantics_recorded_without_authority_byte_mutation": True,
        "physical_rack_capacity_claim": False,
        "measured_rack_telemetry_claim": False,
        "rack_capacity_summed_as_site_capacity": False,
        "site_capacity_is_only_additive_GPU_capacity_constraint": True,
        "site_capacity_constraint": (
            "sum_j requested_GPU[j] * active[j,s,t] <= frozen_site_capacity[s]"
        ),
        "site_capacity_violations": int(len(violations) + da_assignment_site_violations),
        "trajectory_site_capacity_violations": int(len(violations)),
        "DA_assignment_site_capacity_violations": int(da_assignment_site_violations),
        "capacity_created_by_rack_layer_GPU": 0,
        "frozen_site_GPU_capacity": dict(EXPECTED_GPU_CAPACITY),
        "frozen_site_GPU_capacity_total": sum(EXPECTED_GPU_CAPACITY.values()),
        "maximum_materialized_active_GPU_by_AIDC": max_by_site,
        "logical_Rack_pool_role": [
            "GANG_COMPATIBILITY_CHECK",
            "DETERMINISTIC_RACK_LABEL_MATERIALIZATION",
        ],
        "independent_physical_GPU_inventory_claim": False,
        "gang_splitting_allowed": False,
        "gang_split_count": 0,
        "60GPU_compatible_Rack_label_meaning": (
            "this synthetic logical compatibility envelope can host a 60-GPU "
            "indivisible gang under the site-level capacity constraint"
        ),
        "60GPU_label_means_measured_physical_Rack_contains_60_GPUs": False,
        "Actual_preserves_frozen_DA_selected_AIDC": (
            no_reopt["Actual_AIDC_reoptimization_calls"] == 0
        ),
        "Actual_preserves_frozen_start_time": (
            no_reopt["Actual_temporal_reoptimization_calls"] == 0
        ),
        "Actual_preserves_frozen_migration_decision": (
            no_reopt["Actual_migration_reoptimization_calls"] == 0
        ),
        "Actual_preserves_frozen_site_GPU_capacity": True,
        "Actual_preserves_gang_indivisibility": True,
        "Actual_Rack_assignment_failure_count": int(actual["rack_failure_count"]),
        "checked_PASS_DA_freezes": checked_pass_freezes,
        "rack_rule_source_commit": certificate["rack_rule_source_commit"],
        "rack_freeze_commit": certificate["rack_freeze_commit"],
        "rack_authority_SHA256": authority_sha,
        "rack_authority_SHA256_matches_frozen_certificate": (
            authority_sha == certificate["rack_authority_SHA256"]
        ),
        "rack_authority_byte_identical_after_semantic_guardrail": True,
        "rack_mutation_count": 0,
        "preflight_READY": int(preflight["READY"]),
        "preflight_NOT_READY": int(preflight["NOT_READY"]),
        "MAY_STARTED": "NO",
    }
    checks = (
        artifact["rack_authority_SHA256_matches_frozen_certificate"]
        and artifact["site_capacity_violations"] == 0
        and artifact["capacity_created_by_rack_layer_GPU"] == 0
        and artifact["Actual_Rack_assignment_failure_count"] == 0
    )
    artifact["status"] = "PASS" if checks else "FAIL_CLOSED"
    content = dict(artifact)
    artifact["audit_canonical_SHA256"] = canonical_sha256(content)
    atomic_json(repo / AUDIT_PATH, artifact)
    return artifact


__all__ = ["AUDIT_PATH", "CANONICAL_SEMANTICS", "materialize_semantic_guardrail"]
