from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import pytest
from scipy import sparse
from v42_b2_seed_recovery_v18 import initialization as init,certificate_box as box,seed_policy
from v42_b2_seed_recovery_v18.common import atomic,read,sha
from v42_m1_research.check_ub import vector_sha

def point_receipt(tmp_path,point):
    path=tmp_path/'point.npz';np.savez_compressed(path,point=point)
    receipt=dict(PASS=True,case_sha='case',point_path=str(path),point_file_sha256=sha(path),
        point_vector_sha256=vector_sha(point),Global_UB=.64,exact_Global_UB=str(F(.64)),
        strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
        original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha='case'))
    atomic(tmp_path/'STATIONARY_DISPATCH_REPLAY.json',receipt)
    return receipt

def test_valid_full_lp_admission_skips_mip(tmp_path,monkeypatch):
    from v42_b2_seed_recovery_v18 import stationary_dispatch
    point=np.array([.64,1.,0.]);point_receipt(tmp_path,point)
    case=NS(output=tmp_path,case_sha='case',bundle={'day':'2025-05-02'},point=None)
    budget=NS(used=lambda:3300.,remaining=lambda:2100.)
    monkeypatch.setattr(stationary_dispatch,'validated_start',lambda *a:point)
    monkeypatch.setattr(init,'candidate_lp',lambda *a:pytest.fail('candidate LP should be skipped'))
    assert init.initialize(case,budget,None) is point
    receipt=read(tmp_path/'SEED_BYPASS_CERTIFIED_DISPATCH.json')
    assert receipt['PASS'] and receipt['M_SEED_optimize_calls']==0
    assert receipt['point_vector_sha256']==vector_sha(point)
    assert receipt['historical_date_point_reused'] is False
    assert receipt['cumulative_Native_Runtime']==3300

@pytest.mark.parametrize('attack',['LP_only','wrong_case','point_mutation','packet_mutation'])
def test_lp_only_or_unverified_start_is_never_admitted(tmp_path,attack):
    point=np.array([.64,1.,0.]);receipt=point_receipt(tmp_path,point)
    if attack=='LP_only':receipt['original_matrix_and_96_slot_physical_replay']['PASS']=False
    elif attack=='wrong_case':receipt['original_matrix_and_96_slot_physical_replay']['case_sha']='other-day'
    elif attack=='point_mutation':point[1]=.99999999999
    else:Path(receipt['point_path']).write_bytes(b'mutated')
    with pytest.raises(ValueError,match='FULL_STRICT_REPLAY'):
        init.admit(NS(output=tmp_path,case_sha='case',bundle={'day':'2025-05-02'}),point,receipt,
            tmp_path/'STATIONARY_DISPATCH_REPLAY.json',NS(used=lambda:10,remaining=lambda:5390),'LP')
    assert not (tmp_path/'SEED_BYPASS_CERTIFIED_DISPATCH.json').exists()

def data(A):
    return dict(lower=np.array([-2.,-np.inf,-np.inf]),upper=np.array([3.,np.inf,np.inf]),
        sense=np.array(['=','=']),rhs=np.array([1.,2.]),objective=np.array([1.,0.,0.]),
        constant=np.array(0.),names=np.array(['x','helper1','helper2']))

def test_exact_equality_envelopes_replay_and_old_checker_unchanged():
    A=sparse.csr_matrix([[-.1,1.,0.],[0.,-3.,-2.]])
    d=data(A);before={k:v.copy() for k,v in d.items()}
    lo,hi,proof=box.derive(A,d)
    assert box.verify(A,d,lo,hi,proof)['all_original_feasible_points_contained']
    cert=box.check(A,d,{})
    assert cert['exact_bound']=='-2' and cert['native_BestBd_used'] is False
    assert cert['original_checker_byte_preserved']
    for k in before:assert np.array_equal(before[k],d[k])
    for x in (-2.,3.):
        y=F(1)+F(float(.1))*F(x);z=(F(2)-F(-3)*y)/F(-2)
        assert F(lo[1])<=y<=F(hi[1]) and F(lo[2])<=z<=F(hi[2])

@pytest.mark.parametrize('attack',['rhs','pivot','bound','inward','inequality','missing'])
def test_envelope_rejects_tampered_proof(attack):
    A=sparse.csr_matrix([[-.1,1.,0.],[0.,-3.,-2.]])
    d=data(A);lo,hi,proof=box.derive(A,d);proof=deepcopy(proof)
    if attack=='rhs':d['rhs'][0]+=1
    elif attack=='pivot':proof['steps'][0]['pivot']='2'
    elif attack=='bound':proof['steps'][0]['exact_upper']='0'
    elif attack=='inward':proof['steps'][0]['upper']-=.1
    elif attack=='inequality':d['sense'][0]='<'
    else:proof['steps'].pop()
    with pytest.raises(ValueError):box.verify(A,d,lo,hi,proof)

def test_no_arbitrary_caps_for_genuinely_free_variable():
    A=sparse.csr_matrix([[1.,0.,0.]])
    d=data(A);d['sense']=np.array(['=']);d['rhs']=np.array([1.])
    with pytest.raises(ValueError,match='DO_NOT_PROVE_FINITE'):box.derive(A,d)

