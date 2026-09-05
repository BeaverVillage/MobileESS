"""Runtime-only 4-day x 4-thread execution, preserving historical science keys.

Old exact restricted-solve caches remain valid: Threads=1 is a historical
runtime fact, not an objective/constraint authority. New solves use Threads=4.
One restricted candidate worker per day avoids nested 4x4x4 oversubscription.
"""
from concurrent.futures import ProcessPoolExecutor as OriginalProcessPoolExecutor


def four_thread_fixed_candidate(**kwargs):
    from dayahead.v35r3.algorithm import build_fixed_candidate_model
    item=build_fixed_candidate_model(**kwargs)
    item.model.Params.Threads=4
    assert item.model.Params.Threads==4
    return item


def initialize_runtime_worker(initializer,initargs):
    from dayahead.tools import run_v35r3e_r1_beam as beam
    beam.build_fixed_candidate_model=four_thread_fixed_candidate
    if initializer is not None:initializer(*initargs)


class OneSolverPerDayPool(OriginalProcessPoolExecutor):
    def __init__(self,max_workers=None,*,initializer=None,initargs=(),**kwargs):
        super().__init__(max_workers=1,initializer=initialize_runtime_worker,
            initargs=(initializer,initargs),**kwargs)


def install_runtime():
    from dayahead.v37 import runner
    from dayahead.tools import run_v35r3e_r1_beam as beam
    runner.MAX_WORKERS_PER_DATE=1
    beam.ProcessPoolExecutor=OneSolverPerDayPool
    beam.build_fixed_candidate_model=four_thread_fixed_candidate
    return {"max_parallel_day_workers":4,"active_solvers_per_day_max":1,"Threads_per_model":4,
        "max_concurrent_solver_threads":16,"science_mutation":False,
        "historical_Threads_1_exact_cache_reuse_allowed":True}
