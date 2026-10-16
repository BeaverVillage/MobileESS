"""V43 measured Runtime ledger with only the requested V44 stage ceiling changed."""
import ast
import inspect
import math
import textwrap
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from .common import atomic,read,record,digest
from .config import JOINT_SECONDS,K48_SECONDS,JOINT_CALL_CAP,require_day
from .frozen.v43_mess.budget import StageBudget as FrozenBudget


def _constructor():
    tree=ast.parse(textwrap.dedent(inspect.getsource(FrozenBudget.__init__)))
    constants=[n for n in ast.walk(tree) if isinstance(n,ast.Constant) and n.value==1800.]
    if len(constants)!=1:raise ValueError('FROZEN_STAGE_CEILING_BOUNDARY_DRIFT')
    constants[0].value=JOINT_SECONDS;ast.fix_missing_locations(tree)
    ns=dict(FrozenBudget.__init__.__globals__)
    # Zero-argument super carries a class closure; bind its original meaning explicitly.
    class Route(ast.NodeTransformer):
        def visit_Call(self,node):
            if isinstance(node.func,ast.Name) and node.func.id=='super' and not node.args:
                node.args=[ast.Name('FrozenBudget',ast.Load()),ast.Name('self',ast.Load())]
            return self.generic_visit(node)
    tree=Route().visit(tree);ast.fix_missing_locations(tree);ns['FrozenBudget']=FrozenBudget
    exec(compile(tree,inspect.getfile(FrozenBudget),'exec'),ns)
    return ns['__init__']


class StageBudget(FrozenBudget):
    __init__=_constructor()

    def persist(self):
        super().persist()
        # Metadata only: never rewrite an existing V43 ledger.
        doc=read(self.path);doc['policy_version']='V44_M300_J900_MEASURED_RUNTIME'
        doc['authorization']['schema']='V44_DATED_M_STAGE_NATIVE_AUTHORIZATION_V1'
        atomic(self.path,doc)

    def solve(self,model,*,label,cap,callback=None):
        from .execution import assert_current
        assert_current()
        from .runtime import current_identity
        from v42_may_campaign_native90.execution import current
        authority=current_identity(self.case);context=current()
        if (context is None or any(context['request'].get(k)!=authority[k] for k in ('source_sha','arm','stage','day'))):
            raise PermissionError('V44_LOCKED_DATED_STAGE_REQUIRED')
        if ('P2' in label.upper() or not math.isfinite(float(cap)) or cap<=0
                or self.kind=='PLANNING_NATIVE' and cap>JOINT_CALL_CAP):
            raise PermissionError('V44_ORIGINAL_NATIVE_CALL_CAP_REQUIRED')
        self._call_cap=float(cap)
        try:return super(FrozenBudget,self).native_optimize(model,callback,component='UB',track='M',label=label,requested_seconds=cap)
        finally:self._call_cap=None


def require_budget(budget,kind):
    if type(budget) is not StageBudget or budget.kind!=kind or budget.inflight is not None:
        raise PermissionError('V44_REAL_STAGE_BUDGET_REQUIRED')
    if getattr(budget.solve,'__func__',None) is not StageBudget.solve:raise PermissionError('NATIVE_OVERRIDE_FORBIDDEN')
    return budget


def resume(path,*,case,kind,destination,progress=None):
    """Resume only reconciled measured calls, with an immutable old ledger."""
    if Path(destination).exists():raise FileExistsError('RESUME_NEW_LEDGER_DESTINATION_REQUIRED')
    previous=read(path);context=dict(arm=case.identity['arm'],stage=('K48_' if kind=='K48_SEPARATE' else '')+case.identity['stage'],
        stage_case_sha=case.case_sha,source_sha=case.identity['source_sha'])
    if previous.get('stage_context')!=context:raise ValueError('RESUME_CROSS_CASE_OR_SOURCE')
    if previous.get('inflight') is not None:raise ValueError('RESUME_UNRECONCILED_NATIVE_INFLIGHT')
    ceiling=K48_SECONDS if kind=='K48_SEPARATE' else JOINT_SECONDS
    if previous.get('Native_ceiling_seconds')!=ceiling:raise ValueError('RESUME_CEILING_DRIFT')
    calls=previous['calls']
    if any(r.get('runtime_unavailable') or not isinstance(r.get('Native_Runtime'),(int,float))
        or not math.isfinite(r['Native_Runtime']) or r['Native_Runtime']<0 for r in calls):raise ValueError('RESUME_UNKNOWN_RUNTIME')
    measured=sum(r['Native_Runtime'] for r in calls)
    if abs(measured-previous['measured_Native_Runtime'])>1e-7:raise ValueError('RESUME_UNRECONCILED_TOTAL')
    budget=StageBudget(destination,case=case,kind=kind,progress=progress)
    budget.calls=deepcopy(calls);budget.costs=deepcopy(previous['costs']);budget.native_used=measured
    budget.authorization.update(resumed_same_stage=True,old_ledger=record(path),old_native_clocks_reused=True)
    budget.persist();return budget
