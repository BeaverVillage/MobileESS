"""Memoize pure anchor constants only for the fixed MESS coefficient tuple."""
from collections import OrderedDict
import sys
import numpy as np
import dayahead.v28r2.electrical_subproblem as electrical

def make_cache(coefficients, max_bytes):
 original=electrical.anchored_polygon_parameters
 allowed={id(c):c for c in coefficients};cache=OrderedDict()
 stats=dict(calls=0,hits=0,misses=0,bytes=0,limit_bytes=int(max_bytes))
 def parameters(c):
  stats['calls']+=1
  if id(c) not in allowed or allowed[id(c)] is not c:return original(c)
  key=id(c)
  if key in cache:
   stats['hits']+=1;values=cache.pop(key);cache[key]=values
  else:
   stats['misses']+=1;values=original(c)
   size=sum(v.nbytes for v in values)
   while cache and stats['bytes']+size>max_bytes:
    _,removed=cache.popitem(last=False);stats['bytes']-=sum(v.nbytes for v in removed)
   if size<=max_bytes:cache[key]=tuple(v.copy() for v in values);stats['bytes']+=size
  # Original callers receive independent writable arrays. A caller cannot
  # corrupt cached constants used by another candidate.
  return tuple(v.copy() for v in values)
 return parameters,stats,original

def install(coefficients,max_bytes):
 parameters,stats,original=make_cache(coefficients,max_bytes)
 # Replace only bindings to this exact pure function in this worker process.
 # Unchanged input matrices, constraints and objective arithmetic are retained.
 for module in list(sys.modules.values()):
  namespace=getattr(module,'__dict__',{})
  if namespace.get('anchored_polygon_parameters') is original:
   namespace['anchored_polygon_parameters']=parameters
 return stats
