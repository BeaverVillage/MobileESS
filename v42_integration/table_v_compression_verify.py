"""Independent universal matrix checks for the persisted LP sum projection.

This checker does not call the compression constructor or trust its PASS,
packet digests or semantic class labels. It checks each original coefficient,
global equation, box and P1 objective against the produced actual sparse CSR.
"""
from collections import Counter
from fractions import Fraction
import hashlib
import numpy as np
import scipy.sparse as sp


def array_equal(a,b):
    a=np.asarray(a);b=np.asarray(b)
    return a.shape==b.shape and a.dtype==b.dtype and a.tobytes()==b.tobytes()


def csr_equal(a,b):
    a=a.tocsr();b=b.tocsr()
    if not a.has_sorted_indices:a=a.copy();a.sort_indices()
    if not b.has_sorted_indices:b=b.copy();b.sort_indices()
    return a.shape==b.shape and all(array_equal(getattr(a,k),getattr(b,k)) for k in ('indptr','indices','data'))


def require(condition,reason):
    if not condition:raise ValueError(reason)


def exact_multiplier(original,compressed,N,*,native_infinity=False):
    require(len(original)==len(compressed),'BOX_OR_RHS_AXIS_DRIFT')
    for a,b in zip(original,compressed):
        if native_infinity and abs(float(a))>=1e100:
            require(float(a)==float(b),'NATIVE_INFINITY_BOUND_DRIFT')
        else:require(Fraction(float(a))*N==Fraction(float(b)),'NONEXACT_SUM_BOX_OR_RHS')


def verify_sum(source,result):
    target=result['snapshot'];fold=np.asarray(result['fold']);prefix=int(result['prefix'])
    require(len(fold)==source.matrix.shape[1] and np.array_equal(fold[:prefix],np.arange(prefix)),'PROJECTION_COLUMN_COVERAGE')
    grows=np.asarray(result['global_rows']);ng=len(grows)
    # Exact forward identity: A_global = C_global * F, where Y=F*X is a sum.
    # Column gathering performs no coefficient additions or rounding.
    original_global=source.matrix[grows].tocsr()
    reconstructed=target.matrix[:ng][:,fold].tocsr()
    require(csr_equal(original_global,reconstructed),'GLOBAL_COUPLING_FORWARD_IDENTITY_FAILED')
    require(array_equal(source.rhs[grows],target.rhs[:ng]),'GLOBAL_RHS_DRIFT')
    require(array_equal(source.senses[grows],target.senses[:ng]),'GLOBAL_SENSE_DRIFT')
    require(array_equal(source.lower[:prefix],target.lower[:prefix]) and array_equal(source.upper[:prefix],target.upper[:prefix]),'GLOBAL_BOX_DRIFT')
    require(np.all(target.vtypes=='C'),'LP_SCOPE_ONLY_REQUIRED')
    cursor=ng;covered_columns=set(range(prefix));covered_rows=set(map(int,grows));members=[];proof=[]
    for record in result['records']:
        us=record['members'];N=len(us);offset=record['offset'];width=record['width'];nr=record['local_rows']
        require(N==record['cardinality'] and N>0,'CLASS_MULTIPLICITY_DRIFT')
        newcols=np.arange(offset,offset+width);newrows=np.arange(cursor,cursor+nr)
        compressed_local=target.matrix[newrows][:,newcols].tocsr()
        # A local row must contain no variable belonging to another class or global prefix.
        require(target.matrix[newrows].nnz==compressed_local.nnz,'CROSS_CLASS_LOCAL_COUPLING')
        reference=None
        for uid in us:
            cols=np.asarray(record['source_columns'][uid],dtype=np.int64);rows=np.asarray(record['source_rows'][uid],dtype=np.int64)
            require(len(cols)==width and len(rows)==nr,'LOCAL_SOURCE_AXIS_DRIFT')
            require(not covered_columns.intersection(map(int,cols)),'DUPLICATED_UID_COLUMN')
            require(not covered_rows.intersection(map(int,rows)),'DUPLICATED_UID_ROW')
            covered_columns.update(map(int,cols));covered_rows.update(map(int,rows));members.append(uid)
            old=source.matrix[rows][:,cols].tocsr()
            require(source.matrix[rows].nnz==old.nnz,'SOURCE_LOCAL_CROSS_CLASS_ROW')
            require(csr_equal(old,compressed_local),'LOCAL_BINARY64_COEFFICIENT_DRIFT')
            require(array_equal(source.senses[rows],target.senses[newrows]),'LOCAL_SENSE_DRIFT')
            exact_multiplier(source.rhs[rows],target.rhs[newrows],N)
            exact_multiplier(source.lower[cols],target.lower[newcols],N,native_infinity=True)
            exact_multiplier(source.upper[cols],target.upper[newcols],N,native_infinity=True)
            require(np.array_equal(fold[cols],newcols),'LOCAL_SUM_PROJECTION_AXIS_DRIFT')
            require(np.all(np.asarray(result['scale'])[cols]==N),'INVERSE_CARDINALITY_DRIFT')
        proof.append(dict(class_id=record['class_id'],cardinality=N,UIDs=list(us),rows_checked=N*nr,columns_checked=N*width))
        cursor+=nr
    require(cursor==target.matrix.shape[0],'UNOWNED_COMPRESSED_ROW')
    require(covered_columns==set(range(source.matrix.shape[1])),'UNOWNED_SOURCE_COLUMN')
    require(covered_rows==set(range(source.matrix.shape[0])),'UNOWNED_SOURCE_ROW')
    require(len(members)==len(set(members)),'DUPLICATED_UID')
    for before,after in zip(source.objectives,target.objectives):
        require(before.name==after.name and Fraction(before.constant)==Fraction(after.constant),'OBJECTIVE_IDENTITY_DRIFT')
        c,d=before.coefficients(),after.coefficients()
        require(all(c.get(j,Fraction(0))==d.get(int(fold[j]),Fraction(0)) for j in range(len(fold))),'P1_OR_LOCAL_OBJECTIVE_COEFFICIENT_DRIFT')
    require(len(source.objectives)==len(target.objectives),'OBJECTIVE_LAYER_COUNT_DRIFT')
    return dict(PASS=True,scope='CONTINUOUS_LP_ONLY',classes=len(proof),UIDs=len(members),
        global_rows_checked=ng,original_rows_checked=source.matrix.shape[0],original_columns_checked=len(fold),
        every_binary64_local_and_coupling_coefficient_checked=True,exact_rhs_bounds_and_objective_checked=True,
        forward='Y_class = sum(X_uid). Each same local inequality and bound is summed exactly.',
        inverse='X_uid = Y_class/N over the rationals. Convexity proves every original local row and bound.',
        original_integer_model_retained=True,integer_decomposition_claimed=False,
        old_LB_UB_Gap_transferred=False,native_optimize_calls=0,records=proof)


