from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from dayahead.v17_ac_restoration_contract import (
    ACViolation,
    K_MAX,
    NUMERICAL_REPEAT_TOLERANCE,
    RHO,
    RestorationCut,
    ViolationType,
)


def _violation() -> ACViolation:
    return ACViolation(
        violation_type=ViolationType.VOLTAGE_UPPER,
        operating_day="2025-04-12",
        case="B2",
        slot=79,
        asset="bus.1",
        phase="A",
        actual_value=1.05001,
        hard_limit=1.05,
        signed_violation=0.00001,
        fresh_opendss_state_sha256="a" * 64,
        schedule_sha256="b" * 64,
    )


def test_violation_and_cut_are_immutable_and_deterministic() -> None:
    violation = _violation()
    assert violation.sha256 == _violation().sha256
    with pytest.raises(FrozenInstanceError):
        violation.slot = 1  # type: ignore[misc]
    cut = RestorationCut(
        violation_sha256=violation.sha256,
        local_ac_operating_point_sha256="c" * 64,
        derivative_sha256="d" * 64,
        violation_type=violation.violation_type,
        slot=violation.slot,
        relation="<=",
        actual_value=violation.actual_value,
        hard_limit=violation.hard_limit,
        margin=1e-4,
        trust_region_rho=RHO,
        iteration_index=1,
        control_names=("mess_p_kw[X]",),
        anchor_controls=(0.0,),
        coefficients=(0.001,),
        local_radius=(50.0,),
    )
    assert cut.sha256 == cut.sha256
    with pytest.raises(ValueError, match="RHO_NOT_FROZEN"):
        RestorationCut(**{**cut.__dict__, "trust_region_rho": 0.2})


def test_materialized_contract_is_pre_replay_common_and_source_derived() -> None:
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "dayahead/artifacts/v17_candidate"
    contract = json.loads((artifacts / "V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1.json").read_text(encoding="utf-8"))
    validation = json.loads((artifacts / "V17_AC_RESTORATION_CUT_VALIDATION.json").read_text(encoding="utf-8"))
    assert contract["status"] == "FROZEN_BEFORE_APR12_REPLAY"
    assert contract["scope"] == ["B0", "B1", "B2", "B3"]
    assert contract["termination"]["K_MAX"] == K_MAX == 5
    assert contract["local_trust_region"]["rho"] == RHO == 0.10
    assert validation["status"] == "PASS_FROZEN_BEFORE_APR12_REPLAY"
    assert validation["source_validation"]["probe_count"] == 9072
    assert validation["Apr12_B2_outcome_used_for_margin_selection"] is False
    assert validation["margins"]["m_V_pu"] == validation["residual_sources"]["voltage_max_abs_local_residual_pu"] + NUMERICAL_REPEAT_TOLERANCE
    assert validation["margins"]["m_I_pu"] == validation["residual_sources"]["non_dominated_current_max_abs_local_residual_pu"] + NUMERICAL_REPEAT_TOLERANCE
    for payload in (contract, validation):
        assert payload["May_scientific_input_reads"] == 0
        assert payload["June_scientific_input_reads"] == 0
        assert payload["remaining_April_day_runs"] == 0
        assert payload["OpenDSS_calls_inside_Benders"] == 0
