"""Fresh V29R2 Jan--Mar model-fidelity trust recertification.

Absolute feeder feasibility is reported separately from the prospective
model-fidelity selection gate.  Frozen V29R1 sources and D1 anchors are
read-only inputs; every OpenDSS trajectory in this module is newly executed.
"""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import numpy as np

from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
from dayahead.grid_background_v16_2 import build_authority_background_binding
from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.c1_certificate import summarize as summarize_c1
from dayahead.v28r2.electrical_context import ElectricalContext, portable_background_paths, source_root
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v29r1.authority import CANDIDATE_RHOS, CERTIFICATION_DAYS
from dayahead.v29r1.source_resume import sha256_file, write_csv, write_json
from dayahead.v29r1.trust_certification import (
    C1_AGGREGATE_RATING_KW,
    C1_SITE_RATING_KW,
    DIRECTIONAL_PROBE_FRACTION,
    _direction,
    _inputs,
    _trajectory,
)

from .anchor_forensic import OUT_REL, V29R1_SOURCE_REL, evidence_root


TRUST_FREEZE_COMMIT = "be65408dba6ade0d1dacfa6f0b2525f5b37bc87c"
V29R2_BRANCH = "codex/v29r2-anchor-aware-trust-noregret"
VOLTAGE_TOLERANCE = {"mean": 0.003, "p95": 0.005, "max": 0.01}
CURRENT_TOLERANCE = {"mean": 0.01, "p95": 0.02, "max": 0.03}
LIMIT_TOLERANCE = 1e-9


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def verify_frozen_execution_head(repo: Path) -> dict[str, object]:
    """Fail closed unless the prospective contract is committed and unchanged."""

    contract_path = repo / OUT_REL / "V29R2_TRUST_CERT_CONTRACT.json"
    state = {
        "branch": _git(repo, "branch", "--show-current"),
        "head": _git(repo, "rev-parse", "HEAD"),
        "status_short": _git(repo, "status", "--short"),
        "contract_tracked": bool(_git(repo, "ls-files", str(contract_path.relative_to(repo)).replace("\\", "/"))),
    }
    ancestor = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", TRUST_FREEZE_COMMIT, "HEAD"],
        check=False,
    ).returncode == 0
    if state["branch"] != V29R2_BRANCH or state["status_short"] or not state["contract_tracked"] or not ancestor:
        raise RuntimeError(f"V29R2_TRUST_EXECUTION_HEAD_NOT_FROZEN:{state}:ancestor={ancestor}")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    payload_hash = str(contract.pop("contract_payload_sha256"))
    if canonical_sha256(contract) != payload_hash:
        raise RuntimeError("V29R2_TRUST_CONTRACT_PAYLOAD_SHA_MISMATCH")
    forensic_path = repo / OUT_REL / "V29R2_ANCHOR_FORENSIC_FINAL_REVIEW.json"
    if sha256_file(forensic_path) != contract["anchor_forensic_sha256"]:
        raise RuntimeError("V29R2_TRUST_CONTRACT_FORENSIC_SHA_MISMATCH")
    state.update({
        "freeze_commit": TRUST_FREEZE_COMMIT,
        "freeze_commit_is_ancestor": True,
        "contract_file_sha256": sha256_file(contract_path),
        "contract_payload_sha256": payload_hash,
        "old_V29R1_sweep_used_as_authority": False,
    })
    return state


