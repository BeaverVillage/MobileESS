import pandas as pd
import pytest
from dayahead.paper_analysis.storage import write_json
from dayahead.v40h.identity import IntegrityError
from dayahead.v40i.pending_forensic import metrics, buckets, error_class
from dayahead.v40i.electrical import generation_release,ROOT


def test_gpu_weights_do_not_confuse_count_with_grid_exposure():
    frame=pd.DataFrame({'actual_runtime_seconds':[1800.,900.,900.],
                        'prediction':[900.,1800.,0.],'num_gpus_req':[4,1,0]})
    value=metrics(frame,'prediction')
    assert value['underprediction_rate']==pytest.approx(2/3)
    assert value['requested_GPU_weighted_underprediction_rate']==pytest.approx(.8)
    assert value['GPU_WEIGHTED_UNDERPREDICTION_SECONDS']==3600
    assert value['CRITICAL_SLOT_MISS_RATE']==pytest.approx(.5)


def test_four_hour_runtime_bucket_boundary_is_not_in_long_tail():
    frame=pd.DataFrame({'actual_runtime_seconds':[899.,900.,14400.,14401.],
                       'prediction':[900.]*4,'num_gpus_req':[1]*4})
    result=buckets(frame,'prediction')['runtime_bucket']
    assert {r['bucket']:r['sample_count'] for r in result}=={'<15m':1,'15-30m':1,'2-4h':1,'>4h':1}


def test_margin_and_rounding_error_categories_remain_distinct():
    assert error_class(28577,16436.296875,22012.74609375,22500)=='RAW_UNDER_SAFE_STILL_UNCOVERED'
    assert error_class(22300,16436.296875,22012.74609375,22500)=='RAW_UNDER_SAFE_COVERED'
    assert error_class(950,800,1000,900)=='ROUNDING_INDUCED_UNDER'
    assert error_class(950,800,1000,900,False)=='AUTHORITY_MISMATCH'


def test_latest_hold_overrides_old_forensic_release(tmp_path):
    write_json(tmp_path/ROOT/'V40I_ADDITIONAL_FORENSIC_GENERATION_HOLD.json',{'status':'HOLD'})
    write_json(tmp_path/ROOT/'V40I_GENERATION_RELEASE_AFTER_FORENSIC.json',{'status':'RELEASED_AFTER_FORENSIC'})
    with pytest.raises(IntegrityError,match='LATEST_USER_ADDENDUM'):generation_release(tmp_path)
