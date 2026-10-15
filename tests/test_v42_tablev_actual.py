"""Native0 Table V integration tests; no May performance is inferred."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime, timezone, timedelta
import gzip
import json
import numpy as np
import pytest

from test_v42_integration_actual import request,qos
from v42_capacity.actual import Environment
from v42_integration.actual import run_actual
from v42_integration.qos import CausalReferenceScheduler
from v42_integration.tablev_actual import (TableVReferenceController,project_public_initial,
    _require_mess,run_tablev_actual)


def execute(arm):
    jobs=[request('first',gpu=1,q50=900,compatible=('A',)),
        request('second',submit=1,gpu=1,q50=900,compatible=('A',))]
    return run_actual({'A':1},jobs,Environment({'first':450,'second':450}),arm=arm,
        qos_window_provider=qos(),end=2700,controller_class=TableVReferenceController)


def test_b0_b2_have_identical_reference_aidc_trace_without_grid_veto():
    b0,b2=execute('B0'),execute('B2')
    np.testing.assert_array_equal(b0['occupancy_GPU'],b2['occupancy_GPU'])
    assert b0['job_event_ledger']==b2['job_event_ledger']
    assert b0['queue_ledger']==b2['queue_ledger']
    for result in (b0,b2):
        assert result['carryout']['controller']['tablev_state']['sensitivity_reads']==0
        assert not result['carryout']['controller']['tablev_state']['electrical_admission_veto_added']


def test_reference_uses_observed_completion_immediately_without_changing_dispatch_grid():
    result=execute('B0')
    assert result['occupancy_GPU'][0,0]==.5
    jobs=result['carryout']['controller']['episode_jobs']
    assert jobs['first']['completion_observed_time']==450
    assert jobs['first']['release_control_time']==450
    starts={r['job_uid']:r['admitted_time'] for r in result['queue_ledger']}
    assert starts=={'first':0,'second':900}


@pytest.mark.parametrize('arm',['B1','B3'])
def test_reference_controller_cannot_silently_relabel_flexible_arm(arm):
    with pytest.raises(ValueError,match='GRID_BLIND_REFERENCE'):
        TableVReferenceController({'A':1},arm=arm,qos_window_provider=qos())


def projection_fixture():
    raw_request=request('K',source_site=None,origin_unknown=True,episode_id='episode',elapsed_compute_seconds=0,
        can_prestart_place=False,protected=None,batch_eligible=None)
    raw=dict(uid='K',site=None,submit_seconds=0,gpu=1,q50=900,compatible_sites=['A','B'],
        episode_id='episode',elapsed_compute_seconds=0,origin_unknown=True,metadata=deepcopy(raw_request.metadata))
    state=dict(begin_epoch_seconds=0,common_initial_state_sha='initial',running=[],pending=[raw])
    future=request('U',submit=900,can_prestart_place=False)
    opaque=object();provider=SimpleNamespace(provider_sha='provider')
    reference=CausalReferenceScheduler({'A':1,'B':1},reference_sha='reference')
    reference.submit(raw_request,event_seconds=0)
    args=dict(begin=0,requests=[raw_request,future],running=[],environment=opaque)
    return args,state,reference,provider,raw_request,future


def test_initial_1624_projection_pattern_keeps_private_environment_and_source_flags():
    args,state,reference,provider,raw,future=projection_fixture();before=deepcopy(raw.metadata)
    result=project_public_initial(args,state,reference=reference,provider=provider)
    assert result['environment'] is args['environment'] and result['requests'][1] is future
    projected=result['requests'][0]
    assert projected.metadata['origin_unknown'] is False and projected.metadata['cc4_eligible'] is False
    assert projected.metadata['can_prestart_place'] is False and raw.metadata==before
    assert projected.source_site is None


@pytest.mark.parametrize('field,value',[('gpu',2),('q50',1800),('submit',1),('compatible',('B',))])
def test_initial_projection_refuses_request_service_or_source_drift(field,value):
    args,state,reference,provider,raw,_=projection_fixture()
    args['requests'][0]=replace(raw,**{field:value})
    with pytest.raises(ValueError,match='PUBLIC_REQUEST_DRIFT'):
        project_public_initial(args,state,reference=reference,provider=provider)


def test_reference_cannot_consume_saved_or_current_mess_on_plan():
    with pytest.raises(ValueError,match='MESS_OFF_REJECTS_ON_PLAN'):
        _require_mess({},'B0',{'mess':{'plan_sha':'old'}},None)


def test_truth_preparation_stays_below_official_contract_gate(tmp_path,monkeypatch):
    from v42_integration import tablev_actual
    monkeypatch.setattr(tablev_actual,'prepare_reference_inputs',lambda *a,**k:pytest.fail('private bank read'))
    with pytest.raises(ValueError,match='SETTLED_AC_CONTRACT'):
        run_tablev_actual(context={},arm='B0',reference_result={},reference_acceptance={},output=tmp_path/'new',gate={})
    assert not (tmp_path/'new').exists()


def test_actual_source_freeze_calls_original_two_argument_verifier_and_retains_exact_code(tmp_path):
    from v42_integration.tablev_actual import _source_freeze
    from v42_integration.coordinator import verify_sources
    from v42_integration.m_engine import file_record
    original=file_record(__import__('v42_integration.tablev_actual',fromlist=['']).__file__)
    freeze=_source_freeze({'manifest':{'source_freeze':{'files':[]}}},{'sources':[original]},tmp_path)
    verify_sources(freeze,[])
    saved=next(r for r in freeze['files'] if r['path'].endswith('tablev_actual.py'))
    assert saved['sha256']==original['sha256'] and saved['bytes']==original['bytes']
    assert Path(saved['path']).parent.name=='EXECUTED_SOURCE'


def date_private_fixture(tmp_path,monkeypatch,day):
    """Two public D0 jobs and one named dummy private future request."""
    from test_v42_d0_actual_inputs import fixture
    from v42_integration import tablev_actual as api, release_date_case
    from v42_integration.m_engine import file_record
    from v42_integration.policy import digest
    from v42_integration.table_v_flex_planning import compile_public_reference
    state,_,_,strict=fixture()
    begin=datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10))).timestamp()
    delta=begin-state['begin_epoch_seconds']
    state.update(day=day,begin_epoch_seconds=begin,end_epoch_seconds=begin+86400,capacities={'A':4,'B':4})
    for i,row in enumerate(state['running']+state['pending']):
        row['submit_seconds']+=delta
        if row['observed_start_seconds'] is not None:row['observed_start_seconds']+=delta
        row['metadata']['representation_starts_seconds']=tuple(begin+n*900 for n in range(96))
        row.update(source_member='NAMED_DUMMY.parquet',source_row=i,initial_site_authority='NAMED_PUBLIC_ONLY')
    state['running'][0]['origin_unknown']=False
    def stamp(seconds):return datetime.fromtimestamp(seconds,timezone.utc).isoformat()
    def request_row(uid,index,submit):
        return dict(job_uid=uid,source_member='NAMED_DUMMY.parquet',source_row=index,submit_time=stamp(submit),
            GPU_gang=1,Q50_total_seconds=1800,compatible_sites=['A','B'],request_version_history='UNVERIFIED_SOURCE_PROXY')
    plan=dict(day=day,capacities=state['capacities'],slot_seconds=900,issue_time=stamp(begin-21600),
        known_population=[request_row('R',0,begin-7200)],
        forecast_inputs={'current_CC4':{'Q50_GPUh':[1.]*24,'Q90_GPUh':[2.]*24}})
    actual=dict(day=day,capacities=state['capacities'],slot_seconds=900,
        post_issue_arrivals=[request_row('P',1,begin-7200),request_row('FUTURE',2,begin+900)])
    state['provider_identifiers']=dict(runtime_provider_sha='runtime',CC4_provider_sha=digest(plan['forecast_inputs']['current_CC4']),
        frozen_Q50_values_sha=digest({r['job_uid']:r['Q50_total_seconds'] for r in plan['known_population']+actual['post_issue_arrivals']}))
    truth={u:dict(job_uid=u,source_member='NAMED_DUMMY.parquet',source_row=i,start_time=stamp(left),
        end_time=stamp(right),realized_seconds=right-left)
        for u,i,left,right in [('R',0,begin-2700,begin+3000),('P',1,begin+5000,begin+6000),('FUTURE',2,begin+1800,begin+2700)]}
    archive=tmp_path/'archive';raw=archive/'raw'/day;raw.mkdir(parents=True)
    private=tmp_path/'NAMED_DUMMY_PRIVATE_SOURCE.txt';private.write_text('DUMMY_ONLY')
    for name,value in [('PLANNING_INPUT_BUNDLE.json',plan),('ACTUAL_INPUT_BUNDLE.json',actual),
            ('SOURCE_PROVENANCE.json',{'archive':file_record(private)}),('POWER_AUTHORITY.json',{})]:
        (raw/name).write_text(json.dumps(value),encoding='utf8')
    initial=tmp_path/'INITIAL.json.gz';initial.write_bytes(gzip.compress(json.dumps(state).encode(),mtime=0))
    stats=tmp_path/'STATS.txt';stats.write_text('DUMMY_STATS')
    context=dict(manifest=dict(day=day,identity={'case_sha':'current-'+day},source_sha='source',
        source_freeze={'files':[]},initial_record=file_record(initial)),state=state,
        forecast={'Q50_GPUh':[1.]*24,'Q90_GPUh':[2.]*24})
    monkeypatch.setattr(release_date_case,'_require_context',lambda context:None)
    monkeypatch.setattr(api,'_require_reference',lambda *args:compile_public_reference(state)[0])
    monkeypatch.setattr(api,'ARCHIVE',archive)
    monkeypatch.setattr(api,'STRICT_STATS',stats)
    monkeypatch.setattr(api,'STRICT_STATS_SHA',file_record(stats)['sha256'])
    monkeypatch.setattr(api,'load_stats',lambda path:strict.stats)
    extractions=[]
    def extract(population,record):extractions.append(day);return truth,record
    monkeypatch.setattr(api,'_load_private_truth',extract)
    monkeypatch.setattr(api,'_power_model',lambda *args:(object(),[]))
    class Observations:
        sources=[]
        def at(self,when,*,observed_now):
            assert when==observed_now and begin<=when<begin+86400
            return {'weather':{'values':{'t_wb_c':20.,'rh_pct':50.}}}
    monkeypatch.setattr(api.CausalObservations,'load',lambda *args,**kwargs:Observations())
    return api,context,raw,extractions


@pytest.mark.parametrize('day',['2025-05-02','2025-05-31'])
def test_private_actual_preparation_uses_date_roster_and_leaves_future_unknown(tmp_path,monkeypatch,day):
    api,context,raw,extractions=date_private_fixture(tmp_path,monkeypatch,day)
    prepared=api.prepare_reference_inputs(context,reference_result={},reference_acceptance={},output=tmp_path/'PREPARE')
    args=prepared['arguments'];receipt=prepared['projection_receipt']
    assert prepared['raw_folder']==raw and receipt['day']==day
    assert receipt['approved_initial_Known']==2 and receipt['initial_GPU']==1
    assert len(args['running'])==1 and args['end']-args['begin']==96*900 and len(args['weather'])==96
    assert set(args['reference'].assigned)=={'R','P'} and extractions==[day]
    future=next(r for r in args['requests'] if r.uid=='FUTURE')
    assert future.metadata['origin_unknown'] is True and future.metadata['cc4_eligible'] is True
    assert not {'start_time','end_time','realized_seconds','actual_runtime'}&future.metadata.keys()
    assert receipt['Native_calls']==0 and not receipt['private_bank']['private_Environment_fields_read']


def test_other_day_private_descriptor_stops_before_truth_extraction(tmp_path,monkeypatch):
    api,context,raw,extractions=date_private_fixture(tmp_path,monkeypatch,'2025-05-31')
    source=raw/'ACTUAL_INPUT_BUNDLE.json';doc=json.loads(source.read_text());doc['day']='2025-05-01'
    source.write_text(json.dumps(doc),encoding='utf8')
    with pytest.raises(ValueError,match='SAME_DATE_SOURCE_AXIS'):
        api.prepare_reference_inputs(context,reference_result={},reference_acceptance={},output=tmp_path/'REJECTED')
    assert extractions==[] and not (tmp_path/'REJECTED').exists()


def test_fresh_rejects_another_days_actual_receipt_before_any_source_read(tmp_path,monkeypatch):
    from v42_integration import tablev_actual as api
    context={'manifest':{'day':'2025-05-31'}}
    actual=dict(schema=api.SCHEMA,fixture=False,Actual_stage_PASS=True,day='2025-05-01')
    monkeypatch.setattr(api,'checked',lambda *args:pytest.fail('another day source opened'))
    with pytest.raises(ValueError,match='EXACT_CURRENT_ACTUAL'):
        api.run_tablev_fresh(context=context,actual_result=actual,output=tmp_path/'REJECTED')
    assert not (tmp_path/'REJECTED').exists()
