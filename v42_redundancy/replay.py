"""Independent verifier. Does not import or call screening/deletion functions."""
import json,csv,hashlib,struct,itertools
from fractions import Fraction as Q
from collections import Counter
import numpy as np
from v42_degen.identity import inputs
from v42_strengthening.analysis import graph_inputs
from .common import OUT,write,sha

def original_row(A,d,i):
 a,b=A.indptr[i:i+2];sg=-1 if d['sense'][i]=='>' else 1
 js=A.indices[a:b];ws=sg*A.data[a:b];mask=ws!=0
 return js[mask],ws[mask],Q(sg*float(d['rhs'][i])),'=' if d['sense'][i]=='=' else '<'
def row_hash(A,d,i):
 js,ws,b,s=original_row(A,d,i)
 data=s.encode()+js.astype('<i8').tobytes()+np.where(ws==0,0.,ws).astype('<f8').tobytes()+struct.pack('<d',0. if b==0 else float(b))
 return hashlib.sha256(data).hexdigest()

def independent_sources(A,d,sites):
 vf=[str(n).split('[')[0] for n in d['names']];N=len(sites);named=list(map(str,d['names']));namedset=set(named)
 sources={};pivots={};anchors=set()
 for i,n in enumerate(d['row_names']):
  fam=str(n).split('[')[0]
  if not fam.endswith('_binding'):continue
  expected=fam[:-8];a,b=A.indptr[i:i+2];js=A.indices[a:b];ws=A.data[a:b]
  pp=[int(j) for j in js if vf[j]==expected];assert len(pp)==1 and d['sense'][i]=='='
  j=pp[0];assert float(ws[list(js).index(j)])==1 and j not in pivots
  pivots[j]=i;anchors.add(i)
 for j,i in pivots.items():
  if not vf[j].startswith('injection_'):continue
  ss,tt=named[j].split('[',1)[1][:-1].split(',');v=np.zeros(2*N);v[sites.index(ss)+N*(vf[j]=='injection_Q')]=1
  a,b=A.indptr[i:i+2]
  terms={named[k]:float(w) for k,w in zip(A.indices[a:b],A.data[a:b]) if k!=j and w!=0};expected={}
  for u in ['MESS01','MESS02','MESS03','MESS04']:
   for f,c in ([('Q',-1.)] if vf[j]=='injection_Q' else [('Pch',1.),('Pdis',-1.)]):
    key=f'{f}[{u},{ss},{tt}]'
    if key in namedset:expected[key]=c
  assert terms==expected and d['rhs'][i]==0,'INDEPENDENT_INJECTION_DEFINITION_FAIL'
  sources[j]=(v,0.,int(tt))
 for j,i in pivots.items():
  if j in sources:continue
  a,b=A.indptr[i:i+2];v=np.zeros(2*N);tt=None
  for k,w in zip(A.indices[a:b],A.data[a:b]):
   if k==j:continue
   assert int(k) in sources
   dep,c,t=sources[int(k)];assert c==0 and (tt is None or tt==t);tt=t
   pos=np.flatnonzero(dep);assert len(pos)==1 and v[pos[0]]==0
   v[pos[0]]=-float(w)
  if tt is None:tt=int(named[j].split('[',1)[1].split(',')[0])
  sources[j]=(v,float(d['rhs'][i]),tt)
 return sources,anchors

def exact_fixed_security(A,d,i,domain):
 js,ws,b,s=original_row(A,d,i)
 # A fixed physical flow with a free epigraph rho is NOT a violated constant
 # constraint. Its worst bound may fail while the original row remains feasible.
 if any(str(d['names'][j])=='rho_max' and w!=0 and d['lower'][j]!=d['upper'][j] for j,w in zip(js,ws)):return None
 sources,_=independent_sources(A,d,domain['sites']);js,ws,b,s=original_row(A,d,i);N=len(domain['sites']);coeff=[Q(0)]*(2*N);constant=Q(0);tt=0
 for j,w in zip(js,ws):
  if str(d['names'][j])=='rho_max':constant+=Q(float(w))*Q(float(d['upper'][j] if w>0 else d['lower'][j]));continue
  v,c,tt=sources[int(j)];constant+=Q(float(w))*Q(c)
  for k,val in enumerate(v):coeff[k]+=Q(float(w))*Q(float(val))
 for z in range(4):
  for k in np.flatnonzero(domain['reach'][z,tt]):
   if coeff[k] or coeff[k+N]:return None
 return constant