def graph():
    from v42_native.mess import RouteArc,Battery
    arcs=[(s,t,s,t+1,None) for s in ('A','B') for t in range(96)]
    a=RouteArc('out','A','B',20,22,23,4.,'a'*64)
    b=RouteArc('back','B','A',60,62,63,4.,'a'*64)
    arcs.extend([('A',20,'B',23,a),('B',60,'A',63,b)])
    return (('A','B'),{'u':'A'},arcs,Battery(100,1000,500,500,100,120,.95,.95),{})

def test_route_candidates_use_original_eta_energy_soc_complete_paths():
    g=graph();candidates=init.route_paths(g,48,{'A':0,'B':2})
    assert len(candidates)==1
    c=candidates[0]
    assert c['route_energy_kwh']==8 and c['initial_SOC']==c['terminal_SOC']==500
    assert c['route_ids']==['out','back']
    case=NS(graph=g,d=dict(names=np.array(['node_activity[u,A,21]','node_activity[u,B,24]',
        'charge_mode[u,65]','arc[u,192]']),types=np.array(['B']*4)))
    ids,values=init.values_for(case,c['paths'],lambda u,t:t>=63)
    assert values.tolist()==[0.,1.,1.,1.]
    c['paths']['u'].pop(0)
    with pytest.raises(ValueError,match='FLOW_OR_ETA'):init.values_for(case,c['paths'],lambda u,t:False)

def test_fallback_settings_are_initialization_only(tmp_path,monkeypatch):
    from v42_b2_seed_recovery_v18 import execution
    model=NS(Params=NS(),SolCount=0,Status=9,dispose=lambda:None)
    monkeypatch.setattr(execution,'current',lambda:None)
    monkeypatch.setattr(seed_policy,'seed_model',lambda case:(model,{}))
    ledger=tmp_path/'ledger.json';atomic(ledger,{})
    calls=[]
    budget=NS(native_optimize=lambda m,**kw:calls.append(kw),used=lambda:900,remaining=lambda:4500,path=ledger)
    case=NS(output=tmp_path,case_sha='case',bundle={'day':'2025-05-02'})
    point,receipt=seed_policy.seed_integer(case,budget,None)
    assert point is None and receipt['status']=='TIME_LIMIT_NO_VALID_INCUMBENT'
    assert model.Params.MIPFocus==1 and model.Params.SolutionLimit==1
    assert len(calls)==1 and calls[0]['requested_seconds']==900

from test_v42_b2_seed_policy import seed_case,ports

@pytest.mark.parametrize('dual_value,accepted,gap',[('97/100',True,'3/100'),('0',False,'1')])
def test_original_run_consumes_case_point_without_seed_and_keeps_exact_gate(seed_case,monkeypatch,dual_value,accepted,gap):
    from v42_b2_seed_recovery_v18 import m_stage
    from v42_may_campaign_native90 import m_stage as original
    from v42_m1_research.check_lb import check_rational_dual_certificate
    case,budget,model=seed_case
    case.point=model.point.copy();case.planning={};case.identity['transport']=dict(PASS=True)
    monkeypatch.setattr(m_stage,'prepare',lambda *a:case)
    monkeypatch.setattr(m_stage,'seed_integer',lambda *a:pytest.fail('FULL-certified case.point must bypass seed MILP'))
    monkeypatch.setattr('v42_m1_hybrid.blocks.build_blocks',lambda c:NS(units=()))
    monkeypatch.setattr('v42_m1_hybrid.verify.verify_decomposition',lambda *a:None)
    def lb(c,b,p):
        dual={} if dual_value=='0' else {'0':dual_value}
        cert=check_rational_dual_certificate(c.A,c.d,dual,case_sha=c.case_sha)
        cert['exact_Global_LB']=cert['exact_bound'];atomic(c.output/'INITIAL_EXACT_LB_CERTIFICATE.json',cert)
        return dual,cert
    monkeypatch.setattr(original,'_fresh_lp_dual',lb)
    def plan(c,p):
        atomic(c.output/'OPTIMIZED_MESS_PLAN.json',{})
        return {}
    monkeypatch.setattr(original,'_plan',plan)
    def boundary(*a,**kw):raise TimeoutError('fixture Adaptive boundary')
    monkeypatch.setattr('v42_m1_anytime.algorithms.dynamic_grid',boundary)
    result=m_stage.run(dict(arm='B2',day='2025-05-01'),budget,None)
    assert result['PASS'] is accepted and result['exact_gap']==gap
    assert model.calls==0 and budget.used()==0.
    assert result['certificate']['strict_UB']['sha256'] and result['certificate']['exact_LB']['sha256']

def test_prepare_sets_point_before_original_run_without_model_domain_changes(tmp_path,monkeypatch):
    from v42_b2_seed_recovery_v18 import m_stage,execution,policy
    point=np.array([1.,.64])
    case=NS(point=None,identity={k:1 for k in policy.MODEL_FIELDS},output=tmp_path,case_sha='case')
    monkeypatch.setattr(m_stage,'original_prepare',lambda *a:case)
    monkeypatch.setattr(execution,'current',lambda:None)
    monkeypatch.setattr(m_stage,'current',lambda:None)
    seen=[]
    def initialize(c,b,p):
        seen.append((c,b));return point
    monkeypatch.setattr(init,'initialize',initialize)
    budget=object()
    assert m_stage.prepare({'_budget':budget},None).point is point
    assert seen==[(case,budget)]
