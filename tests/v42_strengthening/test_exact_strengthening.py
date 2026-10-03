from fractions import Fraction as F
from itertools import product
from collections import defaultdict
import hashlib
import subprocess
import numpy as np
import pytest
from v42_strengthening.common import ROOT,OUT,SOURCE,SCIENCE,REF,BASE,BASE_LB,UB_REF,read,sha,material
from v42_strengthening.cuts import bounded_A
from v42_strengthening.envelopes import dp,union,intersect,shifted,rational,outward
from v42_strengthening.prototype import fixture,native_pair
from v42_strengthening.flow import travel_lower,affine_add,affine_scale

def paths(arcs,origin='a',horizon=4):
    def visit(s,t,chosen):
        if t==horizon:
            yield chosen;return
        for k,(a,b,d,e,r) in enumerate(arcs):
            if (a,b)==(s,t):yield from visit(d,e,chosen+(k,))
    return list(visit(origin,0,()))

def test_exact_base_model_and_authority():
    r=read(OUT/'M1_STRENGTHENING_BASE_IDENTITY.json')
    assert r['PASS'] and r['base_exact_head']==BASE
    assert (r['rows'],r['columns'],r['binaries'],r['nnz'])==(886017,316743,208312,8447855)
    assert r['scientific_signature']==read(REF/'M1_PR135_MODEL_IDENTITY.json')['reference']
    assert r['A1_freeze_SHA']==sha(SCIENCE/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')
    assert r['NormalAmps_SHA']=='0cffff2af474221a7a5693f3c2b7a83026bd1522de2d3f66032c1757b9735d51'
    assert r['source_data_SHA']==sha(SOURCE/'DATA.pkl')
    assert r['voltage']==[.95,1.05] and r['margin']==0
    assert r['P1_P2_objective_SHA']==sha(SCIENCE/'M1_OBJECTIVE_CONTRACT.json')
    assert all(sha(p)==value for p,value in r['source_asset_SHAs'].items())

def test_baseline_solution_bound_and_census_complete():
    r=read(OUT/'BASELINE_ROOT_LP_RECEIPT.json')
    c=read(OUT/'M1_ROOT_FRACTIONAL_SUMMARY.json')
    assert r['PASS'] and r['baseline_new_optimize_calls']==0 and r['UB_certificate'] is None
    assert abs(r['primal_objective']-BASE_LB)<=1e-8
    with np.load(OUT/'BASELINE_ROOT_LP_SOLUTION.npz') as z:
        mask=(z['integer_types']!='C')&(z['values']>1e-6)&(z['values']<1-1e-6)
        assert int(mask.sum())==c['total_fractional_binaries']==138644
        assert len(z['values'])==316743
    assert sum(r['variable_count'] for r in c['families'])==208312
    assert c['max_site_count']==24 and c['split_slots']==377

def test_A_proof_exhaustive_continuous_domains(monkeypatch):
    import v42_strengthening.cuts as cuts
    monkeypatch.setattr(cuts,'write',lambda *a:None)
    r=bounded_A()
    assert r['PASS'] and r['max_cut_violation']=='0'
    assert r['binary_arc_assignments_examined']==1024
    assert r['primary_projection_exact_equality'] and r['objective_levels_identical']

def test_A_detects_simultaneous_split_power():
    r=read(OUT/'CUT_A_ROOT_VIOLATION_SUMMARY.json')
    assert r['violated_cut_count']==254
    assert r['by_cut']['A1']['violated_count']==r['by_cut']['A2']['violated_count']==0
    assert r['by_cut']['A3']['max_violation']>13
    assert read(OUT/'CUT_A_ROOT_RESULT.json')['selected'] is False

def test_envelope_DP_equals_all_complete_route_intervals():
    sites,initial,arcs,b,H,_=fixture()
    nodes,transit,_,_=dp(sites,'a',arcs,b,H)
    bounds=(rational(b.minimum),rational(b.maximum))
    ch=rational(b.dt_hours*b.eta_charge)*rational(b.p_limit)
    dis=rational(b.dt_hours/b.eta_discharge)*rational(b.p_limit)
    expected=defaultdict(list);expected_transit=defaultdict(list)
    for path in paths(arcs,horizon=H):
        forward=[[(rational(b.initial),rational(b.initial))]]
        for k in path:
            r=arcs[k][-1]
            forward.append(shifted(forward[-1],-dis,ch,bounds) if r is None else shifted(forward[-1],-rational(r.energy_kwh),-rational(r.energy_kwh),bounds))
        backward=[[] for _ in forward];backward[-1]=[(rational(b.terminal),rational(b.terminal))]
        for j in range(len(path)-1,-1,-1):
            r=arcs[path[j]][-1]
            backward[j]=shifted(backward[j+1],-ch,dis,bounds) if r is None else shifted(backward[j+1],rational(r.energy_kwh),rational(r.energy_kwh),bounds)
        for j,k in enumerate(path):
            s,t,d,e,r=arcs[k]
            reachable=intersect(forward[j],backward[j])
            expected[s,t]+=reachable
            if r is not None:
                cost=rational(r.energy_kwh)
                depart=intersect(reachable,[(bounds[0]+cost,bounds[1])])
                expected_transit[k]+=[(a-cost,c-cost) for a,c in depart]
        s,t,d,e,r=arcs[path[-1]]
        expected[d,e]+=intersect(forward[-1],backward[-1])
    for state,values in nodes.items():assert values==union(expected[state])
    for k,values in transit.items():assert values==union(expected_transit[k])

def test_envelopes_round_outward_and_keep_empty_domain():
    sites,initial,arcs,b,H,_=fixture()
    assert outward([],b)==(b.minimum,b.maximum)
    values=[(F(1,3),F(2,3))]
    lo,hi=outward(values,b)
    assert F.from_float(lo)<=F(1,3) and F.from_float(hi)>=F(2,3)
    assert travel_lower(440.,.1)<=F.from_float(440.)+F.from_float(.1)

def test_native_extended_rows_project_exactly_for_all_integer_paths_modes():
    from v42_integrated.matrix import arrays
    first,second=native_pair()
    try:
        A,d=arrays(first);B,e=arrays(second)
        sites,initial,arcs,b,H,_=fixture()
        names=list(map(str,d['names']));index={n:i for i,n in enumerate(names)}
        base_energy_rows=[]
        for t in range(H):
            matches=[i for i,n in enumerate(d['row_names']) if n=='energy_balance' and A[i,index[f'SOC[unit,{t+1}]']]==1]
            assert len(matches)==1;base_energy_rows.append(matches[0])
        assert np.array_equal(d['objective'],e['objective'][:len(names)])
        assert all(e['objective'][len(names):]==0) and all(e['types'][len(names):]=='C')
        assert B[:A.shape[0],A.shape[1]:].nnz==0
        checked=0
        for path in paths(arcs,horizon=H):
            selected=set(path)
            for modes in product((0,1),repeat=H):
                val={n:{} for n in map(str,e['names'])}
                for k in range(len(arcs)):
                    n=f'arc[unit,{k}]'
                    if n in val:val[n]={'constant':F(int(k in selected))} if k in selected else {}
                val['SOC[unit,0]']={'constant':rational(b.initial)}
                for t,mode in enumerate(modes):
                    val[f'charge_mode[unit,{t}]']={'constant':F(mode)} if mode else {}
                    for s in sites:
                        connected=any(arcs[k][:2]==(s,t) and arcs[k][-1] is None for k in path)
                        for family,allowed in [('Pch',mode),('Pdis',1-mode)]:
                            n=f'{family}[unit,{s},{t}]'
                            if n in val and connected and allowed:val[n]={'power_'+str(t):F(1)}
                    row=A.getrow(base_energy_rows[t])
                    E=val[f'SOC[unit,{t}]']
                    for j,coefficient in zip(row.indices,row.data):
                        n=names[j]
                        if not n.startswith('SOC['):E=affine_add(E,affine_scale(val[n],-rational(coefficient)))
                    val[f'SOC[unit,{t+1}]']=E
                for n in map(str,e['names'][len(names):]):
                    u,k=n.split('[',1)[1][:-1].split(',');k=int(k)
                    val[n]=val[f'SOC[unit,{arcs[k][1]}]'] if k in selected else {}
                for i in range(A.shape[0],B.shape[0]):
                    row=B.getrow(i)
                    residual=affine_add(*(affine_scale(val[str(e['names'][j])],rational(c)) for j,c in zip(row.indices,row.data)),{'constant':-rational(e['rhs'][i])})
                    if e['sense'][i]=='=':assert residual=={},(path,modes,str(e['row_names'][i]),residual)
                    # Bounds, after substitution, are source SOC bounds, or
                    # outward-safe travel lower bounds. Off-path = 0 exactly.
                    else:
                        name=str(e['row_names'][i]);k=int(name.rsplit(',',1)[1][:-1])
                        if k not in selected:assert residual=={}
                        elif name.startswith('flow_travel_energy_min'):
                            coefficient=float(row[0,index[f'arc[unit,{k}]']])
                            assert -F.from_float(coefficient)<=rational(b.minimum)+rational(arcs[k][-1].energy_kwh)
                    checked+=1
        assert checked>100
        assert first.NumBinVars==second.NumBinVars
    finally:first.dispose();second.dispose()

def test_matrix_growth_gate_fixed_before_solve():
    r=read(OUT/'SOC_FLOW_MATRIX_GROWTH.json')
    assert r['PASS']
    assert r['preregistered_thresholds']['max_total_nnz_ratio']==2
    assert r['added_binaries']==0 and r['added_continuous_variables']==207928
    result=read(OUT/'SOC_FLOW_FULL_ROOT_RESULT.json')
    assert result['matrix_growth']['added_nnz']<=r['estimated_added_nnz_upper_bound']

def test_selected_LB_material_gate_and_canary_policy():
    selected=read(OUT/'M1_STRENGTHENING_SELECTION.json')
    assert selected['selected_root_LB']>=BASE_LB
    assert selected['canary_authorized']==material(selected['selected_root_LB'])['material']
    assert selected['ineffective_candidates_adopted'] is False
    r=read(OUT/'M1_STRENGTHENED_MIP_CANARY.json')
    assert r['optimization_calls']<=1
    assert r['old_UB_reference_used_as_certificate'] is False
    if r['status']=='NOT_RUN':assert not selected['material_improvement']
    else:
        old=read(REF/'M1_CUTPASSES1_SOLVE_RESULT.json')['settings']
        assert r['settings']==dict(old,TimeLimit=600)

def test_campaign_order_firewall_four_loops_and_no_execution():
    from v42_campaign.plan import build_plan
    plan=read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json')
    assert build_plan()==plan and len(plan['nodes'])==1458
    assert plan['main_order']==['B0','B1','B2','B3_L1']
    assert plan['convergence_order']==['B3_L2','B3_L3','B3_L4']
    assert all(n['execution_status']=='NOT_RUN' for n in plan['nodes'])
    for node in plan['nodes']:
        if node['planning']:
            assert node['Actual_values_allowed'] is False
            assert not any('/ACTUAL' in p or '/FRESH_AC' in p for p in node['Planning_dependencies'])
    changed=subprocess.check_output(['git','diff','--name-only',BASE,'--','v42_campaign','v42_cutpass','v42_degen','v42_native','v42_integrated','docs/v42_m1_cutpass_loop_campaign'],cwd=ROOT).decode()
    assert changed==''

@pytest.mark.parametrize('candidate',['CUT_A_ROOT_RESULT.json','STRENGTHENING_B_ROOT_RESULT.json','SOC_FLOW_FULL_ROOT_RESULT.json'])
def test_no_original_model_change_or_new_binary(candidate):
    result=read(OUT/candidate)
    assert result['model_base_preserved']
    assert result['matrix_growth']['added_binaries']==0
    assert result['optimization_calls']==1
    assert result['settings']==read(SCIENCE/'ROOT_LP_reduced.json')['settings']
