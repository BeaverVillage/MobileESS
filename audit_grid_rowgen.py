"""No-model-build/no-optimization current M1 structural audit."""
from pathlib import Path
from collections import Counter
import json,hashlib,subprocess
import numpy as np
from v42_degen.identity import inputs,signature
from v42_rowgen.core import *
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'docs/v42_m1_exact_grid_rowgen_20261006'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(n,v):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/n;t=p.with_suffix(p.suffix+'.tmp')
    t.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8');t.replace(p)
def run():
    A,d,B,e,identity,freeze=inputs();vf=families(e['names']);rf=families(e['row_names'])
    cc=np.diff(B.tocsc().indptr);rc=np.diff(B.indptr)
    categories={'arc':'A_ROUTE_MOVEMENT_LOCATION','charge_mode':'B_CHARGE_DISCHARGE_MODE',
        'Pch':'C_P','Pdis':'C_P','Q':'D_Q','SOC':'E_SOC','rho_max':'F_RHO_OBJECTIVE',
        **dict.fromkeys(GRID_VARIABLES,'G_GRID_ONLY_AUXILIARIES')}
    vars=[]
    for f in sorted(set(vf)):
        ix=np.flatnonzero(vf==f)
        vars.append(dict(family=f,category=categories.get(f,'H_OTHER'),columns=len(ix),
            binaries=int(np.count_nonzero(e['types'][ix]=='B')),continuous=int(np.count_nonzero(e['types'][ix]=='C')),
            integers=int(np.count_nonzero(e['types'][ix]=='I')),rows_touched=int(np.unique(B.tocsc()[:,ix].indices).size),nnz=int(cc[ix].sum())))
    rowcat={'flow':'mobility_route_flow_and_transition','terminal_location':'mobility_route_flow',
        'energy_balance':'SOC_recurrence','initial_SOC':'initial_terminal_SOC','terminal_SOC':'initial_terminal_SOC',
        'PCS16':'PCS','connected_Pch':'P_Q_connection_coupling','connected_Pdis':'P_Q_connection_coupling',
        'connected_Qmax':'P_Q_connection_coupling','connected_Qmin':'P_Q_connection_coupling',
        'no_simultaneous_charge':'P_mode_coupling','no_simultaneous_discharge':'P_mode_coupling',
        'line_thermal_face':'line_current_and_rho_epigraph','voltage_lower':'voltage','voltage_upper':'voltage',
        'NormalAmps':'transformer_current','transformer_kVA':'transformer_kVA',
        **dict.fromkeys(BINDINGS,'grid_affine_definition')}
    rows=[]
    for f in sorted(set(rf)):
        ix=np.flatnonzero(rf==f);cols=np.unique(B[ix].indices)
        rows.append(dict(family=f,category=rowcat.get(f,'other'),rows=len(ix),columns_touched=len(cols),
            binaries_touched=int(np.count_nonzero(e['types'][cols]=='B')),continuous_touched=int(np.count_nonzero(e['types'][cols]=='C')),
            nnz=int(rc[ix].sum()),sense_counts=dict(Counter(map(str,e['sense'][ix])))))
    assert all(r['category']!='other' for r in rows) and all(v['category']!='H_OTHER' for v in vars)
    assert sum(v['nnz'] for v in vars)==sum(r['nnz'] for r in rows)==B.nnz
    assert sum(v['columns'] for v in vars)==B.shape[1] and sum(r['rows'] for r in rows)==B.shape[0]
    write('CURRENT_M1_VARIABLE_PARTITION.json',dict(PASS=True,families=vars,columns=B.shape[1],binaries=int(np.count_nonzero(e['types']=='B')),continuous=int(np.count_nonzero(e['types']=='C')),nnz=B.nnz,route_transition='Native arc encodes waiting and movement, arrival/connection; no separate location variable.',other_count=0))
    write('CURRENT_M1_ROW_PARTITION.json',dict(PASS=True,families=rows,rows=B.shape[0],nnz=B.nnz,transition='Contained exactly in arc flow rows and route domain; no omitted separate transition family.',other_count=0))
    defs=binding_proof(B,e);full_defs=binding_proof(A,d)
    grid=security_axis(e);aux=np.flatnonzero(np.isin(vf,list(GRID_VARIABLES)))
    science=['v42_integrated/build.py','v42_integrated/contract.py','v42_m1_sparse/grid.py','v42_native/grid.py','v42_bootstrap/grid.py','v42_native/mess.py']
    write('GRID_AFFINE_DEPENDENCY_AUDIT.json',dict(PASS=True,direct_row_generation_possible=True,new_native_calls=0,
        affine_auxiliary_definitions=len(defs),injection_equation='injection_P=sum(Pdis-Pch); injection_Q=sum(Q)',
        response_equation='response=original RHS - sum(original nonpivot coefficients * upstream injection); native pivot exactly +1',
        grid_evaluation='Original CSR rows on full master point, with certified roundoff enclosure and exact rational fallback.',
        grid_security_rows=len(grid),full_original_grid_rows=len(security_axis(d)),
        original_scientific_sources={p:sha(ROOT/p) for p in science},coefficient_authority=identity,
        all_temporal_MESS_physics_in_master=True,grid_dependencies=sorted(set(map(str,vf[np.unique(B[grid].indices)]))),
        classification_method='Every native equality pivot, bound, type and dependency audited; not name inference alone.',
        current_model_signature=signature(B,e)))
    np.savez_compressed(OUT/'GRID_AFFINE_DEFINITION_AXES.npz',definitions=np.asarray(defs),security_rows=grid,auxiliary_columns=aux)
    write('GRID_AUXILIARY_ELIMINATION_PROOF.json',dict(PASS=True,grid_auxiliary_columns=len(aux),all_unique_free_continuous_affine_definitions=True,
        topological_levels=['injection_P/Q from primary Pch/Pdis/Q','response_line/transformer from injection'],
        projection_equivalence='For every primary point each auxiliary has one unique affine value; substitution is bidirectional. Native grid constraints are evaluated in this exact extended formulation.',
        removed_columns=0,removed_percentage=0,production_elimination_applied=False,
        reason='Retain sparse factoring and all exact definitions. Expanding responses can multiply original grid-row density; removal is unnecessary for direct evaluation and would change floating transport.',
        feasibility_recourse_optimization_required=False))
    initial=OriginalRows(B,e);ix=initial.axis;C=B[ix]
    census=lambda M:dict(rows=M.shape[0],columns=M.shape[1],binaries=int(np.count_nonzero(e['types']=='B')),continuous=int(np.count_nonzero(e['types']=='C')),nnz=M.nnz,CSR_bytes=int(M.data.nbytes+M.indices.nbytes+M.indptr.nbytes))
    full=census(B);small=census(C)
    write('ROW_GENERATION_INITIAL_MASTER_CENSUS.json',dict(PASS=True,original_current_M1=full,initial_master=small,
        full_unreduced_original=dict(rows=A.shape[0],columns=A.shape[1],nnz=A.nnz),
        initial_security_policy='Empty security-row subset; all non-grid rows and every grid-affine definition retained.',
        deferred_original_grid_rows=len(grid),row_reduction_fraction=1-len(ix)/B.shape[0],nnz_reduction_fraction=1-C.nnz/B.nnz,
        auxiliary_columns_removed=0,auxiliary_columns_removed_percentage=0,
        memory_estimate='CSR storage only; not a native presolve/factorization/RSS forecast.',
        estimated_CSR_bytes_saved=full['CSR_bytes']-small['CSR_bytes'],materially_smaller=(len(ix)<.8*B.shape[0] and C.nnz<.8*B.nnz)))
    write('DECOMPOSITION_CLASSIFICATION.json',dict(primary_classification='DIRECT_EXACT_ROW_GENERATION_POSSIBLE',
        direct_row_generation_possible=True,grid_only_Benders_required=False,giant_recourse_required=False,
        native_optimization_calls=0,reason='All grid auxiliaries have unique triangular native affine definitions. Grid security is an affine inequality in current master controls; no optimization is required to evaluate it.',
        grid_only_Benders_mathematically_possible=True,fallback_implementation='NOT_NEEDED_DIRECT_EVALUATION_AVAILABLE'))
    write('GRID_ONLY_BENDERS_AUDIT.json',dict(status='NOT_APPLICABLE_DIRECT_AFFINE_AVAILABLE',grid_only_LP_needed=False,giant_recourse_rejected=True,new_recourse_calls=0))
    print(json.dumps(dict(no_solve=True,original=full,initial=small,grid_rows=len(grid),auxiliary_columns=len(aux)),indent=2))
if __name__=='__main__':run()
