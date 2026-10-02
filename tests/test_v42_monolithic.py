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

def test_non_dag_is_rejected_before_build(models):
    o,g,x,c,n=models;bad=list(g);a=bad[-1];bad[-1]=(a[0],a[1],a[2],a[1],a[4])
    with pytest.raises(AssertionError,match='NOT_DAG_TIME_ORDER'):Compact(o,bad,{'M':'A'},4)

@pytest.mark.parametrize('primary_pass,both_optimal',[(True,False),(False,True)])
def test_root_fallback_cannot_bypass_pass_or_optimal_mismatch(monkeypatch,primary_pass,both_optimal):
    import v42_monolithic.secondary_roots as s
    from pathlib import Path
    p=dict(source_sha256=s.sha(Path(s.__file__)),policy=s.POLICY)
    responses={'ROOT_LP_SECONDARY_PREREGISTRATION.json':p,'ROOT_LP_ORIGINAL.json':dict(terminal_optimal=both_optimal),
        'ROOT_LP_COMPACT.json':dict(terminal_optimal=both_optimal),'ROOT_LP_EQUIVALENCE.json':dict(PASS=primary_pass)}
    monkeypatch.setattr(s,'read',lambda name:responses[name])
    monkeypatch.setattr(s,'one',lambda *args:pytest.fail('Fallback must not start any solve'))
    with pytest.raises(AssertionError,match='PRIMARY_PASSED|PRIMARY_OPTIMAL_MISMATCH'):s.run()

def test_source_network_and_p2_authority_receipts():
    if not (OUT/'ORIGINAL_NATIVE_NETWORK_AUDIT.json').exists():pytest.skip('Read-only native audit not completed')
    n=read('ORIGINAL_NATIVE_NETWORK_AUDIT.json');p=read('P2_OBJECTIVE_CONTRACT.json')
    assert n['PASS'] and n['audited_flow_and_terminal_rows']==9220 and n['audited_SOC_recurrence_rows']==384
    assert n['route_energy_coefficient_max_absolute_error']==0 and n['movement_endpoint']=='connect' and n['travel_debit_time']=='depart'
    assert p['PASS'] and p['P2_status']=='NOT_RUN' and p['P2_optimize_calls']==0
    assert p['lexicographic_movement_contract']==['movement_energy_kwh','movement_count']
    assert all(p['vectors'][key]['compact_nonzero_coefficients']==198986 for key in ['movement_energy_kwh','movement_count'])

def test_feasible_immediate_departure_and_three_move_physics():
    from v42_monolithic.sequence_fixtures import run as extra
    result=extra(write=False)
    assert result['PASS'] and {r['movement_count'] for r in result['extra_fixtures']}=={2,3}

def test_final_flags_prevent_hidden_downstream_or_production():
    if not (OUT/'FINAL_FLAGS.json').exists():pytest.skip('Final evidence not yet written')
    flags=read('FINAL_FLAGS.json');authorization=read('COMPACT_M1_PRODUCTION_AUTHORIZATION.json')
    assert not flags['M1_ACCEPTED'] and not flags['Problem13_FINAL'] and not flags['production_1800_run']
    assert all(flags[k]=='NOT_RUN' for k in ['P2','A2','M2','Actual','Fresh_AC'])
    assert all(flags[k]==0 for k in ['Benders_master','Benders_recourse','Farkas_cuts','Phase_I'])
    assert not authorization['production_1800_executed']
    if authorization['COMPACT_M1_PRODUCTION_AUTHORIZED']:
        assert flags['EXACTNESS_PASS'] and read('CANARY_COMPARISON.json')['promising']

def test_final_root_and_canary_gate_correspondence():
    if not (OUT/'FINAL_FLAGS.json').exists():pytest.skip('Final evidence not yet written')
    root=read('ROOT_LP_EQUIVALENCE.json')
    if root['PASS']:
        a=read(root.get('selected_original_artifact','ROOT_LP_ORIGINAL.json'));b=read(root.get('selected_compact_artifact','ROOT_LP_COMPACT.json'))
        assert a['terminal_optimal'] and b['terminal_optimal'] and abs(a['objective']-b['objective'])<=1e-8
        assert a['settings']==b['settings'] and root['original_to_compact']['PASS'] and root['compact_to_original']['PASS']
        for name in ['CANARY_ORIGINAL_600S.json','CANARY_COMPACT_600S.json']:
            c=read(name);assert c['settings']['Heuristics']==0 and c['settings']['Threads']==4 and c['settings']['TimeLimit']==600
    else:
        assert read('CANARY_ORIGINAL_600S.json')['status']=='NOT_RUN' and read('CANARY_COMPACT_600S.json')['status']=='NOT_RUN'

def test_contradictory_bound_cannot_create_negative_gap_acceptance():
    from v42_monolithic.certificates import interval
    rejected=interval(UB+.01,UB)
    assert not rejected['PASS'] and not rejected['solver_bound_used'] and rejected['valid_retained_LB']==LB
    assert rejected['valid_global_gap']>0
    accepted=interval(UB-.001,UB)
    assert accepted['PASS'] and accepted['solver_bound_used'] and accepted['valid_global_gap']<.005
