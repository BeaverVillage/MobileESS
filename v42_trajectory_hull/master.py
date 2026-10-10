"""Original-row DW master with reversible power-of-two row scaling."""
from fractions import Fraction as F
from time import perf_counter
import numpy as np
from scipy import sparse
from v42_m1_hybrid.blocks import verify_decomposition, output_directory
from v42_m1_research.check_ub import matrix_replay, vector_sha
from .case import file_sha
from .budget import write
from .scaling import row_scaling


def audit_transport(expected, actual, nonunit_columns):
    delta = (actual-expected).tocoo()
    delta.eliminate_zeros()
    if delta.nnz:
        raise ValueError('DW_NATIVE_MATRIX_DRIFT')
    return dict(all_coefficients_exact=True, derived_lambda_differences=0,
                native_master_objective_certificate_authority=False,
                search_transport='BIT_EXACT_POWER_TWO_SCALING')



def build_master(case, decomp, columns, output):
    import gurobipy as gp
    begin = perf_counter()
    output = output_directory(output)
    verify_decomposition(case, decomp)
    source_rows = np.sort(np.concatenate((decomp.nonunit_block.original_rows,decomp.coupling_rows)))
    nonunit = decomp.nonunit_columns
    pieces = [case.A[source_rows][:,nonunit].tocsr()]
    objective = list(case.d['objective'][nonunit])
    catalog = []
    exact_products = []
    for unit,block in decomp.units.items():
        source = case.A[source_rows][:,block.original_columns].tocsr()
        candidates = [(case.point[block.original_columns],'ORIGINAL_VERIFIED_UB_SEED')]
        for item in columns.get(unit,[]):
            if not item.get('admission',{}).get('PASS'):
                continue
            if file_sha(item['path']) != item['sha256']:
                raise ValueError('GENERATED_COLUMN_BYTE_DRIFT')
            z=np.load(item['path'],allow_pickle=False)
            if not np.array_equal(z['original_columns'],block.original_columns):
                raise ValueError('GENERATED_COLUMN_ORIGINAL_AXIS_DRIFT')
            candidates.append((z['point'],item['path']))
        seen=set()
        for point, provenance in candidates:
            admission=matrix_replay(block.A,block.d,point)
            if not admission['PASS'] or not admission['integer_pattern_exact'] or not admission['exact_binary_0_1']:
                raise ValueError('FULL96_NUMERICAL_COLUMN_ADMISSION_FAIL')
            digest=vector_sha(point)
            if digest in seen:
                continue
            seen.add(digest)
            values=[];indices=[];exact={}
            for i in np.flatnonzero(np.diff(source.indptr)):
                a,b=source.indptr[i:i+2]
                value=sum((F(float(w))*F(float(point[j])) for j,w in
                           zip(source.indices[a:b],source.data[a:b])),F(0))
                if value:
                    values.append(float(value));indices.append(int(i));exact[str(int(i))]=str(value)
            # Preserve the original failed master's float64 CSR column payload.
            weighted = np.asarray(source @ point).reshape(-1)
            pieces.append(sparse.csr_matrix(weighted.reshape(-1,1)))
            cost=sum((F(float(c))*F(float(point[j])) for j,c in enumerate(block.d['objective']) if c),F(0))
            objective.append(float(cost))
            exact_products.append(exact)
            catalog.append(dict(unit=unit,point_sha=digest,source=provenance,
                                membership='NUMERICALLY_FEASIBLE_INTEGER_PATTERN_SEARCH_ONLY',
                                exact_objective_product=str(cost)))
    n=len(nonunit);k=len(catalog);units=list(decomp.units)
    convex=sparse.lil_matrix((len(units),n+k))
    for j,column in enumerate(catalog):
        convex[units.index(column['unit']),n+j]=1.
    matrix=sparse.vstack((sparse.hstack(pieces,format='csr'),convex.tocsr()),format='csr')
    rhs=np.concatenate((case.d['rhs'][source_rows],np.ones(len(units))))
    senses=np.concatenate((case.d['sense'][source_rows],np.full(len(units),'=')))
    lower=np.concatenate((case.d['lower'][nonunit],np.zeros(k)))
    upper=np.concatenate((case.d['upper'][nonunit],np.ones(k)))
    scaled, scaled_rhs, exponents = row_scaling(matrix, rhs)
    model=gp.Model('V42_FULL96_INTEGER_TRAJECTORY_DW_SEARCH_MASTER')
    try:
        model.Params.OutputFlag=0;model.Params.Method=1
        v=model.addMVar(n+k,lb=lower,ub=upper,vtype='C',obj=np.asarray(objective))
        model.ObjCon=float(case.d['constant'])
        constraints=model.addMConstr(scaled,v,senses,scaled_rhs)
        model.update()
        audit=audit_transport(scaled,model.getA(),n)
        if not np.array_equal(np.asarray(model.getAttr('RHS')),scaled_rhs):
            raise ValueError('ORIGINAL_GRID_RHS_NATIVE_DRIFT')
        if not np.array_equal(np.asarray(model.getAttr('Sense')),senses):
            raise ValueError('ORIGINAL_GRID_SENSE_NATIVE_DRIFT')
        receipt=dict(case_sha=case.case_sha,rows=model.NumConstrs,columns=model.NumVars,
                     row_scale_exponents={str(int(i)):int(exponents[i]) for i in np.flatnonzero(exponents)},
                     column_scaling='IDENTITY', primal_recovery='IDENTITY', dual_recovery='y=R*y_solver',
                     generated_columns=k,source_rows=source_rows.tolist(),catalog=catalog,
                     exact_original_grid_rows_preserved_in_mathematical_master=True,
                     native_transport=audit,build_wall_seconds=perf_counter()-begin,
                     original_grid_nonunit_columns=n,restricted_master_is_Global_LB=False,
                     full_integer_hull_closure='NOT_PROVEN')
        write(output/'EXACT_DERIVED_COLUMN_PRODUCTS.json',exact_products)
        write(output/'MASTER_IDENTITY.json',receipt)
        return model,v,constraints,receipt,source_rows
    except BaseException:
        model.dispose()
        raise
