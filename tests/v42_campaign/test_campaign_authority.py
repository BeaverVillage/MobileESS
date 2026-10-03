import copy,json,threading,os
from pathlib import Path
import pytest
from v42_campaign.authority import MAIN,CONVERGENCE,GROUPS,ARM_SEMANTICS,MAX_B3_LOOPS,EARLY_STOP_ON_CONVERGENCE,file_sha,authority_sha,digest
from v42_campaign.plan import build_plan,dependencies,stage_id
from v42_campaign.engine import CampaignEngine,atomic,handoff
from v42_campaign.firewall import PlanningReads
from v42_campaign.fixtures import exercise,source_fixture,planning_state,CERTIFICATE,DAY,ISSUE
from v42_campaign.state import freeze_state,detector,metrics,main_comparison

@pytest.fixture(scope='module')
def full_plan():return build_plan()
@pytest.fixture(scope='module')
def bounded(tmp_path_factory):return exercise(tmp_path_factory.mktemp('campaign_bound'))
def test_01_main_order(full_plan):
    assert full_plan['main_order']==['B0','B1','B2','B3_L1']
    groups=list(dict.fromkeys(n['group'] for n in full_plan['nodes'] if n['group']))
    assert groups==list(GROUPS) and len(full_plan['days'])==31 and len(full_plan['nodes'])==1458
def test_02_each_main_arm_finishes_actual_fresh(full_plan):
    nodes=full_plan['nodes']
    for group in MAIN[1:]:
        first=next(n for n in nodes if n['group']==group)
        assert first['predecessor'].endswith('/2025-05-31/VALIDATION_FREEZE')
    for group in MAIN:
        stages=[n['stage'] for n in nodes if n['group']==group and n['day']==DAY]
        assert stages[-4:]==['PLANNING_FREEZE','ACTUAL','FRESH_AC','VALIDATION_FREEZE']
def test_03_b3_only_convergence(full_plan):assert set(n['group'] for n in full_plan['nodes'] if n['phase']=='CONVERGENCE')==set(CONVERGENCE)
def test_04_no_other_arm_repetition(full_plan):
    for arm in ('B0','B1','B2'):assert sum(n['stage']=='PLANNING_FREEZE' and n['arm']==arm for n in full_plan['nodes'])==31
def test_05_each_b3_exact_stages(full_plan):
    for group in ('B3_L1',*CONVERGENCE):assert [n['stage'] for n in full_plan['nodes'] if n['group']==group and n['day']==DAY and n['planning']]==['A1','M1','A2','M2']
@pytest.mark.parametrize('loop',[2,3,4],ids=['06_L2','07_L3','08_L4'])
def test_previous_loop_planning_seed(loop,full_plan,bounded):
    node=next(n for n in full_plan['nodes'] if n['id']==stage_id(f'B3_L{loop}',DAY,'A1'))
    assert node['Planning_dependencies']==[stage_id(f'B3_L{loop-1}',DAY,'PLANNING_FREEZE')]
    transfer=next(h for h in bounded['handoffs'] if h['stage']==node['id'])
    assert transfer['fixed_counterpart']['MESS']==bounded['state_freezes'][f'B3_L{loop-1}']['state']['mess']
    assert transfer['warm_start']['AIDC_fixed'] is False and transfer['free_decisions']==['AIDC']
@pytest.mark.parametrize('kind',['ACTUAL','FRESH_AC'],ids=['09_Actual','10_Fresh'])
def test_actual_fresh_never_dependencies(kind,tmp_path):
    entries,_=source_fixture(tmp_path/'D1');entries[0]['kind']=kind
    with pytest.raises(PermissionError):PlanningReads(entries,issue_time=ISSUE)
def test_11_previous_actual_values_cannot_feed(bounded):
    assert all(h['Actual_values_included'] is False for h in bounded['handoffs'])
    def values(value):
        if isinstance(value,dict):return [v for x in value.values() for v in values(x)]
        if isinstance(value,list):return [v for x in value for v in values(x)]
        return [value]
    for group in ('B3_L2','B3_L3','B3_L4'):
        leaves=values(bounded['state_freezes'][group]['state']);assert all(x not in leaves for x in (999999,888,777))
    assert all(r['Actual_reads']==r['Fresh_AC_reads']==0 and r['PASS'] for r in bounded['read_audits'])
def test_12_actual_status_sequence_gate_only(full_plan):
    first=next(n for n in full_plan['nodes'] if n['id']==stage_id('B3_L2',DAY,'A1'))
    assert first['predecessor']=='MAIN_MAY_CAMPAIGN_COMPLETE'
    assert all('/ACTUAL' not in d and '/FRESH_AC' not in d for n in full_plan['nodes'] for d in n['Planning_dependencies'])
    gate=next(n for n in full_plan['nodes'] if n['id']=='MAIN_MAY_CAMPAIGN_COMPLETE');assert len(gate['required_accepted_freezes'])==124
