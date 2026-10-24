"""Stage-local P1 bases; exact basis-block inclusion across graph rebuilds."""
from contextvars import ContextVar
from collections import defaultdict
import hashlib
import numpy as np
from .io import atomic,now

START=ContextVar('ITERATION2_P1_BASIS_START',default=None)

def column_labels(state):
 """Physical descriptor roles, never rebuilt column positions, identify basics."""
 n=state['compact'].matrix.shape[1];labels=[None]*n
 for j in range(state['n']):labels[j]=('GLOBAL',j)
 roles=defaultdict(list)
 for key,meta in state['metas'].items():
  offset=meta['offset']
  for unit in meta['units']:
   for family,items in unit['v'].items():
    for event,expression in items.items():
     if expression[0]=='v':
      roles[offset+int(expression[1])].append((key,unit['id'],family,repr(event)))
  if 'residual_mass_column' in meta:
   labels[offset+meta['residual_mass_column']]=('MASS',key)
  for j,candidate in zip(meta.get('compact_path_columns',()),meta.get('candidates',())):
   labels[offset+j]=('PATH',key,repr(candidate['option']))
 for j,values in roles.items():labels[j]=('ROLE',tuple(sorted(values)))
 return labels

def row_key(snapshot,row,matrix):
 lo,hi=matrix.indptr[row:row+2]
 h=hashlib.sha256()
 h.update(str(snapshot.senses[row]).encode());h.update(np.float64(snapshot.rhs[row]).tobytes())
 h.update(np.asarray(matrix.indices[lo:hi],dtype=np.int64).tobytes())
 h.update(np.asarray(matrix.data[lo:hi],dtype=np.float64).tobytes())
 return h.digest()

def extended_basis(old,new,labels):
 """Preserve the old nonsingular basic minor; new row slacks complete it.

 The old basic structural columns and nonbasic-slack rows form a square
 nonsingular minor. Its exact permutation must occur in the new matrix.
 All remaining new rows have basic slacks, so the full new basis is block
 triangular with that same minor and an identity block. Bounds/RHS may make
 it infeasible, which is allowed for a warm basis, never a feasibility proof.
 """
 s=old['snapshot'];vb,cb=old['basis'];basic=np.flatnonzero(vb==0);rows=np.flatnonzero(cb==-1)
 if len(basic)!=len(rows):return None,'OLD_BASIC_COUNT_INVALID'
 positions=defaultdict(list)
 for j,label in enumerate(labels):
  if label is not None:positions[label].append(j)
 old_counts=defaultdict(int)
 for label in old['labels']:
  if label is not None:old_counts[label]+=1
 mapped=[]
 for j in basic:
  label=old['labels'][j]
  if label is None or old_counts[label]!=1 or len(positions[label])!=1:return None,'BASIC_COLUMN_IDENTITY_NOT_PRESERVED'
  mapped.append(positions[label][0])
 a=s.matrix[:,basic].tocsr();b=new.matrix[:,mapped].tocsr()
 for matrix in (a,b):matrix.sum_duplicates();matrix.eliminate_zeros();matrix.sort_indices()
 wanted={}
 for row in rows:
  signature=row_key(s,row,a)
  if signature in wanted:return None,'OLD_BASIC_MINOR_DUPLICATE_ROWS'
  wanted[signature]=int(row)
 found={}
 # Every nonbasic-slack row in a nonsingular minor contains a basic coefficient.
 sizes=np.unique(np.diff(a.indptr)[rows]);candidate_rows=np.flatnonzero(np.isin(np.diff(b.indptr),sizes))
 for row in candidate_rows:
  signature=row_key(new,row,b)
  if signature in wanted and signature not in found:found[signature]=int(row)
 if len(found)!=len(wanted):return None,'EXACT_BASIC_MINOR_NOT_PRESERVED'
 # Hashes select rows; direct array equality validates every selected entry.
 for signature,old_row in wanted.items():
  new_row=found[signature];al,ah=a.indptr[old_row:old_row+2];bl,bh=b.indptr[new_row:new_row+2]
  if not (np.array_equal(a.indices[al:ah],b.indices[bl:bh]) and np.array_equal(a.data[al:ah],b.data[bl:bh])):
   return None,'BASIC_MINOR_BYTES_DRIFT'
 v=np.where(new.lower>-1e100,-1,np.where(new.upper<1e100,-2,-3)).astype(np.int32)
 c=np.zeros(new.matrix.shape[0],dtype=np.int32)
 v[mapped]=0;c[list(found.values())]=-1
 return (v,c),'EXACT_BASIC_MINOR_EXTENDED'

class Bases:
 def __init__(self):self.previous=None
 def start(self,snapshot,state,fingerprint):
  old=self.previous
  if old is None:return dict(basis=None,reason='FIRST_P1_NO_PRIOR_BASIS',used=False)
  if fingerprint==old['fingerprint']:
   basis=old['basis'];reason='EXACT_SAME_SNAPSHOT'
  elif state is None or old['labels'] is None:
   basis=None;reason='NO_PHYSICAL_COLUMN_IDENTITIES'
  else:basis,reason=extended_basis(old,snapshot,column_labels(state))
  return dict(basis=basis,reason=reason,used=False,source=old['folder'])
 def remember(self,snapshot,state,fingerprint,raw,folder):
  if not all(k in raw for k in ('VBasis','CBasis')):return False
  vb=np.asarray(raw['VBasis']);cb=np.asarray(raw['CBasis'])
  if vb.shape!=(snapshot.matrix.shape[1],) or cb.shape!=(snapshot.matrix.shape[0],):return False
  if not np.all(np.isin(vb,(0,-1,-2,-3))) or not np.all(np.isin(cb,(0,-1))):return False
  if np.count_nonzero(vb==0)+np.count_nonzero(cb==0)!=len(cb):return False
  self.previous=dict(snapshot=snapshot,fingerprint=fingerprint,labels=column_labels(state) if state is not None else None,
   basis=(vb.astype(np.int32).copy(),cb.astype(np.int32).copy()),folder=str(folder))
  return True

def native_class(previous):
 class P1BasisNative(previous):
  def __init__(self,*args,**kwargs):
   super().__init__(*args,**kwargs);self._p1_bases=Bases();self._p1_state=None
  def set_p1_state(self,state):self._p1_state=state
  def solve(self,snapshot,folder,component):
   if component!='ORIGINAL_P1':return super().solve(snapshot,folder,component)
   fingerprint=self.p1_seed['snapshot_sha'] if self.p1_seed else snapshot.fingerprint()
   start=self._p1_bases.start(snapshot,self._p1_state,fingerprint);token=START.set(start)
   try:rec,raw=super().solve(snapshot,folder,component)
   finally:START.reset(token)
   saved=self._p1_bases.remember(snapshot,self._p1_state,fingerprint,raw,folder)
   atomic(folder/'ITERATION2_P1_BASIS_REUSE.json',dict(UTC=now(),reason=start['reason'],basis_supplied=start['used'],
    accepted_basis_saved=saved,source=start.get('source'),scope='ONE_A_STAGE_NO_DATE_OR_PARENT_REUSE',
    Method=2,Presolve=-1,LPWarmStart=2,basis_is_start_only=True,original_acceptance_unchanged=True))
   return rec,raw
 return P1BasisNative
