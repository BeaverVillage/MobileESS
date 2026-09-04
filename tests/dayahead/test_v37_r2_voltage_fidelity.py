from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v36.context import load_day_context as load_april_day_context
from dayahead.v37.runner import _beam_case
from dayahead.v37.voltage_fidelity import (
    load_voltage_fidelity_authority,
    repaired_coefficients,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v37_r2_voltage_fidelity_repair"


def j(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_authority_is_april_only_and_preserves_science_firewalls() -> None:
    authority, _sha = load_voltage_fidelity_authority(ROOT)
    assert authority["classification"] == "DIRECT_AFFINE_VOLTAGE_FIDELITY_REPAIR"
    assert set(authority["calibration_days"]).issubset(
        {f"2025-04-{day:02d}" for day in range(1, 31)}
    )
    assert "2025-04-01" in authority["calibration_days"]
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
    assert authority["authority_frozen"] is True
    assert authority["selectable_service_PCC_coverage"] == "24/24"
    assert authority["target_MESS_PCC_coverage"] == "24/24"
    assert authority["cross_PCC_sensitivity"] is True
    assert authority["phase_coverage"] == ["A", "B", "C"]
    assert authority["April_background_coverage_PASS"] is True


def test_two_pass_and_small_order_history_reproducibility_gates_pass() -> None:
    audit = j("V37_R2_FRESH_REPRODUCIBILITY_AUDIT.json")
    assert audit["full_pass_count"] == 2
    assert audit["each_pass_new_OpenDSS_engine"] is True
    assert audit["identical_deterministic_probe_sequence"] is True
    assert audit["full_pass_state_count"] == 326
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
    assert audit["source_PCC_coverage"] == "24/24"
    assert audit["cross_PCC_coverage"] is True
    assert audit["full_bus_phase_target_count"] == 386
    assert audit["April_background_coverage_PASS"] is True


def test_minimum_april_background_coverage_audit_passes_without_may() -> None:
    audit = j("V37_R2_APRIL_BACKGROUND_COVERAGE_AUDIT.json")
    assert audit["raw_April_day_count"] == 30
    assert audit["raw_April_slot_count"] == 30 * 96
    assert audit["representative_background_slot_count"] == 7
    assert audit["targeted_Fresh_only_representative_state_count"] == 7 * 24
    assert audit["source_PCC_coverage"] == "24/24"
    assert audit["full_bus_phase_target_count_per_source_perturbation"] == 386
    assert audit["selectable_MESS_PCC_phase_target_count_per_source_perturbation"] == 72
    assert audit["additional_full_April_optimization_runs"] == 0
    assert audit["May_data_used"] is False
    assert audit["PASS"] is True


def test_correction_table_is_pcc_phase_specific_and_conservative() -> None:
    table = pd.read_parquet(OUT / "V37_R2_VOLTAGE_SENSITIVITY_CORRECTION_TABLE.parquet")
    assert len(table) == 326 * 24 * 3
    assert set(table["phase"]) == set("ABC")
    assert table["source_service"].nunique() == 24
    assert table["target_service"].nunique() == 24
    assert np.array_equal(
        np.sign(table.loc[table["P_material"], "new_H_P_pu_squared_per_kW"]),
        np.sign(table.loc[table["P_material"], "Fresh_H_P_pu_squared_per_kW"]),
    )
    assert np.array_equal(
        np.sign(table.loc[table["Q_material"], "new_H_Q_pu_squared_per_kvar"]),
        np.sign(table.loc[table["Q_material"], "Fresh_H_Q_pu_squared_per_kvar"]),
    )
    assert (table.loc[table["P_material"], "P_conservatism_pu_squared_per_kW"] >= -1e-15).all()
    assert (table.loc[table["Q_material"], "Q_conservatism_pu_squared_per_kvar"] >= -1e-15).all()
    assert np.allclose(table["delta_P_kW"], 10.0)
    assert np.allclose(table["delta_Q_kvar"], 10.0)
    full = pd.read_parquet(OUT / "V37_R2_FRESH_FULL_BUS_PHASE_SENSITIVITY.parquet")
    assert len(full) == 326 * 386
    assert full["target_bus_phase_key"].nunique() == 386


def test_repaired_production_coefficients_change_only_authorized_cross_pq_rows_and_keep_anchor() -> None:
    _data, electrical = load_april_day_context("2025-04-01")
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
        for base, repaired in zip(old, new, strict=True):
            expected = set()
            for row in authority["corrections"]:
                p_index = controls.index(f"mess_p_kw[{row['source_service']}]")
                q_index = controls.index(f"mess_q_kvar[{row['source_service']}]")
                node_index = nodes.index(row["target_bus_phase_key"])
                old_p = float(base.voltage_matrix[p_index, node_index])
                old_q = float(base.voltage_matrix[q_index, node_index])
                if int(row["P_physical_sign"]) != 0 and not (
                    int(np.sign(old_p)) == int(row["P_physical_sign"])
                    and abs(old_p) >= float(row["P_minimum_abs_H"])
                ):
                    expected.add((p_index, node_index))
                if int(row["Q_physical_sign"]) != 0 and not (
                    int(np.sign(old_q)) == int(row["Q_physical_sign"])
                    and abs(old_q) >= float(row["Q_minimum_abs_H"])
                ):
                    expected.add((q_index, node_index))
            assert 0 < len(expected) <= 24 * 24 * 3 * 2
            changed = set(map(tuple, np.argwhere(base.voltage_matrix != repaired.voltage_matrix)))
            assert changed == expected
            anchor = np.asarray(base.anchor, dtype=float)
            base_anchor = base.voltage_constant + base.voltage_matrix.T @ anchor
            repaired_anchor = repaired.voltage_constant + repaired.voltage_matrix.T @ anchor
            assert np.allclose(repaired_anchor, base_anchor, atol=1e-14, rtol=0.0)
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
    assert audit["V37_P1_cumulative_cache_and_persistent_worker_required"] is True
    source = inspect.getsource(_beam_case)
    assert "frozen.slot_coefficients" in source
    assert "coefficients[int(slot)]" in source
