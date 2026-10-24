"""Use the independent full-domain target for integer search termination."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import inspect,textwrap,linecache,gc,ast
from types import FunctionType
from contextvars import ContextVar
import math
from .io import atomic,now

POLISH=ContextVar('ITERATION2_FIXED_INTEGER_POLISH',default=False)


def support_exhausted(native,model,where,gp,folder):
 """A restricted bound may guide enlargement, never certify a global gap."""
 target=getattr(native,'_iteration2_target',None)
 if target is None or where!=gp.GRB.Callback.MIP:return
 bound=float(model.cbGet(gp.GRB.Callback.MIP_OBJBND))
 # Floating solver bounds only schedule a superset search. They never replace
 # the exact full-domain LB or authorize acceptance, pruning or graph deletion.
 threshold=math.nextafter(float(target),math.inf)+1e-6
 if math.isfinite(bound) and abs(bound)<1e90 and bound>threshold:
  atomic(Path(folder)/'RESTRICTED_SUPPORT_ENLARGEMENT.json',dict(UTC=now(),restricted_bound=bound,
   exact_acceptable_UB=str(target),reason='CURRENT_SUPPORT_BOUND_ABOVE_GLOBAL_TARGET',
   restricted_bound_is_global_certificate=False,scientific_acceptance_unchanged=True,
   prior_graphs_and_incumbent_retained=True,all_calls_in_same_native_account=True))
  model.terminate()


def configure(model,folder):
 if POLISH.get():
  if model.NumIntVars:raise ValueError('FIXED_INTEGER_POLISH_MUST_BE_CONTINUOUS')
  settings=dict(Method=0,Quad=1,Presolve=0,Aggregate=0,ScaleFlag=0,LPWarmStart=1,
   PerturbValue=0,NumericFocus=3,FeasibilityTol=1e-9,OptimalityTol=1e-9)
  for name,value in settings.items():model.setParam(name,value)
  atomic(Path(folder)/'ITERATION2_FIXED_INTEGER_NUMERICAL_POLICY.json',dict(PASS=True,UTC=now(),settings=settings,
   original_integer_decisions_fixed_exactly=True,acceptance_relaxed=False,shared_original_A_account=True))
  return dict(settings,iteration2_fixed_integer_polish=True)
 if not model.NumIntVars:return {}
 # A restricted-domain MIPGap is not the independently certified global gap.
 # The unchanged physical callback stops only at the original global target.
 settings=dict(MIPGap=0.,MIPGapAbs=0.)
 # The old last call spent 1205s in presolve and only 97s in the root LP.
 # Limit passes only for the observed large integer path, keep auto presolve
 # and barrier, and seek a qualifying incumbent against the certified P1 LB.
 if model.NumVars>=1000000:settings.update(PrePasses=3,MIPFocus=1)
 # The observed failure occurred during integer presolve, before root LP.
 # Bound aggregation fill and enable sparse reduction, keeping auto presolve
 # and barrier. No row, bound, type, physical option or RAM gate is changed.
 if model.NumVars>=3000000:settings.update(PreSparsify=1,AggFill=0)
 for name,value in settings.items():model.setParam(name,value)
 atomic(Path(folder)/'ITERATION2_INTEGER_SOLVER_POLICY.json',dict(PASS=True,UTC=now(),settings=settings,
  global_gap_target=.005,restricted_MIP_bound_used_as_global=False,
  original_independent_physical_and_global_gap_callback_retained=True,
  scientific_matrix_unchanged=True,tolerance_relaxed=False,RAM_admission_gate_added=False,
  MemLimit=str(model.Params.MemLimit),SoftMemLimit=str(model.Params.SoftMemLimit)))
 return dict(settings,iteration2_global_integer_target=True)


def compiled(function):
 source=textwrap.dedent(inspect.getsource(function))
 changes={
  '    build_started=perf_counter()':
   "    if component=='INTEGER_CONTROL':_iteration2_gc.collect()\n    build_started=perf_counter()",
  '    effective=apply_policy(model,self.policy,gp)':
   "    if component=='INTEGER_CONTROL':del compiled,delta,expected\n    effective=apply_policy(model,self.policy,gp)\n    if component=='INTEGER_CONTROL':effective.update(_iteration2_integer_configure(model,folder))",
  "FarkasDual_access=component=='NODE_LP',solver_policy_unchanged=True)":
   "FarkasDual_access=component=='NODE_LP',solver_policy_unchanged=not (effective.get('iteration2_global_integer_target',False) or effective.get('iteration2_fixed_integer_polish',False)))",
  '            telemetry.callback(m,w,gp.GRB)':
   "            telemetry.callback(m,w,gp.GRB)\n            if component=='INTEGER_CONTROL':_iteration2_support_exhausted(self,m,w,gp,folder)",
 }
 for old,new in changes.items():
  if source.count(old)!=1:raise ValueError('INTEGER_NATIVE_COMPILER_BOUNDARY_DRIFT:'+old)
  source=source.replace(old,new)
 filename=__file__+'.solve.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
 namespace=dict(function.__globals__,_iteration2_integer_configure=configure,_iteration2_gc=gc,_iteration2_support_exhausted=support_exhausted)
 exec(compile(source,filename,'exec'),namespace)
 return namespace[function.__name__]


def receipt_source(source):
 anchor='    day, inputs, output = _paths(request)'
 item="state['_campaign']['input_receipts']"
 if source.count(anchor)!=1 or source.count(item)!=2:raise ValueError('INTEGER_NATIVE_FACTORY_SOURCE_BOUNDARY_DRIFT')
 source=source.replace(item,'_iteration2_inputs')
 source=source.replace(anchor,anchor+"\n    _iteration2_inputs=dict(state['_campaign']['input_receipts'])")
 return source


def receipt_tree(tree):
 """Bind the actual A2 selective factory, which reads the original disk AST."""
 return ast.parse(receipt_source(ast.unparse(tree))).body[0]


def native_factory(function):
 """Source/input verification needs receipts, not the obsolete full state."""
 source=receipt_source(textwrap.dedent(inspect.getsource(function)))
 filename=__file__+'.native.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
 namespace=dict(function.__globals__);exec(compile(source,filename,'exec'),namespace)
 result=namespace[function.__name__]
 return FunctionType(result.__code__,function.__globals__,result.__name__,result.__defaults__,result.__closure__)


@contextmanager
def scope():
 from v42_a_stage_acceptance import native
 previous=native.Native.solve;function=compiled(previous)
 # Later stage scopes still bind their current numerical policy in this
 # module. Keep that live namespace instead of freezing an earlier policy.
 function=FunctionType(function.__code__,previous.__globals__,function.__name__,function.__defaults__,function.__closure__)
 with patch.object(native,'_iteration2_integer_configure',configure,create=True),patch.object(native,'_iteration2_gc',gc,create=True),patch.object(native,'_iteration2_support_exhausted',support_exhausted,create=True),patch.object(native.Native,'solve',function):yield
