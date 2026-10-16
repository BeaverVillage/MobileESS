"""Locked Native0 replay of archived mathematical arrays, never old points/bounds."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from time import perf_counter
import argparse
import cProfile
import pstats

import numpy as np
from scipy import sparse

from v43.common import RUNS,read,record,atomic,verify_records


def diagnostic_case(output):
    from .library import load
    from v43_arms.reference import load as reference
    from v42_bootstrap.m1 import native_inputs
    prior=RUNS/'may01_B2_M1_attempt001';request=read(prior/'request.json')
    payload=reference(request['fixed_AIDC_reference']);sites,initial,routes,battery,receipt=native_inputs(payload['bundle'])
    graph=(sites,initial,[(s,t,s,t+1,None) for s in sites for t in range(96)]+
        [(r.source,r.depart,r.destination,r.connect,r) for r in dict.fromkeys(routes)],battery,receipt)
    A=sparse.load_npz(prior/'FULL_A.npz');B=sparse.load_npz(prior/'C3A_A.npz')
    with np.load(prior/'FULL_DATA.npz',allow_pickle=False) as z:d={k:z[k].copy() for k in z.files}
    with np.load(prior/'C3A_DATA.npz',allow_pickle=False) as z:e={k:z[k].copy() for k in z.files}
    identity=read(prior/'SCIENTIFIC_CASE_IDENTITY.json');sha=identity.pop('case_sha');m=load()['m_engine']
    assert m.matrix_sha(A)==identity['original_matrix_sha'] and m.domain_sha(d)==identity['original_domain_sha']
    assert m.matrix_sha(B)==identity['selected_matrix_sha'] and m.domain_sha(e)==identity['selected_domain_sha']
    def no_point(*args):raise ValueError('DIAGNOSTIC_ONLY_NO_HISTORICAL_OR_PRODUCTION_POINT')
    case=SimpleNamespace(original_A=A,original_d=d,A=B,d=e,graph=graph,case_sha=sha,
        identity=identity,bundle=payload['bundle'],output=Path(output),lift=no_point)
    prior_binding=read(prior/'COMMON_M_PR222/M_STAGE_RESULT.json')['binding']
    assert m.binding(case)==prior_binding
    return case


def run(output,*,beam=False):
    from v42_may_campaign.common import exclusive_lock
    from v42_may_campaign_native90.preflight import native_zero
    from .library import load,dependency_smoke
    from .performance import install,record_caches
    output=Path(output)
    if output.exists():raise ValueError('NEW_NATIVE0_DIAGNOSTIC_REQUIRED')
    output.mkdir(parents=True)
    with ExitStack() as stack:
        paths=[Path('D:/MobileESS_V42/runtime/v42_may_campaign/NATIVE_WORKER.lock')]
        paths += [Path(f'D:/MobileESS_V42/runtime/v42_may_campaign/native_slots/SLOT_{i}.lock') for i in (1,2,3)]
        paths += [Path('D:/V42_UNIFIED_HEAVY_WORKER.lock'),RUNS/'V43_HEAVY_WORKER.lock']
        for p in paths:stack.enter_context(exclusive_lock(p))
        denied=stack.enter_context(native_zero())
        modules=load();dependency_smoke();case=diagnostic_case(output);c=modules['m_candidates'];m=modules['m_engine']
        if beam:
            from .budget import StageBudget
            install(case,modules);bank=m.IncumbentBank(case)
            budget=StageBudget(output/'SCORE_ONLY_LEDGER.json',case=case,kind='PLANNING_NATIVE')
            began=perf_counter();pools=c.generate(case,None,bank,budget)
            assert pools and budget.used()==0 and not budget.calls
            packet=m.direct_joint(case,None,pools)
            native,_=m._native_joint(case,None,packet,output/'BEAM_NATIVE0_READBACK',1.,native0=True)
            assert native['Native_optimize_calls']==0 and not denied
            result=dict(PASS=True,Native_calls=0,Native_seconds=0.,wall_seconds=perf_counter()-began,
                seedless=True,historical_points_bounds_clocks_read=False,diagnostic_matrices_only=True,
                fresh_Beam_pool_counts={u:len(p) for u,p in pools.items()},
                HiGHS_score_calls=len(budget.costs),HiGHS_measured_wall_seconds=sum(r['wall_seconds'] for r in budget.costs),
                real_four_unit_Beam_Direct_Joint_Native0_PASS=True,production_case_reuse_authorized=False)
            atomic(output/'RESULT.json',result);print(result);return result
        results={};profiles=[]
        def measured(label,fn):
            profiler=cProfile.Profile();began=perf_counter();profiler.enable()
            try:value=fn()
            finally:
                profiler.disable();wall=perf_counter()-began;profiler.dump_stats(str(output/(label+'.pstats')))
                with (output/(label+'.txt')).open('w',encoding='utf8') as f:
                    pstats.Stats(profiler,stream=f).strip_dirs().sort_stats('cumtime').print_stats(25)
            profiles.append(dict(stage=label,wall_seconds=wall));atomic(output/'progress.json',dict(stages=profiles))
            return value
        baseline=measured('BASELINE_GRID_CONTEXT',lambda:c.grid_context(case,None))
        vertices=measured('BASELINE_PCS_VERTICES',lambda:c.pcs_vertices(case))
        install(case,modules)
        cold=measured('CACHED_COLD_GRID_CONTEXT',lambda:c.grid_context(case,None))
        warm=measured('CACHED_WARM_GRID_CONTEXT',lambda:c.grid_context(case,None))
        fast_vertices=measured('CACHED_COLD_PCS_VERTICES',lambda:c.pcs_vertices(case))
        warm_vertices=measured('CACHED_WARM_PCS_VERTICES',lambda:c.pcs_vertices(case))
        assert baseline==cold==warm
        assert np.array_equal(vertices,fast_vertices) and np.array_equal(vertices,warm_vertices)
        # Build the real four-unit Direct Joint and read the Native model back
        # without Optimize; this reaches beyond both formerly hidden failures.
        graph=m.PathGraph(case);pools={u:[graph.complete(u)] for u in graph.origins}
        packet=measured('REAL_STAY_POOL_DIRECT_JOINT',lambda:m.direct_joint(case,None,pools))
        native,_=measured('REAL_NATIVE0_MODEL_READBACK',lambda:m._native_joint(case,None,packet,output/'NATIVE0_READBACK',1.,native0=True))
        assert native['Native_optimize_calls']==0 and not denied
        record_caches(case,output/'CACHE_METRICS.json')
        results=dict(PASS=True,Native_calls=0,historical_points_bounds_or_clocks_read=False,
            diagnostic_matrices_only=True,production_case_reuse_authorized=False,stages=profiles,
            grid_context_bit_exact=True,PCS_vertices_bit_exact=True,real_Direct_Joint_Native0_PASS=True,
            matrix_sha=m.matrix_sha(case.original_A),domain_sha=m.domain_sha(case.original_d),
            cache_metrics=record(output/'CACHE_METRICS.json'))
        atomic(output/'RESULT.json',results);print(results)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output');p.add_argument('--beam',action='store_true');run(**vars(p.parse_args()))
