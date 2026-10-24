"""Bounded existing graph promotion, exact sparse indexing, lossless disk links."""
from contextlib import contextmanager,ExitStack
from pathlib import Path
from unittest.mock import patch
import hashlib,inspect,linecache,textwrap,os
import json
import numpy as np
import scipy.sparse as sp
from fractions import Fraction
from . import config as c
from .io import atomic,record,read,now

MAX_CLASSES=3
MAX_COLUMNS_PER_CLASS=8000
MAX_TOTAL_COLUMNS=20000

def streaming_domain_digest(value):
 """Byte-identical canonical SHA without a giant joined JSON string."""
 h=hashlib.sha256()
 def sequence(items):
  h.update(b'[')
  for offset in range(0,len(items),4096):
   if offset:h.update(b',')
   # Keep the source C encoder fast, but serialize at most4096 items. Each
   # batch loses only its outer brackets; list element bytes stay canonical.
   batch=json.dumps(items[offset:offset+4096],sort_keys=True,separators=(',',':'),default=str,allow_nan=False)
   h.update(batch[1:-1].encode())
  h.update(b']')
 if type(value) in (list,tuple):sequence(value)
 elif type(value) is dict and all(type(key) is str for key in value):
  # Full-domain identities are dictionaries of large stays/blocks sequences.
  # Python iterencode walks every scalar; retain the C encoder in bounded
  # top-level chunks instead, with exactly the original canonical JSON bytes.
  h.update(b'{')
  for index,key in enumerate(sorted(value)):
   if index:h.update(b',')
   h.update(json.dumps(key).encode());h.update(b':');item=value[key]
   if type(item) in (list,tuple):sequence(item)
   else:h.update(json.dumps(item,sort_keys=True,separators=(',',':'),default=str,allow_nan=False).encode())
  h.update(b'}')
 else:h.update(json.dumps(value,sort_keys=True,separators=(',',':'),default=str,allow_nan=False).encode())
 return h.hexdigest()

def domain_digest_code():
 from v42_a_stage_domain_v2 import domain
 if domain.digest.__code__ is streaming_domain_digest.__code__:return streaming_domain_digest.__code__
 source=textwrap.dedent(inspect.getsource(domain.digest))
 if source.count('json.dumps(')!=1 or 'allow_nan=False' not in source or "separators=(',', ':')" not in source:
  raise ValueError('ORIGINAL_DOMAIN_DIGEST_CANONICAL_SCHEMA_DRIFT')
 return streaming_domain_digest.__code__

def selected(request):
 return request.get('arm')=='B3' and request.get('stage')=='A2' and request.get('iteration_stage') in ('A3','A4') and request.get('day') in c.DAYS

def bind_pricing(namespace):
 """Bind to the actual selective A compiler, independent of legacy wrappers."""
 from .adapters import ACTIVE
 request=ACTIVE.get()
 if not request or not selected(request) or namespace.get('_iteration2_direct_pricing_bound'):return
 from v44_recovery_r031 import p1_expansion
 from v42_a_stage_phase1.runner import load_cache
 original=namespace['full_pricing'];expansion=p1_expansion.Expansion();output=Path(request['output'])
 def full_pricing(*args,**kwargs):
  priced,negative=original(*args,**kwargs)
  if args[2] is None and not kwargs.get('zero',False):
   negative=expansion.apply(negative,args[5],read(output/'BLOCK_PRICING_ORACLE_VERIFICATION.json'),Path(args[13]),load_cache)
  return priced,negative
 namespace['full_pricing']=full_pricing;namespace['_iteration2_direct_pricing_bound']=True
 atomic(output/'ITERATION2_PERFORMANCE_BINDING.json',dict(PASS=True,UTC=now(),day=request['day'],iteration_stage=request['iteration_stage'],binding='ACTUAL_SELECTIVE_P1_COMPILER_SHARED_NAMESPACE',source=record(__file__),legacy_active_request_stack_required=False,all_native_pricing_retained=True))

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
 from v42_a_stage_domain_v2 import domain
 digest_function=domain.digest;old_digest=digest_function.__code__;digest_code=domain_digest_code()
 storage=MatrixStorage(c.ROOT);save=sp.save_npz
 try:
  function.__code__=compiled
  digest_function.__code__=digest_code
  with ExitStack() as stack:
   # The selective A body can bypass worker.a_stage's legacy request stack.
   # Its compiler now binds directly below; suppress duplicate legacy binding.
   stack.enter_context(patch.object(p1_expansion,'selected',lambda request:False))
   stack.enter_context(patch.object(p1_expansion.Expansion,'apply',promotion_wrapper(p1_expansion.Expansion.apply,p1_expansion)))
   for name in ('MAX_CLASSES','MAX_COLUMNS_PER_CLASS','MAX_TOTAL_COLUMNS'):stack.enter_context(patch.object(p1_expansion,name,globals()[name]))
   stack.enter_context(patch.object(sp,'save_npz',storage.saver(save)))
   yield storage
 finally:
  function.__code__=previous
  digest_function.__code__=old_digest
  atomic(c.OPS/'PERFORMANCE_LAST_WORKER.json',dict(UTC=now(),existing_complete_graph_promotion_all31_A3_A4=True,maximum_classes=MAX_CLASSES,maximum_columns_per_class=MAX_COLUMNS_PER_CLASS,maximum_total_promoted_columns=MAX_TOTAL_COLUMNS,
   sparse_coupling_rows_extracted_once_per_round=True,all_native_oracles_and_exact_certificates_retained=True,storage=storage.report()))
