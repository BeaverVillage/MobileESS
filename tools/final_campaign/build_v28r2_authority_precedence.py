#!/usr/bin/env python3
"""Freeze the V28R2 precedence addendum and workload eligibility binding."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v28r2.authority import (  # noqa: E402
    AUTHORITY_PRECEDENCE,
    COHORT_IDS,
    CONTROLLABLE_NODE_CLASSES,
    D1_ALLOWED_FIELDS,
    EXPOST_FIELDS,
    WorkloadEligibilityBinding,
    repository_authority_paths,
)


OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def main() -> None:
    paths = repository_authority_paths(REPO)
    frozen = read(paths["final_refreeze"])
    eligibility = read(paths["eligibility"])
    cohorts = read(paths["cohorts"])
    admission = read(paths["admission"])
    binding = WorkloadEligibilityBinding()
    binding.validate()
    if tuple(cohorts["cohort_ids"]) != COHORT_IDS:
        raise RuntimeError("V28R2_REPOSITORY_COHORT_MISMATCH")
    if tuple(admission["allowed_fields"]) != tuple(sorted(D1_ALLOWED_FIELDS)):
        raise RuntimeError("V28R2_REPOSITORY_D1_FIELD_MISMATCH")
    precedence = {
        "artifact_id": "V28R2_AUTHORITY_PRECEDENCE_ADDENDUM_V1",
        "status": "PASS",
        "AUTHORITY_PRECEDENCE_READY": True,
        "ordered_precedence": list(AUTHORITY_PRECEDENCE),
        "latest_refreeze": {
            "created_at_utc": frozen["created_at_utc"],
            "updated_at_utc": frozen["updated_at_utc"],
            "authority_fingerprint": frozen["authority_fingerprint"],
            "authority_ids": frozen["authority_ids"],
            "source": {"path": paths["final_refreeze"].relative_to(REPO).as_posix(), "sha256": sha(paths["final_refreeze"])},
        },
        "conflict_resolution": {
            "V21_six_tier_PARTIAL_adapter": "HISTORICAL_EVIDENCE_ONLY_NOT_CONTROLLABLE_AUTHORITY",
            "controllable_workload": "2026-08-29_NLR_KESTREL_H100_ELIGIBILITY_V1",
            "cohorts": "AIDC_COHORT_CONTRACT_V16_NODE_CLASS_X_RUNTIME_CLASS",
            "reference_schedule": "REFERENCE_COMPUTE_SCHEDULE_V2",
            "ML_family": "V28_FINAL_LIGHTGBM",
            "scale": "V22SR1",
            "thermal": "V24T_C1",
            "solver_grid": "V16_3",
        },
        "source_sha256": {name: sha(path) for name, path in paths.items()},
    }
    workload = {
        "artifact_id": "V28R2_WORKLOAD_ELIGIBILITY_BINDING_V1",
        "status": "PASS",
        "WORKLOAD_ELIGIBILITY_READY": True,
        "authority_id": eligibility["authority_id"],
        "historical_label_rule": eligibility["rule"],
        "historical_label_expost_fields_role": eligibility["expost_fields_role"],
        "controllable_node_classes": list(CONTROLLABLE_NODE_CLASSES),
        "cohort_ids": list(COHORT_IDS),
        "cohort_definition": "node count x frozen runtime class R00/R01/R02",
        "runtime_bins_hours_by_node_class": cohorts["runtime_bins_hours_by_node_class"],
        "partial_controllable": False,
        "partial_reference_embedded": True,
        "sharing_controllable": False,
        "unsupported_fullnode_controllable": False,
        "individual_queue_injection": False,
        "initial_backlog_nodeh": 0.0,
        "D1_mode": admission["mode"],
        "D1_allowed_fields": sorted(D1_ALLOWED_FIELDS),
        "D1_expost_field_denylist": sorted(EXPOST_FIELDS),
        "PARTIAL_CPU_package_increment_invented": False,
        "PARTIAL_to_FULL_remapping": False,
        "uncontrolled_reference_rule": "PARTIAL/shared/unsupported work remains embedded in total P_IT_REF and G_REF and enters the non-controllable reference residual.",
        "source_sha256": {
            "eligibility": sha(paths["eligibility"]),
            "cohorts": sha(paths["cohorts"]),
            "admission": sha(paths["admission"]),
        },
    }
    write("V28R2_AUTHORITY_PRECEDENCE_ADDENDUM.json", precedence)
    write("V28R2_WORKLOAD_ELIGIBILITY_BINDING.json", workload)
    (OUT / "V28R2_AUTHORITY_PRECEDENCE_ADDENDUM.md").write_text(
        "# V28R2 authority precedence addendum\n\n"
        "The 2026-08-29 final scientific re-freeze controls target, eligibility, cohort, D-1 admission, reference schedule, replay, and formulation semantics. "
        "V21's six-tier adapter is historical evidence only; `PARTIAL` is never an actuator. V28 controls the final LightGBM family, V22SR1 the operating scale, V24T C1 thermal physics, and V16.3 the solver/grid structure.\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
