"""Keep A1's compiled repair body connected to live stage stability adapters."""
from contextlib import contextmanager
from types import FunctionType
from unittest.mock import patch
from copy import deepcopy
from pathlib import Path
from v44.common import read,atomic,record
from v44.checkpoints import ledger_state


def live_compiler(original):
    def compile_(function):
        compiled=original(function)
        result=FunctionType(compiled.__code__,function.__globals__,compiled.__name__,compiled.__defaults__,compiled.__closure__)
        result.__kwdefaults__=compiled.__kwdefaults__
        return result
    return compile_


def inherited_budget(parent,base):
    account=ledger_state(Path(parent)/'NATIVE_RUNTIME_LEDGER.json',ceiling=5400.)
    old=read(account['ledger']['path'])
    class Continued(base):
        def __init__(self,*a,**kw):
            self._r046_inherited=False
            super().__init__(*a,**kw)
            self.calls=deepcopy(old['calls']);self.costs=deepcopy(old['costs'])
            self.native_used=account['measured'];self.started=self.clock()-old['wall_seconds']
            self._r046_inherited=True;self.persist()
        def persist(self):
            super().persist()
            if self._r046_inherited:
                value=read(self.path);value.update(parent_ledger=account['ledger'],
                    inherited_Native_seconds=account['measured'],Native_clock_reset=False,
                    resumed_same_stage_budget=True,historical_costs_reused=True)
                atomic(self.path,value)
    return Continued


@contextmanager
def a1_scope(parent):
    from v44_recovery_r029 import integer_repair
    from v44_recovery_r029 import phase_limit
    from v42_may_campaign_native90 import budget
    # The original compiled A1 body captured group/apply-policy before the
    # stage installed stability. Retain its original equations and repair,
    # but resolve those adapters in the live scientific module dictionary.
    compiler=live_compiler(integer_repair.compile_run)
    previous_scope=phase_limit.phase_scope
    old=read(Path(parent)/'NATIVE_RUNTIME_LEDGER.json')
    phase_calls=[r for r in old['calls'] if r['component']=='PHASE_I']
    @contextmanager
    def continued_scope(native,output):
        with previous_scope(native,output) as limited:
            limited.context['used']=sum(r['Native_Runtime'] for r in phase_calls)
            limited.context['calls']=[dict(label='INHERITED_PHASE_I',Native_seconds=r['Native_Runtime'],
                source=record(Path(parent)/'NATIVE_RUNTIME_LEDGER.json')) for r in phase_calls]
            phase_limit.persist(limited.context)
            yield limited
    with patch.object(integer_repair,'compile_run',compiler),patch.object(budget,'DateBudget',inherited_budget(parent,budget.DateBudget)),patch.object(phase_limit,'phase_scope',continued_scope):
        yield
