"""Read-only saved/run provenance audit. No OpenDSS compilation or solver calls."""
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
    p = Path(path).resolve()
    data = p.read_bytes()
    return {'path': str(p), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}

def same(a, b):
    return (Path(a['path']).resolve() == Path(b['path']).resolve()
            and a['sha256'] == b['sha256'] and a['bytes'] == b['bytes'])

def main(args):
    sys.path.insert(0, str(Path(args.source).resolve()))
    from v42_voltage_control.authority import source_files
    from v42_b3_joint.contracts import digest
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    receipt_path = root/'DISPATCH_SOURCE_RECEIPT.json'
    proof = read(receipt_path)
    initial_sources = source_files()
    checks = []
    checked = {}
    def require(value, name):
        checks.append({'check': name, 'PASS': bool(value)})
    def check_record(declared, name):
        actual = record(declared['path'])
        require(same(declared, actual), name)
        checked[actual['path'].casefold()] = actual
    require(initial_sources == proof['source_map'], 'execution_source_map_exact_before')
    require(digest(initial_sources) == proof['source_SHA'], 'execution_source_digest_exact')
    for key in ('original_queue', 'driver', 'dispatcher'):
        check_record(proof[key], 'dispatch_pinned_' + key)
    for name, item in proof['infrastructure'].items():
        check_record(item, 'dispatch_pinned_infrastructure_' + name)
        infra = read(item['path'])
        for key in ('scenario', 'controller_contract'):
            check_record(infra[key], name + '_frozen_' + key)
    require(same(record(root/'DISPATCHER_USED.py'),
                 {**proof['dispatcher'], 'path': str(root/'DISPATCHER_USED.py')}),
            'dispatcher_used_copy_exact')
    queue = read(proof['original_queue']['path'])
    jobs = {(j['arm'], j['day']): j for j in queue['jobs']}
    observed = []
    for job in proof['jobs']:
        folder = Path(job['path'])
        provenance_path = folder/'JOB_SOURCE_PROVENANCE.json'
        if not provenance_path.exists():
            continue
        provenance = read(provenance_path)
        key = f"{job['configuration']}/{job['arm']}/{job['day']}"
        require(provenance['source_SHA'] == proof['source_SHA'], key + '_source_exact')
        require(provenance['scenario_SHA'] == proof['scenarios'][job['configuration']], key + '_scenario_exact')
        require(same(provenance['driver'], proof['driver']), key + '_driver_dispatch_link')
        require(same(provenance['queue'], proof['original_queue']), key + '_queue_dispatch_link')
        require(same(provenance['infrastructure'], proof['infrastructure'][job['configuration']]), key + '_infrastructure_dispatch_link')
        require(provenance['job'] == jobs[(job['arm'], job['day'])], key + '_original_queue_job_literal')
        for name, item in provenance['original_frozen_receipts'].items():
            check_record(item, key + '_original_' + name)
        if (folder/'DRIVER_USED.py').exists():
            require(same(record(folder/'DRIVER_USED.py'),
                         {**proof['driver'], 'path': str(folder/'DRIVER_USED.py')}), key + '_driver_copy_exact')
        result_path = folder/'AC_ONLY_DAY_RESULT.json'
        terminal = read(result_path) if result_path.exists() else None
        if terminal is not None and terminal.get('source_SHA'):
            require(terminal['source_SHA'] == proof['source_SHA'], key + '_terminal_source_exact')
            require(terminal['scenario_SHA'] == proof['scenarios'][job['configuration']], key + '_terminal_scenario_exact')
            require(same(terminal['infrastructure'], proof['infrastructure'][job['configuration']]), key + '_terminal_infrastructure_exact')
            for name in ('raw_AC', 'physical_audit'):
                check_record(terminal[name], key + '_terminal_' + name)
        # Captured process command pins both external reference files even before a job completes.
        process_path = root/'logs'/job['configuration']/job['arm']/(job['day']+'.PROCESS.json')
        if process_path.exists():
            command = read(process_path)['command']
            for flag in ('--ref-scenario', '--ref-time-scenario'):
                path = command[command.index(flag)+1]
                check_record(record(path), key + '_reference_current_snapshot_' + flag)
        observed.append({'job': key, 'provenance': record(provenance_path),
                         'terminal': record(result_path) if terminal is not None else None,
                         'status': terminal.get('status') if terminal else 'RUNNING'})
    # Reread every observed external file to close the before/after byte check.
    for item in list(checked.values()):
        require(same(item, record(item['path'])), 'external_before_after_' + item['path'])
    require(source_files() == initial_sources, 'execution_source_map_exact_after')
    result = {'schema': 'V42_SVR_READONLY_DISPATCH_PIN_GUARD_AUDIT_V1',
              'created_UTC': datetime.now(timezone.utc).isoformat(),
              'PASS': all(c['PASS'] for c in checks),
              'source_SHA': proof['source_SHA'], 'dispatch_receipt': record(receipt_path),
              'external_receipts': list(checked.values()), 'observed_jobs': observed,
              'checks': checks, 'physical_jobs_launched': 0, 'OpenDSS_calls': 0,
              'Native_optimizer_calls': 0, 'source_or_tests_modified': False,
              'scope': 'EXISTING_FROZEN_PLAN_ACTUAL_ONLY; NEW_E2E_NOT_RUN',
              'reference_claim': 'Reference bytes observed twice in this audit; dispatcher did not pin these in its initial proof. Worker source archive records reference bytes separately.'}
    shutil.copyfile(__file__, output/'AUDIT_SCRIPT_USED.py')
    result['audit_script'] = record(output/'AUDIT_SCRIPT_USED.py')
    (output/'READONLY_DISPATCH_PIN_GUARD_AUDIT.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({'PASS': result['PASS'], 'observed_jobs': len(observed), 'checks': len(checks), 'output': str(output)}))
    if not result['PASS']:
        print(json.dumps([c for c in checks if not c['PASS']]))
        return 1
    return 0

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--source', default='D:/v42voltage')
    p.add_argument('--root', required=True)
    p.add_argument('--output', required=True)
    raise SystemExit(main(p.parse_args()))
