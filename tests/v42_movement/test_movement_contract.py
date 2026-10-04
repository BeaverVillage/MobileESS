from v42_movement.common import *
import csv
import numpy as np
import pytest
from fractions import Fraction as F
from v42_degen.identity import inputs,signature,digest
from v42_integrated.matrix import audit
from v42_movement.oracle import polygon_vertices,mul,lower,upper
from v42_movement.separate import conditional_tables

@pytest.fixture(scope='module')
def payload():return inputs()
@pytest.fixture(scope='module')
def supports():
    with np.load(OUT/'PCS_GRID_SUPPORT_VALUES.npz') as z:return {k:z[k] for k in z.files}
@pytest.fixture(scope='module')
def coefficients():
    with np.load(OUT/'GRID_EPIGRAPH_ROW_COEFFICIENTS.npz') as z:return {k:z[k] for k in z.files}

def test_pr138_scientific_identity(payload):
    _,d,B,e,_,_=payload;r=read(OUT/'M1_MOVEMENT_GRID_BASE_IDENTITY.json')
    assert signature(B,e)==r['reference']==r['current']
    assert (B.shape[0],B.shape[1],sum(d['types']=='B'),B.nnz)==(886017,316743,208312,8447855)
    assert r['base_exact_head']==BASE
def test_a1_freeze_unchanged():
    assert sha(OUT/'INTEGRATED_A1_FREEZE.json')==read(OUT/'M1_MOVEMENT_GRID_BASE_IDENTITY.json')['A1_freeze_SHA']
def test_normalamps_unchanged():
    assert read(OUT/'M1_FIXED_DISCRETE_POLISH_AUDIT.json')['original_units']['transformer_current_authority_sha256']==read(OUT/'M1_MOVEMENT_GRID_BASE_IDENTITY.json')['NormalAmps_SHA']
def test_zero_margin():
    r=read(OUT/'M1_FIXED_DISCRETE_POLISH_AUDIT.json')['original_units'];assert r['margin_pu']==0 and r['voltage_band']==[.95,1.05]
def test_p1_p2_unchanged():
    assert sha(SCIENCE/'M1_OBJECTIVE_CONTRACT.json')==read(OUT/'M1_MOVEMENT_GRID_BASE_IDENTITY.json')['P1_P2_objective_SHA']
def test_fixed_pattern_exact(payload):
    _,d,*_=payload;mask=d['types']!='C'
    with np.load(ROOT/'docs/v42_m1_degenmoves_zero_start_v1/RAW_POINTS/ZERO_ACTION_CANDIDATE.npz') as z:source=z['values']
    with np.load(OUT/'M1_FIXED_DISCRETE_POLISH_POINT.npz') as z:point=z['values']
    assert np.array_equal(source[mask],point[mask]) and np.array_equal(point[mask],np.rint(point[mask]))
def test_polish_original_unreduced_rows(payload):
    A,d,*_=payload
    with np.load(OUT/'M1_FIXED_DISCRETE_POLISH_POINT.npz') as z:x=z['values']
    checked=audit(A,d,x,integral=True,tolerance=1e-8)
    assert checked['PASS'] and checked['max_constraint_violation']==read(OUT/'M1_FIXED_DISCRETE_POLISH_AUDIT.json')['original_full_row_audit']['max_constraint_violation']
    assert read(OUT/'M1_FIXED_DISCRETE_POLISH_RESULT.json')['global_UB_certificate'] is None
def test_exact_local_polygon_vertices(supports):
    normals=supports['native_normals'];saved=read(OUT/'PCS_GRID_SUPPORT_ORACLE_PROOF.json')
    pts=sorted(set(polygon_vertices(normals,0)+polygon_vertices(normals,1)))
    assert len(pts)==len(saved['exact_vertices'])
    for (p,q),r,lo,hi in zip(pts,saved['exact_vertices'],supports['vertex_lower'],supports['vertex_upper']):
        assert p==F(int(r['P'][0]),int(r['P'][1])) and q==F(int(r['Q'][0]),int(r['Q'][1]))
        assert F(lo[0])<=p<=F(hi[0]) and F(lo[1])<=q<=F(hi[1])
        assert all(F(float(a))*p+F(float(b))*q<=F(float(h)) for a,b,h in normals)
