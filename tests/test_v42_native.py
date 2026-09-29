from dataclasses import replace
import math
import pytest
import gurobipy as gp
from v42_native.contracts import Deadline
from v42_native.mess import pcs_rows,solve,validate
from v42_native.canary import fixture,mess_grid,aidc_fixture,aidc_grid
from v42_native.solver import assert_milp
from v42_native.service import service_identity,reconcile,boundary
from v42_native.providers import UnpromotedRuntime,JobRequest,FrozenCC4
from v42_native.actual import KernelAnchor,unknown_arrival,event_due,PAPER_POLICIES,repair_pq,require_fresh_ac
from v42_native.aidc import solve as aidc_solve
from v42_native.coordinator import gate
from v42_job_capability import build_domain


@pytest.mark.parametrize('voltage,tx_current,tx_power,feasible',[(1.,.5,1.,True),(.8,.5,1.,False),(1.,1.1,1.,False),(1.,.5,3.,False)])
def test_native_grid_anchor_and_separate_hard_security(voltage,tx_current,tx_power,feasible):
    from types import SimpleNamespace
    import numpy as np
    from v42_native.grid import GridAuthority,add_grid
    c=SimpleNamespace(slot=0,control_names=('P',),coefficient_sha256='a'*64,
        voltage_constant=np.array([voltage]),voltage_matrix=np.zeros((1,1)),
        branch_limits=np.array([2.,2.]),flow_p_constant=np.array([1.,tx_power]),
        flow_q_constant=np.zeros(2),flow_p_matrix=np.zeros((2,1)),flow_q_matrix=np.zeros((2,1)),
        anchor=np.zeros(1),current_matrix=np.zeros((1,2)),current_constant=np.array([.6,tx_current]),
        branch_names=('line.test::a','transformer.main::a'),transformer_ratings=(None,2.))
    authority=GridAuthority(*(['b'*64]*4),.95**2,1.05**2,True)
    m=gp.Model();m.Params.OutputFlag=0
    try:
        rho=add_grid(m,[c],[[0.]],authority);m.setObjective(rho);m.optimize()
        assert (m.Status==gp.GRB.OPTIMAL)==feasible
        if feasible:assert rho.X==pytest.approx(.6)
        assert_milp(m)
    finally:m.dispose()


def test_external_wall_timeout_does_not_accept_raw_diagnostics(tmp_path):
    from v42_native.supervision import supervise
    result,receipt=supervise('M1','v42_native.canary:worker','v42_native.canary:validator',
        {'stage':'M1'},tmp_path/'wall',seconds=.001)
    assert result is None and receipt['timeout_reason']=='EXTERNAL_HARD_WALL_TIMEOUT'
    assert receipt['external_process_tree'] and not receipt['validated_incumbent_exists']


@pytest.mark.parametrize('angle',[math.pi*i/64 for i in range(128)])
def test_inner_polygon_radial_proof(angle):
    radius=math.cos(math.pi/16)/max(math.cos(angle-2*math.pi*f/16) for f in range(16))
    assert math.cos(math.pi/16)-1e-12<=radius<=1+1e-12


@pytest.mark.parametrize('connected',[0,1])
def test_polygon_connection_and_pq(connected):
    m=gp.Model();m.Params.OutputFlag=0
    try:
        p=m.addVar(lb=-5,ub=5);q=m.addVar(lb=-5,ub=5)
        pcs_rows(m,p,q,connected,5);m.setObjective(p+q,gp.GRB.MAXIMIZE);m.optimize()
        assert math.hypot(p.X,q.X)<=5+1e-8
        if not connected:assert abs(p.X)+abs(q.X)<1e-8
        else:assert p.X>0 and q.X>0
        assert_milp(m)
    finally:m.dispose()


