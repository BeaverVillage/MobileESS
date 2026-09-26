"""Fail-closed gate between the two-iteration benchmark and full B2 resume."""
from bootstrap import *
import ast


def main():
    freeze=read(H/'FINAL_CANDIDATE_FREEZE.json')
    assert freeze['PAPER_PCC_CONFIG_USED'] and not freeze['RESITING_USED']
    assert not freeze['FEEDER_MODIFIED'] and not freeze['AIDC_DOUBLE_SCALING']
    assert (freeze['BG_SCALE'],freeze['AIDC_ABSOLUTE_SCALE'],freeze['MESS_SCALE'])==(.552,2.4,2.)
    assert read(H/'B0/COMPLETE.json')['status']=='PASS'
    assert read(H/'Actual/B0_GATE.json')['status']=='PASS'
    benchmark=read(H/'B2_ACTIVE_SET_DIAGNOSTIC/BENCHMARK.json')
    assert benchmark['status']=='BENCHMARK_COMPLETE' and benchmark['full_separation_closed']
    assert len(benchmark['iterations'])==2
    assert benchmark['iterations'][0]['separation']['new_rows']==6735
    final=benchmark['iterations'][-1]
    assert final['separation']['new_rows']==0
    assert final['separation']['all_logical_rows_checked']==31945536
    assert final['separation']['maximum_violation']<=final['separation']['exact_original_row_tolerance']
    assert final['restricted']['status']==2 and final['restricted']['mip_gap']<=.001
    assert final['before']['rows']<.05*992650
    assert final['before']['nonzeros']<.05*61958517
    cache=read(H/'B2_PERFORMANCE_RESUME_AUTHORITY.json')
    assert cache['status']=='PASS' and cache['restricted_candidate_problem_unchanged']
    assert cache['current_mess_runtime_sha256']==sha(H/'mess_runtime.py')
    assert cache['cache_file_count']==201
    assert read(H/'B2_ROOT_PROFILE/COMPARISON.json')['status']=='PASS'
    assert not(H/'B2/COMPLETE.json').exists()
    ast.parse((H/'mess_runtime.py').read_text(encoding='utf-8'))
    ast.parse((H/'mess_grid8500_active.py').read_text(encoding='utf-8'))
    assert read(H/'CAMPAIGN_STATUS.json')['status']=='PAUSED_FOR_ROOT_PROFILE'
    decision=dict(status='READY_FOR_FULL_B2_ACTIVE_SEPARATION',
        candidate=dict(date='2025-05-01',BG=.552,AIDC=2.4,MESS=2.,paper_PCC=True),
        benchmark=record(H/'B2_ACTIVE_SET_DIAGNOSTIC/BENCHMARK.json'),
        report=record(H/'B2_ACTIVE_SET_DIAGNOSTIC/BENCHMARK_REPORT.md'),
        cache_resume=record(H/'B2_PERFORMANCE_RESUME_AUTHORITY.json'),
        source=[record(H/name) for name in ('mess_runtime.py','mess_grid8500_active.py','mess_worker.py')],
        original_objective_domain_MIPGap_unchanged=True,
        no_time_work_node_limit=True,no_active_set_cap=True,
        full_separation_closure_required=True,
        final_96_slot_exact_OpenDSS_required=True,
        benchmark_solution_is_diagnostic_only=True,
        prior_dense_attempt_preserved=True,unix=time.time())
    save(H/'B2_ACTIVE_PRODUCTION_PRELAUNCH.json',decision)
    status=read(H/'CAMPAIGN_STATUS.json')
    status.update(status='B2_ACTIVE_PRODUCTION_READY',stage='B2_ACTIVE_PRODUCTION_PRELAUNCH',
        full_B2_restart_permitted=True,
        active_benchmark=record(H/'B2_ACTIVE_SET_DIAGNOSTIC/BENCHMARK.json'),
        updated_unix=time.time())
    save(H/'CAMPAIGN_STATUS.json',status)
    print('B2_ACTIVE_PRODUCTION_PRELAUNCH_PASS')


if __name__=='__main__':main()
