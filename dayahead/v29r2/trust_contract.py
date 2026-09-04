"""Prospectively freeze the V29R2 model-fidelity trust contract."""

from __future__ import annotations

import json
from pathlib import Path

from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v29r1.authority import CANDIDATE_RHOS, CERTIFICATION_DAYS
from dayahead.v29r1.source_resume import sha256_file, write_json


OUT_REL = Path("dayahead/artifacts/v29r2_anchor_aware_trust_noregret")


def freeze(repo: Path) -> dict[str, object]:
    out = repo / OUT_REL
    forensic_path = out / "V29R2_ANCHOR_FORENSIC_FINAL_REVIEW.json"
    forensic = json.loads(forensic_path.read_text(encoding="utf-8"))
    if forensic["status"] != "PASS" or not forensic["proceed_beyond_Stage_A"]:
        raise RuntimeError("V29R2_TRUST_CONTRACT_WITHOUT_ANCHOR_FORENSIC_PASS")
    payload = {
        "artifact_id": "V29R2_TRUST_CERT_CONTRACT_V1",
        "status": "FROZEN_BEFORE_CANDIDATE_EXECUTION",
        "prospective_lineage": "codex/v29r2-anchor-aware-trust-noregret",
        "scientific_parent": "105b688d90a9ea792cb3ced60773c1c58b6888dc",
        "anchor_forensic_classification": forensic["RESULT_CLASSIFICATION"],
        "anchor_forensic_sha256": sha256_file(forensic_path),
        "certification_population": {
            "start": CERTIFICATION_DAYS[0], "end": CERTIFICATION_DAYS[-1],
            "day_count": len(CERTIFICATION_DAYS), "April_rows": 0,
        },
        "candidate_rho_AIDC": list(CANDIDATE_RHOS),
        "candidate_set_change_count": 0,
        "model_fidelity_gates": {
            "current_error_pu": {"mean_max": .01, "p95_max": .02, "max_max": .03},
            "voltage_error_pu": {"mean_max": .003, "p95_max": .005, "max_max": .01},
            "C1": "existing one-percent site and aggregate rating error authority",
            "all_Fresh_OpenDSS_trajectories_converge": True,
            "finite_arrays": True,
            "slot_line_phase_mapping_identity": True,
        },
        "selection_rule": "largest frozen candidate passing every Jan-Mar model-fidelity and C1 gate",
        "objective_improvement_is_selection_input": False,
        "anchor_absolute_feasibility_is_selection_input": False,
        "April_performance_is_selection_input": False,
        "absolute_physical_state_role": "DIAGNOSTIC_DURING_TRUST_CERT; MANDATORY_FOR_CLAIMED_B0_B1_B2_B3_SCHEDULES",
        "operational_AC_gate": {
            "separate_from_model_fidelity": True,
            "report_absolute_violations": True,
            "report_new_and_resolved_violations": True,
            "report_incremental_relief_vs_matched_baseline": True,
        },
        "unchanged_authorities": {
            "AIDC_scale": True, "site_placement_and_weights": True, "PF_0p95": True,
            "C1_model_family": True, "IEEE123_feeder": True, "ratings": True,
            "regulator_and_capacitor_authority": True, "MESS_ratings": True,
            "rack_capacity": True, "PARTIAL_shared_status": True, "objective": True,
            "forecast_pipeline_and_source_scaling": True,
        },
        "fresh_independent_recertification_required": True,
        "old_V29R1_sweep_may_be_reclassified_as_authority": False,
    }
    payload["contract_payload_sha256"] = canonical_sha256(payload)
    write_json(out / "V29R2_TRUST_CERT_CONTRACT.json", payload)
    return payload
