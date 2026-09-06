"""One inherited full fleet search campaign, retaining its K/beam fallback tree."""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import json
import time
from dayahead.v40a.invariants import digest
from .candidate_cache import require_context
from .identity import require


class ArrayAuthority(dict):
    def close(self):pass


def search_once(repo, day, pcc, context, output, progress, execution_identity):
    from . import beam_driver as beam
    from dayahead.v37 import runner as old
    from dayahead.v36.runner import _prepare_seed_npz
    from dayahead.v35.execution import _planning_grid, daily_traffic_authority
    from dayahead.v35.contracts import PHASE_CALIBRATION
    from dayahead.v36.contracts import FROZEN_MESS_WORKTREE
    from dayahead.v33m.mess_trajectory import MessTrajectory
    from dayahead.v39e.runtime import four_thread_fixed_candidate
    from dayahead.v40a.observability import ObservedProductionPool
    repo=Path(repo);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    workspace=output/'execution_workspace';workspace.mkdir(parents=True,exist_ok=True)
    expected=execution_identity['identity']['inputs']
    require(expected['A0_PCC_SHA']==digest(pcc),'M1_A0_PCC_IDENTITY')
    require(expected['electrical_coefficients']==[c.coefficient_sha256 for c in context.coefficients],'M1_ELECTRICAL_COEFFICIENT_IDENTITY')
    arrays,_=_planning_grid(context.coefficients,context.electrical.voltage,pcc,MessTrajectory(()))
    _prepare_seed_npz(workspace,day,'B1',arrays,context.coefficients)
    keys=('APR01','CACHE_ROOT','prepare_aidc_stages','daily_traffic_authority','slot_coefficients','EXECUTION_CACHE_CONTEXT','PROGRESS_CALLBACK','ProcessPoolExecutor','build_fixed_candidate_model','_local_search','_solve_worker','_solve_item')
    originals={k:getattr(beam,k) for k in keys}
    identity=execution_identity['identity'];fingerprint=execution_identity['identity_SHA']
    electrical=SimpleNamespace(**context.electrical.__dict__)
    electrical.voltage=ArrayAuthority({k:context.electrical.voltage[k] for k in context.electrical.voltage.files})
    electrical.current=ArrayAuthority({k:context.electrical.current[k] for k in context.electrical.current.files})
    try:
        beam.APR01=day;beam.CACHE_ROOT=(output/'search_cache'/fingerprint).resolve()
        beam.prepare_aidc_stages=lambda *a,**k:(None,electrical,{'B0':{'planning_pcc_power_kw':pcc},'B1':{'planning_pcc_power_kw':pcc}})
        from .authorities import load_bound_traffic
        beam.daily_traffic_authority=lambda _repo,_cache,phase,target,admission:load_bound_traffic(repo,target,expected)
        beam.slot_coefficients=lambda *args:context.coefficients[int(args[-1])]
        beam.EXECUTION_CACHE_CONTEXT={'V40H_execution_identity':execution_identity,'execution_fingerprint_sha256':fingerprint,'candidate_cache_root':str(output/'search_cache'/fingerprint/'candidates')}
        require_context(beam.EXECUTION_CACHE_CONTEXT)
        beam.PROGRESS_CALLBACK=progress;beam.ProcessPoolExecutor=ObservedProductionPool
        beam.build_fixed_candidate_model=four_thread_fixed_candidate
        beam._local_search=lambda **kwargs:safe_local(beam,originals['_local_search'],**kwargs)
        beam._solve_worker=safe_worker
        def safe_parent(*args,**kwargs):
            started=time.perf_counter()
            try:return originals['_solve_item'](*args,**kwargs)
            except Exception as error:
                if not old._local_fallback_allowed(error):raise
                return old._failed_candidate_result(str(args[0]),args[1],error,time.perf_counter()-started)
        beam._solve_item=safe_parent
        import os
        previous=Path.cwd();os.chdir(workspace)
        attempts=[];started=time.perf_counter()
        for width in (old.BEAM_WIDTH,old.BEAM_WIDTH_FALLBACK):
            try:
                result=beam._run_case('B3',width,1)
                result.update(V40H_execution_identity=identity,V40H_execution_fingerprint=fingerprint,
                              V40A_route_search_campaign_calls=1,V40A_beam_attempts=attempts+[{'width':width,'status':'PASS'}],
                              V40A_wallclock_seconds=time.perf_counter()-started)
                return result
            except Exception as error:
                attempts.append({'width':width,'status':'FAIL','error':repr(error)})
                if width==old.BEAM_WIDTH and old._beam_fallback_allowed(error):continue
                raise
    finally:
        if 'previous' in locals():os.chdir(previous)
        for k,v in originals.items():setattr(beam,k,v)


def safe_worker(candidate):
    from . import beam_driver as frozen
    from dayahead.v37 import runner as old
    started=time.perf_counter()
    try:
        w=frozen._WORKER
        return frozen._solve_item(str(w['case']),candidate,w['aidc'],w['coefficients'],w['services'],w['fixed_p'],w['fixed_q'],
                                  w['line_states'],w['voltage_states'],w['tx_current_states'],w['tx_kva_states'])
    except Exception as error:
        if not old._local_fallback_allowed(error):raise
        return old._failed_candidate_result(str(frozen._WORKER['case']),candidate,error,time.perf_counter()-started)


def safe_local(beam,original,**kwargs):
    from dayahead.v37 import runner as old
    # Unattested K attempt status files cannot skip a current search level.
    # Candidate solves themselves still resume through the strict cache.
    restore=old._archived_k_attempt
    old._archived_k_attempt=lambda *a,**k:None
    try:return old._run_local_with_frozen_k_fallback(beam,original,**kwargs)
    finally:old._archived_k_attempt=restore
