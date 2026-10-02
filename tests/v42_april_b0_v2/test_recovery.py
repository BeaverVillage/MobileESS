from copy import deepcopy
import pytest
from v42_april_b0_v2.recovery import *

EVENT='2025-04-01T12:00:00+00:00'


def row():return dict(job_uid='1_7',submit_time='2025-04-01T10:00:00+00:00',source_event_identity='event')
def candidate(gpu=None):return dict(row(),gpus_requested=gpu,nodes_req=1)


def test_missing_field_remains_missing_without_imputation():
    r=recover_gpu(row(),[candidate()],event_time=EVENT)
    assert r['GPU_gang'] is None and r['status']=='SOURCE_FIELD_ABSENT'


def test_exact_full_UID_submission_and_source_event_match():
    assert recover_gpu(row(),[candidate(3)],event_time=EVENT)['GPU_gang']==3
    assert recover_gpu(row(),[candidate(3)],event_time=EVENT)['status']=='SOURCE_RECOVERED'
    for field,value in [('job_uid','1'),('submit_time','2025-04-01T09:00:00+00:00'),('source_event_identity','other')]:
        c=candidate(3);c[field]=value
        assert recover_gpu(row(),[c],event_time=EVENT)['GPU_gang'] is None


def test_conflicting_exact_source_rows_rejected():
    r=recover_gpu(row(),[candidate(1),candidate(2)],event_time=EVENT)
    assert r['status']=='AMBIGUOUS_SOURCE_MATCH' and r['ambiguity_count']==2


def test_timezone_normalization_is_exact_not_fuzzy():
    c=candidate(3);c['submit_time']='2025-04-01T04:00:00-06:00'
    assert recover_gpu(row(),[c],event_time=EVENT)['GPU_gang']==3


def test_future_request_and_request_version_cannot_recover_Planning():
    assert recover_gpu(row(),[candidate(2)],event_time='2025-04-01T09:00:00+00:00')['status']=='CAUSAL_AUTHORITY_FAILURE'
    c=candidate(2);c['request_observed_at']='2025-05-01T00:00:00+00:00'
    assert recover_gpu(row(),[c],event_time=EVENT)['status']=='CAUSAL_AUTHORITY_FAILURE'


def test_exact_request_TRES_derivation_and_conflict():
    c=candidate();c['ReqTRES']='cpu=4,gres/gpu=2,gres/gpu:h100=2'
    assert recover_gpu(row(),[c],event_time=EVENT)['GPU_gang']==2
    c['ReqTRES']='gres/gpu=4,gres/gpu:h100=2'
    assert recover_gpu(row(),[c],event_time=EVENT)['status']=='AMBIGUOUS_SOURCE_MATCH'


def test_explicit_request_per_node_derivation_only():
    c=candidate();c['requested_gpus_per_node']=2;c['nodes_req']=3
    assert recover_gpu(row(),[c],event_time=EVENT)['GPU_gang']==6
    del c['requested_gpus_per_node'];c['gpu_nodes_occupied']=3;c['AllocTRES']='gres/gpu=12'
    assert recover_gpu(row(),[c],event_time=EVENT)['GPU_gang'] is None


@pytest.mark.parametrize('tres',['gres/gpu:h100=0','gres/gpu:h100=2,gres/gpu:h100=2','gres/gpu=2,gres/gpu:h100=2x'])
def test_zero_duplicate_or_malformed_resource_request_cannot_create_GPU_gang(tres):
    c=candidate();c['ReqTRES']=tres
    assert recover_gpu(row(),[c],event_time=EVENT)['GPU_gang'] is None


@pytest.mark.parametrize('c',[
    dict(ReqTRES='gres/gpu=0,gres/gpu:h100=2'),
    dict(gpus_requested=2,ReqTRES='gres/gpu=0'),
    dict(gpus_requested=0,ReqTRES='gres/gpu=2'),
])
def test_explicit_zero_request_conflicting_with_positive_source_is_ambiguous(c):
    raw=candidate();raw.update(c)
    assert recover_gpu(row(),[raw],event_time=EVENT)['status']=='AMBIGUOUS_SOURCE_MATCH'


def test_missing_version_does_not_corroborate_positive_other_version():
    r=recover_gpu(row(),[candidate(None),candidate(3)],event_time=EVENT)
    assert r['GPU_gang'] is None


@pytest.mark.parametrize('gpu',[0,-1,1.5,float('nan'),float('inf'),True])
def test_invalid_physical_request_not_promoted(gpu):
    assert recover_gpu(row(),[candidate(gpu)],event_time=EVENT)['GPU_gang'] is None


def test_mass_reconciliation_no_silent_drop_and_immutable_GPU():
    a=[dict(job_uid='j',GPU_gang=2,service_slots=4)]
    assert reconcile_population(a,deepcopy(a))['total_nominal_GPUh']==2
    with pytest.raises(ValueError,match='SILENT_WORKLOAD_DROP'):reconcile_population(a,[])
    with pytest.raises(ValueError,match='IMMUTABLE'):reconcile_population(a,[dict(a[0],GPU_gang=1)])
    a[0]['GPU_gang']=None
    assert reconcile_population(a,deepcopy(a))['total_nominal_GPUh'] is None


def test_exact_thirty_day_axis_rejects_five_day_selection_and_May():
    from datetime import date,timedelta
    days=[(date(2025,4,1)+timedelta(days=i)).isoformat() for i in range(30)]
    validate_date_axis(days)
    for bad in (days[:5],days[:-1]+['2025-05-01'],days+[days[0]],list(reversed(days))):
        with pytest.raises(ValueError,match='EXACT_APRIL'):validate_date_axis(bad)
