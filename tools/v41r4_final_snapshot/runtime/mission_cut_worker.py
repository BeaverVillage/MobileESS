"""V4 worker with inherited Fresh-cut restoration and exact producer selection."""
import sys
from fast_prepare import ROOT,read,record
from dayahead.paper_analysis.storage import write_json
from v41r4_loop_budget import adapted
import v41r4_loop_runtime as runtime
import v41r4_loop_worker as worker
import mission_loop_large_worker as large
from mission_loop_large_block import install as install_blocks
from mission_loop_archive import install as install_archive
from mission_cut_finalize import finalize,preserve

CUT_HELPERS=('mission_ac_cut_restore.py','mission_cut_finalize.py','mission_cut_worker.py',
    'mission_empty_table.py',
    'dayahead/v37r3/restoration.py','dayahead/v17_ac_restoration_contract.py',
    'dayahead/v34/integrated_mess.py','dayahead/v40a/postfreeze.py',
    'dayahead/v40a/grid.py','dayahead/v40h/recourse.py',
    'frozen_artifacts/v41r4_may/loop_wall_v4/audit/mission/AC_CUT_MARGIN_AUTHORITY.json')

def configure_for(day,policy,cut_enabled,large_enabled):
    helpers=(*runtime.HELPERS,*((('mission_loop_large_block.py','mission_loop_large_worker.py')) if large_enabled else ()),
        *(CUT_HELPERS if cut_enabled else ()))
    if large_enabled:install_blocks()
    fn=adapted(runtime.configure,[],dict(HELPERS=helpers,ranking_cache=large.ranking_cache))
    execution=fn(day,policy)
    if cut_enabled:
        original=execution.dayahead
        def with_cuts(target,method):
            try:return original(target,method)
            except ValueError as error:
                if str(error)!='DAYAHEAD_FRESH_PHYSICAL_VIOLATION':raise
                return finalize(target,method,execution)
        execution.dayahead=with_cuts
    return execution

def verify_release():
    release=read(runtime.MAY_OUT/'mission/AC_CUT_EXECUTION_RELEASE.json')
    assert release['status']=='PASS'
    assert all(record(x['path'])==x for x in release['helpers'])

def main(day,phase):
    verify_release();install_archive()
    from mission_empty_table import install as install_empty
    install_empty()
    policy=phase.split('_')[0]
    cut_enabled=phase.endswith('_DA') and policy in ('B2','B3')
    large_enabled=policy in ('B1','B3')
    producer=runtime.MAY_OUT/day/f'PRODUCER_{policy}.json'
    if phase.endswith('_AC') and producer.exists():
        paths={x['path'] for x in read(producer)['science']['files']}
        cut_enabled=str(ROOT/'mission_cut_worker.py') in paths
        large_enabled=str(ROOT/'mission_loop_large_block.py') in paths
    worker.configure=lambda d,p:configure_for(d,p,cut_enabled,large_enabled)
    worker.prepare_ranking=large.prepare_repaired
    worker.main(day,phase)

def resume(day,policy):
    import time
    verify_release();install_archive()
    output=runtime.MAY_RUN/day/policy/'dayahead'
    phase=runtime.MAY_OUT/day/f'PHASE_{policy}_DA.json'
    failure=read(phase);assert failure['error']=="ValueError('DAYAHEAD_FRESH_PHYSICAL_VIOLATION')"
    assert not any((runtime.MAY_RUN/day/p/'actual/ACTUAL_BOUNDARY_RECEIPT.json').exists() for p in ('B0','B1','B2','B3'))
    saved=preserve(day,policy,output)
    producer=runtime.MAY_OUT/day/f'PRODUCER_{policy}.json'
    from dayahead.v40h.identity import verify_manifest
    target=saved/'PRODUCER_REBOUND_ORIGINAL.json'
    assert producer.resolve().is_relative_to(runtime.MAY_RUN.resolve()) and target.resolve().is_relative_to(saved.resolve())
    if target.exists():
        verify_manifest(read(target)['science'])
        partial=saved/('PRODUCER_PARTIAL_'+str(time.time_ns())+'.json')
        assert partial.resolve().is_relative_to(saved.resolve())
        if producer.exists():producer.rename(partial)
    else:
        verify_manifest(read(producer)['science']);producer.rename(target)
    execution=configure_for(day,policy,True,policy=='B3')
    finalize(day,policy,execution)
    runtime.install_reports()
    from v41r4_report import accept_dayahead
    result=accept_dayahead(day,policy)
    import shutil
    preserved=runtime.MAY_OUT/'mission'/f'PRESERVED_PHASE_{day}_{policy}_DA_AC_CUT_FAILURE.json'
    assert not preserved.exists();shutil.copy2(phase,preserved)
    write_json(phase,dict(status='PASS',day=day,phase=f'{policy}_DA',started_at=failure['started_at'],
        completed_at=time.time(),elapsed_seconds=time.time()-failure['started_at'],result=result,
        budget_version='FIXED_1800_LOOP_WALL_CLOCK',automatic_repeat=False,
        recovery='INHERITED_POSTFREEZE_AC_CUT_CALL_RESTORED',AIDC_reruns=0,route_search_reruns=0,retry_count=1))
    print('CUT_RECOVERY_DAYAHEAD_PASS',day,policy,flush=True)

if __name__=='__main__':
    if sys.argv[1]=='resume':resume(sys.argv[2],sys.argv[3])
    else:main(sys.argv[1],sys.argv[2])
