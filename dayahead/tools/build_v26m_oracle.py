"""Build V26M committed-state oracle ceiling and GO/NO-GO gate."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from dayahead.ml.safe_flex.capacity_timeline import read_observed_capacity_timeline
from dayahead.ml.safe_flex.contracts import (
    ORACLE_SCORE_IMPROVEMENT_MIN,
    ORACLE_SHORTFALL_IMPROVEMENT_MIN,
    ORACLE_SUPPORTED_FRACTION_MIN,
    SCHEDULABLE_KNOWN_SHARE_MIN,
)
from dayahead.ml.safe_flex.oracle_ceiling import evaluate_oracle_cases, summarize_oracle


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"
V25 = REPO / "dayahead/artifacts/v25m_beacon_flex"


def _write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    shares = pd.read_csv(OUT / "V26M_OBSERVABLE_STATE_SHARE_BY_DAY.csv")
    oof = pd.read_csv(V25 / "V25M_CANONICAL_BASELINE_DAILY_OOF.csv")
    capacity = read_observed_capacity_timeline(REPO)
    results = evaluate_oracle_cases(shares, oof, capacity)
    results.to_csv(OUT / "V26M_ORACLE_CEILING_RESULTS.csv", index=False)
    summaries = summarize_oracle(results)
    indexed = {row["case_id"]: row for row in summaries}
    o0, o1 = indexed["O0"], indexed["O1"]
    score_improvement = (o0["primary_normalized_envelope_score"] - o1["primary_normalized_envelope_score"]) / o0["primary_normalized_envelope_score"]
    if o0["reserve_shortfall_GPU_h"] > 0:
        shortfall_improvement = (o0["reserve_shortfall_GPU_h"] - o1["reserve_shortfall_GPU_h"]) / o0["reserve_shortfall_GPU_h"]
    else:
        shortfall_improvement = 0.0
    state = json.loads((OUT / "V26M_STATE_RECONSTRUCTION_SUMMARY.json").read_text(encoding="utf-8"))
    share = json.loads((OUT / "V26M_OBSERVABLE_STATE_SHARE_AUDIT.json").read_text(encoding="utf-8"))
    supported = float(state["mass_supported_fraction"])
    schedulable = float(share["shares"]["rho_K_schedulable"]["mass_weighted_aggregate_share"])
    gate_a = supported >= ORACLE_SUPPORTED_FRACTION_MIN
    gate_b = score_improvement >= ORACLE_SCORE_IMPROVEMENT_MIN or shortfall_improvement >= ORACLE_SHORTFALL_IMPROVEMENT_MIN
    gate_c = schedulable >= SCHEDULABLE_KNOWN_SHARE_MIN
    ready = bool(gate_a and gate_b and gate_c)
    contract = {
        "artifact_id": "V26M_ORACLE_CEILING_CONTRACT_V1",
        "authority": "NON_CAUSAL_ORACLE_DIAGNOSTIC_ONLY",
        "evaluation_days": "V25 canonical pooled OOF 151 days, 2024-11-01 through 2025-03-31",
        "O0_input": "raw B2 OOF mean plus raw B3 OOF Q50/Q90; no BR-A reconciliation",
        "O1_change_only": "add realized D-day overlap from jobs pending at cutoff to each O0 statistic",
        "projector": "FROZEN_96_SLOT_AGGREGATE_CUMULATIVE_SERVICE_DESCRIPTOR",
        "projector_scope": "PRE_DEVELOPMENT_INFORMATION_VALUE_PROXY_NOT_FINAL_CLASS_RESOLVED_SAFE_SET",
        "release_shape": "uniform over 96 slots",
        "deadline_shift_slots": 8,
        "capacity": "monthly source-observed lower-bound C_src_GPU times 0.25 h per slot",
        "primary_envelope_score": "sum(abs(Q50-reference))/sum(reference)",
        "reserve_nomination": "Q50 aggregate flexible-service GPU-hours",
        "hidden_shedding_allowed": False,
        "future_values_online_feature_reads": 0,
        "April_target_reads": 0,
        "grid_objective_reads": 0,
    }
    _write("V26M_ORACLE_CEILING_CONTRACT.json", contract)
    review = {
        "artifact_id": "V26M_ORACLE_CEILING_REVIEW_V1",
        "case_summaries": summaries,
        "O1_vs_O0": {
            "primary_envelope_score_relative_improvement": float(score_improvement),
            "reserve_shortfall_relative_improvement": float(shortfall_improvement),
            "interpretation": "pending oracle materially improves the primary boundary score; reserve over-nomination shortfall does not improve",
        },
        "limitations": [
            "Aggregate 96-slot proxy is intentionally simpler than the gated full class-resolved SAFE set.",
            "Oracle values are post-hoc labels and cannot be deployed.",
            "B2/B3 innovation target is submission-cohort service while the reference is realized D-day overlap; the mismatch is held fixed for O0/O1 comparison.",
        ],
    }
    _write("V26M_ORACLE_CEILING_REVIEW.json", review)
    gate = {
        "artifact_id": "V26M_COMMITTED_STATE_VALUE_GATE_V1",
        "A_supported_state_fraction": supported,
        "A_threshold": ORACLE_SUPPORTED_FRACTION_MIN,
        "A_pass": gate_a,
        "B_O1_primary_score_relative_improvement": float(score_improvement),
        "B_primary_threshold": ORACLE_SCORE_IMPROVEMENT_MIN,
        "B_O1_reserve_shortfall_relative_improvement": float(shortfall_improvement),
        "B_shortfall_threshold": ORACLE_SHORTFALL_IMPROVEMENT_MIN,
        "B_pass": gate_b,
        "C_rho_K_schedulable": schedulable,
        "C_threshold": SCHEDULABLE_KNOWN_SHARE_MIN,
        "C_pass": gate_c,
        "exceptional_value_flag": bool(schedulable < SCHEDULABLE_KNOWN_SHARE_MIN and score_improvement >= 0.20),
        "COMMITTED_STATE_VALUE_READY": ready,
        "result_if_stop": None if ready else "V26M_SAFE_COMMITTED_STATE_VALUE_INSUFFICIENT",
        "full_SAFE_development_authorized": ready,
    }
    _write("V26M_COMMITTED_STATE_VALUE_GATE.json", gate)
    print(json.dumps(gate, indent=2))


if __name__ == "__main__":
    main()

