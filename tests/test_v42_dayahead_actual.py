"""Architecture contracts only: fake adapters never represent a production run."""
import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import pytest
from v42_native import coordinator
from v42_native.actual import run_dday_actual, require_dday_kernel
from v42_native.contracts import digest
from v42_native.planning import FrozenDayAheadPlan, freeze_day_ahead_plan, PLAN_FIELDS
from v42_native.voltage import Stage, voltage_for

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/v42_day_ahead_planning_direct_dday_actual'


def plan():
    return dict(stage='M2',accepted_native_plan=True,aidc_schedule={'known':[0,1]},
        known_job_actions={'job':{'site':'A','start':0}},
        unknown_arrival_policy=dict(interface='v42_native.actual.unknown_arrival',authority_sha='b'*64),
        mess_route=['A','B'],movement=[0,1],charge_mode=[1,0],P=[1.,-1.],Q=[.2,-.2],SOC=[5.,6.],
        aidc_electrical_footprint=[2.,3.],grid_anchor=dict(grid_sha='a'*64),
        input_authority_hashes={k:'c'*64 for k in ('workload','placement','runtime','MESS_PQ','forecast')})


def realized():
    return dict(load=[10.,11.],pv=[1.,2.],aidc_state={'running':['known']})


class Actual:
    def __init__(self):
        self.calls=0
        self.reconstruct_calls=0

    def reconstruct_physical(self,schedule,inputs):
        self.reconstruct_calls+=1
        self.received_sha=digest(schedule)
        return dict(schedule=deepcopy(schedule),load=inputs['load'],pv=inputs['pv'],aidc_state=inputs['aidc_state'],
                    execution_controls=dict(local_p_repair=False,local_q_repair=False,
                                            full_reoptimization=False,global_MILP_calls=0))

    def fresh_ac(self,physical):
        self.calls+=1
        self.physical=deepcopy(physical)
        return dict(engine='OpenDSS',fresh_run=True,synthetic=False,
            schedule_sha=physical['schedule_sha'],grid_sha=physical['grid_sha'],
            policy_sha=physical['policy_sha'],physical_arrays_sha=digest(physical),
            realized_inputs_sha=physical['realized_inputs_sha'],execution_layer='DDAY_ACTUAL',
            voltage_lower_pu=.95,voltage_upper_pu=1.05,converged=True,
            voltage_violations=0,line_current_violations=0,transformer_current_violations=0,
            transformer_kVA_violations=0)

    def optimize(self,*args):raise AssertionError('GLOBAL_OPTIMIZER_FORBIDDEN')
    stage_payload=worker=validator=combine=objective=optimize
    def repair_p(self,*args):raise AssertionError('P_REPAIR_FORBIDDEN')
    def repair_q(self,*args):raise AssertionError('Q_REPAIR_FORBIDDEN')


def freeze(tmp_path,value=None):
    return freeze_day_ahead_plan(plan() if value is None else value,tmp_path/'planning',grid_sha='a'*64)


def test_planning_four_stages_return_freeze_without_ac_or_final_kernel(monkeypatch,tmp_path):
    calls=[]
    class Planning:
        worker=validator='test-only';grid_sha='a'*64
        def preflight(self):return dict.fromkeys(coordinator.NATIVE_REQUIRED,True)
        def stage_payload(self,stage,a,m):return {}
        def objective(self,a,m):return (1,)
        def combine(self,a,m):return plan()
        def fresh_ac(self,*args):raise AssertionError('PLANNING_FRESH_AC_REGRESSION')
        def generate_kernel(self,*args):raise AssertionError('PLANNING_KERNEL_REGRESSION')
    def supervised(stage,*args):
        calls.append(stage)
        return {'stage':stage},{'test_only':True}
    monkeypatch.setattr(coordinator,'supervise',supervised)
    result=coordinator.run(Planning(),tmp_path)
    assert calls==['A1','M1','A2','M2']
    assert result['status']=='DAYAHEAD_PLANNING_FROZEN' and 'fresh_ac' not in result
    frozen=FrozenDayAheadPlan.load(tmp_path/'DAYAHEAD_PLANNING_FREEZE.json')
    assert frozen.plan_sha==result['DAYAHEAD_PLAN_SHA']==digest(plan())
    assert (tmp_path/'POLICY_SHA').read_text().strip()==frozen.policy_sha
    assert (tmp_path/'GRID_SHA').read_text().strip()==frozen.grid_sha
    assert not (tmp_path/'FINAL_RESPONSE_KERNEL_AUTHORITY.json').exists()
    assert 'final_kernel_anchor' not in coordinator.NATIVE_REQUIRED


