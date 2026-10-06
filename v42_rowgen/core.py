"""All-row separation on the original IEEE coefficient authority.

Sparse products only screen with a conservative roundoff enclosure. Any
boundary-ambiguous row is evaluated using exact binary-rational arithmetic.
The retained/generated constraints themselves are never transformed.
"""
from fractions import Fraction as F
import hashlib
import numpy as np
from scipy import sparse

SECURITY = frozenset(('line_thermal_face','voltage_lower','voltage_upper',
                      'NormalAmps','transformer_current','transformer_kVA'))
BINDINGS = frozenset(('injection_P_binding','injection_Q_binding',
                     'response_line_P_binding','response_line_Q_binding',
                     'response_line_correction_binding',
                     'response_transformer_P_binding','response_transformer_Q_binding'))
GRID_VARIABLES = frozenset(f[:-8] for f in BINDINGS)
TOL = 1e-8

def families(names):
    return np.asarray([str(n).split('[',1)[0] for n in names])

def security_axis(d):
    return np.flatnonzero(np.isin(families(d['row_names']),list(SECURITY)))

def exact_residual(A,d,x,i):
    a,b=A.indptr[i:i+2]
    r=sum((F(float(w))*F(float(x[j])) for j,w in zip(A.indices[a:b],A.data[a:b])),F(0))-F(float(d['rhs'][i]))
    s=str(d['sense'][i])
    return abs(r) if s=='=' else r if s=='<' else -r

def separate(A,d,x,axis=None,tolerance=TOL):
    """Exhaustively certify every requested row, including zero-nnz rows.

    Return ALL violations. There is no cap, top-K or near-critical acceptance.
    Enclosure accounts for multiplication, accumulation and rhs subtraction;
    subnormal operations are paid absolutely. Ambiguity triggers exact F.
    """
    if not np.isfinite(x).all(): raise ValueError('NONFINITE_POINT')
    if tolerance<0: raise ValueError('NEGATIVE_TOLERANCE')
    axis=np.arange(A.shape[0]) if axis is None else np.asarray(axis,dtype=np.int64)
    C=A[axis].tocsr(); rhs=d['rhs'][axis]; sense=d['sense'][axis]
    raw=C@x-rhs
    if not np.isin(sense,['<','>','=']).all():raise ValueError('UNSUPPORTED_ORIGINAL_SENSE')
    lengths=np.diff(C.indptr).astype(float)
    u=np.finfo(float).eps/2
    k=2*lengths+4
    if np.any(k*u>=1): raise ValueError('ROUNDING_ENCLOSURE_UNSUPPORTED')
    magnitude=abs(C)@abs(x)+abs(rhs)
    # Extra factor four covers the roundoff in computing magnitude itself.
    error=np.nextafter(4*(k*u/(1-k*u))*magnitude+(k+4)*np.nextafter(0.,1.),np.inf)
    if not np.isfinite(raw).all() or not np.isfinite(error).all():raise ValueError('NONFINITE_RESIDUAL_ENCLOSURE')
    vio=np.where(sense=='=',abs(raw),np.where(sense=='<',raw,-raw))
    lo=np.nextafter(vio-error,-np.inf); hi=np.nextafter(vio+error,np.inf)
    ambiguous=np.flatnonzero((lo<=tolerance)&(hi>tolerance))
    bad=lo>tolerance
    exactmax=F(0)
    for q in ambiguous:
        r=exact_residual(A,d,x,int(axis[q]));bad[q]=r>F(float(tolerance));exactmax=max(exactmax,r)
    return dict(checked_rows=len(axis),violated=axis[bad],ambiguous_exact_checks=len(ambiguous),
                maximum_upper=float(np.max(hi,initial=0)),PASS=not bool(np.any(bad)),
                evaluator='IEEE roundoff-enclosed sparse dot; exact binary-rational boundary fallback',
                tolerance=tolerance)

