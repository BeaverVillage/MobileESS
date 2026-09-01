"""Historical 2026-08-28 AIDC-HOLD finalizer; disabled under V16."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .authority import CURRENT_FROZEN_DIMENSIONS, authority_fingerprint, sha256_file
from .science_firewall import CURRENT_AIDC_GATE, UNRESOLVED_DEPENDENCIES


DOCUMENT_SHA256 = "14a0514d8b3decc4f302536ff93d54ad810eb045bc7cb76b6088949fef4b64ba"
PARENT_SHA = "94b6d320d524ea6ef76ba324f91cb820e8e48004"
BRANCH = "codex/dayahead-aidc-joint-v1"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(("git", "-C", str(repo), *args), text=True).strip()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _changed_files(repo: Path) -> list[str]:
    tracked = _git(repo, "diff", "--name-only").splitlines()
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(filter(None, tracked + untracked)))


def _traceability() -> list[tuple[str, str, str, str]]:
    return [
        ("C.Dynamic dimensions", "dayahead/authority.py", "DimensionAuthority", "test_current_frozen_dimension_authority_is_exactly_12_by_48; test_alternative_10_by_40_fixture_requires_no_source_edit"),
        ("C.Production fixture rejection", "dayahead/authority.py", "DimensionAuthority.validate", "test_non_scientific_fixture_is_rejected_by_production_loader"),
        ("C.Master runtime axes", "dayahead/master.py", "build_master_structure", "test_master_indexes_follow_runtime_authority_dimensions"),
        ("D.Role separation", "dayahead/mapping_authority.py", "TrafficNode; MappingAuthority", "test_traffic_roles_are_independent_and_same_node_can_hold_both"),
        ("E.SCATS DST", "dayahead/traffic_da.py", "localize_scats_time", "test_scats_dst_fall_back_fold_maps_to_two_distinct_fixed_aest_times; test_scats_dst_spring_forward_nonexistent_time_fails_closed"),
        ("E.SCATS aggregation/audit", "dayahead/traffic_da.py", "aggregate_scats_15min", "test_scats_aggregation_is_deterministic_and_audits_duplicates"),
        ("E.Route 96 quantiles/Safe ETA", "dayahead/traffic_da.py", "RouteForecast.validate", "test_route_forecast_has_ordered_96_slot_safe_interface"),
        ("E.Namespace separation", "dayahead/traffic_da.py", "assert_separate_namespaces", "test_forecast_and_actual_namespaces_cannot_collapse"),
        ("F.96-slot/cutoff/vintage", "dayahead/input_contract.py", "operating_axis; issuance_cutoff; select_latest_complete_vintage", "test_exact_96_slot_fixed_aest_axis_and_cutoff; test_latest_complete_product_vintage_is_selected_without_slot_mixing"),
        ("F.Resolution conservation", "dayahead/input_contract.py", "pwc_30_to_15; average_5_to_15", "test_resolution_mappings_preserve_energy"),
        ("G.MESS P/Q/SOC/terminal", "dayahead/mess_physics.py", "validate_trajectory", "test_mess_soc_recursion_and_exact_terminal_energy; test_transit_and_connection_delay_force_p_q_zero"),
        ("G.Unique occupancy", "dayahead/mess_physics.py", "validate_occupancy", "test_mess_cannot_clone_location"),
        ("G.16-face PCS", "dayahead/mess_physics.py", "pcs_inner_polygon_satisfied; audit_pcs_exact_norm", "test_16_face_pcs_polygon_is_strictly_inside_exact_circle"),
        ("H.Mobility 5-to-15 SUM", "dayahead/mobility_energy_da.py", "MobilityEnergyProfiles.aggregate", "test_mobility_energy_5_to_15_sum_preserves_signed_total_and_hash"),
        ("H.No future regen pre-credit", "dayahead/mobility_energy_da.py", "departure_energy_required; assert_departure_feasible", "test_future_regeneration_is_not_precredited_at_departure"),
        ("I.Squared voltage/masks", "dayahead/grid_lp.py", "validate_squared_voltage; phase_mask_metrics", "test_squared_voltage_bounds_and_round_trip; test_absent_phases_are_excluded_from_reducers"),
        ("I.Phase-aware LinDistFlow", "dayahead/grid_lp.py", "PhaseAwareGridLPFactory", "test_phase_aware_lindistflow_factory_has_explicit_master_registry_and_pi_cut"),
        ("J.Real Pi cut", "dayahead/grid_lp.py", "CapacityGridLPFactory.solve", "test_real_gurobi_pi_produces_valid_sampled_optimality_cut"),
        ("J.Real Farkas ray", "dayahead/grid_lp.py", "CapacityGridLPFactory.solve", "test_real_gurobi_farkas_ray_and_cut_exclude_infeasible_incumbent"),
        ("K.Standard/CL-MC selection", "dayahead/benders.py", "cuts_for_iteration; critical_times", "test_standard_bd_selects_only_worst_time_optimality_cut; test_cl_mc_bd_selects_all_critical_times"),
        ("K.Bounds/certificate", "dayahead/benders.py", "BoundState.update; termination_status", "test_lb_uses_objbound_and_ub_waits_for_all_feasible; test_gap_certificate_and_time_limit_status"),
        ("L.Scientific execution blocker", "dayahead/master.py", "build_master_structure", "test_scientific_master_fails_closed_on_aidc_hold"),
        ("M.OpenDSS immutable 96 QSTS", "dayahead/opendss_qsts.py", "run_qsts", "test_opendss_96_slot_interface_masks_phases_and_keeps_schedule_immutable"),
        ("N.Result manifest", "dayahead/result_schema.py", "ResultManifest.validate; write_artifact", "test_result_manifest_production_rejects_fixture_dimensions"),
        ("O.Science firewall", "dayahead/science_firewall.py", "AuthorityGate", "test_current_aidc_gate_lists_all_four_unresolved_dependencies_without_fallback"),
        ("O.Forbidden fallback rejection", "dayahead/science_firewall.py", "reject_aidc_fallback", "test_every_forbidden_aidc_synthetic_or_imputation_fallback_is_rejected"),
    ]


def materialize(repo: Path) -> None:
    raise RuntimeError("HISTORICAL_20260828_HOLD_FINALIZER_DISABLED_UNDER_V16")
    out = repo / "dayahead" / "artifacts" / "today"
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    head = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "branch", "--show-current")
    if head != PARENT_SHA or branch != BRANCH:
        raise RuntimeError("repository identity changed since today's C0 snapshot")
    blocker = {
        "authority_id": "TODAY_AIDC_BLOCKER_REPORT_V1",
        "generated_at_utc": now,
        "status": "WAITING_AIDC_AUTHORITY",
        "synthetic_fallback_used": False,
        "unresolved": [
            {"dependency": "total-IT P_NF authority", "blocker": "WAITING_AIDC_P_NF_AUTHORITY"},
            {"dependency": "final P/G/W label lineage", "blocker": "WAITING_AIDC_LABEL_ALIGNMENT"},
            {"dependency": "final service/slack/deadline authority", "blocker": "WAITING_AIDC_SERVICE_CONTRACT"},
            {"dependency": "final 10-vs-12 AIDC spatial authority", "blocker": "WAITING_AIDC_SPATIAL_AUTHORITY"},
        ],
        "preserved_c2_failures": ["FAIL_AIDC_JOINT_LABEL_ALIGNMENT", "FAIL_AIDC_P_LABEL"],
    }
    _write_json(out / "TODAY_AIDC_BLOCKER_REPORT.json", blocker)
    authority = {
        "authority_id": "TODAY_IMPLEMENTATION_AUTHORITY_V1",
        "generated_at_utc": now,
        "repository": "BeaverVillage/MobileESS",
        "parent_sha": PARENT_SHA,
        "head_sha": head,
        "branch": branch,
        "working_tree_committed": False,
        "final_precode_freeze": {"filename": "MobileESS_AIDC_DayAhead_ML_Optimization_FINAL_PRECODE_FREEZE_Codex_Handoff_20260828_IMPLEMENTATION_READY_FINAL_FROZEN.docx", "sha256": DOCUMENT_SHA256},
        "authority_fingerprint": authority_fingerprint(),
        "aidc_scientific_status": "HOLD",
        "c2_status": "FAIL_PRESERVED",
        "current_frozen_aidc_mapping": CURRENT_FROZEN_DIMENSIONS.to_dict(),
        "current_frozen_mapping_preserved": True,
        "dimension_parameterization": {"status": "IMPLEMENTED", "production_default": "12_AIDC_48_LOGICAL_RACK_POOLS", "alternative_fixture": "10_AIDC_40_RACKS_NON_SCIENTIFIC_ONLY"},
        "production_gate": CURRENT_AIDC_GATE.status(),
        "scientific_runs_executed": [],
    }
    _write_json(out / "TODAY_IMPLEMENTATION_AUTHORITY.json", authority)
    tests = {
        "authority_id": "TODAY_TEST_REPORT_V1",
        "generated_at_utc": now,
        "overall_status": "ENGINEERING_PASS_WITH_3_PREEXISTING_ENVIRONMENTAL_FULL_SUITE_FAILURES",
        "scientific_solver_equivalence_claimed": False,
        "runtime": {
            "cwd": str(repo),
            "python": r"C:\Users\kjw39\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
            "PYTHONPATH": str(repo.parent / "tmp" / "python_deps") + ";" + str(repo),
        },
        "commands": [
            {"command": "python -m pytest -q tests/dayahead", "classification": "NON_SCIENTIFIC_ENGINEERING_TEST", "result": "PASS", "summary": "54 passed"},
            {"command": "python -m pytest -q tests/dayahead tests/test_pfr_ai_training.py tests/test_pfr_power.py tests/test_pfr_methods.py tests/test_git_identity.py", "classification": "MIXED_EXISTING_REGRESSION_AND_NON_SCIENTIFIC_ENGINEERING", "result": "PASS", "summary": "94 passed, 71 subtests passed"},
            {"command": "python -m pytest -q tests", "classification": "FULL_REPOSITORY_REGRESSION", "result": "FAIL", "summary": "406 passed, 4 skipped, 84 subtests passed, 3 failed", "failures": [
                {"test": "tests/test_pfr_mess_energy_recovery.py::test_joint_projection_restores_feasibility_across_multiple_trust_regions", "introduced_today": False, "classification": "PRE_EXISTING_GUROBI_13_0_3_WINDOWS_BEHAVIOR", "blocks_tomorrow_aidc_integration": False},
                {"test": "tests/test_shared_exact_source_preparation.py::test_exact_sources_are_prepared_once_and_reused_by_day_workers", "introduced_today": False, "classification": "WINDOWS_MISSING_POSIX_FCNTL", "blocks_tomorrow_aidc_integration": False},
                {"test": "tests/test_shared_exact_source_preparation.py::test_exact_source_cache_is_invalidated_by_source_identity", "introduced_today": False, "classification": "WINDOWS_MISSING_POSIX_FCNTL", "blocks_tomorrow_aidc_integration": False},
            ]},
            {"command": "python -m compileall -q dayahead", "classification": "STATIC_ENGINEERING_CHECK", "result": "PASS"},
            {"command": "git diff --check", "classification": "STATIC_ENGINEERING_CHECK", "result": "PASS"},
            {"command": "python -m dayahead.cli aidc-status", "classification": "SCIENTIFIC_FAIL_CLOSED_GATE", "result": "EXPECTED_EXIT_2", "summary": "WAITING_AIDC_AUTHORITY; four unresolved dependencies; no fallback"},
        ],
        "scientific_B0_B3_runs": 0,
        "scientific_opendss_runs": 0,
    }
    _write_json(out / "TODAY_TEST_REPORT.json", tests)
    commands = r"""#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN='C:/Users/kjw39/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
