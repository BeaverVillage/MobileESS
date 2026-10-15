"""Named public/dummy IO fixtures; never opens retrospective real service."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import gzip
import json
import runpy

import pytest

from v42_integration import release_private_actual_inputs as api
from v42_integration.d0_actual_inputs import D0DriverProjection
from v42_integration.m_engine import file_record
from v42_integration.policy import digest


def fixture(tmp_path,monkeypatch):
    source=runpy.run_path(str(Path(__file__).with_name('test_v42_d0_actual_inputs.py')))
    state,provider,args,strict=source['fixture']()
    begin=state['begin_epoch_seconds'];day='1970-01-02'
    state.update(day=day,capacities=dict(A=4,B=4),end_epoch_seconds=begin+86400)
    state['running'][0]['origin_unknown']=False
    for row in state['running']+state['pending']:
        row.update(source_member='NAMED_FIXTURE.parquet',source_row=0 if row['uid']=='R' else 1,
            initial_site_authority='NAMED_PUBLIC_FIXTURE_ONLY')
    def stamp(seconds):
        return datetime.fromtimestamp(seconds,timezone.utc).isoformat()
    def descriptor(uid,submit,q50,index):
        return dict(job_uid=uid,submit_time=stamp(submit),GPU_gang=1,compatible_sites=['A','B'],
            Q50_total_seconds=q50,source_member='NAMED_FIXTURE.parquet',source_row=index,
            request_version_history='UNVERIFIED_SOURCE_PROXY')
    r=descriptor('R',begin-7200,1800,0);p=descriptor('P',begin-7200,1800,1)
    f=descriptor('FUTURE',begin+900,1800,2);c=descriptor('COMPLETED',begin-10000,900,3)
    plan=dict(day=day,capacities=state['capacities'],issue_time=stamp(begin-21600),slot_seconds=900,
        known_population=[r,c],forecast_inputs=dict(current_CC4=dict(Q50_GPUh=[1.]*24,Q90_GPUh=[2.]*24)))
    actual=dict(day=day,capacities=state['capacities'],slot_seconds=900,post_issue_arrivals=[p,f])
    population=plan['known_population']+actual['post_issue_arrivals']
    state['provider_identifiers']=dict(CC4_provider_sha=digest(plan['forecast_inputs']['current_CC4']),
        frozen_Q50_values_sha=digest({r['job_uid']:r['Q50_total_seconds'] for r in population}))
    truth={}
    for uid,start,end,index in [('R',begin-2700,begin+3000,0),('P',begin+5000,begin+6000,1),
                              ('FUTURE',begin+1800,begin+2700,2),('COMPLETED',begin-8000,begin-4000,3)]:
        truth[uid]=dict(job_uid=uid,start_time=stamp(start),end_time=stamp(end),realized_seconds=end-start,
            source_member='NAMED_FIXTURE.parquet',source_row=index)
    raw=tmp_path/'archive'/'raw'/day;raw.mkdir(parents=True)
    archive=tmp_path/'NAMED_PRIVATE_SOURCE.txt';archive.write_text('NAMED_DUMMY_PRIVATE_BANK_ONLY')
    for name,value in [('PLANNING_INPUT_BUNDLE.json',plan),('ACTUAL_INPUT_BUNDLE.json',actual),
                       ('SOURCE_PROVENANCE.json',dict(archive=file_record(archive))),('POWER_AUTHORITY.json',{})]:
        (raw/name).write_text(json.dumps(value),encoding='utf8')
    initial=tmp_path/'INITIAL.json.gz';initial.write_bytes(gzip.compress(json.dumps(state).encode(),mtime=0))
    stats=tmp_path/'STRICT_STATS_NAMED_FIXTURE.json';stats.write_text('NAMED_STATISTICS_ONLY')
    manifest=dict(identity=provider.identity,source_sha='1'*64,source_freeze=dict(files=[]),
        initial_record=file_record(initial),time_axis=dict(planning_issue_epoch_seconds=begin))
    context=dict(state=state,manifest=manifest,backlog=provider.contract,
        forecast=dict(Q50_GPUh=[1.]*24,Q90_GPUh=[2.]*24))
    monkeypatch.setattr(api,'ARCHIVE',tmp_path/'archive')
    monkeypatch.setattr(api,'STRICT_STATS',stats)
    monkeypatch.setattr(api,'STRICT_STATS_SHA',file_record(stats)['sha256'])
    monkeypatch.setattr(api,'load_stats',lambda path:strict.stats)
    monkeypatch.setattr(api,'_state',lambda context:state)
    return state,plan,actual,truth,context,raw


def dummy_pipeline(tmp_path,monkeypatch,*,slots=16):
    state,plan,actual,truth,context,raw=fixture(tmp_path,monkeypatch)
    calls=[]
    gate=dict(evaluation_case_sha='a'*64,preparation_gate_sha='b'*64)
    monkeypatch.setattr(api,'_require_gate',lambda context,s:(gate,state['day']))
    def private(population,record):
        calls.append('NAMED_DUMMY_PRIVATE_EXTRACTION')
        return truth,record
    monkeypatch.setattr(api,'_load_private_truth',private)
    power=object();monkeypatch.setattr(api,'_power_model',lambda power,caps:(power,[]))
    class Observations:
        sources=[]
        def at(self,when,*,observed_now):
            assert when==observed_now
            return dict(weather=dict(values=dict(t_wb_c=20.,rh_pct=50.)))
    observations=Observations()
    monkeypatch.setattr(api.CausalObservations,'load',lambda *a,**kw:observations)
    def projection(arguments,**kwargs):
        assert kwargs['provider'].strict.receipts=={}
        assert kwargs['provider'].identity==context['manifest']['identity']
        # The projection is independently tested against the original typed
        # contract; this fixture exercises this adapter's IO only.
        return D0DriverProjection(arguments,dict(status='NAMED_PUBLIC_FIXTURE_ONLY'))
    monkeypatch.setattr(api,'project_date_driver_arguments',projection)
    result=api.prepare_private_actual_inputs(context,output=tmp_path/'output',slots=slots)
    return result,context,calls,observations


def test_missing_gate_stops_before_any_private_or_raw_read(tmp_path,monkeypatch):
    _,_,_,_,context,_=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(api,'_load_private_truth',lambda *a:pytest.fail('PRIVATE_READ_BEFORE_GATE'))
    monkeypatch.setattr(api,'read',lambda *a:pytest.fail('DESCRIPTOR_READ_BEFORE_GATE'))
    with pytest.raises(ValueError,match='POST_GATE'):
        api.prepare_private_actual_inputs(context,output=tmp_path/'output')
    assert not (tmp_path/'output').exists()


def test_dummy_private_preparation_is_not_actual_and_future_absent_from_reference(tmp_path,monkeypatch):
    r,c,calls,observations=dummy_pipeline(tmp_path,monkeypatch)
    args=r['arguments'];receipt=r['projection_receipt']
    assert calls==['NAMED_DUMMY_PRIVATE_EXTRACTION']
    assert args['end']-args['begin']==16*900 and len(args['weather'])==16
    assert set(args['reference'].assigned)=={'R','P'}
    assert args['qos_window_provider'].receipts=={} and args['qos_window_provider'].strict.receipts=={}
    assert {x.uid for x in args['requests']}=={'P','FUTURE'}
    assert r['observations'] is observations
    assert receipt['Native_calls']==receipt['AC_calls']==receipt['Actual_calls']==0
    assert receipt['private_bank']['private_Environment_fields_read'] is False
    for request in [args['running'][0][0],*args['requests']]:
        api._require_public_metadata(request.metadata)
        assert not {'start_time','end_time','realized_seconds'}&set(request.metadata)
    assert args['running'][0][1:]==('A',c['state']['running'][0]['observed_start_seconds'])
    decoded=receipt['initial_state_decode']
    assert digest(json.loads(Path(decoded['decoded_record']['path']).read_text()))==digest(c['state'])
    assert decoded['source_record']==c['manifest']['initial_record']


@pytest.mark.parametrize('change,error',[
    ('gpu','IMMUTABLE_PUBLIC'),('q50','IMMUTABLE_PUBLIC'),('member','IMMUTABLE_PUBLIC'),
    ('roster','INITIAL_SOURCE_UID'),('cc4','CC4_FROZEN_Q50')])
def test_public_source_drift_rejected_before_private_extraction(tmp_path,monkeypatch,change,error):
    state,plan,actual,_,_,_=fixture(tmp_path,monkeypatch)
    if change=='gpu':state['pending'][0]['gpu']=2
    elif change=='q50':state['pending'][0]['q50']=42
    elif change=='member':state['pending'][0]['source_row']=999
    elif change=='roster':actual['post_issue_arrivals']=actual['post_issue_arrivals'][1:]
    else:state['provider_identifiers']['CC4_provider_sha']='f'*64
    with pytest.raises(ValueError,match=error):api._public_source_join(state,plan,actual)


@pytest.mark.parametrize('change,error',[
    ('missing','COMPLETE_SOURCE_TRUTH'),('running','RUNNING_SOURCE_HISTORY'),
    ('pending','PENDING_SOURCE_OBSERVED_STATE'),('private','REALIZATION_EVENT_ORDER')])
def test_private_dummy_join_cannot_rewrite_boundary_history(tmp_path,monkeypatch,change,error):
    state,plan,actual,truth,_,_=fixture(tmp_path,monkeypatch)
    if change=='missing':truth.pop('R')
    elif change=='running':state['running'][0]['observed_start_seconds']-=900
    elif change=='pending':
        truth['P']['start_time']=truth['R']['start_time'];truth['P']['realized_seconds']=8700
    else:truth['P']['realized_seconds']=-1
    with pytest.raises(ValueError,match=error):api._driver_bank(state,plan,actual,truth)


def test_private_future_descriptor_discards_retrospective_labels(tmp_path,monkeypatch):
    state,plan,actual,truth,_,_=fixture(tmp_path,monkeypatch)
    actual['post_issue_arrivals'][1].update(start_observed_by_day_end='PRIVATE',end_observed_by_day_end='PRIVATE',
        actual_runtime=12345,realized_seconds=12345)
    bank,receipt=api._driver_bank(state,plan,actual,truth)
    request=next(r for r in bank['requests'] if r.uid=='FUTURE')
    api._require_public_metadata(request.metadata)
    assert request.metadata['origin_unknown'] is True and request.metadata['cc4_eligible'] is True
    assert receipt['private_completion_or_duration_in_request_metadata'] is False


def test_output_must_not_overwrite_existing_private_inputs(tmp_path,monkeypatch):
    r,c,_,_=dummy_pipeline(tmp_path,monkeypatch)
    with pytest.raises(FileExistsError,match='MUST_NOT_OVERWRITE'):
        api.prepare_private_actual_inputs(c,output=tmp_path/'output',slots=16)


def gate_fixture(context,monkeypatch,*,slots=16):
    identity=context['manifest']['identity'];source_sha=context['manifest']['source_sha']
    a=dict(stage='A2',case_sha='a'*64,aidc_anchor='b'*64,FULL_point_replay=dict(point_sha256='c'*64))
    m=dict(stage='M2',case_sha='d'*64,D0_source_identity=identity,D0_fixed_AIDC_anchor=a['aidc_anchor'],
        binding=dict(aidc_anchor=a['aidc_anchor']),mess=dict(case_sha='d'*64,plan_sha='e'*64))
    aa=dict(stage_case_sha=a['case_sha'],source_sha=source_sha,acceptance_sha='f'*64,AIDC_anchor=a['aidc_anchor'],
        Original_FULL=dict(PASS=True,FULL_max_residual=0.,point_sha256='c'*64))
    ma=dict(stage_case_sha=m['case_sha'],source_sha=source_sha,parent_acceptance_sha=aa['acceptance_sha'],
        acceptance_sha='0'*64,AIDC_anchor=a['aidc_anchor'],MESS_anchor=m['mess']['plan_sha'],
        Original_FULL=dict(PASS=True,original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha=m['case_sha']),
            strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True))
    ancestors=dict(A2_result=a,A2_acceptance=aa,M2_result=m,M2_acceptance=ma)
    policy=dict(mode='SOURCE_STRICT',variant='C0')
    source_case=dict(day='1970-01-02',source_identity=identity,source_sha=source_sha)
    payload=api.actual_evaluation_case_payload(source_case,ancestors,policy,slots)
    gate=dict(schema=api.GATE_SCHEMA,status='PASS',source_identity=identity,source_sha=source_sha,
        clock_contract=api.CONTRACT,slots=slots,ancestors=ancestors,actual_policy=policy,
        evaluation_case_payload=payload,evaluation_case_sha=digest(payload))
    gate['preparation_gate_sha']=digest(gate);context['private_actual_preparation_gate']=gate
    monkeypatch.setattr(api,'require_production_acceptance',lambda *a,**kw:None)
    monkeypatch.setattr(api,'compile_date_commands',lambda *a:dict(NAMED_FIXTURE_ONLY=True))
    monkeypatch.setattr(api,'_full_a',lambda a:a)
    monkeypatch.setattr(api,'_full_m',lambda m:m['mess'])
    return gate


def test_post_gate_checks_exact_parent_full_and_canonical_science(tmp_path,monkeypatch):
    *_,context,_=fixture(tmp_path,monkeypatch)
    gate=gate_fixture(context,monkeypatch)
    assert api._require_gate(context,16)[0] is gate
    gate['ancestors']['M2_acceptance']['AIDC_anchor']='9'*64
    gate['preparation_gate_sha']=digest({k:v for k,v in gate.items() if k!='preparation_gate_sha'})
    with pytest.raises(ValueError,match='SOURCE_CHAIN'):api._require_gate(context,16)


def test_self_sealed_gate_still_requires_real_stage_acceptance(tmp_path,monkeypatch):
    *_,context,_=fixture(tmp_path,monkeypatch)
    gate_fixture(context,monkeypatch)
    def reject(*a,**kw):raise ValueError('REAL_PRODUCTION_REQUIRED')
    monkeypatch.setattr(api,'require_production_acceptance',reject)
    with pytest.raises(ValueError,match='REAL_PRODUCTION'):api._require_gate(context,16)


def test_gate_cannot_change_slots_or_reuse_other_evaluation_case(tmp_path,monkeypatch):
    *_,context,_=fixture(tmp_path,monkeypatch)
    gate=gate_fixture(context,monkeypatch)
    with pytest.raises(ValueError,match='POST_GATE'):api._require_gate(context,96)
    gate['evaluation_case_sha']='7'*64
    gate['preparation_gate_sha']=digest({k:v for k,v in gate.items() if k!='preparation_gate_sha'})
    with pytest.raises(ValueError,match='CANONICAL_EVALUATION'):api._require_gate(context,16)
