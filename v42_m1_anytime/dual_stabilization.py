"""Stage-local exact dual search. Computational ranks never certify a Global LB.

For finite boxes B(y)=c0+b'y+sum min((c-A'y)l,(c-A'y)u) is concave.
On a dual segment its only kinks are residual sign crossings. Tracking their
nonpositive slope jumps finds the exact best weight, including very small
weights omitted by a fixed grid. Only the existing independent checker can
admit the resulting same-stage proposal; no solver, model or physics is changed.
"""
from dataclasses import asdict,dataclass
from fractions import Fraction as F
from hashlib import sha256
import json
import math
import re
import numpy as np

GRID=(F(0),F(1,8),F(1,4),F(1,2),F(3,4),F(1))
STAGES={'B2_M','B3_M1','B3_M2'}

@dataclass(frozen=True)
class StageIdentity:
    stage:str
    day:str
    source_sha:str
    input_sha:str
    fixed_input_sha:str
    case_sha:str
    matrix_sha:str
    domain_sha:str

    def __post_init__(self):
        if self.stage not in STAGES or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',self.day):
            raise ValueError('STAGE_IDENTITY_REQUIRED')
        for key,value in asdict(self).items():
            if key not in ('stage','day') and not re.fullmatch('[0-9a-f]{64}',value):
                raise ValueError('STAGE_SOURCE_INPUT_MATRIX_DOMAIN_SHA_REQUIRED:'+key)

    @property
    def sha(self):return sha256(json.dumps(asdict(self),sort_keys=True).encode()).hexdigest()

def dual_sha(dual):
    return sha256('\n'.join(f'{i}:{F(dual[str(i)])}' for i in sorted(map(int,dual))
        if F(dual[str(i)])).encode('ascii')).hexdigest()

def checked_dual(A,d,dual):
    result={}
    for key,value in dual.items():
        i=int(key)
        if str(i)!=str(key) or not 0<=i<A.shape[0]:raise ValueError('DUAL_ROW_AXIS_DRIFT')
        q=F(value);sense=str(d['sense'][i])
        if sense not in ('<','>','=') or (sense=='<' and q>0) or (sense=='>' and q<0):
            raise ValueError('INVALID_DUAL_ROW_SIGN')
        if q:result[str(i)]=str(q)
    return result

def mix(best,new,alpha):
    alpha=F(alpha)
    if not 0<=alpha<=1:raise ValueError('CONVEX_WEIGHT_REQUIRED')
    return {k:str(q) for k in sorted(set(best)|set(new),key=int)
        if (q:=(1-alpha)*F(best.get(k,'0'))+alpha*F(new.get(k,'0')))}

def _domain(A,d):
    if A.shape!=(len(d['rhs']),len(d['objective'])):raise ValueError('MATRIX_DOMAIN_AXIS_DRIFT')
    for name in ('lower','upper','objective'):
        if np.asarray(d[name]).shape!=(A.shape[1],):raise ValueError('VARIABLE_AXIS_DRIFT')
    for name in ('rhs','sense'):
        if np.asarray(d[name]).shape!=(A.shape[0],):raise ValueError('ROW_AXIS_DRIFT')
    if not all(np.isfinite(np.asarray(d[k],dtype=float)).all()
        for k in ('lower','upper','objective','rhs','constant')) or not np.isfinite(A.data).all():
        raise ValueError('FINITE_ORIGINAL_BOX_REQUIRED')
    if np.any(np.asarray(d['lower'])>np.asarray(d['upper'])):raise ValueError('EMPTY_BOX')
    if not set(map(str,d['sense'])).issubset({'<','>','='}):raise ValueError('ROW_SENSE_DRIFT')

def _terms(A,d,dual):
    products={};rhs=F(0)
    for key,value in dual.items():
        i=int(key);q=F(value);rhs+=q*F(float(d['rhs'][i]))
        a,b=A.indptr[i:i+2]
        for j,v in zip(A.indices[a:b],A.data[a:b]):
            j=int(j);products[j]=products.get(j,F(0))+q*F(float(v))
    residual={j:q for j in set(products)|set(map(int,np.flatnonzero(d['objective'])))
        if (q:=F(float(d['objective'][j]))-products.get(j,F(0)))}
    return rhs,residual

