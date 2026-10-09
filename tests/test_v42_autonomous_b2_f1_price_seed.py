"""Native/model-denied production adapter tests; genuine signed checker."""
import copy
import importlib.util
import json
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_autonomous_b2 import f1_price_seed as p
from v42_autonomous_b2 import f1_state
from v42_m1_anytime import algorithms,core
from v42_m1_hybrid import blocks,pricing
from v42_m1_hybrid import bound,verify
from v42_may_campaign_native90.a_routing import rebound
from time import perf_counter
ORIGINAL_LP_ROUND=algorithms.lp_round

REPO=Path(r'D:\MobileESS_v42_autonomous')
spec=importlib.util.spec_from_file_location('original_f1_test_helpers',REPO/'tests/test_v42_autonomous_b2_f1_state.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
env=legacy.env
deny_real_gurobi_models=legacy.deny_real_gurobi_models
REAL_PRODUCTION_AUTHORITY=p._production_authority

@pytest.fixture(autouse=True)
def synthetic_source_authority_only(monkeypatch):
    # These tiny mathematical/state fixtures have an isolated original.py
    # authority, not a 1,106-file production checkout. Only tests substitute
    # the Source admission dependency; no production Boolean opt-out exists.
    stub=lambda request,code_root,adapter:dict(test_fixture_only=True,adapter_source=adapter)
    monkeypatch.setattr(p,'_production_authority',stub)
    # Explicit test-only replacement of both function and its owned binding;
    # the unmodified production function/table are exercised separately.
    bindings=dict(p._OWN_BINDINGS);bindings[('function','_production_authority')]=(stub,stub.__code__)
    monkeypatch.setattr(p,'_OWN_BINDINGS',p.MappingProxyType(bindings))
    monkeypatch.setattr(p,'_BUDGET_CLASS',legacy.Budget)


@pytest.fixture
def ready(env,monkeypatch,request):
    legacy.capture(env,model=legacy.Model(env.case,pi=getattr(request,'param',(10.,))))
    selected,cert=legacy.select(env,dual={'0':'10'})
    assert selected=={} and cert['exact_bound']=='0'
    calls=[]
    def decomposition(case,decomp):
        assert decomp.case_sha==case.case_sha
        return dict(PASS=True,case_sha=case.case_sha)
    def delegate(case,decomp,dual,budget,frontier,path,method,kind='LP_ONLY',*,context=None):
        calls.append(dict(dual=copy.deepcopy(dual),method=method,kind=kind,context=context,
                          budget=budget,frontier=frontier,path=Path(path)))
        return ('ORIGINAL_ROW',None,'ORIGINAL_RESULT')
    monkeypatch.setattr(blocks,'verify_decomposition',decomposition)
    monkeypatch.setattr(algorithms,'lp_round',delegate)
    monkeypatch.setattr(p,'_LP',delegate);monkeypatch.setattr(p,'_DECOMP',decomposition)
    monkeypatch.setattr(p,'_ORIGINALS',tuple((mod,n,delegate if n=='lp_round' else decomposition if n=='verify_decomposition' else fn,
        (delegate if n=='lp_round' else decomposition if n=='verify_decomposition' else fn).__code__)
        for mod,n,fn,code in p._ORIGINALS))
    env.calls=calls;env.original_lp=delegate
    env.decomp=SimpleNamespace(case_sha=env.case.case_sha,coupling_rows=np.array([0]))
    env.frontier=SimpleNamespace(lb=Fraction(0))
    def owned(path):
        path=Path(path).resolve()
        if not path.is_relative_to(env.output.resolve()):raise PermissionError('OWNED_PATH')
        return path
    env.runner=p.scoped_lp_round(delegate,env.request,env.code,lambda:env.scope,owned,legacy.write)
    return env

def call(e,*,dual=None,method='L1',kind='LP_ONLY',path=None,context=None):
    return e.runner(e.case,e.decomp,{} if dual is None else dual,e.budget,e.frontier,
                    path or e.output/'004_L1_00',method,kind,context=context)

def test_negative_valid_nonzero_seed_only_changes_existing_price_input(ready):
    before=copy.deepcopy(ready.budget.calls);result=call(ready,context={'unchanged':'context'})
    assert result==('ORIGINAL_ROW',None,'ORIGINAL_RESULT') and len(ready.calls)==1
    assert ready.calls[0]['dual']=={'0':'10'} and ready.calls[0]['context']=={'unchanged':'context'}
    assert ready.frontier.lb==0 and ready.budget.calls==before
    original=json.loads((ready.output/'INITIAL_EXACT_ORIGINAL_DUAL.json').read_text())
    assert original=={}
    receipt=json.loads((ready.output/'004_L1_00/CURRENT_F1_COMPUTATIONAL_PRICE_SEED.json').read_text())
    assert Fraction(receipt['evidence']['full_domain_certificate']['exact_bound'])==-90
    assert receipt['evidence']['Native_calls_added']==0
    assert receipt['evidence']['selected_certified_dual_replaced'] is False

@pytest.mark.parametrize('method,kind',[('L1','MILP_AND_LP'),('L2','LP_ONLY'),('L3','LP_ONLY'),
                                       ('L4','LP_ONLY'),('OTHER','LP_ONLY')])
def test_unapproved_existing_calls_keep_original_price_identity(ready,method,kind):
    dual={};call(ready,dual=dual,method=method,kind=kind)
    assert ready.calls[0]['dual']=={} and len(ready.calls)==1
    assert not (ready.output/'004_L1_00/CURRENT_F1_COMPUTATIONAL_PRICE_SEED.json').exists()

def test_l4_existing_milp_lp_call_can_use_price_seed(ready):
    call(ready,method='L4',kind='MILP_AND_LP')
    assert len(ready.calls)==1 and ready.calls[0]['kind']=='MILP_AND_LP' and ready.calls[0]['dual']=={'0':'10'}

@pytest.mark.parametrize('dual,lb',[({'0':'1'},Fraction(0)),({},Fraction(1)),({'0':'0'},Fraction(1))])
def test_adopted_stronger_or_nonzero_certified_dual_is_never_overwritten(ready,dual,lb):
    ready.frontier.lb=lb;call(ready,dual=dual)
    assert ready.calls[0]['dual']==dual and ready.frontier.lb==lb

@pytest.mark.parametrize('absence',['scope','state'])
def test_missing_admitted_state_falls_back_without_a_candidate(ready,absence):
    if absence=='scope':
        ready.runner.get_f1_scope=lambda:None
        ready.runner.owner_seals['get_f1_scope']=p._callable_seal(ready.runner.get_f1_scope)
    elif absence=='state':ready.scope.state=None
    call(ready);assert ready.calls[0]['dual']=={}

@pytest.mark.parametrize('ready',[None],indirect=True)
def test_legitimate_finite_f1_pi_absence_uses_existing_original_price(ready):
    call(ready);assert ready.calls[0]['dual']=={}

@pytest.mark.parametrize('drift',[
    lambda e:e.case.d['rhs'].__setitem__(0,3.),
    lambda e:e.case.A.data.__setitem__(0,2.),
    lambda e:e.scope.request.update(day='2025-05-02'),
    lambda e:e.scope.state.binding.update(implementation_SHA='foreign'),
    lambda e:(e.output/'F1_SAME_ATTEMPT_STATE.npz').write_bytes(b'bad'),
    lambda e:e.budget.calls[0].update(Native_Runtime=999.),
    lambda e:e.budget.__setattr__('inflight',{'unmeasured':True}),
    lambda e:(e.code/'original.py').write_bytes(b'foreign science'),
    lambda e:e.decomp.__setattr__('case_sha','foreign'),
])
def test_current_state_source_model_ledger_and_domain_drift_denied_before_delegate(ready,drift):
    drift(ready)
    with pytest.raises((PermissionError,AssertionError)):call(ready)
    assert ready.calls==[]

@pytest.mark.parametrize('key,value',[('case_sha','foreign'),('PASS',False),('selected','CURRENT_ATTEMPT_F1_ORIGINAL_ROW_PI'),
                                      ('maximum_exact_bound','1')])
def test_current_selection_authority_must_remain_zero_and_same_case(ready,key,value):
    path=ready.output/'F1_FULL_DOMAIN_LB_SELECTION.json';obj=json.loads(path.read_text());obj[key]=value;legacy.write(path,obj)
    with pytest.raises(PermissionError,match='CURRENT_ZERO_SELECTION'):call(ready)
    assert ready.calls==[]

@pytest.mark.parametrize('key,value',[('exact_bound','-1'),('dual_SHA256','invented'),('case_sha','foreign'),('PASS',False)])
def test_original_repaired_candidate_must_match_previous_full_domain_checker(ready,key,value):
    path=ready.output/'F1_FULL_DOMAIN_LB_SELECTION.json';obj=json.loads(path.read_text())
    next(c['certificate'] for c in obj['candidates'] if c['kind']=='CURRENT_ATTEMPT_F1_ORIGINAL_ROW_PI')[key]=value
    legacy.write(path,obj)
    with pytest.raises(PermissionError,match='CERTIFICATE_DRIFT'):call(ready)
    assert ready.calls==[]

def test_no_import_of_saved_state_from_another_scope(ready):
    other=f1_state.Scope(ready.request,ready.code,writer=legacy.write);other.state=ready.scope.state
    ready.scope=other
    with pytest.raises(PermissionError,match='SAME_ATTEMPT'):call(ready)
    assert ready.calls==[]

def test_own_price_path_remains_in_current_output(ready):
    with pytest.raises(PermissionError):call(ready,path=ready.root/'foreign/output')
    assert ready.calls==[]

def test_namespace_alias_change_is_denied_before_delegate(ready,monkeypatch):
    monkeypatch.setattr(p.lb,'repair_affine_equality_duals',lambda *a:({},{}))
    with pytest.raises(PermissionError,match='ALIAS_DRIFT'):call(ready)
    assert ready.calls==[]

def test_in_place_original_code_change_is_denied_before_delegate(ready,monkeypatch):
    monkeypatch.setattr(ready.original_lp,'__code__',ready.original_lp.__code__.replace(co_name='mutated_delegate'))
    with pytest.raises(PermissionError,match='ORIGINAL_CODE_DRIFT|SCOPE_DELEGATE_DRIFT'):call(ready)
    assert ready.calls==[]

def test_bound_wrapper_delegate_change_is_denied(ready):
    ready.runner.original=lambda *a,**kw:None
    with pytest.raises(PermissionError,match='SCOPE_DELEGATE_DRIFT'):call(ready)
    assert ready.calls==[]

def test_no_reroute_to_a_different_scope_after_an_actual_call(ready):
    call(ready);ready.scope=f1_state.Scope(ready.request,ready.code,writer=legacy.write)
    with pytest.raises(PermissionError,match='CURRENT_SCOPE_CHANGED'):call(ready)
    assert len(ready.calls)==1

def test_original_failed_delegation_is_not_retried_and_accounting_is_preserved(ready,monkeypatch):
    def failed(case,decomp,dual,budget,frontier,path,method,kind='LP_ONLY',*,context=None):
        budget.inflight={'original_admission':'unfinished'};budget.persist();raise RuntimeError('originalfailure')
    monkeypatch.setattr(algorithms,'lp_round',failed);monkeypatch.setattr(p,'_LP',failed)
    monkeypatch.setattr(p,'_ORIGINALS',tuple((m,n,failed if n=='lp_round' else f,
        failed.__code__ if n=='lp_round' else c) for m,n,f,c in p._ORIGINALS))
    runner=p.scoped_lp_round(failed,ready.request,ready.code,lambda:ready.scope,ready.runner.owned,legacy.write)
    before=copy.deepcopy(ready.budget.calls)
    with pytest.raises(RuntimeError,match='originalfailure'):
        runner(ready.case,ready.decomp,{},ready.budget,ready.frontier,ready.output/'attempt','L1')
    assert ready.budget.calls==before and ready.budget.inflight=={'original_admission':'unfinished'}
    assert json.loads(ready.budget.path.read_text())['inflight']=={'original_admission':'unfinished'}

def test_original_result_and_frontier_publish_semantics_are_forwarded_exactly(ready,monkeypatch):
    # This producer stand-in proves forwarding only; actual original producer
    # and signed checker/full block fixture is a separate test below.
    full={'0':'1/10'};result=({'adopted':True},full,{'original':True})
    def adopted(case,decomp,dual,budget,frontier,path,method,kind='LP_ONLY',*,context=None):
        frontier.lb=Fraction(1,10);return result
    monkeypatch.setattr(algorithms,'lp_round',adopted);monkeypatch.setattr(p,'_LP',adopted)
    monkeypatch.setattr(p,'_ORIGINALS',tuple((m,n,adopted if n=='lp_round' else f,
        adopted.__code__ if n=='lp_round' else c) for m,n,f,c in p._ORIGINALS))
    runner=p.scoped_lp_round(adopted,ready.request,ready.code,lambda:ready.scope,ready.runner.owned,legacy.write)
    got=runner(ready.case,ready.decomp,{},ready.budget,ready.frontier,ready.output/'attempt','L1')
    assert got is result and ready.frontier.lb==Fraction(1,10) and got[1] is full

@pytest.mark.parametrize('bad',[{'00':'1'},{'-1':'1'},{'0':'nan'},{'0':'inf'}])
def test_exact_original_row_normalization_refuses_bad_axis_or_nonfinite(bad):
    with pytest.raises((ValueError,PermissionError)):p._dual(bad)

class FiveColumnModel(legacy.Model):
    """Fake Native backend only, supplying genuine full-axis state attributes."""
    def __init__(self,case):
        super().__init__(case,fixed=False,pi=(10.,0.,0.,0.,0.),basis=False)
        self.attrs['VType']=['C']*5;self.attrs['X']=[1.,1.,1.,1.,4.]
    def getVars(self):return list(range(5))
    def getConstrs(self):return list(range(5))

@pytest.fixture
def original_path(env,monkeypatch):
    # Original finite domain: rho>=sum SOCu, every SOCu>=1, original
    # 0<=SOCu<=1 and0<=rho<=4. Exact optimum4. F1lambda10 by itself has
    # box certificate-36; local-domain priced dual10 certifies4.
    names=np.array([f'SOC[u{i},0]' for i in range(1,5)]+['rho_max'])
    A=sparse.csr_matrix(np.array([[-1.,-1.,-1.,-1.,1.],
          [1.,0.,0.,0.,0.],[0.,1.,0.,0.,0.],[0.,0.,1.,0.,0.],[0.,0.,0.,1.,0.]]))
    d=dict(lower=np.zeros(5),upper=np.array([1.,1.,1.,1.,4.]),objective=np.array([0.,0.,0.,0.,1.]),
        rhs=np.array([0.,1.,1.,1.,1.]),sense=np.array(['>']*5),names=names,
        row_names=np.array(['joint_coupling','local_u1','local_u2','local_u3','local_u4']),types=np.array(['C']*5),constant=np.array(0.))
    env.case=SimpleNamespace(A=A,d=d,case_sha=core.CASE,output=env.output)
    env.scope=f1_state.Scope(env.request,env.code,writer=legacy.write)
    env.scope.capture(legacy.original_f1(env,model=FiveColumnModel(env.case)),env.case,env.budget,
                      pattern=(np.array([],dtype=np.int64),np.array([],dtype=float)))
    dual,cert=legacy.select(env,dual={'0':'10'})
    assert dual=={} and cert['exact_bound']=='0'
    env.decomp=blocks.build_blocks(env.case)
    output=env.output.resolve()
    def owned(path):
        path=Path(path).resolve()
        if not path.is_relative_to(output):raise PermissionError('OWNED_PATH')
        path.mkdir(parents=True,exist_ok=True);return path
    routed_write=rebound(core.write,dict(core.write.__globals__,ROOT=output))
    monkeypatch.setattr(core,'write',routed_write);monkeypatch.setattr(algorithms,'write',routed_write)
    monkeypatch.setattr(pricing,'output_directory',owned)
    env.budget.started=perf_counter();env.budget.wall=lambda:perf_counter()-env.budget.started
    env.budget.snapshot=lambda:dict(Native_Runtime=0.,Native_calls=len(env.budget.calls),Native_Work=0.)
    ub=output/'synthetic_strict_ub.json';legacy.write(ub,dict(PASS=True,case_sha=core.CASE,exact_Global_UB='4'))
    env.frontier=core.Frontier(output/'frontier',env.budget,'0','4',output/'INITIAL_EXACT_LB_CERTIFICATE.json',ub)
    env.synthetic_pricing=[]
    def synthetic_prices(case,decomp,prices,ledger,path,*,lp_seconds):
        # Native-free controlled producer. Both original exact global bound
        # and independent producer checker run unchanged; no claimed solve.
        assert lp_seconds==45 and len(decomp.units)==4
        pricing.persist_prices(case,decomp,prices,path)
        selected={u:({'0':'10'} if env.strong else {}) for u in decomp.units}
        legacy.write(Path(path)/'SELECTED_UNIT_DUALS_EXACT.json',selected)
        producer=bound.certify_global(case,decomp,prices.coupling_dual,selected,prices.seed_nonunit_dual)
        env.synthetic_pricing.append(dict(coupling=dict(prices.coupling_dual),selected=selected,cap=lp_seconds))
        return dict(exact_global_certificate=producer,
            records=[dict(kind='LP',unit=u,native=dict(Native_Runtime=0.,Native_ObjBound=999999.)) for u in decomp.units])
    monkeypatch.setattr(pricing,'run_lp_prices',synthetic_prices)
    monkeypatch.setattr(p,'_PRICE_HELPERS',tuple((m,n,synthetic_prices if n=='run_lp_prices' else f,
        synthetic_prices.__code__ if n=='run_lp_prices' else c) for m,n,f,c in p._PRICE_HELPERS))
    env.runner=p.scoped_lp_round(ORIGINAL_LP_ROUND,env.request,env.code,lambda:env.scope,owned,legacy.write)
    return env

@pytest.mark.parametrize('strong',[False,True])
def test_actual_original_lp_round_pricing_checker_and_frontier_math_path(original_path,strong):
    e=original_path;e.strong=strong;before=copy.deepcopy(e.budget.calls)
    row,adopted,result=e.runner(e.case,e.decomp,{},e.budget,e.frontier,e.output/'original_L1','L1')
    assert len(e.synthetic_pricing)==1 and e.synthetic_pricing[0]['coupling']=={'0':'10'}
    assert e.budget.calls==before and e.synthetic_pricing[0]['cap']==45
    assert row['adopted'] is strong
    if strong:
        assert e.frontier.lb==4 and adopted=={'0':'10','1':'10','2':'10','3':'10','4':'10'}
        final=f1_state._ORIGINAL_FUNCTIONS['CHECKER'](e.case.A,e.case.d,adopted,case_sha=e.case.case_sha)
        assert Fraction(final['exact_bound'])==e.frontier.lb
        assert row['certified_gain']==4.
    else:
        assert e.frontier.lb==0 and adopted is None and row['candidate_LB']==-36.
        final=f1_state._ORIGINAL_FUNCTIONS['CHECKER'](e.case.A,e.case.d,{},case_sha=e.case.case_sha)
        assert Fraction(final['exact_bound'])==e.frontier.lb
    assert json.loads((e.output/'INITIAL_EXACT_ORIGINAL_DUAL.json').read_text())=={}
    assert result['records'][0]['native']['Native_ObjBound']==999999.

def test_full_lp_missing_pi_zero_tie_is_legitimate_price_seed_admission(ready):
    # Recreate an actual original selector result with no fullLP dual; its first
    # zero FULL_LP candidate wins the tie, ahead of ORIGINAL_ZERO_SIGNED_DUAL.
    selected,cert=legacy.select(ready,dual={})
    assert selected=={} and cert['selected_candidate']=='ORIGINAL_FULL_LP'
    call(ready)
    assert ready.calls[0]['dual']=={'0':'10'} and ready.frontier.lb==0

def test_original_uncertifiable_optional_f1_candidate_uses_cold_price(ready):
    path=ready.output/'F1_FULL_DOMAIN_LB_SELECTION.json';o=json.loads(path.read_text())
    o['candidates']=[x for x in o['candidates'] if x['kind']!='CURRENT_ATTEMPT_F1_ORIGINAL_ROW_PI']
    o['f1_status']='F1_CANDIDATE_NOT_CERTIFIABLE:originalfiniteboundproofunavailable'
    legacy.write(path,o);call(ready)
    assert ready.calls[0]['dual']=={} and ready.frontier.lb==0

def test_missing_candidate_under_available_status_is_corruption(ready):
    path=ready.output/'F1_FULL_DOMAIN_LB_SELECTION.json';o=json.loads(path.read_text())
    o['candidates']=[x for x in o['candidates'] if x['kind']!='CURRENT_ATTEMPT_F1_ORIGINAL_ROW_PI']
    legacy.write(path,o)
    with pytest.raises(PermissionError,match='CURRENT_CERTIFIED_F1'):call(ready)
    assert ready.calls==[]

@pytest.mark.parametrize('which,key,value',[('dual','0','1'),('cert','exact_bound','1'),
    ('cert','exact_Global_LB','1'),('cert','case_sha','foreign'),('cert','selected_candidate','foreign'),
    ('cert','dual_SHA256','invented'),('cert','PASS',False)])
def test_exact_zero_driver_dual_and_certificate_must_remain_bound(ready,which,key,value):
    name='INITIAL_EXACT_ORIGINAL_DUAL.json' if which=='dual' else 'INITIAL_EXACT_LB_CERTIFICATE.json'
    path=ready.output/name;o=json.loads(path.read_text());o[key]=value;legacy.write(path,o)
    with pytest.raises(PermissionError,match='CURRENT_ZERO_SELECTION'):call(ready)
    assert ready.calls==[]

def test_negative_frontier_is_not_the_certified_zero_driver_gate(ready):
    ready.frontier.lb=Fraction(-1);call(ready)
    assert ready.calls[0]['dual']=={} and ready.frontier.lb==-1

@pytest.mark.parametrize('name',['verify_state','_authority_check','_ledger','_state_metadata_digest'])
def test_original_state_verifier_rejects_instance_descriptor_shadowing(ready,name):
    setattr(ready.scope,name,lambda *a,**k:ready.scope.state)
    with pytest.raises(PermissionError,match='STATE_DESCRIPTOR_REQUIRED'):call(ready)
    assert ready.calls==[]

def test_original_state_descriptor_rejects_same_code_different_function_globals(ready,monkeypatch):
    from types import FunctionType
    original=f1_state.Scope.verify_state
    replacement=FunctionType(original.__code__,dict(original.__globals__),original.__name__,original.__defaults__,original.__closure__)
    monkeypatch.setattr(f1_state.Scope,'verify_state',replacement)
    with pytest.raises(PermissionError,match='F1_SCOPE_CODE_DRIFT'):call(ready)
    assert ready.calls==[]

def test_bound_ownership_callback_closure_change_is_denied(ready):
    callback=ready.runner.owned
    assert callback.__closure__
    callback.__closure__[0].cell_contents=object()
    with pytest.raises(PermissionError,match='SCOPE_DELEGATE_DRIFT'):call(ready)
    assert ready.calls==[]

def test_authority_now_instance_override_cannot_bypass_source_replay(ready):
    ready.scope._authority_now=lambda:ready.scope._authority
    with pytest.raises(PermissionError,match='LIVE_AUTHORITY_DESCRIPTOR'):call(ready)
    assert ready.calls==[]

def test_writer_mutation_of_price_helper_is_denied_before_original_entry(ready,monkeypatch):
    def writer(path,value):
        legacy.write(path,value)
        pricing.make_prices=lambda *a,**k:None
    ready.runner.writer=writer;ready.runner.owner_seals['writer']=p._callable_seal(writer)
    monkeypatch.setattr(pricing,'make_prices',pricing.make_prices)
    with pytest.raises(PermissionError,match='PRICE_HELPER_DRIFT'):call(ready)
    assert ready.calls==[]

def test_writer_direct_global_namespace_is_sealed(ready):
    scope=ready.runner;namespace={'original_write':legacy.write}
    exec('def writer(path,value): original_write(path,value)',namespace)
    writer=namespace['writer']
    scope.writer=writer;scope.owner_seals['writer']=p._callable_seal(writer)
    scope.namespace.extend(p._function_namespace(writer))
    namespace['original_write']=lambda *a,**k:None
    with pytest.raises(PermissionError,match='DELEGATE_NAMESPACE_DRIFT'):call(ready)
    assert ready.calls==[]

@pytest.mark.parametrize('name',['_production_authority','_read','_dual','_dual_sha','_digest'])
def test_own_helper_alias_replacement_is_denied_before_delegate(ready,monkeypatch,name):
    original=getattr(p,name)
    from types import FunctionType
    fake=FunctionType(original.__code__,dict(original.__globals__),original.__name__,original.__defaults__,original.__closure__)
    monkeypatch.setattr(p,name,fake)
    with pytest.raises(PermissionError,match='OWN_CODE_OR_ALIAS_DRIFT'):call(ready)
    assert ready.calls==[]

@pytest.mark.parametrize('name',['_production_authority','_read','_dual','_dual_sha','_digest'])
def test_own_helper_inplace_code_change_is_denied_before_delegate(ready,monkeypatch,name):
    original=getattr(p,name);monkeypatch.setattr(original,'__code__',original.__code__.replace(co_name='changed_helper'))
    with pytest.raises(PermissionError,match='OWN_CODE_OR_ALIAS_DRIFT'):call(ready)
    assert ready.calls==[]

@pytest.mark.parametrize('name',['_integrity','_state','_seed'])
def test_own_instance_helper_shadow_is_denied_before_delegate(ready,name):
    setattr(ready.runner,name,lambda *a,**kw:None)
    with pytest.raises(PermissionError,match='OWN_INSTANCE_SHADOW'):call(ready)
    assert ready.calls==[]

@pytest.mark.parametrize('name',['_integrity','_state','_seed'])
def test_own_class_descriptor_swap_is_denied_before_delegate(ready,monkeypatch,name):
    original=getattr(p.PriceSeed,name)
    from types import FunctionType
    fake=FunctionType(original.__code__,dict(original.__globals__),original.__name__,original.__defaults__,original.__closure__)
    monkeypatch.setattr(p.PriceSeed,name,fake)
    with pytest.raises(PermissionError,match='OWN_CODE_OR_ALIAS_DRIFT'):call(ready)
    assert ready.calls==[]

def test_own_guard_function_replacement_is_denied_at_entry(ready,monkeypatch):
    monkeypatch.setattr(p,'_guard_own',lambda *a,**kw:None)
    with pytest.raises(PermissionError,match='OWN_ENTRY_GUARD_DRIFT'):call(ready)
    assert ready.calls==[]

@pytest.mark.parametrize('name',['__init__','__call__'])
def test_own_constructor_and_call_code_must_be_original_at_factory(ready,monkeypatch,name):
    original=getattr(p.PriceSeed,name)
    monkeypatch.setattr(original,'__code__',original.__code__.replace(co_name='changed_scope_code'))
    with pytest.raises(PermissionError,match='OWN_CODE_OR_ALIAS_DRIFT'):
        p.scoped_lp_round(ready.original_lp,ready.request,ready.code,lambda:ready.scope,ready.runner.owned,legacy.write)

def current_production_request(tmp_path):
    # Reversible audit-only metadata, using actual frozen original inputs and
    # B1 receipts. No campaign request/output/ledger/queue is changed.
    from v42_autonomous_b2 import worker
    base=Path(r'D:\v42_may_restart_20261010_02')
    manifest=json.loads((base/'B2_V34_ZERO_START_DEPLOYMENT_MANIFEST.json').read_text(encoding='utf-8'))
    request=json.loads((base/'dates/B2/2025-05-01/attempts/repair_b2_v34_01_s1/request.json').read_text(encoding='utf-8'))
    root=tmp_path/'actual99factory';root.mkdir()
    execution=worker.sources();assert len(execution)==99
    manifest.update(execution_sources=execution,execution_SHA=worker.digest(execution))
    manifest['attempt_id']='audit_price35';manifest['attempt_ids']=['audit_price35']
    manifest['prior_attempts']={}
    path=root/'manifest.json';legacy.write(path,manifest)
    out=root/'dates/B2/2025-05-01/attempts/audit_price35/output'
    request.update(root=str(root),attempt_id='audit_price35',manifest=str(path),manifest_SHA=f1_state._record(path)['sha256'],
        implementation_SHA=manifest['execution_SHA'],deployment_SHA=manifest['execution_SHA'],previous_attempts=[],
        result=str(out.parent/'RESULT.json'),output=str(out),progress=str(out.parent/'progress.json'),error=str(out.parent/'error.json'))
    return request,manifest,path

def test_actual99_source_constructor_and_factory_create_no_output_or_native(tmp_path,monkeypatch):
    request,manifest,path=current_production_request(tmp_path)
    monkeypatch.setattr(p,'_production_authority',REAL_PRODUCTION_AUTHORITY)
    bindings=dict(p._OWN_BINDINGS);bindings[('function','_production_authority')]=(REAL_PRODUCTION_AUTHORITY,REAL_PRODUCTION_AUTHORITY.__code__)
    monkeypatch.setattr(p,'_OWN_BINDINGS',p.MappingProxyType(bindings))
    calls=[]
    def prohibited(*args,**kwargs):calls.append('callback');raise AssertionError('CONSTRUCTOR_CALLBACK_FORBIDDEN')
    runner=p.scoped_lp_round(ORIGINAL_LP_ROUND,request,REPO,prohibited,prohibited,prohibited)
    assert runner.authority['execution_SHA']==manifest['execution_SHA'] and runner.authority['adapter_source']==f1_state._record(p.__file__)
    assert len(runner.authority['loaded_sources'])==9 and calls==[]
    assert not Path(request['output']).exists() and not Path(request['output']).parent.exists()

def test_actual99_loaded_mutable_parallel_source_is_denied(tmp_path,monkeypatch):
    request,manifest,path=current_production_request(tmp_path)
    monkeypatch.setattr(pricing,'__file__',str(tmp_path/'parallel/pricing.py'))
    with pytest.raises(PermissionError,match='LOADED_IMMUTABLE_SOURCE_REQUIRED'):
        REAL_PRODUCTION_AUTHORITY(request,REPO,f1_state._record(p.__file__))

def test_actual99_declared_self_source_sha_drift_has_shared_global_class(tmp_path):
    request,manifest,path=current_production_request(tmp_path)
    manifest['execution_sources']['v42_autonomous_b2/f1_price_seed.py']='0'*64
    legacy.write(path,manifest);request['manifest_SHA']=f1_state._record(path)['sha256']
    with pytest.raises(PermissionError,match='GLOBAL_SOURCE_INTEGRITY_FAILURE:PRICE_SEED_SHARED_SOURCE_SHA_DRIFT'):
        REAL_PRODUCTION_AUTHORITY(request,REPO,f1_state._record(p.__file__))

def test_actual99_complete_active_package_source_map_is_required(tmp_path):
    request,manifest,path=current_production_request(tmp_path)
    manifest['execution_sources'].pop('v42_autonomous_b2/pricing_cache.py')
    from v42_autonomous_b2 import worker
    manifest['execution_SHA']=worker.digest(manifest['execution_sources']);legacy.write(path,manifest)
    request.update(manifest_SHA=f1_state._record(path)['sha256'],implementation_SHA=manifest['execution_SHA'])
    with pytest.raises(PermissionError,match='B2_DEPLOYMENT_OR_REQUEST_SEAL_DRIFT'):
        REAL_PRODUCTION_AUTHORITY(request,REPO,f1_state._record(p.__file__))
