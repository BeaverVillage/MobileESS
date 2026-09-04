#!/usr/bin/env python3
"""Resolve and freeze the unique V28 authority lineage."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead" / "artifacts" / "v28_final_dayahead_actual"


AUTHORITIES = {
    "final_15_minute_96_slot_formulation": "dayahead/artifacts/v16_3_final/V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json",
    "final_B0_B3_definitions": "dayahead/artifacts/v16_3_final/V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json",
    "final_CL_MC_BD_implementation": "dayahead/v16_3_decomposition_executor.py",
    "final_Standard_BD_implementation": "dayahead/v16_3_decomposition_executor.py",
    "final_Monolithic_implementation": "dayahead/final_science_solver_v16_3.py",
    "final_Actual_realized_decomposition_contract": "dayahead/artifacts/v16/AIDC_REALIZED_DECOMPOSITION_CONTRACT.json",
    "final_Fresh_OpenDSS_configuration": "dayahead/artifacts/v16_3_final/V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json",
    "V22SR1_scale": "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_FINAL_IEEE123_AIDC_SCALE.json",
    "V22SR1_site_weights": "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_PRIMARY_SITE_WEIGHTS.csv",
    "V24T_C1_thermal_model_branch": "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json",
    "V27_final_ML_decision": "dayahead/artifacts/v27m_safe_flex_r1/V27M_FINAL_REVIEW.json",
    "V21_LightGBM_quantile_models": "dayahead/artifacts/v21_pre_science_integration/V21_B3_PRODUCTION_MODEL_AUTHORITY.json",
    "traffic_forecast_realized_authority": "dayahead/artifacts/v16/DAYAHEAD_IMPLEMENTATION_AUTHORITY.json",
    "grid_demand_forecast_actual_authority": "dayahead/artifacts/v16_3_final/V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json",
    "PV_forecast_actual_authority": "dayahead/artifacts/v16_3_final/V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json",
    "Mobile_ESS_mobility_authority": "dayahead/artifacts/v16/DAYAHEAD_IMPLEMENTATION_AUTHORITY.json",
    "12_site_AIDC_mapping": "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_PRIMARY_SITE_WEIGHTS.csv",
    "rack_cohort_allocation_authority": "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json",
}


def git(*args: str) -> str:
    return subprocess.check_output(("git", *args), cwd=REPO, text=True, encoding="utf-8").strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def authority_record(relative: str) -> dict[str, object]:
    path = REPO / relative
    if path.exists():
        return {
            "path": relative,
            "exists_at_resolution": True,
            "sha256": sha256(path),
            "git_last_commit": git("log", "-1", "--format=%H", "--", relative),
        }
    if "v24t_thermal_aware_aidc" in relative:
        branch = "e7dad3a7b7c10dcb343747849e577d053c125e44"
        object_spec = f"{branch}:{relative}"
        try:
            content = subprocess.check_output(("git", "show", object_spec), cwd=REPO)
        except subprocess.CalledProcessError:
            return {"path": relative, "exists_at_resolution": False, "status": "MISSING_IN_V24T"}
        return {
            "path": relative,
            "exists_at_resolution": False,
            "source_branch_head": branch,
            "sha256": hashlib.sha256(content).hexdigest(),
            "status": "RESOLVED_ON_V24T_PENDING_EXACT_IMPORT",
        }
    return {"path": relative, "exists_at_resolution": False, "status": "MISSING"}


def main() -> None:
    resolved = {name: authority_record(path) for name, path in AUTHORITIES.items()}
    unresolved = [name for name, record in resolved.items() if str(record.get("status", "")).startswith("MISSING")]
    lineage = {
        "artifact_id": "V28_LINEAGE_RESOLUTION_V1",
        "classification": "V28_FINAL_AUTHORITY_LINEAGE_RESOLVED" if not unresolved else "V28_FINAL_OPTIMIZER_AUTHORITY_AMBIGUOUS",
        "integration_base": "a9f75e603a74cd3f938aa7eb7dfa537fd4ea0662",
        "V22SR1_head": "499d5793ed4b725fa5d0b38691b07752c4f88482",
        "V24T_head": "e7dad3a7b7c10dcb343747849e577d053c125e44",
        "V27_head": "a9f75e603a74cd3f938aa7eb7dfa537fd4ea0662",
        "V24T_merge_base_with_V27": "1322b563c78bb0522e5633ed0524f3865bc154fd",
        "authorities": resolved,
        "optimizer_resolution": {
            "authority_id": "V16_3_DA_AIDC_ICPS_AC_ANCHORED_FROZEN_D1_CONTROL",
            "formulation_and_constraints": "V16_3_FROZEN_FORMULATION_ONLY",
            "monolithic": "dayahead.final_science_solver_v16_3.solve_shadow",
            "standard_single_cut_BD": "dayahead.v16_3_decomposition_executor.solve_benders(method=STANDARD_BD)",
            "CL_MC_BD": "dayahead.v16_3_decomposition_executor.solve_benders(method=CL_MC_BD)",
            "CL_MC_BD_repository_spelled_expansion": None,
            "CL_MC_BD_repository_semantics": "ALL_CRITICAL_TIME_FULL_LP_MULTI_CUT_BENDERS_DECOMPOSITION",
            "identifier_preserved_without_invented_expansion": True,
            "equivalence_tolerance": 0.001,
            "ambiguity": False,
        },
        "V28_binding_replacements": {
            "RC_MQT": "V27_FINAL_LIGHTGBM_DECISION",
            "beta_AIDC": "V22SR1_ABSOLUTE_12_SITE_OPERATING_LOAD_AUTHORITY",
            "constant_PUE_main": "V24T_C1_WEATHER_AND_LOAD_DEPENDENT_QUASISTATIC_PUE",
            "solver_threads": "V28_FIXED_THREADS_4",
        },
        "unresolved_authorities": unresolved,
    }
    conflict = {
        "artifact_id": "V28_AUTHORITY_CONFLICT_AUDIT_V1",
        "status": "PASS_FAIL_CLOSED_CONFLICTS_RESOLVED" if not unresolved else "FAIL",
        "conflicts": [
            {
                "id": "C01_LEGACY_RC_MQT_INPUT_BINDING",
                "source": AUTHORITIES["final_15_minute_96_slot_formulation"],
                "resolution": "retain formulation; replace forecast binding with frozen LightGBM mean/Q50/Q90 authority",
            },
            {
                "id": "C02_LEGACY_BETA_AIDC_SCALE",
                "source": AUTHORITIES["final_15_minute_96_slot_formulation"],
                "resolution": "retain equations; remove beta scale calls and bind V22SR1 absolute operating-load scale",
            },
            {
                "id": "C03_CONSTANT_PUE_AS_OLD_MAIN",
                "source": AUTHORITIES["final_15_minute_96_slot_formulation"],
                "resolution": "C0 remains sensitivity only; C1 is V28 primary planning and evaluation thermal authority",
            },
            {
                "id": "C04_V24T_C2_PRESENT_BUT_REJECTED",
                "source": "V24T branch",
                "resolution": "import for historical preservation only; production import graph rejects dynamic_state/C2",
            },
            {
                "id": "C05_V16_3_THREADS_1",
                "source": "dayahead/v16_3_decomposition_executor.py configure_model",
                "resolution": "historical module remains immutable; V28 runtime adapter enforces Threads=4",
            },
        ],
        "legacy_final_binding_rules": {
            "event_trigger": False,
            "local_repair": False,
            "rolling_MPC": False,
            "5_minute_control": False,
            "representative_weeks": False,
            "M1_M2_M3_M4": False,
            "legacy_1_208_MW_stress_scale": False,
            "RC_MQT": False,
            "constant_PUE_only_main": False,
        },
        "unresolved": unresolved,
    }
    atomic_json(OUT / "V28_LINEAGE_RESOLUTION.json", lineage)
    atomic_json(OUT / "V28_AUTHORITY_CONFLICT_AUDIT.json", conflict)


if __name__ == "__main__":
    main()