def test_freeze_digest_and_nested_state_immutable_and_write_once(tmp_path):
    original=plan();frozen=freeze(tmp_path,original);sha=frozen.plan_sha
    original['P'][0]=99
    copy=frozen.plan;copy['mess_route'].append('C')
    with pytest.raises(FrozenInstanceError):frozen.canonical_json='{}'
    assert frozen.plan_sha==sha and frozen.plan==plan()
    with pytest.raises(FileExistsError):freeze(tmp_path)


@pytest.mark.parametrize('field',PLAN_FIELDS)
def test_freeze_requires_complete_physical_and_authority_fields(tmp_path,field):
    p=plan();del p[field]
    with pytest.raises(ValueError,match='FREEZE_FIELDS'):freeze(tmp_path,p)
    assert not (tmp_path/'planning/DAYAHEAD_PLANNING_FREEZE.json').exists()


@pytest.mark.parametrize('field',['DAYAHEAD_PLAN_SHA','POLICY_SHA','GRID_SHA'])
def test_reload_rejects_tampered_digests(tmp_path,field):
    frozen=freeze(tmp_path);doc=frozen.document;doc[field]='d'*64
    with pytest.raises(ValueError,match='SHA_MISMATCH'):FrozenDayAheadPlan(json.dumps(doc))


def test_reload_rejects_tampered_schedule(tmp_path):
    doc=freeze(tmp_path).document;doc['plan']['P'][0]+=1
    with pytest.raises(ValueError,match='PLAN_SHA_MISMATCH'):FrozenDayAheadPlan(json.dumps(doc))


@pytest.mark.parametrize('bad',[None,True,'schedule'])
def test_freeze_rejects_invalid_schedule_shape(tmp_path,bad):
    p=plan();p['P']=bad
    with pytest.raises(ValueError):freeze(tmp_path,p)


@pytest.mark.parametrize('bad',['new_ml.authority',None])
def test_freeze_cannot_introduce_an_unknown_policy_interface(tmp_path,bad):
    p=plan();p['unknown_arrival_policy']['interface']=bad
    with pytest.raises(ValueError,match='EXISTING_CAUSAL_POLICY'):freeze(tmp_path,p)


def test_schema_and_runtime_freeze_agree(tmp_path):
    import re
    schema=json.loads((EVIDENCE/'DAYAHEAD_FREEZE_SCHEMA.json').read_text(encoding='utf8'))
    doc=freeze(tmp_path).document
    assert set(schema['required'])==set(doc)
    assert set(schema['properties']['plan']['required'])==set(PLAN_FIELDS)
    assert schema['properties']['schema_version']['const']==doc['schema_version']
    for name in ('DAYAHEAD_PLAN_SHA','POLICY_SHA','GRID_SHA'):
        assert re.fullmatch(schema['$defs']['sha']['pattern'],doc[name])
    for name in PLAN_FIELDS:
        assert name in schema['properties']['plan']['properties']


def test_source_supersession_allowlist_cannot_authorize_drift():
    from v42_voltage.preservation import assert_authorized,assert_snapshot
    with pytest.raises(AssertionError,match='UNSEALED_CURRENT_CHANGE'):
        assert_authorized('v42_native/coordinator.py','0'*64)
    with pytest.raises(AssertionError,match='BASELINE_HASH_MISMATCH'):
        import hashlib
        assert_authorized('v42_native/coordinator.py',
            hashlib.sha256((ROOT/'v42_native/coordinator.py').read_bytes()).hexdigest(),'0'*64)
    with pytest.raises(AssertionError,match='HISTORICAL_RECEIPT_DRIFT'):
        assert_snapshot([dict(path='v42_native/coordinator.py',sha256='0'*64)])


def test_actual_same_sha_realized_inputs_single_ac_no_optimizer_no_repairs(tmp_path):
    frozen=freeze(tmp_path);backend=Actual();inputs=realized()
    result=run_dday_actual(frozen,inputs,backend,tmp_path/'actual')
    assert result['PASS'] and result['status']=='PASS'
    assert backend.calls==backend.reconstruct_calls==1
    assert backend.received_sha==result['DAYAHEAD_PLAN_SHA']==frozen.plan_sha
    assert result['fresh_ac']['schedule_sha']==frozen.plan_sha
    assert backend.physical['load']==inputs['load']
    assert backend.physical['pv']==inputs['pv']
    assert backend.physical['aidc_state']==inputs['aidc_state']
    assert result['global_MILP_calls']==0 and not result['final_kernel_created']
    assert frozen.plan==plan() and inputs==realized()
    with pytest.raises(FileExistsError):run_dday_actual(frozen,inputs,backend,tmp_path/'actual')
    assert backend.calls==1