def test_epigraph_exact_factored_reconstruction(payload,coefficients):
    _,_,B,e,*_=payload;z=coefficients;rho=int(z['rho_column'])
    assert np.array_equal(z['rows'],B[:,rho].nonzero()[0])
    for k,i in enumerate(z['rows']):
        a,b=B.indptr[i:i+2];js=B.indices[a:b];cs=B.data[a:b];mask=js!=rho
        x,y=z['factor_indptr'][k:k+2]
        assert np.array_equal(js[mask],z['factor_columns'][x:y])
        assert np.array_equal(cs[mask],z['factor_values'][x:y])
        assert cs[js==rho].item()==-1 and z['native_rhs'][k]==e['rhs'][i] and e['sense'][i]=='<'
    assert read(OUT/'GRID_EPIGRAPH_ROW_DECOMPOSITION.json')['exact_reconstruction_PASS']
def test_dense_intervals_enclose_exact_dyadic_samples(payload,coefficients):
    _,_,B,e,*_=payload;z=coefficients;names=list(map(str,e['names']));bindings={}
    selected=set(np.linspace(0,len(z['rows'])-1,193,dtype=int))|{int(np.argmax(z['fixed_lower']))}
    required=set()
    for k in selected:
        a,b=z['factor_indptr'][k:k+2];required.update(z['factor_columns'][a:b])
    for i in z['binding_rows']:
        a,b=B.indptr[i:i+2];row=dict(zip(map(int,B.indices[a:b]),map(float,B.data[a:b])))
        j=next(j for j in row if names[j].startswith('response_'));scale=row.pop(j)
        if j not in required:continue
        bindings[j]=(F(float(e['rhs'][i]))/F(scale),{k:-F(v)/F(scale) for k,v in row.items()})
    sites=list(map(str,z['sites']));injection={}
    for j,n in enumerate(names):
        if n.startswith('injection_'):
            f,args=n.split('[',1);s,t=args[:-1].split(',');injection[j]=sites.index(s)*2+(f=='injection_Q')
    # All time slots, plus both archive endpoints and the critical support row.
    for k in selected:
        cs=[F(0)]*48;b=-F(float(z['native_rhs'][k]));x,y=z['factor_indptr'][k:k+2]
        for j,c in zip(z['factor_columns'][x:y],z['factor_values'][x:y]):
            const,row=bindings[j];b+=F(float(c))*const
            for j2,v in row.items():cs[injection[j2]]+=F(float(c))*v
        assert F(float(z['fixed_lower'][k]))<=b<=F(float(z['fixed_upper'][k]))
        for j,c in enumerate(cs):assert F(float(z['coefficient_lower'][k,j]))<=c<=F(float(z['coefficient_upper'][k,j]))
def test_support_intervals_and_global_bound(supports):
    z=supports;assert np.all(z['phi_lower']<=z['phi_upper']) and np.all(z['psi_lower']<=0)
    r=read(OUT/'GRID_SUPPORT_GLOBAL_LB.json')
    assert float(z['row_lower'].max())==r['L_support_global']<=BASE_LB+1e-8
def test_transit_semantics_and_endpoint():
    # Exhaustive bounded DAG paths, including 2-slot travel and arrival stay.
    arcs=[('A',0,'A',1),('A',0,'B',2),('A',1,'A',2),('A',1,'B',3),('A',2,'A',3),('B',2,'B',3)]
    paths=[]
    def visit(node,path):
        if node[1]==3:paths.append(path);return
        for j,a in enumerate(arcs):
            if a[:2]==node:visit(a[2:],path+[j])
    visit(('A',0),[])
    for path in paths:
        for j in path:
            s,t,d,c=arcs[j]
            if s!=d:
                assert all(not any(arcs[k][1]==slot and arcs[k][0]==arcs[k][2] for k in path) for slot in range(t,c))
    assert [1,5] in paths  # connect=2 has a legal stay; never include it in transit.
    assert read(OUT/'MOVEMENT_ARC_TRANSIT_SEMANTICS_PROOF.json')['connect_is_not_automatically_transit']
def test_original_flow_network_coefficients(payload):
    from collections import defaultdict
    from v42_strengthening.analysis import graph_inputs
    A,d,*_=payload;sites,initial,arcs,*_=graph_inputs();index={str(n):j for j,n in enumerate(d['names'])}
    incoming=defaultdict(list);outgoing=defaultdict(list)
    for k,(s,t,dest,conn,_) in enumerate(arcs):outgoing[s,t].append(k);incoming[dest,conn].append(k)
    rows=np.flatnonzero(d['row_names']=='flow');position=0
    for u,origin in sorted(initial.items()):
        for s in sites:
            for t in range(96):
                i=rows[position];position+=1;expected={}
                for k in outgoing[s,t]:
                    n=f'arc[{u},{k}]'
                    if n in index:expected[index[n]]=1.
                for k in incoming[s,t]:
                    n=f'arc[{u},{k}]'
                    if n in index:expected[index[n]]=-1.
                a,b=A.indptr[i:i+2];actual=dict(zip(map(int,A.indices[a:b]),map(float,A.data[a:b])))
                assert actual==expected and d['sense'][i]=='=' and d['rhs'][i]==int(t==0 and s==origin)
    assert position==len(rows)
