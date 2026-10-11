import hashlib,json,math,re,time
from collections import Counter
from fractions import Fraction as F
from pathlib import Path
import numpy as np
from scipy import sparse

root=Path(__file__).resolve().parents[2]
out=root/'docs/v42_joint_critical_grid_lb_pilot'
previous=root/'docs/v42_physical_global_lb_pilot'
started=time.perf_counter()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
native0=read(out/'NATIVE0.json')
for name in ('JOINT_A.npz','JOINT_DATA.npz','K16_EXACT_ROWS.json'):
    assert sha(out/name)==native0['files'][name],name
A=sparse.load_npz(out/'JOINT_A.npz')
z=np.load(out/'JOINT_DATA.npz');d={k:z[k] for k in z.files}
k16=read(out/'K16_EXACT_ROWS.json')
p=k16['physicalrowcount']
names=d['names'];unitnames=('MESS01','MESS02','MESS03','MESS04')
owner=np.array([unitnames.index(str(n).split('[',1)[1].split(',',1)[0]) if str(n)!='rho_max' else 4 for n in names],dtype=np.int8)
physical=A[:p]
entryowner=owner[physical.indices]
minimum=np.minimum.reduceat(entryowner,physical.indptr[:-1]);maximum=np.maximum.reduceat(entryowner,physical.indptr[:-1])
assert np.all(minimum==maximum) and np.all(minimum<4)
rowowner=minimum
counts=[]
for m,unit in enumerate(unitnames):
    rows=np.flatnonzero(rowowner==m);columns=np.flatnonzero(owner==m)
    counts.append(dict(unit=unit,physical_rows=len(rows),physical_columns=len(columns),binaries=int(np.count_nonzero(d['vtypes'][columns]=='B')),
        physical_nnz=int(np.sum(np.diff(physical.indptr)[rows])),
        physical_row_families=dict(Counter(str(n).split('[',1)[0] for n in d['row_names'][rows])),
        physical_column_families=dict(Counter(str(n).split('[',1)[0] for n in names[columns])),
        K16_rows_touching_vehicle=16,K16_PQ_terms_per_row=72))
old=read(previous/'WEIGHTS.json');grid=read(previous/'GRID_PROVENANCE_AUDIT.json')
assert grid['PASS'] and len(grid['selected_rows'])==len(k16['rows'])==len(old['rows'])==16
rowtable=[];weighted_max_loss=F(0);weighted_min_loss=F(0);magnitude=[]
for k,(record,wr,provenance) in enumerate(zip(k16['rows'],old['rows'],grid['selected_rows'])):
    assert record['name']==wr['name']==provenance['name']
    assert record['original_row']==wr['row']==provenance['row']
    b=F(record['b']);rhs=F(record['native_rhs']);upper_error=F(0);max_loss=b+rhs;min_loss=b+rhs
    a,bptr=A.indptr[p+k:p+k+2]
    actual=dict(zip(map(int,A.indices[a:bptr]),map(float,A.data[a:bptr])))
    for j,exact in record['terms'].items():
        j=int(j);coefficient=F(exact);native=F(actual[j]);lo=F(float(d['lb'][j]));hi=F(float(d['ub'][j]));delta=native-coefficient
        assert actual[j]==float(coefficient) and actual[j]!=0
        upper_error+=max(delta*lo,delta*hi)
        max_loss+=max(-delta*lo,-delta*hi);min_loss+=min(-delta*lo,-delta*hi)
        magnitude.append(abs(float(native)))
    assert upper_error==F(record['error_upper_bound']) and rhs>=-b+upper_error
    assert min_loss==F(record['rhs_outward_extra'])>=0 and max_loss>=min_loss
    weight=F(wr['weight']);weighted_max_loss+=weight*max_loss;weighted_min_loss+=weight*min_loss
    rowtable.append(dict(original_row=wr['row'],name=wr['name'],slot=provenance['slot'],
        interval_from_midnight_minutes=provenance['interval_from_midnight_minutes'],
        branch_index=provenance['branch_index'],branch_name=provenance['branch_name'],facet=provenance['facet'],
        angle_degrees=provenance['angle_degrees'],comparison_weight=str(weight),
        original_rho_coefficient=wr['original_rho_coefficient'],original_RHS=wr['original_RHS'],
        exact_fixed_term=wr['b'],fixed_term_float=float(F(wr['b'])),U4_thermal_value=wr['U4_thermal_value'],
        physical_terms=len(record['terms']),native_rhs=record['native_rhs'],
        native_face_loss_min_exact=str(min_loss),native_face_loss_max_exact=str(max_loss),
        native_face_loss_max_float=float(max_loss)))
