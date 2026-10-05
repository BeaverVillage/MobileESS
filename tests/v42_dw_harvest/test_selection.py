from fractions import Fraction as F
import hashlib
import itertools
import numpy as np
from v42_dw_harvest.selection import HarvestState, projection_key, select_batch


class ToyAdapter:
    def __init__(self, alpha=20., pi=(0., 0.), true_pi=None):
        self.alpha, self.pi, self.true_pi = F(alpha), tuple(map(F, pi)), tuple(map(F, true_pi or pi))

    def audit(self, x):
        # x=(integer route identity, master injection1, injection2, local cost).
        return dict(PASS=len(x)==4 and all(np.isfinite(x)) and x[0]==round(x[0]) and 0<=x[0]<=100 and all(-10<=v<=10 for v in x[1:]))

    def exact(self, x):
        key=hashlib.sha256(repr(x).encode()).hexdigest()
        a={i:F(v) for i,v in enumerate(x[1:3]) if v};c=F(x[3])
        true=c-self.alpha-sum((self.true_pi[i]*v for i,v in a.items()),F(0))
        search=c-self.alpha-sum((self.pi[i]*v for i,v in a.items()),F(0))
        return key,a,c,true,search


def test_external_rc_exact_and_true_dual_rejection():
    state=HarvestState(0,ToyAdapter(alpha=1.,pi=(2.,0.),true_pi=(0.,0.)))
    state.observe((1,1,0,2),native_objective=-1.)
    assert state.events[-1]['search_RC']==-1. and state.events[-1]['true_RC']==1.
    assert not state.selected()


def test_infeasible_and_objective_mismatch_never_admitted():
    s=HarvestState(0,ToyAdapter())
    s.observe((.5,1,0,0));s.observe((1,1,0,0),native_objective=-10.)
    assert not s.selected() and [e['decision'] for e in s.events]==['INFEASIBLE','SEARCH_OBJECTIVE_MISMATCH']


def test_exact_projection_duplicates_not_tolerance_merges():
    s=HarvestState(0,ToyAdapter())
    for x in [(1,1,0,0),(2,1,0,0),(3,np.nextafter(1.,2.),0,0)]:s.observe(x)
    assert len(s.selected())==2 and s.metrics()['duplicates_removed']==1


def test_pending_dominance_and_no_existing_column_deletion():
    s=HarvestState(0,ToyAdapter())
    s.observe((1,1,0,2));s.observe((2,1,0,1));s.observe((3,1,0,3))
    assert len(s.selected())==1 and s.selected()[0].objective==1
    assert s.metrics()['dominated_removed']==2
    old={projection_key(0,{0:F(1)}):F(2)}
    s=HarvestState(0,ToyAdapter(),existing_projections=old)
    s.observe((1,1,0,3));s.observe((2,1,0,2));s.observe((3,1,0,1))
    assert len(s.selected())==1 and old=={projection_key(0,{0:F(1)}):F(2)}


def test_existing_pool_and_same_solve_exact_trajectory_dedup():
    a=ToyAdapter();x=(1.,1.,0.,0.);key=a.exact(x)[0]
    s=HarvestState(0,a,[key]);s.observe(x);assert not s.selected()
    s=HarvestState(0,a);s.observe(x);s.observe(x);assert len(s.selected())==1
    assert s.metrics()['duplicates_removed']==1


def test_k8_deterministic_strong4_diverse4():
    points=[(i,float(i%4),float(i//4),float(i)/10) for i in range(12)]
    batches=[]
    for order in [points,list(reversed(points)),points[5:]+points[:5]]:
        s=HarvestState(0,ToyAdapter())
        for x in order:s.observe(x)
        batches.append(s.selected())
    assert len(batches[0])==8 and batches[0]==batches[1]==batches[2]
    assert [c.objective for c in batches[0][:4]]==list(map(F,[0.,.1,.2,.3]))
    assert len({c.trajectory_SHA for c in batches[0]})==8


def test_projection_keys_mess_axis_and_signed_zero():
    assert projection_key(0,{0:F(0),1:F(1)})==projection_key(0,{1:F(1)})
    assert projection_key(0,{1:F(1)})!=projection_key(1,{1:F(1)})


def test_one_actual_pricing_tree_yields_many_validated_columns():
    import gurobipy as gp
    from v42_dw_harvest.selection import UsefulColumn
    with gp.Model('tiny_single_tree_harvest') as m:
        m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.Presolve=0;m.Params.Heuristics=0
        m.Params.FeasibilityTol=1e-8;m.Params.IntFeasTol=1e-8;m.Params.OptimalityTol=1e-8
        xs=m.addVars(12,vtype=gp.GRB.BINARY,obj={i:-(i+1) for i in range(12)})
        m.addConstr(xs.sum()==1);m.update();m.NumStart=12
        for k in range(12):
            m.Params.StartNumber=k
            m.setAttr('Start',list(xs.values()),[float(i==k) for i in range(12)])
        captures=[]
        def callback(native,where):
            if where==gp.GRB.Callback.MIPSOL:
                x=native.cbGetSolution(list(xs.values()))
                assert abs(sum(x)-1)<1e-8 and all(v==round(v) for v in x)
                rc=-sum((F(i+1)*F(v) for i,v in enumerate(x)),F(0))
                assert abs(float(rc)-native.cbGet(gp.GRB.Callback.MIPSOL_OBJ))<1e-8
                captures.append(UsefulColumn(0,repr(x),projection_key(0,{i:F(v) for i,v in enumerate(x) if v}),rc,rc,rc,tuple(x),'MIPSOL'))
        m.optimize(callback)  # Exactly one tree / call, no no-good cuts.
        assert m.Status==gp.GRB.OPTIMAL and len({c.trajectory_SHA for c in captures})>=2
        assert len(select_batch(captures))<=8


def test_old_new_rmp_optimum_equivalence_under_exact_projection_pruning():
    import gurobipy as gp
    points=[(1,0,0,0),(2,0,0,1),(3,1,0,1),(4,1,0,2),(5,1,0,1)]
    s=HarvestState(0,ToyAdapter())
    for x in points:s.observe(x)
    def solve(columns):
        with gp.Model('tiny_projection_rmp') as m:
            m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.OptimalityTol=1e-8
            v=m.addVars(len(columns),obj={i:c[3] for i,c in enumerate(columns)})
            m.addConstr(v.sum()==1);m.addConstr(gp.quicksum(v[i]*c[1] for i,c in enumerate(columns))>=.5)
            m.optimize();assert m.Status==2;return m.ObjVal
    assert abs(solve(points)-solve([c.values for c in s.selected()]))<1e-8


def test_certification_factory_returns_original_controller():
    from v42_dw_harvest.worker import controller_factory
    from v42_dw_runtime.validation import DiscoveryController
    from v42_dw_runtime.contracts import DiscoverySnapshot,RuntimeFlags
    snapshot=DiscoverySnapshot.create(1,[0.],[0.],[0.]*4,[0.]*4,.1,.6)
    factory=controller_factory({},None,DiscoveryController)
    c=factory('FINAL_CERTIFICATION',0,snapshot,None,RuntimeFlags(True,True,True,False),[])
    assert type(c) is DiscoveryController and not c.enabled