REPO='C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/github_MobileESS_march_validity_fix'
export PYTHONPATH='C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/tmp/python_deps;C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/github_MobileESS_march_validity_fix'
cd "$REPO"

# NON_SCIENTIFIC_ENGINEERING_TEST
"$PYTHON_BIN" -m pytest -q tests/dayahead

# MIXED_EXISTING_REGRESSION_AND_NON_SCIENTIFIC_ENGINEERING
"$PYTHON_BIN" -m pytest -q tests/dayahead tests/test_pfr_ai_training.py tests/test_pfr_power.py tests/test_pfr_methods.py tests/test_git_identity.py

# FULL_REPOSITORY_REGRESSION (known Windows/Gurobi failures are reported, never hidden)
"$PYTHON_BIN" -m pytest -q tests

# STATIC_ENGINEERING_CHECKS
"$PYTHON_BIN" -m compileall -q dayahead
git diff --check

# SCIENTIFIC_FAIL_CLOSED_GATE (expected exit code 2 while AIDC authority is HOLD)
"$PYTHON_BIN" -m dayahead.cli aidc-status
"""
    _write_text(out / "TODAY_TEST_COMMANDS.sh", commands)
    trace_path = out / "TODAY_PRECODE_TO_CODE_TRACEABILITY.csv"
    with trace_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("requirement", "source_file", "function_or_class", "test"))
        writer.writerows(_traceability())
    changed_before = _changed_files(repo)
    report = f"""# CODEX Today AIDC-HOLD Implementation Report

