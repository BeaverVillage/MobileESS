"""Read V17 identities and certificates; never dispatch or touch a Solver."""
from pathlib import Path
from types import SimpleNamespace
import time
from v42_b2_start_recovery_v13 import coordinator as co
from v42_campaign_monitor import monitor as display
from v42_b2_monitor_v15.actual import comparison
from v42_b2_monitor_v16.certificates import enrich, certificate, optional
from v42_may_campaign_native90.a_routing import rebound
from v42_may_campaign_native90.common import exclusive_lock, LockBusy
from v42_pr134_b1.common import same_process

VERSION = 'B2_RECOVERY_NATIVE_AND_CERTIFICATE_MONITOR_V18'
NATIVE_FIELDS = ('Native_SolCount', 'Native_solution_count_callback', 'Native_incumbent',
    'Native_BestBd', 'Native_Gap', 'Native_NodeCount', 'Native_open_nodes',
    'Native_root_progress', 'Native_subphase', 'Native_iteration_count',
    'Native_first_incumbent_Runtime', 'Native_first_incumbent_UTC', 'Native_observation_UTC', 'Native_objective_basis')


def worker_view(root, day, row, epoch):
    request = co.read(row['request'])
    progress = optional(request['progress'])
    active = dict(arm='B2', day=day, request=row['request'], worker_slot=request['worker_slot'],
        started_UTC=request['started_UTC'], worker=progress.get('worker', {}))
    worker = display.enrich_worker(co.worker_snapshot(active), epoch)
    ledger = optional(Path(request['result']).parent/'NATIVE_RUNTIME_LEDGER.json')
    manifest=optional(request.get('manifest','')) if request.get('manifest') else {}
    cap=manifest.get('initialization_native_limit_seconds',5400.)
    completed = ledger.get('measured_Native_Runtime')
    reported = progress.get('Native_Runtime')
    eligible = (bool(ledger.get('inflight')) and display.finite(completed)
        and progress.get('Native_Runtime_completed') == completed
        and display.finite(reported) and reported >= completed)
    used = reported if eligible else completed
    worker.update(Native_Runtime_seconds=completed, reported_native_runtime_seconds=used,
        reported_native_remaining_seconds=max(0.,cap-used) if display.finite(used) else None,
        native_limit_seconds=cap,
        native_runtime_basis='SOLVER_CALLBACK_CURRENT_CALL_INCLUDED' if eligible else 'COMPLETED_NATIVE_LEDGER',
        global_gap_display=dict(available=False,value=None,target=.03),
        worker_result_received=Path(request['result']).is_file(),
        prior_native_runtime_seconds=(ledger.get('prior_attempt') or {}).get('Native_Runtime',0),
        attempt_id=request['attempt_id'], source_SHA=request['implementation_SHA'])
    if ledger.get('budget_basis')=='CONSERVATIVE_LOST_CALL_WINDOW':
        accounted=progress.get('Native_budget_accounted_upper_bound',ledger.get('Native_budget_accounted_upper_bound'))
        worker.update(Native_Runtime_seconds=None,reported_native_runtime_seconds=accounted,
            reported_native_remaining_seconds=max(0.,5400-accounted) if display.finite(accounted) else None,
            native_runtime_basis='CONSERVATIVE_LOST_CALL_WINDOW',actual_cumulative_Native_Runtime='UNKNOWN',
            current_attempt_measured_Native_Runtime=ledger.get('current_attempt_measured_Native_Runtime'),
            lost_call_reserved_seconds=(ledger.get('prior_attempt') or {}).get('lost_call_reserved_seconds'))
    # Only file-backed independent certificates may supply these three fields.
    worker.update(UB=None, independent_Global_LB=None, Certified_Gap=None)
    worker = enrich(worker)
    output = Path(request['output'])
    seed_certificate=output/'BENCHMARK_FULL_CERTIFICATE.json'
    if not seed_certificate.exists():seed_certificate=output/'STATIONARY_DISPATCH_REPLAY.json'
    if worker['UB'] is None and seed_certificate.is_file():
        identity = optional(output/'SCIENTIFIC_CASE_IDENTITY.json')
        try:
            if identity.get('arm') != 'B2' or identity.get('day') != day:
                raise ValueError('CURRENT_DAY_CASE_REQUIRED')
            evidence = certificate(seed_certificate,output,identity['case_sha'],'UB')
            worker['UB'] = evidence['value']
            worker['bound_status'].update(UB_reason='같은 날짜 FULL 물리·정수 검증 통과',UB_certificate=evidence)
            worker['global_gap_display']['reason'] = '검증된 초기해 확보 · 독립 LB 인증 대기'
        except (OSError,ValueError,KeyError,TypeError) as error:
            worker['bound_status']['stationary_certificate_error'] = str(error)
    native = {k:progress.get(k,'UNKNOWN') for k in NATIVE_FIELDS}
    native['diagnostic_only'] = True
    worker['native_diagnostics'] = native
    worker['bound_status'].update(solver_bounds_available=True,
        solver_bounds_reason='Native 값은 탐색 진단이며 Global Gap은 독립 인증서로 계산')
    track = (ledger.get('inflight') or {}).get('track')
    if track == 'M_START':worker['bound_status']['phase_label'] = '같은 날짜 dispatch 초기해 탐색'
    if track=='M_MODE_GUIDE':worker['bound_status']['phase_label']='같은 날짜 LP로 이산 모드 후보 생성'
    if Path(request['result']).is_file():
        result=optional(request['result']);scientific=result.get('scientific',{})
        if result.get('benchmark_initialization_only'):
            worker['initialization_benchmark']=dict(status=result['status'],
                first_FULL_pass_wall_seconds=scientific.get('first_FULL_pass_wall_seconds'),
                LP_Runtime=scientific.get('LP_Runtime'),seed_MILP_calls=scientific.get('seed_MILP_calls'),
                seed_MILP_Runtime=scientific.get('seed_MILP_Runtime'),point_SHA=scientific.get('point_SHA'),
                first_FULL_stage=scientific.get('first_FULL_stage'))
    return worker


