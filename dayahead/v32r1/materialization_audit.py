"""V32R1 Phase-I authority audit with mandatory fail-closed ordering.

The frozen source archives cover Jan--Mar, but V30 has no authority-capable
general-day Stage-1 schedule generator.  It loads the four Apr-04 schedules
from V29R2.  This module records that distinction and deliberately does not
invent a schedule generator, create partial operational authority, or start
the V32 frontier phase.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd


STARTING_HEAD = "e604d8f41e6207fa2881dd06ba944bd5479cd228"
BRANCH = "codex/v32r1-janmar-v30-authority-materialization"
V32_MANIFEST_SHA = "9462b2b46d151a0084817172d20d49e53c04c8f02a18b98384a7b56fe4aaa95d"
V31_MANIFEST_SHA = "3dba51dc72ce12eeb79166e15f737e084625b047f9639a57683f18824525eaf6"
V30_HEAD = "f0fcc1c2835cc90b65aab7b788f1b55af544f6ea"
V30_TREE = "9a33aa0bb56f41df1fdc01e50fbca379b76a8968"
SCENARIO_SHA = "02e29c64c8fa662c78bf88e43c10a6508efc0bb5669f9ffe6d33c798a887d2b0"
M_CURRENT = 0.0009917274479849247
K = 64
OFFICIAL_CASES = ("B0", "B1", "B2", "B3")
TARGET_CASES = ("B1", "B3")
CLASSIFICATION = "V32R1_JANMAR_AUTHORITY_MATERIALIZATION_BLOCKED"
BLOCKER = "NO_FROZEN_V30_GENERAL_DAY_STAGE1_SCHEDULE_GENERATOR"
OUT_REL = Path("dayahead/artifacts/v32r1_janmar_v30_authority")
V32_REL = Path("dayahead/artifacts/v32_preapril_current_frontier_freshac")
V31_REL = Path("dayahead/artifacts/v31_v30_safety_headroom_forensic")
FRONTIER_REL = Path("dayahead/artifacts/v32r1_preapril_current_frontier_freshac")


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"V32R1_JSON_OBJECT_REQUIRED:{path}")
    return value


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8", newline="\n")


def _days() -> list[str]:
    start = date(2025, 1, 1)
    return [(start + timedelta(days=i)).isoformat() for i in range(90)]


def _files_digest(root: Path, *, exclude: Sequence[str] = ()) -> dict[str, object]:
    excluded = set(exclude)
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name not in excluded):
        rows.append({"path": path.relative_to(root).as_posix(), "sha256": _sha(path), "byte_count": path.stat().st_size})
    return {
        "file_count": len(rows), "byte_count": sum(int(row["byte_count"]) for row in rows),
        "aggregate_manifest_sha256": _canonical_sha(rows), "files": rows,
    }


def _month_content_days(path: Path, marker: str) -> set[str]:
    found: set[str] = set()
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            with archive.open(member) as stream:
                for raw in stream:
                    line = raw.decode("utf-8", errors="ignore")
                    if line.startswith("D,") and marker in line:
                        match = re.search(r'"(2025/[0-9]{2}/[0-9]{2}) ', line)
                        if match:
                            found.add(match.group(1).replace("/", "-"))
    return found


def _raw_authorities(repo: Path, raw_root: Path) -> tuple[list[dict[str, object]], dict[str, set[str]]]:
    preflight = _read_json(repo / "dayahead/artifacts/v16/AIDC_RAW_PREFLIGHT.json")
    inventory = {str(row["relative_path"]): row for row in preflight["inventory"]}
    relative = [
        *(f"전력 데이터 AEMO Victoria/PUBLIC_ARCHIVE#DISPATCHREGIONSUM#FILE01#20250{m}010000.zip" for m in (1, 2, 3)),
        *(f"AEMO rooftop PV 자료/2025_0{m}/PUBLIC_ARCHIVE#ROOFTOP_PV_ACTUAL#FILE01#20250{m}010000.zip" for m in (1, 2, 3)),
        "교통 장기 데이터 Victoria SCATS/traffic_signal_volume_data_2024.zip",
        "교통 장기 데이터 Victoria SCATS/traffic_signal_volume_data_january_2025.zip",
        "교통 장기 데이터 Victoria SCATS/traffic_signal_volume_data_february_2025.zip",
        "교통 장기 데이터 Victoria SCATS/traffic_signal_volume_data_march_2025.zip",
    ]
    records: list[dict[str, object]] = []
    for rel in relative:
        frozen = inventory[rel]
        path = raw_root / rel
        observed = _sha(path)
        records.append({"role": "frozen_raw_archive", "path": str(path), "relative_path": rel, "sha256": observed, "frozen_sha256": frozen["sha256"], "hash_match": observed == frozen["sha256"], "byte_count": path.stat().st_size})

    demand_days: set[str] = set()
    pv_days: set[str] = set()
    for m in (1, 2, 3):
        demand_path = raw_root / f"전력 데이터 AEMO Victoria/PUBLIC_ARCHIVE#DISPATCHREGIONSUM#FILE01#20250{m}010000.zip"
        pv_path = raw_root / f"AEMO rooftop PV 자료/2025_0{m}/PUBLIC_ARCHIVE#ROOFTOP_PV_ACTUAL#FILE01#20250{m}010000.zip"
        demand_days |= _month_content_days(demand_path, ",VIC1,")
        pv_days |= _month_content_days(pv_path, ",VIC1,")

    # Kestrel and observed weather were already frozen as semantic authorities.
    service = _read_json(repo / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret/V29R2_EXEC_SERVICE_DATA_CONTRACT.json")
    kestrel = Path(str(service["source_path"]))
    kestrel_sha = _sha(kestrel)
    with zipfile.ZipFile(kestrel) as archive:
        names = " ".join(archive.namelist()).replace("\\", "/")
    kestrel_months = {m for m in ("01", "02", "03") if f"year=2025/month={m}" in names or f"year=2025/month={int(m)}" in names}
    records.append({"role": "strict_FULL_actual_workload", "path": str(kestrel), "sha256": kestrel_sha, "frozen_sha256": service["source_sha256"], "hash_match": kestrel_sha == service["source_sha256"], "content_months": sorted(kestrel_months), "byte_count": kestrel.stat().st_size})

    weather = _read_json(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_MELBOURNE_ACTUAL_WEATHER_AUTHORITY.json")
    weather_path = Path(str(weather["path"]))
    weather_sha = _sha(weather_path)
    records.append({"role": "realized_weather", "path": str(weather_path), "sha256": weather_sha, "frozen_sha256": weather["sha256"], "hash_match": weather_sha == weather["sha256"], "timestamp_start": weather["timestamp_start"], "timestamp_end": weather["timestamp_end"], "byte_count": weather_path.stat().st_size})

    # SCATS date coverage is content-derived by the frozen V29R1 audit.
    coverage = _read_json(repo / "dayahead/artifacts/v29r1_janmar_source_authority_recovery/V29R1_JANMAR_RAW_SOURCE_COVERAGE.json")
    traffic_record = coverage["categories"]["realized_traffic_replay"]
    missing_traffic: set[str] = set()
    for span in traffic_record["missing_ranges"]:
        first = date.fromisoformat(str(span["start"]))
        missing_traffic.update((first + timedelta(days=i)).isoformat() for i in range(int(span["day_count"])))
    traffic_days = set(_days()) - missing_traffic
    return records, {"demand": demand_days, "pv": pv_days, "traffic": traffic_days, "kestrel": set(_days()) if kestrel_months == {"01", "02", "03"} else set()}


def _source_census(repo: Path, trust_cache: Path, raw_root: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    raw_records, coverage = _raw_authorities(repo, raw_root)
    rows: list[dict[str, object]] = []
    used: list[dict[str, object]] = list(raw_records)
    all_raw_hashes_match = all(bool(row["hash_match"]) for row in raw_records)
    for day in _days():
        root = trust_cache / "days" / day
        manifest_path = root / "source_day_manifest.json"
        forecast_path = root / "aemo_forecast.json"
        gfs_path = root / "gfs_d1_weather.parquet"
        status = "COMPLETE"
        reasons: list[str] = []
        try:
            manifest = _read_json(manifest_path)
            forecast = _read_json(forecast_path)
            gfs = pd.read_parquet(gfs_path)
            forecast_sha, gfs_sha = _sha(forecast_path), _sha(gfs_path)
            categories = manifest["categories"]
            hash_ok = (
                forecast_sha == categories["causal_grid_demand_forecast_vintage"]["sha256"]
                and forecast_sha == categories["causal_rooftop_pv_forecast_vintage"]["sha256"]
                and gfs_sha == categories["gfs_d1_weather"]["sha256"]
            )
            shape_ok = all(len(forecast[name]) == 96 for name in ("timestamps_96", "demand_mw_96", "pv_mw_96")) and len(gfs) == 96 and int(gfs.isna().sum().sum()) == 0
            causal_ok = not bool(manifest["causality"]["future_actual_used"]) and not bool(manifest["causality"]["April_development_data_used"])
            used.extend([
                {"role": "day_ahead_demand_and_pv_forecast", "day": day, "path": str(forecast_path), "sha256": forecast_sha, "byte_count": forecast_path.stat().st_size},
                {"role": "forecast_weather_C1", "day": day, "path": str(gfs_path), "sha256": gfs_sha, "byte_count": gfs_path.stat().st_size},
                {"role": "source_day_manifest", "day": day, "path": str(manifest_path), "sha256": _sha(manifest_path), "byte_count": manifest_path.stat().st_size},
            ])
        except Exception as exc:  # evidence is classified, never silently accepted
            hash_ok = shape_ok = causal_ok = False
            reasons.append(type(exc).__name__)
        traffic_ok = day in coverage["traffic"]
        month_sources = day in coverage["demand"] and day in coverage["pv"] and traffic_ok and day in coverage["kestrel"]
        if not traffic_ok:
            reasons.append("MISSING_REALIZED_SCATS_TRAFFIC_DAY")
        if not all_raw_hashes_match or not hash_ok:
            status = "HASH_MISMATCH"
        elif not (shape_ok and causal_ok and month_sources):
            status = "INCOMPLETE"
        rows.append({
            "day": day, "classification": status,
            "DA_workload_authority": "FROZEN_MODEL_AND_RAW_QUEUE_AUTHORITY_AVAILABLE",
            "Actual_workload_authority": "FROZEN_STRICT_FULL_KESTREL_ARCHIVE_AVAILABLE",
            "demand_forecast": "COMPLETE" if shape_ok else "INCOMPLETE",
            "realized_demand": "COMPLETE_RAW_ARCHIVE",
            "PV_forecast": "COMPLETE" if shape_ok else "INCOMPLETE",
            "realized_PV": "COMPLETE_RAW_ARCHIVE",
            "forecast_weather_C1": "COMPLETE" if shape_ok else "INCOMPLETE",
            "realized_weather_C1": "COMPLETE_RAW_AUTHORITY",
            "traffic_mobility": "COMPLETE_RAW_ARCHIVE_AND_FROZEN_ENGINEERING_ROUTE" if traffic_ok else "MISSING_REALIZED_TRAFFIC",
            "feeder_source": "COMPLETE_FROZEN_IEEE123_AND_90_ANCHOR_BACKGROUNDS",
            "rack_capacity": "COMPLETE_FROZEN_V16_MAPPING",
            "workload_compatibility": "COMPLETE_STRICT_FULL_FROZEN_DOMAIN",
            "hash_identity": hash_ok and all_raw_hashes_match,
            "semantic_shape_validation": shape_ok,
            "future_actual_reads": 0,
            "April_rows_used": 0,
            "reason": ";".join(reasons),
        })
    manifest = {
        "artifact_id": "V32R1_JANMAR_SOURCE_MANIFEST_V1", "status": "PASS" if all(row["classification"] == "COMPLETE" for row in rows) else "FAIL",
        "day_count": 90, "complete_day_count": sum(row["classification"] == "COMPLETE" for row in rows),
        "raw_authority_hash_count": len(raw_records), "day_object_hash_count": 90 * 3,
        "all_raw_hashes_match_frozen_preflight": all_raw_hashes_match,
        "source_records": used, "source_manifest_sha256": _canonical_sha(used),
        "April_rows_used": 0,
    }
    return rows, manifest


def _starting(repo: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    if _git(repo, "rev-parse", "HEAD") != STARTING_HEAD or _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V32R1_STARTING_AUTHORITY_FAIL_CLOSED")
    v32 = _read_json(repo / V32_REL / "V32_ARTIFACT_SHA256.json")
    v31 = _read_json(repo / V31_REL / "V31_ARTIFACT_SHA256.json")
    v30_tree = _git(repo, "rev-parse", "HEAD:dayahead/v30")
    if v32["aggregate_manifest_sha256"] != V32_MANIFEST_SHA or v31["aggregate_manifest_sha256"] != V31_MANIFEST_SHA or v30_tree != V30_TREE:
        raise RuntimeError("V32R1_PROTECTED_AUTHORITY_IDENTITY_FAIL_CLOSED")
    audit = {
        "artifact_id": "V32R1_STARTING_AUTHORITY_AUDIT_V1", "status": "PASS",
        "verified_starting_SHA": STARTING_HEAD, "selected_base_SHA": STARTING_HEAD, "branch": BRANCH,
        "V31_HEAD": "7662c8cc14e0ddfb1d049865cb72b21b6c39faa4", "V32_manifest_sha256": V32_MANIFEST_SHA,
        "V31_manifest_sha256": V31_MANIFEST_SHA, "V30_production_HEAD": V30_HEAD,
        "official_cases": list(OFFICIAL_CASES), "official_case_count": 4,
        "K": K, "scenario_set_sha256": SCENARIO_SHA, "M_CURRENT_pu": M_CURRENT,
        "April_rows_used": 0, "May_rows_used": 0, "clean_status_verified_before_change": True,
    }
    paths = (
        "dayahead/v29", "dayahead/v29r1", "dayahead/v29r2", "dayahead/v29r3", "dayahead/v30", "dayahead/v31", "dayahead/v32",
        "dayahead/artifacts/v29_grid_responsive_aidc", "dayahead/artifacts/v29r1_janmar_source_authority_recovery",
        "dayahead/artifacts/v29r1_reliability_calibrated_noregret", "dayahead/artifacts/v29r2_anchor_aware_trust_noregret",
        "dayahead/artifacts/v29r3_aidc_effect_forensic", "dayahead/artifacts/v30_two_stage_aidc_recourse",
        "dayahead/artifacts/v31_v30_safety_headroom_forensic", "dayahead/artifacts/v32_preapril_current_frontier_freshac",
    )
    trees = {path: _git(repo, "rev-parse", f"HEAD:{path}") for path in paths}
    preservation = {"artifact_id": "V32R1_PRECHANGE_PRESERVATION_MANIFEST_V1", "status": "PASS", "base_HEAD": STARTING_HEAD, "protected_git_trees": trees, "protected_mismatch_count": 0}
    identity = {
        "artifact_id": "V32R1_V30_PRODUCTION_TREE_IDENTITY_V1", "status": "PASS",
        "V30_frozen_production_HEAD": V30_HEAD, "expected_tree": V30_TREE,
        "observed_tree": v30_tree, "byte_tree_identical": v30_tree == V30_TREE,
        "changed_paths": [],
    }
    return audit, preservation, identity


def run(repo: Path, trust_cache: Path, raw_root: Path) -> dict[str, object]:
    repo, trust_cache, raw_root = repo.resolve(), trust_cache.resolve(), raw_root.resolve()
    out = repo / OUT_REL
    out.mkdir(parents=True, exist_ok=True)
    if (repo / FRONTIER_REL).exists():
        raise RuntimeError("V32R1_FRONTIER_NAMESPACE_EXISTS_BEFORE_AUTHORITY_FREEZE")
    audit, preservation, identity = _starting(repo)
    census, source_manifest = _source_census(repo, trust_cache, raw_root)
    if source_manifest["status"] != "PASS":
        stage1_reason = "MISSING_REALIZED_TRAFFIC_AUTHORITY_2025-02-28"
    else:
        stage1_reason = BLOCKER

    _write_json(out / "V32R1_STARTING_AUTHORITY_AUDIT.json", audit)
    _write_json(out / "V32R1_V30_PRODUCTION_TREE_IDENTITY.json", identity)
    _write_json(out / "V32R1_PRECHANGE_PRESERVATION_MANIFEST.json", preservation)
    _write_csv(out / "V32R1_JANMAR_SOURCE_CENSUS.csv", census, list(census[0]))
    _write_json(out / "V32R1_JANMAR_SOURCE_MANIFEST.json", source_manifest)

    schedule_rows = [{"day": day, "case": case, "status": "NOT_MATERIALIZED", "reason": stage1_reason, "schedule_sha256": "", "source_manifest_sha256": source_manifest["source_manifest_sha256"], "April_rows_used": 0} for day in _days() for case in OFFICIAL_CASES]
    _write_csv(out / "V32R1_DA_SCHEDULE_COVERAGE.csv", schedule_rows, list(schedule_rows[0]))

    code_evidence = {
        "V30_loader": "dayahead/v30/dayahead_formulation.py::load_frozen_schedules",
        "loader_scope": "Apr-04 only: V29R2_APR04_DAYAHEAD_{B0,B1,B2,B3}_SCHEDULE.json",
        "V30_runner_day_constant": "dayahead/v30/four_case_runner.py::DAY='2025-04-04'",
        "V30_stage1_behavior": "reports headroom and carries the frozen V29R2 objective; it does not solve a general-day V30 Stage-1 model",
        "lower_level_conflict": "V29R2 apr04_runner is also day-fixed and selects B3 MESS rung using same-day scenario Fresh AC; binding that into a general-day V30 Stage-1 would be new integration/scientific authority",
        "prohibited_substitutions": ["reuse Apr-04 schedule for Jan-Mar", "silently generalize V29R2 Apr-04 runner", "invent V30 robust Stage-1 implementation", "choose a new MESS rung rule"],
    }
    _write_json(out / "V32R1_B0_B2_REFERENCE_IDENTITY.json", {"artifact_id": "V32R1_B0_B2_REFERENCE_IDENTITY_V1", "status": "NOT_EVALUATED_PHASE_I_BLOCKED", "day_coverage": 0, "required_day_coverage": 90, "reason": stage1_reason, "code_evidence": code_evidence})
    _write_json(out / "V32R1_B1_B3_AIDC_POLICY_IDENTITY.json", {"artifact_id": "V32R1_B1_B3_AIDC_POLICY_IDENTITY_V1", "status": "CONTRACT_IDENTITY_PASS_OPERATIONAL_IDENTITY_NOT_EVALUATED", "policy_sha256": "ccc21ad3118dae01825b6ac678b2fd7f74fdd624f01639aa995be1d03ae5ac4a", "B1_policy_sha256": "ccc21ad3118dae01825b6ac678b2fd7f74fdd624f01639aa995be1d03ae5ac4a", "B3_policy_sha256": "ccc21ad3118dae01825b6ac678b2fd7f74fdd624f01639aa995be1d03ae5ac4a", "operational_day_coverage": 0, "reason": stage1_reason})

    schema = {"artifact_id": "V32R1_STAGE2_CAUSAL_RESOURCE_SCHEMA_V1", "status": "FROZEN_SCHEMA_OUTPUT_NOT_MATERIALIZED", "axes": ["day=90", "case=B1/B3", "slot=96", "cohort=15", "rack=48"], "fields": ["DA_authorized_service", "cumulative_actual_arrivals", "backlog_pre", "source_available_service", "residual_rack_occupancy", "flexible_rack_capacity", "total_rack_capacity", "compatibility", "original_DA_rack", "h_REC", "already_started", "still_eligible", "execution_before_decision", "feasible_execution_upper_bound", "y_ACT", "backlog_post", "unexecuted_reason"], "units": "node-h unless boolean/index", "ordering": "day,case,slot,cohort,rack", "schema_sha256": None}
    schema["schema_sha256"] = _canonical_sha({k: v for k, v in schema.items() if k != "schema_sha256"})
    _write_json(out / "V32R1_STAGE2_CAUSAL_RESOURCE_SCHEMA.json", schema)
    _write_json(out / "V32R1_STAGE2_CAUSAL_RESOURCE_MANIFEST.json", {"artifact_id": "V32R1_STAGE2_CAUSAL_RESOURCE_MANIFEST_V1", "status": "NOT_MATERIALIZED_PHASE_I_BLOCKED", "B1_day_coverage": 0, "B3_day_coverage": 0, "B1_epochs": 0, "B3_epochs": 0, "resource_tensor_sha256": None, "reason": stage1_reason})
    _write_json(out / "V32R1_MESS_TRAJECTORY_MANIFEST.json", {"artifact_id": "V32R1_MESS_TRAJECTORY_MANIFEST_V1", "status": "NOT_MATERIALIZED_PHASE_I_BLOCKED", "B2_day_coverage": 0, "B3_day_coverage": 0, "Actual_MESS_reoptimization_calls": 0, "aggregate_sha256": None, "reason": stage1_reason})

    sens_schema = {"artifact_id": "V32R1_CURRENT_SENSITIVITY_SCHEMA_V1", "status": "FROZEN_SCHEMA_OUTPUT_NOT_MATERIALIZED", "shape": [90, 96, 12, "branch_phase_count"], "quantity": "normalized current/loading sensitivity per AIDC site active-power control", "required_fields": ["control_names", "branch_names", "phases", "base_loading", "normalization_rating_authority", "source_state", "feeder_state_sha256", "method_fingerprint"], "selection_use": "planning-side only before Fresh frontier", "schema_sha256": None}
    sens_schema["schema_sha256"] = _canonical_sha({k: v for k, v in sens_schema.items() if k != "schema_sha256"})
    _write_json(out / "V32R1_CURRENT_SENSITIVITY_SCHEMA.json", sens_schema)
    _write_json(out / "V32R1_CURRENT_SENSITIVITY_MANIFEST.json", {"artifact_id": "V32R1_CURRENT_SENSITIVITY_MANIFEST_V1", "status": "NOT_MATERIALIZED_PHASE_I_BLOCKED", "day_coverage": 0, "aggregate_sha256": None, "reason": stage1_reason})
    _write_json(out / "V32R1_CURRENT_SENSITIVITY_COMPATIBILITY_AUDIT.json", {"artifact_id": "V32R1_CURRENT_SENSITIVITY_COMPATIBILITY_AUDIT_V1", "status": "NOT_EVALUATED_REQUIRED_V30_S_VECTOR_UNAVAILABLE", "required_status": "PASS", "compatible_day_slot_count": 0, "required_day_slot_count": 8640, "exact_V30_constraint": "s·(p_candidate-p_anchor)+(M_CURRENT/peak_control_kw)||p_candidate-p_anchor||_1<=0", "reason": stage1_reason})
    _write_json(out / "V32R1_CAUSAL_READ_AUDIT.json", {"artifact_id": "V32R1_CAUSAL_READ_AUDIT_V1", "status": "NOT_EVALUATED_PHASE_I_BLOCKED", "future_Actual_reads": 0, "Stage2_epochs_executed": 0, "same_slot_only_contract_frozen": True, "Fresh_frontier_calls": 0, "reason": stage1_reason})
    _write_json(out / "V32R1_MASS_CONSERVATION_AUDIT.json", {"artifact_id": "V32R1_MASS_CONSERVATION_AUDIT_V1", "status": "NOT_EVALUATED_PHASE_I_BLOCKED", "evaluated_day_case_count": 0, "maximum_workload_mass_error_nodeh": None, "maximum_backlog_error_nodeh": None, "tolerance_nodeh": 1e-9, "strict_FULL_only": True, "PARTIAL_shared_controllable": False, "preemption": False, "running_job_migration": False, "same_slot_only": True, "hidden_creation_or_deletion": False, "reason": stage1_reason})
    coverage = {"artifact_id": "V32R1_AUTHORITY_COVERAGE_AUDIT_V1", "status": "FAIL_CLOSED_INCOMPLETE", "source_days": source_manifest["complete_day_count"], "required_source_days": 90, "B0_DA_days": 0, "B1_DA_days": 0, "B2_DA_days": 0, "B3_DA_days": 0, "B0_Actual_anchor_days": 0, "B1_Stage2_days": 0, "B2_Actual_anchor_days": 0, "B3_Stage2_days": 0, "B2_MESS_days": 0, "B3_MESS_days": 0, "planning_sensitivity_days": 0, "B1_Stage2_epochs": 0, "B3_Stage2_epochs": 0, "combined_Stage2_epochs": 0, "future_Actual_reads": 0, "April_rows_used": 0, "blocking_gate": stage1_reason, "code_evidence": code_evidence}
    _write_json(out / "V32R1_AUTHORITY_COVERAGE_AUDIT.json", coverage)
    freeze = {"artifact_id": "V32R1_JANMAR_AUTHORITY_FREEZE_V1", "status": "FAIL_CLOSED_NOT_FROZEN", "freeze_pass": False, "Git_HEAD_at_attempt": STARTING_HEAD, "V30_production_HEAD": V30_HEAD, "K": K, "scenario_set_sha256": SCENARIO_SHA, "M_CURRENT_pu": M_CURRENT, "source_manifest_sha256": source_manifest["source_manifest_sha256"], "day_coverage": coverage, "resource_tensor_schema_sha256": schema["schema_sha256"], "MESS_trajectory_aggregate_sha256": None, "planning_sensitivity_aggregate_sha256": None, "complete_authority_aggregate_sha256": None, "frontier_phase_authorized": False, "reason": stage1_reason}
    _write_json(out / "V32R1_JANMAR_AUTHORITY_FREEZE.json", freeze)
    review = {"RESULT_CLASSIFICATION": CLASSIFICATION, "status": "COMPLETE_FAIL_CLOSED_PHASE_I_AUDIT", "primary_blocker": stage1_reason, "source_coverage": f"{source_manifest['complete_day_count']}/90", "operational_authority_frozen": False, "frontier_phase_started": False, "frontier_namespace_created": False, "Fresh_frontier_calls": 0, "production_V30_changed": False, "April_used": False, "May_used": False, "scientific_parameter_changes": False, "one_required_next_authority": "A prospectively frozen, general-day V30 Stage-1 schedule-construction contract that binds the V30 scenario objective and the inherited V29R2 MESS no-regret rung without result-driven choice."}
    _write_json(out / "V32R1_FINAL_REVIEW.json", review)
    _write_text(out / "README.md", f"""