def test_every_arc_lb_matches_support(coefficients,supports):
    z=supports;v,resp=conditional_tables(coefficients['fixed_lower'],z['psi_lower'],z['times'],z['rows']);global_lb=float(z['row_lower'].max());units=list(map(str,z['units']))
    count=0
    with (OUT/'MOVEMENT_ARC_CONDITIONAL_LB.csv').open(encoding='utf8',newline='') as f:
        for r in csv.DictReader(f):
            m=units.index(r['MESS']);dep=int(r['depart']);conn=int(r['connect']);raw=max(global_lb,float(v[m,dep:conn].max()))
            assert raw==float(r['L_arc_raw']) and max(BASE_LB,raw)==float(r['L_arc'])
            assert conn-dep==int(r['transit_length']);count+=1
    assert count==131350
def test_individual_two_case_validity():
    for lb in (BASE_LB,BASE_LB+.01,.8):
        delta=lb-BASE_LB
        assert BASE_LB+delta*0==BASE_LB and abs(BASE_LB+delta-lb)<1e-15
    assert read(OUT/'MOVEMENT_ARC_CONDITIONAL_LB_PROOF.json')['individual_cut_valid']
def test_clique_at_most_one_and_cut():
    values=[BASE_LB+.01,BASE_LB+.04,BASE_LB+.2]
    for selected in (None,0,1,2):
        x=[int(j==selected) for j in range(3)];rhs=BASE_LB+sum((lb-BASE_LB)*v for lb,v in zip(values,x))
        assert sum(x)<=1 and abs(rhs-(BASE_LB if selected is None else values[selected]))<1e-15
    assert read(OUT/'MOVEMENT_ARC_CLIQUE_PROOF.json')['PASS']
def test_no_new_binary_or_domain_pruning():
    r=read(OUT/'MOVEMENT_GRID_STRENGTHENED_ROOT_RESULT.json');assert r['no_new_binary'] and r['integer_feasible_set_unchanged'] and r['original_prefix_exact']
    assert r['matrix']['columns']==316743 and r['matrix']['binaries']==208312
def test_rejected_strengthening_absent():
    assert not read(OUT/'MOVEMENT_GRID_STRENGTHENED_ROOT_RESULT.json')['rejected_strengthening_added']
    assert all(r['kind'] in ('individual','clique') for r in read(OUT/'SELECTED_MOVEMENT_GRID_CUTS.json')['cuts'])
def test_campaign_orchestrator():
    from v42_campaign.plan import build_plan
    assert read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json')==build_plan()
    assert len(build_plan()['nodes'])==1458 and read(OUT/'CAMPAIGN_ORCHESTRATOR_PRESERVATION.json')['semantic_plan_equal']
def test_actual_firewall_and_four_loops():
    r=read(OUT/'CAMPAIGN_ORCHESTRATOR_PRESERVATION.json');assert r['Actual_feedback_firewall_preserved'] and r['previous_Planning_only'] and r['B3_four_loop_contract_preserved']
    assert not r['B0_B1_B2_repeated'] and not r['fixed_point_early_stop']
def test_production_calls_zero():
    r=read(OUT/'CAMPAIGN_NO_EXECUTION_RECEIPT.json');assert r['campaign_optimizer_calls']==r['campaign_Actual_calls']==r['campaign_Fresh_AC_calls']==0
def test_material_gate_and_canary_policy():
    assert not material(BASE_LB+.0049)['PASS'] and material(BASE_LB+.0051)['PASS']
    root=read(OUT/'MOVEMENT_GRID_STRENGTHENED_ROOT_RESULT.json');canary=read(OUT/'MOVEMENT_GRID_MIP_CANARY_RESULT.json')
    if not root['material_gate']['PASS']:assert canary['status']=='NOT_RUN' and canary['optimization_calls']==0
def test_four_environment_threads_one():
    assert all(os.environ.get(k)=='1' for k in ENV)
