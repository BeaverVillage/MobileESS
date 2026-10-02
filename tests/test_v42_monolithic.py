import numpy as np
import pytest
import gurobipy as gp
from v42_monolithic.fixtures import make,paths,run,CASES
from v42_monolithic.formulation import Compact
from v42_monolithic.common import read,OUT,LB,UB,preserve
from v42_monolithic.prepare import SETTINGS

@pytest.fixture
def models():
    with gp.Env(params={'OutputFlag':0}) as env:
        o,g,x=make(env,'immediate_post_connect');c=Compact(o,g,{'M':'A'},4);n=c.build(env);n.Params.OutputFlag=0
        yield o,g,x,c,n
        o.dispose();n.dispose()

def test_initial_state(models):
    o,g,x,c,n=models;p=c.z['M','A',0];assert c.lower[p]==c.upper[p]==1
def test_occupancy_and_immediate_departure(models):
    o,g,x,c,n=models;path=next(p for p in paths(g,x) if len([k for k in p if g[k][-1]])==2)
    v=np.zeros(o.NumVars)
    for k in path:v[x[k].index]=1
    y=c.forward(v);assert y[c.z['M','B',2]]==1 and c.connected(y,'M','B',2)==0
    assert np.array_equal(c.inverse(y),v)
def test_bidirectional_stay_mapping(models):
    o,g,x,c,n=models;o.Params.OutputFlag=0;o.optimize();v=np.array(o.getAttr('X'));y=c.forward(v)
    assert np.max(abs(c.inverse(y)-v))<1e-12
    for key,j in c.stays.items():assert abs(c.connected(y,*key)-v[j])<1e-12
def test_no_route_lost(models):
    o,g,x,c,n=models;assert set(c.movement_columns)=={('M',k) for k in x if g[k][-1] is not None}
def test_travel_energy_timing(models):
    o,g,x,c,n=models
    for k,a in enumerate(g):
        if a[-1] is None or k not in x:continue
        row=o.getConstrByName(f'energy_balance_{a[1]}').index
        assert o.getA()[row,x[k].index]==a[-1].energy_kwh
def test_charge_mode_pq_soc_identity(models):
    o,g,x,c,n=models
    for j,name in enumerate(c.old_names):
        if str(name).startswith(('charge_mode[','Pch[','Pdis[','Q[','SOC[')):
            p=c.position[j];assert c.T[j,p]==1 and c.types[p]==c.old_types[j] and c.lower[p]==c.old_lb[j] and c.upper[p]==c.old_ub[j]
def test_all_pcs16_and_grid_rows_preserved(models):
    o,g,x,c,n=models
    assert (c.A!=c.oldA@c.T).nnz==0
    assert np.array_equal(n.getAttr('RHS')[:o.NumConstrs],o.getAttr('RHS'))
    assert sum(k.ConstrName=='PCS16' for k in o.getConstrs())==16*len(c.stays)
def test_terminal_soc_preserved(models):
    o,g,x,c,n=models;row=o.getConstrByName('terminal_SOC').index
    assert np.array_equal(c.A[row].data,c.oldA[row].data) and c.old_b[row]==1
@pytest.mark.parametrize('case',['parallel_identical','parallel_distinct'])
def test_parallel_selectors(case):
    with gp.Env(params={'OutputFlag':0}) as env:
        o,g,x=make(env,case);c=Compact(o,g,{'M':'A'},4)
        assert len(c.selectors)==2 and all(c.types[p]=='B' for p in c.selectors)
        assert len(c.movement_columns)==2;o.dispose()
def test_lp_projection(models):
    o,g,x,c,n=models;a=o.relax();b=n.relax();a.Params.OutputFlag=b.Params.OutputFlag=0;a.optimize();b.optimize()
    assert abs(a.ObjVal-b.ObjVal)<=1e-8 and c.residual(c.forward(np.array(a.getAttr('X'))))<=1e-8
    assert c.residual(np.array(b.getAttr('X')))<=1e-8;a.dispose();b.dispose()
def test_exhaustive_fixtures_and_integrality():
    with gp.Env(params={'OutputFlag':0}) as env:r=run(env,write=False)
    assert r['PASS'] and r['fixtures']==12 and r['path_comparisons']==31 and r['fractionality_infeasibility_probes']==19
def test_no_heuristic_and_fixed_lane_policy():
    p=read('PREREGISTRATION.json');assert SETTINGS['Heuristics']==0 and not p['pruning'] and not p['route_pool'] and not p['trajectory_limit']
    assert p['order']==['ROOT_ORIGINAL','ROOT_COMPACT','C0_ORIGINAL','C1_COMPACT']
def test_p2_a2_m2_contract_and_no_production():
    p=read('PREREGISTRATION.json');assert p['P2_NOT_RUN'] and p['A2_NOT_RUN'] and p['M2_NOT_RUN'] and not p['M1_ACCEPTED'] and not p['production_1800_run']
    assert 'movement energy then movement count' in p['P2_contract']
def test_no_benders_new_experiment():
    p=read('PREREGISTRATION.json');assert all(p[k]==0 for k in ['Benders_master','Benders_recourse','Farkas_cuts','Phase_I'])
def test_base_bytes_preserved():assert preserve()==2365
def test_full_census_and_mapping_when_prepared():
    if not (OUT/'FULL_DOMAIN_CENSUS.json').exists():pytest.skip('Full build not completed')
    f=read('FULL_DOMAIN_CENSUS.json');b=read('BINARY_REDUCTION_REPORT.json');s=read('MIP_START_MAPPING.json')
    assert f['PASS'] and f['route_binaries']==207928 and f['original']['binary']==208312
    assert f['compact']['binary']==f['node_activity_binaries']+f['parallel_selector_binaries']+384
    assert f['continuous_movement_flows']+f['parallel_selector_binaries']+f['removed_stay_binaries']==f['route_binaries']
    assert b['PASS'] and b['binary_reduction_percent']>=80 and s['PASS'] and abs(s['compact_objective']-UB)<=1e-12
    assert read('MIP_START_PHYSICAL_VALIDATION.json')['PASS']
