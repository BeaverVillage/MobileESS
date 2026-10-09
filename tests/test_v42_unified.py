"""Independent contract, policy and state-transition regression tests (optimize=0)."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from v42_native.contracts import digest
from v42_unified.audit import ROOT, REPORTS
from v42_unified.interface import validate_handoff, m1_payload
from v42_unified.verify_interface import verify
from v42_unified.policy import Policy, NativeBudget
from v42_unified.pipeline import configuration, require_stage, run_pipeline
from v42_unified.storage import FrozenStore, sha, setup


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


@pytest.fixture
def original_edge():
    folder = ROOT/'docs/v42_may12_p1_exact_rescue_20261008'
    h = read(REPORTS/'A1_P1_ONLY_TO_M1_HANDOFF.json')
    certificates = {k:read(folder/n) for k,n in dict(zero='PHASE1_ZERO_CERTIFICATE.json',
        closure='COMPLETE_PRICING_CLOSURE.json', bound='P1_FULL_DOMAIN_BOUND_CERTIFICATE.json',
        integer='P1_INTEGER_RESULT.json', physical='ORIGINAL_PHYSICAL_REPLAY.json').items()}
    return h, read(folder/'P1_ONLY_FREEZE.json'), read(folder/'ORIGINAL_INPUT_AND_ARRAY_IDENTITY_FINAL.json'), certificates, \
        read(REPORTS/'A1_ORIGINAL_INTEGER_PHYSICAL_REPLAY.json'), sha(folder/'P1_ONLY_FREEZE.json'), tuple(h['anchor']['control_names'])


def test_real_original_p1_edge_independently_verified(original_edge):
    r=verify(*original_edge)
    assert r['PASS'] and r['original_jobs']==1782 and r['native_optimize_calls']==0 and not r['P2_certified']


@pytest.mark.parametrize('mutation', ['P2','A1','job','control','input','grid','axis','source','bound','decision','scope','day'])
def test_rehashed_scientific_interface_mutations_are_rejected(original_edge, mutation):
    args=deepcopy(original_edge);h=args[0];a=h['anchor']
    if mutation=='P2':a['P2_certificate']={'PASS':True}
    elif mutation=='A1':a['A1_ACCEPTED']=True
    elif mutation=='job':next(iter(a['selected_jobs'].values()))['start']+=1
    elif mutation=='control':a['controls'][0][0]+=1
    elif mutation=='input':a['input_authority_hashes']['initial/input']='f'*64
    elif mutation=='grid':a['grid_array_identities'][0]['sha256']='f'*64
    elif mutation=='axis':a['control_names'][0]='aidc_load_kw[DRIFT]'
    elif mutation=='source':a['source_freeze_sha256']='f'*64
    elif mutation=='bound':a['exact_P1']['exact_LB']='0'
    elif mutation=='decision':a['M1_AIDC_decision_variables']=1
    elif mutation=='scope':h['downstream_accepted']=True
    elif mutation=='day':a['day']='2025-05-01'
    h['anchor_sha256']=digest(a) # A self hash alone is never scientific authority.
    with pytest.raises(ValueError):verify(*args)


def test_old_p2_required_interface_does_not_accept_new_contract(original_edge):
    from v42_bootstrap.handoff import validate_handoff as old
    with pytest.raises(ValueError):old(original_edge[0], original_edge[0]['anchor'])
    assert validate_handoff(original_edge[0])


def test_frozen_input_mismatch_cannot_reuse_old_m1(original_edge):
    h=original_edge[0];a=h['anchor']
    expected={k:deepcopy(a[k]) for k in ('input_authority_hashes','grid_array_identities','day')}
    expected['day']='2025-05-01'
    with pytest.raises(ValueError,match='IDENTITY_MISMATCH'):validate_handoff(h,expected_identity=expected)


def test_pq_soc_route_contract_retained(original_edge):
    p=m1_payload(original_edge[0],{k:'a'*64 for k in ('route_table_sha256','battery_sha256','initial_sites_sha256','traffic_forecast_sha256')})
    assert {'Pch','Pdis','Q','SOC','route','charge_mode'}<=set(p['decision_variables'])
    assert {'travel_energy','connection_delay','terminal_SOC','PCS16','energy_balance'}<=set(p['constraints'])
    assert not p['M1_ACCEPTED'] and p['P2_certificate_from_A1'] is None


@pytest.mark.parametrize('stage',('A1','M1','A2','M2'))
def test_cumulative_native_budget_includes_all_calls_no_wall_reset(stage):
    now=[0.];b=NativeBudget(stage,clock=lambda:now[0]);calls=[]
    m=SimpleNamespace(Params=SimpleNamespace(MemLimit=float('inf'),SoftMemLimit=float('inf')),Runtime=0.,Work=0.,Status=2)
    def optimize():
        calls.append(m.Params.TimeLimit);m.Runtime=2700.;m.Work=1.;now[0]+=3000.
    m.optimize=optimize
    b.optimize(m);now[0]+=400. # Construction/validation wall never replenishes Native.
    assert b.remaining==2700.
    b.optimize(m)
    assert calls==[5400.,2700.] and b.remaining==0.
    assert not b.receipt()['practical_wall_PASS']
    with pytest.raises(TimeoutError):b.optimize(m)
    assert m.Params.Threads==1 and m.Params.MIPGap==.005


def test_memory_limit_rejected_and_integration_optimize_forbidden():
    m=SimpleNamespace(Params=SimpleNamespace(MemLimit=2.,SoftMemLimit=float('inf')))
    with pytest.raises(ValueError,match='MEMORY'):NativeBudget('M1').optimize(m)
    with pytest.raises(PermissionError):NativeBudget('M1',native_allowed=False).optimize(m)


@pytest.mark.parametrize('kwargs', [dict(native_seconds=3600),dict(threads=4),dict(global_gap=.1),dict(mess_feasibility=1e-6)])
def test_policy_drift_rejected(kwargs):
    with pytest.raises(ValueError):Policy(**kwargs)


def test_frozen_store_verifies_before_copy(tmp_path):
    p=tmp_path/'frozen.json';p.write_text('{}',encoding='utf8');r=dict(path=str(p),sha256=sha(p),bytes=2)
    store=FrozenStore();q=store.copy(r)
    assert q.drive.upper()=='D:' and sha(q)==r['sha256']
    p.write_text('{ }',encoding='utf8')
    with pytest.raises(ValueError):FrozenStore().copy(r)


def test_failed_native_call_charged_once():
    b=NativeBudget('A1');m=SimpleNamespace(Params=SimpleNamespace(MemLimit=float('inf'),SoftMemLimit=float('inf')),Runtime=17.,Work=3.,Status=9)
    def failed():raise RuntimeError('native failure')
    m.optimize=failed
    with pytest.raises(RuntimeError):b.optimize(m)
    assert b.remaining==5383. and b.receipt()['native_calls']==1


def test_default_config_is_d_only_and_no_new_native():
    c=configuration();assert c['workspace'].lower()=='d:\\mobileess_v42' and not c['integration_native_optimize_allowed']
    assert setup().drive.upper()=='D:'


class ContractBackend:
    """Only an orchestration test double; no actual scientific/AC result."""
    def __init__(self, pending=None):self.order=[];self.requests={};self.pending=pending
    def execute(self,stage,request,budget):
        self.order.append(stage);self.requests[stage]=deepcopy(request)
        if stage==self.pending:return dict(status='PENDING',reason='No independently accepted result')
        decisions={stage:1}
        return dict(stage=stage,input_identity=request['input_identity'],decisions=decisions,
                    decision_sha256=digest(decisions),acceptance_scope='P1_AND_P2',contract_test_only=True)
    def verify(self,stage,result,request):
        return dict(PASS=True,original_integer_physical_PASS=True,input_identity=request['input_identity'],
            upstream_sha256=request['upstream_sha256'],decision_sha256=result['decision_sha256'],
            original_P2_certificate_PASS=True,global_domain_certificate_PASS=True,exact_LB='1',exact_UB='1',
            AIDC_anchor_unchanged=True,AIDC_decision_variables=0,MESS_anchor_unchanged=True,fixed_A2_no_regret_PASS=True)
    def combine(self,a,m,authority):
        self.order.append('PLANNING_FREEZE')
        return dict(aidc_schedule=a['decisions'],known_job_actions={},
            unknown_arrival_policy=dict(interface='v42_native.actual.unknown_arrival',authority_sha='a'*64),
            mess_route=m['decisions'],movement={},charge_mode={},P={},Q={},SOC={},aidc_electrical_footprint={},
            grid_anchor={'grid_sha':'b'*64},input_authority_hashes=authority['input_authority_hashes'])
    def actual(self,frozen,output):
        self.order.append('ACTUAL');return dict(global_MILP_calls=0,local_PQ_repair=0,plan_sha256=frozen.plan_sha,contract_test_only=True)
    def fresh_ac_receipt(self,frozen,actual,output):
        self.order.append('FRESH_AC');return dict(engine='OpenDSS',fresh_run=True,synthetic=False,
            schedule_sha=frozen.plan_sha,grid_sha=frozen.grid_sha,converged=True,voltage_violations=0,
            line_current_violations=0,transformer_current_violations=0,transformer_kVA_violations=0,contract_test_only=True)
    def validate_actual(self,frozen,actual,fresh):
        self.order.append('VALIDATION');return dict(PASS=True,frozen_input_identity_PASS=True,contract_test_only=True)


def test_single_pipeline_stage_order_warm_start_and_no_false_pending_completion(tmp_path):
    authority=dict(day='2000-01-01',input_authority_hashes={'fixture':'a'*64},grid_array_identities=[{'fixture':True}])
    b=ContractBackend();r=run_pipeline(b,authority,tmp_path/'all')
    assert b.order==['A1','M1','A2','M2','PLANNING_FREEZE','ACTUAL','FRESH_AC','VALIDATION']
    assert r['completed_pipeline'] and r['validation']['contract_test_only']
    assert b.requests['A2']['warm_start']['stage']=='A1' and b.requests['M2']['warm_start']['stage']=='M1'
    assert b.requests['M2']['upstream']['AIDC']['stage']=='A2'
    b=ContractBackend('M1');r=run_pipeline(b,authority,tmp_path/'pending')
    assert b.order==['A1','M1'] and not r['completed_pipeline'] and r['M1_ACCEPTED'] is False


@pytest.mark.parametrize('key,value', [('exact_LB','0'),('AIDC_anchor_unchanged',False),('original_P2_certificate_PASS',False),('decision_sha256','f'*64)])
def test_m1_cannot_advance_on_uncertified_gap_or_changed_physics(key,value):
    b=ContractBackend();request=dict(input_identity='a'*64,upstream_sha256='b'*64)
    result=b.execute('M1',request,None);independent=b.verify('M1',result,request);independent[key]=value
    with pytest.raises(ValueError):require_stage('M1',result,request,independent,Policy())


def test_operational_scope_cannot_authorize_optimize_or_incomplete_pipeline():
    from v42_unified.execution import operational_scope, authorize_if_active, guard_operational_optimize
    authority=dict(day='2025-05-12',input_authority_hashes={'input':'a'*64},grid_array_identities=[{'a':1}])
    with pytest.raises(PermissionError):
        with operational_scope(authority,{}):pass
    b=ContractBackend();request=dict(input_identity=digest(authority),upstream_sha256='b'*64)
    receipts={}
    for stage in ('A1','M1','A2','M2'):
        result=b.execute(stage,request,None);receipts[stage]=dict(result=result,independent=b.verify(stage,result,request))
    with operational_scope(authority,receipts):
        assert authorize_if_active('2025-05-12','PLANNING_FREEZE')=='2025-05-12'
        with pytest.raises(PermissionError):authorize_if_active('2025-05-12','OPTIMIZE')
        with pytest.raises(PermissionError):guard_operational_optimize()
        with pytest.raises(PermissionError):authorize_if_active('2025-05-01','FRESH_AC')
    assert authorize_if_active('2025-05-12','PLANNING_FREEZE') is None


def test_unfinished_m_handoff_rejected_on_d(tmp_path):
    from v42_unified.handoff import inspect_completed_result
    p=tmp_path/'handoff.json';p.write_text(json.dumps(dict(schema='V42_COMPLETED_M_HANDOFF_V1',state='RUNNING')),encoding='utf8')
    with pytest.raises(ValueError,match='COMPLETED_M_RESULT_REQUIRED'):inspect_completed_result(p)


def test_completed_m_handoff_requires_all_pinned_scientific_identities(tmp_path):
    from v42_unified.handoff import inspect_completed_result
    from v42_unified.audit import M_HEAD
    doc=dict(schema='V42_COMPLETED_M_HANDOFF_V1',state='COMPLETE',
             baseline_completed_head=M_HEAD,completed_head=M_HEAD,
             preserved_scientific_hashes={'arbitrary_evidence.json':'a'*64})
    p=tmp_path/'incomplete_scientific_identity.json'
    p.write_text(json.dumps(doc),encoding='utf8')
    with pytest.raises(ValueError,match='IDENTITIES_MISSING'):inspect_completed_result(p)
