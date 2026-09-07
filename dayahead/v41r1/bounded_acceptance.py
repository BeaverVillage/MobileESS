"""Bounded May-04 B1 development acceptance; no monthly dispatch."""
import argparse
from pathlib import Path
import time
import threading
import psutil
from dayahead.v41.data import RUNTIME
from dayahead.v41.preflight import record
from dayahead.paper_analysis.storage import read,write_json


def run(seconds,tag):
    from dayahead.v41.electrical import load
    from dayahead.v41.reserve import bind
    from dayahead.v40g_segments.canonical import import_frozen,planning_power
    from dayahead.v40g.optimizer import solve
    from .feasible_seed import policy_reference
    root=RUNTIME/'bounded_compute'/tag
    if root.exists():raise ValueError('PRESERVE_EXISTING_ACCEPTANCE_ATTEMPT')
    root.mkdir(parents=True);start=time.perf_counter();stop=threading.Event();samples=[]
    def sample():
        process=psutil.Process()
        while not stop.wait(1):
            samples.append(dict(seconds=time.perf_counter()-start,rss=process.memory_info().rss,available=psutil.virtual_memory().available))
    thread=threading.Thread(target=sample,daemon=True);thread.start()
    context=None
    try:
        print('LOADING_CURRENT_MAY04_COEFFICIENTS',flush=True);context=load('2025-05-04')
        path=RUNTIME/'inputs/2025-05-04/V41_ML_SNAPSHOT_2025-05-04.json';bind(context,path,record(path)['sha256'])
        context.v41_bounded_compute=dict(total_seconds=seconds,fix_and_optimize=True)
        jobs=read(RUNTIME/'inputs/2025-05-04/common_q90_v3/COMMON_B0_REFERENCE_JOBS.json')
        for policy in ('B0','B1','B2','B3'):
            policy_reference(jobs,context,root/'policy_seeds'/policy,policy)
        print('POLICY_REFERENCE_SEEDS_PASS',flush=True)
        power=planning_power(import_frozen(jobs),context)
        result=solve(jobs,power['pcc'],context,root/'A0')
        write_json(root/'COMPUTATIONAL_RESULT.json',dict(status='PASS',day='2025-05-04',policy='B1',
            total_wall_seconds=time.perf_counter()-start,optimization_seconds=result['optimization_seconds'],
            registered_budget_seconds=seconds,full_campaign_budget_seconds=1800,
            final_objective_vector=result['OBJECTIVE_VECTOR'],quality=result['solution_quality'],
            seed_audit=record(root/'A0/POLICY_FEASIBLE_SEED_AUDIT.json'),
            candidate_manifest=record(root/'A0/V41R1_FULL_CANDIDATE_MANIFEST.json'),
            coverage=record(root/'A0/CANDIDATE_COVERAGE_REPORT.json'),
            Fresh_Actual='NOT_YET_RUN; DEVELOPMENT_GATE_ONLY'))
        print('COMPUTATIONAL_RESULT_PASS',result['OBJECTIVE_VECTOR'],flush=True)
    except BaseException as error:
        write_json(root/'ERROR.json',dict(error=repr(error),elapsed_seconds=time.perf_counter()-start))
        raise
    finally:
        stop.set();thread.join()
        write_json(root/'MEMORY_SAMPLES.json',dict(samples=samples,peak_rss=max((x['rss'] for x in samples),default=0)))
        if context is not None:context.electrical.voltage.close();context.electrical.current.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=float,default=1800);p.add_argument('--tag',required=True)
    a=p.parse_args();run(a.seconds,a.tag)