def fresh_reachability(A,d):
 sites,initial,arcs,battery,receipt=graph_inputs();units=sorted(initial);H=96
 result=np.zeros((4,H,len(sites)),bool)
 # Independent graph sweep in arc-index order: stays occur before travel in
 # the authority, so use iterative transitive closure until no additions.
 existing=set(map(str,d['names']))
 for z,u in enumerate(units):
  live=[(k,a) for k,a in enumerate(arcs) if f'arc[{u},{k}]' in existing]
  f={(initial[u],0)};changed=True
  while changed:
   before=len(f)
   for k,(s,t,v,e,r) in live:
    if (s,t) in f:f.add((v,e))
   changed=len(f)!=before
  back={(a[2],96) for k,a in live if a[3]==96};changed=True
  while changed:
   before=len(back)
   for k,(s,t,v,e,r) in reversed(live):
    if (v,e) in back:back.add((s,t))
   changed=len(back)!=before
  for k,(s,t,v,e,r) in live:
   if r is None and (s,t) in f and (v,e) in back:result[z,t,sites.index(s)]=True
 saved=json.loads((OUT/'M1_ROUTE_REACHABILITY_CERTIFICATE.json').read_text(encoding='utf-8'))
 for z,u in enumerate(units):
  for t in range(H):assert set(np.asarray(sites)[result[z,t]])==set(saved['reachable_connected_sites'][u][t])
 return sites,result

def independent_vertices(A,d):
 certificate=json.loads((OUT/'M1_PQ_ENVELOPE_CERTIFICATE.json').read_text(encoding='utf-8'))
 planes=[tuple(map(Q,p)) for p in certificate['PCS16_faces']]
 position=0
 for i,n in enumerate(d['row_names']):
  if str(n).split('[')[0]!='PCS16':continue
  a,b=A.indptr[i:i+2];terms={str(d['names'][j]):Q(float(w)) for j,w in zip(A.indices[a:b],A.data[a:b]) if w}
  p=next((v for k,v in terms.items() if k.startswith('Pdis[')),Q(0));q=next((v for k,v in terms.items() if k.startswith('Q[')),Q(0));c=-next(v for k,v in terms.items() if k.startswith('arc['))
  assert (p,q,c)==planes[position%16] and d['sense'][i]=='<' and d['rhs'][i]==0
  assert next((v for k,v in terms.items() if k.startswith('Pch[')),Q(0))==-p
  position+=1
 assert position==certificate['original_PCS_rows_checked']
 # Native connection P/Q bounds are independently checked by domain audit.
 planes += [(Q(1),Q(0),Q(300)),(Q(-1),Q(0),Q(300)),(Q(0),Q(1),Q(400)),(Q(0),Q(-1),Q(400))]
 points=set()
 for i in range(len(planes)):
  a,b,c=planes[i]
  for j in range(i):
   d,e,f=planes[j];det=a*e-d*b
   if det==0:continue
   x=(c*e-f*b)/det;y=(a*f-d*c)/det
   if all(p*x+q*y<=r for p,q,r in planes):points.add((x,y))
 assert points=={tuple(map(Q,p)) for p in certificate['PCS16_vertices']}
 def interval(x):
  v=float(x);return (v if Q(v)<=x else np.nextafter(v,-np.inf),v if Q(v)>=x else np.nextafter(v,np.inf))
 return [(interval(x),interval(y)) for x,y in sorted(points)]

def independent_security_bound(A,d,i,sources,reach,vertices):
 # Interval affine substitution via elementary operations, independently of
 # production sparse dot/gamma enclosure. Each source has exact stored factors.
 js,ws,rhs,s=original_row(A,d,i);N=reach.shape[2];lo=np.zeros(2*N);hi=lo.copy();constant_hi=0.;tt=None
 for j,w in zip(js,ws):
  if str(d['names'][j])=='rho_max':
   bound=float(d['upper'][j] if w>=0 else d['lower'][j]);assert abs(bound)<1e90
   term_hi=np.nextafter(float(w)*bound,np.inf)
   constant_hi=np.nextafter(constant_hi+term_hi,np.inf);continue
  v,c,t=sources[int(j)];assert tt is None or tt==t;tt=t
  p=np.asarray(float(w)*v);pl=np.nextafter(p,-np.inf);ph=np.nextafter(p,np.inf)
  lo=np.nextafter(lo+pl,-np.inf);hi=np.nextafter(hi+ph,np.inf)
  constant_hi=np.nextafter(constant_hi+np.nextafter(float(w)*c,np.inf),np.inf)
 if tt is None:tt=0
 values=np.zeros(N)
 for (xl,xh),(yl,yh) in vertices:
  p=np.nextafter(np.maximum.reduce([lo[:N]*xl,lo[:N]*xh,hi[:N]*xl,hi[:N]*xh]),np.inf)
  q=np.nextafter(np.maximum.reduce([lo[N:]*yl,lo[N:]*yh,hi[N:]*yl,hi[N:]*yh]),np.inf)
  values=np.maximum(values,np.nextafter(p+q,np.inf))
 ub=constant_hi
 for m in range(4):ub=np.nextafter(ub+float(np.max(values[reach[m,tt]],initial=0.)),np.inf)
 assert np.isfinite(ub)
 return ub,rhs

