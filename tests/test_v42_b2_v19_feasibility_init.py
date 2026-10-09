from types import SimpleNamespace as NS
import numpy as np
import pytest
from v42_b2_seed_recovery_v19 import initialization as init,diagnostics as diag,native_diagnostics as native

def case():
    route=NS(energy_kwh=20.,validate=lambda H:None)
    return NS(d=dict(names=np.array(['arc[M1,0]','arc[M1,1]','node_activity[M1,S0,0]',
        'node_activity[M1,STA2,0]','charge_mode[M1,0]','charge_mode[M1,1]']),types=np.array(['B']*6)),
        graph=(['S0','STA2'],{'M1':'S0'},[('S0',0,'S0',1,None),('S0',0,'STA2',2,route)],
        NS(maximum=100.,minimum=10.),None))

def test_f2_routes_fixed_but_selected_charge_modes_free_and_original_domain_unchanged():
    c=case();lo=np.zeros(6);hi=np.ones(6);before=c.d['types'].copy()
    low,high,receipt=init.pattern_bounds(c,lo,hi,stationary=True,free_modes=[1])
    assert low.tolist()==[1.,0.,1.,0.,0.,0.]
    assert high.tolist()==[1.,0.,1.,0.,0.,1.]
    assert np.array_equal(lo,np.zeros(6)) and np.array_equal(hi,np.ones(6))
    assert np.array_equal(c.d['types'],before) and receipt['original_constraints_removed']==0

def test_f2_all_modes_are_free_with_all_stationary_routes_still_fixed():
    low,high,_=init.pattern_bounds(case(),np.zeros(6),np.ones(6),stationary=True,free_modes=range(96))
    assert low[4:].tolist()==[0.,0.] and high[4:].tolist()==[1.,1.]
    assert low[:4].tolist()==high[:4].tolist()==[1.,0.,1.,0.]

def test_f3_expansion_releases_legal_routes_without_dropping_rows():
    c=case();lo=np.zeros(6);hi=np.ones(6)
    a,b,_=init.pattern_bounds(c,lo,hi,sites=['S0'],free_modes=range(96))
    x,y,receipt=init.pattern_bounds(c,lo,hi,sites=['S0','STA2'],free_modes=range(96))
    assert b[1]==0 and y[1]==1 and b[3]==0 and y[3]==1
    assert receipt['original_Adaptive_domain_changed'] is False

def test_screen_cannot_expand_a_fixed_original_bound():
    c=case();hi=np.ones(6);hi[0]=0
    with pytest.raises(ValueError,match='ORIGINAL_BOUND_DOMAIN'):
        init.pattern_bounds(c,np.zeros(6),hi,stationary=True,free_modes=range(96))

def test_voltage_slots_include_neighbors_but_do_not_delete_other_constraints():
    slots=init.critical_slots([dict(name='voltage_upper[43,235]'),dict(name='energy_balance[M1,6]')])
    assert slots==[41,42,43,44,45]

@pytest.mark.parametrize('code,name',[(3,'INFEASIBLE'),(4,'INF_OR_UNBD'),(9,'TIME_LIMIT'),(12,'NUMERIC'),(2,'OPTIMAL')])
def test_native_termination_classification(code,name):assert init.status_name(code)==name

def test_callback_cap_interrupt_is_distinct_from_infeasibility():
    assert init.status_name(11,True)=='INTERRUPTED_AT_POLICY_CAP'
    assert init.status_name(11,False)=='INTERRUPTED'

@pytest.mark.parametrize('name,group',[
    ('voltage_upper[43,235]','Voltage upper/lower'),('PCS16[1]','PCS kVA'),
    ('energy_balance[M1,43]','SOC time coupling'),('charge_mode[M1,43]','Charging/discharging exclusivity'),
    ('terminal_location[M1]','Route flow'),('injection_P_binding[A,43]','Fixed AIDC PCC power')])
def test_conflict_classification(name,group):assert diag.category(name)==group

