import pytest
import pandas as pd
from dayahead.v40i.h100_forensic import positive_quantiles, percentile, safety_layers, Q
from dayahead.v40i.completed_forensic import completed_bias_verdict
from dayahead.v40i.reactive_forensic import pq_authority


def test_positive_residual_quantiles_include_zero_error_population():
    # Filtering to strictly positive errors would incorrectly return q50=100.
    assert positive_quantiles([-100,0,0,100])['q50']==0
    assert positive_quantiles([-100,0,0,100])['q90']==pytest.approx(70)


def test_empirical_percentiles_preserve_ties_and_extreme_support():
    assert percentile([1,2,2,4],[0,2,4,5]).tolist()==[0,.75,1,1]


def test_capped_safe_is_not_confused_with_uncapped_q_or_ceil():
    f=pd.DataFrame({'actual_runtime_seconds':[1200.], 'point_runtime_seconds':[1000.], 'requested_seconds':[1100.]})
    x=safety_layers(f).iloc[0]
    assert x.point_plus_q_seconds==1000+Q
    assert x.capped_safe_seconds==1100
    assert x.effective_seconds==1800
    assert x.q_only_error_seconds<0<x.capped_safe_error_seconds
    assert x.effective_error_seconds<0


def test_no_status_stratum_proves_bias_without_stored_error_evidence():
    assert completed_bias_verdict({'sample_count':0})=='INSUFFICIENT_MODEL_EVIDENCE'
    m={'sample_count':2562,'signed_mean_error_seconds':7064.,'median_signed_error_seconds':332.,'underprediction_rate':.6413}
    assert completed_bias_verdict(m)=='POINT_MODEL_SYSTEMATIC_UNDERPREDICTION'


def test_solver_readback_does_not_upgrade_derived_Q_to_independent_authority():
    for kind in ['setpoint_readback','OpenDSS_branch_flow','measured']:
        assert pq_authority(kind,True)=='DERIVED_FIXED_PF_BOUNDARY_NOT_INDEPENDENT_Q_AUTHORITY'
    assert pq_authority('measured',False)=='MEASURED_CANDIDATE_REQUIRES_SITE_TIME_IDENTITY'
