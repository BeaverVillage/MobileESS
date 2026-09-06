from datetime import datetime, timedelta, timezone
from copy import deepcopy
import pytest
from dayahead.paper_analysis.storage import write_json
from dayahead.v40h.identity import file_record, IntegrityError
from dayahead.v40i.authority import *


def observed_fixture(tmp_path, uid='8749975', state='PENDING', start=13, service=11904):
    issue=datetime(2025,5,2,18,tzinfo=timezone.utc)
    path=tmp_path/'raw.json'; contract=tmp_path/'contract.py'
    write_json(path,{'uid':uid}); contract.write_text('frozen replay contract')
    job=dict(job_uid=uid,requested_GPU=4,state_at_issue=state,start_slot=start,migration_selected=False)
    observed_start=issue-timedelta(hours=1) if state=='RUNNING' else issue+timedelta(seconds=start*900)
    end=issue+timedelta(seconds=service) if state=='RUNNING' else observed_start+timedelta(seconds=service)
    obs=dict(start_time=observed_start,end_time=end,gpus_requested=4)
    return timing_from_observation(job,obs,issue,observation_record=file_record(path),replay_contract_record=file_record(contract))


def test_uid_8749975_is_not_pre_day_complete(tmp_path):
    timing=observed_fixture(tmp_path)
    result=classify(uid='8749975',day='2025-05-03',timing=timing)
    assert not result['pre_day_complete_recomputed'] and not result['blocker_released']
    assert result['final_classification']==MISSING
    assert result['remaining_service_at_d_day_sec']==pytest.approx(2004)
    assert timing['earliest_finish']==pytest.approx(26.2266666667)
    assert not result['site_authority_present']


def test_pending_earliest_completion_does_not_prove_actual_completion(tmp_path):
    timing=observed_fixture(tmp_path,start=1,service=900)
    assert timing['earliest_finish']==2
    assert classify(uid='8749975',day='2025-05-03',timing=timing)['final_classification']==MISSING


def test_running_pre_day_completion_uses_timing_only(tmp_path):
    timing=observed_fixture(tmp_path,state='RUNNING',start=0,service=21600)
    result=classify(uid='8749975',day='2025-05-03',timing=timing)
    assert result['final_classification']==PRE_COMPLETE and result['blocker_released']
    assert not result['site_authority_present'] and not result['segment_authority_present']


def test_missing_timing_never_excludes():
    result=classify(uid='1',day='2025-05-01',timing={'authority_kind':'PLANNING','actual_finish':2})
    assert result['final_classification']==MISSING


def segments_fixture(tmp_path, uid='8666895'):
    rows=[dict(segment_start=0,segment_end=25,actual_site='AIDC05',compute_active=1),
        dict(segment_start=25,segment_end=28,actual_site=None,compute_active=0),
        dict(segment_start=28,segment_end=110,actual_site='AIDC01',compute_active=1)]
    path=tmp_path/'actual_segments.json';write_json(path,{'authority_kind':'ACTUAL_EXECUTION_SEGMENTS','uid':uid,'day':'2025-05-01','segments':rows})
    evidence=dict(authority_kind='ACTUAL_EXECUTION_SEGMENTS',uid=uid,day='2025-05-01',file=file_record(path),record_id=uid)
    timing=dict(authority_kind='ACTUAL_TIMING',uid=uid,timing_authority_present=True,counterfactual_timing_complete=True,
        active_intervals=[[0,25],[28,110]],service_seconds=107*900,actual_start=0,actual_finish=110)
    return rows,evidence,timing


def test_uid_8666895_gap_preserved(tmp_path):
    rows,evidence,timing=segments_fixture(tmp_path)
    result=classify(uid='8666895',day='2025-05-01',timing=timing,site_segments=rows,segment_evidence=evidence)
    assert result['final_classification']==AUTHORIZED
    s=result['canonical_segments'];assert [(x['segment_start'],x['segment_end'],x['compute_active'],x['actual_site']) for x in s]==[(0,25,1,'AIDC05'),(25,28,0,None),(28,110,1,'AIDC01')]
    assert sum((x['segment_end']-x['segment_start']) for x in s if x['compute_active'])==107


def test_planning_site_is_not_actual_site_authority(tmp_path):
    rows,evidence,timing=segments_fixture(tmp_path);evidence['authority_kind']='PLANNING'
    result=classify(uid='8666895',day='2025-05-01',timing=timing,site_segments=rows,segment_evidence=evidence)
    assert result['final_classification']==MISSING and not result['planning_fallback_used']


@pytest.mark.parametrize('fault',['neighbor_interpolation','partial','filled_gap','omitted_gap'])
def test_partial_or_interpolated_site_cannot_release(tmp_path,fault):
    rows,evidence,timing=segments_fixture(tmp_path)
    if fault=='neighbor_interpolation': rows[0]['segment_end']=24
    elif fault=='partial': rows=rows[:2]
    elif fault=='filled_gap': rows[1].update(compute_active=1,actual_site='AIDC05')
    else: rows=[rows[0],rows[2]]
    write_json(evidence['file']['path'],{'authority_kind':'ACTUAL_EXECUTION_SEGMENTS','uid':'8666895','day':'2025-05-01','segments':rows})
    evidence['file']=file_record(evidence['file']['path'])
    result=classify(uid='8666895',day='2025-05-01',timing=timing,site_segments=rows,segment_evidence=evidence)
    assert result['final_classification']==MISSING


def test_single_site_label_not_segment_authority(tmp_path):
    rows,evidence,timing=segments_fixture(tmp_path);evidence['authority_kind']='ACTUAL_SITE_LABEL'
    assert classify(uid='8666895',day='2025-05-01',timing=timing,site_segments=rows,segment_evidence=evidence)['final_classification']==MISSING


def test_timing_contradiction_rejected(tmp_path):
    rows,evidence,timing=segments_fixture(tmp_path);timing['actual_finish']=20
    with pytest.raises(IntegrityError,match='TIMING_FINISH'):
        classify(uid='8666895',day='2025-05-01',timing=timing)


def test_site_authority_cannot_be_attached_to_unrelated_file(tmp_path):
    rows,evidence,timing=segments_fixture(tmp_path);rows[0]['actual_site']='AIDC02'
    with pytest.raises(IntegrityError,match='SOURCE_RECORD_BINDING'):
        classify(uid='8666895',day='2025-05-01',timing=timing,site_segments=rows,segment_evidence=evidence)