def test_13_main_separate_from_convergence(bounded):assert list(bounded['main_comparison'])==list(MAIN)
def test_14_l4_does_not_replace_l1():
    result=main_comparison(dict(B0=0,B1=1,B2=2,B3_L1=3,B3_L4=4));assert result['B3_L1']==3 and 'B3_L4' not in result
def test_15_max_loops_four():assert MAX_B3_LOOPS==4
def test_16_no_convergence_early_stop(bounded):assert EARLY_STOP_ON_CONVERGENCE is False and bounded['all_four_loops_completed'] and bounded['fixed_point_did_not_stop'] and bounded['two_cycle_did_not_stop']
def test_17_two_cycle():assert detector(['a','b','a'])==dict(EXACT_FIXED_POINT=False,TWO_CYCLE=True,STILL_EVOLVING=False,stop_requested=False)
def test_18_fixed_point():assert detector(['a','a'])==dict(EXACT_FIXED_POINT=True,TWO_CYCLE=False,STILL_EVOLVING=False,stop_requested=False)
def test_19_resume_authority_mismatch(tmp_path):
    engine=CampaignEngine(tmp_path,source_hashes={'s':'abc'});ledger=engine.ledger;ledger['identity']['authority_sha256']='wrong';atomic(engine.path,ledger)
    with pytest.raises(ValueError,match='RESUME_AUTHORITY'):CampaignEngine(tmp_path,source_hashes={'s':'abc'})
def test_20_campaign_production_calls_zero(bounded,tmp_path):
    assert all(bounded[k]==0 for k in ('optimizer_calls_for_campaign','Actual_calls_for_campaign','Fresh_AC_calls_for_campaign'))
    engine=CampaignEngine(tmp_path,source_hashes={})
    with pytest.raises(PermissionError):engine.production_execute()
    with pytest.raises(PermissionError):engine.begin(engine.plan['nodes'][0]['id'])
    with pytest.raises(PermissionError):CampaignEngine(tmp_path/'production',source_hashes={},mode='PRODUCTION')
def test_arm_semantics_common_population():
    assert all(a['workload_present'] and a['Runtime_CC4_common'] and a['physical_queue_capacity_active'] and not a['ML_OFF'] for a in ARM_SEMANTICS.values())
    assert [(a['AIDC_grid_aware_flexibility'],a['MESS_ON']) for a in ARM_SEMANTICS.values()]==[(False,False),(True,False),(False,True),(True,True)]
def test_m2_route_is_free_not_fixed(bounded):
    m2=next(h for h in bounded['handoffs'] if h['stage'].endswith('/M2'))
    assert set(m2['fixed_counterpart'])=={'AIDC'} and m2['warm_start']['route_fixed'] is False
    assert set(m2['free_decisions'])=={'MESS.route','MESS.movement','MESS.P','MESS.Q','MESS.SOC'}
def test_state_hash_metadata_independent():
    state=planning_state({'D1':'s'});a=freeze_state(state,group='B3_L1',day=DAY);b=freeze_state(state,group='B3_L4',day=DAY)
    assert a['state_sha256']==b['state_sha256'];state['mess']['p']['t0']=123;assert a['state']['mess']['p']['t0']==0
@pytest.mark.parametrize('reader',['open','path','caught'])
def test_raw_actual_reads_blocked(tmp_path,reader):
    entries,_=source_fixture(tmp_path/'D1');actual=tmp_path/'ACTUAL_L1.json';atomic(actual,{'load':999})
    guard=PlanningReads(entries,issue_time=ISSUE)
    with pytest.raises(PermissionError):
        with guard:
            if reader=='path':actual.read_text(encoding='utf8')
            elif reader=='caught':
                try:actual.read_text(encoding='utf8')
                except PermissionError:pass
            else:
                with open(actual) as f:f.read()
    assert not guard.receipt['PASS'] and any(not r['allowed'] for r in guard.attempts)
@pytest.mark.parametrize('mutation',['future','hash','path','producer'])
def test_causal_entry_mutations_rejected(tmp_path,mutation):
    entries,_=source_fixture(tmp_path/'D1')
    if mutation=='future':entries[0]['available_at']='2025-05-01T01:00:00+10:00'
    elif mutation=='hash':entries[0]['sha256']='bad'
    elif mutation=='path':entries[0]['path']=str(tmp_path/'Fresh_AC.json')
    else:entries[0]['producer_phase']='ACTUAL'
    with pytest.raises(PermissionError):
        with PlanningReads(entries,issue_time=ISSUE):pass
def test_guard_background_reader_forbidden(tmp_path):
    entries,_=source_fixture(tmp_path/'D1')
    with pytest.raises(PermissionError):
        with PlanningReads(entries,issue_time=ISSUE):
            try:threading.Thread(target=lambda:None).start()
            except PermissionError:pass
def first_fixture_engine(tmp_path):
    entries,sources=source_fixture(tmp_path/'D1');engine=CampaignEngine(tmp_path/'engine',source_hashes=sources,plan=build_plan([DAY]),mode='SYNTHETIC');return engine,sources
