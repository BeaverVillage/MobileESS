"""Bounded observer qualification. Never construct or optimize a model."""
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

REPO = Path(r'D:\MobileESS_v42_autonomous')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def records(paths):
    return {str(path): sha(path) for path in paths}


def main():
    import pytest
    import gurobipy as gp
    from v42_autonomous_monitor import monitor
    from v42_autonomous_monitor.host import Snapshot
    from v42_b3_joint import source_coordinator
    root = Path(r'D:\v42_may_restart_20261010_02')
    freeze = read(root / 'autonomous/V35_SPARSE_IMMUTABLE_FREEZE.json')
    manifest = read(root / 'B2_V35_ZERO_START_DEPLOYMENT_MANIFEST.json')
    frozen_paths = [Path(item['path']) for item in freeze['source_files']]
    original_paths = [REPO / name for name in manifest['builder_original_sources']]
    selected = ['tests/test_v42_autonomous_monitor_assembled_lb.py',
                'tests/test_v42_autonomous_monitor.py', 'tests/test_v42_b2_monitor_v16.py']
    owned = [REPO / name for name in ['v42_autonomous_monitor/current_certificates.py',
             'v42_autonomous_monitor/monitor.py', *selected]]
    original_reader = REPO / 'v42_b2_monitor_v16/certificates.py'
    before = dict(frozen=records(frozen_paths), original_repo=records(original_paths),
                  owned=records(owned), original_reader=sha(original_reader))
    attempted = []

    def deny_model(*args, **kwargs):
        attempted.append('gurobipy.Model')
        raise AssertionError('MONITOR_QUALIFICATION_MODEL_DENIED')

    def deny_init(*args, **kwargs):
        attempted.append('retained_Model.__init__')
        raise AssertionError('MONITOR_QUALIFICATION_RETAINED_MODEL_DENIED')

    def deny_native(*args, **kwargs):
        attempted.append('retained_Model.optimize')
        raise AssertionError('MONITOR_QUALIFICATION_NATIVE_DENIED')

    original_model = gp.Model
    xml_path = OUT / 'selected_native_denied.xml'
    actual = []
    with patch.object(original_model, '__init__', deny_init), patch.object(original_model, 'optimize', deny_native), patch.object(gp, 'Model', deny_model):
        exit_code = pytest.main([*selected, '-q', '--junitxml=' + str(xml_path),
            '--basetemp=' + str(REPO / 'tmp/monitor_assembled_lb_native_denied')])
        cp = read(root / 'SUPERVISOR_STATE.json')
        for day in ('2025-05-01', '2025-05-02', '2025-05-03'):
            key = 'B2/' + day
            worker = cp['workers'].get(key)
            if not worker:
                continue
            request_path = Path(worker['request'])
            request = read(request_path)
            value = monitor.b2_bound(request['output'], day, request,
                source=worker.get('source_SHA'), attempt=worker.get('attempt_id'))
            compact = {name: value.get(name) for name in ('UB', 'LB', 'gap', 'status', 'error')}
            compact.update(day=day, request_path=str(request_path), request_SHA=sha(request_path),
                           attempt=request['attempt_id'], source=request['implementation_SHA'])
            if value.get('evidence'):
                compact['selected_receipts'] = value['evidence']
            actual.append(compact)
    after = dict(frozen=records(frozen_paths), original_repo=records(original_paths),
                 owned=records(owned), original_reader=sha(original_reader))
    suites = ET.parse(xml_path).getroot()
    stats = {name: sum(int(s.get(name, '0')) for s in suites.iter('testsuite'))
             for name in ('tests', 'failures', 'errors', 'skipped')}
    expected_frozen = {item['path']: item['sha256'] for item in freeze['source_files']}
    expected_original = {str(REPO / name): value for name, value in manifest['builder_original_sources'].items()}
    checks = dict(selected_tests_PASS=exit_code == 0 and stats['tests'] > 0
                  and stats['failures'] == stats['errors'] == 0,
                  native_model_attempts_zero=attempted == [],
                  all_source_bytes_unchanged=before == after,
                  frozen_1111_match_freeze=before['frozen'] == expected_frozen,
                  original_repo_1007_match_manifest=before['original_repo'] == expected_original,
                  own_adapter_outside_scientific_maps=all(
                      str(path.relative_to(REPO)).replace('\\', '/') not in
                      {**manifest['builder_original_sources'], **manifest['execution_sources']}
                      for path in owned[:2]),
                  current_May01_assembled_LB_display_verified=any(
                      item['day'] == '2025-05-01' and item['status'] == 'CERTIFIED'
                      and item.get('selected_receipts', {}).get('LB', {}).get('schema')
                      == 'CURRENT_ASSEMBLED_ORIGINAL_EXACT_LB' for item in actual))
    receipt = dict(PASS=all(checks.values()), UTC=datetime.now(timezone.utc).isoformat(),
                   checks=checks, selected_test_statistics=stats, source_before=before, source_after=after,
                   test_XML=dict(path=str(xml_path), sha256=sha(xml_path)),
                   producer=dict(path=str(Path(__file__).resolve()), sha256=sha(__file__)),
                   actual_current_observations=actual, model_native_attempts=attempted,
                   model_constructions=0, Native_optimize_calls=0,
                   limitations=['Display checks existing producer receipts; does not replay scientific matrices.',
                                'No monitor reload, worker lifecycle control, solver or fresh date PASS claim.'])
    path = OUT / 'MONITOR_ASSEMBLED_LB_NATIVE_DENIED_REVIEW_RECEIPT.json'
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps(dict(PASS=receipt['PASS'], checks=checks, statistics=stats,
                         receipt=str(path), sha256=sha(path), actual=[{
                             k:item[k] for k in ('day','UB','LB','gap','status','error')}
                             for item in actual])))
    return 0 if receipt['PASS'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
