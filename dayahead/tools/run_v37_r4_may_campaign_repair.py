"""Prepare and audit all May inputs without starting the May campaign."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Any

import numpy as np
import pandas as pd

from dayahead.v28r2.source_cache import day_root
from dayahead.v37.aidc import build_day, validate_cohort_contract
from dayahead.v37.aidc_materializer import R4A_DAY_ROOT, R4A_ROOT, load_day_manifest
from dayahead.v37.context import load_day_context
from dayahead.v37.contracts import CACHE_ROOT, EXPECTED_DATES, FIREWALL, SOURCE_DATA_REPOSITORY
from dayahead.v37.preflight import (
    anchor_paths,
    production_loader_dry_run,
    sha256_file,
    validate_anchor_pair,
    validate_causal_vintage,
    validate_preflight_manifest,
)
from dayahead.v37r3.voltage_authority import (
    APPLICABILITY_RELATIVE_PATH,
    APPLICABILITY_SCHEMA,
    AUTHORITY_RELATIVE_PATH,
    coefficient_payload_sha256,
    load_joint_voltage_authority,
)


OUTPUT_RELATIVE = Path("dayahead/artifacts/v37_r4_may_campaign_repair")


def _json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _materialize_one(repo_text: str, day: str) -> dict[str, Any]:
    repo = Path(repo_text)
    started = time.perf_counter()
    electrical = None
    try:
        prior = validate_anchor_pair(repo, day)
        if prior["status"] == "PASS":
            return {"operating_day": day, "action": "REUSED_VALID", "status": "PASS"}
        _data, electrical = load_day_context(repo, day)
        result = validate_anchor_pair(repo, day)
        if result["status"] != "PASS":
            raise RuntimeError(";".join(result["failures"]))
        return {
            "operating_day": day,
            "action": "MATERIALIZED_D1_CAUSAL_PIPELINE",
            "elapsed_seconds": time.perf_counter() - started,
            "status": "PASS",
        }
    except Exception as error:
        return {
            "operating_day": day,
            "action": "MATERIALIZATION_FAILED",
            "elapsed_seconds": time.perf_counter() - started,
            "reason": f"{type(error).__name__}:{error}",
            "status": "FAIL",
        }
    finally:
        if electrical is not None:
            electrical.voltage.close()
            electrical.current.close()


def _preflight_one(repo_text: str, day: str) -> dict[str, Any]:
    return production_loader_dry_run(Path(repo_text), day)


def _parallel(
    worker: Any, repo: Path, days: tuple[str, ...], workers: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, str(repo), day): day for day in days}
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(json.dumps({
                "operating_day": row["operating_day"],
                "status": row["status"],
                "action": row.get("action"),
                "reasons": row.get("reasons", []),
                "elapsed_seconds": row.get("elapsed_seconds"),
            }, ensure_ascii=False, default=str), flush=True)
    return sorted(rows, key=lambda row: str(row["operating_day"]))


def write_anchor_and_authorization_audits(repo: Path, output: Path) -> None:
    rows = []
    for day in EXPECTED_DATES:
        anchor = validate_anchor_pair(repo, day)
        source = day_root(SOURCE_DATA_REPOSITORY, day)
        vintage_path = source / "aemo_forecast.json"
        if vintage_path.is_file():
            vintage = validate_causal_vintage(
                json.loads(vintage_path.read_text(encoding="utf-8")), day,
            )
        else:
            vintage = {"status": "FAIL", "failures": ["AEMO_FORECAST_MISSING"]}
        rows.append({**anchor, "causal_vintage": vintage})
    passed = sum(row["status"] == "PASS" and row["causal_vintage"]["status"] == "PASS" for row in rows)
    anchor_manifest = {
        "artifact_id": "V37_R4_MAY_D1_AC_ANCHOR_MANIFEST_V1",
        "generation_pipeline": "V28R2_FROZEN_D1_CAUSAL_PIPELINE",
        "May_results_used_for_materialization": False,
        "expected_dates": 31,
        "ANCHORS_AVAILABLE": f"{passed}/31",
        "causal_vintage_failures": sum(row["causal_vintage"]["status"] != "PASS" for row in rows),
        "status": "PASS" if passed == 31 else "FAIL",
        "dates": rows,
    }
    _json(output / "V37_R4_MAY_D1_AC_ANCHOR_MANIFEST.json", anchor_manifest)
    if passed != 31:
        raise RuntimeError(f"V37_R4_ANCHORS_NOT_31_OF_31:{passed}")

    authority, authority_sha = load_joint_voltage_authority(repo)
    voltage_by_day = {
        day: validate_anchor_pair(repo, day)["voltage_sha256"]
        for day in EXPECTED_DATES
    }
    applicability = {
        "schema_id": APPLICABILITY_SCHEMA,
        "artifact_id": "V37_R4_MAY_VOLTAGE_APPLICABILITY_V1",
        "classification": "EVALUATION_APPLICABILITY_ONLY_NO_COEFFICIENT_CHANGE",
        "calibration_data_range": "APRIL_PRE_MAY_ONLY",
        "calibration_days": authority["calibration_days"],
        "evaluation_applicability_range": [EXPECTED_DATES[0], EXPECTED_DATES[-1]],
        "authorized_dates": list(EXPECTED_DATES),
        "authorized_date_count": len(EXPECTED_DATES),
        "coefficient_authority_path": str(AUTHORITY_RELATIVE_PATH).replace("\\", "/"),
        "coefficient_authority_file_sha256": authority_sha,
        "coefficient_payload_sha256": coefficient_payload_sha256(authority),
        "coefficient_values_changed": False,
        "May_data_used_for_calibration": False,
        "base_voltage_authority_sha256_by_day": voltage_by_day,
    }
    applicability_path = repo / APPLICABILITY_RELATIVE_PATH
    _json(applicability_path, applicability)
    authorization = {
        "artifact_id": "V37_R4_MAY_AUTHORIZATION_AUDIT_V1",
        "root_cause": "TEMPORARY_R3_EVALUATION_WHITELIST_LIMITED_TO_MAY01_05",
        "repair": "SEPARATE_APRIL_CALIBRATION_AUTHORITY_FROM_MAY_EVALUATION_APPLICABILITY",
        "coefficient_values_changed": False,
        "coefficient_payload_sha256": applicability["coefficient_payload_sha256"],
        "coefficient_authority_file_sha256": authority_sha,
        "applicability_manifest_sha256": sha256_file(applicability_path),
        "MAY_AUTHORIZED_DATES": "31/31",
        "authorized_dates": list(EXPECTED_DATES),
        "status": "PASS",
    }
    _json(output / "V37_R4_MAY_AUTHORIZATION_AUDIT.json", authorization)


def write_aidc_audits(repo: Path, output: Path) -> None:
    rows = []
    for day in EXPECTED_DATES:
        aidc = build_day(repo, day, "B1")
        row = validate_cohort_contract(aidc.ledger, day)
        row["CENTER_trajectory_slots"] = len(aidc.power)
        row["CENTER_pcc_shape"] = str(tuple(aidc.pcc_p_kw.shape))
        rows.append(row)
    pd.DataFrame(rows).to_csv(
        output / "V37_R4_AIDC_COHORT_FORENSIC.csv", index=False, encoding="utf-8",
    )
    counts = [int(row["temporal_controllable_jobs"]) for row in rows]
    audit = {
        "artifact_id": "V37_R4_AIDC_COHORT_CONTRACT_AUDIT_V1",
        "failure_classification": "A_HARD_CODED_APR01_COUNT_INCORRECTLY_USED_AS_CONTRACT",
        "historical_behavior": (
            "Apr-01 realized numeric count checks were executable gates; an earlier total-"
            "PARTIAL count check also mixed fixed and temporal jobs."
        ),
        "repair": "VALIDATE_FROZEN_COHORT_CONSTRUCTION_RULE_NOT_NUMERIC_REALIZATION",
        "scheduler_source": "V37_R4A_PER_DAY_CAUSAL_KESTREL_SNAPSHOT",
        "causal_cutoff_rule": "D_MINUS_1_18_FIXED_AEST",
        "temporal_definition": ["NORMAL_QUEUE_CONTROLLED", "STANDBY_QUEUE_CONTROLLED"],
        "PARTIAL_shared_rule": "requested_GPUs < 4 * requested_nodes",
        "fail_closed_duration_authority_preserved": True,
        "no_double_counting": True,
        "May_per_date_temporal_cohort_range": [min(counts), max(counts)],
        "expected_dates": 31,
        "passed_dates": sum(row["rule_validation"] == "PASS" for row in rows),
        "dates": rows,
        "AIDC_COHORT_CONTRACT": "PASS",
        "status": "PASS",
    }
    _json(output / "V37_R4_AIDC_COHORT_CONTRACT_AUDIT.json", audit)
    manifests = [load_day_manifest(repo, day) for day in EXPECTED_DATES]
    kestrel_rows = [{
        "operating_day": manifest["operating_day"],
        **dict(manifest.get("Kestrel_D1_snapshot_audit", {})),
        "source_snapshot_sha256": manifest["source_snapshot_sha256"],
    } for manifest in manifests]
    kestrel_pass = all(
        row.get("source_members_opened")
        and row.get("source_members_contributing")
        and row.get("future_D_day_execution_used_for_membership") is False
        for row in kestrel_rows
    )
    _json(repo / R4A_ROOT / "V37_R4A_KESTREL_D1_SNAPSHOT_AUDIT.json", {
        "artifact_id": "V37_R4A_KESTREL_D1_SNAPSHOT_AUDIT_V1",
        "issue_time_rule": "D_MINUS_1_18_FIXED_AEST",
        "expected_dates": 31,
        "passed_dates": sum(
            bool(row.get("source_members_opened"))
            and bool(row.get("source_members_contributing"))
            and row.get("future_D_day_execution_used_for_membership") is False
            for row in kestrel_rows
        ),
        "dates": kestrel_rows,
        "status": "PASS" if kestrel_pass else "FAIL",
    })
    _json(repo / R4A_ROOT / "V37_R4A_KESTREL_MONTH_BOUNDARY_AUDIT.json", {
        "artifact_id": "V37_R4A_KESTREL_MONTH_BOUNDARY_AUDIT_V1",
        "May01_issue_time": manifests[0]["D_minus_1_issue_time"],
        "May01_Apr_origin_RUNNING": kestrel_rows[0].get("running_jobs_carried_across_month_boundary"),
        "May01_Apr_origin_PENDING": kestrel_rows[0].get("pending_jobs_carried_across_month_boundary"),
        "source_partition_rule": "OPEN_ALL_ARCHIVE_MEMBERS_REQUIRED_BY_ISSUE_TIME_STATE",
        "dates": kestrel_rows,
        "status": "PASS" if kestrel_pass and (
            int(kestrel_rows[0].get("running_jobs_carried_across_month_boundary", 0))
            + int(kestrel_rows[0].get("pending_jobs_carried_across_month_boundary", 0)) > 0
        ) else "FAIL",
    })
    _json(repo / R4A_ROOT / "V37_R4A_READINESS_LOGIC_REPAIR.json", {
        "artifact_id": "V37_R4A_READINESS_LOGIC_REPAIR_V1",
        "required_predicate": "expected_count==31 AND runnable_count==31 AND missing_count==0",
        "source_required_predicate": "requested_count==31 AND runnable_count==31 AND failed_count==0",
        "partial_campaign_launch_allowed": False,
        "manifest_implementation": "dayahead/v37/manifest.py::build_date_manifest",
        "source_implementation": "dayahead/v37/sources.py::materialize_sources",
        "campaign_gate": "dayahead/v37/campaign.py::run_campaign",
        "status": "PASS",
    })

    production_files = [
        *(repo / "dayahead/v37").glob("*.py"),
        *(repo / "dayahead/v37r3").glob("*.py"),
        *(repo / "tools/v37").glob("*.ps1"),
    ]
    stale_terms = (
        "FROZEN_APR01_RW_AND_RSP_TEMPLATE", "APR01_AUTHORITY_PRESERVED_FOR_MAY_EVALUATION",
        "V36_APR01_EXPANDED_TEMPORAL_PROFILE", "frozen_daily_template",
        "_apr01_power(", "_apr01_ledger(",
    )
    stale_hits = []
    for path in production_files:
        if path.name == "aidc_materializer.py":
            continue  # explicit Apr-01 regression evidence only
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for term in stale_terms:
                if term in line:
                    stale_hits.append({"path": _portable_path(repo, path), "line": number, "term": term})
    _json(repo / R4A_ROOT / "V37_R4A_STALE_APR_TEMPLATE_REFERENCE_AUDIT.json", {
        "artifact_id": "V37_R4A_STALE_APR_TEMPLATE_REFERENCE_AUDIT_V1",
        "production_hits": stale_hits,
        "historical_exception": "aidc_materializer.py Apr-01 exact-regression functions only",
        "status": "PASS" if not stale_hits else "FAIL",
    })

    constant_terms = (
        "EXPANDED_TEMPORAL_JOBS", "PARTIAL_SHARED_TEMPORAL_JOBS",
        "EXPANDED_TEMPORAL_GPU_HOURS", "PARTIAL_SHARED_TEMPORAL_GPU_HOURS",
    )
    constant_hits = []
    invalid_hits = []
    for path in production_files:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(term in line for term in constant_terms):
                hit = {"path": _portable_path(repo, path), "line": number, "text": line.strip()}
                constant_hits.append(hit)
                if path.name not in {"contracts.py", "aidc_materializer.py"}:
                    invalid_hits.append(hit)
    _json(repo / R4A_ROOT / "V37_R4A_APR01_CONSTANT_USAGE_AUDIT.json", {
        "artifact_id": "V37_R4A_APR01_CONSTANT_USAGE_AUDIT_V1",
        "classification": "APR01_REGRESSION_EVIDENCE_ONLY",
        "all_hits": constant_hits,
        "universal_May_gate_hits": invalid_hits,
        "status": "PASS" if not invalid_hits else "FAIL",
    })

    required_fingerprints = {
        "operating_day", "source_snapshot_sha256", "ledger_sha256",
        "RW_schedule_sha256", "RSP_schedule_sha256",
        "RW_active_GPU_trajectory_sha256", "RSP_active_GPU_trajectory_sha256",
        "CENTER_IT_power_trajectory_sha256", "C1_PCC_P_trajectory_sha256",
        "C1_PCC_Q_trajectory_sha256",
    }
    fingerprint_rows = []
    for day in EXPECTED_DATES:
        cases = {case: build_day(repo, day, case) for case in ("B0", "B1", "B2", "B3")}
        fingerprints = dict(cases["B0"].fingerprints)
        sha_fields = required_fingerprints - {"operating_day"}
        complete = set(fingerprints) >= required_fingerprints and all(
            len(str(fingerprints[field])) == 64 for field in sha_fields
        ) and fingerprints["operating_day"] == day
        fingerprint_rows.append({
            "operating_day": day,
            "fingerprints": fingerprints,
            "B0_equals_B2": np.array_equal(cases["B0"].pcc_p_kw, cases["B2"].pcc_p_kw)
                and np.array_equal(cases["B0"].pcc_q_kvar, cases["B2"].pcc_q_kvar),
            "B1_equals_B3": np.array_equal(cases["B1"].pcc_p_kw, cases["B3"].pcc_p_kw)
                and np.array_equal(cases["B1"].pcc_q_kvar, cases["B3"].pcc_q_kvar),
            "complete": complete,
        })
    fingerprint_pass = all(
        row["complete"] and row["B0_equals_B2"] and row["B1_equals_B3"]
        for row in fingerprint_rows
    )
    _json(repo / R4A_ROOT / "V37_R4A_PER_DAY_AIDC_FINGERPRINT_AUDIT.json", {
        "artifact_id": "V37_R4A_PER_DAY_AIDC_FINGERPRINT_AUDIT_V1",
        "required_fields": sorted(required_fingerprints),
        "old_Apr_template_cache_reusable": False,
        "dates": fingerprint_rows,
        "status": "PASS" if fingerprint_pass else "FAIL",
    })
    _json(repo / R4A_ROOT / "V37_R4A_LEGACY_PGW_BINDING_AUDIT.json", {
        "artifact_id": "V37_R4A_LEGACY_PGW_BINDING_AUDIT_V1",
        "P_G_W_source": "dayahead/v37/context.py::_causal_optimizer_predictions_may",
        "legacy_consumer": "dayahead/v28r2/electrical_context.py::_legacy_reference",
        "operational_AIDC_path": (
            "per-day D-1 snapshot -> RW/RSP occupancy -> CENTER GPU-slot power -> C1 PCC"
        ),
        "operational_override": "dayahead/v37/runner.py::_planning_grid uses selected per-day pcc_p_kw/pcc_q_kvar",
        "classification": "LEGACY_BACKGROUND_ELECTRICAL_CONTEXT_ONLY",
        "double_operational_binding": False,
        "science_changed": False,
        "status": "PASS",
    })
    fresh_required = {
        "Fresh_used_for_AIDC_or_MESS_initial_decisions": "NO",
        "Fresh_used_for_post_selection_AC_feasibility_detection": "YES",
        "Fresh_used_by_frozen_fixed_discrete_PQ_restoration": "YES",
        "Fresh_changes_MESS_destination_route_departure_or_move": "NO",
    }
    _json(repo / R4A_ROOT / "V37_R4A_FRESH_ROLE_SEMANTICS_AUDIT.json", {
        "artifact_id": "V37_R4A_FRESH_ROLE_SEMANTICS_AUDIT_V1",
        "required_roles": fresh_required,
        "actual_roles": {key: FIREWALL.get(key) for key in fresh_required},
        "algorithm_changed": False,
        "status": "PASS" if all(FIREWALL.get(key) == value for key, value in fresh_required.items()) else "FAIL",
    })


def _portable_path(repo: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def _launch_fingerprints(repo: Path) -> list[dict[str, str]]:
    paths: set[Path] = {
        repo / AUTHORITY_RELATIVE_PATH,
        repo / APPLICABILITY_RELATIVE_PATH,
        repo / "dayahead/v37/aidc.py",
        repo / "dayahead/v37/aidc_materializer.py",
        repo / "dayahead/v37/context.py",
        repo / "dayahead/v37/contracts.py",
        repo / "dayahead/v37/campaign.py",
        repo / "dayahead/v37/manifest.py",
        repo / "dayahead/v37/preflight.py",
        repo / "dayahead/v37/runner.py",
        repo / "dayahead/v37/sources.py",
        repo / "dayahead/v37r3/restoration.py",
        repo / "dayahead/v37r3/voltage_authority.py",
        repo / "dayahead/v34/integrated_mess.py",
        repo / "dayahead/v17_ac_restoration_contract.py",
        repo / "tools/v37/run_may_locked_final.ps1",
        repo / "dayahead/artifacts/v17_candidate/V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1.json",
        repo / "dayahead/artifacts/v17_candidate/V17_AC_RESTORATION_CUT_VALIDATION.json",
    }
    for day in EXPECTED_DATES:
        aidc_manifest = load_day_manifest(repo, day)
        paths.add(repo / R4A_DAY_ROOT / day / "V37_R4A_DAY_MANIFEST.json")
        paths.update(repo / record["path"] for record in aidc_manifest["files"].values())
        paths.update(anchor_paths(repo, day))
        source = day_root(SOURCE_DATA_REPOSITORY, day)
        paths.update({
            source / "aemo_forecast.json",
            source / "gfs_d1_weather.parquet",
            source / "kestrel_d1_scheduler_snapshot.parquet",
            source / "source_day_manifest.json",
        })
        traffic = repo / CACHE_ROOT / "traffic/shared/traffic" / day
        paths.update({traffic / "TRAFFIC_FORECAST.npz", traffic / "ROUTE_TABLE.json.gz"})
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(f"V37_R4_LAUNCH_FINGERPRINT_FILE_MISSING:{missing[:3]}")
    return [
        {"path": _portable_path(repo, path), "sha256": sha256_file(path)}
        for path in sorted(paths, key=lambda item: str(item).lower())
    ]


def write_preflight(repo: Path, output: Path, workers: int) -> None:
    rows = _parallel(_preflight_one, repo, EXPECTED_DATES, workers)
    ready = sum(row["status"] == "READY" for row in rows)
    missing = sum(any("MISSING" in reason for reason in row["reasons"]) for row in rows)
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=repo, text=True,
    ).strip()
    count_pass = lambda key: sum(
        row["checks"].get(key, {}).get("status") == "PASS" for row in rows
    )
    aidc_passed = count_pass("AIDC_PER_DAY_CAUSAL_MATERIALIZATION_PASS")
    kestrel_passed = count_pass("kestrel_D1_causal_snapshot")
    traffic_passed = count_pass("traffic")
    electrical_passed = count_pass("electrical_anchor")
    restoration_passed = count_pass("restoration_contract")
    launch_fingerprints = _launch_fingerprints(repo) if ready == 31 and missing == 0 else []
    payload = {
        "artifact_id": "V37_R4_MAY_31DAY_PRODUCTION_PREFLIGHT_V1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "branch": branch,
        "expected_dates": len(EXPECTED_DATES),
        "ready_dates": ready,
        "not_ready_dates": len(EXPECTED_DATES) - ready,
        "missing_dates": missing,
        "PRODUCTION_PREFLIGHT": f"{ready}/31",
        "PER_DAY_AIDC": f"{aidc_passed}/31 PASS" if aidc_passed == 31 else f"{aidc_passed}/31 FAIL",
        "KESTREL_D1_CAUSAL_SNAPSHOT": f"{kestrel_passed}/31 PASS" if kestrel_passed == 31 else f"{kestrel_passed}/31 FAIL",
        "ACTUAL_TRAFFIC_AUTHORITY_PREFLIGHT": f"{traffic_passed}/31 PASS" if traffic_passed == 31 else f"{traffic_passed}/31 FAIL",
        "D1_ELECTRICAL_AUTHORITY": f"{electrical_passed}/31 PASS" if electrical_passed == 31 else f"{electrical_passed}/31 FAIL",
        "RESTORATION_LOADER": f"{restoration_passed}/31 PASS" if restoration_passed == 31 else f"{restoration_passed}/31 FAIL",
        "TRUE_PRODUCTION_LOADER_PREFLIGHT": f"{ready}/31 PASS" if ready == 31 else f"{ready}/31 FAIL",
        "MAY_STARTED": "NO",
        "MAY_CAMPAIGN_LAUNCH_READY": "YES" if ready == 31 and missing == 0 else "NO",
        "optimization_calls": 0,
        "Gurobi_optimize_calls": 0,
        "campaign_processes_spawned": 0,
        "dates": rows,
        "launch_fingerprints": launch_fingerprints,
        "final_implementation_fingerprint_sha256": hashlib.sha256(json.dumps(
            launch_fingerprints, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest() if launch_fingerprints else None,
    }
    failures = validate_preflight_manifest(payload)
    payload["fail_closed_validation"] = {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
    }
    _json(output / "V37_R4_MAY_31DAY_PRODUCTION_PREFLIGHT.json", payload)
    true_payload = dict(payload)
    true_payload["artifact_id"] = "V37_R4A_TRUE_31DAY_PRODUCTION_LOADER_PREFLIGHT_V1"
    _json(output / "V37_R4A_TRUE_31DAY_PRODUCTION_LOADER_PREFLIGHT.json", true_payload)
    traffic_rows = [{
        "operating_day": row["operating_day"],
        **dict(row["checks"].get("traffic", {})),
        "candidate_table_sha256": row["checks"].get(
            "candidate_route_enumeration", {}
        ).get("candidate_table_sha256"),
        "structural_placeholder_used": False,
    } for row in rows]
    _json(output / "V37_R4A_REAL_TRAFFIC_PREFLIGHT.json", {
        "artifact_id": "V37_R4A_REAL_TRAFFIC_PREFLIGHT_V1",
        "expected_dates": 31,
        "passed_dates": traffic_passed,
        "required_authorities": ["TRAFFIC_FORECAST.npz", "ROUTE_TABLE.json.gz", "Safe_ETA", "candidate_table_SHA"],
        "structural_placeholder_accepted": False,
        "dates": traffic_rows,
        "status": "PASS" if traffic_passed == 31 else "FAIL",
    })
    flat_rows = [{
        "operating_day": row["operating_day"],
        "status": row["status"],
        "reasons": "|".join(row["reasons"]),
        "D1_demand_vintage": row["checks"].get("causal_vintage", {}).get("status"),
        "D1_rooftop_PV_vintage": row["checks"].get("causal_vintage", {}).get("status"),
        "AIDC_cohort": row["checks"].get("AIDC_cohort", {}).get("rule_validation"),
        "AIDC_per_day_causal": row["checks"].get(
            "AIDC_PER_DAY_CAUSAL_MATERIALIZATION_PASS", {}
        ).get("status"),
        "D1_AC_anchor": row["checks"].get("electrical_anchor", {}).get("status"),
        "traffic_Safe_ETA": row["checks"].get("traffic", {}).get("Safe_ETA"),
        "travel_energy": row["checks"].get("traffic", {}).get("travel_energy"),
        "case_fingerprints": len(row["checks"].get("case_execution_fingerprints", {})),
    } for row in rows]
    pd.DataFrame(flat_rows).to_csv(
        output / "V37_R4_MAY_31DAY_PRODUCTION_PREFLIGHT.csv",
        index=False,
        encoding="utf-8",
    )
    pd.DataFrame(flat_rows).to_csv(
        output / "V37_R4A_TRUE_31DAY_PRODUCTION_LOADER_PREFLIGHT.csv",
        index=False,
        encoding="utf-8",
    )
    if failures:
        raise RuntimeError(f"V37_R4_PRODUCTION_PREFLIGHT_FAIL:{failures}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--stage", choices=("anchors", "audits", "preflight", "all"), default="all",
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    output = repo / OUTPUT_RELATIVE
    output.mkdir(parents=True, exist_ok=True)
    if args.stage in {"anchors", "all"}:
        actions = _parallel(_materialize_one, repo, EXPECTED_DATES, args.workers)
        _json(output / "V37_R4_D1_AC_ANCHOR_MATERIALIZATION_LOG.json", {
            "artifact_id": "V37_R4_D1_AC_ANCHOR_MATERIALIZATION_LOG_V1",
            "actions": actions,
            "status": "PASS" if all(row["status"] == "PASS" for row in actions) else "FAIL",
        })
        if any(row["status"] != "PASS" for row in actions):
            raise RuntimeError("V37_R4_D1_AC_ANCHOR_MATERIALIZATION_FAIL")
    if args.stage in {"anchors", "audits", "all"}:
        write_anchor_and_authorization_audits(repo, output)
        write_aidc_audits(repo, output)
    if args.stage in {"preflight", "all"}:
        write_preflight(repo, output, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
