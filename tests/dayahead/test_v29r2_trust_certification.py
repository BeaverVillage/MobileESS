from __future__ import annotations

import json
import csv
from pathlib import Path

import numpy as np

from dayahead.v29r1.authority import CANDIDATE_RHOS
from dayahead.v29r2.trust_certification import (
    CURRENT_TOLERANCE,
    TRUST_FREEZE_COMMIT,
    VOLTAGE_TOLERANCE,
    _hidden_large_error_mismatches,
    _metrics,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret"


def test_frozen_contract_precedes_candidate_execution() -> None:
    contract = json.loads((OUT / "V29R2_TRUST_CERT_CONTRACT.json").read_text(encoding="utf-8"))
    assert TRUST_FREEZE_COMMIT == "be65408dba6ade0d1dacfa6f0b2525f5b37bc87c"
    assert contract["status"] == "FROZEN_BEFORE_CANDIDATE_EXECUTION"
    assert contract["candidate_rho_AIDC"] == list(CANDIDATE_RHOS)
    assert contract["old_V29R1_sweep_may_be_reclassified_as_authority"] is False


def test_fidelity_tolerances_are_unchanged() -> None:
    assert VOLTAGE_TOLERANCE == {"mean": .003, "p95": .005, "max": .01}
    assert CURRENT_TOLERANCE == {"mean": .01, "p95": .02, "max": .03}


def test_metric_and_hidden_mismatch_accounting() -> None:
    actual = np.asarray([[1.061, .99]])
    predicted = np.asarray([[1.049, .99]])
    assert _metrics(predicted, actual)["max"] == np.max(np.abs(predicted - actual))
    count = _hidden_large_error_mismatches(
        predicted, actual, np.asarray([[.9]]), np.asarray([[1.04]]),
    )
    assert count == 2


def _rows(name: str) -> list[dict[str, str]]:
    with (OUT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_fresh_trust_authority_is_complete_and_selects_only_by_fidelity() -> None:
    decision = json.loads((OUT / "V29R2_TRUST_CERT_DECISION.json").read_text(encoding="utf-8"))
    fidelity = _rows("V29R2_TRUST_CERT_FIDELITY_RESULTS.csv")
    c1 = _rows("V29R2_TRUST_CERT_C1_RESULTS.csv")
    diagnostics = _rows("V29R2_TRUST_CERT_ANCHOR_DIAGNOSTICS.csv")
    candidates = _rows("V29R2_TRUST_CERT_CANDIDATES.csv")
    assert len(fidelity) == len(c1) == len(diagnostics) == 360
    assert len(candidates) == 4
    assert decision["status"] == "PASS"
    assert decision["selected_rho_AIDC"] == 1.0
    assert decision["selection_inputs"] == ["Fresh_OpenDSS_model_fidelity", "C1_one_percent_authority"]
    assert decision["Fresh_OpenDSS_execution"]["total_sequential_slot_solves"] == 60_480
    assert decision["old_V29R1_sweep_reclassified"] is False
    assert decision["V29R1_read_only_before_after"]["identity"] is True
    assert all(row["status"] == "PASS" for row in fidelity + c1 + candidates)
    assert all(row["Fresh_independent_execution"] == "True" for row in fidelity)
    assert all(row["absolute_physical_feasibility_used_for_status"] == "False" for row in fidelity)
    assert all(row["absolute_physical_feasibility_is_selection_input"] == "False" for row in diagnostics)
    assert all(row["April_rows_used"] == "0" for row in fidelity + c1 + diagnostics + candidates)


def test_fresh_fidelity_metrics_and_additional_gates_pass() -> None:
    fidelity = _rows("V29R2_TRUST_CERT_FIDELITY_RESULTS.csv")
    assert max(float(row["voltage_error_mean_pu"]) for row in fidelity) <= VOLTAGE_TOLERANCE["mean"]
    assert max(float(row["voltage_error_p95_pu"]) for row in fidelity) <= VOLTAGE_TOLERANCE["p95"]
    assert max(float(row["voltage_error_max_pu"]) for row in fidelity) <= VOLTAGE_TOLERANCE["max"]
    assert max(float(row["current_error_mean_pu"]) for row in fidelity) <= CURRENT_TOLERANCE["mean"]
    assert max(float(row["current_error_p95_pu"]) for row in fidelity) <= CURRENT_TOLERANCE["p95"]
    assert max(float(row["current_error_max_pu"]) for row in fidelity) <= CURRENT_TOLERANCE["max"]
    for row in fidelity:
        assert row["all_slots_converged"] == "True"
        assert row["finite_arrays"] == "True"
        assert row["slot_line_phase_mapping_identity"] == "True"
        assert row["P_Q_sign_consistency"] == "True"
        assert row["hidden_large_error_planning_safe_AC_violation_count"] == "0"
