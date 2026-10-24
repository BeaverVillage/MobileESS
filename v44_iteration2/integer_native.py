"""Use the independent full-domain target for integer search termination."""
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import inspect,textwrap,linecache,gc,ast
from types import FunctionType
from .io import atomic,now


def configure(model,folder):
 if not model.NumIntVars:return {}
 # A restricted-domain MIPGap is not the independently certified global gap.
 # The unchanged physical callback stops only at the original global target.
 settings=dict(MIPGap=0.,MIPGapAbs=0.)
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
   "FarkasDual_access=component=='NODE_LP',solver_policy_unchanged=not effective.get('iteration2_global_integer_target',False))",
 }
 for old,new in changes.items():
  if source.count(old)!=1:raise ValueError('INTEGER_NATIVE_COMPILER_BOUNDARY_DRIFT:'+old)
  source=source.replace(old,new)
 filename=__file__+'.solve.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
 namespace=dict(function.__globals__,_iteration2_integer_configure=configure,_iteration2_gc=gc)
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
 with patch.object(native,'_iteration2_integer_configure',configure,create=True),patch.object(native,'_iteration2_gc',gc,create=True),patch.object(native.Native,'solve',function):yield
