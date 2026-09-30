from dataclasses import replace
from collections import defaultdict
import copy
import pytest
import numpy as np
import gurobipy as gp
from .common import *
from .graph import GraphFactory,old_to_compact,reconstruct
from .formulation import add_job,contributions,add_resources,values
from .equivalence import fixture,paths,model_for
from .native import completion_risk
from v42_job_capability import build_domain,resources_used,checkpoint_records
from v42_boundary.boundaries import load_native

@pytest.mark.parametrize('case',list('ABCDEFGHIJ'))
def test_exhaustive_bidirectional_paths_and_integral_states(case):
    j,b,r,_=fixture(case);old,_=build_domain(j,b,r)
    f,z,g=paths(j,b,r,old)
    assert len(f)==len(z)==len(old)
    assert all(row['maximum_state_fractionality']<1e-8 for row in z)

@pytest.mark.parametrize('seed',range(20))
def test_varied_WAN_fixed_occupancy_restart_carryout(seed):
    rng=np.random.default_rng(seed);j,b,r,_=fixture('F')
    j=replace(j,service_slots=int(rng.integers(2,9)),gpu=int(rng.integers(1,5)))
    r=replace(r,control_end=12,restart_slots=int(rng.integers(1,3)))
    r.fixed_gpu={(k,int(rng.integers(0,19))):int(rng.integers(0,9)) for k in ('A','B')}
    r.fixed_transfers={int(rng.integers(0,12)):int(rng.integers(0,2))}
    r.wan_capacities={('AB',t):int(rng.choice([0,80,160,640])) for t in range(12)}
    b=replace(b,latest_completion=22);old,_=build_domain(j,b,r)
    paths(j,b,r,old)

@pytest.mark.parametrize('elapsed',[None,0,1,899,900,1799,1800,1801,57238.3])
def test_RUNNING_phase_history_and_empty_prefix(elapsed):
    j,b,r,_=fixture('E');j=replace(j,elapsed_seconds=elapsed);old,_=build_domain(j,b,r)
    f,z,g=paths(j,b,r,old)
    assert all(s==j.event and k==j.reference_site for k,s in g.events['y'])

@pytest.mark.parametrize('mutation',['double_start','double_finish','double_checkpoint','no_transfer','early_transfer','wrong_source','wrong_destination',
    'source_gap','destination_gap','wait_compute','restart_compute','fractional_gang','short_service'])
def test_invalid_compact_assignments_rejected_by_actual_rows(mutation):
    j,b,r,_=fixture('F');old,_=build_domain(j,b,r)
    o=next(o for o in old if o.migrated and o.transfer_start>o.checkpoint)
    g=GraphFactory(r,30).graph(j,b);a=old_to_compact(o)
    if mutation=='double_start':a['y'][next(k for k in g.events['y'] if k not in a['y'])]=1
    elif mutation=='double_finish':a['f1'][next(k for k in g.events['f1'] if k not in a['f1'])]=1
    elif mutation=='double_checkpoint':a['q'][next(k for k in g.events['q'] if k not in a['q'])]=1
    elif mutation=='no_transfer':a['w']={}
    elif mutation=='early_transfer':
        a['q']={(o.initial_site,4):1};a['w']={(o.initial_site,o.destination,2):1}
    elif mutation=='wrong_source':a['q']={(o.destination,o.checkpoint):1}
    elif mutation=='wrong_destination':a['f1']={(o.initial_site,o.segments[-1][2]):1}
    elif mutation=='source_gap':a['r0'][o.initial_site,o.start]=0
    elif mutation=='destination_gap':a['r1'][o.destination,o.restart_end]=0
    elif mutation=='wait_compute':a['r0'][o.initial_site,o.checkpoint]=1
    elif mutation=='restart_compute':a['r1'][o.destination,o.restart_end-1]=1
    elif mutation=='fractional_gang':a['r0'][o.initial_site,o.start]=.5
    elif mutation=='short_service':a['f1']={(o.destination,o.segments[-1][2]-1):1}
    m,v,use,_,_=model_for({j.uid:j},{j.uid:b},r,graphs={j.uid:g})
    for n,items in v[j.uid].items():
        for key,x in items.items():m.addConstr(gp.LinExpr(x)==a[n].get(key,0))
    # An out-of-index event is itself forbidden. Force contradiction explicitly
    # rather than silently dropping the malformed requested event.
    outside=any(x and key not in v[j.uid][n] for n,items in a.items() for key,x in items.items())
    if outside:m.addConstr(gp.LinExpr()==1)
    m.optimize();assert m.Status==gp.GRB.INFEASIBLE;m.dispose()

def test_fixed_schedule_has_zero_selection_binaries():
    j,b,r,_=fixture('A');g=GraphFactory(r,30).graph(j,b)
    m,v,use,_,_=model_for({j.uid:j},{j.uid:b},r,graphs={j.uid:g});m.update()
    assert g.fixed and m.NumBinVars==0;m.dispose()

def test_wait_equal_checkpoint_zero_WAN_until_departure_and_exact_service():
    j,b,r,_=fixture('F');old,_=build_domain(j,b,r);g=GraphFactory(r,30).graph(j,b)
    assert any(o.migrated and o.transfer_start==o.checkpoint for o in old)
    assert any(o.migrated and o.transfer_start>o.checkpoint for o in old)
    for o in old:
        a=old_to_compact(o);assert reconstruct(j,b,r,g,a)==o
        assert sum(a['r0'].values())+sum(a['r1'].values())==j.service_slots
        if o.migrated:
            assert all(not a['r0'].get((o.initial_site,t),0) for t in range(o.checkpoint,o.restart_end))
            assert {t for k,t in a['h']}==set(range(o.checkpoint,o.transfer_start))