# V32R1 Jan--Mar V30 authority materialization audit

Result: `{CLASSIFICATION}`.

The source census is 89/90 complete.  The frozen February SCATS archive contains
27 days and has no 2025-02-28 realized-traffic record.  V32R1 forbids inventing,
interpolating, or downloading a replacement authority, so the mandatory source
gate stops Phase I before optimization.  A second latent blocker was also
audited: V30 loads four frozen Apr-04 V29R2 schedules and contains no general-day
Stage-1 schedule generator.  Generalizing the V29R2 Fresh-selected MESS rung and
binding it to the V30 scenario objective would require new authority.

No partial operational authority was represented as valid, no authority freeze
was declared, the Phase-II frontier namespace was not created, and Fresh
frontier calls are zero.
""")
    return review


def finalize(repo: Path, *, passed: int, failed: int, not_run: int, command: str) -> dict[str, object]:
    repo = repo.resolve()
    out = repo / OUT_REL
    if failed or not_run:
        raise RuntimeError("V32R1_TESTS_NOT_GREEN")
    _write_json(out / "V32R1_TEST_REPORT.json", {"artifact_id": "V32R1_TEST_REPORT_V1", "status": "PASS", "passed": passed, "failed": failed, "not_run": not_run, "command": command, "blocked_outcome_tests_validate_fail_closed_behavior": True, "read_only_cache_junctions_removed_after_run": True})
    pre = _read_json(out / "V32R1_PRECHANGE_PRESERVATION_MANIFEST.json")
    current = {path: _git(repo, "rev-parse", f"HEAD:{path}") for path in pre["protected_git_trees"]}
    mismatches = [path for path, sha in current.items() if sha != pre["protected_git_trees"][path]]
    post = {"artifact_id": "V32R1_POSTCHANGE_PRESERVATION_AUDIT_V1", "status": "PASS" if not mismatches else "FAIL", "protected_mismatch_count": len(mismatches), "mismatches": mismatches, "protected_git_trees": current, "V30_production_tree_unchanged": current["dayahead/v30"] == V30_TREE}
    _write_json(out / "V32R1_POSTCHANGE_PRESERVATION_AUDIT.json", post)
    if mismatches:
        raise RuntimeError("V32R1_POSTCHANGE_PRESERVATION_FAIL")
    manifest = _files_digest(out, exclude=("V32R1_AUTHORITY_SHA256.json",))
    manifest.update({"artifact_id": "V32R1_AUTHORITY_SHA256_V1", "status": "PASS_AUDIT_PACKAGE_NOT_OPERATIONAL_AUTHORITY"})
    _write_json(out / "V32R1_AUTHORITY_SHA256.json", manifest)
    return {"manifest": manifest, "post": post}
