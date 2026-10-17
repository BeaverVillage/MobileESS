"""Latest user policy: charge the complete Phase I Native scope, cap at 1500s."""
from contextvars import ContextVar
from contextlib import contextmanager
from unittest.mock import patch
from pathlib import Path
from v44.common import atomic,now

CURRENT=ContextVar('R026F1_PHASE_I_NATIVE_BUDGET',default=None)
LIMIT=1500.


class PhaseINativeLimit(RuntimeError):
    pass


class LimitedNative:
    def __init__(self,native,context):self.native=native;self.context=context
    def __getattr__(self,name):return getattr(self.native,name)
    def remaining(self):
        left=self.native.remaining()
        if self.context['active']:
            if self.context['used']>=LIMIT:raise PhaseINativeLimit('PHASE_I_NATIVE_1500_LIMIT_REACHED')
            return min(left,LIMIT-self.context['used'])
        return left
    def solve(self,snapshot,folder,component):
        if component=='ORIGINAL_P1':self.context['active']=False;persist(self.context)
        self.remaining()
        result=self.native.solve(snapshot,folder,component)
        if self.context['active'] and (self.context['used']>=LIMIT or self.context.get('Native_TimeLimit_terminated')):
            persist(self.context);raise PhaseINativeLimit('PHASE_I_NATIVE_1500_LIMIT_REACHED')
        return result


def persist(c):
    atomic(c['output']/'PHASE_I_NATIVE_BUDGET.json',dict(UTC=now(),limit=LIMIT,Native_seconds=c['used'],
        phase_I_active=c['active'],calls=c['calls'],Native_only=True,
        includes_Phase_I_LP_and_local_pricing=True,P1_and_integer_excluded=True,
        threshold_reached=c['used']>=LIMIT,Native_TimeLimit_terminated=c.get('Native_TimeLimit_terminated',False),
        case_action='FAIL_DATE_ARM_CONTINUE_NEXT_ELIGIBLE_COMPARISON'))


@contextmanager
def phase_scope(native,output):
    c=dict(active=True,used=0.,calls=[],output=Path(output));token=CURRENT.set(c)
    try:
        with install():yield LimitedNative(native,c)
    finally:persist(c);CURRENT.reset(token)


@contextmanager
def install():
    from v42_may_campaign_native90.budget import DateBudget
    original=DateBudget.native_optimize
    original_remaining=DateBudget.remaining
    def remaining(self,reserve=None):
        value=original_remaining(self,reserve)
        c=CURRENT.get()
        if c is not None and c['active']:return min(value,max(0.,LIMIT-c['used']))
        return value
    def optimize(self,model,*args,**kwargs):
        c=CURRENT.get()
        if c is None or not c['active']:return original(self,model,*args,**kwargs)
        left=LIMIT-c['used']
        if left<=0:raise PhaseINativeLimit('PHASE_I_NATIVE_1500_LIMIT_REACHED')
        kwargs['requested_seconds']=min(kwargs.get('requested_seconds') or left,left)
        before=self.native_used
        try:return original(self,model,*args,**kwargs)
        finally:
            elapsed=self.native_used-before;c['used']+=elapsed
            if getattr(model,'Status',None)==9:c['Native_TimeLimit_terminated']=True
            c['calls'].append(dict(label=kwargs.get('component',kwargs.get('label')),Native_seconds=elapsed))
            persist(c)
    with patch.object(DateBudget,'remaining',remaining),patch.object(DateBudget,'native_optimize',optimize):yield
