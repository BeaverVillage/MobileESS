from dataclasses import replace
from collections import defaultdict
import json
import gurobipy as gp
import pytest
from v42_root.gates import fixture,model,classes_for
from v42_root.native import reconstruct
from v42_root.common import ROOT,OUT,value
from v42_root.eliminate import project
from v42_job_capability import Option,validate,build_domain,resources_used,resource_limit

@pytest.mark.parametrize('case',list('ABCDEFGHIJ'))
@pytest.mark.parametrize('kind',['F2A','F2B','F2C'])
def test_full_physical_authorities(case,kind):
    j,b,r,_=fixture(case);jobs={j.uid:j};bounds={j.uid:b}
    m,units,data,*_=model(jobs,bounds,r,kind);m.optimize();assert m.Status==gp.GRB.OPTIMAL
    plan=reconstruct(units,data)[j.uid];plan['segments']=tuple(plan['segments']);plan['wan']=tuple(plan['wan']);o=Option(**plan)
    assert validate(j,o,b,r)
    assert sum(z-a for k,a,z in o.segments)==j.service_slots
    assert reconstruct(units,data)==reconstruct(units,data)
    m.dispose()

@pytest.mark.parametrize('change',['uid','Runtime','shift_cost','latest_completion','checkpoint','rack_sites'])
def test_scientific_class_strictness(change):
    j,b,r,_=fixture('F');jobs={j.uid:j,'OTHER':replace(j,uid='OTHER')};bounds={u:b for u in jobs};raw={u:dict(risk_nominal_completion_issue_slot=0,reference_end=0) for u in jobs};costs={}
    if change=='Runtime':raw['OTHER']['risk_nominal_completion_issue_slot']=1
    if change=='shift_cost':costs['OTHER']={'shift_cost':2}
    if change=='latest_completion':bounds['OTHER']=replace(b,latest_completion=b.latest_completion+1)
    if change=='checkpoint':jobs['OTHER']=replace(jobs['OTHER'],checkpoint_authorized=False)
    if change=='rack_sites':jobs['OTHER']=replace(jobs['OTHER'],initial_sites=('A',))
    classes=classes_for(jobs,bounds,r,raw=raw,costs=costs)
    assert len(classes)==(1 if change=='uid' else 2)

@pytest.mark.parametrize('family',['r0','h','r1'])
def test_eliminated_state_complete_integer_paths(family):
    j,b,r,_=fixture('F');j=replace(j,service_slots=4);b=replace(b,allowed_starts=(0,),latest_completion=14)
    m,units,data,*_=model({j.uid:j},{j.uid:b},r,'F2');v={j.uid:units[0]['v']}
    n,nv,convert=project(m,v,{family});new=[dict(units[0],v=nv[j.uid])]
    expected=set(build_domain(j,b,r)[0]);n.Params.Threads=1;n.Params.PoolSearchMode=2;n.Params.PoolGap=0;n.Params.PoolSolutions=1000;n.optimize();assert n.Status==gp.GRB.OPTIMAL
    found=set()
    for i in range(n.SolCount):
        n.Params.SolutionNumber=i;d=reconstruct(new,data,pool=True)[j.uid];d['segments']=tuple(d['segments']);d['wan']=tuple(d['wan']);found.add(Option(**d))
    assert found==expected
    assert n.NumVars<m.NumVars
    m.dispose();n.dispose()

def test_f0_fixed_duration_projection_complete():
    j,b,r,_=fixture('D');m,units,data,*_=model({j.uid:j},{j.uid:b},r,'F2')
    n,nv,_=project(m,{j.uid:units[0]['v']},{'f0'});n.Params.PoolSearchMode=2;n.Params.PoolSolutions=100;n.Params.PoolGap=0;n.optimize();assert n.Status==gp.GRB.OPTIMAL
    found=[]
    for i in range(n.SolCount):
        n.Params.SolutionNumber=i;found.append(reconstruct([dict(units[0],v=nv[j.uid])],data,pool=True)[j.uid])
    assert len(found)==len(build_domain(j,b,r)[0]);assert n.NumBinVars<m.NumBinVars
    n.dispose();m.dispose()

