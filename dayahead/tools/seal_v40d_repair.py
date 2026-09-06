"""Adopt verified repaired B2 cases and seal the cap-10 campaign revision."""
from pathlib import Path
from datetime import datetime, timezone
import json
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from dayahead.v40b.common import ROOT, read, write, digest, sha
from dayahead.v40b.reuse import validate_case_files, write_matrix
from dayahead.v40b.recovery import certified_day, completed_case
from dayahead.v40d.policy import load_policy, POLICY_PATH


def main():
    repair = ROOT / 'repairs/08_ac_restoration'
    repair.mkdir(parents=True, exist_ok=False)
    policy = load_policy(REPO)
    days = ('2025-05-21', '2025-05-28', '2025-05-30')
    method = read(ROOT / 'V40B_V40A_METHOD_FREEZE.json')
    execution = read(ROOT / 'V40B_EXECUTION_FREEZE.json')
    old_execution = execution['execution_SHA']
    progress = read(ROOT / 'V40A_MAY_PROGRESS.json')
    if progress['status'] != 'PAUSED_BY_USER':
        raise RuntimeError('SEAL_REQUIRES_PAUSED_CAMPAIGN')
    certs = {}
    for day in days:
        cert = read(REPO / 'dayahead/artifacts/v40d_ac_restoration/cap10' / day / 'PRODUCTION_CERTIFICATE.json')
        if cert['AC_restoration_policy_sha256'] != policy['policy_sha256'] or not cert['old_failed_result_unchanged']:
            raise RuntimeError('REPAIRED_CERTIFICATE_INVALID')
        validate_case_files(day, 'B2', Path(cert['checkpoint']), Path(cert['case_root']))
        certs[day] = cert
    suite = ET.parse(REPO / 'dayahead/artifacts/v40d_ac_restoration/V40D_PYTEST.xml').getroot().find('testsuite')
    if suite is None or int(suite.attrib['failures']) or int(suite.attrib['errors']):
        raise RuntimeError('PYTEST_NOT_PASSED')
    before_paths = list(ROOT.glob('*.json'))
    before_paths += [ROOT / 'V40B_MAY_EXECUTION_MATRIX.csv']
    for day in days:
        before_paths += [ROOT / 'days' / day / 'FAILURE.json', ROOT / 'days' / day / 'CASE_COMPLETION.json', ROOT / 'status' / f'{day}.json']
    preserved = {}
    with zipfile.ZipFile(repair / 'PRE_ADOPTION_CONTROL_STATE.zip', 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in before_paths:
            if path.is_file():
                rel = path.relative_to(REPO).as_posix()
                preserved[rel] = sha(path)
                archive.write(path, rel)
    write(repair / 'PRE_ADOPTION_MANIFEST.json', {'files': preserved})
    completed_preservation = {}
    for day in progress['completed_days']:
        if certified_day(day, method['method_SHA']) is None:
            raise RuntimeError('COMPLETED_DAY_INVALID:' + day)
        completed_case(day, 'B3', method['method_SHA'])
        path = ROOT / 'days' / day / 'DAY_CERTIFICATE.json'
        completed_preservation[day] = sha(path)
    write(repair / 'COMPLETED_DAY_COMPATIBILITY.json', {
        'status': 'PASS', 'policy_sha256': policy['policy_sha256'], 'days': completed_preservation,
        'rule': 'Increasing only the stop bound preserves every previous early PASS and its output bytes.',
        'new_B3_reused_as_old_method': False,
    })
    for day, cert in certs.items():
        dest = ROOT / 'days' / day / 'B2/CASE_CERTIFICATE.json'
        if dest.exists():
            raise RuntimeError('UNEXPECTED_EXISTING_B2_CERTIFICATE:' + day)
        write(dest, cert)
        completion_path = ROOT / 'days' / day / 'CASE_COMPLETION.json'
        completion = read(completion_path)
        completion['cases']['B2'] = {'status': 'COMPLETE_NEW_V40A', 'certificate': str(dest), 'certificate_SHA': sha(dest)}
        write(completion_path, completion)
        failure = ROOT / 'days' / day / 'FAILURE.json'
        archived = repair / 'failed_attempts' / day / 'FAILURE.json'
        archived.parent.mkdir(parents=True)
        shutil.copyfile(failure, archived)
        if sha(failure) != sha(archived):
            raise RuntimeError('FAILURE_ARCHIVE_MISMATCH')
        failure.unlink()
        status = read(ROOT / 'status' / f'{day}.json')
        status.update(status='PAUSED_BY_USER', case='B3', current_stage='B2_REPAIRED_WAITING_B3', completed_units=3,
                      error=None, solver_detail={}, repaired_B2_rounds=cert['restoration_rounds'],
                      AC_restoration_policy_sha256=policy['policy_sha256'])
        write(ROOT / 'status' / f'{day}.json', status)
    rows = read(ROOT / 'V40B_MAY_EXECUTION_MATRIX.json')['rows']
    for row in rows:
        if row['day'] in days:
            cases = read(ROOT / 'days' / row['day'] / 'CASE_COMPLETION.json')['cases']
            if row['case'] in cases:
                row.update(cases[row['case']])
            elif row['case'] == 'B3':
                row['status'] = 'RUN_REQUIRED'
    write_matrix(rows)
    write(ROOT / 'V40D_RESOLVED_FAILURES.json', {'status': 'PASS', 'days': list(days),
          'case': 'B2', 'policy_sha256': policy['policy_sha256'], 'B3_still_required': True,
          'certificates': {day: str(ROOT / 'days' / day / 'B2/CASE_CERTIFICATE.json') for day in days}})
    allowed_changes = {'dayahead/tools/run_v40b_campaign.py', 'dayahead/v40b/b3.py',
                       'dayahead/tools/monitor_v40b_may_live.ps1', 'dayahead/tools/v40c_supervise_once.py'}
    changed = [rel for rel, old in execution['source_files'].items() if sha(REPO / rel) != old]
    if set(changed) - allowed_changes:
        raise RuntimeError('UNEXPECTED_SOURCE_CHANGE:' + str(set(changed) - allowed_changes))
    source_files = {rel: sha(REPO / rel) for rel in execution['source_files']}
    extra_sources = list((REPO / 'dayahead/v40d').glob('*.py')) + [
        REPO / 'dayahead/tools/run_v40d_restoration_trial.py', REPO / 'dayahead/tools/adopt_v40d_restoration_trial.py',
        REPO / 'dayahead/tools/seal_v40d_repair.py', REPO / 'dayahead/tools/v40c_supervise_once.py',
    ]
    source_files.update({p.relative_to(REPO).as_posix(): sha(p) for p in extra_sources})
    tests = {rel: sha(REPO / rel) for rel in execution['test_source_files']}
    tests.update({p.relative_to(REPO).as_posix(): sha(p) for p in (REPO / 'tests/dayahead').glob('test_v40d_*') if p.is_file()})
    inputs = dict(execution['input_files'])
    inputs[POLICY_PATH.as_posix()] = sha(REPO / POLICY_PATH)
    identity = dict(execution['identity'])
    identity.update(source_manifest_SHA=digest(source_files), tests_manifest_SHA=digest(tests),
                    input_manifest_SHA=digest(inputs), supersedes_execution_SHA=old_execution,
                    repair_id='V40D_AC_RESTORATION_08', AC_restoration_policy_SHA=policy['policy_sha256'],
                    effective_scientific_SHA=digest({'planning_method_SHA': method['method_SHA'], 'AC_restoration_policy_SHA': policy['policy_sha256']}))
    execution.update(identity=identity, execution_SHA=digest(identity), source_files=source_files,
                     test_source_files=tests, input_files=inputs, supersedes_execution_SHA=old_execution,
                     sealed_at_utc=datetime.now(timezone.utc).isoformat(),
                     May_result_based_tuning_allowed=True, authorized_revision_controls=['max_restoration_rounds'],
                     amendment='User-authorized V40D: post-selection AC restoration limit 5 to 10 for B2/B3. Planning method, margins, physical limits and route decisions unchanged. May-failure-informed revision explicitly recorded.')
    write(ROOT / 'V40B_EXECUTION_FREEZE.json', execution)
    tests_report = read(ROOT / 'V40B_TEST_REPORT.json')
    tests_report.update(execution_SHA=execution['execution_SHA'])
    tests_report['V40D_REPAIR_08'] = {'status': 'PASS', 'tests': int(suite.attrib['tests']),
                'xml_SHA': sha(REPO / 'dayahead/artifacts/v40d_ac_restoration/V40D_PYTEST.xml'),
                'real_B2_Fresh_revalidations': {day: cert['restoration_rounds'] for day, cert in certs.items()},
                'PowerShell_monitor_checks': 'Existing live-detail and new paused-display tests PASS'}
    write(ROOT / 'V40B_TEST_REPORT.json', tests_report)
    progress.update(failed_days=[d for d in progress['failed_days'] if d not in days], repaired_days=list(days),
                    paused_days=sorted(set(progress['preserved_running_days']) | set(days)),
                    execution_SHA=execution['execution_SHA'], AC_restoration_policy_SHA=policy['policy_sha256'],
                    effective_scientific_SHA=identity['effective_scientific_SHA'],
                    last_update=datetime.now(timezone.utc).isoformat(), repair_directory=str(repair))
    write(ROOT / 'V40A_MAY_PROGRESS.json', progress)
    from dayahead.v40b.supervision import verify_freeze
    verify_freeze()
    from dayahead.v40a.authority import source_authority
    inherited = source_authority(REPO, REPO / 'dayahead/artifacts/v40a_bounded_iterative_aidc_mess_coopt')
    audit = {'status': 'PASS', 'execution_SHA': execution['execution_SHA'], 'method_SHA': method['method_SHA'],
             'planning_method_unchanged': True, 'scientific_restoration_revision': True,
             'AC_restoration_policy_SHA': policy['policy_sha256'], 'effective_scientific_SHA': identity['effective_scientific_SHA'],
             'changed_existing_sources': changed, 'preserved_completed_days': len(completed_preservation),
             'repaired_B2_days': list(days), 'remaining_days': progress['paused_days'],
             'max_rounds_before': 5, 'max_rounds_after': 10, 'physical_limits_or_margins_changed': False,
             'inherited_source_authority': inherited, 'tests': tests_report['V40D_REPAIR_08']}
    write(repair / 'CHANGE_IMPACT_AUDIT.json', audit)
    print(json.dumps({key: audit[key] for key in ['status', 'execution_SHA', 'preserved_completed_days', 'repaired_B2_days', 'remaining_days']}, indent=2))


if __name__ == '__main__':
    main()
