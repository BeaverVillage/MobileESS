"""One finite restricted master pilot; its objective has no Global LB authority."""
from fractions import Fraction as F
from pathlib import Path
from time import perf_counter
import json
import numpy as np
from scipy import sparse
import gurobipy as gp
from v42_unified.audit import write
from v42_unified.storage import sha
from v42_m1_research.check_ub import matrix_replay,vector_sha
from .blocks import verify_decomposition,output_directory


def build_master(case,decomp,columns,output):
    start=perf_counter();output=output_directory(output)
    verify_decomposition(case,decomp)
    source_rows=np.sort(np.concatenate((decomp.nonunit_block.original_rows,decomp.coupling_rows)))
    nonunit=decomp.nonunit_columns
    pieces=[case.A[source_rows][:,nonunit].tocsr()]
    objective=list(map(float,case.d['objective'][nonunit]));catalog=[];column_count={}
    for u,block in decomp.units.items():
        source=case.A[source_rows][:,block.original_columns].tocsr()
        candidates=[];seen=set()
        seed=np.asarray(case.point)[block.original_columns].copy()
        seed_path=output/(u+'_MASTER_SEED_COLUMN.npz')
        np.savez_compressed(seed_path,point=seed,original_columns=block.original_columns)
        candidates.append(dict(path=str(seed_path),sha256=sha(seed_path),source='VERIFIED_FULL_ORIGINAL_STRICT_SEED'))
        candidates.extend(c for c in columns.get(u,[]) if c.get('admission',{}).get('PASS'))
        column_count[u]=0
        for item in candidates:
            path=Path(item['path'])
            if sha(path)!=item['sha256']:raise ValueError('DW_COLUMN_BYTE_DRIFT')
            with np.load(path,allow_pickle=False) as z:
                point=z['point'].copy();axis=z['original_columns'].copy()
            if not np.array_equal(axis,block.original_columns):raise ValueError('DW_COLUMN_ORIGINAL_AXIS_DRIFT')
            if point.shape!=(len(axis),) or not np.isfinite(point).all():raise ValueError('DW_COLUMN_POINT_DRIFT')
            replay=matrix_replay(block.A,block.d,point)
            if not replay['PASS'] or not replay['integer_pattern_exact'] or not replay['exact_binary_0_1']:
                raise ValueError('DW_COLUMN_LOCAL_ORIGINAL_DOMAIN_REPLAY_FAILED')
            key=vector_sha(point)
            if key in seen:continue
            seen.add(key)
            weighted=source@point
            pieces.append(sparse.csr_matrix(weighted.reshape(-1,1)))
            objective.append(float(block.d['objective']@point))
            catalog.append(dict(unit=u,point_vector_sha256=key,point_path=str(path),
                point_file_sha256=item['sha256'],original_columns=axis.tolist(),local_replay=replay))
            column_count[u]+=1
    rowcount=len(source_rows);n=len(nonunit);k=len(catalog)
    matrix=sparse.hstack(pieces,format='csr')
    units=list(decomp.units)
    convex=sparse.lil_matrix((len(units),n+k))
    for j,item in enumerate(catalog):convex[units.index(item['unit']),n+j]=1.
    matrix=sparse.vstack((matrix,convex.tocsr()),format='csr')
    rhs=np.concatenate((case.d['rhs'][source_rows],np.ones(len(units))))
    sense=np.concatenate((case.d['sense'][source_rows],np.full(len(units),'=')))
    lower=np.concatenate((case.d['lower'][nonunit],np.zeros(k)))
    upper=np.concatenate((case.d['upper'][nonunit],np.ones(k)))
    names=list(map(str,case.d['names'][nonunit]))+[f"lambda[{item['unit']},{j}]" for j,item in enumerate(catalog)]
    model=gp.Model('V42_FAST_HYBRID_ONE_RESTRICTED_MASTER')
    try:
        model.Params.OutputFlag=1;model.Params.Method=1
        variables=model.addMVar(n+k,lb=lower,ub=upper,vtype='C',obj=np.asarray(objective))
        variables.VarName=names;model.ObjCon=float(case.d['constant'])
        rows=model.addMConstr(matrix,variables,sense,rhs)
        model.update()
        native=model.getA();delta=native-matrix;delta.eliminate_zeros()
        if delta.nnz or not np.array_equal(np.asarray(model.getAttr('RHS')),rhs):raise ValueError('DW_NATIVE_MATRIX_DRIFT')
        receipt=dict(PASS=True,case_sha=case.case_sha,source_rows=source_rows.tolist(),
            nonunit_columns=nonunit.tolist(),column_count_by_unit=column_count,catalog=catalog,
            rows=model.NumConstrs,columns=model.NumVars,source_nonunit_coefficients_exact=True,
            derived_lambda_coefficients='binary64 original-CSR dot physical-column; diagnostic RMP rounding only',
            original_F_subset_restricted_master=False,
            full_DW_original_F_inclusion_requires_entire_feasible_trajectory_catalog=True,
            restricted_master_objective_is_Global_LB=False,
            restricted_master_objective_is_Global_UB=False,build_wall_seconds=perf_counter()-start)
        write(output/'RMP_IDENTITY.json',receipt)
        return model,variables,rows,receipt,source_rows
    except BaseException:
        model.dispose();raise