def test_f0_cannot_be_silently_removed_for_migration():
    j,b,r,_=fixture('F');m,units,data,*_=model({j.uid:j},{j.uid:b},r,'F2')
    with pytest.raises(ValueError,match='NONMIGRATION'):project(m,{j.uid:units[0]['v']},{'f0'})
    m.dispose()

@pytest.mark.parametrize('family',['depart','arrive','link_bytes'])
def test_eliminated_routing_helpers_reproduce_exact_transfer(family):
    from v42_exact.factor import mapping
    j,b,r,_=fixture('F');j=replace(j,service_slots=4);b=replace(b,allowed_starts=(0,),latest_completion=14)
    o=next(x for x in build_domain(j,b,r)[0] if x.migrated)
    m,units,data,*_=model({j.uid:j},{j.uid:b},r,'F2A');v=units[0]['v'];a=mapping(j,data[5][j.uid],r,o)
    for name in ('y','q','f0','f1','pair','wan_start','wan_active','wan_final'):
        for key,x in v[name].items():m.addConstr(gp.LinExpr(x)==a.get(name,{}).get(key,0))
    m.optimize();assert m.Status==gp.GRB.OPTIMAL
    assert all(not isinstance(x,gp.Var) for x in v[family].values())
    assert all(abs(value(x)-a[family].get(key,0))<1e-5 for key,x in v[family].items())
    d=reconstruct(units,data)[j.uid];assert tuple(d['wan'])==o.wan
    m.dispose()

@pytest.mark.parametrize('kind',['F2B','F2C'])
def test_count_histogram_multiple_starts_and_whole_gangs(kind):
    j,b,r,_=fixture('D');j=replace(j,service_slots=2);b=replace(b,allowed_starts=(0,2),latest_completion=12);jobs={j.uid:j,'Z':replace(j,uid='Z')};bounds={u:b for u in jobs}
    m,units,data,*_=model(jobs,bounds,r,kind);stay=next(x for x in units if x['stay_count']);m.addConstr(stay['v']['y']['A',0]==1);m.addConstr(stay['v']['y']['B',2]==1);m.optimize();assert m.Status==gp.GRB.OPTIMAL
    selected=reconstruct(units,data);assert [selected[u]['start'] for u in sorted(selected)]==[0,2]
    assert m.NumIntVars-m.NumBinVars>0
    assert all(sum(z-a for k,a,z in o['segments'])==2 for o in selected.values())
    assert reconstruct(units,data)==selected;m.dispose()

@pytest.mark.parametrize('kind',['F2A','F2B','F2C'])
def test_structurally_deterministic_build(kind):
    j,b,r,_=fixture('F');jobs={j.uid:j,'Z':replace(j,uid='Z')};bounds={u:b for u in jobs};fingerprints=[]
    for i in range(2):
        m,*_=model(jobs,bounds,r,kind);m.update();fingerprints.append(m.Fingerprint);m.dispose()
    assert fingerprints[0]==fingerprints[1]

def test_service_count_averaging_is_not_individual_service():
    j,b,r,_=fixture('F');plans=[Option(0,'A',(('A',0,2),('B',4,7)),2,1800.,'B',2,3,4,(('AB',2,320),)),Option(0,'A',(('A',0,4),('B',6,9)),4,3600.,'B',4,5,6,(('AB',4,320),))]
    assert sum(z-a for o in plans for k,a,z in o.segments)==2*j.service_slots
    for o in plans:
        with pytest.raises(ValueError):validate(j,o,b,r)

def test_WAN_residual_min_cannot_be_aggregated_by_sum():
    assert min(2,5)+min(8,5)==7
    assert min(2+8,2*5)==10

def test_frozen_authorities_and_no_DW_import():
    import sys,hashlib
    d=json.loads((OUT/'LEGACY_PRESERVATION_AUDIT.json').read_text())
    from v42_voltage.preservation import assert_legacy
    assert_legacy(d['files'])
    assert not any(n=='v42_dw' or n.startswith('v42_dw.') for n in sys.modules)
