import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pfr.tools.analyze_january_b8_timing import analyze as analyze_b8
from pfr.tools.analyze_january_daily import (
    bootstrap_mean_ci,
    lag1_autocorrelation,
    load_method_rows,
)


def test_constant_paired_difference_is_deterministic_iid() -> None:
    result = bootstrap_mean_ci([2.0] * 31)

    assert result["bootstrap_mode"] == "PAIRED_DAY_IID"
    assert result["mean_difference"] == 2.0
    assert result["ci95_lower"] == 2.0
    assert result["ci95_upper"] == 2.0


def test_material_serial_dependence_selects_moving_block() -> None:
    values = [float(index) for index in range(31)]

    assert abs(lag1_autocorrelation(values)) >= 0.30
    first = bootstrap_mean_ci(values)
    second = bootstrap_mean_ci(values)

    assert first == second
    assert first["bootstrap_mode"] == "CIRCULAR_MOVING_BLOCK"


def test_loader_accepts_runtime_pass_committed_markers(tmp_path: Path) -> None:
    method_root = tmp_path / "B8"
    for issue in range(288):
        issue_root = method_root / f"issue_{issue:06d}"
        issue_root.mkdir(parents=True)
        (issue_root / "COMMIT_MARKER.json").write_text(
            json.dumps(
                {
                    "status": "PASS_COMMITTED",
                    "commit_marker": True,
                    "actual_gurobi_used": True,
                    "actual_fresh_opendss_used": True,
                    "future_actual_used": False,
                    "pre_state_sha256": f"state-{issue}",
                    "post_state_sha256": f"state-{issue + 1}",
                }
            ),
            encoding="utf-8",
        )

    assert len(load_method_rows(tmp_path, "B8")) == 288


def _timing_row(exogenous_sha256: str) -> dict[str, object]:
    return {
        "causal_exogenous_sha256": exogenous_sha256,
        "realized_grid_cost_aud": 1.0,
        "deadline_misses": 0,
        "compute_debt_gpu_hours": 0.0,
        "energy_debt_kwh": 0.0,
        "full_replan_count_cumulative": 1,
        "communication_bytes_cumulative": 1,
        "safety_filter_intervention": False,
        "mobility_energy_kwh": 0.0,
        "runtime_seconds": 1.0,
    }


def _january_roots(prefix: str) -> dict[str, Path]:
    return {
        f"2025-01-{day:02d}": Path(f"/{prefix}/{day:02d}")
        for day in range(1, 32)
    }


def test_b8_analysis_certifies_paired_exogenous_identity() -> None:
    with patch(
        "pfr.tools.analyze_january_b8_timing.load_method_rows",
        return_value=[_timing_row("a" * 64)],
    ):
        result = analyze_b8(_january_roots("main"), _january_roots("b8"))

    assert result["status"] == "PASS"
    assert result["paired_exogenous_identity"] == "PASS"
    assert len(result["paired_exogenous_sha256"]) == 31


def test_b8_analysis_rejects_unpaired_exogenous_inputs() -> None:
    def rows(root: Path, method: str) -> list[dict[str, object]]:
        value = "a" * 64 if method == "B7" else "b" * 64
        return [_timing_row(value)]

    with patch(
        "pfr.tools.analyze_january_b8_timing.load_method_rows",
        side_effect=rows,
    ), pytest.raises(RuntimeError, match="exogenous inputs are not paired"):
        analyze_b8(_january_roots("main"), _january_roots("b8"))
