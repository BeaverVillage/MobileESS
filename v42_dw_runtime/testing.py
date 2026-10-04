"""Lane C resource envelope and narrow pytest entrypoint; never repo-wide pytest."""
import os
for _name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'
os.environ['FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE'] = 'true'

from contextlib import contextmanager
import threading
import time


@contextmanager
def bounded_solver_calls():
    import gurobipy as gp
    import psutil
    process = psutil.Process()
    if psutil.virtual_memory().available < 1024**3:
        raise RuntimeError('Lane C requires the established 1 GiB RAM floor')
    original = gp.Model.optimize
    lock = threading.Lock()
    state = dict(active=False, calls=[], peak_sampled_RSS=process.memory_info().rss,
                 minimum_sampled_available_RAM=psutil.virtual_memory().available)
    def optimize(model, *args, **kwargs):
        if model.Params.Threads != 1 or not 0 < model.Params.TimeLimit <= 30:
            raise RuntimeError('Lane C bounded solver contract violated')
        available = psutil.virtual_memory().available
        state['minimum_sampled_available_RAM'] = min(state['minimum_sampled_available_RAM'], available)
        if available < 1024**3:
            raise RuntimeError('Available RAM below 1 GiB')
        if not lock.acquire(blocking=False):
            raise RuntimeError('Concurrent Lane C optimize forbidden')
        started = time.perf_counter()
        try:
            state['active'] = True
            return original(model, *args, **kwargs)
        finally:
            ended = time.perf_counter()
            state['active'] = False
            state['peak_sampled_RSS'] = max(state['peak_sampled_RSS'], process.memory_info().rss)
            state['calls'].append(dict(start=started, end=ended, wall_seconds=ended-started,
                Threads=int(model.Params.Threads), TimeLimit=float(model.Params.TimeLimit),
                rows=model.NumConstrs, columns=model.NumVars, status=int(model.Status), pid=os.getpid()))
            lock.release()
    gp.Model.optimize = optimize
    try:
        yield state
    finally:
        gp.Model.optimize = original


def run():
    import pytest
    from .fixtures import write
    counts = dict(passed=0, failed=0, skipped=0)
    class CountReports:
        def pytest_runtest_logreport(self, report):
            if report.when == 'call':
                counts[report.outcome] += 1
    with bounded_solver_calls() as state:
        code = pytest.main(['-q', 'tests/v42_dw_runtime'], plugins=[CountReports()])
    calls = state['calls']
    write('DW_LANE_C_TEST_RECEIPT.json', dict(exit_code=int(code), scope='tests/v42_dw_runtime only', counts=counts,
        solver_calls=calls, observed_calls_nonoverlapping=all(a['end'] <= b['start'] for a, b in zip(calls, calls[1:])),
        observed_all_solver_calls_bounded=all(c['Threads']==1 and c['TimeLimit']<=30 and c['wall_seconds']<=30 for c in calls),
        peak_sampled_RSS_bytes=state['peak_sampled_RSS'], minimum_sampled_available_RAM=state['minimum_sampled_available_RAM'],
        sample_scope='own process before/after solver calls; unsampled peaks not claimed',
        FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE=True))
    return code


if __name__ == '__main__':
    raise SystemExit(run())