def run(case,decomp,columns,ledger,output,*,seconds=30):
    if seconds!=30:raise ValueError('ONE_PREREGISTERED_30_SECOND_RMP_REQUIRED')
    output=Path(output);start=perf_counter()
    with ledger.cost('RMP_model_build','ONE_RESTRICTED_MASTER',track='RMP'):
        model,variables,rows,identity,source_rows=build_master(case,decomp,columns,output)
    try:
        native=ledger.optimize(model,track='RMP',label='ONE_RESTRICTED_MASTER',requested_seconds=seconds)
        result=dict(case_sha=case.case_sha,identity=identity,native=native,
            Native_objective_diagnostic=None,restricted_master_is_Global_LB=False,
            restricted_master_is_Global_UB=False,pricing_closure='NOT_PROVEN',
            full_original_dual=None,convexity_duals=None)
        if model.SolCount:
            result['Native_objective_diagnostic']=float(model.ObjVal)
            np.savez_compressed(output/'RMP_RAW_POINT.npz',point=np.asarray(variables.X),source_rows=source_rows)
        try:
            pi=np.asarray(rows.Pi,dtype=np.float64)
        except gp.GurobiError:
            pi=None
        if pi is not None and np.isfinite(pi).all():
            signed=pi[:len(source_rows)].copy();senses=case.d['sense'][source_rows]
            invalid=((senses=='<')&(signed>0))|((senses=='>')&(signed<0))
            signed[invalid]=0.
            full={str(int(i)):str(F(float(q))) for i,q in zip(source_rows,signed) if q}
            eta={u:str(F(float(pi[len(source_rows)+j]))) for j,u in enumerate(decomp.units)}
            write(output/'RMP_ORIGINAL_ROW_DUAL_EXACT.json',full)
            write(output/'RMP_CONVEXITY_DUAL_EXACT.json',eta)
            np.savez_compressed(output/'RMP_RAW_DUAL.npz',dual=pi,source_rows=source_rows)
            result.update(full_original_dual=full,convexity_duals=eta,
                invalid_original_inequality_multiplier_signs_zeroed=int(invalid.sum()),
                dual_status='FINITE_ORIGINAL_ROW_DUAL_AVAILABLE_NOT_NATIVE_OBJECTIVE_PROOF')
        else:result['dual_status']='NO_FINITE_PI_FOLLOWUP_PRICING_NOT_RUN'
        result['wall_seconds']=perf_counter()-start
        write(output/'RMP_RESULT.json',result)
        return result
    finally:model.dispose()