def test_resume_partial_optimizer_refused(tmp_path):
    engine,sources=first_fixture_engine(tmp_path);engine.begin(engine.next_stage()['id'])
    with pytest.raises(ValueError,match='PARTIAL'):CampaignEngine(engine.root,source_hashes=sources,plan=engine.plan,mode='SYNTHETIC')
    engine.fail(engine.active_stage,'test cleanup')
def test_resume_source_mismatch(tmp_path):
    engine,sources=first_fixture_engine(tmp_path)
    with pytest.raises(ValueError,match='MISMATCH'):CampaignEngine(engine.root,source_hashes=dict(sources,D1='changed'),plan=engine.plan,mode='SYNTHETIC')
def test_immutable_freeze_tamper_resume_refused(tmp_path):
    engine,sources=first_fixture_engine(tmp_path);sid=engine.next_stage()['id'];engine.begin(sid);engine.finish(sid,dict(Planning_state=planning_state(sources),certificate=CERTIFICATE),validated=True)
    freeze=engine.root/engine.ledger['stages'][sid]['freeze_path'];freeze.write_text('{}',encoding='utf8')
    with pytest.raises(ValueError,match='SHA_MISMATCH'):CampaignEngine(engine.root,source_hashes=sources,plan=engine.plan,mode='SYNTHETIC')
def test_immutable_publication_never_overwrites(tmp_path):
    path=tmp_path/'freeze.json';atomic(path,{'x':1},immutable=True)
    with pytest.raises(FileExistsError):atomic(path,{'x':2},immutable=True)
    assert json.loads(path.read_text())=={'x':1}
def test_stage_order_and_overlap_refused(tmp_path):
    engine,sources=first_fixture_engine(tmp_path)
    with pytest.raises(ValueError):engine.begin(engine.plan['nodes'][1]['id'])
    engine.begin(engine.next_stage()['id'])
    with pytest.raises(RuntimeError):engine.begin(engine.active_stage)
    engine.fail(engine.active_stage,'cleanup')
def test_failed_science_stops_no_retry(tmp_path):
    engine,sources=first_fixture_engine(tmp_path);sid=engine.next_stage()['id'];engine.begin(sid)
    with pytest.raises(ValueError):engine.finish(sid,dict(Planning_state=planning_state(sources),certificate={}),validated=True)
    with pytest.raises(ValueError):engine.next_stage()
@pytest.mark.parametrize('stage,key',[('ACTUAL','Actual_complete'),('FRESH_AC','Fresh_AC_complete')])
def test_incomplete_evaluation_refused(stage,key,tmp_path):
    engine,sources=first_fixture_engine(tmp_path);node=next(n for n in engine.plan['nodes'] if n['stage']==stage)
    with pytest.raises(ValueError,match='INCOMPLETE'):engine.validate_data(node,{key:False})
def test_actual_payload_handoff_refused():
    node=dict(stage='A1',loop=2,Planning_dependencies=['previous'],free_decisions=['AIDC'])
    payload=dict(producer_phase='ACTUAL',validated=True,complete=True,data=dict(state=planning_state({'D1':'s'})))
    with pytest.raises(PermissionError):handoff(node,{'previous':payload})
def test_metrics_nested_movement_and_population():
    a=planning_state({'D1':'s'});b=copy.deepcopy(a);a['mess']['movement']={'e':[0,1]};b['mess']['movement']={'e':[1,1]};b['mess']['p']['t0']=2
    result=metrics(a,b);assert result['differences']['movement_count_difference']==1 and result['differences']['MESS_P_L1']==2
    b['population_sha256']='different'
    with pytest.raises(ValueError):metrics(a,b)
def test_preopened_actual_stream_refused(tmp_path):
    entries,_=source_fixture(tmp_path/'D1');path=tmp_path/'ACTUAL_prior.json';atomic(path,{'load':999})
    with path.open() as handle:
        with pytest.raises(PermissionError,match='PREOPENED'):
            with PlanningReads(entries,issue_time=ISSUE):handle.read()
def test_low_level_preopened_fd_refused(tmp_path):
    entries,_=source_fixture(tmp_path/'D1');path=tmp_path/'ACTUAL_prior.json';atomic(path,{'load':999});fd=os.open(path,os.O_RDONLY)
    try:
        with pytest.raises(PermissionError):
            with PlanningReads(entries,issue_time=ISSUE):os.read(fd,10)
    finally:os.close(fd)
def test_unregistered_alias_of_actual_refused(tmp_path):
    entries,_=source_fixture(tmp_path/'D1');path=tmp_path/'plain.json';atomic(path,{'load':999})
    with pytest.raises(PermissionError):
        with PlanningReads(entries,issue_time=ISSUE):path.read_text()
def test_runtime_state_schema_rejects_actual_fields():
    from v42_campaign.state import validate_state
    state=planning_state({'D1':'s'});state['Actual_tap']=777
    with pytest.raises(ValueError):validate_state(state)
