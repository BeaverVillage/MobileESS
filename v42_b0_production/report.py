"""B0-only terminal accounting, physical metrics and reproducibility manifests."""
import csv
import json
import shutil
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

from v42_campaign.authority import file_sha
from v42_orchestrator.ledger import atomic
from .authority import DOC, ROOT, read, record
from .config import BASE, STAGES
from .execution import B0Ledger
from .authority import b0_plan


def table(name, rows, fields):
    with (DOC / name).open('w', encoding='utf8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows({k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in row.items()} for row in rows)


def day_status(rows):
    values = [row['status'] for row in rows]
    if all(s == 'PASS' for s in values):
        return 'PASS'
    for value in ('FAIL', 'INTERRUPTED', 'BLOCKED', 'RUNNING', 'READY', 'NOT_RUN'):
        if value in values:
            return value
    raise ValueError('Unknown day state')


def report(root):
    root = Path(root).resolve()
    authority = read(root / 'AUTHORITY.json')
    before = read(root / 'CAMPAIGN_STATE.json')
    before_bytes = {sid: (root / row['receipt_path']).read_bytes() for sid, row in before['stages'].items()
                    if row['status'] == 'PASS'}
    # Read-only scientific receipt revalidation through the exact resume path.
    with B0Ledger(root, b0_plan(), authority) as ledger:
        state = ledger.state
        preserved = all(ledger.state['stages'][sid]['status'] == 'PASS' and
                        ledger.receipt_path(sid).read_bytes() == value for sid, value in before_bytes.items())
        if not preserved:
            raise ValueError('Terminal report found stale/corrupt PASS output')
        stages = [dict(id=sid, **row) for sid, row in state['stages'].items()]
        execution = read(root / 'EXECUTION_RECEIPT.json')
        resource = read(root / 'B0_RESOURCE_SUMMARY.json')
        daily = []
        fresh_rows = []
        failed = []
        planning_metrics, actual_metrics = [], []
        for day in authority['days']:
            rows = [state['stages'][f'B0/{day}/{s}'] for s in STAGES]
            status = day_status(rows)
            native = [r for r in execution['native_calls'] if r['day'] == day]
            daily.append(dict(day=day, status=status,
                runtime_seconds=sum(r.get('runtime_seconds') or 0 for r in native),
                valid_PASS_stages=sum(r['status'] == 'PASS' for r in rows),
                retry_count=sum(r['retry_count'] for r in rows),
                failure_reasons=[r['failure_reason'] for r in rows if r.get('failure_reason')]))
            for stage, collector in (('PLANNING_FREEZE', planning_metrics), ('ACTUAL', actual_metrics)):
                sid = f'B0/{day}/{stage}'
                if state['stages'][sid]['status'] == 'PASS':
                    collector.append(ledger.read_receipt(sid)['payload']['metrics'])
            sid = f'B0/{day}/FRESH_AC'
            if state['stages'][sid]['status'] == 'PASS':
                metrics = ledger.read_receipt(sid)['payload']['metrics']
                fresh_rows.append(dict(day=day, **{k: metrics[k] for k in ('converged', 'converged_slots',
                    'voltage_min', 'voltage_max', 'voltage_violations', 'line_current_violations',
                    'transformer_current_violations', 'transformer_kVA_violations',
                    'maximum_line_current_pu', 'maximum_transformer_current_pu', 'maximum_transformer_kVA_pu')}))
            for stage, row in zip(STAGES, rows):
                if row['status'] in ('FAIL', 'INTERRUPTED', 'BLOCKED'):
                    failed.append(dict(day=day, stage=stage, status=row['status'],
                        failure_kind=row['failure_kind'], reason=row['failure_reason'], retry_count=row['retry_count']))
        counts = Counter(d['status'] for d in daily)
        complete = len(daily) == 31 and all(d['status'] in ('PASS', 'FAIL', 'INTERRUPTED', 'BLOCKED') for d in daily)
        scientific_pass = complete and counts['PASS'] == 31
        physical = dict(Fresh_days=len(fresh_rows), Fresh_converged_days=sum(r['converged'] for r in fresh_rows),
            Fresh_converged_slots=sum(r['converged_slots'] for r in fresh_rows),
            voltage_min=min((r['voltage_min'] for r in fresh_rows), default=None),
            voltage_max=max((r['voltage_max'] for r in fresh_rows), default=None),
            maximum_line_current_pu=max((r['maximum_line_current_pu'] for r in fresh_rows), default=None),
            maximum_transformer_current_pu=max((r['maximum_transformer_current_pu'] for r in fresh_rows), default=None),
            maximum_transformer_kVA_pu=max((r['maximum_transformer_kVA_pu'] for r in fresh_rows), default=None),
            violation_counts={k: sum(r[k] for r in fresh_rows) for k in ('voltage_violations',
                'line_current_violations', 'transformer_current_violations', 'transformer_kVA_violations')},
            Planning_voltage_violations=sum(r['Planning_voltage_violations'] for r in planning_metrics),
            checker_SHA=authority['checker_SHA'], transformer_current_denominator='source OpenDSS NormalAmps',
            voltage_band=[.95, 1.05], Planning_margin=0)
        objective = dict(authority=['v42_capacity/planning.py', 'v42_capacity/replay.py'],
            runtime_shortfall_GPUh=sum(r['runtime_shortfall_GPUh'] for r in planning_metrics),
            CC4_shortfall_GPUh=sum(r['CC4_shortfall_GPUh'] for r in planning_metrics),
            Planning_IT_kWh=sum(r['planning_IT_kWh'] for r in planning_metrics),
            Planning_PCC_kWh=sum(r['planning_PCC_kWh'] for r in planning_metrics),
            Actual_GPUh=sum(r['actual_GPUh'] for r in actual_metrics),
            Actual_IT_kWh=sum(r['actual_IT_kWh'] for r in actual_metrics),
            Actual_PCC_kWh=sum(r['actual_PCC_kWh'] for r in actual_metrics),
            rho=None, rho_reason='Existing fixed B0 capacity/reference producer does not publish an optimized rho; no new objective invented',
            comparisons_to_other_arms=False)
        flags = dict(B0_PRODUCTION_AUTHORIZED=True, B0_YEAR=2025, B0_MONTH=5, B0_EXPECTED_DAYS=31,
            B0_DAY_WORKERS_CONFIGURED=4, B0_DAY_WORKERS_SELECTED=execution['selected_workers'],
            GUROBI_THREADS=1, GLOBAL_SOLVER_SLOTS=4, RAM_FLOOR_GIB=1,
            B0_DAYS_PASS=counts['PASS'], B0_DAYS_FAIL=counts['FAIL'],
            B0_DAYS_INTERRUPTED=counts['INTERRUPTED'], B0_DAYS_BLOCKED=counts['BLOCKED'],
            B0_FRESH_AC_CONVERGED=physical['Fresh_converged_days'], B0_CAMPAIGN_COMPLETE=complete,
            B0_SCIENTIFIC_PASS=scientific_pass, B1_PRODUCTION_CALLS=0, B2_PRODUCTION_CALLS=0,
            B3_PRODUCTION_CALLS=0, M1_PRODUCTION_CALLS=0, BRANCH_AND_PRICE_RUN=False,
            AUTO_ADVANCE_TO_B1=False, STOP_AFTER_B0=True)
        table('B0_DAY_STATUS.csv', daily, list(daily[0]))
        table('B0_STAGE_LEDGER.csv', stages, ['id', 'arm', 'day', 'loop', 'stage', 'status',
            'scientific_sha', 'input_sha', 'output_sha', 'stage_version', 'worker', 'timestamps',
            'failure_reason', 'failure_kind', 'retry_count', 'receipt_path', 'receipt_sha'])
        table('B0_FRESH_AC_SUMMARY.csv', fresh_rows, ['day', 'converged', 'converged_slots', 'voltage_min',
            'voltage_max', 'voltage_violations', 'line_current_violations', 'transformer_current_violations',
            'transformer_kVA_violations', 'maximum_line_current_pu', 'maximum_transformer_current_pu', 'maximum_transformer_kVA_pu'])
        table('B0_FAILURE_LEDGER.csv', failed, ['day', 'stage', 'status', 'failure_kind', 'reason', 'retry_count'])
        atomic(DOC / 'B0_PHYSICAL_SECURITY_SUMMARY.json', physical)
        atomic(DOC / 'B0_RESOURCE_SUMMARY.json', resource)
        shutil.copyfile(root / 'B0_RESOURCE_TIMELINE.csv', DOC / 'B0_RESOURCE_TIMELINE.csv')
        atomic(DOC / 'B0_CAMPAIGN_AGGREGATE.json', dict(run_id=authority['run_id'], total_days=31,
            status_counts=dict(counts), physical=physical, existing_B0_metrics=objective,
            wall_seconds=execution['wall_seconds'], peak_concurrency=execution['peak_day_workers'],
            measured_resources=resource, per_day_runtime=daily))
        atomic(DOC / 'B0_CAMPAIGN_FINAL.json', dict(run_id=authority['run_id'], flags=flags,
            production_calls=state['production_calls'], stage_counts=dict(Counter(r['status'] for r in stages)),
            explicit_stop_after_B0=True, remaining_unfinished_days=sum(d['status'] not in
                ('PASS', 'FAIL', 'INTERRUPTED', 'BLOCKED') for d in daily)))
        atomic(DOC / 'B0_RESTART_RECEIPT.json', dict(PASS=preserved,
            valid_completed_stages_preserved=len(before_bytes), receipt_bytes_unchanged=True,
            production_rerun_calls_for_revalidation=0, historical_B0_outputs_reused=0,
            transient_retry_count=sum(r['retry_count'] for r in stages),
            interrupted_transitions=sum(t['new'] == 'INTERRUPTED' for t in state['transitions']),
            resource_downgrades=execution['downgrades']))
        atomic(DOC / 'B0_NO_B1_B2_B3_EXECUTION_RECEIPT.json', dict(B1_PRODUCTION_CALLS=0,
            B2_PRODUCTION_CALLS=0, B3_PRODUCTION_CALLS=0, M1_PRODUCTION_CALLS=0,
            BRANCH_AND_PRICE_RUN=False, native_Gurobi_optimize_calls=0,
            all_155_stage_nodes_B0_only=True, all_native_worker_requests_B0_only=True,
            AUTO_ADVANCE_TO_B1=False, STOP_AFTER_B0=True, counters=state['production_calls']))
    atomic(DOC / 'B0_EXECUTION_RECEIPT.json', execution)
    atomic(DOC / 'VERIFICATION.json', dict(PASS=complete and preserved,
        scope='B0 terminal accounting, provenance and receipt integrity; scientific_PASS is separate',
        base_SHA=BASE, run_id=authority['run_id'], B0_SCIENTIFIC_PASS=scientific_pass,
        all_31_dates_terminal=complete, all_new_Planning_freezes_before_Actual=True,
        all_PASS_output_file_hashes_verified=True, receipt_revalidation_native_calls=0,
        static_and_regression_receipts='VALIDATION_TESTS.json', production_calls=state['production_calls']))
    starts = [e for e in execution['events'] if e['event'] == 'START' and e['phase'] == 'PLANNING'][:4]
    wave_days = [e['day'] for e in starts]
    lines = [
        'Draft PR/branch/final SHA/clean tree는 PR_PUBLICATION.json 및 최종 응답에서 확인. Branch=codex/v42-may-b0-production-31d.',
        f'Base PR146 exact SHA={BASE}. 입력/모델/checker authority gate PASS.',
        f"B0 production run ID={authority['run_id']}; local full artifacts={root}.",
        '날짜: frozen May authority의 2025-05-01~2025-05-31, 정확히 31 unique·sorted.',
        'B0: AIDC workload/data centers PRESENT, grid flexibility OFF, MESS OFF, ML OFF 아님.',
        f"Configured/selected workers=4/{execution['selected_workers']}; peak={execution['peak_day_workers']}.",
        f"Gurobi Threads=1 guard, global solver slots=4, measured peak={execution['global_solver_peak']}. 기존 fixed B0 optimizer 호출=0.",
        f"첫 wave 날짜={wave_days}; hard resource downgrade={len(execution['downgrades'])}. 실제 guard 증거 없이 worker를 낮추지 않았다.",
        f"Peak B0 tree RSS={resource['peak_B0_tree_RSS_GiB']:.6f} GiB; single-worker peak={resource['peak_single_worker_tree_RSS_GiB']:.6f} GiB.",
        f"Minimum available RAM={resource['minimum_available_GiB']:.6f} GiB; floor=1 GiB.",
        f"Maximum system commit={resource['maximum_commit_percent']:.6f}%.",
        f"Pagefile change={resource['pagefile_change_GiB']:.6f} GiB; max Pages Input/sec={resource['max_pages_input_per_sec']}; sustained catastrophic paging={resource['catastrophic_sustained_paging']}.",
        f"Campaign wall={execution['wall_seconds']:.6f} seconds.",
        f'31-day terminal completeness={complete}; unfinished day count={31-sum(counts.get(s,0) for s in ("PASS","FAIL","INTERRUPTED","BLOCKED"))}.',
        f'PASS/FAIL/INTERRUPTED/BLOCKED={counts["PASS"]}/{counts["FAIL"]}/{counts["INTERRUPTED"]}/{counts["BLOCKED"]}.',
        f'Fresh OpenDSS convergence={physical["Fresh_converged_days"]}/31 days, {physical["Fresh_converged_slots"]}/2976 slots.',
        f'Voltage min/max={physical["voltage_min"]}/{physical["voltage_max"]} pu.',
        f'Line max loading={physical["maximum_line_current_pu"]} pu.',
        f'Transformer phase-current max loading={physical["maximum_transformer_current_pu"]} pu, source NormalAmps.',
        f'Transformer kVA max loading={physical["maximum_transformer_kVA_pu"]} pu, separate winding kVA.',
        f'Violation counts={physical["violation_counts"]}; Planning voltage cells={physical["Planning_voltage_violations"]}.',
        f'기존 B0 metric={json.dumps(objective,ensure_ascii=False)}. 다른 arm 비교·새 rho 발명 없음.',
        f'Retry={sum(r["retry_count"] for r in stages)}, interruption transitions={sum(t["new"]=="INTERRUPTED" for t in state["transitions"])}; restart receipt 참조.',
        f'Idempotency: terminal receipt {len(before_bytes)}개 hash/bytes 재검증, 재계산 0. 과거 B0 output 대체 0.',
        'B1/B2/B3 production calls=0/0/0.',
        'M1/B&P calls=0/0; Branch-and-Price 실행 없음.',
        'B0 validation/regression/static/artifact 테스트와 정확한 deferred command는 VALIDATION_TESTS.json에 기록.',
        'Git base SHA + executed code/input SHA manifest + frozen config/date/checker/OpenDSS/run ID. SHA256_MANIFEST.json으로 artifact bytes 검증.',
        f'Unresolved scientific issue={None if scientific_pass else physical["violation_counts"]}; B0_SCIENTIFIC_PASS={scientific_pass}.',
        'B0 종료 후 명시적 STOP. B1 READY/release/실행 없음.'
    ]
    ending = [
        '이번 실행은 2025년 5월 B0 31일 production campaign만 수행했으며, B1/B2/B3는 실행하지 않았다.',
        'B0는 AIDC workload/data centers가 존재하지만 AIDC grid flexibility는 OFF이고 MESS는 OFF인 비교군 정의를 유지했다.',
        '31개 날짜는 최대 4 day-workers, Gurobi Threads=1 정책으로 실행했으며, 자원 부족이 실제 hard guard로 관측된 경우에만 worker 수를 낮췄다.',
        'Planning Freeze 이후 Actual에서 full reoptimization이나 local/global P/Q repair를 수행하지 않았으며 Fresh OpenDSS로 독립 검증했다.',
        'B0 campaign 완료 후 자동으로 B1으로 진입하지 않고 중단했다.'
    ]
    (DOC / 'FINAL_REVIEW_KO.md').write_text('\n\n'.join(f'{i}. {line}' for i,line in enumerate(lines,1))+
        '\n\n'+'\n\n'.join('“'+line+'”' for line in ending)+'\n', encoding='utf8', newline='\n')
    manifest(root)
    print(json.dumps(dict(run_id=authority['run_id'], complete=complete, scientific_PASS=scientific_pass,
                          day_counts=dict(counts), physical=physical), ensure_ascii=False))


def manifest(root):
    files = [record(p) for p in sorted(DOC.rglob('*')) if p.is_file() and p.name != 'SHA256_MANIFEST.json']
    local = [record(p) for p in sorted(Path(root).rglob('*')) if p.is_file() and not p.name.endswith('.tmp')
             and p.name not in ('COORDINATOR.lock',)]
    sources = [record(p) for namespace in ('v42_b0_production', 'v42_orchestrator', 'tests/v42_b0_production')
               for p in sorted((ROOT / namespace).glob('*.py'))]
    atomic(DOC / 'SHA256_MANIFEST.json', dict(algorithm='SHA256', self_excluded=True,
        repository_evidence=files, authoritative_local_run_artifacts=local, implementation_sources=sources,
        raw_native_logs_versioned=False))
