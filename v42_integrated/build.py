"""Fresh Original M1 assembly from the integrated A1 freeze, never old matrix patch."""
import csv, json, pickle, time
from pathlib import Path
import numpy as np
from scipy import sparse
import gurobipy as gp
from .governance import ROOT, OUT, NORMALAMPS, write, sha
from .a1 import LOCAL
from .contract import physical_authority, all_transformer_rows, M_P2
from .matrix import arrays, duplicates, column_identity

def run():
    freeze=json.loads((OUT/'INTEGRATED_A1_FREEZE.json').read_text(encoding='utf8'))
    if not freeze['PASS']:raise ValueError('A1_FREEZE_REQUIRED_BEFORE_M1')
    if (LOCAL/'M1_BUILD_STARTED.json').exists():raise ValueError('M1_BUILD_NO_RETRY')
    (LOCAL/'M1_BUILD_STARTED.json').write_text(json.dumps(dict(A1_freeze_sha256=sha(OUT/'INTEGRATED_A1_FREEZE.json'))),encoding='utf8')
    assert sha(LOCAL/'DATA.pkl')==freeze['source_data_sha256']
    with (LOCAL/'DATA.pkl').open('rb') as f:data=pickle.load(f)
    bundle=data[0];anchor=freeze['anchor'];bindings=[];cost=[];thermal_bindings=[];captured=[];control_handles=[]
    from v42_bootstrap.m1 import native_inputs, OptimizeOnlyBudget
    from v42_m1_sparse.grid import add_compressed, response
    from v42_bootstrap.grid import coefficients
    from v42_native.voltage import Stage, authority_sha, voltage_for
    from v42_native.grid import GridAuthority
    from v42_native.contracts import digest
    import v42_native.mess as mess
    sites,initial,routes,battery,receipt=native_inputs(bundle)
    cert,coeff=coefficients(bundle)
    assert anchor['voltage_authority_sha256']==authority_sha(Stage.A1)
    def grid(m,p,q):
        pp={key:response(m,f'injection_P[{key[0]},{key[1]}]',v,bindings) for key,v in p.items()}
        qq={key:response(m,f'injection_Q[{key[0]},{key[1]}]',v,bindings) for key,v in q.items()}
        controls=[]
        for t,c in enumerate(coeff):
            row=[]
            for i,name in enumerate(c.control_names):
                site=name.split('[')[1][:-1]
                if name.startswith('aidc_load_kw'):row.append(float(anchor['controls'][t][i]))
                elif name.startswith('mess_p_kw'):row.append(pp[site,t])
                elif name.startswith('mess_q_kvar'):row.append(qq[site,t])
                else:raise ValueError('UNKNOWN_CONTROL')
            controls.append(row)
        v=voltage_for(Stage.M1)
        topology=cert['input_identity']['identity']['inputs']['OpenDSS_master']['sha256']
        ga=GridAuthority(topology,digest(bundle['capacities']),freeze['source_data_sha256'],digest(bundle['battery']),v.lower_squared,v.upper_squared,True,stage=Stage.M1,transformer_current_authority_sha256=NORMALAMPS)
        builder=lambda model,c,x,a:add_compressed(model,c,x,a,'M1-F3',bindings,cost)
        rho=all_transformer_rows(builder,thermal_bindings)(m,coeff,controls,ga)
        control_handles.extend(controls)
        return [('rho',rho),('reserve_shortfall',0.)]
    def capture(m,objectives,deadline,*args,**kwargs):
        assert [n for n,_ in objectives]==['rho','reserve_shortfall','movement_kwh','movement_count','tie']
        m.setObjective(objectives[0][1]);m.update()
        write('M1_OBJECTIVE_CONTRACT.json',dict(P1='MIN MAX_LINE_LOADING',P2=list(M_P2),movement_energy_coefficients={objectives[2][1].getVar(i).VarName:objectives[2][1].getCoeff(i) for i in range(objectives[2][1].size())},movement_count_variables=[objectives[3][1].getVar(i).VarName for i in range(objectives[3][1].size())],P2_execution='Only after P1 acceptance; this task performs one bound-oriented P1 solve',reserve_shortfall_objective=False,CC4_deviation_objective=False,route_fixed=False,AIDC_variables=0))
        captured.append(m.copy());return None,dict(optimization_calls=0)
    old=mess.optimize;mess.optimize=capture;begin=time.perf_counter()
    try:mess.solve('M1',OptimizeOnlyBudget(),sites,initial,routes,battery,96,grid)
    finally:mess.optimize=old
    m=captured[0];m.update()
    assert len(thermal_bindings)==120*96
    A,d=arrays(m)
    np.savez_compressed(LOCAL/'FULL_DATA.npz',**d);sparse.save_npz(LOCAL/'FULL_A.npz',A)
    families={};grid_rows=grid_nnz=0
    for i,n in enumerate(d['row_names']):
        family=str(n).split('[',1)[0];families[family]=families.get(family,0)+1
        if family.startswith(('voltage_','line_thermal','NormalAmps','transformer_','response_','injection_')):
            grid_rows+=1;grid_nnz+=int(A.indptr[i+1]-A.indptr[i])
    census=dict(rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,integers=m.NumIntVars-m.NumBinVars,continuous=m.NumVars-m.NumIntVars,nnz=A.nnz,coefficient_min=float(abs(A.data).min()),coefficient_max=float(abs(A.data).max()),coefficient_dynamic_range=float(abs(A.data).max()/abs(A.data).min()),row_family_counts=families,grid_rows=grid_rows,grid_nnz=grid_nnz,grid_rows_share=grid_rows/m.NumConstrs,grid_nnz_share=grid_nnz/A.nnz,build_seconds=time.perf_counter()-begin,source_A1_freeze_sha256=sha(OUT/'INTEGRATED_A1_FREEZE.json'),new_matrix_regenerated=True,old_matrix_patch=False,horizon=96,episode='2025-05-01')
    write('INTEGRATED_M1_MATRIX_CENSUS.json',census)
    pairs=duplicates(A,d['rhs'],d['sense']);print('M1_DUPLICATES',len(pairs),flush=True)
    removed={i for i,_,_ in pairs};keep=np.array([i for i in range(A.shape[0]) if i not in removed]);reduced=m.copy()
    original_reduced_rows=reduced.getConstrs()
    reduced.remove([original_reduced_rows[i] for i in sorted(removed)]);reduced.update()
    B,e=arrays(reduced)
    assert column_identity(d)==column_identity(e)
    assert np.array_equal(B.indptr,A[keep].indptr) and np.array_equal(B.indices,A[keep].indices) and np.array_equal(B.data,A[keep].data)
    proof=dict(PASS=True,full_rows=A.shape[0],reduced_rows=B.shape[0],columns=A.shape[1],removed_rows=len(pairs),full_nnz=A.nnz,reduced_nnz=B.nnz,comparison='exact coefficient index/data bytes + binary RHS + sense',constant_rows_retained=True,proportional_rows_removed=False,tolerance_comparison=False,variables_bounds_types_objective_unchanged=True,column_identity_sha256=column_identity(d),feasible_set_proof='Every removed row is identical to its retained representative in coefficients, sense and RHS; all other rows and every column attribute remain identical.',new_model_independent_scan=True,old_count_not_assumed=True)
    np.savez_compressed(LOCAL/'REDUCTION_AXES.npz',keep=keep)
    write('INTEGRATED_M1_DUPLICATE_PROOF.json',proof)
    with (OUT/'INTEGRATED_M1_DUPLICATE_MAP.csv').open('w',encoding='utf8',newline='') as f:
        writer=csv.writer(f);writer.writerow(['removed_row','retained_representative','row_payload_SHA256']);writer.writerows(pairs)
    with (OUT/'M1_TRANSFORMER_AUTHORITY_BINDING.csv').open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(thermal_bindings[0]));writer.writeheader();writer.writerows(thermal_bindings)
    names=m.getConstrs()
    for i,row in enumerate(names):
        if not row.ConstrName.startswith('NormalAmps['):row.ConstrName=row.ConstrName+'__'+str(i)
    reduced_names=reduced.getConstrs()
    for j,i in enumerate(keep):reduced_names[j].ConstrName=names[i].ConstrName if names[i].ConstrName.startswith('NormalAmps[') else str(d['row_names'][i])+'__'+str(i)
    m.update();reduced.update();m.write(str(LOCAL/'FULL.mps'));reduced.write(str(LOCAL/'REDUCED.mps'))
    with np.load(LOCAL/'FULL_DATA.npz') as z:dd={k:z[k] for k in z.files}
    from .start import compatible,reconstruct
    old_anchor=json.loads((ROOT/'docs/v42_m1_relaxation_strengthening/A1_AIDC_GRID_CONTROL_ANCHOR.json').read_text(encoding='utf8'))
    start_result=dict(reused=False,old_certificate_used=False,variables_fixed=False,new_A1_compatible=compatible(anchor,old_anchor))
    if not start_result['new_A1_compatible']:
        start_result.update(status='REJECTED',reason='NEW_A1_FIXED_AIDC_DIFFERS_FROM_OLD_A1')
    else:
        source=Path('C:/Users/kjw39/Documents/Codex/2026-10-03/m1-root-pathology-diagnostics/worktree/docs/v42_m1_compact_exact_start/ORIGINAL_RECONSTRUCTED_START.npz')
        if source.is_file():
            try:
                with np.load(source) as z:point,start_audit=reconstruct(A,dd,z['names'],z['values'])
                start_result.update(audit=start_audit,reused=start_audit['PASS'],status='ACCEPTED_WARM_START_ONLY' if start_audit['PASS'] else 'REJECTED',source_sha256=sha(source),no_old_margin_rating_dependency=True)
                if start_audit['PASS']:np.savez_compressed(LOCAL/'M1_START.npz',values=point)
            except ValueError as error:start_result.update(status='REJECTED',reason=str(error))
        else:start_result.update(status='REJECTED',reason='EXACT_SOURCE_START_UNAVAILABLE')
    write('M1_START_COMPATIBILITY.json',start_result)
    write('M1_MODEL_IDENTITY.json',dict(full_MPS_sha256=sha(LOCAL/'FULL.mps'),reduced_MPS_sha256=sha(LOCAL/'REDUCED.mps'),matrix_sha256=sha(LOCAL/'FULL_A.npz'),data_sha256=sha(LOCAL/'FULL_DATA.npz'),A1_freeze_sha256=sha(OUT/'INTEGRATED_A1_FREEZE.json'),NormalAmps_authority=NORMALAMPS))
    m.dispose();reduced.dispose();print('M1_PREPARED',census,proof,start_result,flush=True)

def main():
    from .import_guard import selected_imports
    with selected_imports(),physical_authority():run()

if __name__=='__main__':
    from pathlib import Path
    main()