## Repository snapshot

- Repository: BeaverVillage/MobileESS
- Parent SHA: `{PARENT_SHA}`
- Final HEAD SHA: `{head}` (implementation remains an uncommitted working-tree change)
- Branch: `{branch}`
- Relevant open PR: #9, `codex/march-validity-fixes` at `{PARENT_SHA}`
- Final Pre-Code Freeze SHA-256: `{DOCUMENT_SHA256}`

## Implemented scope

Implemented AIDC-independent Day-Ahead infrastructure: runtime-driven AIDC/Rack axes; traffic-node/AIDC-anchor/MESS-service role separation; fixed-AEST D-1 traffic and input interfaces; MESS P/Q/SOC/mobility physics; Safe mobility-energy aggregation; phase-aware lossless LinDistFlow with u080-only hard limits, phase masks, explicit Gurobi rows, Pi and Farkas interfaces; Standard BD and CL-MC-BD cut selection and certified LB/UB bookkeeping; dimensioned Master/reference interfaces; immutable 96-slot OpenDSS QSTS orchestration; result namespaces/manifests/SHA utilities; and an explicit science firewall.

## Science invariants preserved

- AIDC means AI Data Center in new paper-facing text.
- C2 remains `FAIL` with `FAIL_AIDC_JOINT_LABEL_ALIGNMENT` and `FAIL_AIDC_P_LABEL`.
- The current 12 AIDC x 4 logical Rack pool mapping remains the only frozen scientific mapping.
- The 10/40 mapping exists only under `tests/fixtures/non_scientific/` with `scientific_eligible=false` and is rejected by production loaders.
- No P/G/W, P^NF, GPU occupancy, deadline/slack, scientific schedule, scientific B0-B3 result, AIDC ML output, or scientific OpenDSS result was fabricated or executed.
- Any production path that needs unresolved AIDC science returns `WAITING_AIDC_AUTHORITY` with dependency-specific blockers.
- Raw authority files were not moved, renamed, or overwritten.

