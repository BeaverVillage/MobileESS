"""Physical boundary adversaries and algorithm-level decomposition checks."""
from dataclasses import replace
from collections import defaultdict
import pytest
import gurobipy as gp
from v42_compact.equivalence import fixture
from v42_dw.audits import make_factory,synthetic_binder,reduced_cost_audit
from v42_dw.pricing import price,initial_columns
from v42_dw.master import Master
from v42_dw.cg import generate
from v42_job_capability import build_domain,resources_used,Option

@pytest.fixture
def setup():
    j,b,r,_=fixture('F');f=make_factory({j.uid:j},{j.uid:b},r);old,_=build_domain(j,b,r)
    return j,b,r,f,old

def test_physical_profiles_and_registry(setup):
    j,b,r,f,old=setup
    for o in old:
        c=f.make(j.uid,o)
        assert c.signature==f.make(j.uid,o).signature
        assert sum(c.gpu.values())==j.gpu*j.service_slots
        use=resources_used(j,o)
        assert c.gpu=={(k,t):n for (kind,k,t),n in use.items() if kind=='GPU'}
        assert c.wan=={(k,t):n for (kind,k,t),n in use.items() if kind=='WAN'}
        assert c.active=={t:n for (kind,k,t),n in use.items() if kind=='ACTIVE'}
        site,_,end=o.segments[-1]
        assert c.risk==f.risk(j.uid,site,end)
        co=c.master_coefficients()
        assert co['CONVEXITY',j.uid]==1
        for (k,t),n in c.gpu.items():assert co['GPU',k,t]==-n
        for (k,t),n in c.risk.items():
            if n:assert co['RISK',k,t]==-n
        for (k,t),n in c.wan.items():assert co['WAN',k,t]==n
        if o.migrated:
            blocked=range(o.checkpoint,o.restart_end)
            assert not any((k,t) in c.gpu for k in r.capacities for t in blocked)

@pytest.mark.parametrize('change',[
    {'initial_site':'Z'}, {'start':99}, {'checkpoint':1}, {'transfer_start':0},
    {'physical_checkpoint_seconds':1}, {'restart_end':9}, {'destination':'A'},
    {'segments':(('A',0,2),('B',4,6),('A',7,9))},
    {'wan':(('AB',2,1),)},
])
def test_invalid_columns_rejected(setup,change):
    j,b,r,f,old=setup;o=next(x for x in old if x.migrated)
    with pytest.raises(ValueError):f.make(j.uid,replace(o,**change))

def test_wait_zero_rate_restart_carryout():
    j,b,r,_=fixture('F');r=replace(r,wan_capacities={('AB',t):0 if t in (2,3) else 160 for t in range(12)})
    f=make_factory({j.uid:j},{j.uid:b},r);old,_=build_domain(j,b,r)
    delayed=[o for o in old if o.migrated and o.transfer_start>o.checkpoint]
    assert delayed
    for o in delayed:
        c=f.make(j.uid,o)
        assert o.restart_end==o.transfer_end+r.restart_slots
        assert sum(c.wan.values())==r.bytes_per_gpu*j.gpu
    j,b,r,_=fixture('I');f=make_factory({j.uid:j},{j.uid:b},r);old,_=build_domain(j,b,r)
    assert all(f.make(j.uid,o).record()['completion_slot']>r.control_end for o in old)

def test_fixed_constants_and_convexity():
    j,b,r,_=fixture('A');f=make_factory({j.uid:j},{j.uid:b},r);initial,fixed,_=initial_columns(f)
    assert not initial and len(fixed)==1
    m=Master(f,initial,fixed,synthetic_binder(r));assert m.size()['columns']==0
    assert all(k[0]!='CONVEXITY' for k in m.rows);m.dispose()

def test_duplicate_insertion_all_jobs_and_lock_rc(setup):
    j,b,r,f,old=setup;initial,fixed,_=initial_columns(f);m=Master(f,initial,fixed,synthetic_binder(r))
    assert not m.add(initial[j.uid]);assert m.size()['binaries']==0
    audits=[]
    migrated=next(o for o in old if o.migrated)
    result=generate(m,include_tie=False,solve_audit=lambda:audits.append(reduced_cost_audit(m,f.make(j.uid,migrated))))
    assert result['converged'] and result['phase1_zero']
    assert all(x['jobs_priced']==1 and x['complete_pricing'] for x in result['iterations'])
    assert all(x['duplicate_rediscoveries']==0 for x in result['iterations'])
    assert any(x['active_locks']>=4 for x in audits)
    assert all(x['PASS'] for x in audits)
    assert all(v.UB==0 for v in m.artificial)
    assert m.size()['binaries']==0
    m.dispose()

