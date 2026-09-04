"""V29R2 pre-April anchor-physics forensic.

This module is deliberately limited to Stage A.  It reads the frozen V29R1
source/cache/anchor evidence, runs independent Fresh OpenDSS F0--F3
trajectories, and writes only the V29R2 artifact namespace.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
from dayahead.grid_background_v16_2 import (
    ALPHA_GRID,
    IEEE123_NATIVE_P_KW,
    P95_REFERENCE_MW,
    PV_CAPACITY_EXPECTED_KW,
    PV_REFERENCE_MAX_MW,
    build_authority_background_binding,
)
from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.electrical_context import ElectricalContext, portable_background_paths, source_root
from dayahead.v28r2.formulation import PF_TAN
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.opendss_mapping import CAPACITORS, REGULATORS, FeederAssets
from dayahead.v29r1.authority import CERTIFICATION_DAYS
from dayahead.v29r1.runner import hash_scope
from dayahead.v29r1.source_resume import (
    sha256_file,
    validate_aemo,
    validate_gfs,
    write_csv,
    write_json,
)
from dayahead.v29r1.trust_certification import _inputs, _trajectory


V29R1_HEAD = "105b688d90a9ea792cb3ced60773c1c58b6888dc"
V29R2_BRANCH = "codex/v29r2-anchor-aware-trust-noregret"
OUT_REL = Path("dayahead/artifacts/v29r2_anchor_aware_trust_noregret")
V29R1_SOURCE_REL = Path("cache/v29r1_trust_cert_sources/jan_mar_2025")
REPRODUCTION_TOLERANCE = 1e-7
ACCOUNTING_TOLERANCE = 1e-10
LIMIT_TOLERANCE = 1e-9

VIOLATION_DAYS = (
    "2025-01-03", "2025-01-05", "2025-01-08", "2025-01-10", "2025-01-14",
    "2025-01-20", "2025-01-21", "2025-01-27", "2025-02-02", "2025-02-03",
    "2025-02-04", "2025-02-06", "2025-02-07", "2025-02-10", "2025-02-11",
    "2025-02-12", "2025-02-13", "2025-02-22", "2025-02-24", "2025-02-26",
    "2025-03-04", "2025-03-07", "2025-03-09", "2025-03-10", "2025-03-11",
    "2025-03-14",
)
CONTROL_SELECTION_SALT = "V29R2_ANCHOR_CONTROL_DAYS_V1"


def evidence_root(repo: Path) -> Path:
    return repo.parent / "MobileESS_v29r1"


def campaign_root() -> Path:
    return Path(r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend")


def control_days() -> tuple[str, ...]:
    eligible = sorted(set(CERTIFICATION_DAYS) - set(VIOLATION_DAYS))
    ranked = sorted(
        eligible,
        key=lambda day: hashlib.sha256(f"{CONTROL_SELECTION_SALT}:{day}".encode()).hexdigest(),
    )
    return tuple(sorted(ranked[:10]))


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _verify_authority(repo: Path) -> dict[str, object]:
    v29r1 = evidence_root(repo)
    state = {
        "V29R2_branch": _git(repo, "branch", "--show-current"),
        "V29R2_base_head": _git(repo, "rev-parse", "HEAD"),
        "V29R1_branch": _git(v29r1, "branch", "--show-current"),
        "V29R1_head": _git(v29r1, "rev-parse", "HEAD"),
        "V29R1_status_short": _git(v29r1, "status", "--short"),
    }
    if state != {
        "V29R2_branch": V29R2_BRANCH,
        "V29R2_base_head": V29R1_HEAD,
        "V29R1_branch": "codex/v29r1-reliability-calibrated-noregret",
        "V29R1_head": V29R1_HEAD,
        "V29R1_status_short": "",
    }:
        raise RuntimeError(f"V29R2_GIT_AUTHORITY_MISMATCH:{state}")
    return state


def _prechange_manifest(repo: Path, git_state: Mapping[str, object]) -> dict[str, object]:
    v29r1 = evidence_root(repo)
    scopes = {
        "V29R1_BLOCKED_EVIDENCE": [v29r1 / "dayahead/artifacts/v29r1_reliability_calibrated_noregret"],
        "V29R1_SOURCE_RECOVERY_EVIDENCE": [v29r1 / "dayahead/artifacts/v29r1_janmar_source_authority_recovery"],
        "V29R1_SOURCE_AND_ANCHOR_CACHE": [v29r1 / V29R1_SOURCE_REL],
    }
    hashed = {}
    for name, paths in scopes.items():
        print(json.dumps({"phase": "v29r2-prechange-hash", "scope": name}), flush=True)
        hashed[name] = hash_scope(paths)
    payload = {
        "artifact_id": "V29R2_PRECHANGE_AUTHORITY_MANIFEST_V1",
        "status": "PASS",
        "git_state": dict(git_state),
        "protected_scopes": hashed,
        "V29R1_read_only": True,
    }
    write_json(repo / OUT_REL / "V29R2_PRECHANGE_AUTHORITY_MANIFEST.json", payload)
    return payload


def _source_hash_audit(repo: Path) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    v29r1 = evidence_root(repo)
    selected, aemo_archives = validate_aemo(campaign_root())
    gfs = validate_gfs(12)
    frozen_raw = _load_json(
        v29r1 / "dayahead/artifacts/v29r1_janmar_source_authority_recovery/V29R1_JANMAR_DOWNLOADED_RAW_VALIDATION.json"
    )
    frozen_aemo = {
        (str(row["path"]), str(row["sha256"])) for row in frozen_raw["AEMO_archives"]
    }
    current_aemo = {(str(row["path"]), str(row["sha256"])) for row in aemo_archives}
    if current_aemo != frozen_aemo:
        raise RuntimeError("V29R2_AEMO_FROZEN_HASH_MISMATCH")

    material = _load_json(
        v29r1 / "dayahead/artifacts/v29r1_janmar_source_authority_recovery/V29R1_JANMAR_MATERIALIZATION_REPORT.json"
    )
    day_records = {str(row["day"]): row for row in material["days"]}
    recomputed_lines = []
    source_file_rows = []
    for day in CERTIFICATION_DAYS:
        root = v29r1 / V29R1_SOURCE_REL / "days" / day
        manifest_path = root / "source_day_manifest.json"
        actual_manifest_sha = sha256_file(manifest_path)
        if actual_manifest_sha != day_records[day]["manifest_sha256"]:
            raise RuntimeError(f"V29R2_MATERIALIZED_MANIFEST_SHA_MISMATCH:{day}")
        manifest = _load_json(manifest_path)
        for category in (
            "gfs_d1_weather", "causal_grid_demand_forecast_vintage",
            "causal_rooftop_pv_forecast_vintage",
        ):
            record = manifest["categories"][category]
            path = Path(str(record["path"]))
            actual = sha256_file(path)
            if actual != record["sha256"]:
                raise RuntimeError(f"V29R2_MATERIALIZED_SOURCE_SHA_MISMATCH:{day}:{category}")
            source_file_rows.append({"day": day, "category": category, "sha256": actual})
        material_aemo = _load_json(root / "aemo_forecast.json")
        if canonical_sha256(material_aemo) != canonical_sha256(selected[day]):
            raise RuntimeError(f"V29R2_AEMO_MATERIALIZED_VALUE_MISMATCH:{day}")
        recomputed_lines.append(f"{day}:{actual_manifest_sha}\n")
    content_manifest = hashlib.sha256("".join(recomputed_lines).encode()).hexdigest()
    if content_manifest != material["content_manifest_sha256"]:
        raise RuntimeError("V29R2_MATERIALIZED_CONTENT_MANIFEST_MISMATCH")
    payload = {
        "status": "PASS",
        "GFS_operating_days": 90,
        "GFS_lead_tasks": len(gfs),
        "GFS_message_records": sum(int(row["record_count"]) for row in gfs),
        "GFS_validation_digest": canonical_sha256(gfs),
        "AEMO_archive_count": len(aemo_archives),
        "AEMO_archive_hash_identity": True,
        "AEMO_materialized_value_identity_day_count": 90,
        "materialized_source_file_count": len(source_file_rows),
        "materialized_content_manifest_sha256": content_manifest,
        "frozen_content_manifest_sha256": material["content_manifest_sha256"],
        "future_actual_used": False,
        "redownload_performed": False,
    }
    return payload, selected


def _critical(result: object) -> dict[str, object]:
    line_mask = np.asarray([kind == "line" for kind in result.branch_kinds])
    line_indices = np.flatnonzero(line_mask)
    line_flat = int(np.argmax(result.phase_current_loading_pu[:, line_mask]))
    line_slot, local = np.unravel_index(line_flat, result.phase_current_loading_pu[:, line_mask].shape)
    line_index = int(line_indices[local])
    vmax_flat = int(np.argmax(result.voltage_pu))
    vmax_slot, vmax_node = np.unravel_index(vmax_flat, result.voltage_pu.shape)
    vmin_flat = int(np.argmin(result.voltage_pu))
    vmin_slot, vmin_node = np.unravel_index(vmin_flat, result.voltage_pu.shape)
    return {
        "critical_line": result.branch_names[line_index],
        "critical_line_phase": result.branch_phases[line_index],
        "critical_line_slot": int(line_slot),
        "critical_line_current_a": float(result.phase_current_a[line_slot, line_index]),
        "critical_line_rating_a": float(
            result.phase_current_a[line_slot, line_index]
            / result.phase_current_loading_pu[line_slot, line_index]
        ),
        "Vmax_node": result.node_names[vmax_node], "Vmax_phase": result.node_phases[vmax_node],
        "Vmax_slot": int(vmax_slot),
        "Vmin_node": result.node_names[vmin_node], "Vmin_phase": result.node_phases[vmin_node],
        "Vmin_slot": int(vmin_slot),
    }


def _result_row(day: str, sample: str, result: object) -> dict[str, object]:
    summary = dict(result.summary)
    summary["opendss_version"] = " ".join(str(summary["opendss_version"]).splitlines()).strip()
    return {"day": day, "sample": sample, "case": result.case, **summary, **_critical(result)}


def _violation_ledger(day: str, timestamps: Sequence[str], result: object) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for slot in range(96):
        vmax = float(result.voltage_pu[slot].max())
        vmin = float(result.voltage_pu[slot].min())
        line_mask = np.asarray([kind == "line" for kind in result.branch_kinds])
        rho = float(result.phase_current_loading_pu[slot, line_mask].max())
        for node, value in enumerate(result.voltage_pu[slot]):
            value = float(value)
            if value > 1.05 + LIMIT_TOLERANCE or value < .95 - LIMIT_TOLERANCE:
                high = value > 1.05
                rows.append({
                    "day": day, "slot": slot, "timestamp": timestamps[slot],
                    "violation_type": "VOLTAGE_HIGH" if high else "VOLTAGE_LOW",
                    "asset": result.node_names[node], "phase": result.node_phases[node],
                    "value": value, "limit": 1.05 if high else .95,
                    "Vmax_pu": vmax, "Vmin_pu": vmin, "rho_AC": rho,
                    "current_A": "", "rating_A": "",
                    "gV_high": max(0.0, value - 1.05),
                    "gV_low": max(0.0, .95 - value), "gI": 0.0,
                })
        for branch, (name, phase, kind) in enumerate(zip(
            result.branch_names, result.branch_phases, result.branch_kinds, strict=True,
        )):
            loading = float(result.phase_current_loading_pu[slot, branch])
            kva = float(result.transformer_total_kva_loading_pu[slot, branch])
            if loading > 1.0 + LIMIT_TOLERANCE:
                current = float(result.phase_current_a[slot, branch])
                rows.append({
                    "day": day, "slot": slot, "timestamp": timestamps[slot],
                    "violation_type": "CURRENT_OVERLOAD" if kind == "line" else "TRANSFORMER_OVERLOAD",
                    "asset": name, "phase": phase, "value": loading, "limit": 1.0,
                    "Vmax_pu": vmax, "Vmin_pu": vmin, "rho_AC": rho,
                    "current_A": current, "rating_A": current / loading,
                    "gV_high": 0.0, "gV_low": 0.0, "gI": max(0.0, loading - 1.0),
                })
            if kind == "transformer" and kva > 1.0 + LIMIT_TOLERANCE:
                rows.append({
                    "day": day, "slot": slot, "timestamp": timestamps[slot],
                    "violation_type": "TRANSFORMER_OVERLOAD", "asset": name,
                    "phase": phase, "value": kva, "limit": 1.0,
                    "Vmax_pu": vmax, "Vmin_pu": vmin, "rho_AC": rho,
                    "current_A": float(result.phase_current_a[slot, branch]), "rating_A": "KVA_AUTHORITY",
                    "gV_high": 0.0, "gV_low": 0.0, "gI": max(0.0, kva - 1.0),
                })
    return rows


def _metric(result: object, ledger: Mapping[str, object]) -> float:
    slot = int(ledger["slot"])
    asset = str(ledger["asset"])
    phase = str(ledger["phase"])
    if str(ledger["violation_type"]).startswith("VOLTAGE"):
        index = next(i for i, (name, ph) in enumerate(zip(result.node_names, result.node_phases, strict=True)) if name == asset and ph == phase)
        return float(result.voltage_pu[slot, index])
    index = next(i for i, (name, ph) in enumerate(zip(result.branch_names, result.branch_phases, strict=True)) if name == asset and ph == phase)
    if str(ledger["rating_A"]) == "KVA_AUTHORITY":
        return float(result.transformer_total_kva_loading_pu[slot, index])
    return float(result.phase_current_loading_pu[slot, index])


def _attribution(ledger: Mapping[str, object], results: Mapping[str, object]) -> dict[str, object]:
    values = {case: _metric(result, ledger) for case, result in results.items()}
    aidc = values["F1"] - values["F0"]
    mess = values["F2"] - values["F0"]
    interaction = values["F3"] - values["F1"] - values["F2"] + values["F0"]
    high_or_current = str(ledger["violation_type"]) != "VOLTAGE_LOW"
    sign = 1.0 if high_or_current else -1.0
    limit = float(ledger["limit"])
    background_stress = max(0.0, sign * (values["F0"] - limit))
    return {
        "day": ledger["day"], "slot": ledger["slot"], "timestamp": ledger["timestamp"],
        "violation_type": ledger["violation_type"], "asset": ledger["asset"], "phase": ledger["phase"],
        "F0_value": values["F0"], "F1_value": values["F1"],
        "F2_value": values["F2"], "F3_value": values["F3"],
        "AIDC_contribution_F1_minus_F0": aidc,
        "MESS_maintenance_contribution_F2_minus_F0": mess,
        "interaction_residual_F3_minus_F1_minus_F2_plus_F0": interaction,
        "accounting_error": values["F3"] - (values["F0"] + aidc + mess + interaction),
        "background_positive_stress": background_stress,
        "AIDC_positive_stress": max(0.0, sign * aidc),
        "MESS_positive_stress": max(0.0, sign * mess),
        "interaction_positive_stress": max(0.0, sign * interaction),
    }


def _day_classification(rows: Sequence[Mapping[str, object]]) -> str:
    totals = {
        "BACKGROUND": sum(float(row["background_positive_stress"]) for row in rows),
        "AIDC_REFERENCE": sum(float(row["AIDC_positive_stress"]) for row in rows),
        "MESS_MAINTENANCE": sum(float(row["MESS_positive_stress"]) for row in rows),
        "INTERACTION": sum(float(row["interaction_positive_stress"]) for row in rows),
    }
    active = [name for name, value in totals.items() if value > ACCOUNTING_TOLERANCE]
    if len(active) != 1:
        return "MIXED"
    return f"{active[0]}_DRIVEN"


def _day_worker(repo_text: str, day: str, sample: str) -> dict[str, object]:
    repo = Path(repo_text)
    v29r1 = evidence_root(repo)
    inputs = _inputs(v29r1, day)
    source = source_root(repo)
    background = build_authority_background_binding(
        timestamps_fixed_aest=inputs.vintage["timestamps_96"],
        demand_mw_96=inputs.vintage["demand_mw_96"],
        rooftop_pv_mw_96=inputs.vintage["pv_mw_96"],
        paths=portable_background_paths(repo, source),
    )
    binding = build_full_grid_binding(
        assets=source / "opendss_assets", contract=source / "power_v70_p4f_contract",
        demand_mw_96=inputs.vintage["demand_mw_96"], rooftop_pv_mw_96=inputs.vintage["pv_mw_96"],
        aidc_plan_kw_96x12=inputs.reference_pcc_kw.tolist(),
        pcc_asset=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        background_binding=background,
    )
    anchor_path = v29r1 / V29R1_SOURCE_REL / "electrical_anchor" / day / "D1_AC_ANCHOR.npz"
    voltage = np.load(anchor_path, allow_pickle=False)
    legacy = (
        {"plan_kw_96x12": tuple(tuple(map(float, row)) for row in inputs.reference_pcc_kw)},
        inputs.vintage, background, binding, anchor_path, "V29R2_ANCHOR_FORENSIC",
    )
    context = ElectricalContext(legacy, voltage, None, source, anchor_path, anchor_path)
    zero = np.zeros_like(inputs.reference_pcc_kw)
    trajectories = {
        "F0": _trajectory(day, "V29R2_F0_BACKGROUND_ONLY", zero),
        "F1": _trajectory(day, "V29R2_F1_BACKGROUND_PLUS_AIDC_REFERENCE", inputs.reference_pcc_kw),
        "F2": _trajectory(day, "V29R2_F2_BACKGROUND_PLUS_MESS_MAINTENANCE", zero),
        "F3": _trajectory(day, "V29R2_F3_FULL_D1_ANCHOR", inputs.reference_pcc_kw),
    }
    results = {
        case: run_fresh_opendss(repo=repo, context=context, voltage=voltage, trajectory=trajectory)
        for case, trajectory in trajectories.items()
    }
    frozen_voltage = np.sqrt(np.asarray(voltage["anchor_v_squared"], dtype=float))
    frozen_current = np.asarray(voltage["branch_current_a"], dtype=float)
    frozen_rows = _csv_rows(
        v29r1 / "dayahead/artifacts/v29r1_reliability_calibrated_noregret/V29R1_TRUST_CERT_OPENDSS_RESULTS.csv"
    )
    frozen_row = next(row for row in frozen_rows if row["day"] == day and row["rho_AIDC"] == "0.1")
    f3_summary = results["F3"].summary
    summary_errors = {
        "rho_max_AC": abs(float(f3_summary["rho_max_AC"]) - float(frozen_row["anchor_rho_max_AC"])),
        "Vmin_pu": abs(float(f3_summary["Vmin_pu"]) - float(frozen_row["anchor_Vmin_pu"])),
        "Vmax_pu": abs(float(f3_summary["Vmax_pu"]) - float(frozen_row["anchor_Vmax_pu"])),
        "transformer_phase_current_loading_max": abs(
            float(f3_summary["transformer_phase_current_loading_max"])
            - float(frozen_row["anchor_transformer_phase_current_loading_max"])
        ),
        "transformer_total_kva_loading_max": abs(
            float(f3_summary["transformer_total_kva_loading_max"])
            - float(frozen_row["anchor_transformer_total_kva_loading_max"])
        ),
    }
    reproduction = {
        "frozen_V29R1_Fresh_summary_max_abs_error": max(summary_errors.values()),
        "frozen_V29R1_Fresh_summary_field_errors": summary_errors,
        "native_anchor_NPZ_voltage_max_abs_difference_pu": float(np.max(np.abs(results["F3"].voltage_pu - frozen_voltage))),
        "native_anchor_NPZ_current_max_abs_difference_A": float(np.max(np.abs(results["F3"].phase_current_a - frozen_current))),
        "tap_max_abs_error": float(np.max(np.abs(results["F3"].regulator_taps - voltage["regulator_taps"]))),
        "capacitor_mismatch_count": int(np.sum(results["F3"].capacitor_states != voltage["capacitor_states"])),
    }
    if max(reproduction["frozen_V29R1_Fresh_summary_max_abs_error"], reproduction["tap_max_abs_error"]) > REPRODUCTION_TOLERANCE or reproduction["capacitor_mismatch_count"]:
        raise RuntimeError(f"V29R2_ANCHOR_REPRODUCTION_FAILURE:{day}:{reproduction}")
    f0_f2 = max(
        float(np.max(np.abs(results["F0"].voltage_pu - results["F2"].voltage_pu))),
        float(np.max(np.abs(results["F0"].phase_current_loading_pu - results["F2"].phase_current_loading_pu))),
    )
    f1_f3 = max(
        float(np.max(np.abs(results["F1"].voltage_pu - results["F3"].voltage_pu))),
        float(np.max(np.abs(results["F1"].phase_current_loading_pu - results["F3"].phase_current_loading_pu))),
    )
    if max(f0_f2, f1_f3) > ACCOUNTING_TOLERANCE:
        raise RuntimeError(f"V29R2_ZERO_MESS_IDENTITY_FAILURE:{day}:{f0_f2}:{f1_f3}")
    ledger = _violation_ledger(day, inputs.vintage["timestamps_96"], results["F3"])
    attribution = [_attribution(row, results) for row in ledger]
    if any(abs(float(row["accounting_error"])) > ACCOUNTING_TOLERANCE for row in attribution):
        raise RuntimeError(f"V29R2_COMPONENT_ACCOUNTING_FAILURE:{day}")
    control_rows = []
    for slot, timestamp in enumerate(inputs.vintage["timestamps_96"]):
        row = {
            "day": day, "sample": sample, "slot": slot, "timestamp": timestamp,
            "source_voltage_pu": 1.0,
            "anchor_generation_control_mode": "STATIC_NATIVE_MAXCONTROLITER_100",
            "forensic_replay_control_mode": "FROZEN_ANCHOR_STATE_CONTROL_OFF",
            "anchor_control_converged": bool(results["F3"].convergence[slot]),
        }
        row.update({f"tap_{name}": float(results["F3"].regulator_taps[slot, i]) for i, name in enumerate(REGULATORS)})
        row.update({f"capacitor_{name}": int(results["F3"].capacitor_states[slot, i]) for i, name in enumerate(CAPACITORS)})
        control_rows.append(row)
    construction = {
        "day": day,
        "background_identity_max": max(float(value) for value in background.evidence["identity_maxima"].values()),
        "demand_operational_scale_max_error_kw": max(
            abs(
                float(row["operational_after_alpha_kw"])
                - ALPHA_GRID * float(inputs.vintage["demand_mw_96"][index]) * IEEE123_NATIVE_P_KW / P95_REFERENCE_MW
            ) for index, row in enumerate(background.evidence["slot_totals"])
        ),
        "pv_scale_max_error_kw": max(
            abs(
                float(row["pv_after_alpha_kw"])
                - ALPHA_GRID * float(inputs.vintage["pv_mw_96"][index]) / PV_REFERENCE_MAX_MW * PV_CAPACITY_EXPECTED_KW
            ) for index, row in enumerate(background.evidence["slot_totals"])
        ),
        "AIDC_P_Q_identity_max_error_kvar": float(np.max(np.abs(
            trajectories["F3"].pcc_q_kvar - trajectories["F3"].pcc_p_kw * PF_TAN
        ))),
        "AIDC_P_nonnegative": bool(np.all(trajectories["F3"].pcc_p_kw >= 0.0)),
        "MESS_maintenance_P_max_abs_kw": float(np.max(np.abs(trajectories["F2"].mess_p_kw))),
        "MESS_maintenance_Q_max_abs_kvar": float(np.max(np.abs(trajectories["F2"].mess_q_kvar))),
        "line_phase_count": int(sum(kind == "line" for kind in results["F3"].branch_kinds)),
        "transformer_phase_count": int(sum(kind == "transformer" for kind in results["F3"].branch_kinds)),
        "convergence_count_F0_F3": sum(int(result.convergence.sum()) for result in results.values()),
    }
    voltage.close()
    return {
        "day": day, "sample": sample,
        "results": [_result_row(day, sample, result) for result in results.values()],
        "ledger": ledger, "attribution": attribution,
        "day_classification": _day_classification(attribution) if attribution else "NON_VIOLATION_CONTROL",
        "reproduction": reproduction, "F0_F2_identity_max_error": f0_f2,
        "F1_F3_identity_max_error": f1_f3, "control_rows": control_rows,
        "construction": construction,
    }


def _construction_snapshot(repo: Path, source_audit: Mapping[str, object], day_rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    assets = FeederAssets.from_repo(repo)
    asset_shas = assets.sha256
    v29r1 = evidence_root(repo)
    production_assets = FeederAssets.from_repo(v29r1).sha256
    if asset_shas != production_assets:
        raise RuntimeError("V29R2_ELECTRICAL_ASSET_SHA_MISMATCH")
    max_fields = (
        "background_identity_max", "demand_operational_scale_max_error_kw",
        "pv_scale_max_error_kw", "AIDC_P_Q_identity_max_error_kvar",
        "MESS_maintenance_P_max_abs_kw", "MESS_maintenance_Q_max_abs_kvar",
    )
    maxima = {field: max(float(row[field]) for row in day_rows) for field in max_fields}
    pass_status = max(maxima.values()) <= 1e-8
    return {
        "artifact_id": "V29R2_ANCHOR_ELECTRICAL_CONSTRUCTION_AUDIT_V1",
        "status": "PASS" if pass_status else "FAIL",
        "deterministic_implementation_defect_found": False if pass_status else True,
        "source_hash_audit": dict(source_audit),
        "numerical_identity_maxima": maxima,
        "demand_scaling_formula": "alpha_grid * AEMO_demand_MW * 3490 / 7100.2615",
        "PV_scaling_formula": "alpha_grid * AEMO_rooftop_PV_MW / 4021.226 * 698.000002861023",
        "PV_sign_convention": "gross load minus positive PV generator equals net load",
        "AIDC_sign_convention": "positive P/Q is consumption at dedicated PCC",
        "AIDC_power_factor": .95,
        "AIDC_Q_formula": "Q=P*tan(acos(.95))",
        "C1_PCC_conversion": "unchanged V24T endpoint-secant family inherited from V29R1",
        "source_voltage_pu": 1.0,
        "regulator_anchor_mode": "native static controls, maxcontroliter=100",
        "regulator_replay_mode": "frozen D1 anchor taps, RegControls disabled, controlmode=off",
        "capacitor_replay_mode": "frozen D1 anchor states",
        "IEEE123_and_rating_asset_sha256": asset_shas,
        "April_production_asset_sha256": production_assets,
        "April_numerical_construction_contract_identity": asset_shas == production_assets,
        "rating_change_count": 0, "source_scaling_change_count": 0,
        "regulator_or_capacitor_authority_change_count": 0,
    }


def run(repo: Path, *, workers: int = 4) -> dict[str, object]:
    repo = repo.resolve()
    git_state = _verify_authority(repo)
    prechange = _prechange_manifest(repo, git_state)
    source_audit, _selected = _source_hash_audit(repo)
    days = tuple(VIOLATION_DAYS) + control_days()
    samples = {day: "VIOLATION" if day in VIOLATION_DAYS else "CONTROL" for day in days}
    outputs = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_day_worker, str(repo), day, samples[day]): day for day in days}
        for index, future in enumerate(as_completed(futures), start=1):
            day = futures[future]
            outputs.append(future.result())
            print(json.dumps({"phase": "anchor-forensic", "day": day, "complete": index, "total": len(days)}), flush=True)
    outputs.sort(key=lambda row: str(row["day"]))
    all_results = [row for output in outputs for row in output["results"]]
    ledger = [row for output in outputs if output["sample"] == "VIOLATION" for row in output["ledger"]]
    attribution = [row for output in outputs if output["sample"] == "VIOLATION" for row in output["attribution"]]
    controls = [row for row in all_results if row["sample"] == "CONTROL"]
    control_devices = [row for output in outputs for row in output["control_rows"]]
    observed_violation_days = sorted({str(row["day"]) for row in ledger})
    if observed_violation_days != list(VIOLATION_DAYS):
        raise RuntimeError(f"V29R2_F3_VIOLATION_DAY_SET_MISMATCH:{observed_violation_days}")
    out = repo / OUT_REL
    write_csv(out / "V29R2_ANCHOR_VIOLATION_LEDGER.csv", ledger)
    write_csv(out / "V29R2_ANCHOR_F0_F3_OPENDSS_RESULTS.csv", all_results)
    write_csv(out / "V29R2_ANCHOR_COMPONENT_ATTRIBUTION.csv", attribution)
    write_csv(out / "V29R2_ANCHOR_CONTROL_DEVICE_AUDIT.csv", control_devices)
    write_csv(out / "V29R2_ANCHOR_CONTROL_DAY_RESULTS.csv", controls)
    construction = _construction_snapshot(repo, source_audit, [row["construction"] for row in outputs])
    write_json(out / "V29R2_ANCHOR_ELECTRICAL_CONSTRUCTION_AUDIT.json", construction)
    classifications = {str(row["day"]): str(row["day_classification"]) for row in outputs if row["sample"] == "VIOLATION"}
    classes = set(classifications.values())
    if classes == {"BACKGROUND_DRIVEN"}:
        overall = "V29R2_ANCHOR_SOURCE_CORRECT_BACKGROUND_STRESS"
    elif classes <= {"BACKGROUND_DRIVEN", "AIDC_REFERENCE_DRIVEN", "MIXED"}:
        overall = "V29R2_ANCHOR_SOURCE_CORRECT_MIXED_STRESS"
    else:
        overall = "V29R2_ANCHOR_CAUSE_UNRESOLVED"
    max_repro_summary = max(float(row["reproduction"]["frozen_V29R1_Fresh_summary_max_abs_error"]) for row in outputs)
    max_native_v = max(float(row["reproduction"]["native_anchor_NPZ_voltage_max_abs_difference_pu"]) for row in outputs)
    max_native_i = max(float(row["reproduction"]["native_anchor_NPZ_current_max_abs_difference_A"]) for row in outputs)
    max_accounting = max(abs(float(row["accounting_error"])) for row in attribution)
    per_day_slots = {
        day: len({int(row["slot"]) for row in ledger if row["day"] == day}) for day in VIOLATION_DAYS
    }
    review = {
        "artifact_id": "V29R2_ANCHOR_FORENSIC_FINAL_REVIEW_V1",
        "RESULT_CLASSIFICATION": overall,
        "status": "PASS" if overall.startswith("V29R2_ANCHOR_SOURCE_CORRECT") else "FAIL",
        "proceed_beyond_Stage_A": overall in {
            "V29R2_ANCHOR_SOURCE_CORRECT_BACKGROUND_STRESS",
            "V29R2_ANCHOR_SOURCE_CORRECT_AIDC_DRIVEN_STRESS",
            "V29R2_ANCHOR_SOURCE_CORRECT_MIXED_STRESS",
        },
        "source_and_materialization_hashes": source_audit,
        "violation_day_count": len(observed_violation_days),
        "violation_days": observed_violation_days,
        "non_violation_control_selection": {
            "rule": f"lowest SHA256({CONTROL_SELECTION_SALT}:day), then chronological output order",
            "days": list(control_days()), "count": len(control_days()),
        },
        "day_classifications": classifications,
        "violating_slot_count_by_day": per_day_slots,
        "F3_reproduction": {
            "status": "PASS", "tolerance": REPRODUCTION_TOLERANCE,
            "frozen_V29R1_Fresh_summary_max_abs_error": max_repro_summary,
            "native_anchor_NPZ_voltage_max_abs_difference_pu": max_native_v,
            "native_anchor_NPZ_current_max_abs_difference_A": max_native_i,
        },
        "component_accounting": {"status": "PASS", "maximum_abs_error": max_accounting},
        "MESS_maintenance_authority": "P=Q=0 in frozen D1 anchor; therefore F2 equals F0",
        "electrical_construction_audit": construction,
        "scientific_parameter_changes": 0,
        "April_rows_used": 0,
        "prechange_manifest": prechange,
    }
    write_json(out / "V29R2_ANCHOR_FORENSIC_FINAL_REVIEW.json", review)
    md = f"""# V29R2 pre-April anchor-physics forensic

