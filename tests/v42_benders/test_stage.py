import numpy as np
import pytest
import gurobipy as gp
from v42_native.mess import Battery,RouteArc
from v42_benders.stage import Authority,build_model,solve_mess_stage_exact_benders
from v42_benders.canonical import from_model

def authority():
    routes=(RouteArc('low','A','B',0,1,1,.2,'a'*64),RouteArc('high','A','B',0,1,1,4.,'b'*64))
    battery=Battery(0,20,10,10,16,16,.9,.9)
    def grid(anchor,m,p,q):
        rho=m.addVar(lb=0,name='rho_max')
        for t in range(2):m.addConstr(anchor['load']-.005*sum(q[s,t] for s in ['A','B'])<=rho,name='grid')
        if anchor['require_B']:m.addConstr(q['B',1]>=2,name='M2_new_anchor')
        return [('rho',rho),('reserve_shortfall',gp.LinExpr(0.))]
    def validate(anchor,state,names,z):
        # Native physical constraints checked independently from assembled model.
        v=dict(zip(names,z));arcs=[('A',0,'A',1,None),('A',1,'A',2,None),('B',0,'B',1,None),('B',1,'B',2,None)]
        arcs.extend((r.source,r.depart,r.destination,r.connect,r) for r in routes)
        chosen=[k for k in range(len(arcs)) if v.get(f'arc[U,{k}]',0)>.5]
        for s in ['A','B']:
            for t in range(2):
                for key in ['Pch','Pdis','Q']:v.setdefault(f'{key}[U,{s},{t}]',0.)
        from v42_native.mess import validate as physical
        from dataclasses import replace
        audit=physical(dict(values=v,initial_sites=state['sites'],chosen_arcs={'U':chosen},mode='MILP'),
            ('A','B'),routes,replace(battery,initial=state['initial_SOC']),2,tolerance=1e-6)
        return {'PASS':audit['PASS'] and (not anchor['require_B'] or v['Q[U,B,1]']>=2-1e-7)}
    return Authority(('A','B'),routes,battery,2,grid,validate)

def test_M2_explicit_anchor_changes_grid_but_keeps_complete_route_bounds():
    a=authority();state=dict(sites={'U':'A'},initial_SOC=10)
    first=build_model(dict(load=1.,require_B=False),state,a)
    second=build_model(dict(load=2.,require_B=True),state,a)
    m1,m2=first['model'],second['model'];c1,c2=from_model(m1),from_model(m2)
    assert np.array_equal(c1.names,c2.names)
    assert np.array_equal(c1.xlower,c2.xlower) and np.array_equal(c1.xupper,c2.xupper)
    assert len(c1.xi)==7 and len(c2.xi)==7 and m2.NumConstrs==m1.NumConstrs+1
    assert all(prefix in ''.join(c2.names[c2.yi]) for prefix in ['Pch','Pdis','Q','SOC'])
    m1.dispose();m2.dispose()

def test_M2_joint_route_PQ_SOC_uses_M1_as_Start_only():
    a=authority();state=dict(sites={'U':'A'},initial_SOC=10)
    r1,z1,c1=solve_mess_stage_exact_benders(dict(load=1.,require_B=False),state,'P1_MAX_LINE_LOADING',authority=a,time_limit=30)
    assert z1 is not None and r1['accepted']
    # Warm start need not be feasible under a NEW anchor; no fixing is permitted.
    r2,z2,c2=solve_mess_stage_exact_benders(dict(load=1.,require_B=True),state,'P1_MAX_LINE_LOADING',authority=a,time_limit=30,warm_start=z1)
    assert z2 is not None and r2['accepted'] and z2['Q[U,B,1]']>=2-1e-7
    assert r2['route_bounds_unchanged'] and r2['joint_P_Q_SOC_decisions']
    assert r2['warm_start_values_applied']==7 and r2['warm_start_constraints_changed']==0

def test_stage_objective_and_P2_acceptance_gate():
    a=authority();state=dict(sites={'U':'A'},initial_SOC=10)
    with pytest.raises(ValueError,match='P2_REQUIRES'):solve_mess_stage_exact_benders({},state,'P2_MIN_INTERVENTION',authority=a)
    with pytest.raises(ValueError,match='OBJECTIVE_STAGE'):solve_mess_stage_exact_benders({},state,'other',authority=a)
    with pytest.raises(ValueError,match='P1_HAS_NO_LOCK'):solve_mess_stage_exact_benders({},state,'P1_MAX_LINE_LOADING',p1_lock={'accepted':True,'value':1},authority=a)

def test_initial_state_is_explicit_and_rebuilt():
    a=authority();built=build_model(dict(load=1.,require_B=False),dict(sites={'U':'A'},initial_SOC=11),a)
    m=built['model'];assert m.getConstrByName('initial_SOC').RHS==11
    assert m.getConstrByName('terminal_SOC').RHS==10
    assert m.NumBinVars==7;m.dispose()

def test_P1_lock_cannot_cross_anchor_state_context():
    a=authority();state=dict(sites={'U':'A'},initial_SOC=10)
    with pytest.raises(ValueError,match='CONTEXT_MISMATCH'):
        solve_mess_stage_exact_benders(dict(load=2.,require_B=True),state,'P2_MIN_INTERVENTION',
            p1_lock=dict(accepted=True,value=1.,anchor_state_sha256='wrong'),authority=a)

def test_same_context_P2_uses_inherited_lock_and_joint_recourse():
    a=authority();state=dict(sites={'U':'A'},initial_SOC=10);anchor=dict(load=1.,require_B=False)
    p1,z1,_=solve_mess_stage_exact_benders(anchor,state,'P1_MAX_LINE_LOADING',authority=a,time_limit=30)
    assert p1['accepted']
    lock=dict(accepted=True,value=p1['upper'],anchor_state_sha256=p1['anchor_state_sha256'])
    p2,z2,_=solve_mess_stage_exact_benders(anchor,state,'P2_MIN_INTERVENTION',authority=a,time_limit=30,p1_lock=lock,warm_start=z1)
    assert p2['P2_complete'] and p2['P1_lock']==p1['upper']+1e-7
    assert z2['rho_max']<=p2['P1_lock']+1e-7 and p2['warm_start_constraints_changed']==0
