"""One inherited full fleet search campaign, retaining its K/beam fallback tree."""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import json
import time
from .invariants import digest


class ArrayAuthority(dict):
    def close(self):pass


def search_once(repo, day, pcc, context, output, progress):
    from dayahead.tools import run_v35r3e_r1_beam as beam
    from dayahead.v37 import runner as old
    from dayahead.v36.runner import _prepare_seed_npz
    from dayahead.v35.execution import _planning_grid, daily_traffic_authority
    from dayahead.v35.contracts import PHASE_CALIBRATION
    from dayahead.v36.contracts import FROZEN_MESS_WORKTREE
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v39e.runtime import four_thread_fixed_candidate
    from .observability import ObservedProductionPool
    repo=Path(repo);output=Path(output)
    arrays,_=_planning_grid(context.coefficients,context.electrical.voltage,pcc,MessTrajectory(()))
    _prepare_seed_npz(repo,day,'B1',arrays,context.coefficients)
    keys=('APR01','CACHE_ROOT','prepare_aidc_stages','daily_traffic_authority','slot_coefficients','EXECUTION_CACHE_CONTEXT','PROGRESS_CALLBACK','ProcessPoolExecutor','build_fixed_candidate_model','_local_search','_solve_worker','_solve_item')
    originals={k:getattr(beam,k) for k in keys}
    identity={'method':'V40A_M1','day':day,'A0_PCC':digest(pcc),'grid':[c.coefficient_sha256 for c in context.coefficients],
              'K':200,'K_fallback':[200,400,800,'FULL'],'beam':2,'beam_fallback':4,'seed':2,'WorkLimit':[60,180,300]}
    from .context import file_sha
    identity['source_SHAs']={relative:file_sha(repo/relative) for relative in (
        'dayahead/v40a/mobility.py','dayahead/v40a/context.py','dayahead/v40a/observability.py',
        'dayahead/v37/runner.py','dayahead/v39e/runtime.py','dayahead/v34/integrated_mess.py',
        'dayahead/v35r3/algorithm.py','dayahead/tools/run_v35r3e_r1_beam.py',
        'dayahead/v35r3e/algorithm.py','dayahead/v35r3e_r1/beam.py','dayahead/v33m/mess_mobility_milp.py')}
    fingerprint=digest(identity)
    electrical=SimpleNamespace(**context.electrical.__dict__)
    electrical.voltage=ArrayAuthority({k:context.electrical.voltage[k] for k in context.electrical.voltage.files})
    electrical.current=ArrayAuthority({k:context.electrical.current[k] for k in context.electrical.current.files})
    try:
        beam.APR01=day;beam.CACHE_ROOT=Path('dayahead/cache/v40a')/fingerprint
        beam.prepare_aidc_stages=lambda *a,**k:(None,electrical,{'B0':{'planning_pcc_power_kw':pcc},'B1':{'planning_pcc_power_kw':pcc}})
        beam.daily_traffic_authority=lambda _repo,_cache,phase,target,admission:daily_traffic_authority(FROZEN_MESS_WORKTREE,FROZEN_MESS_WORKTREE/'dayahead/cache/v35',phase,target,admission)
        beam.slot_coefficients=lambda *args:context.coefficients[int(args[-1])]
        beam.EXECUTION_CACHE_CONTEXT={**identity,'execution_fingerprint_sha256':fingerprint,'candidate_cache_root':str(repo/'dayahead/cache/v40a'/fingerprint/'candidates')}
        beam.PROGRESS_CALLBACK=progress;beam.ProcessPoolExecutor=ObservedProductionPool
        beam.build_fixed_candidate_model=four_thread_fixed_candidate
        beam._local_search=lambda **kwargs:old._run_local_with_frozen_k_fallback(beam,originals['_local_search'],**kwargs)
        beam._solve_worker=old._v37_safe_restricted_worker
        def safe_parent(*args,**kwargs):
            started=time.perf_counter()
            try:return originals['_solve_item'](*args,**kwargs)
            except Exception as error:
                if not old._local_fallback_allowed(error):raise
                return old._failed_candidate_result(str(args[0]),args[1],error,time.perf_counter()-started)
        beam._solve_item=safe_parent
        attempts=[];started=time.perf_counter()
        for width in (old.BEAM_WIDTH,old.BEAM_WIDTH_FALLBACK):
            try:
                result=beam._run_case('B3',width,1)
                result.update(V40A_execution_identity=identity,V40A_execution_fingerprint=fingerprint,
                              V40A_route_search_campaign_calls=1,V40A_beam_attempts=attempts+[{'width':width,'status':'PASS'}],
                              V40A_wallclock_seconds=time.perf_counter()-started)
                return result
            except Exception as error:
                attempts.append({'width':width,'status':'FAIL','error':repr(error)})
                if width==old.BEAM_WIDTH and old._beam_fallback_allowed(error):continue
                raise
    finally:
        for k,v in originals.items():setattr(beam,k,v)