def _box_value(d,terms):
    rhs,residual=terms
    correction=sum((r*F(float(d['lower'][j] if r>0 else d['upper'][j]))
        for j,r in residual.items()),F(0))
    return F(float(np.asarray(d['constant']).item()))+rhs+correction

def ray_maximum(A,d,base,new):
    """Exact segment maximum, without claiming an independent certificate."""
    A=A.tocsr();_domain(A,d)
    base=checked_dual(A,d,base);new=checked_dual(A,d,new)
    t0=_terms(A,d,base);t1=_terms(A,d,new);value=_box_value(d,t0)
    slope=t1[0]-t0[0];jumps={};crossings=0
    for j in set(t0[1])|set(t1[1]):
        r0=t0[1].get(j,F(0));dr=t1[1].get(j,F(0))-r0
        if not dr:continue
        lo=F(float(d['lower'][j]));hi=F(float(d['upper'][j]))
        slope+=dr*(lo if r0>0 or (r0==0 and dr>0) else hi)
        alpha=-r0/dr
        if 0<alpha<1:
            crossings+=1;jumps[alpha]=jumps.get(alpha,F(0))-(hi-lo)*abs(dr)
    best=value;best_alpha=F(0);previous=F(0);initial=slope
    for alpha in sorted(jumps):
        value+=slope*(alpha-previous)
        if value>best:best=value;best_alpha=alpha
        slope+=jumps[alpha];previous=alpha
    value+=slope*(1-previous)
    if value>best:best=value;best_alpha=F(1)
    return dict(alpha=str(best_alpha),exact_computational_box_bound=str(best),
        baseline_computational_box_bound=str(_box_value(d,t0)),initial_slope=str(initial),
        residual_crossings=crossings,distinct_breakpoints=len(jumps),
        independent_certificate=False,Global_LB_claimed=False)

def repair_equalities(A,d,dual):
    """Preserve rational input and inequality multipliers; cancel affine helpers."""
    A=A.tocsr();_domain(A,d);dual=checked_dual(A,d,dual)
    q={int(i):F(v) for i,v in dual.items()};family=lambda n:str(n).split('[',1)[0]
    names=[family(n) for n in d['names']];definitions={}
    for i,name in enumerate(d['row_names']):
        f=family(name)
        if not f.endswith('_binding') or d['sense'][i]!='=':continue
        a,b=A.indptr[i:i+2];matches=[int(j) for j in A.indices[a:b] if names[int(j)]==f[:-8]]
        if len(matches)!=1 or matches[0] in definitions:raise ValueError('UNIQUE_ORIGINAL_AFFINE_PIVOT_REQUIRED')
        definitions[matches[0]]=i
    used={j:set() for j in definitions};dependencies={}
    for j,i in definitions.items():
        a,b=A.indptr[i:i+2];dependencies[j]={int(k) for k in A.indices[a:b] if int(k)!=j and int(k) in definitions}
        for k in dependencies[j]:used[k].add(j)
    ready=[j for j in definitions if not used[j]];order=[]
    while ready:
        j=ready.pop();order.append(j)
        for k in dependencies[j]:
            used[k].remove(j)
            if not used[k]:ready.append(k)
    if len(order)!=len(definitions):raise ValueError('AFFINE_DEFINITION_CYCLE')
    products={}
    for i,v in q.items():
        a,b=A.indptr[i:i+2]
        for j,w in zip(A.indices[a:b],A.data[a:b]):
            j=int(j);products[j]=products.get(j,F(0))+v*F(float(w))
    changed=0
    for j in order:
        i=definitions[j];a,b=A.indptr[i:i+2];terms=list(zip(A.indices[a:b],A.data[a:b]))
        pivot=next(F(float(w)) for k,w in terms if int(k)==j)
        correction=(F(float(d['objective'][j]))-products.get(j,F(0)))/pivot
        if not correction:continue
        q[i]=q.get(i,F(0))+correction
        if not q[i]:del q[i]
        for k,w in terms:
            k=int(k);products[k]=products.get(k,F(0))+correction*F(float(w))
        changed+=1
    if any(products.get(j,F(0))!=F(float(d['objective'][j])) for j in definitions):
        raise ValueError('AFFINE_RESIDUAL_NOT_EXACT_ZERO')
    result=checked_dual(A,d,{str(i):str(v) for i,v in q.items()})
    return result,dict(changed_equalities=changed,auxiliary_columns=len(definitions),
        inequality_multipliers_unchanged=True,Native_calls=0,Global_LB_claimed=False)

