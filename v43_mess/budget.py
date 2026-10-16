"""V43 stage authority; inherited measured-Native accounting and no P2."""
from contextlib import contextmanager, ExitStack
from pathlib import Path
import os
import math

import psutil

from v43.common import ROOT, RUNS, read, record, verify_records, atomic
from v42_may_campaign_native90.budget import DateBudget


@contextmanager
def worker_permit(request, sources):
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign import execution as legacy
    from v42_may_campaign_native90 import execution as inherited
    from v42_may_campaign_native90 import budget as inherited_budget
    valid=(request['arm']=='B2' and request['stage']=='M1') or (request['arm']=='B3' and request['stage'] in ('M1','M2','A2'))
    if request['day'] != '2025-05-01' or not valid:
        raise PermissionError('V43_MAY01_EXPLICIT_ARM_STAGE_ONLY')
    with ExitStack() as stack:
        locks=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
        locks += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
        locks += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
        for path in locks:stack.enter_context(exclusive_lock(path))
        verify_records(sources)
        old=(legacy.guard,inherited.guard,inherited_budget.guard)
        original=inherited.guard
        def guard(model):
            verify_records(sources)
            original(model)
        token=legacy._active.set(dict(request=request,manifest=dict(schema='V43_MAY01_STAGE_PERMIT_V1'),
            worker_slot=None,manifest_sha=request['source_sha']))
        legacy.guard=inherited.guard=inherited_budget.guard=guard
        try:yield
        finally:
            legacy.guard,inherited.guard,inherited_budget.guard=old
            legacy._active.reset(token)


class StageBudget(DateBudget):
    """Keep original ledger/guard, honoring the original per-call Joint/K caps."""
    def __init__(self,path,*,case,kind,progress=None):
        if kind not in ('PLANNING_NATIVE','K48_SEPARATE'):raise ValueError('M_BUDGET_KIND')
        self.kind=kind;self.case=case;self._call_cap=None
        self.context=dict(arm=case.identity['arm'],stage=('K48_' if kind=='K48_SEPARATE' else '')+case.identity['stage'],
            stage_case_sha=case.case_sha,source_sha=case.identity['source_sha'])
        self.authorization=dict(schema='V43_MAY01_M_STAGE_NATIVE_AUTHORIZATION_V1',budget_kind=kind,
            context=self.context,old_native_clocks_reused=False)
        super().__init__(path,native_limit=300. if kind=='K48_SEPARATE' else 1800.,progress=progress)

    def remaining(self,reserve=None):
        left=super().remaining(reserve)
        return left if self._call_cap is None else min(left,self._call_cap)

    def check(self,reserve=0):
        if (self.path.parent/'STOP_REQUESTED.json').exists():raise RuntimeError('V43_M_OFFICIAL_STOP_REQUESTED')
        # Existing TableV M budgets subtract measured Runtime and admit no
        # next call when exhausted. A solver's actual TimeLimit overshoot is
        # recorded honestly rather than discarding its returned valid bound.
        return None

    def charge(self,runtime):
        if not math.isfinite(float(runtime)) or runtime<0:raise ValueError('NONFINITE_NATIVE_RUNTIME')
        self.native_used+=float(runtime);self.persist()
        if self.native_used>self.native_limit:
            atomic(self.path.with_name(self.path.stem+'_MEASURED_CEILING_OVERRUN.json'),dict(
                measured_Native_seconds=self.native_used,requested_ceiling_seconds=self.native_limit,
                overrun_seconds=self.native_used-self.native_limit,next_native_call_permitted=False,
                original_policy='TableVStageBudget.remaining: max(0, cap - measured Runtime)',
                source=record(ROOT/'v43_mess/budget.py')))

    def solve(self,model,*,label,cap,callback=None):
        from .library import current_identity
        from v42_may_campaign_native90.execution import current
        authority=current_identity(self.case)
        if 'P2' in label.upper() or not math.isfinite(float(cap)) or float(cap)<=0:
            raise PermissionError('V43_M_FINITE_POSITIVE_P1_CALL_ONLY')
        context=current()
        if (context is None or context['request']['source_sha']!=authority['source_sha']
                or context['request']['arm']!=authority['arm'] or context['request']['stage']!=authority['stage']):
            raise PermissionError('V43_REAL_LOCKED_M_STAGE_SOURCE_CASE_REQUIRED')
        self._call_cap=float(cap)
        try:
            return super().native_optimize(model,callback,component='UB',track='M',label=label,requested_seconds=cap)
        finally:self._call_cap=None


def require_budget(budget,kind):
    if type(budget) is not StageBudget or budget.kind!=kind or budget.inflight is not None:
        raise PermissionError('V43_REAL_M_STAGE_BUDGET_REQUIRED')
    if getattr(budget.solve,'__func__',None) is not StageBudget.solve:
        raise PermissionError('V43_M_NATIVE_METHOD_OVERRIDE_FORBIDDEN')
    return budget
