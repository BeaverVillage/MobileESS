"""Small existing-core fixtures and mock 28-case routing; never dispatch solvers."""
from pathlib import Path
from copy import deepcopy
import importlib.util
import json
import numpy as np
import pytest

from v44.common import ROOT,DOC,atomic,read,digest
from v44.config import DAYS,ARMS


def original_fixture():
    spec=importlib.util.spec_from_file_location('v44_original_matrix_fixture',ROOT/'tests/test_v43_mess_library.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.example()


@pytest.mark.parametrize('day',DAYS)
def test_original_seedless_k16_rules_with_dated_identity(day,tmp_path):
    from v44.frozen.v43_mess.library import load,current_identity
    from v44.frozen.v43_mess.prepared import run_prepared_k48
    case=original_fixture();case.identity.update(schema='V44_DATED_FIXED_AIDC_MESS_CASE_V1',day=day)
    case.bundle['day']=day;case.case_sha=digest(case.identity)
    k=load()['table_v_k48'];packet,proof=k.prepare_k16(case,None,tmp_path/'K16')
    assert proof['PASS'] and proof['Native_optimize_calls']==0
    assert packet['start'] is None and packet['source']['day']==day
    assert sum(n.startswith('charge_mode[') for n in packet['d']['names'])==384
    assert current_identity(case)['stage_case_sha']==case.case_sha
    old=packet
    for count in (32,48):
        cuts,_=k.separate(case,old,np.zeros(len(old['columns'])))
        new,cert=k.append_cuts(case,old,cuts,tmp_path/str(count))
        assert cert['K']==count and cert['PASS']
        assert (new['A'][:old['A'].shape[0]]!=old['A']).nnz==0
        old=new
    assert k.summarize_current_k48(old,cert,[])['Global_LB'] is None


def test_b3_uid8632559_adapter_reuses_relaxed_known_and_unknown_policy():
    from test_v43_relaxed_known_window import make
    from v44.actual_policy import B3RelaxedKnownController
    class Fixture(B3RelaxedKnownController):
        def __init__(self,*args,**kwargs):super().__init__(*args,**dict(kwargs,arm='B3'))
    c,r=make(cls=Fixture,start=18.5*3600,reference=18*3600,latest=18*3600)
    c.submit(r,r.submit)
    assert c.admit(18*3600)==[]
    assert c.admit(18.5*3600)==[r.uid]
    assert c.arm=='B3' and c.known_schedule[r.uid]['site']=='A'
    assumption=next(e for e in c.events if e['event']=='KNOWN_RESEARCH_WINDOW_ASSUMPTION')
    assert 'V44_B1_B3' in assumption['scope'] and not assumption['Source_authority_promoted']


def test_driver_preserves_original_fresh_rewrite_boundaries(tmp_path):
    import v43_actual.compare as original
    import v43_baseline.worker as baseline
    from v44.worker import driver
    a=driver(original.run,tmp_path/'actual.py');b=driver(baseline.run,tmp_path/'baseline.py')
    body=(tmp_path/'actual.py').read_text(encoding='utf8')
    assert body.count('fresh=oracle._probe(rows)')==1
    assert body.count("for variant in ('C0','C1'):")==1
    assert 'from v44.execution import shared_lease_scope as exclusive_lock' in body
    assert a.__code__.co_name==b.__code__.co_name=='run'


def test_28_case_mock_stage_chain_and_same_day_a1_reuse(tmp_path,monkeypatch):
    import v44.campaign as campaign
    import v44.worker as worker
    import v44.daily as daily
    from v44.locks import coordinator
    calls=[]
    def load(folder,day):
        doc=read(Path(folder)/'AIDC_REFERENCE.json')
        return dict(bundle=dict(day=day),planning={},identity=doc['identity']),doc
    def aidc(folder,day,arm,stage):
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        atomic(folder/'AIDC_REFERENCE.json',dict(identity=dict(day=day,arm=arm,stage=stage,reused_exact_A1=stage=='A1')))
        return load(folder,day)[0]
    def reference(day,output):calls.append((day,'B0','REFERENCE'));return aidc(output,day,'B0','REFERENCE')
    def a_stage(request,*,m1=None):
        day,arm,stage=(request[k] for k in ('day','arm','stage'));calls.append((day,arm,stage))
        if stage=='A2':assert m1['day']==day and m1['stage']=='M1'
        folder=Path(request['root'])/'AIDC_FROZEN';aidc(folder,day,arm,stage)
        cache=Path(request['output'])/'STATIC/DOMAIN'/day/'PHYSICAL_DOMAIN_CACHE.json'
        atomic(cache,dict(complete_domain_hashes={'fixture':day}))
        atomic(Path(request['output'])/'A_PREPARE_RECEIPT.json',dict(verification={'day':day}))
        from v44.common import record
        result=dict(day=day,arm=arm,stage=stage,PASS=True,AIDC_reference=record(folder/'AIDC_REFERENCE.json'),
            FULL_feasible=True,P2_calls=0,certified_gap=.004,independent_Global_LB_validated=True,finished_UTC='fixture')
        atomic(Path(request['root'])/'RESULT.json',result)
        return result
    def m_stage(request,aidc):
        day,arm,stage=(request[k] for k in ('day','arm','stage'));calls.append((day,arm,stage))
        assert aidc['identity']['day']==day
        assert aidc['identity']['stage']==('REFERENCE' if arm=='B2' else 'A1' if stage=='M1' else 'A2')
        result=dict(day=day,arm=arm,stage=stage,allow_downstream=True,MESS_plan={'day':day,'stage':stage})
        atomic(Path(request['output'])/'RESULT.json',result);return result
    def actual(request,folder,mess):
        day,arm=(request[k] for k in ('day','arm'));calls.append((day,arm,'ACTUAL_FRESH'))
        if arm in ('B2','B3'):assert mess['day']==day
        else:assert mess is None
        return dict(PASS=True)
    monkeypatch.setattr(daily,'day_inputs',lambda day:dict(day=day,native_folder=str(tmp_path/'input'),files={}))
    monkeypatch.setattr(daily,'load_aidc',load)
    for name,function in [('reference',reference),('a_stage',a_stage),('m_stage',m_stage),('actual',actual)]:monkeypatch.setattr(worker,name,function)
    # Inputs are tiny named fixtures here. Their existing receipt paths are
    # read only when creating A1's cache proof; no real data or models are read.
    native=tmp_path/'input';native.mkdir();atomic(native/'NATIVE_INPUT.json',{});atomic(native/'WINDOWS.json',{})
    original=campaign.stage_request
    def stage_request(case,stage):return dict(original(case,stage),input_folder=str(native))
    monkeypatch.setattr(campaign,'stage_request',stage_request)
    with coordinator(tmp_path,external=[]) as lease:
        for lane,arms in [('B2',('B2',)),('MAIN',('B0','B1','B3'))]:
            atomic(tmp_path/'PHASE.json',dict(lane=lane))
            for day in DAYS:
                for arm in arms:
                    request=dict(day=day,arm=arm,worker_slot=1,case_root=str(tmp_path/day/arm/'attempt001'),
                        campaign_root=str(tmp_path),lease=lease,sources=[],source_sha=digest([]))
                    result=campaign.run_case(request)
                    assert result['status']=='COMPLETE',result
    assert sum(stage=='A1' for _,_,stage in calls)==7
    assert sum(stage=='M1' for _,_,stage in calls)==14
    assert sum(stage=='M2' for _,_,stage in calls)==7
    assert sum(stage=='ACTUAL_FRESH' for _,_,stage in calls)==28
    assert not any(arm=='B2' and stage in ('A1','A2') for _,arm,stage in calls)


@pytest.mark.parametrize('day',DAYS)
def test_actual_wrapper_uses_dated_midnight_and_c1_without_running_driver(day,tmp_path,monkeypatch):
    import v44.worker as worker
    import v43_corrective.compare as original
    from v44.config import axis,KNOWN_POLICY
    from v44.common import record
    # Replace only the final execution boundary: no Actual, AC, or Native call.
    def run(arm,output,**kwargs):
        return dict(PASS=True,arm=arm,day_start_seconds=1746021600.,options=kwargs)
    monkeypatch.setattr(original,'run',run)
    monkeypatch.setattr(worker,'assert_current',lambda:None)
    monkeypatch.setattr(worker,'day_inputs',lambda d:dict(actual_bundle='D:/fixture/'+d))
    monkeypatch.setattr(worker,'corrective_binding',lambda *a:object())
    monkeypatch.setattr(worker,'driver',lambda function,path:function)
    import v44.svr11_actual as svr11
    def routed(original,proxy,binding,midnight):
        return lambda arm,output,**kw:dict(PASS=True,arm=arm,day_start_seconds=midnight,options=kw)
    monkeypatch.setattr(svr11,'corrective_driver',routed)
    proof=tmp_path/'MOCK_PROOF.json';atomic(proof,dict(mock=True))
    request=dict(output=str(tmp_path/'ACTUAL'),day=day,arm='B3',stage='ACTUAL',
        correction_proof=record(proof),case_root=str(tmp_path),sources=[],source_sha=digest([]))
    result=worker.actual.__wrapped__(request,'D:/fixture_A2',{'frozen':True})
    assert result['day_start_seconds']==axis(day)['day_start_seconds']
    assert result['options']['variants']==('C1',)
    assert result['options']['known_window_policy']==KNOWN_POLICY
    assert result['options']['control_slots']==120 and result['options']['ac_mode']=='FAST'
    assert result['options']['correction_proof']==str(proof)
    with pytest.raises(worker.NotReady,match='CORRECTION_PROOF_REQUIRED'):
        worker.actual.__wrapped__(dict(request,correction_proof=None),'D:/fixture_A2',{'frozen':True})


def test_monitor_reads_dispatcher_layout_and_distinguishes_physical_fail(tmp_path):
    from v44.monitor import rows
    case=tmp_path/DAYS[0]/'B2'/'attempt001'
    atomic(case/'START.json',dict(pid=123,worker_slot=2))
    atomic(case/'M1/RESULT.json',dict(PASS=True,status='TIME_LIMIT_FULL_FEASIBLE_GAP_NOT_CERTIFIED',
        Global_UB=.6,Global_LB=.4,Global_Gap=1/3,global_gap_certified=False,FULL_feasible=True,
        timeout=True,Native_seconds=1200.,build_wall_seconds=5.))
    atomic(case/'M1/K48_NATIVE_LEDGER.json',dict(measured_Native_Runtime=300.,Native_ceiling_seconds=300.))
    atomic(case/'M1/JOINT_NATIVE_LEDGER.json',dict(measured_Native_Runtime=900.,Native_ceiling_seconds=900.))
    atomic(case/'ACTUAL/RESULT.json',dict(PASS=False,Actual96_execution_PASS=True,Fresh96_physical_PASS=False,
        Actual_wall_seconds=12.,Fresh_wall_seconds=2.))
    data={r['stage']:r for r in rows(dict(cases=[dict(day=DAYS[0],arm='B2',status='INPUT_READY',blockers=[])]),tmp_path)}
    assert data['M1']['FULL_feasible'] is True and data['M1']['FULL_UB']==.6
    assert data['M1']['Native_used']==900. and data['K48_M1']['Native_used']==300.
    assert data['M1']['Native_remaining']==0. and data['M1']['pid']==123
    assert data['ACTUAL']['status']=='COMPLETE' and data['FRESH']['status']=='COMPLETE_PHYSICAL_FAIL'
    assert data['FRESH']['Fresh_wall']==2. and data['ACTUAL']['Actual_wall']==12.


def test_a2_historical_cache_route_does_not_recurse_when_module_is_patched(tmp_path,monkeypatch):
    import v44.daily as daily
    import v43_followup.physical_cache as original
    calls=[]
    def historical(*args,**kwargs):calls.append(kwargs);return {'historical':'domain'}
    monkeypatch.setattr(daily,'_historical_cache_loader',historical)
    monkeypatch.setattr(original,'load_current_date_physical_cache',daily.load_current_date_physical_cache)
    proof=tmp_path/'PROOF.json';atomic(proof,dict(schema='V43_COMPLETED_STATIC_PHYSICAL_CASE_V1'))
    loader=object()
    result=daily.load_current_date_physical_cache({},(),case_proof=proof,original_loader=loader)
    assert result=={'historical':'domain'} and len(calls)==1
    assert calls[0]['original_loader'] is loader