def test_positive_artificial_never_accepted(setup):
    j,b,r,f,old=setup;initial,fixed,_=initial_columns(f);m=Master(f,initial,fixed,synthetic_binder(r))
    m.m.setObjective(m.artificial_expr);m.m.optimize()
    # Force actual global infeasibility in a synthetic test, not May physics.
    row=m.rows['GPU','A',0];row.RHS=100.;m.m.optimize()
    assert m.artificial_expr.getValue()>0
    with pytest.raises(ValueError,match='POSITIVE_PHASE1'):m.disable_artificial()
    m.dispose()

def test_exact_pricing_no_complete_domain_dependency(setup,monkeypatch):
    from v42_boundary.generator import Generator
    j,b,r,f,old=setup
    monkeypatch.setattr(Generator,'domain',lambda *a:pytest.fail('production complete enumeration'))
    c,rc,p=price(f,j.uid,{})
    assert c.option in old and rc==0
    assert p['WAN_transitions']==len(f.graphs[j.uid].transfers)

def test_registry_factorization_random_duals(setup):
    import numpy as np
    from v42_dw.column import PricingCosts
    j,b,r,f,old=setup;cs=[f.make(j.uid,o) for o in old]
    keys=set().union(*(x.master_coefficients() for x in cs));rng=np.random.default_rng(47)
    dual={k:float(rng.normal()) for k in sorted(keys)};cost=PricingCosts(f,j.uid,dual)
    for c in cs:
        o=c.option;k=o.initial_site;s=o.start;site,_,end=o.segments[-1]
        val=cost.convexity+cost.start(k,s)+sum(cost.run(k,a,z) for k,a,z in o.segments)+cost.terminal(site,end)
        if o.migrated:val+=cost.metric['migration_count']+cost.tie('q',(k,o.checkpoint))+cost.transfer(k,o.destination,o.transfer_start,f.graphs[j.uid].transfers[k,o.destination,o.transfer_start])+cost.tie('f1',(site,end))
        else:val+=cost.tie('f0',(site,end))
        assert val==pytest.approx(c.reduced_cost(dual),abs=1e-7)

def test_complete_phase1_infeasibility_certificate():
    j,b,r,_=fixture('A');f=make_factory({j.uid:j},{j.uid:b},r);initial,fixed,_=initial_columns(f)
    def impossible(m,known,risk):
        z=m.addVar(lb=0,ub=0);m.addConstr(z>=1);return [('rho',z),('reserve_shortfall',z),('CC4_reference_deviation',z)]
    m=Master(f,initial,fixed,impossible);result=generate(m,include_tie=False)
    assert result['infeasible'] and not result['phase1_zero'] and not result['converged'];m.dispose()

@pytest.mark.parametrize('tie',[0.,.25,-.5])
def test_template_reuse_equals_uncached_exact_pricing(setup,tie):
    import numpy as np
    from v42_dw.pricing import PricingSweep
    j,b,r,_,old=setup;j2=replace(j,uid='F2');f=make_factory({j.uid:j,j2.uid:j2},{j.uid:b,j2.uid:b},r)
    columns=[f.make(uid,o) for uid in f.jobs for o in old];keys=set().union(*(c.master_coefficients() for c in columns))
    rng=np.random.default_rng(63)
    for index in range(8):
        dual={k:float(rng.uniform(-1,1)) for k in sorted(keys)};dual['METRIC','deterministic_tie']=tie
        sweep=PricingSweep(f,dual)
        for uid in sorted(f.jobs):
            c,rc,p=sweep.price(uid);exact,value,_=price(f,uid,dual)
            assert c.option==exact.option and rc==value

def test_template_cache_includes_gpu_when_graph_sha_equal():
    from v42_dw.pricing import PricingSweep
    j,b,r,_=fixture('C');other=replace(j,uid='C2',gpu=2)
    f=make_factory({j.uid:j,other.uid:other},{j.uid:b,other.uid:b},r)
    assert f.graphs[j.uid].sha==f.graphs[other.uid].sha
    dual={('GPU','A',0):2.,('GPU','B',0):1.}
    sweep=PricingSweep(f,dual)
    for uid in f.jobs:
        c,rc,_=sweep.price(uid);exact,value,_=price(f,uid,dual)
        assert rc==value and c.option==exact.option
    assert len(sweep.cache)==2

def test_complete_structure_counts_match_exact_traversal(setup):
    from v42_dw.pricing import structure_counts
    j,b,r,f,old=setup;c,rc,p=price(f,j.uid,{})
    expected=structure_counts(f.graphs[j.uid],r.control_end)
    assert all(p[k]==v for k,v in expected.items())