def verify_certificate(A,d,c,removed,sources=None,reach=None,vertices=None):
 i=int(c['original_row_id']);js,ws,rhs,s=original_row(A,d,i)
 # RHS is the round-trip decimal spelling of a stored IEEE float; reading it
 # as a decimal rational would incorrectly change the original authority.
 assert row_hash(A,d,i)==c['row_SHA256'];assert rhs==Q(float(c['RHS']))
 assert c['canonical_sense']==s and c['original_sense']==str(d['sense'][i])
 cat=c['category'];dom=c['dominator']
 if dom:
  j=int(dom);assert i!=j
  if j in removed:assert not removed[j]['dominator']
  ks,vs,b,r=original_row(A,d,j);assert s==r and np.array_equal(js,ks)
  if not len(ws):
   assert rhs==b if s=='=' or cat=='EXACT_DUPLICATE' else rhs>=b
  else:
   scale=Q(float(ws[0]))/Q(float(vs[0]));assert s=='=' or scale>0
   assert all(Q(float(x))==scale*Q(float(y)) for x,y in zip(ws,vs))
   assert rhs==scale*b if s=='=' else rhs>=scale*b
  if cat=='EXACT_DUPLICATE':assert np.array_equal(ws,vs) and rhs==b
  return 'EXACT_ROW_IMPLICATION',0
 assert s!='=','ONE_SIDED_EQUALITY_DELETION'
 if c['arithmetic_method']=='EXACT_BINARY_RATIONAL_VARIABLE_BOX':
  ub=Q(0)
  for j,w in zip(js,ws):
   v=float(d['upper'][j] if w>=0 else d['lower'][j]);assert abs(v)<1e90
   ub+=Q(float(w))*Q(v)
  assert ub==Q(c['certified_upper_bound']) and rhs-ub==Q(c['certified_slack']) and ub<rhs
  return 'EXACT_FINITE_BOUNDS',float(rhs-ub)
 ub,rhs=independent_security_bound(A,d,i,sources,reach,vertices)
 stored=Q(float(c['certified_upper_bound']))
 assert stored<=rhs-Q(1e-8)*max(Q(1),abs(rhs),abs(stored))
 assert rhs-stored==Q(c['certified_slack'])
 assert Q(ub)<=rhs-Q(1e-8)*max(Q(1),abs(rhs),abs(Q(ub))),('REPLAY_BOUND_FAIL',i,ub,float(rhs))
 return 'INDEPENDENT_ELEMENTARY_INTERVAL_PCS_SUPPORT',float(rhs-Q(ub))

def run():
 import time
 start=time.perf_counter();_,_,A,d,_,_=inputs();sites,reach=fresh_reachability(A,d);sources,anchors=independent_sources(A,d,sites);vertices=independent_vertices(A,d)
 with (OUT/'M1_REMOVED_ROW_CERTIFICATES.csv').open(encoding='utf-8') as f:removed={int(c['original_row_id']):c for c in csv.DictReader(f)}
 assert not anchors.intersection(removed),'REMOVED_AFFINE_ANCHOR'
 counts=Counter();slack=float('inf')
 for k,(i,c) in enumerate(removed.items()):
  method,margin=verify_certificate(A,d,c,removed,sources,reach,vertices);counts[method]+=1
  if margin:slack=min(slack,margin)
  if (k+1)%25000==0:print('INDEPENDENT_REPLAY',k+1,'wall',time.perf_counter()-start,flush=True)
 with np.load(OUT/'M1_REDUCTION_AXES.npz') as z:keep=z['keep'];gone=z['removed']
 assert set(gone)==set(removed) and len(keep)+len(gone)==A.shape[0]
 from scipy import sparse
 reduced=sparse.load_npz(OUT/'M1_EXACT_REDUCED_A.npz');expected=A[keep]
 assert np.array_equal(reduced.indptr,expected.indptr) and np.array_equal(reduced.indices,expected.indices) and np.array_equal(reduced.data,expected.data)
 # Mutation resistance: coefficient/RHS, upper/slack, missing or cyclic
 # dominator each rejected, without solving any optimization problem.
 mutations=[]
 for kind in ['ROW_HASH','RHS','UPPER_BOUND','SELF_DEPENDENCY']:
  source=next(c for c in removed.values() if bool(c['dominator'])==(kind=='SELF_DEPENDENCY'))
  c=dict(source)
  if kind=='ROW_HASH':c['row_SHA256']='0'*64
  elif kind=='RHS':c['RHS']=str(Q(c['RHS'])+1)
  elif kind=='UPPER_BOUND':c['certified_upper_bound']=str(Q(c['RHS'])+1)
  else:c['dominator']=c['original_row_id']
  rejected=False
  try:verify_certificate(A,d,c,removed,sources,reach,vertices)
  except (AssertionError,ValueError):rejected=True
  assert rejected;mutations.append(dict(mutation=kind,rejected=True))
 result=dict(PASS=True,rows_checked=len(removed),all_removed_rows_independently_verified=True,methods=dict(counts),minimum_independent_positive_slack=slack if np.isfinite(slack) else None,dependencies_closed=True,acyclic=True,retained_affine_anchors=len(anchors),reduced_matrix_is_exact_original_subset=True,independent_reachability_matches=True,exact_PCS_vertex_enumeration_matches=True,proof_mutation_tests=mutations,heavy_optimize_calls=0,wall=time.perf_counter()-start,decision_function_reused=False)
 write('M1_INDEPENDENT_CERTIFICATE_REPLAY.json',result);print('REPLAY_PASS',result,flush=True)
 return result
if __name__=='__main__':run()
