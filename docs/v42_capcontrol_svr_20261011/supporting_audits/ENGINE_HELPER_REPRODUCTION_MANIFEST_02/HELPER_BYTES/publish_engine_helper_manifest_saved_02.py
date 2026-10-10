"""Publish exact helper bytes and preserved dispatcher journal history. File-only."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import shutil
import sys

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def record(path):
    p = Path(path).resolve(); data = p.read_bytes()
    return {'path': str(p), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

def main(args):
    sys.path.insert(0, str(Path(args.source).resolve()))
    from v42_voltage_control.authority import source_files
    from v42_b3_joint.contracts import digest
    source = source_files(); source_sha = digest(source)
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=False)
    helpers = output/'HELPER_BYTES'; helpers.mkdir()
    prior = read(args.prior_manifest)
    assert prior['execution_source_SHA'] == source_sha
    def copy(path, name):
        src = Path(path); dst = helpers/name
        shutil.copyfile(src, dst)
        assert record(src)['sha256'] == record(dst)['sha256']
        return {'original': record(src), 'archive': record(dst),
                'proposed_Git_destination': 'docs/v42_voltage_control/evidence_helpers/'+name+'.txt'}
    rows = []
    for row in prior['helpers']:
        assert record(row['original']['path']) == row['original']
        rows.append({**row, **copy(row['original']['path'], row['name'])})
    rows.append({'name': Path(__file__).name, 'role': 'This saved-artifact manifest publisher; no physical or optimization execution',
                 **copy(__file__, Path(__file__).name)})
    root = Path(args.root).resolve()
    proof = read(root/'DISPATCH_SOURCE_RECEIPT.json')
    progress = read(root/'DISPATCH_PROGRESS.json')
    recovery = read(root/'DISPATCH_FINAL_RECEIPT_RECOVERY.json')
    assert proof['source_map'] == source and proof['source_SHA'] == recovery['source_after_SHA'] == source_sha
    assert progress['running'] == [] and progress['status'] == 'STOPPED_PHYSICAL_CANARY_FAILURE'
    assert progress['completed_comparisons'] == 10 and progress['remaining_comparisons'] == 120
    original = Path(proof['dispatcher']['path'])
    assert record(original) == proof['dispatcher']
    assert original.read_bytes() == (root/'DISPATCHER_USED.py').read_bytes()
    broken = original.read_text(encoding='utf8')
    fixed = Path(args.future_v2).read_text(encoding='utf8')
    old = 'dict(**final,source_after_SHA=digest(source_files()),Native_optimizer_calls=0)'
    new = 'dict(final,source_after_SHA=digest(source_files()),Native_optimizer_calls=0)'
    assert broken.count(old) == 1 and broken.replace(old, new) == fixed
    original_copy = copy(root/'DISPATCHER_USED.py', 'ORIGINAL_DISPATCHER_USED.py')
    driver_copy = copy(proof['driver']['path'], 'ORIGINAL_DAY_DRIVER_USED.py')
    assert record(proof['driver']['path']) == proof['driver']
    v2_copy = copy(args.future_v2, 'run_ac_only_svr_comparison_v2.py')
    for item in recovery['actual_day_results']:
        assert record(item['path']) == item
    shutil.copyfile(root/'DISPATCH_FINAL_RECEIPT_RECOVERY.json', output/'PRESERVED_DISPATCH_FINAL_RECEIPT_RECOVERY.json')
    shutil.copyfile(Path(args.prior_manifest).parent/'REPRODUCTION_KO.md', output/'REPRODUCTION_KO.md')
    result = {**prior, 'schema': 'V42_ENGINE_HELPER_REPRODUCTION_MANIFEST_V2',
              'created_UTC': datetime.now(timezone.utc).isoformat(), 'helpers': rows,
              'previous_manifest': record(args.prior_manifest),
              'original_dispatcher_history': {**original_copy, 'execution_status': 'EXECUTED_AND_PRESERVED',
                  'physical_control_or_hardware_error': False,
                  'journal_error': 'TypeError duplicate Native_optimizer_calls keyword only after saved physical STOP and ten completed day results.'},
              'original_day_driver': driver_copy,
              'future_dispatcher_v2': {**v2_copy, 'execution_status': 'NOT_EXECUTED',
                  'difference': 'Single final-journal dict(**final,...) -> dict(final,...) replacement.',
                  'new_AC_or_optimizer_calls': 0},
              'terminal_recovery': record(root/'DISPATCH_FINAL_RECEIPT_RECOVERY.json'),
              'current_dispatch_pin_guard_audit': record(args.pin_audit),
              'current_known_four_time_current_audit': record(args.time_current_audit),
              'terminal_scope': {'planned_comparisons': 130, 'completed_comparisons': 10,
                  'PASS': 8, 'PHYSICAL_FAIL': 2, 'IMPLEMENTATION_FAILURE': 0,
                  'unexecuted_comparisons_due_canary_gate': 120, 'status': progress['status'],
                  'all31May_qualified': False, 'new_model_E2E_qualified': False,
                  'physical_failures_preserved': True},
              'source_before_after_exact': source_files() == source,
              'Native_optimizer_calls': 0, 'OpenDSS_calls_in_manifest_generation': 0}
    (output/'ENGINE_HELPER_REPRODUCTION_MANIFEST.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({'PASS': result['source_before_after_exact'], 'helpers': len(rows), 'future_v2': 'NOT_EXECUTED', 'output': str(output)}))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True)
    p.add_argument('--root', required=True)
    p.add_argument('--prior-manifest', required=True)
    p.add_argument('--future-v2', required=True)
    p.add_argument('--pin-audit', required=True)
    p.add_argument('--time-current-audit', required=True)
    p.add_argument('--output', required=True)
    main(p.parse_args())
