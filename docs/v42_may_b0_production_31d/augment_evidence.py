"""Add first-wave and bounded infrastructure-retry evidence to native results."""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from v42_b0_production.authority import DOC, read, record
from v42_orchestrator.ledger import atomic


def main():
    root = Path(read(DOC / 'RUN_LOCATION.json')['run_root'])
    execution = read(root / 'EXECUTION_RECEIPT.json')
    with (root / 'B0_RESOURCE_TIMELINE.csv').open(encoding='utf8') as handle:
        rows = list(csv.DictReader(handle))
    starts = [e for e in execution['events'] if e['event'] == 'START' and e['phase'] == 'PLANNING'][:4]
    days = [e['day'] for e in starts]
    end = max(e['elapsed_s'] for e in execution['events'] if e['event'] == 'END'
              and e['phase'] == 'PLANNING' and e['day'] in days)
    wave = [r for r in rows if float(r['elapsed_s']) <= end]
    wave_guards = [e for e in execution['downgrades'] if e['measured']['elapsed_s'] <= end]
    first = dict(days=days, admitted_workers=4, first_wave_workers=4,
        final_selected_workers=execution['selected_workers'], end_elapsed_s=end,
        peak_tree_RSS_GiB=max(float(r['B0_tree_RSS_GiB']) for r in wave),
        minimum_available_GiB=min(float(r['available_GiB']) for r in wave),
        maximum_commit_percent=max(float(r['commit_percent']) for r in wave),
        hard_guard_events_during_first_wave=wave_guards,
        subsequent_hard_guard_events=execution['downgrades'], PASS=not wave_guards)
    atomic(DOC / 'B0_FIRST_WAVE_RESOURCE_RECEIPT.json', first)
    failures = []
    for path in root.rglob('RESULT.json'):
        result = read(path)
        if result['status'] != 'ERROR':
            continue
        request = read(path.with_name('REQUEST.json'))
        failures.append(dict(day=request['day'], stage=request['stage'], status='RETRIED_INFRASTRUCTURE',
            failure_kind='INFRASTRUCTURE_TRANSIENT', reason=result['error_type']+': '+result['reason'],
            retry_count=1, native_result_path=str(path)))
    with (DOC / 'B0_FAILURE_LEDGER.csv').open('a', encoding='utf8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['day', 'stage', 'status', 'failure_kind', 'reason', 'retry_count'],
                                extrasaction='ignore', lineterminator='\n')
        writer.writerows(failures)
    atomic(DOC / 'B0_TRANSIENT_RETRY_DETAILS.json', dict(native_errors=failures,
        bounded_policy=True, scientific_inputs_changed=False))
    prior = read(DOC / 'SUPERSEDED_RUN_RECEIPT.json')
    prior['replacement_run_id'] = read(root / 'AUTHORITY.json')['run_id']
    prior['replacement_wall_seconds'] = execution['wall_seconds']
    prior['both_production_attempts_wall_seconds'] = prior['wall_seconds'] + execution['wall_seconds']
    atomic(DOC / 'SUPERSEDED_RUN_RECEIPT.json', prior)
    report = DOC / 'FINAL_REVIEW_KO.md'
    text = report.read_text(encoding='utf8')
    text = '\n\n'.join((f'8. 첫 4-worker wave PASS={first["PASS"]}; peak RSS={first["peak_tree_RSS_GiB"]:.6f} GiB, '
        f'available RAM min={first["minimum_available_GiB"]:.6f} GiB, commit max={first["maximum_commit_percent"]:.6f}%. '
        f'후반 실제 hard guard downgrade={execution["downgrades"]}.') if p.startswith('8. ') else p
        for p in text.split('\n\n'))
    note = ('자원 측정 간격 요건을 충족하지 못한 앞선 실행은 진단 이력으로 보존했다. '
             '최종 authority는 새 run ID로 생성한 두 번째 31일 실행이며 앞선 output을 재사용하지 않았다. '
             'SUPERSEDED_RUN_RECEIPT.json과 NONAUTHORITATIVE_OBSERVER_INTERVAL_RUN을 참조.\n\n')
    text = text.replace('“이번 실행은', note+'“이번 실행은')
    report.write_text(text, encoding='utf8', newline='\n')
    print(json.dumps(dict(first_wave=first, transient_errors=len(failures))))


if __name__ == '__main__':
    main()