class DualSearch:
    """One stage/attempt owns proposal deduplication and bounded rescue evidence."""
    def __init__(self,identity,*,max_exact=2,min_gain=F(1,1000),max_rescues=1,finite_box=None):
        if type(identity) is not StageIdentity:raise ValueError('VERIFIED_STAGE_IDENTITY_REQUIRED')
        if type(max_exact) is not int or not 1<=max_exact<=2:raise ValueError('AT_MOST_TWO_EXACT_CHECKS')
        if type(max_rescues) is not int or not 0<=max_rescues<=1:raise ValueError('AT_MOST_ONE_LB_RESCUE')
        self.identity=identity;self.max_exact=max_exact;self.min_gain=F(min_gain)
        if self.min_gain<=0:raise ValueError('POSITIVE_RESEARCH_MATERIALITY_REQUIRED')
        self.max_rescues=max_rescues;self.seen=set();self.priced=set();self.pending=None;self.rescues=0
        self.master_catalogs=set()
        self.source_pairs=set()
        if finite_box is not None and not callable(finite_box):raise ValueError('PROVED_FINITE_BOX_PROVIDER_REQUIRED')
        self.finite_box=finite_box

    def select(self,case,base,new,baseline_lb,*,certify):
        if case.case_sha!=self.identity.case_sha:raise ValueError('STAGE_CASE_IDENTITY_DRIFT')
        A=case.A.tocsr();d=case.d;box_proof=None
        if not np.isfinite(d['lower']).all() or not np.isfinite(d['upper']).all():
            if self.finite_box is None:
                checked_dual(A,d,base);new=checked_dual(A,d,new)
                return dict(status='NOT_RUN_FINITE_BOX_PROOF_NOT_PREPARED',identity=asdict(self.identity),
                    dual=new,Global_LB_published=False)
            lo,hi,box_proof=self.finite_box(A,d)
            replay=box_proof.get('independent_replay',{})
            if box_proof.get('PASS') is not True or replay.get('PASS') is not True or replay.get('all_original_feasible_points_contained') is not True:
                raise ValueError('INDEPENDENT_ORIGINAL_EQUALITY_BOX_PROOF_REQUIRED')
            # The selected model and its original domain remain byte-identical.
            # Only computational candidate ranks use the proved envelope.
            d=dict(d,lower=np.array(lo,copy=True),upper=np.array(hi,copy=True))
        _domain(A,d)
        base=checked_dual(A,d,base);new=checked_dual(A,d,new)
        pair=self.identity.sha+':'+dual_sha(base)+':'+dual_sha(new)
        if pair in self.source_pairs:return dict(status='NON_NOVEL',identity=asdict(self.identity),dual=new)
        self.source_pairs.add(pair)
        repaired,repair=repair_equalities(A,d,new);proposals=[];local=set()
        for label,end in (('RMP',new),('AFFINE_REPAIRED_RMP',repaired)):
            ray=ray_maximum(A,d,base,end)
            for alpha in (*GRID,F(ray['alpha'])):
                dual=mix(base,end,alpha);fingerprint=dual_sha(dual)
                if fingerprint==dual_sha(base) or fingerprint in local:continue
                local.add(fingerprint);key=self.identity.sha+':'+fingerprint
                if key in self.seen or key in self.priced:continue
                score=_box_value(d,_terms(A,d,dual))
                proposals.append((score,key,label,str(alpha),dual,ray))
        proposals.sort(key=lambda x:(-x[0],x[1]))
        if not proposals:return dict(status='NON_NOVEL',identity=asdict(self.identity),repair=repair,dual=new)
        checks=[];best=None
        for score,key,label,alpha,dual,ray in proposals[:self.max_exact]:
            self.seen.add(key) # Failures and nonimproving trials are consumed too.
            cert=certify(dual)
            if cert.get('PASS') is not True or cert.get('case_sha')!=self.identity.case_sha:
                raise ValueError('INDEPENDENT_SAME_STAGE_CERTIFICATE_REQUIRED')
            value=F(cert['exact_bound'])
            checks.append(dict(key=key,alpha=alpha,proposal=label,exact_independent_bound=str(value),
                computational_rank_bound=str(score),Global_LB_published=False))
            if best is None or value>best['value']:
                best=dict(value=value,key=key,alpha=alpha,proposal=label,dual=dual,certificate=cert,ray=ray)
        gain=best['value']-F(baseline_lb)
        status='QUALIFIED' if gain>=self.min_gain else 'VALID_PROPOSAL'
        return dict(status=status,identity=asdict(self.identity),identity_sha=self.identity.sha,
            dual=best['dual'],key=best['key'],alpha=best['alpha'],certificate=best['certificate'],
            certified_gain=str(gain),checks=checks,repair=repair,ray=best['ray'],
            computational_box_proof=box_proof,Global_LB_published=False)

    def pricing_key(self,decomp,dual,kind='LP_ONLY'):
        rows=set(map(int,decomp.coupling_rows))|set(map(int,decomp.nonunit_block.original_rows))
        active={str(i):dual[str(i)] for i in rows if str(i) in dual and F(dual[str(i)])}
        return self.identity.sha+':'+kind+':'+dual_sha(active)

    def consume_pricing(self,decomp,dual,kind='LP_ONLY'):
        key=self.pricing_key(decomp,dual,kind)
        if key in self.priced:return False
        self.priced.add(key) # Consume before delegation, including failures.
        return True

    def record_rmp(self,catalog_sha):
        if not re.fullmatch('[0-9a-f]{64}',catalog_sha):raise ValueError('CATALOG_SHA_REQUIRED')
        self.master_catalogs.add(catalog_sha)

    def record_pricing(self,dual,certificate,certified_gain,*,new_catalog_sha=None):
        if certificate.get('PASS') is not True or certificate.get('case_sha')!=self.identity.case_sha:
            raise ValueError('SAME_STAGE_PRICING_CERTIFICATE_REQUIRED')
        if (F(certified_gain)>=self.min_gain and self.rescues<self.max_rescues
                and new_catalog_sha is not None and new_catalog_sha not in self.master_catalogs):
            if not re.fullmatch('[0-9a-f]{64}',new_catalog_sha):raise ValueError('CATALOG_SHA_REQUIRED')
            self.pending=dict(catalog_sha=new_catalog_sha,certificate=dict(certificate),identity_sha=self.identity.sha)

    def take_rescue(self,history,remaining,gap):
        if not math.isfinite(float(remaining)) or float(remaining)<210 or F(gap)<=F(3,100):return None
        if self.pending is None or self.rescues>=self.max_rescues:return None
        if self.pending['catalog_sha'] in self.master_catalogs:return None
        recent=history[-8:]
        if len(recent)<8 or any(r['method'].startswith('L') and r['certified_gain']>0 for r in recent):return None
        result=self.pending;self.pending=None;self.rescues+=1
        return dict(**result,method='L2',reason='NOVEL_SAME_STAGE_CERTIFIED_GAIN_BOUNDED_LB_RESCUE')