@pytest.mark.parametrize('field',['mess_route','movement','P','Q','known_job_actions','aidc_schedule',
                                  'charge_mode','SOC','unknown_arrival_policy','grid_anchor','input_authority_hashes'])
@pytest.mark.parametrize('target',['argument','returned_schedule'])
def test_actual_cannot_change_frozen_decisions(tmp_path,field,target):
    class Mutating(Actual):
        def reconstruct_physical(self,schedule,inputs):
            physical=super().reconstruct_physical(schedule,inputs)
            (schedule if target=='argument' else physical['schedule'])[field]=['changed']
            return physical
    frozen=freeze(tmp_path);backend=Mutating()
    with pytest.raises(ValueError,match='FROZEN_PLAN_CHANGED'):
        run_dday_actual(frozen,realized(),backend,tmp_path/'actual')
    assert backend.calls==0 and frozen.plan==plan()


@pytest.mark.parametrize('flag',['local_p_repair','local_q_repair','full_reoptimization'])
def test_actual_repair_and_reoptimization_requests_rejected_before_backend(tmp_path,flag):
    backend=Actual()
    with pytest.raises(ValueError,match='FORBIDDEN'):
        run_dday_actual(freeze(tmp_path),realized(),backend,tmp_path/'actual',**{flag:True})
    assert backend.calls==backend.reconstruct_calls==0


@pytest.mark.parametrize('flag',['local_p_repair','local_q_repair','full_reoptimization','global_MILP_calls'])
def test_actual_rejects_backend_correction_or_optimizer_controls(tmp_path,flag):
    class Mutating(Actual):
        def reconstruct_physical(self,schedule,inputs):
            physical=super().reconstruct_physical(schedule,inputs)
            physical['execution_controls'][flag]=1
            return physical
    backend=Mutating()
    with pytest.raises(ValueError,match='EXECUTION_CONTROLS_FORBIDDEN'):
        run_dday_actual(freeze(tmp_path),realized(),backend,tmp_path/'actual')
    assert backend.calls==0


@pytest.mark.parametrize('field',['P','Q','mess_route'])
def test_actual_rejects_physical_control_shadowing(tmp_path,field):
    class Shadowing(Actual):
        def reconstruct_physical(self,schedule,inputs):
            physical=super().reconstruct_physical(schedule,inputs);physical[field]=['override'];return physical
    backend=Shadowing()
    with pytest.raises(ValueError,match='PHYSICAL_RECONSTRUCTION_REQUIRED'):
        run_dday_actual(freeze(tmp_path),realized(),backend,tmp_path/'actual')
    assert backend.calls==0


@pytest.mark.parametrize('field,bad',[
    ('voltage_violations',1),('line_current_violations',1),('transformer_current_violations',1),
    ('transformer_kVA_violations',1),('converged',False),('synthetic',True),('fresh_run',False),
    ('PASS',False),('engine','stub'),('schedule_sha','e'*64),('grid_sha','e'*64),
    ('policy_sha','e'*64),('physical_arrays_sha','e'*64),('realized_inputs_sha','e'*64),
    ('execution_layer','DAYAHEAD'),('voltage_lower_pu',.955),('voltage_upper_pu',1.045)])
def test_fresh_ac_failures_record_fail_no_rescue_no_kernel(tmp_path,field,bad):
    class Failing(Actual):
        def fresh_ac(self,physical):
            r=super().fresh_ac(physical);r[field]=bad;return r
    backend=Failing();frozen=freeze(tmp_path)
    result=run_dday_actual(frozen,realized(),backend,tmp_path/'actual')
    assert not result['PASS'] and result['status']=='FAIL' and backend.calls==1
    assert result['fresh_ac'][field]==bad and frozen.plan==plan()
    assert json.loads((tmp_path/'actual/DDAY_ACTUAL_RESULT.json').read_text())['status']=='FAIL'
    with pytest.raises(ValueError):require_dday_kernel(frozen,result,{})


def test_ac_exception_recorded_without_retry(tmp_path):
    class Failing(Actual):
        def fresh_ac(self,physical):
            self.calls+=1;raise RuntimeError('OpenDSS unavailable')
    backend=Failing()
    r=run_dday_actual(freeze(tmp_path),realized(),backend,tmp_path/'actual')
    assert r['status']=='FAIL' and 'OpenDSS unavailable' in r['failure'] and backend.calls==1


