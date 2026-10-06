"""Sparse affine screening with an outward-safe analytic PCS support bound."""
from fractions import Fraction as F
import numpy as np
from scipy import sparse
from v42_rowgen.core import binding_proof,security_axis
from .domain import suffix

def down(x):return np.nextafter(x,-np.inf)
def up(x):return np.nextafter(x,np.inf)
def outward(v):
 x=float(v);return (x if F(x)<=v else down(x),x if F(x)>=v else up(x))
def sparse_enclosure(C,T):
 v=C@T;mag=abs(C)@abs(T)
 n=np.diff(C.indptr)[:,None];k=2*n+4;u=np.finfo(float).eps/2
 error=up(4*(k*u/(1-k*u))*mag+(k+4)*np.nextafter(0.,1.))
 return down(v-error),up(v+error)

def affine_source(A,d,domain):
 sites=domain['sites'];N=len(sites);names=list(map(str,d['names']));lookup={n:i for i,n in enumerate(names)}
 definitions=binding_proof(A,d);anchors=set(i for i,j in definitions)
 T=np.zeros((A.shape[1],2*N),float);base=np.zeros((A.shape[1],1),float);times=np.full(A.shape[1],-1,int)
 definition={j:i for i,j in definitions};live=np.zeros((4,96,N),bool)
 for i,j in definitions:
  n=names[j];a,b=A.indptr[i:i+2]
  if not n.startswith('injection_'):continue
  site,tt=suffix(n);t=int(tt);s=sites.index(site);q=n.startswith('injection_Q');coord=s+N*q
  T[j,coord]=1;times[j]=t
  terms={names[k]:float(w) for k,w in zip(A.indices[a:b],A.data[a:b]) if k!=j}
  expected={}
  for z,u in enumerate(domain['units']):
   if q:
    key=f'Q[{u},{site},{t}]'
    if key in lookup:expected[key]=-1.;live[z,t,s]=True
   else:
    for f,c in [('Pch',1.),('Pdis',-1.)]:
     key=f'{f}[{u},{site},{t}]'
     if key in lookup:expected[key]=c
  assert terms==expected and d['rhs'][i]==0,('INJECTION_GRAPH_DRIFT',i,n,terms,expected)
 for i,j in definitions:
  if names[j].startswith('injection_'):continue
  a,b=A.indptr[i:i+2];js=A.indices[a:b];ws=A.data[a:b];mask=js!=j
  deps=js[mask];weights=ws[mask]
  tt=int(suffix(names[j])[0]);assert all(times[k]==tt for k in deps)
  coords=[]
  for k,w in zip(deps,weights):
   coord=int(np.flatnonzero(T[k])[0]);assert coord not in coords,'REPEATED_INJECTION_COORD'
   coords.append(coord);T[j,coord]=-float(w)
  times[j]=tt;base[j,0]=float(d['rhs'][i])
 assert np.all(domain['reach']<=live)
 return T,base,times,definitions,anchors

def support_bounds(cp_lo,cp_hi,domain,reach=None):
 """Return per-site PCS support upper enclosures for a chunk of rows."""
 N=len(domain['sites']);pL,pH=cp_lo[:,:N],cp_hi[:,:N];qL,qH=cp_lo[:,N:],cp_hi[:,N:]
 result=np.zeros(pL.shape)
 for p,q in domain['vertices']:
  pl,ph=outward(p);ql,qh=outward(q)
  # General interval product: vertices may be negative; coefficients may cross0.
  pt=up(np.maximum.reduce([pL*pl,pL*ph,pH*pl,pH*ph]));qt=up(np.maximum.reduce([qL*ql,qL*qh,qH*ql,qH*qh]))
  result=np.maximum(result,up(pt+qt))
 return result

def screen(A,d,domain):
 T,base,times,definitions,anchors=affine_source(A,d,domain);axis=security_axis(d)
 count=A.shape[0];upper=np.full(count,np.inf);all_upper=np.full(count,np.inf);box_upper=np.full(count,np.inf)
 zero=np.zeros(count,bool);rowtime=np.full(count,-1,int)
 rho=int(np.flatnonzero(d['names']=='rho_max')[0]);rholower=F(float(d['lower'][rho]));rhoupper=F(float(d['upper'][rho]))
 assert rholower==0
 for start in range(0,len(axis),4096):
  ix=axis[start:start+4096];C=A[ix].tocsr(copy=True);sgn=np.where(d['sense'][ix]=='>',-1.,1.);C=sparse.diags(sgn)@C
  C=C.tocsr();lo,hi=sparse_enclosure(C,T);bl,bh=sparse_enclosure(C,base);bh=bh[:,0]
  ts=[];extras=np.zeros(len(ix));constant=[]
  for z,i in enumerate(ix):
   a,b=C.indptr[z:z+2];js=C.indices[a:b];ws=C.data[a:b];tset=set(int(times[j]) for j in js if times[j]>=0)
   assert len(tset)<=1,'MULTITIME_SECURITY';t=next(iter(tset)) if tset else 0;ts.append(t);rowtime[i]=t
   # No other explicit decision families are permitted in security equations.
   for j,w in zip(js,ws):
    if times[j]<0:
     assert j==rho,'UNKNOWN_SECURITY_DECISION'
     extras[z]=outward(F(float(w))*(rhoupper if w>=0 else rholower))[1]
   # Exact-zero affine support can be known before any rounded products if
   # every source support is zero at every live reachable site. Cancellations
   # are left conservative here and handled by independent exact replay.
   active=np.any(domain['reach'][:,t],axis=0);active2=np.tile(active,2)
   constant.append(all(not np.any(T[j,active2]) for j,w in zip(js,ws) if w!=0))
  ts=np.asarray(ts);su=support_bounds(lo,hi,domain)
  reach_upper=bh.copy();unrestricted=bh.copy();naive=bh.copy()
  for m in range(4):
   mask=domain['reach'][m,ts,:]
   reach_upper=up(reach_upper+np.max(np.where(mask,su,0.),axis=1))
   unrestricted=up(unrestricted+np.max(su,axis=1))
   total=np.zeros(len(ix))
   for s in range(len(domain['sites'])):total=up(total+su[:,s])
   naive=up(naive+total)
  upper[ix]=up(reach_upper+extras);all_upper[ix]=up(unrestricted+extras);box_upper[ix]=up(naive+extras);zero[ix]=constant
 return dict(axis=axis,upper=upper,unrestricted_upper=all_upper,naive_upper=box_upper,zero=zero,rowtime=rowtime,definitions=definitions,anchors=anchors)
