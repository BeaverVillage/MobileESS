import numpy as np
import pytest

from dayahead.v28r2.reference_delta import build_reference_delta


def test_reference_delta_map_first_nonnegative():
    racks = ("R1", "R2")
    p = np.full(96, 100.0)
    g = np.full(96, 80.0)
    p_fixed = np.vstack([np.full(96, 20.0), np.full(96, 30.0)])
    g_fixed = np.vstack([np.full(96, 16.0), np.full(96, 24.0)])
    result = build_reference_delta(
        p, g, p_fixed, g_fixed, rack_ids=racks,
        power_weights={"R1": 0.4, "R2": 0.6}, gpu_weights={"R1": 0.4, "R2": 0.6},
    )
    assert result.p_res_plan_kw.shape == (2, 96)
    assert result.g_res_plan_gpu.shape == (2, 96)
    assert np.all(result.p_res_plan_kw >= 0)
    assert np.all(result.g_res_plan_gpu >= 0)


def test_reference_delta_substantive_negative_fails_without_clipping():
    with pytest.raises(ValueError, match="FAIL_REFERENCE_DELTA_DECOMPOSITION"):
        build_reference_delta(
            np.ones(96), np.ones(96), np.full((1, 96), 2.0), np.zeros((1, 96)),
            rack_ids=("R",), power_weights={"R": 1.0}, gpu_weights={"R": 1.0},
        )