def _metrics(predicted: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    error = np.abs(np.asarray(predicted, dtype=float) - np.asarray(actual, dtype=float))
    return {
        "max": float(error.max()),
        "p95": float(np.quantile(error, 0.95)),
        "mean": float(error.mean()),
    }


def _mapping(result: object) -> tuple[object, ...]:
    return (
        tuple(result.node_names), tuple(result.node_phases),
        tuple(result.branch_names), tuple(result.branch_phases), tuple(result.branch_kinds),
        tuple(np.asarray(result.voltage_pu).shape),
        tuple(np.asarray(result.phase_current_loading_pu).shape),
    )


def _finite(result: object) -> bool:
    tx_mask = np.asarray([kind == "transformer" for kind in result.branch_kinds])
    arrays: Iterable[np.ndarray] = (
        result.voltage_pu, result.phase_current_a, result.phase_current_loading_pu,
        result.losses_kw_kvar, result.regulator_taps, result.capacitor_states,
        result.transformer_total_kva_loading_pu[:, tx_mask],
    )
    return all(bool(np.isfinite(array).all()) for array in arrays)


def _violation_keys(result: object) -> set[tuple[object, ...]]:
    keys: set[tuple[object, ...]] = set()
    for slot, node in zip(*np.where(result.voltage_pu > 1.05 + LIMIT_TOLERANCE)):
        keys.add(("VOLTAGE_HIGH", int(slot), result.node_names[node], result.node_phases[node]))
    for slot, node in zip(*np.where(result.voltage_pu < .95 - LIMIT_TOLERANCE)):
        keys.add(("VOLTAGE_LOW", int(slot), result.node_names[node], result.node_phases[node]))
    for slot, branch in zip(*np.where(result.phase_current_loading_pu > 1.0 + LIMIT_TOLERANCE)):
        keys.add((f"{result.branch_kinds[branch].upper()}_PHASE_CURRENT", int(slot), result.branch_names[branch], result.branch_phases[branch]))
    tx_mask = np.asarray([kind == "transformer" for kind in result.branch_kinds])
    tx_indices = np.flatnonzero(tx_mask)
    for slot, local in zip(*np.where(result.transformer_total_kva_loading_pu[:, tx_mask] > 1.0 + LIMIT_TOLERANCE)):
        branch = int(tx_indices[local])
        keys.add(("TRANSFORMER_TOTAL_KVA", int(slot), result.branch_names[branch], result.branch_phases[branch]))
    return keys


def _severity(result: object) -> dict[str, float]:
    line_mask = np.asarray([kind == "line" for kind in result.branch_kinds])
    tx_mask = ~line_mask
    return {
        "gV_high_pu": max(0.0, float(np.max(result.voltage_pu)) - 1.05),
        "gV_low_pu": max(0.0, .95 - float(np.min(result.voltage_pu))),
        "gI_line_pu": max(0.0, float(np.max(result.phase_current_loading_pu[:, line_mask])) - 1.0),
        "gI_transformer_phase_pu": max(0.0, float(np.max(result.phase_current_loading_pu[:, tx_mask])) - 1.0),
        "gS_transformer_pu": max(0.0, float(np.max(result.transformer_total_kva_loading_pu[:, tx_mask])) - 1.0),
    }


def _hidden_large_error_mismatches(
    predicted_voltage: np.ndarray,
    actual_voltage: np.ndarray,
    predicted_current: np.ndarray,
    actual_current: np.ndarray,
) -> int:
    pred_v_safe = (predicted_voltage >= .95) & (predicted_voltage <= 1.05)
    actual_v_bad = (actual_voltage < .95 - LIMIT_TOLERANCE) | (actual_voltage > 1.05 + LIMIT_TOLERANCE)
    v_large = np.abs(predicted_voltage - actual_voltage) > VOLTAGE_TOLERANCE["max"]
    pred_i_safe = predicted_current <= 1.0
    actual_i_bad = actual_current > 1.0 + LIMIT_TOLERANCE
    i_large = np.abs(predicted_current - actual_current) > CURRENT_TOLERANCE["max"]
    return int(np.sum(pred_v_safe & actual_v_bad & v_large) + np.sum(pred_i_safe & actual_i_bad & i_large))


def _day_certify(repo: Path, day: str) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
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
        inputs.vintage, background, binding, anchor_path, "V29R2_FRESH_MODEL_FIDELITY_CERT",
    )
    context = ElectricalContext(legacy, voltage, None, source, anchor_path, anchor_path)
    direction = _direction(inputs)
    anchor = run_fresh_opendss(
        repo=repo, context=context, voltage=voltage,
        trajectory=_trajectory(day, "V29R2_TRUST_ANCHOR", inputs.reference_pcc_kw),
    )
    plus = run_fresh_opendss(
        repo=repo, context=context, voltage=voltage,
        trajectory=_trajectory(day, "V29R2_TRUST_PROBE_PLUS", inputs.reference_pcc_kw + DIRECTIONAL_PROBE_FRACTION * direction),
    )
    minus = run_fresh_opendss(
        repo=repo, context=context, voltage=voltage,
        trajectory=_trajectory(day, "V29R2_TRUST_PROBE_MINUS", inputs.reference_pcc_kw - DIRECTIONAL_PROBE_FRACTION * direction),
    )
    voltage_derivative = (plus.voltage_pu - minus.voltage_pu) / (2.0 * DIRECTIONAL_PROBE_FRACTION)
    current_derivative = (plus.phase_current_loading_pu - minus.phase_current_loading_pu) / (2.0 * DIRECTIONAL_PROBE_FRACTION)
    line_mask = np.asarray([kind == "line" for kind in anchor.branch_kinds])
    mapping_reference = _mapping(anchor)
    probe_mapping_identity = _mapping(plus) == mapping_reference == _mapping(minus)
    anchor_keys = _violation_keys(anchor)
    anchor_severity = _severity(anchor)
    c1 = summarize_c1(inputs.coefficients, site_rating_kw=C1_SITE_RATING_KW, aggregate_rating_kw=C1_AGGREGATE_RATING_KW)
    fidelity_rows: list[dict[str, object]] = []
    c1_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []
    for rho in CANDIDATE_RHOS:
        candidate_pcc = inputs.reference_pcc_kw + float(rho) * direction
        trajectory = _trajectory(day, f"V29R2_TRUST_RHO_{rho:.2f}", candidate_pcc)
        result = run_fresh_opendss(repo=repo, context=context, voltage=voltage, trajectory=trajectory)
        predicted_voltage = anchor.voltage_pu + float(rho) * voltage_derivative
        predicted_current = anchor.phase_current_loading_pu + float(rho) * current_derivative
        v_error = _metrics(predicted_voltage, result.voltage_pu)
        i_error = _metrics(predicted_current[:, line_mask], result.phase_current_loading_pu[:, line_mask])
        converged = bool(np.asarray(result.convergence, dtype=bool).all())
        finite = _finite(result) and bool(np.isfinite(predicted_voltage).all()) and bool(np.isfinite(predicted_current).all())
        mapping_identity = probe_mapping_identity and _mapping(result) == mapping_reference
        sign_consistent = bool(
            np.all(candidate_pcc >= inputs.pcc_min_kw - 1e-8)
            and np.all(candidate_pcc <= inputs.pcc_max_kw + 1e-8)
            and np.allclose(trajectory.pcc_q_kvar, trajectory.pcc_p_kw * np.tan(np.arccos(.95)), atol=1e-10)
        )
        hidden = _hidden_large_error_mismatches(
            predicted_voltage, result.voltage_pu,
            predicted_current[:, line_mask], result.phase_current_loading_pu[:, line_mask],
        )
        errors_pass = (
            all(v_error[key] <= VOLTAGE_TOLERANCE[key] for key in VOLTAGE_TOLERANCE)
            and all(i_error[key] <= CURRENT_TOLERANCE[key] for key in CURRENT_TOLERANCE)
        )
        fidelity_pass = errors_pass and converged and finite and mapping_identity and sign_consistent and hidden == 0
        fidelity_rows.append({
            "day": day, "rho_AIDC": rho, "status": "PASS" if fidelity_pass else "FAIL",
            "Fresh_independent_execution": True,
            "OpenDSS_solve_count": int(np.asarray(result.convergence, dtype=bool).sum()),
            "voltage_error_mean_pu": v_error["mean"], "voltage_error_p95_pu": v_error["p95"], "voltage_error_max_pu": v_error["max"],
            "current_error_mean_pu": i_error["mean"], "current_error_p95_pu": i_error["p95"], "current_error_max_pu": i_error["max"],
            "error_tolerances_pass": errors_pass, "all_slots_converged": converged,
            "finite_arrays": finite, "slot_line_phase_mapping_identity": mapping_identity,
            "P_Q_sign_consistency": sign_consistent,
            "hidden_large_error_planning_safe_AC_violation_count": hidden,
            "absolute_physical_feasibility_used_for_status": False,
            "April_rows_used": 0,
        })
        c1_rows.append({
            "day": day, "rho_AIDC": rho, "status": c1["status"],
            "coefficient_count": c1["coefficient_count"],
            "minimum_conservatism_kw": c1["minimum_conservatism_kw"],
            "maximum_site_error_kw": c1["maximum_site_error_kw"],
            "maximum_aggregate_error_kw": c1["maximum_aggregate_error_kw"],
            "site_error_threshold_kw": c1["site_error_threshold_kw"],
            "aggregate_error_threshold_kw": c1["aggregate_error_threshold_kw"],
            "April_rows_used": 0,
        })
        candidate_keys = _violation_keys(result)
        candidate_severity = _severity(result)
        diagnostic_rows.append({
            "day": day, "rho_AIDC": rho,
            **{f"anchor_{key}": value for key, value in anchor_severity.items()},
            **{f"candidate_{key}": value for key, value in candidate_severity.items()},
            "anchor_absolute_violation_count": len(anchor_keys),
            "candidate_absolute_violation_count": len(candidate_keys),
            "candidate_new_violation_count": len(candidate_keys - anchor_keys),
            "candidate_resolved_violation_count": len(anchor_keys - candidate_keys),
            "absolute_physical_feasibility_is_selection_input": False,
            "April_rows_used": 0,
        })
    voltage.close()
    return fidelity_rows, c1_rows, diagnostic_rows


