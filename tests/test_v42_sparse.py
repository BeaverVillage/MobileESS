from dataclasses import replace,asdict
from collections import defaultdict
import gurobipy as gp
import pytest
from v42_root.gates import fixture,model,classes_for
from v42_root.native import reconstruct
from v42_sparse.config import PRIMARY
from v42_sparse.runtime import coefficient_vector,factor_finishes
from v42_sparse.canonical import assign
from v42_job_capability import Option,resources_used

@pytest.mark.parametrize('field',['runtime_authority','exact_service_seconds','V10_Q50_total_seconds'])
def test_equal_slots_and_risk_offset_do_not_hide_different_provider_semantics(field):
    j,b,r,_=fixture('F');jobs={'A':replace(j,uid='A'),'B':replace(j,uid='B')};bounds={u:b for u in jobs}
    raw={u:dict(risk_nominal_completion_issue_slot=0,reference_end=0) for u in jobs}
    raw['A'][field]=1;raw['B'][field]=2
    assert len(classes_for(jobs,bounds,r,raw=raw))==2

def test_restored_cache_cannot_bypass_provider_signature(monkeypatch,tmp_path):
    import pickle
    import v42_root.data as source
    j,b,r,_=fixture('F');jobs={u:replace(j,uid=u) for u in ['A','B']};bounds={u:b for u in jobs}
    raw={u:dict(risk_nominal_completion_issue_slot=0,reference_end=0,runtime_authority=u) for u in jobs}
    bundle=dict(runtime_reserve_gamma=2.423057443558147,runtime_survival_kernel=[1,.5,.25])
    cache=tmp_path/'DATA.pkl';cache.write_bytes(pickle.dumps((bundle,jobs,bounds,r,raw,{},{},dict(classes={'stale':['A','B']}))))
    before=cache.read_bytes();monkeypatch.setattr(source,'LOCAL',tmp_path)
    verified=source.prepare();assert len(verified[-1]['classes'])==2
    assert verified[-1]['cached_classes_independently_reverified']
    assert cache.read_bytes()==before

def test_nonmigration_histogram_keeps_only_authorized_finish_support():
    from v42_exact.support import ExactFactory
    from v42_root.factor import add_job
    j,b,r,_=fixture('D');j=replace(j,service_slots=2,checkpoint_authorized=False);b=replace(b,allowed_starts=(0,),latest_completion=2)
    g=ExactFactory(r,2).graph(j,b)
    events=dict(g.events);events['y']=tuple(g.events['y'])+(('A',2),)
    g=replace(g,events=events)
    m=gp.Model();m.Params.OutputFlag=0;v=add_job(m,j,g,r,eliminate_f0=True)
    assert ('A',2) not in v['y'];m.optimize();assert m.Status==gp.GRB.OPTIMAL;m.dispose()

@pytest.mark.parametrize('kind',PRIMARY[1:]+['DA0','DA1','DA2','DA3','LINK','F0','STATE'])
@pytest.mark.parametrize('case',['B','F','J'])
def test_sparse_candidates_complete_individual_validation(kind,case):
    j,b,r,_=fixture(case);m,units,data,*_=model({j.uid:j},{j.uid:b},r,kind)
    m.optimize();assert m.Status==gp.GRB.OPTIMAL
    assert reconstruct(units,data)==reconstruct(units,data);m.dispose()

def test_Runtime_count_rejects_unequal_entire_coefficient_vector():
    j,b,r,_=fixture('F');jobs={'A':replace(j,uid='A'),'B':replace(j,uid='B')}
    raw={'A':dict(risk_nominal_completion_issue_slot=20,reference_end=20),'B':dict(risk_nominal_completion_issue_slot=21,reference_end=20)}
    bundle=dict(runtime_reserve_gamma=2.423057443558147,runtime_survival_kernel=[1,.5,.25])
    assert coefficient_vector(jobs['A'],raw['A'],'A',30,bundle)!=coefficient_vector(jobs['B'],raw['B'],'A',30,bundle)
    m=gp.Model();m.Params.OutputFlag=0;x=m.addVar();y=m.addVar()
    with pytest.raises(ValueError,match='UNEQUAL_RUNTIME'):factor_finishes(m,[('A','A',30,x),('B','A',30,y)],jobs,raw,bundle,{'g':['A','B']})
    m.dispose()

def test_Runtime_count_exact_sum_and_downstream_vector():
    j,b,r,_=fixture('F');jobs={u:replace(j,uid=u) for u in ['A','B']};raw={u:dict(risk_nominal_completion_issue_slot=20,reference_end=20) for u in jobs}
    bundle=dict(runtime_reserve_gamma=2.423057443558147,runtime_survival_kernel=[1,.5,.25]);m=gp.Model();m.Params.OutputFlag=0
    x=m.addVar(lb=1,ub=1);y=m.addVar(lb=1,ub=1)
    out=factor_finishes(m,[('A','A',30,x),('B','A',30,y)],jobs,raw,bundle,{'g':['A','B']});m.optimize()
    assert len(out)==1 and out[0][3].X==2
    vec=coefficient_vector(jobs['A'],raw['A'],'A',30,bundle)
    assert all(a*out[0][3].X==a*x.X+a*y.X for key,a in vec);m.dispose()

def test_canonical_UID_assignment_preserves_all_resource_aggregates():
    j,b,r,_=fixture('D');jobs={u:replace(j,uid=u) for u in ['A','Z']};bounds={u:b for u in jobs}
    options=[Option(0,'A',(('A',0,j.service_slots),)),Option(0,'B',(('B',0,j.service_slots),))]
    selected={'Z':asdict(options[0]),'A':asdict(options[1])};data=(None,jobs,bounds,r,None,None,None,dict(classes=classes_for(jobs,bounds,r)))
    result=assign(selected,data);assert result==assign(selected,data)==assign(result,data)
    def resources(plans):
        out=defaultdict(float)
        for u,row in plans.items():
            d=dict(row);d['segments']=tuple(d['segments']);d['wan']=tuple(d['wan'])
            for key,n in resources_used(jobs[u],Option(**d)).items():out[key]+=n
        return out
    assert resources(result)==resources(selected)
    assert result['A']['initial_site']=='A'
