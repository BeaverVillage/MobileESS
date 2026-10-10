"""Single-model, single-full-CSR-readback, optimize=0 coefficient repair audit."""
from pathlib import Path
from time import perf_counter
from hashlib import sha256
import json
import numpy as np
from scipy import sparse
from v42_m1_hybrid.blocks import matrix_sha
from v42_may_campaign.m_model import _domain_sha
from .scaling import row_scaling


def run(folder):
    import gurobipy as gp
    import psutil
    begin=perf_counter();folder=Path(folder)
    A=sparse.load_npz(folder/'ORIGINAL_MASTER_CSR.npz').tocsr()
    d=dict(np.load(folder/'ORIGINAL_MASTER_DOMAIN.npz',allow_pickle=False))
    scaled,rhs,exponents=row_scaling(A,d['rhs'])
    tiny=A.tocoo();mask=(abs(tiny.data)<1e-13)&(tiny.data!=0)
    coordinates=[dict(row=int(i),column=int(j),value=float(v),original_source_row=int(d['source_rows'][i]))
                 for i,j,v in zip(tiny.row[mask],tiny.col[mask],tiny.data[mask])]
    initial_rss=psutil.Process().memory_info().rss
    model=gp.Model('V42_TRAJECTORY_DW_COEFFICIENT_REPAIR_BUILD_ONLY')
    try:
        model.Params.OutputFlag=0;model.Params.Threads=1
        model.Params.FeasibilityTol=1e-8;model.Params.OptimalityTol=1e-8;model.Params.IntFeasTol=1e-8
        v=model.addMVar(A.shape[1],lb=d['lower'],ub=d['upper'],obj=d['objective'],vtype='C')
        model.ObjCon=float(d['constant'])
        constraints=model.addMConstr(A,v,d['sense'],d['rhs'])
        model.update()
        # Scalar old nnz census, not a second full CSR readback.
        old_nnz=int(model.NumNZs)
        if A.nnz-old_nnz!=len(coordinates):
            raise ValueError('LOSS_CAUSE_NOT_ISOLATED_NO_REPAIR')
        variables=model.getVars();rows=model.getConstrs()
        for i in np.flatnonzero(exponents):
            a,b=scaled.indptr[i:i+2]
            for j,value in zip(scaled.indices[a:b],scaled.data[a:b]):
                model.chgCoeff(rows[int(i)],variables[int(j)],float(value))
            rows[int(i)].RHS=float(rhs[i])
        model.update()
        actual=model.getA().tocsr()  # The only full matrix readback in this task.
        for key in ('indptr','indices','data'):
            if not np.array_equal(getattr(actual,key),getattr(scaled,key)):
                raise ValueError('SCALED_SOLVER_CSR_IDENTITY_FAIL')
        recovered=actual.copy()
        recovered.data=np.ldexp(actual.data,-np.repeat(exponents,np.diff(actual.indptr)))
        if matrix_sha(recovered)!=matrix_sha(A):
            raise ValueError('ORIGINAL_MASTER_CSR_RECOVERY_FAIL')
        native_rhs=np.asarray(model.getAttr('RHS'))
        if not np.array_equal(native_rhs,rhs) or not np.array_equal(np.ldexp(native_rhs,-exponents),d['rhs']):
            raise ValueError('RHS_RECOVERY_FAIL')
        if not np.array_equal(np.asarray(model.getAttr('Sense')),d['sense']):
            raise ValueError('SENSE_IDENTITY_FAIL')
        if not np.array_equal(np.asarray(model.getAttr('Obj')),d['objective']) or model.ObjCon!=float(d['constant']):
            raise ValueError('OBJECTIVE_IDENTITY_FAIL')
        native_lower=np.asarray(model.getAttr('LB'));native_upper=np.asarray(model.getAttr('UB'))
        for native,source in ((native_lower,d['lower']),(native_upper,d['upper'])):
            infinite=np.isinf(source)
            if not np.array_equal(native[~infinite],source[~infinite]) or not np.all(np.sign(native[infinite])==np.sign(source[infinite])):
                raise ValueError('VARIABLE_DOMAIN_IDENTITY_FAIL')
            if not np.all(abs(native[infinite])>=gp.GRB.INFINITY):
                raise ValueError('BACKEND_INFINITY_NOT_EQUIVALENT')
        recovered_domain=dict(d,rhs=np.ldexp(native_rhs,-exponents),sense=np.asarray(model.getAttr('Sense')),
                              lower=d['lower'].copy(),upper=d['upper'].copy(),
                              objective=np.asarray(model.getAttr('Obj')),constant=np.asarray(model.ObjCon))
        result=dict(status='MASTER_EQUIVALENCE_PASS',old_deleted_coefficient_count=A.nnz-old_nnz,
            loss_coordinates=coordinates,loss_variable_family='lambda[MESS01,verified_integer_UB_seed]',
            cause='Gurobi automatic coefficient filtering below 1e-13; no source CSR assembly mismatch',
            row_scale_exponents={str(int(i)):int(exponents[i]) for i in np.flatnonzero(exponents)},
            column_scaling='S=I',old_original_nnz=int(A.nnz),old_native_nnz=old_nnz,
            new_native_nnz=int(actual.nnz),remaining_coefficient_loss=0,
            original_matrix_sha=matrix_sha(A),scaled_matrix_sha=matrix_sha(scaled),
            native_scaled_matrix_sha=matrix_sha(actual),recovered_original_matrix_sha=matrix_sha(recovered),
            original_domain_sha=_domain_sha(d),recovered_original_domain_sha=_domain_sha(recovered_domain),
            source_domain_unchanged=True,objective_and_bounds_unchanged=True,
            rows=model.NumConstrs,columns=model.NumVars,
            original_abs_coefficient_range=[float(min(abs(A.data))),float(max(abs(A.data)))],
            scaled_abs_coefficient_range=[float(min(abs(actual.data))),float(max(abs(actual.data)))],
            affected_scaled_coefficients=[float(np.ldexp(c['value'],exponents[c['row']])) for c in coordinates],
            max_scaled_abs_RHS=float(max(abs(rhs))),process_rss_before_model_bytes=initial_rss,
            process_rss_after_model_bytes=psutil.Process().memory_info().rss,
            process_peak_working_set_bytes=getattr(psutil.Process().memory_info(),'peak_wset',None),
            solver_memory_GB=float(model.MemUsed),solver_peak_memory_GB=float(model.MaxMemUsed),
            Native_optimize_calls=0,Native_Runtime=0,Master_Model_objects=1,full_CSR_readbacks=1,
            Certified_LB_improvement='NOT_MEASURED',wall_seconds=perf_counter()-begin)
        sparse.save_npz(folder/'SCALED_SOLVER_READBACK_CSR.npz',actual)
        np.savez(folder/'ROW_SCALING.npz',exponents=exponents,scaled_rhs=rhs)
        (folder/'EQUIVALENCE_RESULT.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
        print(json.dumps(result,indent=2))
        return result
    except Exception as exc:
        (folder/'EQUIVALENCE_FAILURE.json').write_bytes((json.dumps(dict(status='MASTER_BUILD_FAIL',
            error=repr(exc),Native_optimize_calls=0,Master_Model_objects=1),indent=2)+'\n').encode())
        raise
    finally:
        model.dispose()


if __name__=='__main__':
    run(Path(__file__).resolve().parents[1]/'runtime/v42_trajectory_hull/coefficient_repair')
