import json
from pathlib import Path

from pfr.tools.compose_pfr3_factorized_authority import compose


def _write(path: Path, value: dict) -> Path:
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_composition_preserves_three_separate_authorities(tmp_path: Path) -> None:
    mobility = _write(
        tmp_path / "mobility.json",
        {
            "status": "PASS",
            "authority": "joint",
            "target_joint_coverage": 0.95,
            "no_2025_retuning": True,
            "row_wise_cross_dataset_merge": False,
            "score": "max((T_actual-T_q50)/scale,(E_actual-E_q50)/scale)",
            "calibration": {"joint_quantile": 2.0},
        },
    )
    workload = _write(
        tmp_path / "workload.json",
        {
            "status": "PASS",
            "calibration_year": 2024,
            "no_2025_recalibration": True,
            "old_idc_residual_reused": False,
            "new_spatial_operator_applied_after_global_calibration": True,
            "target_coverage": 0.95,
            "normalized_daily_joint_quantile": 0.2,
        },
    )
    grid = _write(
        tmp_path / "grid.json",
        {
            "status": "PASS",
            "authority_type": "CAUSAL_ADAPTIVE_QUANTILE_ENVELOPE",
            "future_actual_used": False,
            "post_outcome_retuning": False,
            "realized_values_used_for_evaluation_only": True,
            "tensor_audit": {"nonfinite_values": 0, "quantile_crossings": 0},
            "physical_grid_set": {"upper_net_demand": "q90-q10"},
        },
    )

    result = compose(mobility, workload, grid)

    assert result["status"] == "PASS"
    assert set(result["components"]) == {"U_mob", "U_work", "U_grid"}
    assert result["joint_cross_factor_recalibration"] is False


def test_composition_fails_when_grid_uses_future_actual(tmp_path: Path) -> None:
    mobility = _write(
        tmp_path / "mobility.json",
        {
            "status": "PASS",
            "no_2025_retuning": True,
            "row_wise_cross_dataset_merge": False,
            "score": "max((T_actual-T_q50),(E_actual-E_q50))",
        },
    )
    workload = _write(
        tmp_path / "workload.json",
        {
            "status": "PASS",
            "calibration_year": 2024,
            "no_2025_recalibration": True,
            "old_idc_residual_reused": False,
            "new_spatial_operator_applied_after_global_calibration": True,
        },
    )
    grid = _write(
        tmp_path / "grid.json",
        {
            "status": "PASS",
            "authority_type": "CAUSAL_ADAPTIVE_QUANTILE_ENVELOPE",
            "future_actual_used": True,
            "post_outcome_retuning": False,
            "realized_values_used_for_evaluation_only": True,
            "tensor_audit": {"nonfinite_values": 0, "quantile_crossings": 0},
        },
    )

    result = compose(mobility, workload, grid)

    assert result["status"] == "FAIL"
    assert result["gates"]["grid_causal_adaptive_envelope_pass"] is False
