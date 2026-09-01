import json
from pathlib import Path

import numpy as np

from dayahead.v29.formulation import materialize_formulation_data_v29


REPO = Path(__file__).resolve().parents[2]
ART = REPO / "dayahead/artifacts/v29_grid_responsive_aidc"


def test_v29_formulation_preserves_24h_one_shot_freeze():
    contract = json.loads((ART / "V29_COMMON_FORMULATION_CONTRACT.json").read_text(encoding="utf-8"))
    assert contract["horizon"] == {"hours": 24, "slots": 96, "resolution_minutes": 15, "one_shot": True, "daily_independent": True}
    assert contract["objective"] == "MIN_MAX_NORMALIZED_PHASE_LINE_CURRENT"
    assert contract["rho_AIDC"] == 0.1
    assert contract["PARTIAL_shared_controllable"] is False
    assert contract["running_job_preemption"] is False
    assert contract["synthetic_deadline"] is False
    assert contract["critical_reserve_hard_constraint"] is False
    assert contract["secondary_objective"] is False


def test_reference_v3_carryin_mass_delta_and_no_double_counting():
    expected = {"2025-04-01": 0.0, "2025-04-02": 0.0, "2025-04-03": 216.0, "2025-04-04": 1020.0}
    for day, carryin in expected.items():
        data = materialize_formulation_data_v29(REPO, day)
        assert abs(float(data.initial_backlog_nodeh.sum()) - carryin) <= 1e-9
        assert np.array_equal(data.reference.backlog_nodeh[0], data.initial_backlog_nodeh)
        assert abs(float(data.initial_backlog_nodeh.sum() + data.arrivals_nodeh.sum() - data.reference.x_ref_nodeh.sum() - data.reference.backlog_nodeh[-1].sum())) <= 1e-8
        assert data.delta.p_res_plan_kw.min() >= -1e-9
        assert data.delta.g_res_plan_gpu.min() >= -1e-9
        assert np.allclose(data.delta.p_res_plan_kw.sum(axis=0) + data.reference.p_f_ref_kw.sum(axis=0), data.p_it_q90_kw, rtol=0, atol=1e-8)
        assert np.allclose(data.delta.g_res_plan_gpu.sum(axis=0) + data.reference.g_f_ref_gpu.sum(axis=0), data.g_q90_gpu, rtol=0, atol=1e-8)


def test_b0_b2_reference_v3_bytes_are_identical():
    contract = json.loads((ART / "V29_REFERENCE_COMPUTE_SCHEDULE_V3_CONTRACT.json").read_text(encoding="utf-8"))
    assert contract["grid_loading_reads"] == contract["MESS_state_reads"] == contract["Actual_reads"] == contract["result_reads"] == 0
    assert all(row["B0_B2_reference_bytes_identical"] for row in contract["days"])
    assert all(row["reference_mass_error_nodeh"] <= 1e-8 for row in contract["days"])
