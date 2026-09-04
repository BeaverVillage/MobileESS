import inspect
from pathlib import Path

import numpy as np

from dayahead.v28r2.c1_affine import (
    analytic_convexity_certificate, endpoint_secant, exact_c1_pcc_kw, load_c1,
)


def parameters():
    repo = Path(__file__).resolve().parents[2]
    return load_c1(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")


def test_endpoint_secant_is_equality_majorant_on_full_interval():
    p = parameters()
    coefficient = endpoint_secant("AIDC01", 0, 10.0, 60.0, 14.0, 65.0, p)
    x = np.linspace(10.0, 60.0, 2001)
    error = coefficient.slope * x + coefficient.intercept_kw - exact_c1_pcc_kw(x, 14.0, 65.0, p)
    assert analytic_convexity_certificate(p, 10.0, 60.0, 14.0)
    assert error.min() >= -1e-10
    assert abs(error[0]) <= 1e-10
    assert abs(error[-1]) <= 1e-10
    assert abs(error.max() - coefficient.maximum_error_kw) <= 1e-6


def test_binding_source_has_no_epigraph_pue_plan_c2_or_beta():
    from dayahead.v28r2 import c1_affine

    source = inspect.getsource(c1_affine)
    assert "PUE_PLAN" not in source
    assert "beta_AIDC" not in source
    assert "C2_" not in source
    assert "addConstr" in source


def test_frozen_c1_has_zero_quadratic_and_other_slope():
    p = parameters()
    assert p.it_mw_squared == 0.0
    assert p.other_it_mw == 0.0
