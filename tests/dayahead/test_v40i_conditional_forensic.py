import pandas as pd
from dayahead.v40i.conditional_forensic import walltime_regime,prior_training,support_bin
from dayahead.v40i.h100_forensic import distribution


def test_walltime_regimes_do_not_double_count_exact_12_and_48_hours():
    assert [walltime_regime(h*3600) for h in [4,8,11,12,24,47,48,49]]==[
        '<=4h','4-8h','8-12h_excluding12','exact12h','12-24h','24-48h_excluding48','exact48h','>48h']


def test_support_reference_excludes_self_future_and_old_labels():
    frame=pd.DataFrame({'job_id':['past','at_split','future','too_old'],
       'end_time':['2025-03-01T00:00Z','2025-03-24T00:00Z','2025-03-25T00:00Z','2024-01-01T00:00Z'],
       'runtime_seconds':[10.,10.,10.,10.]})
    assert prior_training(frame,'2025-03-24T00:00Z').job_id.tolist()==['past']


def test_support_count_labels_are_descriptive_not_fitted_state_claims():
    assert support_bin(0)=='NO_EXACT_SUPPORT_REGIME_MISMATCH_CANDIDATE'
    assert support_bin(99)=='SPARSE_OBSERVED_EXACT_SUPPORT'
    assert support_bin(100)=='STRONG_OBSERVED_EXACT_SUPPORT'


def test_singleton_regime_does_not_invent_skewness_or_kurtosis():
    result=distribution([18650.])
    assert result['N']==1 and result['median']==18650
    assert result['sample_skewness'] is None and result['sample_excess_kurtosis'] is None