def test_ac_cannot_mutate_physical_arrays(tmp_path):
    class Mutating(Actual):
        def fresh_ac(self,physical):
            r=super().fresh_ac(physical);physical['schedule']['P'][0]+=1;return r
    backend=Mutating();frozen=freeze(tmp_path)
    r=run_dday_actual(frozen,realized(),backend,tmp_path/'actual')
    assert r['status']=='FAIL' and 'PHYSICAL_ARRAYS_CHANGED' in r['failure']
    assert backend.calls==1 and frozen.plan==plan()


def test_final_kernel_gate_uses_actual_not_planning_and_exact_upstream(tmp_path):
    frozen=freeze(tmp_path);upstream={k:'c'*64 for k in ('workload','placement','runtime','MESS_PQ')}
    upstream['grid_anchor']=frozen.grid_sha
    with pytest.raises(ValueError):require_dday_kernel(frozen,{'status':'DAYAHEAD_PLANNING_FROZEN'},upstream)
    result=run_dday_actual(frozen,realized(),Actual(),tmp_path/'actual')
    assert require_dday_kernel(frozen,result,upstream)
    with pytest.raises(ValueError):require_dday_kernel(frozen,result,dict(upstream,runtime='d'*64))
    changed=deepcopy(result);changed['fresh_ac']['execution_layer']='DAYAHEAD'
    with pytest.raises(ValueError):require_dday_kernel(frozen,changed,upstream)
    for key in ('physical_arrays_sha','realized_inputs_sha'):
        changed=deepcopy(result);del changed[key];del changed['fresh_ac'][key]
        with pytest.raises(ValueError,match='SHA256_REQUIRED'):require_dday_kernel(frozen,changed,upstream)


@pytest.mark.parametrize('accepted',[False,None])
def test_kernel_does_not_mint_native_acceptance(tmp_path,accepted):
    p=plan();p['accepted_native_plan']=accepted;frozen=freeze(tmp_path,p)
    result=run_dday_actual(frozen,realized(),Actual(),tmp_path/'actual')
    upstream={k:'c'*64 for k in ('workload','placement','runtime','MESS_PQ')};upstream['grid_anchor']='a'*64
    with pytest.raises(ValueError,match='FINAL_NATIVE_M2'):require_dday_kernel(frozen,result,upstream)


def test_voltage_authorities_preserved():
    assert (voltage_for(Stage.A1).lower_pu,voltage_for(Stage.A1).upper_pu)==(.95,1.05)
    for s in (Stage.M1,Stage.A2,Stage.M2):
        assert (voltage_for(s).lower_pu,voltage_for(s).upper_pu)==(.955,1.045)
    assert (voltage_for(Stage.ACTUAL).lower_pu,voltage_for(Stage.ACTUAL).upper_pu)==(.95,1.05)


def test_repository_v42_ac_call_only_in_actual_and_no_global_optimizer():
    calls=[]
    for folder in ROOT.glob('v42*'):
        if not folder.is_dir():continue
        for source in folder.rglob('*.py'):
            tree=ast.parse(source.read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='fresh_ac':
                    calls.append(source.relative_to(ROOT).as_posix())
    assert calls==['v42_native/actual.py']
    for file in ('planning.py','coordinator.py'):
        text=(ROOT/'v42_native'/file).read_text()
        assert 'fresh_ac' not in text and 'require_fresh_ac' not in text
    tree=ast.parse((ROOT/'v42_native/actual.py').read_text())
    forbidden={'optimize','solve','stage_payload','combine','worker','repair_p','repair_q'}
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
            assert node.func.attr not in forbidden


def test_v41_historical_preservation_evidence_and_no_production_claim():
    audit=json.loads((EVIDENCE/'V41_PRESERVATION_AUDIT.json').read_text(encoding='utf8'))
    assert audit['PASS'] and audit['baseline_sha']=='e2d4779685fff6d0cf022c649733b2ca41fdfc08'
    assert audit['changed_historical_paths']==[] and audit['external_sources']
    for source in audit['external_sources']:
        path=Path(source['path'])
        if path.is_file():
            import hashlib
            assert hashlib.sha256(path.read_bytes()).hexdigest()==source['observed_sha256']
    flags=json.loads((EVIDENCE/'FINAL_FLAGS.json').read_text())
    assert flags['M1_ACCEPTED'] is flags['PROBLEM13_FINAL_VALIDATED'] is False
    assert flags['ACTUAL_PRODUCTION_RUN'] is flags['FRESH_OPENDSS_RUN'] is False
