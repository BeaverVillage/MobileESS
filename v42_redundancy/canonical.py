"""Exact rational canonicalization, independent of inherited row hash code."""
from fractions import Fraction as F
import math,hashlib,struct
import numpy as np
def row(A,d,i):
 a,b=A.indptr[i:i+2];sgn=-1 if d['sense'][i]=='>' else 1
 ws=sgn*A.data[a:b];js=A.indices[a:b];mask=ws!=0
 return js[mask],np.where(ws[mask]==0,0.,ws[mask]),sgn*float(d['rhs'][i]),'=' if d['sense'][i]=='=' else '<'
def payload(A,d,i,lhs=False):
 js,ws,b,s=row(A,d,i)
 return s.encode()+js.astype('<i8').tobytes()+ws.astype('<f8').tobytes()+(b'' if lhs else struct.pack('<d',0. if b==0 else b))
def proportional_key(A,d,i):
 js,ws,b,s=row(A,d,i)
 if not len(ws):return None,None
 # Every IEEE coefficient is dyadic. Integer primitive vector is unique.
 ratios=[float(w).as_integer_ratio() for w in ws]
 den=max(v for _,v in ratios)
 ints=[n*(den//q) for n,q in ratios]
 gcd=math.gcd(*ints)
 ints=[n//gcd for n in ints]
 # Inequality multiplier must remain positive. Equality may change sign.
 if s=='=' and ints[0]<0:ints=[-n for n in ints]
 scale=F(float(ws[0]))/ints[0]
 h=hashlib.sha256(s.encode()+js.astype('<i8').tobytes()+','.join(map(str,ints)).encode()).digest()
 return (h,tuple(map(int,js)),tuple(ints),s),F(b)/scale
def exact_box(A,d,i):
 js,ws,b,s=row(A,d,i)
 if s=='=':return None
 value=F(0)
 for j,w in zip(js,ws):
  v=float(d['upper'][j] if w>=0 else d['lower'][j])
  if not np.isfinite(v) or abs(v)>=1e90:return None
  value+=F(float(w))*F(v)
 return value
def exact_audits(A,d):
 dup={};pairs={};groups={};dom={};lhs={};collisions=0
 for i in range(A.shape[0]):
  p=payload(A,d,i);h=hashlib.sha256(p).digest()
  if h in dup:
   rep=dup[h];assert p==payload(A,d,rep),'HASH_COLLISION';pairs[i]=rep;collisions+=1
  else:dup[h]=i
  key,rhs=proportional_key(A,d,i)
  if key is None:continue
  h=key[0]
  if h in lhs:
   oldkey,oldrhs,rep=lhs[h];assert oldkey==key,'PROPORTIONAL_HASH_COLLISION'
   if key[-1]=='=':
    if rhs==oldrhs and i not in pairs:dom[i]=rep
   elif rhs>=oldrhs:
    if i not in pairs:dom[i]=rep
   else:
    dom[rep]=i;lhs[h]=(key,rhs,i)
  else:lhs[h]=(key,rhs,i)
 # Chase representatives, including exact duplicate of a weaker inequality.
 graph=dict(dom);graph.update(pairs)
 for i in list(graph):
  seen={i};j=graph[i]
  while j in graph:
   assert j not in seen,'CIRCULAR_PROOF';seen.add(j);j=graph[j]
  graph[i]=j
 return pairs,dom,graph,collisions
