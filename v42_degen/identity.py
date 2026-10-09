import hashlib
import numpy as np
from scipy import sparse
from .common import SOURCE,REF,OUT,NORMALAMPS,sha,read,write
from v42_integrated.matrix import arrays

def digest(value):
    a=np.asarray(value)
    if a.dtype.kind=='f':a=np.where(a==0.,0.,a)
    return hashlib.sha256(str(a.dtype).encode()+str(a.shape).encode()+np.ascontiguousarray(a).tobytes()).hexdigest()
def signature(A,d):
    return dict(matrix_indptr=digest(A.indptr),matrix_indices=digest(A.indices),matrix_coefficients=digest(A.data),objective=digest(d['objective']),objective_constant=digest(d['constant']),bounds_lower=digest(d['lower']),bounds_upper=digest(d['upper']),vtypes=digest(d['types']),RHS=digest(d['rhs']),senses=digest(d['sense']),variable_names=digest(d['names']))
def inputs():
    identity=read(REF/'M1_MODEL_IDENTITY.json');freeze=read(REF/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')
    assert freeze['PASS'] and freeze['source_data_sha256']==sha(SOURCE/'DATA.pkl')
    for key,path in [('full_MPS_sha256',SOURCE/'FULL.mps'),('reduced_MPS_sha256',SOURCE/'REDUCED.mps'),('matrix_sha256',SOURCE/'FULL_A.npz'),('data_sha256',SOURCE/'FULL_DATA.npz'),('A1_freeze_sha256',REF/'INTEGRATED_A1_FREEZE_SINGLE_THREAD.json')]:
        assert sha(path)==identity[key],key
    assert identity['NormalAmps_authority']==NORMALAMPS
    with np.load(SOURCE/'FULL_DATA.npz') as z:d={k:z[k] for k in z.files}
    A=sparse.load_npz(SOURCE/'FULL_A.npz')
    with np.load(SOURCE/'REDUCTION_AXES.npz') as z:keep=z['keep']
    reduced=A[keep];e=dict(d,rhs=d['rhs'][keep],sense=d['sense'][keep],row_names=d['row_names'][keep])
    return A,d,reduced,e,identity,freeze
def model(reduced,e,identity):
    import gurobipy as gp
    assert sha(SOURCE/'REDUCED.mps')==identity['reduced_MPS_sha256']
    m=gp.read(str(SOURCE/'REDUCED.mps'));m.Params.OutputFlag=1;m.Params.LogToConsole=0;m.Params.Threads=1
    B,f=arrays(m)
    same=np.array_equal(reduced.indptr,B.indptr) and np.array_equal(reduced.indices,B.indices) and np.array_equal(reduced.data,B.data)
    for key in ('objective','constant','lower','upper','types','rhs','sense','names'):same=same and np.array_equal(e[key],f[key])
    assert same,'PR134_SCIENTIFIC_MATRIX_IDENTITY_FAILED'
    assert (m.NumConstrs,m.NumVars,m.NumBinVars,B.nnz)==(886017,316743,208312,8447855)
    reference=signature(reduced,e);current=signature(B,f)
    assert current==reference,'PR134_PAYLOAD_FINGERPRINT_FAILED'
    return m,dict(PASS=True,PR134_exact_head='52ef855a59144a7c561df44b81dc2ad265babdbd',scientific_payload_equal=True,reference=reference,current=current,rows=m.NumConstrs,columns=m.NumVars,binaries=m.NumBinVars,nnz=B.nnz,cold_Gurobi_fingerprint=m.Fingerprint,signed_zero_semantics='Only IEEE +0/-0 normalized for scientific fingerprints; no nonzero rounding or tolerance comparison.',A1_freeze_sha256=identity['A1_freeze_sha256'],NormalAmps_authority_sha256=NORMALAMPS,source_data_sha256=sha(SOURCE/'DATA.pkl'),source_cache_reused_read_only=True,full_reduced_LP_gate=read(REF/'M1_SINGLE_THREAD_ROOT_LP_EQUIVALENCE.json')['PASS'],new_LP_solves=0,old_UB_LB_gap_used=False)