assert sum(F(row['weight']) for row in old['rows'])==1
assert sum(r['physical_rows'] for r in counts)==p and sum(r['physical_columns'] for r in counts)+1==A.shape[1]
assert sum(r['physical_nnz'] for r in counts)+sum(len(r['terms'])+1 for r in k16['rows'])==A.nnz
eps=float(weighted_max_loss)
if F(eps)<weighted_max_loss: eps=float(np.nextafter(eps,np.inf))
facts=dict(schema='V42_JOINT_MODEL_REPORT_FACTS_V1',PASS=True,source='FROZEN_JOINT_ARRAYS_AND_PR209_SAVED_METADATA_ONLY',
    model_unchanged=True,Native_optimize_calls=0,FULL_or_C3A_matrices_loaded=False,
    source18r=native0['source'],PR209_parent=native0['parent'],case_sha=native0['case_sha'],
    original_matrix_sha=native0['original_matrix_sha'],original_domain_sha=native0['original_domain_sha'],
    Source18r_C3A_matrix_sha=native0['selected_matrix_sha'],Source18r_C3A_domain_sha=native0['selected_domain_sha'],
    frozen_Joint_matrix_sha=native0['matrix_sha'],frozen_input_file_sha256={name:native0['files'][name] for name in ('JOINT_A.npz','JOINT_DATA.npz','K16_EXACT_ROWS.json')},
    PR209_grid_provenance_sha256=sha(previous/'GRID_PROVENANCE_AUDIT.json'),PR209_weights_sha256=sha(previous/'WEIGHTS.json'),
    dimensions=dict(rows=A.shape[0],columns=A.shape[1],binary=int(np.count_nonzero(d['vtypes']=='B')),NNZ=A.nnz),
    physical_dimension_total=dict(rows=p,columns=A.shape[1]-1,binary=int(np.count_nonzero(d['vtypes']=='B')),NNZ=physical.nnz),
    shared_dimensions=dict(rho_columns=1,rho_domain=[0,1],rho_type='C',rho_objective=1,objective_constant=0,K16_rows=16,K16_NNZ=A.nnz-physical.nnz),
    per_vehicle_census=counts,K16=rowtable,
    K16_native_coefficient_absolute_range=[min(magnitude),max(magnitude)],
    projection_formula='pi(F_FULL) subset J_exact subset J_native; exact physical Compact/C2/C3A projection and conservative K16 RHS conversion',
    exact_native_functions=dict(exact='g_k(x)=b_k+a_k^T*x',native='g_hat_k(x)=a_hat_k^T*x-r_hat_k',
        delta='delta_kj=a_hat_kj-a_kj',outward_rhs='r_hat_k>=-b_k+sum_j max(delta_kj*l_j,delta_kj*u_j)',
        loss='D_k(x)=g_k(x)-g_hat_k(x)=b_k+r_hat_k-sum_j delta_kj*x_j',
        loss_bounds='0<=D_k(x)<=epsilon_k=b_k+r_hat_k+sum_j max(-delta_kj*l_j,-delta_kj*u_j)'),
    weighted_dominance=dict(weight='1/16 for mathematical comparison only; 16 individual rows remain in MILP',
        exact='opt(J_exact)>=L_w_exact>=PR209 certified LB',
        native='opt(J_native)>=L_w_exact-epsilon_w>=PR209 certified LB-epsilon_w',
        epsilon_w_exact=str(weighted_max_loss),epsilon_w_float_outward=eps,
        weighted_face_loss_min_exact=str(weighted_min_loss),
        solver_bound_note='A TIME_LIMIT B&B ObjBound need not attain either optimal-value dominance lower limit. It remains separately conditional on the solver numerical global-bound contract.',
        exact_BB_trace_certificate=False),
    comparison=dict(PR209_certified_LB=0.11666465693783702,Source18r_full_solver_ObjBound=0.28940049108548904,
        verified_UB=0.6760534504652341,LB_for_3_percent_gap=0.655771846951277),
    elapsed_seconds=time.perf_counter()-started)
(out/'MODEL_REPORT_FACTS.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=True,dimensions=facts['dimensions'],per_vehicle_census=counts,epsilon_w_float_outward=eps,elapsed_seconds=facts['elapsed_seconds']),ensure_ascii=False,indent=2))
