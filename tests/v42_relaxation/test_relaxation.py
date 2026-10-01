"""Check the mechanisms independently of full-case solve outcomes."""
import gurobipy as gp
import pytest
from v42_native.mess import Battery,RouteArc
from v42_relaxation.diagnostics import energy_model,mode_rows

def test_native_hook_exposes_read_only_context_without_changing_default_matrix(monkeypatch):
    from dataclasses import FrozenInstanceError
    import v42_native.mess as native
    records=[]
    def capture(m,objectives,deadline,*args,**kwargs):
        m.setObjective(objectives[0][1]);m.update()
        records.append((m.NumVars,m.NumConstrs,m.NumNZs,m.Fingerprint))
        return None,{}
    monkeypatch.setattr(native,'optimize',capture)
    class Budget:
        stage='M1'
        def check(self):pass
    def builder(m,p,q):return [('rho',m.addVar(name='rho')),('reserve_shortfall',0)]
    observed=[]
    def inspect(m,c):
        observed.append(c)
        assert tuple(c.charge_mode)==(('M',0),('M',1))
        with pytest.raises(TypeError):c.x['M',0]=0
        with pytest.raises(TypeError):c.initial_sites['M']='B'
        with pytest.raises(FrozenInstanceError):c.horizon=3
    b=Battery(0,10,5,5,4,5,1,1)
    native.solve('M1',Budget(),('A',),{'M':'A'},(),b,2,builder)
    native.solve('M1',Budget(),('A',),{'M':'A'},(),b,2,builder,strengthening_hook=inspect)
    assert len(observed)==1 and records[0]==records[1]

def test_mode_aggregate_violation_and_connected_discharge():
    sites=('A','B');initial={'M':'A'};b=Battery(0,10,5,5,100,100,1,1)
    v={'arc[M,0]':.5,'arc[M,1]':.5,'charge_mode[M,0]':.25,
       'Pch[M,A,0]':25.,'Pch[M,B,0]':25.,'Pdis[M,A,0]':40.,'Pdis[M,B,0]':40.}
    row=mode_rows(v,sites,initial,b,1)[0]
    assert row['H1_residual']==-.75
    assert row['H2_residual']==25.
    assert row['H3_residual']==5.

@pytest.mark.parametrize('power,expected',[(0,gp.GRB.OPTIMAL),(8,gp.GRB.OPTIMAL),(24,gp.GRB.INFEASIBLE)])
@pytest.mark.parametrize('compact_bounds',[False,True])
def test_fixed_arc_energy_distinguishes_branch_pooling(power,expected,compact_bounds):
    # A half-mass branch can carry at most 5 kWh. Injecting 6 kWh into
    # that branch is impossible even if opposite-branch discharge cancels
    # perfectly in the pooled time-indexed SOC recurrence.
    b=Battery(0,10,5,5,100,100,1,1)
    r=RouteArc('A:B:0','A','B',0,1,1,0,'a'*64)
    arcs=[('A',0,'A',1,None),('A',0,'B',1,r),
          ('A',1,'A',2,None),('B',1,'B',2,None)]
    x={('M',k):.5 for k in range(4)}
    ch={('M','A',0):0,('M','B',0):0,('M','A',1):power,('M','B',1):0}
    dis={key:0 for key in ch};dis['M','B',1]=power
    m,_=energy_model(arcs,('A','B'),{'M':'A'},b,x,ch,dis,horizon=2,compact_bounds=compact_bounds)
    try:
        m.Params.Threads=1;m.optimize();assert m.Status==expected
    finally:m.dispose()

def test_no_energy_is_invented_at_reconvergence():
    b=Battery(0,10,5,4,100,100,1,1)
    r=RouteArc('A:B:0','A','B',0,1,1,2,'a'*64)
    arcs=[('A',0,'A',1,None),('A',0,'B',1,r),
          ('A',1,'A',2,None),('B',1,'A',2,RouteArc('B:A:1','B','A',1,2,2,0,'b'*64))]
    x={('M',k):.5 for k in range(4)}
    ch={('M',s,t):0 for s in ('A','B') for t in range(2)}
    m,_=energy_model(arcs,('A','B'),{'M':'A'},b,x,ch,ch,horizon=2)
    try:
        m.Params.Threads=1;m.optimize();assert m.Status==gp.GRB.OPTIMAL
    finally:m.dispose()

def test_preservation_authorization_remains_hash_specific():
    from v42_voltage.preservation import assert_authorized
    from v42_relaxation.base import ROOT,sha
    with pytest.raises(AssertionError,match='UNSEALED_CURRENT_CHANGE|UNAUTHORIZED_LEGACY_CHANGE'):
        assert_authorized('v42_native/mess.py','0'*64)
    with pytest.raises(AssertionError,match='BASELINE_HASH_MISMATCH|DEFAULT_MODEL_REGRESSION_MISSING|UNAUTHORIZED_LEGACY_CHANGE'):
        assert_authorized('v42_native/mess.py',sha(ROOT/'v42_native/mess.py'),'0'*64)


def test_barrier_capture_keeps_actual_status_and_supports_optimum_interval():
    # The constraint supplies a rigorous lower bound 1. The captured feasible
    # point supplies the upper bound; no solver status is relabeled.
    import numpy as np
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Method=2;m.Params.Threads=1
    m.Params.Presolve=0  # Only this tiny API fixture needs a nonempty barrier.
    x=m.addVar(lb=0);m.addConstr(x>=1);m.setObjective(x)
    captured=[]
    def cb(model,where):
        if where==gp.GRB.Callback.MESSAGE and 'Crossover log...' in model.cbGet(gp.GRB.Callback.MSG_STRING):
            captured.append(True);model.terminate()
    try:
        m.optimize(cb);assert captured
        assert m.Status in (gp.GRB.INTERRUPTED,gp.GRB.OPTIMAL)
        primal=np.asarray(m.getAttr('BarX'));dual=np.asarray(m.getAttr('BarPi'))
        assert np.isfinite(primal).all() and np.isfinite(dual).all()
        assert abs(primal[0]-1)<1e-7 and dual[0]>=-1e-5
    finally:m.dispose()
