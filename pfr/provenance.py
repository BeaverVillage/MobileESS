"""Stable source identity for January scientific-result reuse."""

from __future__ import annotations

import hashlib
from pathlib import Path


def scientific_implementation_files(repo: Path) -> tuple[Path, ...]:
    repo = repo.resolve()
    files = sorted((repo / "pfr").glob("*.py"))
    files.extend(
        (
            repo / "pfr" / "tools" / "run_pfr_matrix.py",
            repo / "pfr" / "tools" / "run_pfr_daily_campaign.py",
            repo / "pfr" / "tools" / "run_frozen_rep_week_daily_campaign.py",
            repo / "pfr" / "tools" / "run_full_february_march_2025_local.sh",
            repo / "pfr" / "tools" / "verify_daily_campaign_storage.py",
            repo / "pfr" / "tools" / "audit_h0_surrogate_fidelity.py",
        )
    )
    files.extend(
        (
            repo / "science" / "EXACT_GRID_RUNNER_24SERVICE.py",
            repo / "pfr" / "contracts" / "COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.dss",
            repo / "pfr" / "contracts" / "COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.json",
            repo / "pfr" / "contracts" / "IEEE123_NATIVE_CONTROL_ASSET_AUDIT_V1.json",
            repo / "pfr" / "contracts" / "PFR_RUNTIME_CONTRACT.json",
            repo / "pfr" / "contracts" / "IDC_MIGRATION_AUTHORITY_V1.json",
            repo / "pfr" / "contracts" / "AC_SAFETY_FILTER_CONTRACT.json",
            repo
            / "pfr"
            / "contracts"
            / "BACKGROUND_LOAD_SCALE_CONSISTENCY_AUDIT_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "BACKGROUND_NATIVE_FEASIBILITY_GATE_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json",
            repo
            / "pfr"
            / "contracts"
            / "PFR10_GLOBAL_AC_PROJECTION_REDESIGN_V8.json",
            repo
            / "pfr"
            / "contracts"
            / "PREDICTIVE_NATIVE_DWELL_GUARD_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "MESS_MOBILITY_PHYSICS_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "MESS_MOBILITY_EXECUTION_SUMO_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "H0_SURROGATE_FIDELITY_GATE_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "EPISODE_BOUNDARY_RECOVERY_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "RETAINED_PLAN_EVENT_TRIGGER_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "SERVICE_FEASIBILITY_CLASSIFICATION_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "SIMULATION_CALENDAR_DATE_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "REBOUND_SHADOW_AUTHORITY_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "ELECTRICAL_STRESS_RESULT_SCHEMA_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "CAUSAL_PHASE_ENVELOPE_SURROGATE_V1.json",
            repo
            / "pfr"
            / "contracts"
            / "MESS_REACTIVE_DISPATCH_AUTHORITY_V1.json",
        )
    )
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise RuntimeError(f"scientific implementation source is missing: {missing}")
    return tuple(files)


def scientific_implementation_fingerprint(repo: Path) -> str:
    repo = repo.resolve()
    digest = hashlib.sha256()
    for path in scientific_implementation_files(repo):
        relative = path.relative_to(repo).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 << 20), b""):
                digest.update(block)
    return digest.hexdigest()