## Explicitly deferred AIDC decisions

1. Source-backed total-IT non-flexible power P^NF.
2. Final joint P/G/W label lineage and temporal alignment.
3. Final service/slack/deadline contract.
4. Future 10-versus-current-12 AIDC spatial authority.
5. AIDC ML/HPO/cohort/split/refit/forecast execution.
6. Scientific B0-B3, production solvers, AIDC OpenDSS, and realized AIDC replay.

## New modules and principal interfaces

`DimensionAuthority`, `MappingAuthority`, `RouteForecast`, `MobilityEnergyProfiles`, `validate_trajectory`, `PhaseAwareGridLPFactory`, `CapacityGridLPFactory`, `CutRegistry`, `BoundState`, `build_master_structure`, `build_reference_schedule`, `run_qsts`, `ResultManifest`, and `AuthorityGate`.

## Test result

- Day-Ahead: 54 passed.
- Focused regression: 94 passed plus 71 subtests.
- Full `tests/`: 406 passed, 4 skipped, 84 subtests passed, 3 failed.
- The three full-suite failures are pre-existing/environment-specific: two require POSIX `fcntl`; one is the existing Windows/Gurobi 13.0.3 trust-region behavior. No failing test is under `tests/dayahead/`, and none blocks later AIDC authority integration.
- All solver/fixture conclusions are labeled `NON_SCIENTIFIC_ENGINEERING_TEST`; no scientific Solver Equivalence PASS is claimed.

## Known blockers and limitations

Scientific execution remains blocked by the four authority items listed above. The OpenDSS module supplies clean-engine orchestration and KPI/mask contracts through an injected engine adapter; it does not generate prohibited scientific AIDC loads or results. Parallel LP execution is intentionally not enabled; the correctness-first 96-LP interface is complete. The working tree is not committed, so Final HEAD equals Parent SHA.

## Changed files

See `TODAY_CHANGED_FILES.txt` for the exact machine-readable list and `TODAY_PRECODE_TO_CODE_TRACEABILITY.csv` for requirement-to-code-to-test mapping.
"""
    _write_text(out / "CODEX_TODAY_AIDC_HOLD_IMPLEMENTATION_REPORT.md", report)
    changed = _changed_files(repo)
    _write_text(out / "TODAY_CHANGED_FILES.txt", "\n".join(changed) + "\n")
    checksum_path = out / "TODAY_SHA256SUMS.txt"
    files = [repo / name for name in _changed_files(repo) if name != checksum_path.relative_to(repo).as_posix()]
    lines = [f"{sha256_file(path)}  {path.relative_to(repo).as_posix()}" for path in files if path.is_file()]
    _write_text(checksum_path, "\n".join(sorted(lines)) + "\n")
    # Refresh changed-file inventory after the checksum artifact exists.
    _write_text(out / "TODAY_CHANGED_FILES.txt", "\n".join(_changed_files(repo)) + "\n")
    # Recompute once more because TODAY_CHANGED_FILES now contains the checksum
    # filename; the checksum file itself remains intentionally self-excluded.
    files = [repo / name for name in _changed_files(repo) if name != checksum_path.relative_to(repo).as_posix()]
    lines = [f"{sha256_file(path)}  {path.relative_to(repo).as_posix()}" for path in files if path.is_file()]
    _write_text(checksum_path, "\n".join(sorted(lines)) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[1]
    materialize(repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