def verify_redundancy(source,reduced,receipt):
    retained=receipt['retained_rows'];retained_set=set(retained);covered=set(retained)
    require(csr_equal(source.matrix[retained],reduced.matrix),'REDUNDANCY_RETAINED_MATRIX_DRIFT')
    require(array_equal(source.rhs[retained],reduced.rhs) and array_equal(source.senses[retained],reduced.senses),'REDUNDANCY_RETAINED_RHS_DRIFT')
    for duplicate,original in receipt['exact_duplicates']:
        require(original in retained_set,'DUPLICATE_AUTHORITY_ROW_NOT_RETAINED')
        require(csr_equal(source.matrix[duplicate],source.matrix[original]),'FALSE_DUPLICATE_ROW')
        require(source.rhs[duplicate]==source.rhs[original] and source.senses[duplicate]==source.senses[original],'FALSE_DUPLICATE_RHS')
        covered.add(duplicate)
    for row in receipt['constant_tautologies']:
        require(source.matrix[row].nnz==0,'FALSE_CONSTANT_ROW')
        b=Fraction(float(source.rhs[row]));sense=source.senses[row]
        require((sense=='=' and b==0) or (sense=='<' and b>=0) or (sense=='>' and b<=0),'FALSE_TAUTOLOGY')
        covered.add(row)
    require(covered==set(range(source.matrix.shape[0])),'DELETED_ROW_WITHOUT_PROOF')
    require(all(array_equal(getattr(source,k),getattr(reduced,k)) for k in ('lower','upper','vtypes')),'REDUNDANCY_COLUMN_OR_TYPE_DRIFT')
    require(source.objectives==reduced.objectives,'REDUNDANCY_OBJECTIVE_DRIFT')
    return dict(PASS=True,exact_duplicates=len(receipt['exact_duplicates']),constant_tautologies=len(receipt['constant_tautologies']),
                LP_and_integer_row_equivalence=True,unproved_inequality_deletions=0)
