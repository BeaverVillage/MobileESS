"""Preserve the failed attempt and adopt live workers without restarting them."""
import time,shutil,psutil
from fast_prepare import ROOT,read,record
from dayahead.paper_analysis.storage import write_json
from dayahead.v40h.identity import verify_manifest
from v41r4_loop_runtime import MAY_RUN,MAY_OUT,LOGS

def main():
    tests=read(MAY_OUT/'mission/LARGE_BLOCK_REPAIR_TEST.json');assert tests['status']=='PASS'
    verify_manifest(read(MAY_OUT/'MAY_CAMPAIGN_RELEASE_V4.json')['source'])
    evidence=MAY_OUT/'mission/LARGE_BLOCK_FAILURE_2025-05-11';evidence.mkdir(exist_ok=False)
    phase=MAY_OUT/'2025-05-11/PHASE_B1_DA.json';failure=read(phase)
    assert failure['status']=='FAIL_CLOSED' and failure['error']=="RuntimeError('COMPLETE_JOB_BLOCK_EXCEEDS_MAX_FREE_DISCRETE:301')"
    da=MAY_RUN/'2025-05-11/B1/dayahead'
    assert not (da/'DAYAHEAD_RECEIPT.json').exists()
    assert not any((MAY_RUN/'2025-05-11'/p/'actual/ACTUAL_BOUNDARY_RECEIPT.json').exists() for p in ('B0','B1','B2','B3'))
    state=read(MAY_RUN/'campaign_progress.json')
    assert state['status'] in ('FAIL_CLOSED_DRAINING','FAIL_CLOSED')
    supervisor=psutil.Process(state['supervisor_pid']) if psutil.pid_exists(state['supervisor_pid']) else None
    if supervisor:
        assert 'mission_loop_resume.py' in ' '.join(supervisor.cmdline())
        supervisor.suspend()
    try:
        state=read(MAY_RUN/'campaign_progress.json')
        adopted=[]
        for r in state['active']:
            if psutil.pid_exists(r['worker_pid']):
                p=psutil.Process(r['worker_pid']);assert r['day'] in p.cmdline() and r['phase'] in p.cmdline()
                assert r['day']!='2025-05-11'
                adopted.append(dict(r,created_at=p.create_time()))
            else:assert read(MAY_OUT/r['day']/f"PHASE_{r['phase']}.json")['status']=='PASS'
        shutil.copytree(MAY_OUT/'2025-05-11',evidence/'audit_before')
        shutil.copy2(LOGS/'2025-05-11/B1_DA.log',evidence/'B1_DA.log')
        write_json(evidence/'campaign_before.json',state)
        # Explicitly verify all resolved move endpoints stay in the campaign tree.
        moves=[(da,evidence/'dayahead_failed')]
        for name in ('PHASE_B1_DA.json','PRODUCER_B1.json','B1_SINGLE_CORRECTED_RUN_TOKEN.json','B1_COLD_START_AUTHORITY.json'):
            moves.append((MAY_OUT/'2025-05-11'/name,evidence/name))
        for source,target in moves:
            assert source.resolve().is_relative_to(MAY_RUN.resolve())
            assert target.resolve().is_relative_to(evidence.resolve()) and not target.exists()
        for source,target in moves:source.rename(target)
        shutil.copy2(evidence/'PHASE_B1_DA.json',MAY_OUT/'mission/PRESERVED_PHASE_2025-05-11_B1_DA_FAILURE.json')
        repair=dict(status='PASS',helpers=[record(ROOT/n) for n in ('mission_loop_large_block.py','mission_loop_large_worker.py','mission_loop_large_supervisor.py')],
            tests=record(MAY_OUT/'mission/LARGE_BLOCK_REPAIR_TEST.json'),original_release=record(MAY_OUT/'MAY_CAMPAIGN_RELEASE_V4.json'),
            reason='Allow complete indivisible 11970-variable job 301 beyond nominal 10000-variable neighborhood limit',
            user_authorization='2026-09-08: 수정하고 돌리자',created_at=time.time(),
            original_science_sources_unchanged=True,candidate_pruning=0,model_rows_changed=0,ranking_changed=False,
            B1_A1_same_algorithm=True,search_loop_wall_seconds=1800,no_stagnation_stop=True,
            failed_attempt=str(evidence),completed_results_reused=True,retained_workers=adopted,
            retry_scope='2025-05-11 B1; subsequent B1/B3 use repaired source-bound producer')
        write_json(MAY_OUT/'mission/LARGE_BLOCK_REPAIR_RELEASE.json',repair)
        write_json(MAY_OUT/'mission/SUPERVISOR_TAKEOVER.json',dict(state,active=adopted,takeover_at=time.time(),repair=record(MAY_OUT/'mission/LARGE_BLOCK_REPAIR_RELEASE.json')))
        if supervisor:supervisor.terminate();supervisor.wait(15)
        for r in adopted:
            if not psutil.pid_exists(r['worker_pid']):assert read(MAY_OUT/r['day']/f"PHASE_{r['phase']}.json")['status']=='PASS'
        print('PRESERVED_FAILED_ATTEMPT_AND_ADOPTED',[(r['day'],r['phase'],r['worker_pid']) for r in adopted])
    except BaseException:
        if supervisor and supervisor.is_running():supervisor.resume()
        raise

if __name__=='__main__':main()
