from v42_dw_root.common import *
import csv,hashlib
import numpy as np
import pytest
from scipy import sparse
from fractions import Fraction as F
from v42_degen.identity import inputs,signature,digest
from v42_integrated.matrix import audit
from v42_dw_root.partition import axes
from v42_dw_root.models import hash_column
from v42_dw_root.run import no_negative

@pytest.fixture(scope='module')
def data():
    A,d,B,e,i,freeze=inputs();owner,rows=axes();return A,d,B,e,i,freeze,owner,rows
@pytest.fixture(scope='module')
def ledgers():
    result={}
    for name in ('DW_PRICING_RUN_LEDGER','DW_COLUMN_VALIDATION_LEDGER','DW_COLUMN_HASH_LEDGER','DW_RMP_ITERATION_LEDGER'):
        with (OUT/(name+'.csv')).open(encoding='utf8',newline='') as f:result[name]=list(csv.DictReader(f))
    return result
def test_pr139_scientific_identity(data):
    _,_,B,e,*_=data;r=read(OUT/'DW_BASE_MODEL_IDENTITY.json')
    assert r['PASS'] and r['base_exact_head']==BASE and signature(B,e)==r['reference']==r['current']
    assert (B.shape[0],B.shape[1],int((e['types']=='B').sum()),B.nnz)==(886017,316743,208312,8447855)