def test_no_second_migration_and_rack_authority():
    j,b,r,_=fixture('F');j=replace(j,migrations_used=1);g=GraphFactory(r,30).graph(j,b)
    assert not g.events['q'] and not g.events['w']
    j,b,r,_=fixture('H');g=GraphFactory(r,30).graph(j,b)
    assert all(k=='A' for k,s in g.events['y']) and not g.events['w']

def test_joint_two_jobs_use_actual_coupled_capacity():
    j,b,r,_=fixture('C');r=replace(r,capacities={'A':4,'B':4});k=replace(j,uid='second',reference_site='B')
    factory=GraphFactory(r,30);graphs={x.uid:factory.graph(x,b) for x in (j,k)}
    m,v,use,_,_=model_for({j.uid:j,k.uid:k},{j.uid:b,k.uid:b},r,graphs=graphs)
    m.addConstr(v[j.uid]['y']['A',0]==1);m.addConstr(v[k.uid]['y']['A',0]==1)
    m.optimize();assert m.Status==gp.GRB.INFEASIBLE;m.dispose()

def test_Runtime_completion_coefficients_exact_normal_and_migrated():
    from v42_final.reserve import risk_exposure
    j,b,r,_=fixture('F');old,_=build_domain(j,b,r)
    bundle=dict(runtime_reserve_gamma=2.423057443558147,runtime_survival_kernel=[1.,.75,.3])
    row=dict(risk_nominal_completion_issue_slot=30,reference_end=6)
    for o in old:
        expected={k:bundle['runtime_reserve_gamma']*x for k,x in risk_exposure(j.gpu,30+o.segments[-1][2]-6,o.segments[-1][0],bundle['runtime_survival_kernel'],range(24,120)).items()}
        assert completion_risk(j,row,o.segments[-1][0],o.segments[-1][2],bundle)==expected

def test_deterministic_graph_and_model_signature():
    j,b,r,_=fixture('F');a=GraphFactory(r,30).graph(j,b);z=GraphFactory(r,30).graph(j,b)
    assert a.sha==z.sha
    fingerprints=[]
    for graph in (a,z):
        m,v,use,_,_=model_for({j.uid:j},{j.uid:b},r,graphs={j.uid:graph});m.update();fingerprints.append(m.Fingerprint);m.dispose()
    assert fingerprints[0]==fingerprints[1]

def test_preserved_TS_and_interfaces_no_expanded_production_path():
    for row in read(OUT/'PR98_BYTE_SNAPSHOT.json'):assert sha(row['path'])==row['sha256']
    assert read(PR98/'FINAL_TS_CAPABILITY_SUMMARY.json')['known_TS_candidates']==1024
    for filename in ('native.py','execute.py','graph.py','formulation.py'):
        source=(ROOT/'v42_compact'/filename).read_text(encoding='utf8')
        assert 'pickle' not in source and 'temporal_domain(' not in source and 'build_domain(' not in source and '.domain(' not in source

@pytest.mark.parametrize('incumbent,gap,expected',[(1.,.0009,True),(1.,.01,False),(None,None,False),(1.,0.,True)])
def test_time_limit_quality_does_not_require_OPTIMAL(incumbent,gap,expected):
    from .execute import quality_met
    assert quality_met([dict(status=gp.GRB.TIME_LIMIT,incumbent=incumbent,gap=gap)])==expected

@pytest.mark.parametrize('bound',[float('-inf'),float('inf'),float('nan')])
def test_no_incumbent_nonfinite_bound_receipt_is_valid_JSON(bound):
    from .execute import optimization_receipt
    row=optimization_receipt([dict(status=gp.GRB.TIME_LIMIT,incumbent=None,best_bound=bound,gap=None,nodes=0,solve_seconds=1.)],{},False)
    encoded=json.dumps(row,allow_nan=False)
    assert json.loads(encoded)['passes'][0]['best_bound'] is None

def test_validation_budget_preserves_quality_qualified_incumbent(monkeypatch,tmp_path):
    from . import execute
    j,b,r,_=fixture('A');g=GraphFactory(r,30).graph(j,b)
    m=gp.Model();m.Params.OutputFlag=0;x=m.addVar(vtype=gp.GRB.BINARY);m.addConstr(x==1)
    data=({}, {j.uid:j}, {j.uid:b}, r, {}, {j.uid:g}, {})
    monkeypatch.setattr(execute,'prepare',lambda context:data)
    monkeypatch.setattr(execute,'build',lambda context,data:(m,{j.uid:old_to_compact(g.fixed)},[('rho',x),('later',x)],[]))
    class Context:
        folder=tmp_path
        candidate=None
        @property
        def remaining(self):return 29 if (tmp_path/'OPTIMIZATION.json').exists() else 60
        def progress(self,value):pass
        def publish(self,candidate):self.candidate=candidate
        def check(self,seconds=0):
            if self.remaining<=seconds:raise TimeoutError()
    context=Context();execute.worker(context,dict(sources=[],mode='SOLVE'))
    assert context.candidate['audit']['quality_rule_met'] and not context.candidate['audit']['lex_complete']
