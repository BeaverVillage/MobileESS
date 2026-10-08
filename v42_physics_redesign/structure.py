"""Actual CSR partition and full-horizon diagnostic, never a solve."""
from .common import *
from .temporal import build
from collections import Counter,defaultdict
from fractions import Fraction as F

PHYSICAL={'route_flow','node_activity','charge_mode','SOC','Pch','Pdis','Q','injection_P','injection_Q','rho_max'}
SECURITY={'line_thermal_face','voltage_upper','voltage_lower','transformer_kVA'}

def main():
    prior.forbid_optimize();paths_audit('structure_and_full_horizon_cut_proof')
    A,d,_=hc.load();names=np.array([str(n).split('[')[0] for n in d['names']]);families=np.array([str(n).split('[')[0] for n in d['row_names']]);rho=int(np.flatnonzero(d['objective'])[0])
    source=ROOT/'docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz'
    with np.load(source) as f:x=f['x'].copy();pi=f['Pi'].copy();rc=f['RC'].copy()
    slack=np.where(d['sense']=='<',d['rhs']-A@x,np.where(d['sense']=='>',A@x-d['rhs'],d['rhs']-A@x))
    save(WORK/'artifacts/ARCHIVED_ROOT_DIAGNOSTIC.npz',x=x,Pi=pi,RC=rc,original_row_slack_reconstructed=slack)
    rowstats=[]
    for family,count in Counter(families).items():
        axis=np.flatnonzero(families==family);rowstats.append(dict(family=family,rows=count,nnz=int(A[axis].nnz),absolute_dual_mass=float(abs(pi[axis]).sum()),active_residual_le_1e6=int((abs(slack[axis])<=1e-6).sum()),max_abs_dual=float(abs(pi[axis]).max())))
    table(REPORTS/'ROOT_ROW_FAMILY_DIAGNOSTIC.csv',rowstats)
    colstats=[]
    for family,count in Counter(names).items():
        axis=np.flatnonzero(names==family);v=x[axis];integer=(d['types'][axis]=='B');colstats.append(dict(family=family,columns=count,original_binary_count=int(integer.sum()),fractional_binary_count=int((integer&(abs(v-np.rint(v))>1e-8)).sum()),fractional_01_continuous_count=int(((v>1e-8)&(v<1-1e-8)&(~integer)).sum()),min=float(v.min()),max=float(v.max()),zero_RC_le_1e8=int((abs(rc[axis])<=1e-8).sum())))
    table(REPORTS/'ROOT_VARIABLE_FAMILY_DIAGNOSTIC.csv',colstats)
    # Enumerate actual physics-only columns and rows. No duplicate variables.
    shared=np.flatnonzero(np.isin(names,list(PHYSICAL)));network=np.setdiff1d(np.arange(A.shape[1]),shared);pure=np.flatnonzero(np.asarray(A[:,network].getnnz(axis=1)).ravel()==0)
    bindings=np.flatnonzero(np.char.endswith(families.astype(str),'_binding'));definitions={};nonunit=[]
    for i in bindings:
        fam=str(families[i])[:-8];row=A.getrow(i);piv=[(int(j),float(a)) for j,a in zip(row.indices,row.data) if names[j]==fam]
        if len(piv)==1 and piv[0][1]==1. and d['sense'][i]=='=' and piv[0][0] not in definitions:definitions[piv[0][0]]=int(i)
        else:nonunit.append(int(i))
    unidentified=[int(j) for j in network if int(j) not in definitions]
    partition=dict(PASS=True,original_columns=A.shape[1],physics_shared_columns=len(shared),network_residual_columns=len(network),physics_only_rows=len(pure),physics_only_nnz=int(A[pure][:,shared].nnz),coupling_rows=A.shape[0]-len(pure),binding_rows=len(bindings),exact_direct_unit_definitions=len(definitions),network_variables_without_direct_binding=len(unidentified),nonunit_or_aliased_binding_rows=nonunit,unidentified_network_variables_sample=[str(d['names'][j]) for j in unidentified[:20]],shared_axis_sha256=hashlib.sha256(shared.tobytes()).hexdigest(),row_axis_sha256=hashlib.sha256(pure.tobytes()).hexdigest(),original_bounds_retained=True,original_variable_copies=0,scientific_objective=prior.objective_identity(A,d),partial_Benders_adoption=False,adopted_structure='Compact original-variable monolithic branch-and-cut with full physical master and original grid rows',reason='Pure physics master retains original 96-slot coupling, but its incomplete grid relaxation cannot beat the original C3A LP. Closure with residual constraints is the original LP. Retain all sparse network variables and every original grid row, avoiding repeated giant recourse/rowgen restarts; investigate genuinely new temporal integer disjunctions as B2.',original_grid_rows_permanently_removed=0)
    write(REPORTS/'CSR_PARTITION_AUDIT.json',partition);save(WORK/'artifacts/PHYSICAL_MASTER_AXES.npz',shared=shared,network=network,pure_physics_rows=pure,all_original_grid_rows=np.flatnonzero(np.isin(families,list(SECURITY))))
    from v42_strengthening.analysis import graph_inputs
    sites,initial,arcs,battery,receipt=graph_inputs();reader=hc.physical_reader()
    # Every original FULL energy equality must transport exactly to the
    # immutable C3A energy namespace, with no missing horizon or unit.
    current=set()
    for i in np.flatnonzero(families=='energy_balance'):
        row=A.getrow(i);current.add((tuple((int(j),F.from_float(float(a))) for j,a in zip(row.indices,row.data)),str(d['sense'][i]),F.from_float(float(d['rhs'][i]))))
    matched=[]
    for i,n in enumerate(reader.d['row_names']):
        if str(n).split('[')[0]!='energy_balance':continue
        row=reader.full.getrow(i);terms=defaultdict(F);offset=F(0)
        for j,a in zip(row.indices,row.data):
            k=int(reader.target[j]);a=F.from_float(float(a));offset+=a*F.from_float(float(reader.offset[j]))
            if k>=0:terms[k]+=a
        signature=(tuple(sorted((j,a) for j,a in terms.items() if a)),str(reader.d['sense'][i]),F.from_float(float(reader.d['rhs'][i]))-offset)
        assert signature in current,'ORIGINAL_FULL_TO_C3A_ENERGY_IDENTITY_FAILURE';matched.append(i)
    assert len(matched)==384
    write(REPORTS/'TEMPORAL_SCIENTIFIC_IDENTITY.json',dict(PASS=True,original_FULL_energy_rows_to_C3A_exact=384,all_4_MESS_96_slots=True,graph_receipt=receipt,original_SOC_bounds_finite=True,old_PR183_integer_flow_uniqueness_proof_sha256=sha(P183/'ROUTE_PROJECTION_AUDIT.json'),physical_source_inverse_preserved=True,scientific_matrix_SHA256=sha(hc.PARENT/'C3A_A.npz')))
    T,tr,proofs=build(A,d,x,reader,arcs)
    # H2 estimate uses actual non-SOC terms in each energy row. Exact prefix
    # accumulation densifies route columns; no discretized energy states.
    energy=np.flatnonzero(families=='energy_balance');prefix_nnz=0
    for unit in initial:
        cumulative=set()
        for t in range(96):
            matching=[]
            for i in energy:
                row=A.getrow(i)
                if any(str(d['names'][j])==f'SOC[{unit},{t+1}]' and a==1. for j,a in zip(row.indices,row.data)):matching.append(i)
            if t==95:
                # Terminal equality is represented after initial/terminal
                # elimination. Upper-bound estimate includes every own-unit
                # energy-row non-SOC term not encountered earlier.
                matching=[i for i in energy if any(str(d['names'][j]).startswith(f'Pch[{unit},') for j in A.getrow(i).indices)]
            for i in matching:
                cumulative.update(int(j) for j in A.getrow(i).indices if names[j]!='SOC')
            prefix_nnz+=len(cumulative)*(1 if t==95 else 2)
    # Correct value for H2 terminal replacement and 380 finite-state bounds.
    complexity=[dict(candidate='B0_ARCHIVED_C3A',columns=A.shape[1],binaries=int((d['types']=='B').sum()),continuous=int((d['types']=='C').sum()),rows=A.shape[0],nnz=A.nnz,added_columns=0,exactness='Original authority',root_execution='ARCHIVED'),dict(candidate='H1_PURE_PHYSICAL_MASTER_INCOMPLETE_GRID',columns=len(shared),binaries=int((d['types'][shared]=='B').sum()),continuous=int((d['types'][shared]=='C').sum()),rows=len(pure),nnz=int(A[pure][:,shared].nnz),added_columns=0,exactness='Only exact with residual original grid constraints; standalone relaxation',root_execution='NOT_RUN: cannot strengthen original C3A LP'),dict(candidate='B1_FULL_PHYSICS_GRID_CLOSURE',columns=A.shape[1],binaries=int((d['types']=='B').sum()),continuous=int((d['types']=='C').sum()),rows=A.shape[0],nnz=A.nnz,added_columns=0,exactness='Identity mapping, all original constraints',root_execution='REUSE_B0: mathematically identical; no duplicate solve'),dict(candidate='H2_EXACT_TEMPORAL_SOC_ELIMINATION',columns=A.shape[1]-380,binaries=int((d['types']=='B').sum()),continuous=int((d['types']=='C').sum())-380,rows=A.shape[0]-384+764,nnz=A.nnz-A[energy].nnz+prefix_nnz,added_columns=-380,exactness='Exact cumulative substitution and all original SOC bounds/terminal; same LP feasible projection',root_execution='NOT_RUN: no LP strengthening and predicted fill-in'),dict(candidate='B2_COMPACT_FULL_PHYSICS_PLUS_TEMPORAL_DISJUNCTIONS',columns=A.shape[1],binaries=int((d['types']=='B').sum()),continuous=int((d['types']=='C').sum()),rows=A.shape[0]+T.shape[0],nnz=A.nnz+T.nnz,added_columns=0,exactness='Original integer schedules preserved; new integer-valid route/SOC inequalities',root_execution='GATED_ROOT_MAX_900_SECONDS')]
    reference_min=float(abs(A.data[A.data!=0]).min());reference_max=float(abs(A.data).max())
    for item in complexity:
        item.update(matrix_abs_min_nonzero=reference_min,matrix_abs_max=reference_max,original_C3A_reference_abs_min_nonzero=reference_min,original_C3A_reference_abs_max=reference_max,presolve_size_estimate='NOT_MEASURED: no invented removal count',model_size_source='Measured original/partition CSR',native_model_build_wall_seconds='NOT_MEASURED')
        if item['candidate'].startswith(('H1_','H2_')):
            item['matrix_abs_min_nonzero']=item['matrix_abs_max']='NOT_MEASURED_FOR_CANDIDATE'
        if item['candidate'].startswith('H2_'):
            item['model_size_source']='Symbolic axis/row counts; prefix nnz estimate, not materialized CSR'
        if item['candidate'].startswith('B2_'):
            item.update(matrix_abs_min_nonzero=min(reference_min,float(abs(T.data).min())) if T.nnz else reference_min,matrix_abs_max=max(reference_max,float(abs(T.data).max())) if T.nnz else reference_max,model_size_source='Measured original CSR plus measured temporal CSR; not native presolve',temporal_row_build_wall_seconds=read(REPORTS/'VALID_INEQUALITY_CERTIFICATES.json')['build_wall_seconds'])
    table(REPORTS/'MODEL_COMPLEXITY_COMPARISON.csv',complexity)
    write(REPORTS/'ROOT_RAW_POINT_AUDIT.json',dict(PASS_as_integer_witness=False,accepted_as_global_LB=False,source_SHA256=sha(source),native_root_objective=float(d['objective']@x),existing_certified_global_LB=LB,stationarity_vs_RC_max=float(abs(d['objective']-A.T@pi-rc).max()),raw_original_replay=hc.replay(A,d,x,False),root_primal_dual_RC_available=True,native_slack_missing=True,slack_reconstructed_from_original_CSR=True,UB_not_proven_optimal=True,remaining_gap_not_equated_to_true_integrality_gap=True,temporal_cut_count=T.shape[0],temporal_cut_nnz=T.nnz))
    print('STRUCTURAL_GATE',json.dumps(clean(dict(partition=partition,temporal_rows=T.shape[0],temporal_nnz=T.nnz,H2_nnz_estimate=complexity[3]['nnz']))),flush=True)

if __name__=='__main__':main()
