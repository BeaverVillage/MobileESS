"""Bounded existing graph promotion, exact sparse indexing, lossless disk links."""
from contextlib import contextmanager,ExitStack
from pathlib import Path
from unittest.mock import patch
import hashlib,inspect,linecache,textwrap,os
import numpy as np
import scipy.sparse as sp
from fractions import Fraction
from . import config as c
from .io import atomic,record,read,now

MAX_CLASSES=12
MAX_COLUMNS_PER_CLASS=20000
MAX_TOTAL_COLUMNS=200000

def selected(request):
 return request.get('arm')=='B3' and request.get('stage')=='A2' and request.get('iteration_stage') in ('A3','A4') and request.get('day') in c.DAYS

def promotion_wrapper(original,module):
 def apply(self,negative,data,qualified,folder,loader):
  # Spend the bounded complete-graph allowance on a demonstrated plateau,
  # rather than exhausting it on early classes while the objective improves.
  priced=read(Path(folder)/'FULL_PRICING_RESULT.json');value=Fraction(priced['active_objective_upper'])
  prior=getattr(self,'_iteration2_last_upper',None)
  plateau=prior is not None and abs(value-prior)<=Fraction(1,100000000)
  self._iteration2_last_upper=value
  with patch.object(module,'MAX_COLUMNS_PER_CLASS',MAX_COLUMNS_PER_CLASS if plateau else 0):
   result=original(self,negative,data,qualified,folder,loader)
  atomic(Path(folder)/'ITERATION2_P1_PLATEAU_ACCELERATION.json',dict(UTC=now(),plateau=plateau,prior_upper=str(prior) if prior is not None else None,current_upper=str(value),negative_classes=len(negative),promotion_eligibility_columns=MAX_COLUMNS_PER_CLASS if plateau else 0,maximum_total_columns=MAX_TOTAL_COLUMNS,original_exact_pricing_retained=True))
  return result
 return apply

def pricing_code(function):
 source=textwrap.dedent(inspect.getsource(function))
 changes={
  '    for i,(key,want) in enumerate(sorted(required.items())):':
   "    owned_by_class={}\n    for column,klass in owned.items():owned_by_class.setdefault(klass,[]).append(column)\n    for columns in owned_by_class.values():columns.sort()\n    coupling_matrix=original.matrix[list(axes.values())].tocsr()\n    for i,(key,want) in enumerate(sorted(required.items())):",
  "        cols=sorted(j for j,klass in owned.items() if klass==key);rows=list(local_rows.get(key,()))":
   "        cols=owned_by_class.get(key,[]);rows=list(local_rows.get(key,()))",
  "        active_B=original.matrix[list(axes.values())][:,cols].tocsr()":
   "        active_B=coupling_matrix[:,cols].tocsr()",
 }
 for old,new in changes.items():
  if source.count(old)!=1:raise ValueError('ITERATION2_PRICING_INDEX_SOURCE_DRIFT:'+old)
  source=source.replace(old,new)
 filename=__file__+'.pricing.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
 ns={};exec(compile(source,filename,'exec'),ns);return ns[function.__name__].__code__

class MatrixStorage:
 def __init__(self,root):self.root=Path(root).resolve();self.entries={};self.links=0;self.saved_bytes=0;self.writes=0;self.fallbacks=0
 def owned(self,path):
  if not isinstance(path,(str,os.PathLike)):return False
  p=Path(path)
  return p.name=='MATRIX.npz' and 'STATIC' in p.parts and 'NATIVE' in p.parts and p.resolve().is_relative_to(self.root)
 def saver(self,original):
  def save(path,matrix,compressed=True):
   if not self.owned(path) or matrix.format not in ('csr','csc'):return original(path,matrix,compressed=compressed)
   path=Path(path);h=hashlib.sha256(repr((matrix.shape,matrix.format,bool(compressed))).encode())
   for a in (matrix.indptr,matrix.indices,matrix.data):
    h.update(repr((a.shape,a.dtype.str)).encode());h.update(memoryview(np.ascontiguousarray(a)).cast('B'))
   key=h.hexdigest();prior=self.entries.get(key)
   # A repeated caller must never overwrite another hard link's bytes.
   if path.exists() and path.stat().st_nlink>1:path.unlink()
   if prior and not path.exists():
    try:
     source=Path(prior['path'])
     if record(source)==prior:
      path.parent.mkdir(parents=True,exist_ok=True);os.link(source,path)
      self.links+=1;self.saved_bytes+=prior['bytes'];return
    except (OSError,ValueError):self.fallbacks+=1
   original(path,matrix,compressed=compressed);self.writes+=1;self.entries[key]=record(path)
  return save
 def report(self):return dict(lossless=True,compressed_npz_retained=True,linked_matrices=self.links,avoided_duplicate_bytes=self.saved_bytes,unique_writes=self.writes,fallbacks=self.fallbacks,copy_on_write=True,raw_vectors_or_certificates_omitted=False)

@contextmanager
def scope():
 from v44_recovery_r031 import p1_expansion
 from v42_a_stage_canary import pricing
 # Imported aliases and routed function copies retain this code object.
 function=pricing.full_pricing;previous=function.__code__;compiled=pricing_code(function)
 storage=MatrixStorage(c.ROOT);save=sp.save_npz
 try:
  function.__code__=compiled
  with ExitStack() as stack:
   stack.enter_context(patch.object(p1_expansion,'selected',selected))
   stack.enter_context(patch.object(p1_expansion.Expansion,'apply',promotion_wrapper(p1_expansion.Expansion.apply,p1_expansion)))
   for name in ('MAX_CLASSES','MAX_COLUMNS_PER_CLASS','MAX_TOTAL_COLUMNS'):stack.enter_context(patch.object(p1_expansion,name,globals()[name]))
   stack.enter_context(patch.object(sp,'save_npz',storage.saver(save)))
   yield storage
 finally:
  function.__code__=previous
  atomic(c.OPS/'PERFORMANCE_LAST_WORKER.json',dict(UTC=now(),existing_complete_graph_promotion_all31_A3_A4=True,maximum_classes=MAX_CLASSES,maximum_columns_per_class=MAX_COLUMNS_PER_CLASS,maximum_total_promoted_columns=MAX_TOTAL_COLUMNS,
   sparse_coupling_rows_extracted_once_per_round=True,all_native_oracles_and_exact_certificates_retained=True,storage=storage.report()))
