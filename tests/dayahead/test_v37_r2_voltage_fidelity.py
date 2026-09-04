from __future__ import annotations

import json
import inspect
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v37.context import load_day_context
from dayahead.v37.runner import _beam_case
from dayahead.v37.voltage_fidelity import (
    load_voltage_fidelity_authority,
    repaired_coefficients,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v37_r2_voltage_fidelity_repair"


def j(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_authority_is_apr01_only_and_preserves_science_firewalls() -> None:
    authority, _sha = load_voltage_fidelity_authority(ROOT)
    assert authority["classification"] == "DIRECT_AFFINE_VOLTAGE_FIDELITY_REPAIR"
    assert authority["calibration_days"] == ["2025-04-01"]
    assert authority["calibration_source"]["completed_integrated_April_authority_days"] == ["2025-04-01"]
    assert authority["calibration_source"]["May_results_used_for_coefficient_derivation"] is False
    assert authority["calibration_source"]["May_results_used_for_intercept_derivation"] is False
    assert authority["calibration_source"]["May_margin_used"] is False
    for field in (
        "Benders_changed", "K_changed", "beam_changed",
        "MESS_physical_limits_changed", "AIDC_changed",
        "voltage_physical_limit_changed",
    ):
        assert authority[field] is False


def test_two_pass_and_small_order_history_reproducibility_gates_pass() -> None:
    audit = j("V37_R2_FRESH_REPRODUCIBILITY_AUDIT.json")
    assert audit["full_pass_count"] == 2
    assert audit["each_pass_new_OpenDSS_engine"] is True
    assert audit["identical_deterministic_probe_sequence"] is True
    assert audit["full_pass_state_count"] == 62
    assert audit["full_repeat_PASS"] is True
    assert audit["baseline_consistency_PASS"] is True
    assert audit["order_history_PASS"] is True
    assert audit["authority_freeze_allowed"] is True
    order = audit["order_history_check"]
    assert 5 <= order["state_count"] <= 10
    assert order["large_negative_Q_included"] is True
    assert order["low_voltage_state_included"] is True
    assert order["phases"] == ["A", "B", "C"]
    assert len(order["PCCs"]) > 1
    assert audit["saved_Apr01_baseline"]["exceedance_count"] == 0


def test_correction_table_is_pcc_phase_specific_and_conservative() -> None:
    table = pd.read_parquet(OUT / "V37_R2_VOLTAGE_SENSITIVITY_CORRECTION_TABLE.parquet")
    assert len(table) == 62 * 3
    assert set(table["phase"]) == set("ABC")
    assert table["service"].nunique() == 7
    assert set(table["classification"]) == {"CORRECT_BOTH"}
    assert table["P_sign_match"].all() and table["Q_sign_match"].all()
    assert (table["old_H_P_pu_squared_per_kW"] > 0.0).all()
    assert (table["old_H_Q_pu_squared_per_kvar"] > 0.0).all()
    assert (table["P_conservatism_pu_squared_per_kW"] >= 0.0).all()
    assert (table["Q_conservatism_pu_squared_per_kvar"] >= 0.0).all()
    assert np.allclose(table["delta_P_kW"], 1.0)
    assert np.allclose(table["delta_Q_kvar"], 1.0)


def test_repaired_production_coefficients_change_only_local_pq_rows_and_keep_anchor() -> None:
    _data, electrical = load_day_context(ROOT, "2025-05-01")
    try:
        old = tuple(
            slot_coefficients(
                electrical.legacy_context, electrical.voltage, electrical.current, slot,
            )
            for slot in range(96)
        )
        new = repaired_coefficients(ROOT, electrical)
        nodes = tuple(map(str, electrical.voltage["node_names"]))
        controls = tuple(map(str, electrical.voltage["control_names"]))
        authority, _sha = load_voltage_fidelity_authority(ROOT)
        expected = set()
        for row in authority["corrections"]:
            expected.add((controls.index(f"mess_p_kw[{row['service']}]"), nodes.index(row["target_bus_phase_key"])))
            expected.add((controls.index(f"mess_q_kvar[{row['service']}]"), nodes.index(row["target_bus_phase_key"])))
        assert len(expected) == 7 * 3 * 2
        for base, repaired in zip(old, new, strict=True):
            changed = set(map(tuple, np.argwhere(base.voltage_matrix != repaired.voltage_matrix)))
            assert changed == expected
            anchor = np.asarray(base.anchor, dtype=float)
            base_anchor = base.voltage_constant + base.voltage_matrix.T @ anchor
            repaired_anchor = repaired.voltage_constant + repaired.voltage_matrix.T @ anchor
            assert np.allclose(repaired_anchor, base_anchor, atol=1e-14, rtol=0.0)
            for control_index, node_index in expected:
                assert repaired.voltage_matrix[control_index, node_index] > base.voltage_matrix[control_index, node_index] > 0.0
    finally:
        electrical.voltage.close()
        electrical.current.close()


def test_production_integration_retains_direct_affine_architecture() -> None:
    audit = j("V37_R2_PRODUCTION_INTEGRATION_AUDIT.json")
    assert audit["affine_structure_preserved"] is True
    assert audit["original_direct_affine_row_count_per_full_model"] == 37_056
    assert audit["OpenDSS_calls_inside_optimizer"] == 0
    assert audit["new_binary_variables"] == 0
    assert audit["production_consumers"] == ["_add_fixed_voltage", "solve_integrated_mess"]
    source = inspect.getsource(_beam_case)
    assert "frozen.slot_coefficients" in source
    assert "coefficients[int(slot)]" in source
