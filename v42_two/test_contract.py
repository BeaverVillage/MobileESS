"""Adversarial ordered-choice fixtures and objective/domain regression."""
from types import SimpleNamespace
import gurobipy as gp
import pytest
from .contract import *

def choice(options,block='AIDC',reference=0):
    # option = (rho, migration/movement energy, start/ movement count, relocation)
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.MIPGap=.005
    x=[m.addVar(vtype='B') for _ in options];m.addConstr(gp.quicksum(x)==1)
    rho=m.addVar(lb=0)
    for xx,row in zip(x,options):m.addConstr(rho>=row[0]*xx)
    expr=lambda column:gp.quicksum(row[column]*xx for row,xx in zip(options,x))
    reserve=m.addVar(lb=0);cc=m.addVar(lb=0)
    if block=='AIDC':
        legacy=[('rho',rho),('reserve_shortfall',reserve),('CC4_reference_deviation',cc),('migration_count',expr(1)),('shift_slots',expr(2)),('prestart_changes',expr(3))]
        units=[dict(uid=str(i),v={'y':{('A',row[2]):xx}}) for i,(row,xx) in enumerate(zip(options,x))]
        data=(None,{str(i):SimpleNamespace(reference_start=reference) for i in range(len(options))})
        m.update();before=m.Fingerprint;groups=aidc_groups(legacy,units,data);m.update();assert before==m.Fingerprint
    else:groups=mess_groups([('rho',rho),('reserve_shortfall',reserve),('movement_kwh',expr(1)),('movement_count',expr(2)),('tie',expr(3))])
    assert len(groups)==2 and [g.name for g in groups]==['MAX_LINE_LOADING','MIN_INTERVENTION']
    for group,name,obj in passes(groups):
        m.setObjective(obj);m.optimize();assert m.Status==gp.GRB.OPTIMAL
        m.addConstr(obj<=m.ObjVal+(P1_EPS if name=='rho' else COMPONENT_EPS))
    selected=next(i for i,v in enumerate(x) if v.X>.5)
    names=[name for _,name,_ in passes(groups)]
    assert not any(n in names for n in ['reserve_shortfall','CC4_reference_deviation','tie'])
    m.dispose();return selected

@pytest.mark.parametrize('options,expected',[
    ([(1,1,0,0),(1,0,5,1)],1), # STAY dominates migration despite shift/placement.
    ([(1,0,5,0),(1,0,0,1)],1), # Zero shift dominates lower-priority placement.
    ([(1,0,2,1),(1,0,2,0)],1), # No relocation after equal prior components.
    ([(.8,1,2,1),(1,0,0,0)],0), # Required intervention must preserve better P1.
    ([(1,0,-3,0),(1,0,2,0)],1), # Magnitude, not signed shift.
])
def test_adversarial_AIDC(options,expected):assert choice(options)==expected

@pytest.mark.parametrize('options,expected',[
    ([(1,3,1,0),(1,0,0,100)],1),
    ([(1,3,2,0),(1,3,1,100)],1),
    ([(.8,3,1,0),(1,0,0,0)],0),
])
def test_adversarial_MESS(options,expected):assert choice(options,'MESS')==expected

def test_degenerate_integer_gap_certificate():
    assert relative_gap(0,0) is None
    assert integer_certificate(0,0) and integer_certificate(3,2.999999)
    # A certified lower bound above 2 already proves an integer optimum of 3.
    assert integer_certificate(3,2.1)
    assert not integer_certificate(3,2.0)

def test_MESS_physical_adapter_preserves_joint_model():
    from v42_native.canary import fixture,mess_grid
    from v42_native.contracts import Deadline
    from .mess import solve
    sites,H,b,r=fixture()
    result,receipt=solve('M1',Deadline('M1',20),sites,{'M':'A'},r,b,H,mess_grid,unit_test=True)
    assert result['physical_audit']['PASS'] and result['lex_complete']
    assert receipt['scientific_objective_count']==2
    assert [x['component'] for x in receipt['passes']]==['rho','movement_energy','movement_count']
    assert any(n.startswith('SOC[') for n in result['values'])
    assert any(n.startswith('Q[') for n in result['values'])
    assert any(n.startswith('Pch[') for n in result['values'])
    assert result['report_only_metrics']['raw_reserve_shortfall']>=0
