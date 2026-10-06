"""Durable terminal LP evidence before a strict, independent pricing gate.

This does not project Pi, relax its sign, or certify full-domain pricing.
The native row convention here is the unmodified minimization master.
"""
from pathlib import Path
import hashlib,json,uuid
import numpy as np
from scipy import sparse

EPS=1e-8
ROW_EPS=1e-6
ARRAY_FIELDS=('indptr','indices','data','shape','rhs','sense','lower','upper',
              'objective','constant','row_names','names','point','pi','rc')

def array_sha(value):
    a=np.ascontiguousarray(value)
    return hashlib.sha256(str(a.dtype).encode()+str(a.shape).encode()+a.tobytes()).hexdigest()

def canonical_dual(raw_pi,row_multiplier):
    """If stored row is s*(original row), canonical multiplier is s*Pi."""
    s=np.asarray(row_multiplier,dtype=float)
    if not np.isfinite(s).all() or np.any(s==0):raise ValueError('INVALID_ROW_TRANSFORMATION')
    return np.asarray(raw_pi,dtype=float)*s

def capture(model,path):
    """Read one terminal representation; persist *before* any acceptance gate."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() or path.with_suffix('.json').exists():raise FileExistsError('IMMUTABLE_DUAL_SNAPSHOT')
    if model.Status!=2 or model.IsMIP or model.ModelSense!=1 or model.NumObj!=1:
        raise ValueError('TERMINAL_SINGLE_OBJECTIVE_MIN_LP_REQUIRED')
    A=model.getA().tocsr()
    values=dict(indptr=A.indptr,indices=A.indices,data=A.data,shape=np.array(A.shape),
        rhs=np.asarray(model.getAttr('RHS')),sense=np.asarray(model.getAttr('Sense')),
        lower=np.asarray(model.getAttr('LB')),upper=np.asarray(model.getAttr('UB')),
        objective=np.asarray(model.getAttr('Obj')),constant=np.array(model.ObjCon),
        row_names=np.asarray(model.getAttr('ConstrName')),names=np.asarray(model.getAttr('VarName')),
        point=np.asarray(model.getAttr('X')),pi=np.asarray(model.getAttr('Pi')),rc=np.asarray(model.getAttr('RC')))
    optional={}
    for attr in ('BarPi','BarX','VBasis','CBasis'):
        try:values['raw_'+attr]=np.asarray(model.getAttr(attr));optional[attr]='SAVED_NOT_USED'
        except Exception:optional[attr]='UNAVAILABLE'
    identity={k:array_sha(values[k]) for k in ARRAY_FIELDS}
    meta=dict(origin=str(uuid.uuid4()),status=int(model.Status),model_sense=int(model.ModelSense),
        fingerprint=int(model.Fingerprint),native_objective=float(model.ObjVal),runtime=float(model.Runtime),
        parameters={k:model.getParamInfo(k)[2] for k in ('Method','Crossover','Threads','OptimalityTol','FeasibilityTol','Seed')},
        terminal_pair='X/Pi/RC queried from the same terminal model; BarPi/BarX never substituted',
        row_convention='Master build transports original CSR/RHS/senses verbatim; added convexity is equality.',
        original_to_native_row_multiplier=1,optional=optional,identity=identity)
    with path.open('xb') as stream:np.savez_compressed(stream,**values)
    meta['snapshot_SHA']=hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix('.json').write_text(json.dumps(meta,indent=2,allow_nan=False),encoding='utf8')
    return meta

def validate(path):
    path=Path(path);meta=json.loads(path.with_suffix('.json').read_text())
    with np.load(path,allow_pickle=False) as z:v={k:z[k] for k in ARRAY_FIELDS}
    identities={k:array_sha(v[k]) for k in ARRAY_FIELDS}
    identity=identities==meta['identity'] and hashlib.sha256(path.read_bytes()).hexdigest()==meta['snapshot_SHA']
    A=sparse.csr_matrix((v['data'],v['indices'],v['indptr']),shape=tuple(v['shape']))
    x,pi,rc=v['point'],v['pi'],v['rc'];sense=v['sense']
    finite=all(np.isfinite(v[k]).all() for k in ('point','pi','rc','rhs','objective','data'))
    sign=bool(np.all(pi[sense=='<']<=0) and np.all(pi[sense=='>']>=0))
    bad=np.flatnonzero(((sense=='<')&(pi>0))|((sense=='>')&(pi<0)))
    manual=v['objective']-A.T@pi;error=float(np.max(abs(manual-rc),initial=0))
    residual=A@x-v['rhs'];vio=np.maximum(0,np.where(sense=='=',abs(residual),np.where(sense=='<',residual,-residual)))
    bounds=float(max(0,np.max(v['lower']-x,initial=0),np.max(x-v['upper'],initial=0)))
    primal=float(v['objective']@x+v['constant'])
    # Native reduced costs include lower/upper-bound dual contributions.
    # Do not replace a nonzero RC at an infinite supporting bound with zero.
    selected=np.where(rc>=0,v['lower'],v['upper']);mask=rc!=0
    support_available=bool(np.all(np.isfinite(selected[mask])) and np.all(abs(selected[mask])<1e90))
    dual=float(pi@v['rhs']+v['constant']+rc[mask]@selected[mask]) if support_available else None
    difference=abs(primal-dual) if dual is not None else None
    strong=bool(support_available and difference<=EPS and abs(primal-meta['native_objective'])<=EPS)
    feasible=bool(vio.max(initial=0)<=ROW_EPS and bounds<=EPS)
    pair=meta['status']==2 and meta['model_sense']==1 and meta['original_to_native_row_multiplier']==1
    result=dict(PASS=bool(identity and finite and sign and error<=EPS and strong and feasible and pair),
        same_axis_SHA_PASS=identity,finite=finite,strict_sense_sign_PASS=sign,
        first_bad_row=None if not len(bad) else dict(index=int(bad[0]),name=str(v['row_names'][bad[0]]),sense=str(sense[bad[0]]),Pi=float(pi[bad[0]])),
        max_existing_column_RC_error=error,existing_column_RC_PASS=error<=EPS,
        strong_duality_PASS=strong,primal_objective=primal,dual_objective_including_bound_terms=dual,
        strong_duality_difference=difference,bound_terms_available=support_available,primal_feasible=feasible,
        max_row_violation=float(vio.max(initial=0)),max_bound_violation=bounds,
        exact_sign_not_projected=True,numerical_authority=EPS,affine_authority=ROW_EPS,
        full_domain_corrected_bound_certified=False,pricing_calls_authorized=False)
    path.with_suffix('.audit.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf8')
    return result

def require_terminal_dual(model,path):
    capture(model,path)
    result=validate(path)
    if not result['PASS']:raise ValueError('STOP_DUAL_AUTHORITY_UNRESOLVED:'+json.dumps(result,sort_keys=True))
    return result
