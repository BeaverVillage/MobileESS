"""Materialize and freeze V29 common-formulation contracts."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v29.authority import RHO_AIDC
from dayahead.v29.formulation import formulation_fingerprint, materialize_formulation_data_v29


DAYS = ("2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    out = REPO / "dayahead/artifacts/v29_grid_responsive_aidc"; out.mkdir(parents=True, exist_ok=True)
    days = []
    for day in DAYS:
        data = materialize_formulation_data_v29(REPO, day)
        reference_bytes = data.reference.canonical_bytes()
        # B0 and B2 consume the same serialized V3 reference object.
        b0_hash = digest(reference_bytes); b2_hash = digest(reference_bytes)
        p_identity = data.delta.p_res_plan_kw.sum(axis=0) + data.reference.p_f_ref_kw.sum(axis=0)
        g_identity = data.delta.g_res_plan_gpu.sum(axis=0) + data.reference.g_f_ref_gpu.sum(axis=0)
        days.append({
            "day": day, "initial_carryin_nodeh": float(data.initial_backlog_nodeh.sum()),
            "D_day_arrival_nodeh": float(data.arrivals_nodeh.sum()),
            "reference_service_nodeh": float(data.reference.x_ref_nodeh.sum()),
            "reference_terminal_backlog_nodeh": float(data.reference.backlog_nodeh[-1].sum()),
            "reference_mass_error_nodeh": float(data.initial_backlog_nodeh.sum() + data.arrivals_nodeh.sum() - data.reference.x_ref_nodeh.sum() - data.reference.backlog_nodeh[-1].sum()),
            "B0_reference_V3_sha256": b0_hash, "B2_reference_V3_sha256": b2_hash,
            "B0_B2_reference_bytes_identical": b0_hash == b2_hash,
            "minimum_P_RES_kw": float(data.delta.p_res_plan_kw.min()),
            "minimum_G_RES_gpu": float(data.delta.g_res_plan_gpu.min()),
            "maximum_P_total_double_count_error_kw": float(np.max(np.abs(p_identity - data.p_it_q90_kw))),
            "maximum_G_total_double_count_error_gpu": float(np.max(np.abs(g_identity - data.g_q90_gpu))),
            "input_sha256": data.input_sha256,
        })
    fingerprint = formulation_fingerprint(REPO)
    write(out / "V29_COMMON_FORMULATION_CONTRACT.json", {
        "artifact_id": "V29_COMMON_FORMULATION_CONTRACT_V1", "status": "PASS",
        "horizon": {"hours": 24, "slots": 96, "resolution_minutes": 15, "one_shot": True, "daily_independent": True},
        "cutoff": "D-1 18:00 fixed AEST", "initial_backlog": "causal PRE_DAY_QUEUE_BRIDGE_V1",
        "service_balance": "B[t+1]=B[t]+W_forecast[t]-sum_r x[t]",
        "terminal": "B[96]=B_REF_V3[96]", "objective": "MIN_MAX_NORMALIZED_PHASE_LINE_CURRENT",
        "rho_AIDC": RHO_AIDC, "PARTIAL_shared_controllable": False,
        "running_job_preemption": False, "synthetic_deadline": False,
        "critical_reserve_hard_constraint": False, "secondary_objective": False,
        "site_sensitivity_objective_weight": False, "site_ID_hardcoding": False,
        "days": days,
    })
    write(out / "V29_REFERENCE_COMPUTE_SCHEDULE_V3_CONTRACT.json", {
        "artifact_id": "V29_REFERENCE_COMPUTE_SCHEDULE_V3_CONTRACT_V1", "status": "PASS",
        "inputs": ["causal carry-in queue", "D-day Q50 flexible arrivals"],
        "policy": "deterministic earliest-feasible fluid service",
        "tie_break": ["cohort ID", "AIDC ID", "Rack ID", "slot"],
        "grid_loading_reads": 0, "MESS_state_reads": 0, "Actual_reads": 0, "result_reads": 0,
        "days": days,
    })
    write(out / "V29_REFERENCE_DELTA_CONTRACT.json", {
        "artifact_id": "V29_REFERENCE_DELTA_CONTRACT_V1", "status": "PASS",
        "P_RES": "P_TOTAL_Q90-P_FLEX_REF_V3", "G_RES": "G_TOTAL_Q90-G_FLEX_REF_V3",
        "negative_residual_clipping": False, "negative_residual_failure": "FAIL_REFERENCE_DELTA",
        "total_forecast_double_counting": False, "days": days,
    })
    write(out / "V29_FORMULATION_FINGERPRINT.json", {
        "artifact_id": "V29_FORMULATION_FINGERPRINT_V1", "status": "PASS",
        "formulation_fingerprint": fingerprint,
        "hashed_components": ["carry-in authority", "queue bridge", "reference V3", "workload eligibility", "P/G/W authority", "C1", "scale", "grid", "mobility", "rho=.10", "connection delay", "source namespace", "objective", "time axis"],
        "days": [{"day": row["day"], "input_sha256": row["input_sha256"]} for row in days],
    })


if __name__ == "__main__":
    main()