def test_first_mipsol_uses_candidate_objective_even_when_prior_solcount_is_zero():
    import gurobipy as gp
    class Model:
        def cbGet(self,key):
            if key==gp.GRB.Callback.MIPSOL_OBJ:return 0.
            if key==gp.GRB.Callback.MIPSOL_SOLCNT:return 0.
            if key==gp.GRB.Callback.MIPSOL_OBJBST:return 1e100
            return 0.
    row=native.observe(Model(),gp.GRB.Callback.MIPSOL,gp)
    assert row['Native_incumbent']==0 and row['Native_solution_count_callback']==0
    assert row['Native_gap_source']=='CALLBACK_FLOAT_OBJECTIVE_BOUNDS_NOT_CERTIFIED'

class FakeModel:
    def __init__(self):
        self.Params=NS(Method=-1);self.Status=9;self.SolCount=0
        self.attrs={'LB':[0.]*6,'UB':[1.]*6,'VType':['B']*6,'Obj':[1.,2.,3.,4.,5.,6.]}
    def getVars(self):return list(range(6))
    def getAttr(self,k):return list(self.attrs[k])
    def setAttr(self,k,variables,value):self.attrs[k]=list(value)
    def setObjective(self,v,*a):self.attrs['Obj']=[float(v)]*6
    def reset(self):pass
    def update(self):pass
    def dispose(self):pass

@pytest.mark.parametrize('winner',['F2_CRITICAL_MODES','F5'])
def test_full_admission_and_unrestricted_fallback_restore_original_model(tmp_path,monkeypatch,winner):
    c=case();c.output=tmp_path;c.case_sha='case'
    model=FakeModel();point=np.array([1.,0.,1.,0.,0.,0.]);calls=[]
    monkeypatch.setattr(init,'validated_start',lambda *a:None)
    monkeypatch.setattr(init,'repaired_dispatch',lambda *a:None)
    monkeypatch.setattr(init,'analyze',lambda *a:[dict(name='voltage_upper[0,235]',domain='C3A')])
    monkeypatch.setattr(init,'sensitivity',lambda *a:({'S0':0.,'STA2':1.},0,[]))
    monkeypatch.setattr(init.original,'_model',lambda *a:(model,{}))
    budget=NS(native_limit=1500.,calls=[dict(Native_status=11)],used=lambda:len(calls),remaining=lambda:1500.-len(calls))
    def optimize(m,**kwargs):
        stage=kwargs['track'];calls.append(stage)
        if stage=='F5':
            assert m.attrs['LB']==[0.]*6 and m.attrs['UB']==[1.]*6
            assert m.attrs['VType']==['B']*6 and m.attrs['Obj']==[1.,2.,3.,4.,5.,6.]
            assert kwargs['requested_seconds']==300.
        else:assert m.attrs['Obj']==[0.]*6
        assert m.Params.SolutionLimit==1 and m.Params.MIPGap==.03
    budget.native_optimize=optimize
    monkeypatch.setattr(init,'full_point',lambda *a:(point,{'PASS':True},tmp_path/'FULL.json') if a[-1]==winner else None)
    def accepted(case,found,budget,stage):
        assert stage==winner and found[1]['PASS'] is True
        return found[0]
    monkeypatch.setattr(init,'accepted',accepted)
    assert init.initialize(c,budget,None) is point
    if winner.startswith('F2'):assert calls==['F2_CRITICAL_MODES']
    else:assert calls[-1]=='F5'

def test_f1_verified_point_skips_every_partial_and_unrestricted_milp(tmp_path,monkeypatch):
    from test_v42_b2_direct_lp_v18 import point_receipt
    point=np.array([1.,0.,.64]);receipt=point_receipt(tmp_path,point)
    init.atomic(tmp_path/'STATIONARY_DISPATCH_REPLAY.json',receipt)
    c=NS(output=tmp_path,case_sha='case',bundle={'day':'2025-05-04'})
    monkeypatch.setattr(init,'validated_start',lambda *a:point)
    monkeypatch.setattr(init.original,'_model',lambda *a:pytest.fail('F1 must skip additional MILP'))
    budget=NS(calls=[dict(Native_status=2,Native_Runtime=7.6,track='M_START',component='FEASIBILITY_LP')],
        used=lambda:7.6,remaining=lambda:1492.4,wall=lambda:167.6)
    assert init.initialize(c,budget,None) is point
    bypass=init.read(tmp_path/'SEED_BYPASS_CERTIFIED_DISPATCH.json')
    assert bypass['first_initialization_stage']=='F1_STATIONARY_LP' and bypass['unrestricted_F5_calls']==0
