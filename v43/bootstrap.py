"""Seal preserved baselines, causal contract, and the untouched Golden request."""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import psutil
from .common import *

def bootstrap():
    DOC.mkdir(parents=True, exist_ok=True)
    if (DOC / 'V43_BASELINE_AND_SOURCE_FREEZE.json').exists():
        raise PermissionError('BOOTSTRAP_ALREADY_SEALED')
    request_source = Path('C:/Users/kjw39/.codex/attachments/596267b6-3185-4400-9fae-e23b87782c26/붙여넣은 텍스트.txt')
    (DOC / 'USER_REQUEST_V43.txt').write_bytes(request_source.read_bytes())
    support = [export_support(p) for p in (
        'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json',
        'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv',
        'docs/v42_may01_native_canary/EXACT_SOURCE_PATH_RECOVERY.json',
        'docs/v42_a_stage_phase1_residual_migration_20261008/ROW_ATTRIBUTION_AUTHORITY.json',
        'docs/v42_ts_cc4_temporal_refinement/TS_HIERARCHICAL_BACKOFF_AUTHORITY.json',
        'docs/v42_ts_cc4_temporal_refinement/CC4_SERVICE_TIMING_ENVELOPE.csv')]
    old_request = read(HIST / 'request.json')
    inputs = Path(old_request['input_folder'])
    bundle = read(inputs / 'NATIVE_INPUT.json')
    issue = datetime.fromisoformat(bundle['issue_time'])
    midnight = datetime.fromisoformat(bundle['day']).replace(tzinfo=timezone(timedelta(hours=10)))
    assert issue == midnight - timedelta(hours=6)
    known = bundle['known_population']
    bad = [r['job_uid'] for r in known if not r['known_at_issue'] or datetime.fromisoformat(r['submit_time']) > issue]
    assert not bad, bad
    old_input = read(HIST / 'output/A_PREPARE_RECEIPT.json')['scientific_input']
    verify_records(list(old_input.values()))
    sources = []
    for row in read(HIST / 'output/A_NATIVE_SOURCE_FREEZE.json')['sources']:
        rel = row['path'].split('MobileESS_V42\\', 1)[1].replace('\\', '/')
        p = ROOT / rel
        if not p.exists(): export_support(rel)
        new = record(p)
        assert new['sha256'] == row['sha256'] and new['bytes'] == row['bytes'], rel
        sources.append(dict(relative_path=rel, historical=row, current=new, bit_exact=True))
    rollback = read(PR231 / 'docs/v42_1_freeze_20261016/OUTSIDE_ROLLBACK_BUNDLE_RECEIPT.json')
    verify_records(rollback['copied_manifest_records'])
    tag = git('rev-parse', 'v42.1-freeze-20261016^{}').decode().strip()
    assert tag == rollback['source_SHA']
    workers = []
    processes = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            if (p.info['name'] or '').lower() not in ('python.exe', 'pythonw.exe', 'python'): continue
            processes.append(p.info)
            cmd = ' '.join(p.info['cmdline'] or [])
            if p.pid != os.getpid() and ('worker' in cmd.lower() or 'native0' in cmd.lower() or 'audit_v42' in cmd.lower()):
                workers.append(p.info)
        except psutil.Error: pass
    assert not workers, workers
    state = read(PR231 / 'docs/v42_2_campaign_20261016/CHECKPOINT.json')
    preserved = dict(observed_UTC=now(), python_processes=processes, heavy_workers=workers,
        checkpoint=record(PR231 / 'docs/v42_2_campaign_20261016/CHECKPOINT.json'),
        STATE=read(PR231 / 'docs/v42_2_campaign_20261016/STATE.json'),
        stale_heartbeat_not_evidence_of_live_process=True,
        M_NATIVE0_05=state['M_NATIVE0_05'], B1_ATTEMPT005=state['B1_ATTEMPT005'],
        worktrees=git('worktree', 'list', '--porcelain').decode('utf8'),
        PR231_dirty_status=subprocess.check_output(['git','status','--porcelain','-uno'],cwd=PR231,text=True),
        PR231_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=PR231,text=True).strip(),
        original_sources_edited=False, original_runs_stopped=False)
    atomic(DOC / 'PRESERVED_V42_STATE.json', preserved)
    freeze = dict(schema='V43_BASELINE_SOURCE_FREEZE_V1', observed_UTC=now(),
        base_commit=BASE, branch=git('branch','--show-current').decode().strip(), worktree=str(ROOT),
        rollback_tag='v42.1-freeze-20261016', rollback_commit=tag,
        rollback_manifest_bundle_verified=True, rollback=rollback,
        baseline_execution_sources=sources, sources=source_records(), support=support,
        historical_request=record(HIST/'request.json'), historical_result_role='HISTORICAL_BASELINE_ONLY',
        scientific_inputs=list(old_input.values()), PR231_current_HEAD=preserved['PR231_HEAD'],
        user_request=record(DOC/'USER_REQUEST_V43.txt'), independent_runtime_root=str(RUNS),
        historical_point_bound_or_result_loaded_as_new=False, Worker=1, Threads=1)
    atomic(DOC/'V43_BASELINE_AND_SOURCE_FREEZE.json', freeze)
    atomic(DOC/'V43_TIME_AND_CAUSAL_CONTRACT.json', dict(schema='V43_D1_CAUSAL_V1',
        timezone='Australia/Melbourne', May_AEST_UTC_offset_hours=10,
        cutoff_local='D-1T18:00:00+10:00', issue_time=bundle['issue_time'], slot_seconds=900,
        internal_slot_interval=[0,120], prefix_slot_interval=[0,24], evaluation_slot_interval=[24,120],
        planning_reoptimization_during_prefix=False, future_unknown_UIDs_permitted=False,
        D0_snapshot_is_planning_authority=False, known_rows=len(known), late_known_UIDs=bad,
        forecast_issue_and_transitive_source_validation='PENDING_NATIVE0_AND_CAUSAL_AUDIT',
        Actual_prefix_continuity='NOT_CERTIFIED', Known_schedule_after_acceptance='FROZEN'))
    atomic(DOC/'V43_UNKNOWN_PRESITE_SOURCE_AUTHORITY.json', dict(
        strict_policy_id='V43_UNKNOWN_C1_STRICT_SOURCE_V1', basic_policy_id='V43_UNKNOWN_C0_V1',
        research_policy_id='V43_UNKNOWN_C1_R1_ASSUMED_V1', status='NOT_PORTED',
        running_migration_new_authority=False, initial_reference_grid_blind=True,
        additional_data_access_is_ASSUMED=True, R1_is_production_PASS=False, R2='HOLD',
        source_forbidden_destinations_preserved=True, per_UID_authority='PENDING_SOURCE_AUDIT'))
    atomic(DOC/'V43_PRESITE_ACTUAL_EXECUTION_AUDIT.json', dict(status='NOT_RUN', Gate_B_PASS=False,
        Selected=None, Actually_Started=None, Changed_GPUh=None, future_information_leakage='NOT_CERTIFIED'))
    atomic(DOC/'V43_MESS_K48_BEAM_JOINT_CERTIFICATION.json',dict(status='NOT_RUN', Gate_C_PASS=False,
        case_SHA=None, LB=None, UB=None, Global_Gap=None, old_case_bounds_transferred=False,
        Native_stage_limit=1800, K48_limit=300, joint_call_limit=140, Worker=1, Threads=1))
    fields=['day','arm','policy_id','status','Planning_max_loading','Actual_max_loading','Global_LB','FULL_UB','Global_gap','Fresh_AC96_PASS']
    for name,days in [('V43_MAY01_FOUR_ARM_RESULTS.csv',['2025-05-01']),('V43_MAY2025_31DAY_RESULTS.csv',[f'2025-05-{i:02d}' for i in range(1,32)])]:
        with (DOC/name).open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            w.writerows(dict(day=d,arm=a,policy_id=p,status='NOT_RUN') for d in days for a in ('B0','B1','B2','B3') for p in ('V43_UNKNOWN_C0_V1','V43_UNKNOWN_C1_STRICT_SOURCE_V1'))
    for name,columns in [('V43_UNKNOWN_C0_C1_COMPARISON.csv',['day','arm','policy_id','status','submitted_UIDs','basic_assigned','eligible_UIDs','candidates','hard_feasible','selected','actually_started','changed_GPUh','queue','completion','carryout','delay','GPU_violations','rack_violations','WAN_violations','Actual_max_loading','Actual_mean_loading','voltage_violations','thermal_violations','controller_P50','controller_P95','controller_max']),('V43_NATIVE_AND_WALL_RUNTIME_BREAKDOWN.csv',['day','arm','stage','attempt','status','Native_seconds','build_wall_seconds','validation_wall_seconds','total_wall_seconds'])]:
        with (DOC/name).open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerow(dict(day='2025-05-01',arm='B1',status='NOT_RUN'))
    req = dict(old_request)
    # No historical physical cache or solved state is used in this first reproduction.
    for key in list(req):
        if key.startswith('_') or key in ('worker_command','manifest','manifest_SHA','implementation_SHA','policy_version','started_UTC'):
            req.pop(key)
    attempt = RUNS/'golden_B1_20250501_attempt001'
    req.update(root=str(attempt), run_id=attempt.name, output=str(attempt/'output'),
        progress=str(attempt/'progress.json'),result=str(attempt/'RESULT.json'),error=str(attempt/'error.json'),
        policy_id='V43_PR189_GOLDEN_UNMODIFIED_V1', Worker=1, Threads=1,
        _expected_model_verification=old_request['_expected_model_verification'])
    atomic(DOC/'GOLDEN_REQUEST.json',req)
    atomic(DOC/'CHECKPOINT.json',dict(state='BASELINE_SEALED_GATE_A_NOT_RUN',Gate_A_PASS=False,
        Gate_B_PASS=False,Gate_C_PASS=False,Gate_D_PASS=False,May31_PASS=False,
        next_command='python -X utf8 -u -m v43.golden', request=record(DOC/'GOLDEN_REQUEST.json'),
        Source=record(DOC/'V43_BASELINE_AND_SOURCE_FREEZE.json')))
    print(json.dumps(dict(status='BASELINE_SEALED',sources=len(freeze['sources']),rollback='VERIFIED',known=len(known),attempt=str(attempt))))

if __name__ == '__main__': bootstrap()