def test_a1_freeze_unchanged():
    assert sha(SCIENCE/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')==read(OUT/'DW_BASE_MODEL_IDENTITY.json')['A1_freeze_SHA']
def test_zero_margin_unchanged():
    r=read(OUT/'DW_BASE_MODEL_IDENTITY.json');assert r['margin']==0 and r['voltage']==[.95,1.05]
def test_normalamps_unchanged():
    from v42_thermal.authority import current_authority
    assert current_authority()['transformer_current_authority_sha256']==read(OUT/'DW_BASE_MODEL_IDENTITY.json')['NormalAmps_SHA']
def test_p1_p2_contract_unchanged():
    assert sha(SCIENCE/'M1_OBJECTIVE_CONTRACT.json')==read(OUT/'DW_BASE_MODEL_IDENTITY.json')['P1_P2_objective_SHA']
def test_actual_block_reassembly(data):
    _,_,B,e,_,_,owner,row_owner=data;chunks=[]
    for m in range(4):
        rr=np.flatnonzero(row_owner==m);cc=np.flatnonzero(owner==m);block=B[rr][:,cc].tocoo()
        chunks.append((rr[block.row],cc[block.col],block.data))
    rr=np.flatnonzero(row_owner<0)
    for m in (-1,0,1,2,3):
        cc=np.flatnonzero(owner==m);block=B[rr][:,cc].tocoo();chunks.append((rr[block.row],cc[block.col],block.data))
    restored=sparse.coo_matrix((np.concatenate([c[2] for c in chunks]),(np.concatenate([c[0] for c in chunks]),np.concatenate([c[1] for c in chunks]))),shape=B.shape).tocsr()
    assert np.array_equal(restored.indptr,B.indptr) and np.array_equal(restored.indices,B.indices) and np.array_equal(restored.data,B.data)
    assert restored.nnz==B.nnz
    for i,m in enumerate(row_owner):
        if m>=0:assert np.all(owner[B.indices[B.indptr[i]:B.indptr[i+1]]]==m)
def test_every_added_trajectory_all_original_local_rows(data,ledgers):
    _,_,B,e,_,_,owner,row_owner=data
    for r in ledgers['DW_COLUMN_VALIDATION_LEDGER']:
        if r['added']!='True':continue
        m=UNITS.index(r['MESS']);rr=np.flatnonzero(row_owner==m);cc=np.flatnonzero(owner==m)
        with np.load(OUT/r['file']) as z:x=z['local_values'];assert np.array_equal(z['original_columns'],cc)
        d=dict(e,rhs=e['rhs'][rr],sense=e['sense'][rr],lower=e['lower'][cc],upper=e['upper'][cc],types=e['types'][cc],objective=e['objective'][cc],constant=np.array(0.))
        assert audit(B[rr][:,cc],d,x,integral=True,tolerance=1e-8)['PASS']
        assert np.array_equal(x[d['types']!='C'],np.rint(x[d['types']!='C']))
def test_every_master_column_actual_matrix_product(data,ledgers):
    _,_,B,e,_,_,owner,row_owner=data;rr=np.flatnonzero(row_owner<0)
    for r in ledgers['DW_COLUMN_VALIDATION_LEDGER']:
        m=UNITS.index(r['MESS']);cc=np.flatnonzero(owner==m)
        with np.load(OUT/r['file']) as z:
            x=z['local_values'];a=z['master_coefficients'];assert np.array_equal(B[rr][:,cc]@x,a)
            for i,n,d in zip(z['exact_rows'],z['exact_numerators'],z['exact_denominators']):assert abs(F(int(n),int(d))-F(float(a[i])))<=F(1e-12)
    assert read(OUT/'DW_INITIAL_RMP_REPRODUCTION.json')['PASS']
def test_reduced_cost_sign_fixture():
    r=read(OUT/'DW_REDUCED_COST_SIGN_PROOF.json');assert r['PASS'] and abs(r['manual_reduced_cost']-r['solver_reported_RC'])<=1e-10
    assert r['after_candidate']<r['initial_objective'] and r['manual_reduced_cost']<-1e-7
def test_pricing_full_original_local_domain(data):
    _,_,B,e,_,_,owner,row_owner=data;r=read(OUT/'DW_PRICING_MODEL_CENSUS.json')
    for m,b in enumerate(r['blocks']):
        rr=np.flatnonzero(row_owner==m);cc=np.flatnonzero(owner==m)
        assert (b['rows'],b['columns'],b['binaries'],b['nnz'])==(len(rr),len(cc),int((e['types'][cc]=='B').sum()),B[rr][:,cc].nnz)
        assert b['full_original_domain'] and b['horizon']==96 and b['pricing_cost_exact_sign_changes']
def test_no_topk_pool_hamming_site_time_pruning():
    r=read(OUT/'DW_EXACTNESS_CONTRACT.json')
    assert all(r[k] is False for k in ('top_k_routes','route_pool_restriction','hamming_restriction','site_pruning','time_pruning','heuristic_pricing'))
def test_timeout_never_certifies_by_status(ledgers):
    assert not no_negative(None) and not no_negative(-1e-7) and no_negative(-1e-8)
    for r in ledgers['DW_PRICING_RUN_LEDGER']:
        if r['NO_NEGATIVE_COLUMN_CERTIFIED']=='True':assert r['global_BestBd'] and float(r['global_BestBd'])>=-1e-8
def test_valid_negative_column_allowed_without_optimal(ledgers):
    for r in ledgers['DW_COLUMN_VALIDATION_LEDGER']:
        if r['kind']=='NEGATIVE_PRICING' and r['added']=='True':assert r['PASS']=='True' and float(r['reduced_cost'])<=-1e-7
    # The acceptance rule intentionally requires a validated point, not status 2.
    assert read(OUT/'DW_EXECUTION_PREREGISTRATION.json')['early_negative_stop_allowed']
def test_termination_all_four_same_dual(ledgers):
    r=read(OUT/'DW_ROOT_RESULT.json');cert=read(OUT/'DW_ROOT_CERTIFICATE.json')
    if r['DW_ROOT_OPTIMAL_CERTIFIED']:
        assert all(r['final_pricing_certificates'].values()) and cert['PASS']
        key=cert['same_RMP_dual_SHA']
        certified={row['MESS'] for row in ledgers['DW_PRICING_RUN_LEDGER'] if row['dual_SHA']==key and row['NO_NEGATIVE_COLUMN_CERTIFIED']=='True'}
        assert certified==set(UNITS)
    else:assert r['DW_root_LB'] is None and cert['L_DW'] is None
def test_bounded_full_enumeration_integer_equivalence():
    r=read(OUT/'DW_BOUNDED_EXACT_EQUIVALENCE.json');assert r['PASS'] and r['all_legal_fixture_routes_enumerated']
    assert all(f['integer_equivalence_PASS'] for f in r['fixtures'])
    feasible=r['fixtures'][0];assert feasible['original_integer_objective']==feasible['DW_integer_objective']==.5 and feasible['route_PQ_SOC_equal']
    infeasible=r['fixtures'][1];assert infeasible['original_status']==infeasible['DW_integer_status']==3
def test_dw_fixture_LP_ge_arc_LP():
    for f in read(OUT/'DW_BOUNDED_EXACT_EQUIVALENCE.json')['fixtures']:
        if f['original_status']==2:assert f['DW_LP']>=f['arc_LP']-1e-9
def test_column_hash_exact_no_aging_deletion(ledgers):
    added=0
    for r in ledgers['DW_COLUMN_HASH_LEDGER']:
        with np.load(OUT/r['file']) as z:
            x=z['local_values'];a=z['master_coefficients'];c=float(z['objective'])
            assert hash_column(x,a,c)==r['SHA256'] and hashlib.sha256(x.tobytes()).hexdigest()==r['local_vector_SHA']
        added+=r['added']=='True'
    assert added==read(OUT/'DW_ROOT_RESULT.json')['final_trajectory_columns']
    assert hash_column(np.array([0.]),np.array([1.]),0.)!=hash_column(np.array([-0.]),np.array([1.]),0.)
def test_campaign_orchestrator_unchanged():
    from v42_campaign.plan import build_plan
    assert read(REF/'MAY_CAMPAIGN_DRY_RUN_PLAN.json')==build_plan() and len(build_plan()['nodes'])==1458
def test_actual_firewall_unchanged():
    r=read(OUT/'CAMPAIGN_ORCHESTRATOR_PRESERVATION.json');assert r['Actual_feedback_firewall_preserved'] and r['previous_Planning_only']
def test_B3_four_loop_unchanged():
    r=read(OUT/'CAMPAIGN_ORCHESTRATOR_PRESERVATION.json');assert r['B3_four_loop_contract_preserved'] and not r['B0_B1_B2_repeated'] and not r['fixed_point_early_stop']
def test_production_calls_zero():
    r=read(OUT/'DW_ROOT_RESULT.json');assert r['campaign_optimizer_calls']==r['campaign_Actual_calls']==r['campaign_Fresh_AC_calls']==0
    assert not r['branch_and_price_run'] and not r['P2_RUN'] and r['A2']==r['M2']=='NOT_RUN'
def test_single_worker_and_wall_budget(ledgers):
    r=read(OUT/'DW_ROOT_RESULT.json');assert r['wall_budget_PASS'] and r['Gurobi_Threads']==1 and r['sequential_heavy_workers']==1
    assert all(float(p['runtime'])<=601 for p in ledgers['DW_PRICING_RUN_LEDGER'])
    assert all(os.environ[k]=='1' for k in ENV)
