import copy
from pathlib import Path
import pytest
import gurobipy as gp
from v42_native.voltage import *
from v42_native.grid import GridAuthority,add_grid
from v42_native.actual import repair_pq,require_fresh_ac,require_frozen_replay
from v42_native.contracts import digest
from v42_voltage.handoff import validate_handoff


def test_exact_squared_authority_and_all_planning_paths():
    assert PLANNING_LOWER_SQUARED==pytest.approx(PLANNING_LOWER_PU**2,abs=1e-15)
    assert PLANNING_UPPER_SQUARED==pytest.approx(PLANNING_UPPER_PU**2,abs=1e-15)
    assert (ACTUAL_LOWER_PU,ACTUAL_UPPER_PU)==(.95,1.05)
    root=Path(__file__).resolve().parents[1]
    for f in ('v42_boundary/model.py','v42_compact/native.py','v42_temporal/native.py','v42_exact/validation.py','v42_native/canary.py','v42_voltage/grid.py'):
        s=(root/f).read_text(encoding='utf8')
        assert ('voltage_for' in s or 'PLANNING_LOWER_SQUARED' in s) and ('voltage_for' in s or 'PLANNING_UPPER_SQUARED' in s)
        assert '.95**2' not in s and '1.05**2' not in s
    assert authority()['stages']==['M1','A2','M2']
    assert authority(Stage.A1)['lower_pu']==.95 and authority(Stage.A1)['upper_pu']==1.05


@pytest.mark.parametrize('lo,hi',[(.95**2,1.05**2),(.955,1.045),(.912025,1.05**2)])
def test_grid_rejects_unsquared_old_and_mixed_authorities(lo,hi):
    with pytest.raises(ValueError,match='PLANNING_VOLTAGE_AUTHORITY_MISMATCH'):
        GridAuthority(*['a'*64]*4,lo,hi,True,stage=Stage.M1).validate()