def view(root):
    root = Path(root)
    campaign=root
    v19=[(p.name,'CHECKPOINT_V19.json') for p in sorted(campaign.glob('initialization_benchmark_v19_[0-9][0-9]'),reverse=True)]
    for candidate,checkpoint in v19+[('initialization_benchmark_v18r3_01','CHECKPOINT_V18R3.json'),('initialization_benchmark_v18r2_01','CHECKPOINT_V18R2.json')]:
        benchmark=campaign/candidate
        if (benchmark/checkpoint).exists():root=benchmark;break
    version=19 if (root/'CHECKPOINT_V19.json').is_file() else '18R3' if (root/'CHECKPOINT_V18R3.json').is_file() else '18R2' if (root/'CHECKPOINT_V18R2.json').is_file() else 18 if (root/'CHECKPOINT_V18.json').is_file() else 17
    cp = co.read(root/f'CHECKPOINT_V{version}.json')
    manifest = co.read(root/f'CONTINUATION_V{version}_MANIFEST.json')
    workers = [worker_view(root,day,row,time.time()) for day,row in cp.get('workers',{}).items()]
    if manifest.get('benchmark_initialization_only'):
        for day in manifest['canary_days']:
            row=cp['dates']['B2/'+day]
            if day not in cp.get('workers',{}) and row.get('request') and row.get('result'):
                workers.append(worker_view(root,day,row,time.time()))
        if version=='18R3':
            row=cp['dates']['B2/2025-05-02']
            if row.get('request') and row.get('result'):
                worker=worker_view(root,'2025-05-02',row,time.time())
                worker.update(worker_slot=2,original_execution_slot=1)
                workers.append(worker)
        if version==19:
            # Display slots identify dates; both sequential executions use slot 1.
            for worker in workers:
                worker.update(original_execution_slot=worker['worker_slot'],
                    worker_slot=manifest['canary_days'].index(worker['day'])+1)
            row=cp['dates'].get('B2/2025-05-02',{})
            if row.get('request') and row.get('result'):
                historical=worker_view(root,'2025-05-02',row,time.time())
                historical.update(original_execution_slot=historical['worker_slot'],worker_slot=3,historical_comparison=True)
                workers.append(historical)
    slots = []
    for slot in range(1,4):
        worker = next((w for w in workers if w['worker_slot']==slot),None)
        if worker is None:
            waiting_day = (manifest['canary_days'][slot-1] if version==19 and slot<=len(manifest['canary_days']) else f'2025-05-{slot:02d}' if version==17 else None) if not cp.get('canary_PASS') else None
            prior = manifest.get('prior_attempts',{}).get(waiting_day,{})
            used = prior.get('Native_Runtime')
            worker = dict(worker_slot=slot, arm='B2', day=waiting_day, display_waiting=True,
                worker_alive=False, phase='HELD_FOR_CANARY' if not cp.get('canary_PASS') else 'IDLE',
                waiting_reason=('May03/04 초기해 성능시험 · 날짜 순서대로 실행' if version==19 else 'May01 독립 인증·Adaptive 실행 확인 후 재개' if version==17 else 'May02/03 LP 직접 채택·인증·Adaptive 확인 후 재개') if not cp.get('canary_PASS') else '날짜 배정 대기',
                Native_Runtime_seconds=used, native_remaining_seconds=max(0.,5400.-used) if display.finite(used) else None)
        slots.append(worker)
    heartbeat = optional(root/f'COORDINATOR_V{version}_HEARTBEAT.json')
    alive = same_process(heartbeat.get('process',{}))
    initial_summary=None
    if manifest.get('benchmark_initialization_only'):
        measured=[w for w in workers if w['day'] in manifest['canary_days'] and w.get('worker_result_received')]
        passed=sum(w.get('UB') is not None for w in measured)
        initial_summary=dict(FULL_PASS=passed,failed=len(measured)-passed,
            completed=len(measured),total=len(manifest['canary_days']))
    return display.clean(dict(run_id=manifest['run_id'],state=cp['state'],
        algorithm_version=manifest['schema'],display_version=VERSION,runtime_root=str(root),
        coordinator_alive=alive,canary_PASS=bool(cp.get('canary_PASS')),parallel_workers=cp.get('parallel_workers',1),
        canary_label='May03/04' if version==19 else 'May01' if version==17 else 'May02/03',
        B1=co.counts(cp,'B1'),B2=co.counts(cp,'B2'),workers=workers,worker_slots=slots,
        B2_validation_detail=dict(PASS=True,status=cp['state'],error=None),
        actual_comparison=comparison(cp['dates']),last_error=cp.get('last_error'),
        source_SHA=manifest['execution_SHA'],telemetry_only=True,
        initialization_summary=initial_summary,
        benchmark_initialization_only=manifest.get('benchmark_initialization_only',False)))


def run(root):
    try:
        with exclusive_lock(Path(root)/'MONITOR_GAP_V8.lock'):
            proxy=SimpleNamespace(runtime_path=co.runtime_path,
                load_manifest=lambda root,verify=False: co.read(Path(root)/'CONTINUATION_V17_MANIFEST.json'))
            return rebound(display.run,dict(display.run.__globals__,original=proxy,view=view,__file__=__file__))(root)
    except LockBusy:
        return 0
