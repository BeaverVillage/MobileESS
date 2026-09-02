from __future__ import annotations

import json
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
