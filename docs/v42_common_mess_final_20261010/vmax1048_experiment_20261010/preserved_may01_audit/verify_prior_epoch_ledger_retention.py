"""Read-only source/evidence audit; imports no optimizer or AC engine."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import subprocess

OUT = Path(r'D:\v42_actual_voltage_audit_20261010')
NEW = Path(r'D:\v42_common_mess_campaign_20261010_02\COMMON_U4_QUALIFICATION_MANIFEST.json')
EXPECTED_SOURCE = 'ab5ce30460ed0fab7f7a69962af4ecabd63c3005b0983c865b6866f4dea4ee0e'
EXPECTED_COMMIT = '982c108e8c49ba6883a04bfa887bbae3501693be'

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def record(p):
    p = Path(p).resolve()
    with p.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(p), sha256=digest, bytes=p.stat().st_size)

def source_check(manifest):
    root = Path(manifest['code_root']).resolve()
    declared = manifest['execution_sources']
    current = {}
    for folder in sorted(root.glob('v42_*')):
        files = sorted(folder.rglob('*.py')) if folder.is_dir() else ([folder] if folder.suffix == '.py' else [])
        for path in files:
            current[path.relative_to(root).as_posix()] = record(path)['sha256']
    combined = hashlib.sha256(json.dumps(current, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(code_root=str(root), file_count=len(current), declared_file_count=len(declared),
                source_SHA=combined, declared_source_SHA=manifest['execution_SHA'],
                source_file_bytes_equal=current == declared,
                combined_SHA_equal=combined == manifest['execution_SHA'])

def finite_nonnegative(x):
    return type(x) in (int, float) and math.isfinite(x) and x >= 0

new = read(NEW)
new_source = source_check(new)
old_manifest_receipt = record(new['previous_common_epoch']['path'])
old = read(old_manifest_receipt['path'])
old_source = source_check(old)
commit = subprocess.run(['git', '-C', new['code_root'], 'rev-parse', 'HEAD'],
                        check=True, text=True, capture_output=True).stdout.strip()
rows = []
errors = []
for case, retained in sorted(new['prior_attempts'].items()):
    for stored in retained:
        result_record = record(stored['result']['path'])
        result = read(result_record['path'])
        result_ledger_receipt = result.get('native_ledger')
        ledger_record = record(result_ledger_receipt['path'])
        ledger = read(ledger_record['path'])
        calls = ledger.get('calls', [])
        checks = dict(
            retained_result_SHA_and_size_match=result_record == stored['result'],
            declared_RESULT_ledger_SHA_and_size_match=ledger_record == result_ledger_receipt,
            retained_ledger_SHA_and_size_match=ledger_record == stored.get('native_ledger'),
            retained_ledger_equals_RESULT_declared_ledger=stored.get('native_ledger') == result_ledger_receipt,
            completed_ledger_no_inflight=ledger.get('inflight') is None,
            at_least_one_completed_call=bool(calls),
            source_identity_matches_prior_manifest=(result.get('source_SHA') == stored['source_SHA'] == old['execution_SHA']
                and result.get('source_commit') == stored['source_commit'] == old['source_commit']),
            status_matches_retained_row=result.get('status') == stored.get('status'),
            all_calls_measured_completed=all(c.get('status') in ('FINISHED', 'FAILED')
                and c.get('entered_native') is True and c.get('runtime_unavailable') is False
                and finite_nonnegative(c.get('Native_Runtime')) for c in calls),
        )
        measured = sum(c.get('Native_Runtime', 0.) for c in calls) if checks['all_calls_measured_completed'] else None
        checks['call_sum_equals_ledger_Runtime'] = (measured is not None
            and finite_nonnegative(ledger.get('measured_Native_Runtime'))
            and math.isclose(measured, ledger['measured_Native_Runtime'], rel_tol=0, abs_tol=1e-9))
        checks['call_sum_equals_RESULT_Runtime'] = (measured is not None
            and finite_nonnegative(result.get('native_runtime_seconds'))
            and math.isclose(measured, result['native_runtime_seconds'], rel_tol=0, abs_tol=1e-9))
        checks['call_sum_equals_retained_Runtime'] = (measured is not None
            and finite_nonnegative(stored.get('native_runtime_seconds'))
            and math.isclose(measured, stored['native_runtime_seconds'], rel_tol=0, abs_tol=1e-9))
        checks['worker_wall_cost_retained'] = result.get('worker_wall_seconds') == stored.get('worker_wall_seconds')
        total = 0.
        limits_valid = True
        for call in calls:
            limit = call.get('effective_TimeLimit')
            if not finite_nonnegative(limit) or limit <= 0 or limit > 1800-total:
                limits_valid = False
            if finite_nonnegative(call.get('Native_Runtime')):
                total += call['Native_Runtime']
        checks['cumulative_native_limits_admitted'] = limits_valid
        row = dict(case=case, PASS=all(checks.values()), checks=checks,
            result_current=result_record, RESULT_declared_native_ledger=result_ledger_receipt,
            ledger_current=ledger_record, retained_result=stored['result'],
            retained_native_ledger=stored.get('native_ledger'), status=result['status'],
            native_call_count=len(calls), measured_native_runtime_seconds=measured,
            worker_wall_seconds=result.get('worker_wall_seconds'),
            calls=[{k:c.get(k) for k in ('component', 'track', 'label', 'status', 'Native_Runtime',
                'effective_TimeLimit', 'Native_status', 'runtime_unavailable', 'entered_native')} for c in calls])
        rows.append(row)
        errors.extend(case+':'+name for name, passed in checks.items() if not passed)

checks = dict(
    new_source_bytes_match=new_source['source_file_bytes_equal'] and new_source['combined_SHA_equal'],
    expected_new_source_SHA=new['execution_SHA'] == EXPECTED_SOURCE,
    expected_new_commit=new['source_commit'] == commit == EXPECTED_COMMIT,
    old_manifest_receipt_matches=old_manifest_receipt == new['previous_common_epoch'],
    old_frozen_source_bytes_match=old_source['source_file_bytes_equal'] and old_source['combined_SHA_equal'],
    both_prior_cases_present=set(new['prior_attempts']) == {'B2/2025-05-01', 'B2/2025-05-02'},
    all_prior_attempts_pass=all(row['PASS'] for row in rows) and len(rows) == 2,
)
errors.extend(name for name, passed in checks.items() if not passed)
audit = dict(schema='V42_PRIOR_COMMON_EPOCH_LEDGER_RETENTION_AUDIT_V1',
    UTC=datetime.now(timezone.utc).isoformat(), PASS=all(checks.values()),
    launch_blocked_due_to_actual_drift=not all(checks.values()), errors=errors,
    native_optimize_calls=0, OpenDSS_calls=0, source_mutation_count=0, original_evidence_mutation_count=0,
    new_manifest=record(NEW), new_source_SHA=new['execution_SHA'], new_source_commit=new['source_commit'],
    new_source=new_source, previous_manifest_current=old_manifest_receipt, previous_source=old_source,
    checks=checks, inherited_completed_attempt_count=len(rows), full_ledger_count=len(rows),
    full_ledger_native_call_count=sum(row['native_call_count'] for row in rows),
    preserved_historical_native_runtime_seconds=sum(row['measured_native_runtime_seconds'] or 0 for row in rows),
    preserved_historical_worker_wall_seconds=sum(row['worker_wall_seconds'] or 0 for row in rows),
    ledger_count_scope='All completed common-U4 epoch-1 attempts retained in epoch-2 prior_attempts',
    attempts=rows)
path = OUT/'PRIOR_EPOCH_LEDGER_RETENTION_AUDIT.json'
path.write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
print(json.dumps(dict(path=str(path), audit_receipt=record(path), PASS=audit['PASS'], errors=errors,
    new_source_SHA=audit['new_source_SHA'], new_source_file_count=new_source['file_count'],
    old_source_file_count=old_source['file_count'], full_ledger_count=audit['full_ledger_count'],
    full_ledger_native_call_count=audit['full_ledger_native_call_count'],
    preserved_historical_native_runtime_seconds=audit['preserved_historical_native_runtime_seconds']), indent=2))
raise SystemExit(0 if audit['PASS'] else 1)
