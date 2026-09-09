"""Sealed performance-only entry point; no heavy-prefix fallback is permitted."""
from binding import *
import time, traceback

def install():
    verify_method()
    seal=read(OUT/'PERFORMANCE_FREEZE.json')
    assert seal['classification']=='PERFORMANCE_ONLY_EXACT_EQUIVALENT_ACCELERATION_PASS'
    assert sha(OUT/'evidence/MAY12_FINAL_EQUIVALENCE_GATE.json')==seal['gate_SHA']
    assert sha(OUT/'cached_engine.py')==seal['performance_engine_SHA']
    assert all(sha(OUT/name)==h for name,h in seal['implementation_files'].items())
    import qsafe
    from cached_engine import CachedPrefixEngine
    def heavy_disabled(self,t,q):
        raise RuntimeError('HEAVY_ACTUAL_PREFIX_REPLAY_DISABLED; '+str(getattr(self,'fallback_reason',None)))
    qsafe.PrefixEngine.evaluate=heavy_disabled
    qsafe.PrefixEngine=CachedPrefixEngine
    import actual_worker
    assert actual_worker.robust_search.namespace['PrefixEngine'] is CachedPrefixEngine
    return actual_worker

if __name__=='__main__':
    day=sys.argv[1];policies=sys.argv[2:]
    assert len(policies)==1 and policies[0] in ('B0','B1','B2','B3')
    try:install().main(day,policies)
    except BaseException as e:
        save(OUT/'failures'/f'{day}_{policies[0]}_{time.time_ns()}.json',dict(status='TECHNICAL_FAILURE',day=day,policy=policies[0],error=repr(e),traceback=traceback.format_exc(),heavy_fallback_disabled=True))
        raise