def test_mess_three_formulations_same_routes_service_and_safe_circle():
    sites,H,b,r=fixture();results={}
    for mode in ('MILP','LEGACY_BOTH','CIRCLE_ONLY_DIAGNOSTIC'):
        result,receipt=solve('M1',Deadline('M1',20),sites,{'M':'A'},r,b,H,mess_grid,mode=mode,diagnostic=True)
        assert result['physical_audit']['PASS'] and result['physical_audit']['max_exact_circle_ratio']<=1+1e-5
        assert result['physical_audit']['mobility_energy_kwh']>0
        assert receipt['model_size']['quadratic_constraints']==(0 if mode=='MILP' else 13)
        results[mode]=result
    assert results['MILP']['objectives']['rho']==pytest.approx(results['LEGACY_BOTH']['objectives']['rho'],abs=3e-7)
    assert results['MILP']['objectives']['rho']>=results['CIRCLE_ONLY_DIAGNOSTIC']['objectives']['rho']-1e-7


def test_m2_warm_start_applied_and_accepted():
    sites,H,b,r=fixture()
    first,_=solve('M1',Deadline('M1',20),sites,{'M':'A'},r,b,H,mess_grid)
    second,receipt=solve('M2',Deadline('M2',20),sites,{'M':'A'},r,b,H,mess_grid,first)
    assert receipt['warm_start_values_applied']>0 and receipt['warm_start_accepted']
    assert second['domain_sha256']==first['domain_sha256']


def test_a2_warm_start_joint_options_and_fixed_constants():
    jobs,b,r=aidc_fixture();u=next(iter(jobs))
    options,_=build_domain(jobs[u],b[u],r)
    assert {'SHIFT_PREPLACE','SHIFT_PREPLACE_MIGRATE'}<={o.action(jobs[u]) for o in options}
    first,_=aidc_solve('A1',Deadline('A1',20),jobs,b,r,aidc_grid,seconds_authority={u:5400})
    second,receipt=aidc_solve('A2',Deadline('A2',20),jobs,b,r,aidc_grid,first,seconds_authority={u:5400})
    assert receipt['warm_start_values_applied']>0 and receipt['warm_start_accepted']
    job=replace(jobs[u],initial_sites=('A',),checkpoint_authorized=False,standby_candidate_authorized=False)
    _,fixed=aidc_solve('A1',Deadline('A1',20),{u:job},b,r,aidc_grid,seconds_authority={u:5400})
    assert fixed['model_size']['binary']==0 and fixed['singleton_jobs']==1


def test_cross_midnight_exact_seconds_and_tail():
    receipt=service_identity(1900,4,(('A',95,98),))
    assert receipt['prefix_compute_seconds']==900 and receipt['tail_compute_seconds']==1000
    assert receipt['unused_final_reservation_seconds']==800
    assert receipt['exact_compute_GPUh']==pytest.approx(1900*4/3600)


def test_snapshot_reconciliation_never_moves_site_or_invents_requeue():
    old={'episode_id':'e','site':'A','absolute_start_seconds':0}
    current={'episode_id':'e','site':'A','observed_seconds':10,'state':'PENDING'}
    assert reconcile(old,current,10)['release_previous'] is False
    current.update(state='RUNNING',known_start_seconds=5)
    assert reconcile(old,current,10)['release_previous'] is True
    current['site']='B'
    with pytest.raises(ValueError):reconcile(old,current,10)


def test_provider_missing_and_future_truth_rejected():
    j=JobRequest('u',0,{'qos':'normal'},{'qos':0},'a'*64);provider=UnpromotedRuntime()
    assert provider.predict_total(j,0).status=='UNPROMOTED'
    with pytest.raises(ValueError):provider.predict_total(replace(j,features={'actual_runtime':3},observed_at={'actual_runtime':0}),0)
    with pytest.raises(ValueError):provider.predict_remaining(j,-1,0)
    with pytest.raises(ValueError):FrozenCC4((1,)*24,(2,)*24,1,'a'*64,True).validate(0)


def test_unknown_handler_does_not_invoke_policy_with_unpromoted_provider():
    j=JobRequest('u',0,{}, {},'a'*64);anchor=KernelAnchor(*['a'*64]*4)
    def forbidden(*args):raise AssertionError('POLICY_MUST_NOT_RUN')
    result=unknown_arrival(j,0,UnpromotedRuntime(),anchor,anchor,forbidden,{})
    assert result['global_MILP_calls']==0 and result['capability_masks'] is None
    with pytest.raises(ValueError):anchor.require_same(replace(anchor,reference_sha='b'*64))