def _worker(repo_text: str, day: str) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    return _day_certify(Path(repo_text), day)


def certify(repo: Path, *, workers: int = 4) -> dict[str, object]:
    execution = verify_frozen_execution_head(repo)
    v29r1 = evidence_root(repo)
    v29r1_before = {
        "head": _git(v29r1, "rev-parse", "HEAD"),
        "status_short": _git(v29r1, "status", "--short"),
    }
    fidelity_rows: list[dict[str, object]] = []
    c1_rows: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_worker, str(repo.resolve()), day): day for day in CERTIFICATION_DAYS}
        for index, future in enumerate(as_completed(futures), start=1):
            day = futures[future]
            fresh, c1, diagnostic = future.result()
            fidelity_rows.extend(fresh)
            c1_rows.extend(c1)
            diagnostics.extend(diagnostic)
            print(json.dumps({"phase": "v29r2-trust-cert", "day": day, "complete": index, "total": 90}), flush=True)
    key = lambda row: (str(row["day"]), float(row["rho_AIDC"]))
    fidelity_rows.sort(key=key); c1_rows.sort(key=key); diagnostics.sort(key=key)
    out = repo / OUT_REL
    write_csv(out / "V29R2_TRUST_CERT_FIDELITY_RESULTS.csv", fidelity_rows)
    write_csv(out / "V29R2_TRUST_CERT_C1_RESULTS.csv", c1_rows)
    write_csv(out / "V29R2_TRUST_CERT_ANCHOR_DIAGNOSTICS.csv", diagnostics)
    candidates: list[dict[str, object]] = []
    for rho in CANDIDATE_RHOS:
        fidelity = [row for row in fidelity_rows if float(row["rho_AIDC"]) == rho]
        c1 = [row for row in c1_rows if float(row["rho_AIDC"]) == rho]
        diagnostic = [row for row in diagnostics if float(row["rho_AIDC"]) == rho]
        fidelity_pass = len(fidelity) == 90 and all(row["status"] == "PASS" for row in fidelity)
        c1_pass = len(c1) == 90 and all(row["status"] == "PASS" for row in c1)
        candidates.append({
            "rho_AIDC": rho, "status": "PASS" if fidelity_pass and c1_pass else "FAIL",
            "certification_day_count": len({row["day"] for row in fidelity}),
            "Fresh_candidate_trajectory_count": len(fidelity),
            "Fresh_candidate_slot_solve_count": sum(int(row["OpenDSS_solve_count"]) for row in fidelity),
            "model_fidelity_all_days_pass": fidelity_pass, "C1_all_days_pass": c1_pass,
            "maximum_voltage_error_pu": max(float(row["voltage_error_max_pu"]) for row in fidelity),
            "maximum_current_error_pu": max(float(row["current_error_max_pu"]) for row in fidelity),
            "anchor_violation_day_count": len({row["day"] for row in diagnostic if int(row["anchor_absolute_violation_count"]) > 0}),
            "candidate_violation_day_count": len({row["day"] for row in diagnostic if int(row["candidate_absolute_violation_count"]) > 0}),
            "candidate_new_violation_count": sum(int(row["candidate_new_violation_count"]) for row in diagnostic),
            "candidate_resolved_violation_count": sum(int(row["candidate_resolved_violation_count"]) for row in diagnostic),
            "absolute_physical_feasibility_used_for_selection": False,
            "objective_improvement_used_for_selection": False, "April_rows_used": 0,
        })
    write_csv(out / "V29R2_TRUST_CERT_CANDIDATES.csv", candidates)
    passing = [float(row["rho_AIDC"]) for row in candidates if row["status"] == "PASS"]
    selected = max(passing) if passing else None
    v29r1_after = {
        "head": _git(v29r1, "rev-parse", "HEAD"),
        "status_short": _git(v29r1, "status", "--short"),
    }
    if v29r1_after != v29r1_before:
        raise RuntimeError(f"V29R2_TRUST_CERT_MODIFIED_V29R1:{v29r1_before}:{v29r1_after}")
    decision = {
        "artifact_id": "V29R2_TRUST_CERT_DECISION_V1",
        "status": "PASS" if selected is not None else "V29R2_BLOCKED_NO_MODEL_FIDELITY_CERTIFIED_RHO",
        "selected_rho_AIDC": selected, "candidate_set": list(CANDIDATE_RHOS),
        "selection_rule": "largest prospectively frozen candidate passing every Jan-Mar model-fidelity and C1 gate",
        "selection_inputs": ["Fresh_OpenDSS_model_fidelity", "C1_one_percent_authority"],
        "excluded_selection_inputs": ["anchor_absolute_feasibility", "candidate_absolute_feasibility", "objective_improvement", "April_performance"],
        "contract_execution": execution,
        "certification_population": {"start": CERTIFICATION_DAYS[0], "end": CERTIFICATION_DAYS[-1], "day_count": 90},
        "voltage_tolerance": VOLTAGE_TOLERANCE, "current_tolerance": CURRENT_TOLERANCE,
        "directional_probe_fraction": DIRECTIONAL_PROBE_FRACTION,
        "probe_family": "FROZEN_SIMULTANEOUS_ALTERNATING_LOW_HIGH_ENDPOINT",
        "fresh_independent_recertification": True, "old_V29R1_sweep_reclassified": False,
        "April_rows_used": 0, "April_performance_used_for_selection": False,
        "objective_improvement_used_for_selection": False,
        "Fresh_OpenDSS_execution": {
            "anchor_trajectory_count": 90, "directional_probe_trajectory_count": 180,
            "candidate_trajectory_count": len(fidelity_rows), "total_trajectory_count": 270 + len(fidelity_rows),
            "sequential_slot_solves_per_trajectory": 96,
            "total_sequential_slot_solves": (270 + len(fidelity_rows)) * 96,
        },
        "V29R1_read_only_before_after": {"before": v29r1_before, "after": v29r1_after, "identity": True},
        "candidate_results": candidates,
        "downstream_science_authorized": selected is not None,
        "required_statement": (
            f"V29R2 selected rho_AIDC={selected:.2f} using a freshly rerun pre-April certification under the prospectively frozen V29R2 contract."
            if selected is not None else "No rho_AIDC passed the frozen V29R2 model-fidelity and C1 gates."
        ),
    }
    write_json(out / "V29R2_TRUST_CERT_DECISION.json", decision)
    lines = [
        "# V29R2 Trust Certification Final Review", "",
        f"Status: **{decision['status']}**", "",
        "The trust selection gate used only Fresh OpenDSS model fidelity and the frozen C1 one-percent authority. "
        "Absolute anchor and candidate violations are retained in the diagnostic artifact and were not selection inputs.", "",
        f"Fresh execution: {270 + len(fidelity_rows)} trajectories and {(270 + len(fidelity_rows)) * 96:,} sequential slot solves; April rows used: 0.", "",
    ]
    for row in candidates:
        lines.append(
            f"- rho={float(row['rho_AIDC']):.2f}: {row['status']}; fidelity={row['model_fidelity_all_days_pass']}; "
            f"C1={row['C1_all_days_pass']}; max voltage error={float(row['maximum_voltage_error_pu']):.9g} pu; "
            f"max current error={float(row['maximum_current_error_pu']):.9g} pu."
        )
    lines.extend(["", decision["required_statement"], ""])
    (out / "V29R2_TRUST_CERT_FINAL_REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    if selected is None:
        raise RuntimeError("V29R2_BLOCKED_NO_MODEL_FIDELITY_CERTIFIED_RHO")
    return decision
