"""Bound full-heap scans while retaining exact native retirement ownership checks."""
from contextlib import contextmanager
from types import FunctionType,SimpleNamespace
from unittest.mock import patch
import gc,time,sys


class RetirementCollector:
    def __init__(self,completed,collect=None):
        self.completed=completed;self.collect=collect or gc.collect
        self.calls=0;self.full_collections=0;self.young_collections=0;self.seconds=0.;self.max_pending=0
    def run(self):
        self.calls+=1;count=len(self.completed);self.max_pending=max(self.max_pending,count)
        full=self.calls%8==0 or count>=16
        began=time.perf_counter()
        try:
            if full:self.full_collections+=1;return self.collect(2)
            self.young_collections+=1;return self.collect(1)
        finally:self.seconds+=time.perf_counter()-began
    def report(self):
        return dict(calls=self.calls,full_collections=self.full_collections,young_collections=self.young_collections,
            collection_wall_seconds=self.seconds,max_pending_retired_contexts=self.max_pending,
            force_full_at_pending=16,full_collection_period=8,
            native_context_reuse=False,native_disposer_changed=False,retirement_ownership_checks_skipped=0)


@contextmanager
def scope(oracle):
    if getattr(oracle,'_independent_fresh',False):raise PermissionError('R029_CURRENT_CONTEXT_GC_ONLY')
    import v42_svr11.context_lifecycle as lifecycle
    collector=getattr(oracle,'_r029_context_gc',None)
    if collector is None:collector=oracle._r029_context_gc=RetirementCollector(lifecycle._completed)
    original=lifecycle.flush_completed_probes
    namespace=dict(original.__globals__,gc=SimpleNamespace(collect=collector.run))
    adapted=FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__)
    adapted.__kwdefaults__=original.__kwdefaults__
    # The original body still checks every exact retired owner/callback manager.
    with patch.object(lifecycle,'flush_completed_probes',adapted):yield collector


def finish():
    # Final case cleanup uses the original full collector, including Fresh.
    lifecycle=sys.modules.get('v42_svr11.context_lifecycle')
    if lifecycle is None or not lifecycle._completed:return 0
    return lifecycle.flush_completed_probes()