def test_event_namespace_and_cadence():
    assert event_due(2,PAPER_POLICIES[0],2,threshold=1)
    assert not event_due(1,PAPER_POLICIES[0],2,threshold=1)
    assert not event_due(2,PAPER_POLICIES[2],0,threshold=1)
    with pytest.raises(ValueError):event_due(2,'M1',2,threshold=1)


def test_repair_p_and_q_with_energy_compensation_no_discrete_actions():
    _,_,b,_=fixture()
    plan=dict(P=[1.,-1.],Q=[0.,0.],connected=[1,1],charge_mode=[0,1],mobility_kwh=[0.,0.],
        initial_kwh=10,terminal_kwh=10,unit='kW_kvar_kWh',causal_inputs_verified=True)
    def grid(m,p,q):
        rho=m.addVar(lb=0);m.addConstr(.8-.1*p[0]-.01*q[0]<=rho);return rho
    result,receipt=repair_pq(plan,b,grid,max_delta_kw=2,max_delta_kvar=2)
    assert result is not None and receipt['model_size']['integer']==receipt['model_size']['binary']==0
    v=result['values'];assert abs(v['P[0]']-1)>1e-5 and v['Q[0]']>0
    assert v['SOC[2]']==pytest.approx(10) and v['SOC[1]']==pytest.approx(10-.25*v['P[0]']/.95)
    assert [row['level'] for row in receipt['passes']]==['rho','P_change','Q_change']
    with pytest.raises(ValueError):repair_pq(dict(plan,mobility_kwh=[-.1,0]),b,grid,max_delta_kw=2,max_delta_kvar=2)
    with pytest.raises(ValueError):repair_pq(plan,b,grid,max_delta_kw=2,max_delta_kvar=2,policy_id=PAPER_POLICIES[2])


def test_final_fresh_ac_gate_rejects_stub_stale_and_violation():
    r=dict(engine='OpenDSS',fresh_run=True,synthetic=False,schedule_sha='a'*64,grid_sha='b'*64,converged=True,
        voltage_violations=0,line_current_violations=0,transformer_current_violations=0,transformer_kVA_violations=0)
    assert require_fresh_ac(r,'a'*64,'b'*64)
    for bad in (dict(r,synthetic=True),dict(r,converged=False),dict(r,line_current_violations=1),dict(r,schedule_sha='c'*64)):
        with pytest.raises(ValueError):require_fresh_ac(bad,'a'*64,'b'*64)


def test_native_gate_no_stub_or_ml_dependency():
    assert not gate({})['PASS']
    import v42_native.providers as p
    assert 'lightgbm' not in vars(p) and 'raddit' not in vars(p)
    with pytest.raises(ValueError):Deadline('A1',601)


def test_hidden_quadratic_callback_rejected():
    m=gp.Model();m.Params.OutputFlag=0
    try:
        x=m.addVar();m.addQConstr(x*x<=1)
        with pytest.raises(ValueError):assert_milp(m)
    finally:m.dispose()


def test_P2_only_uncertainty_not_known_service():
    from v42_native.envelope import bind
    m=gp.Model();m.Params.OutputFlag=0
    try:
        f=FrozenCC4((1.,)*24,(4.,)*24,0,'a'*64,True)
        def physics(model,nominal,reserve):return dict(nominal_physics=True,incremental_readiness_physics=True,authority_sha256='b'*64)
        env=bind(m,f,0,{('A',t):7 for t in range(96)},{'A':8},physics)
        m.setObjective(env['shortfall']);m.optimize()
        assert m.ObjVal==pytest.approx(72)  # known7 + nominal1 leaves no reserve
        assert all(v.X==pytest.approx(0) for v in env['reserve'].values())
    finally:m.dispose()


def test_completion_cannot_release_a_current_running_observation():
    old={'episode_id':'e','site':'A','absolute_start_seconds':0}
    current={'episode_id':'e','site':'A','observed_seconds':10,'state':'RUNNING','known_start_seconds':2}
    with pytest.raises(ValueError):
        reconcile(old,current,10,completion_receipt=dict(episode_id='e',observed_seconds=10,source_sha256='a'*64))