def test_removed_repair_never_builds_or_optimizes(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Actual optimizer accessed')
    monkeypatch.setattr(gp,'Model',forbidden)
    with pytest.raises(ValueError,match='ACTUAL_LOCAL_PQ_REPAIR_REMOVED_IN_V42'):
        repair_pq({},None,forbidden,max_delta_kw=0,max_delta_kvar=0)


def test_frozen_actual_replay_and_failed_fresh_ac_have_no_fallback():
    p=dict(route=['A','B'],P=[-1,1],Q=[2,-2],movement=[.1])
    assert require_frozen_replay(p,copy.deepcopy(p))
    for field in ('route','P','Q','movement'):
        changed=copy.deepcopy(p);changed[field]=[]
        with pytest.raises(ValueError,match='ACTUAL_FROZEN_PLAN_CHANGED'):require_frozen_replay(p,changed)
    r=dict(engine='OpenDSS',fresh_run=True,synthetic=False,schedule_sha='a'*64,grid_sha='b'*64,converged=True,
           voltage_violations=1,line_current_violations=0,transformer_current_violations=0,transformer_kVA_violations=0)
    with pytest.raises(ValueError,match='FRESH_AC_PHYSICS'):require_fresh_ac(r,'a'*64,'b'*64)
    r.update(voltage_violations=0,voltage_lower_pu=.955,voltage_upper_pu=1.045)
    with pytest.raises(ValueError,match='ACTUAL_PHYSICAL_VOLTAGE_AUTHORITY'):require_fresh_ac(r,'a'*64,'b'*64)


def test_handoff_acceptance_hash_unknown_and_individual_count_gates():
    anchor=dict(voltage_authority_sha256=authority_sha(),controls=[[1,2]])
    h=dict(accepted=True,known_jobs=1499,physical_PASS=True,unknown_individual_jobs_fabricated=False,anchor_digest=digest(anchor))
    assert validate_handoff(h,anchor)
    for update in (dict(accepted=False),dict(known_jobs=117),dict(physical_PASS=False),dict(unknown_individual_jobs_fabricated=True)):
        with pytest.raises(ValueError):validate_handoff(dict(h,**update),anchor)
    with pytest.raises(ValueError,match='A1_ANCHOR_CHANGED'):validate_handoff(h,dict(anchor,controls=[[9,2]]))


def test_fixed_m1_grid_adds_no_aidc_variables_and_pq_cannot_change_anchor(monkeypatch,tmp_path):
    import numpy as np
    from types import SimpleNamespace
    import v42_voltage.grid as grid
    master=tmp_path/'master.dss';master.write_text('frozen')
    names=['aidc_load_kw[AIDC01]','mess_p_kw[AIDC01]','mess_q_kvar[AIDC01]']
    coeff=[SimpleNamespace(slot=t,control_names=names,coefficient_sha256='a'*64,
                           voltage_constant=np.array([1.]),voltage_matrix=np.array([[-.001],[.001],[.001]]),
                           branch_names=[],branch_limits=[],transformer_ratings=[],anchor=np.zeros(3),
                           flow_p_constant=np.zeros(0),flow_q_constant=np.zeros(0),flow_p_matrix=np.zeros((0,3)),
                           flow_q_matrix=np.zeros((0,3)),current_matrix=np.zeros((3,0)),current_constant=np.zeros(0)) for t in range(96)]
    cert=dict(input_identity=dict(identity=dict(inputs=dict(OpenDSS_master=dict(path=str(master))))))
    monkeypatch.setattr(grid,'coefficients',lambda b:(cert,coeff))
    anchor=dict(voltage_authority_sha256=authority_sha(),control_names=names,controls=[[1.,0.,0.]]*96)
    before=digest(anchor)
    with gp.Model() as m:
        m.Params.OutputFlag=0
        p={('AIDC01',t):m.addVar(lb=-2,ub=2,name=f'P[{t}]') for t in range(96)}
        q={('AIDC01',t):m.addVar(lb=-2,ub=2,name=f'Q[{t}]') for t in range(96)}
        levels,ctrl=grid.frozen_grid(m,dict(capacities={'AIDC01':80},battery={}),anchor,p,q)
        m.setObjective(-p['AIDC01',0]-q['AIDC01',0]);m.optimize()
        assert p['AIDC01',0].X==2 and q['AIDC01',0].X==2
        assert all(row[0]==1. for row in ctrl) and digest(anchor)==before
        assert all(not v.VarName.startswith(('known','anonymous','CC4','AIDC')) for v in m.getVars())
        assert len([c for c in m.getConstrs() if c.ConstrName.startswith('voltage_')])==192


def test_m1_optimize_only_budget_is_cumulative_and_build_has_no_clock_charge():
    from v42_voltage.m1 import OptimizeOnlyBudget
    b=OptimizeOnlyBudget();b.check();assert b.remaining==1800
    b.spent=800;b.check();assert b.remaining==1000
    b.spent=1800
    with pytest.raises(ValueError,match='M1_OPTIMIZE_BUDGET_EXHAUSTED'):b.check()


def test_joint_mess_route_charge_discharge_both_q_signs_and_travel_soc():
    from v42_native.canary import fixture
    from v42_native.contracts import Deadline
    from v42_two.mess import solve
    sites,H,b,routes=fixture()
    def grid(m,p,q):
        rho=m.addVar(lb=0,ub=1,name='rho_max')
        m.addConstr(p['A',0]<=-1);m.addConstr(q['A',0]>=1);m.addConstr(q['A',1]<=-1)
        m.addConstr(p['B',4]>=1)
        for t in range(H):m.addConstr(.8-.01*p['B',t]-.01*q['B',t]<=rho)
        return [('rho',rho),('reserve_shortfall',gp.LinExpr(0))]
    best,receipt=solve('M1',Deadline('M1',20),sites,{'M':'A'},routes,b,H,grid,unit_test=True)
    assert best['physical_audit']['PASS'] and best['physical_audit']['mobility_energy_kwh']==pytest.approx(.1)
    v=best['values'];assert v['Pch[M,A,0]']>=1-1e-5 and v['Pdis[M,B,4]']>=1-1e-5
    assert v['Q[M,A,0]']>=1-1e-5 and v['Q[M,A,1]']<=-1+1e-5
    assert v['SOC[M,3]']==pytest.approx(v['SOC[M,2]']-.1,abs=1e-5)
    assert v['SOC[M,8]']==pytest.approx(b.terminal)
    assert all(any(n.startswith(prefix) for n in v) for prefix in ('arc[','charge_mode[','Pch[','Pdis[','Q[','SOC['))
    assert best['physical_audit']['max_exact_circle_ratio']<=1+1e-5


def test_saved_interval_certificate_proves_full_box_contradiction():
    import json,numpy as np
    root=Path(__file__).resolve().parents[1]
    proof=json.loads((root/'docs/v42_voltage_margin_a1_m1/A1_INFEASIBILITY_DIAGNOSIS.json').read_text())
    assert proof['independent_proof_PASS'] and len(proof['violations'])==145
    for row in proof['violations']:
        a=np.array(row['voltage_coefficients']);lb=np.array(row['controls_lower']);ub=np.array(row['controls_upper'])
        lo=row['voltage_constant']+np.maximum(a,0)@lb+np.minimum(a,0)@ub
        hi=row['voltage_constant']+np.maximum(a,0)@ub+np.minimum(a,0)@lb
        assert lo==pytest.approx(row['minimum_squared'],abs=1e-12)
        assert hi==pytest.approx(row['maximum_squared'],abs=1e-12)
        assert lo>PLANNING_UPPER_SQUARED+1e-8 or hi<PLANNING_LOWER_SQUARED-1e-8