def row_digest(A,d,i):
    a,b=A.indptr[i:i+2]
    h=hashlib.sha256()
    for v in (A.indices[a:b].astype('<i8'),A.data[a:b].astype('<f8'),
              np.array([d['rhs'][i]],dtype='<f8')):h.update(v.tobytes())
    h.update(str(d['sense'][i]).encode())
    return h.hexdigest()

class OriginalRows:
    """Monotone original-index subset, with immutable coefficient transport."""
    def __init__(self,A,d,initial_security=()):
        self.A=A.tocsr();self.d=d;self.grid=security_axis(d)
        self.present=np.ones(A.shape[0],dtype=bool);self.present[self.grid]=False
        initial=np.asarray(initial_security,dtype=np.int64)
        if not np.isin(initial,self.grid).all():raise ValueError('INITIAL_ROW_NOT_GRID')
        self.present[initial]=True
    @property
    def axis(self):return np.flatnonzero(self.present)
    def pending(self,x):
        r=separate(self.A,self.d,x,self.grid[~self.present[self.grid]])
        return r
    def add(self,indices):
        indices=np.unique(np.asarray(indices,dtype=np.int64))
        if not np.isin(indices,self.grid).all():raise ValueError('ROW_NOT_ORIGINAL_GRID')
        fresh=indices[~self.present[indices]];self.present[fresh]=True
        return fresh
    def final(self,x):
        # Always all original grid rows, regardless of active subset.
        return separate(self.A,self.d,x,self.grid)

def binding_proof(A,d):
    """Native singleton pivots and two-level dependency proof, no LP solve."""
    vf=families(d['names']);rf=families(d['row_names'])
    aux=np.flatnonzero(np.isin(vf,list(GRID_VARIABLES)))
    definitions=[];seen=set()
    for i in np.flatnonzero(np.isin(rf,list(BINDINGS))):
        a,b=A.indptr[i:i+2];js=A.indices[a:b];ws=A.data[a:b]
        fam=str(rf[i])[:-8]
        piv=js[vf[js]==fam]
        if len(piv)!=1:raise ValueError('NON_SINGLETON_AFFINE_PIVOT')
        j=int(piv[0]);p=float(ws[np.flatnonzero(js==j)[0]])
        if p!=1. or str(d['sense'][i])!='=':raise ValueError('NONUNIT_NATIVE_PIVOT')
        if j in seen:raise ValueError('MULTIPLE_AUX_DEFINITIONS')
        seen.add(j)
        dependencies=js[js!=j]
        if fam.startswith('injection_'):
            allowed=('Pch','Pdis') if fam=='injection_P' else ('Q',)
        else:allowed=('injection_P','injection_Q')
        if not np.isin(vf[dependencies],allowed).all():raise ValueError('NONAFFINE_GRID_DEPENDENCY')
        if d['types'][j]!='C' or abs(d['lower'][j])<1e90 or abs(d['upper'][j])<1e90 or d['objective'][j]!=0:
            raise ValueError('GRID_AUX_NATIVE_ATTRIBUTE_CHANGED')
        definitions.append((int(i),j))
    if seen!=set(map(int,aux)):raise ValueError('MISSING_AUX_DEFINITION')
    non_grid=np.flatnonzero(~np.isin(rf,list(SECURITY|BINDINGS)))
    if A[non_grid][:,aux].nnz:raise ValueError('GRID_AUX_IN_TEMPORAL_PHYSICS')
    return definitions

def affine_extend(A,d,x,definitions):
    """Diagnostic unique affine extension, not incumbent repair."""
    x=np.array(x,copy=True)
    for i,j in sorted(definitions,key=lambda ij:not str(d['names'][ij[1]]).startswith('injection_')):
        a,b=A.indptr[i:i+2];js=A.indices[a:b];ws=A.data[a:b]
        mask=js!=j
        value=F(float(d['rhs'][i]))-sum((F(float(w))*F(float(x[k])) for k,w in zip(js[mask],ws[mask])),F(0))
        x[j]=float(value)
    return x
