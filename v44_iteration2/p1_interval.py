"""Reprice an unresolved exact interval; never turn an uncertain bound into PASS."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from unittest.mock import patch
from pathlib import Path
import inspect,textwrap,linecache
from .io import atomic,now

LEVEL=ContextVar('ITERATION2_P1_INTERVAL_PRECISION',default=0)
MAX_REFINEMENTS=2

def unresolved(priced,folder,snapshot,attempt,native):
 if priced.get('no_negative_omitted_block_certified') or priced.get('negative_blocks'):
  raise ValueError('P1_INTERVAL_REPAIR_WRONG_BRANCH')
 atomic(Path(folder)/'ITERATION2_UNRESOLVED_INTERVAL.json',dict(UTC=now(),snapshot_sha=snapshot.fingerprint(),
  attempt=attempt,maximum_refinements=MAX_REFINEMENTS,valid_full_domain_lower_bound=priced.get('full_domain_phase1_lower_bound'),
  minimum_STAY_reduced_cost_lower_bound=priced.get('min_stay_rc'),minimum_migration_reduced_cost_lower_bound=priced.get('min_migration_rc'),original_price_epsilon='1/100000000',
  no_negative_support=True,certificate_closure_forced=False,raw_points_bounds_and_objective_unchanged=True,
  all_extra_calls_charged_to_same_A5400_account=True))
 if attempt>=MAX_REFINEMENTS:raise ValueError('ITERATION2_P1_INTERVAL_REFINEMENT_EXHAUSTED_WITHOUT_CERTIFICATE')
 native.remaining();return attempt+1

def compiler(original):
 def compile_(function,namespace):
  compiled=original(function,namespace);source=textwrap.dedent(inspect.getsource(compiled))
  edits={
   '    traces=[]\n    while True:':'    traces=[];iteration2_interval_attempt=0\n    while True:',
   "        s=state['compact'];f=folder/'P1'/('S'+str(len(traces)))":"        _iteration2_interval_level.set(iteration2_interval_attempt)\n        s=state['compact'];f=folder/'P1'/('S'+str(len(traces)))",
   "        if not negative:raise ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')":
    "        if not negative:\n            iteration2_interval_attempt=_iteration2_interval_unresolved(priced,f,s,iteration2_interval_attempt,native)\n            p1point=raw['X']\n            continue",
   "        state,p1point=activate(state,negative,raw['X'],f,max_batch=len(negative))":
    "        state,p1point=activate(state,negative,raw['X'],f,max_batch=len(negative))\n        iteration2_interval_attempt=0",
  }
  for old,new in edits.items():
   if source.count(old)!=1:raise ValueError('ITERATION2_P1_INTERVAL_SOURCE_BOUNDARY_DRIFT:'+old)
   source=source.replace(old,new)
  namespace.update(_iteration2_interval_level=LEVEL,_iteration2_interval_unresolved=unresolved)
  name=__file__+'.phase.generated';linecache.cache[name]=(len(source),None,source.splitlines(True),name)
  exec(compile(source,name,'exec'),namespace);adapted=namespace['run']
  @wraps(adapted)
  def run(*args,**kwargs):
   token=LEVEL.set(0)
   try:return adapted(*args,**kwargs)
   finally:LEVEL.reset(token)
  return run
 return compile_

@contextmanager
def scope():
 from v44_recovery_r029 import p1_acceleration
 with patch.object(p1_acceleration,'compile_p1',compiler(p1_acceleration.compile_p1)):yield
