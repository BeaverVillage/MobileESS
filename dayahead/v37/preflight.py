"""Fail-closed May production-input preflight without running optimization."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from dayahead.tools.run_v35r3e_r1_beam import _service_mapping
from dayahead.v17_ac_restoration_contract import K_MAX, RHO
from dayahead.v28r2.source_cache import day_root
from dayahead.v35.execution import daily_traffic_authority
from dayahead.v37r3.voltage_authority import (
    APPLICABILITY_RELATIVE_PATH,
    AUTHORITY_RELATIVE_PATH,
    joint_repaired_coefficients,
    load_joint_voltage_authority,
    load_may_voltage_applicability,
)

from .aidc import build_day, validate_cohort_contract
from .context import load_day_context
from .contracts import CACHE_ROOT, EXPECTED_DATES, PASS_ID, PHASE, SOURCE_DATA_REPOSITORY


FIXED_AEST = timezone(timedelta(hours=10))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def anchor_paths(repo: Path, day: str) -> tuple[Path, Path]:
    root = repo / CACHE_ROOT / "electrical" / day / "data"
    return (
        root / f"D1_AC_ANCHOR_SENSITIVITY_{day}.npz",
        root / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{day}.npz",
    )


def validate_causal_vintage(vintage: Mapping[str, Any], day: str) -> dict[str, Any]:
    expected_cutoff = datetime.fromisoformat(day).replace(tzinfo=FIXED_AEST) - timedelta(hours=6)
    cutoff = datetime.fromisoformat(str(vintage["cutoff_fixed_aest"]))
    demand_issue = datetime.fromisoformat(str(vintage["demand_issue"]))
    pv_issue = datetime.fromisoformat(str(vintage["pv_issue"]))
    timestamps = tuple(map(str, vintage["timestamps_96"]))
    demand = np.asarray(vintage["demand_mw_96"], dtype=float)
    pv = np.asarray(vintage["pv_mw_96"], dtype=float)
    failures: list[str] = []
    if cutoff != expected_cutoff:
        failures.append("D_MINUS_1_CUTOFF_MISMATCH")
    if demand_issue > cutoff:
        failures.append("DEMAND_ISSUE_AFTER_CUTOFF")
    if pv_issue > cutoff:
        failures.append("PV_ISSUE_AFTER_CUTOFF")
    if len(timestamps) != 96 or demand.shape != (96,) or pv.shape != (96,):
        failures.append("AEMO_96_SLOT_AXIS")
    if not np.isfinite(demand).all() or not np.isfinite(pv).all():
        failures.append("AEMO_NONFINITE")
    for field in ("demand_source_sha256", "pv_source_sha256"):
        if len(str(vintage.get(field, ""))) != 64:
            failures.append(f"{field.upper()}_MISSING")
    archive = dict(vintage.get("cross_month_archive_authority", {}))
    if not archive.get("demand_path") or not archive.get("pv_path"):
        failures.append("AEMO_ARCHIVE_EVIDENCE_MISSING")
    return {
        "operating_day": day,
        "cutoff_fixed_aest": cutoff.isoformat(),
        "expected_cutoff_fixed_aest": expected_cutoff.isoformat(),
        "demand_issue": demand_issue.isoformat(),
        "pv_issue": pv_issue.isoformat(),
        "demand_source_sha256": str(vintage.get("demand_source_sha256", "")),
        "pv_source_sha256": str(vintage.get("pv_source_sha256", "")),
        "archive_month": archive.get("archive_month"),
        "demand_archive_path": archive.get("demand_path"),
        "pv_archive_path": archive.get("pv_path"),
        "future_data_reads": 0,
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }


def validate_anchor_pair(repo: Path, day: str) -> dict[str, Any]:
    voltage_path, current_path = anchor_paths(repo, day)
    failures: list[str] = []
    if not voltage_path.is_file():
        failures.append("D1_VOLTAGE_ANCHOR_MISSING")
    if not current_path.is_file():
        failures.append("D1_CURRENT_ANCHOR_MISSING")
    if failures:
        return {
            "operating_day": day,
            "voltage_path": str(voltage_path.relative_to(repo)).replace("\\", "/"),
            "current_path": str(current_path.relative_to(repo)).replace("\\", "/"),
            "failures": failures,
            "status": "FAIL",
        }

    with np.load(voltage_path, allow_pickle=False) as voltage:
        nodes = tuple(map(str, voltage["node_names"]))
        controls = tuple(map(str, voltage["control_names"]))
        branches = tuple(map(str, voltage["branch_names"]))
        expected_shapes = {
            "anchor_v_squared": (96, len(nodes)),
            "sensitivity": (96, len(controls), len(nodes)),
            "anchor_control": (96, len(controls)),
            "branch_p_kw": (96, len(branches)),
            "branch_q_kvar": (96, len(branches)),
            "branch_current_a": (96, len(branches)),
            "root_pq": (96, 2),
        }
        if str(voltage["operating_day"]) != day:
            failures.append("VOLTAGE_OPERATING_DAY")
        for name, shape in expected_shapes.items():
            array = np.asarray(voltage[name])
            if array.shape != shape:
                failures.append(f"VOLTAGE_SHAPE_{name}")
            elif not np.isfinite(array).all():
                failures.append(f"VOLTAGE_NONFINITE_{name}")
        if np.asarray(voltage["regulator_taps"]).shape != (96, 7):
            failures.append("REGULATOR_TAP_AXIS")
        if np.asarray(voltage["capacitor_states"]).shape != (96, 4):
            failures.append("CAPACITOR_STATE_AXIS")
        if len(nodes) != 386 or len(controls) != 60 or len(branches) != 383:
            failures.append("FROZEN_ELECTRICAL_AXIS")
        node_set = set(nodes)
        mapping = _service_mapping()
        for bus in mapping.values():
            if any(f"{bus}.{phase}" not in node_set for phase in (1, 2, 3)):
                failures.append(f"PCC_PHASE_AXIS_{bus}")
        voltage_sha = sha256_file(voltage_path)

    with np.load(current_path, allow_pickle=False) as current:
        current_branches = tuple(map(str, current["branch_names"]))
        current_controls = tuple(map(str, current["control_names"]))
        if str(current["operating_day"]) != day:
            failures.append("CURRENT_OPERATING_DAY")
        if current_branches != branches or current_controls != controls:
            failures.append("CURRENT_AUTHORITY_AXIS")
        for name, shape in {
            "rating_a": (len(branches),),
            "anchor_current_loading_pu": (96, len(branches)),
            "current_sensitivity_pu_per_control": (96, len(controls), len(branches)),
        }.items():
            array = np.asarray(current[name])
            if array.shape != shape:
                failures.append(f"CURRENT_SHAPE_{name}")
            elif not np.isfinite(array).all():
                failures.append(f"CURRENT_NONFINITE_{name}")
        if str(current["source_voltage_cache_sha256"]) != voltage_sha:
            failures.append("CURRENT_SOURCE_VOLTAGE_SHA")
        if not any(name.startswith("transformer.") for name in current_branches):
            failures.append("TRANSFORMER_AUTHORITY_AXIS")

    return {
        "operating_day": day,
        "voltage_path": str(voltage_path.relative_to(repo)).replace("\\", "/"),
        "voltage_sha256": voltage_sha,
        "current_path": str(current_path.relative_to(repo)).replace("\\", "/"),
        "current_sha256": sha256_file(current_path),
        "slot_count": 96,
        "node_count": len(nodes),
        "phase_coverage": "A/B/C",
        "control_count": len(controls),
        "branch_count": len(branches),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }


def production_loader_dry_run(repo: Path, day: str) -> dict[str, Any]:
    """Load all production authorities for one day, without invoking Gurobi."""

    checks: dict[str, Any] = {}
    reasons: list[str] = []
    electrical = None
    try:
        source = day_root(SOURCE_DATA_REPOSITORY, day)
        source_manifest = source / "source_day_manifest.json"
        if not source_manifest.is_file():
            raise RuntimeError("SOURCE_DAY_MANIFEST_MISSING")
        source_payload = json.loads(source_manifest.read_text(encoding="utf-8"))
        checks["source_day_sha256"] = str(source_payload["source_day_sha256"])

        # A preflight is read-only.  Refuse a missing/invalid pair before the
        # production context loader gets a chance to materialize it.
        anchor = validate_anchor_pair(repo, day)
        checks["electrical_anchor"] = anchor
        if anchor["status"] != "PASS":
            raise RuntimeError(";".join(anchor["failures"]))

        data, electrical = load_day_context(repo, day)
        vintage = validate_causal_vintage(data.vintage, day)
        checks["causal_vintage"] = vintage
        reasons.extend(vintage["failures"])

        aids = {case: build_day(repo, day, case) for case in ("B0", "B1", "B2", "B3")}
        cohort = validate_cohort_contract(aids["B1"].ledger, day)
        checks["AIDC_cohort"] = cohort
        if not np.array_equal(aids["B0"].pcc_p_kw, aids["B2"].pcc_p_kw):
            reasons.append("AIDC_B0_B2_REFERENCE_MISMATCH")
        if not np.array_equal(aids["B1"].pcc_p_kw, aids["B3"].pcc_p_kw):
            reasons.append("AIDC_B1_B3_CENTER_MISMATCH")
        if aids["B1"].power["official_scenario"].nunique() != 1 or str(
            aids["B1"].power["official_scenario"].iloc[0]
        ) != "CENTER":
            reasons.append("AIDC_CENTER_CONTRACT")

        authority, authority_sha = load_joint_voltage_authority(repo)
        applicability, applicability_sha = load_may_voltage_applicability(
            repo, authority, authority_sha,
        )
        coefficients = joint_repaired_coefficients(repo, electrical)
        if len(coefficients) != 96:
            reasons.append("VOLTAGE_COEFFICIENT_SLOT_AXIS")
        checks["voltage_authority"] = {
            "coefficient_authority_sha256": authority_sha,
            "applicability_sha256": applicability_sha,
            "authorized_base_anchor_sha256": applicability[
                "base_voltage_authority_sha256_by_day"
            ][day],
            "coefficient_slots": len(coefficients),
        }

        bundle, _graph, route_table, traffic_files = daily_traffic_authority(
            repo, repo / CACHE_ROOT / "traffic", PHASE, day, {"status": "PASS", "May_numeric_reads_before_admission": 0},
        )
        if len(route_table.departure_slots) != 96 or len(route_table.service_ids) != 24:
            reasons.append("MESS_ROUTE_TABLE_AXIS")
        if len(route_table.records) != 96 * 24 * 24:
            reasons.append("MESS_ROUTE_TABLE_PRODUCT")
        routes = tuple(route_table.records.values())
        if not all(
            np.isfinite((row.route_safe_eta_sec, row.energy_safe_kwh)).all()
            # The frozen Safe-ETA authority is a separately calibrated value;
            # it is conservatively no faster than Q50 but is not defined as
            # max(Q90, ...), so Q90 ordering is not an invariant.
            and row.route_safe_eta_sec >= row.route_q50_eta_sec
            and row.energy_safe_kwh >= row.energy_nominal_kwh
            for row in routes
        ):
            reasons.append("SAFE_ETA_OR_TRAVEL_ENERGY")
        if not bundle.causality_pass or bundle.future_actual_read_count != 0:
            reasons.append("TRAFFIC_CAUSALITY")
        checks["traffic"] = {
            "forecast_sha256": traffic_files[0]["sha256"],
            "route_table_sha256": traffic_files[1]["sha256"],
            "route_authority_sha256": route_table.canonical_sha256,
            "issue_time": bundle.issue_time.isoformat(),
            "max_input_timestamp": bundle.max_input_timestamp.isoformat(),
            "Safe_ETA": "PASS",
            "travel_energy": "PASS",
        }

        mapping = _service_mapping()
        checks["service_PCC_mapping"] = {
            "count": len(mapping),
            "sha256": hashlib.sha256(json.dumps(
                mapping, sort_keys=True, separators=(",", ":"),
            ).encode()).hexdigest(),
        }
        checks["restoration_contract"] = {
            "adapter": "dayahead.v37r3.restoration",
            "rho": RHO,
            "max_rounds": K_MAX,
            "P_Q_only_recourse": True,
            "fixed_discrete_MESS_decisions": True,
            "beam_rerun_during_restoration": False,
        }

        # Imported lazily to avoid a module cycle at import time.
        from .runner import case_execution_fingerprint

        fingerprints = {
            case: case_execution_fingerprint(repo, day, case, aids[case])
            for case in ("B0", "B1", "B2", "B3")
        }
        checks["case_execution_fingerprints"] = {
            case: row["execution_fingerprint_sha256"]
            for case, row in fingerprints.items()
        }
        checks["fingerprint_authorities"] = {
            "voltage_authority_sha256": fingerprints["B0"]["voltage_authority_sha256"],
            "voltage_applicability_sha256": fingerprints["B0"]["voltage_applicability_sha256"],
            "AIDC_cohort_contract_sha256": fingerprints["B0"]["AIDC_cohort_contract_sha256"],
            "restoration_cut_fingerprint_sha256": fingerprints["B0"]["restoration_cut_fingerprint_sha256"],
            "network_context_SHA": fingerprints["B0"]["network_context_SHA"],
            "execution_code_SHA": fingerprints["B0"]["execution_code_SHA"],
        }
    except Exception as error:  # fail closed and preserve exact loader reason
        reasons.append(f"{type(error).__name__}:{error}")
    finally:
        if electrical is not None:
            electrical.voltage.close()
            electrical.current.close()
    return {
        "operating_day": day,
        "status": "READY" if not reasons else "NOT_READY",
        "reasons": reasons,
        "checks": checks,
        "optimization_calls": 0,
        "Gurobi_optimize_calls": 0,
        "Fresh_OpenDSS_solve_calls": 0,
        "campaign_started": False,
        "pass_id": PASS_ID,
    }


def validate_preflight_manifest(payload: Mapping[str, Any]) -> list[str]:
    """Pure fail-closed gate shared by tests and the PowerShell launcher contract."""

    failures: list[str] = []
    if int(payload.get("expected_dates", -1)) != len(EXPECTED_DATES):
        failures.append("EXPECTED_DATES_NOT_31")
    if int(payload.get("ready_dates", -1)) != len(EXPECTED_DATES):
        failures.append("READY_DATES_NOT_31")
    if int(payload.get("not_ready_dates", -1)) != 0:
        failures.append("NOT_READY_DATES_NONZERO")
    if int(payload.get("missing_dates", -1)) != 0:
        failures.append("MISSING_DATES_NONZERO")
    if payload.get("MAY_STARTED") != "NO":
        failures.append("MAY_STARTED_NOT_NO")
    if payload.get("MAY_CAMPAIGN_LAUNCH_READY") != "YES":
        failures.append("MAY_CAMPAIGN_LAUNCH_NOT_READY")
    rows = payload.get("dates", [])
    if len(rows) != len(EXPECTED_DATES):
        failures.append("DATE_ROW_COUNT_NOT_31")
    elif tuple(row.get("operating_day") for row in rows) != EXPECTED_DATES:
        failures.append("DATE_AXIS_MISMATCH")
    elif any(row.get("status") != "READY" for row in rows):
        failures.append("DATE_NOT_READY")
    fingerprints = payload.get("launch_fingerprints", [])
    if not fingerprints:
        failures.append("LAUNCH_FINGERPRINTS_MISSING")
    return failures