RESULT CLASSIFICATION: `{overall}`

- Source/materialization hashes: PASS (90 days, 2,250 GFS leads, 13,500 messages)
- F3 frozen V29R1 Fresh-summary reproduction: PASS; maximum field error `{max_repro_summary:.3e}`
- Native-anchor NPZ vs frozen-state replay diagnostic: voltage `{max_native_v:.3e}` pu, current `{max_native_i:.3e}` A
- Electrical construction audit: `{construction['status']}`; deterministic defect found: `{construction['deterministic_implementation_defect_found']}`
- Violation population: 26/26 exact frozen days
- Non-violation controls: {', '.join(control_days())}
- Component accounting maximum error: `{max_accounting:.3e}`

The F0--F3 experiment preserved the exact feeder, source scaling, PF, PCC, ratings,
native D1 tap/cap acquisition, and frozen-state replay semantics.  The frozen D1 anchor
contains MESS P=Q=0, so F2 is exactly F0 and F3 is exactly F1.  No altered-control
experiment was promoted to authority.

Proceed beyond Stage A: `{review['proceed_beyond_Stage_A']}`.
"""
    (out / "V29R2_ANCHOR_FORENSIC_FINAL_REVIEW.md").write_text(md, encoding="utf-8", newline="\n")
    if not review["proceed_beyond_Stage_A"]:
        raise RuntimeError(overall)
    return review
