"""Copy exact control review artifacts; seal only after actual reload evidence."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import ast
import hashlib
import json

REPO = Path(r'D:\MobileESS_v42_autonomous')
ROOT = Path(r'D:\v42_may_restart_20261010_02')
DEST = REPO / 'docs/v42_autonomous_may_20261010/MONITOR_ASSEMBLED_LB_EXCLUSIVE_HOST'
OWNER = Path(r'D:\v42_monitor_assembled_lb_review_20261010_01')
INDEPENDENT = Path(r'D:\v42_monitor_assembled_lb_independent_review_20261010_01')
HOST_INDEPENDENT = Path(r'D:\v42_monitor_exclusive_host_independent_review_20261010_01')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def copy(source, relative, records):
    source = Path(source)
    raw = source.read_bytes()
    path = DEST / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, 'PREPARED_ARTIFACT_BYTES_CHANGED:' + str(relative)
    else:
        path.write_bytes(raw)
    records[str(relative)] = dict(origin=str(source), bytes=len(raw), sha256=sha(raw))
    return raw


def static_helper(source):
    raw = source.read_bytes()
    tree = ast.parse(raw.decode('utf8'))
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            calls.append(ast.unparse(node.func))
    text = raw.decode('utf8')
    checks = dict(parse_without_execution=True, actual_lease_required='assert_lease(ROOT' in text,
                  exact_two_owned_display_identities='for expected in (prior, latest)' in text
                  and "latest['PID'] == 7340 and prior['PID'] == 102084" in text,
                  all_current_listener_set_required='assert listeners == set(hosts)' in text,
                  termination_only_exact_display_loop='for expected in (hosts[7340], hosts[102084])' in text
                  and calls.count('process.terminate') == 1,
                  replacement_command_and_hidden_cwd='subprocess.Popen(old[\'command\'], cwd=CODE' in text
                  and 'creationflags=subprocess.CREATE_NO_WINDOW' in text,
                  current_three_science_identities_preserved="assert set(workers) == {'B2/2025-05-01','B2/2025-05-02','B2/2025-05-03'}" in text
                  and "identity(saved['process']['PID']) == saved['process']" in text,
                  supervisor_identity_preserved="assert identity(sup['PID']) == sup" in text,
                  completed_native_prefix_preserved="ledger['calls'][:len(prefixes[key])] == prefixes[key]" in text,
                  post_actual_sole_listener="assert listeners == {new['PID']}" in text,
                  no_solver_or_model_call=not any(name.rsplit('.', 1)[-1] in ('optimize','Model') for name in calls))
    return dict(PASS=all(checks.values()), UTC=datetime.now(timezone.utc).isoformat(),
                source=dict(path=str(source), sha256=sha(raw), bytes=len(raw)), checks=checks,
                operation='AST_PARSE_ONLY_HELPER_NOT_EXECUTED', Native_optimize_calls=0,
                model_constructions=0, production_process_mutations=0,
                limitation='Static scope checks do not prove actual reload execution or OS continuity.')


def prepare(actual=None):
    assert not (DEST / 'SHA_INVENTORY.json').exists(), 'PACKAGE_ALREADY_SEALED'
    records = {}
    owner_names = ['MONITOR_ASSEMBLED_LB_NATIVE_DENIED_REVIEW_RECEIPT.json',
        'MONITOR_ASSEMBLED_LB_NATIVE_DENIED_REVIEW_RECEIPT_02.json',
        'MONITOR_EXCLUSIVE_HOST_NATIVE_DENIED_REVIEW_RECEIPT.json',
        'selected_native_denied.xml','selected_native_denied_02.xml','selected_native_denied_03.xml',
        'run_native_denied_review.py','run_native_denied_review_02.py','run_native_denied_review_03.py']
    for name in owner_names:
        copy(OWNER / name, Path('QUALIFICATION/OWNER') / name, records)
    for name in ['MONITOR_ASSEMBLED_LB_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json',
                 'INDEPENDENT_SELECTED_NATIVE_DENIED_97.xml','run_independent_native_denied_review.py',
                 'MONITOR_ASSEMBLED_LB_STATIC_AND_RELOAD_HELPER_READONLY_REVIEW.json','seal_static_monitor.py']:
        copy(INDEPENDENT / name, Path('QUALIFICATION/INDEPENDENT_ADAPTER') / name, records)
    for name in ['MONITOR_EXCLUSIVE_HOST_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json',
                 'INDEPENDENT_SELECTED_NATIVE_DENIED_103.xml','run_independent_review.py','prepare_runner.py']:
        copy(HOST_INDEPENDENT / name, Path('QUALIFICATION/INDEPENDENT_HOST') / name, records)
    for name in ['ACTUAL_MONITOR_8794_DUPLICATE_OWNER_READONLY_AUDIT.json','audit_actual_monitor_owners.py']:
        copy(OWNER / name, Path('DUPLICATE_OWNERSHIP') / name, records)
    names = ['v42_autonomous_monitor/current_certificates.py','v42_autonomous_monitor/monitor.py',
             'v42_autonomous_monitor/host.py','v42_b2_monitor_v16/certificates.py',
             'tests/test_v42_autonomous_monitor_assembled_lb.py','tests/test_v42_autonomous_monitor_exclusive_host.py',
             'tests/test_v42_autonomous_monitor.py','tests/test_v42_b2_monitor_v16.py']
    for name in names:
        copy(REPO / name, Path('QUALIFIED_SOURCE') / name, records)
    for name in ['reload_owned_monitor_assembled_lb.py','reload_owned_monitor_assembled_lb_02.py',
                 'reload_owned_monitor_assembled_lb_03.py','MONITOR_ASSEMBLED_LB_RELOAD_IMPORT_FAILURE_01.json',
                 'MONITOR_ASSEMBLED_LB_RELOAD_OWNERSHIP_FAILURE_02.json']:
        copy(ROOT / 'autonomous' / name, Path('RELOAD') / name, records)
    helper = ROOT / 'autonomous/reload_owned_monitor_assembled_lb_03.py'
    review = static_helper(helper)
    assert review['PASS'], review
    static_path = DEST / 'RELOAD/HELPER03_OWNER_AST_SCOPE_REVIEW.json'
    if not static_path.exists():
        write(static_path, review)
    else:
        previous = json.loads(static_path.read_text())
        assert previous['source'] == review['source'] and previous['checks'] == review['checks']
    copy(__file__, Path('PACKAGE_PRODUCER.py'), records)
    if actual:
        actual = Path(actual)
        value = json.loads(copy(actual, Path('RELOAD') / actual.name, records))
        assert value.get('PASS') is True and value.get('only_one_actual_listener') is True
        before_record = value['before']
        before_path = Path(before_record['path'])
        raw = copy(before_path, Path('RELOAD') / before_path.name, records)
        assert sha(raw) == before_record['sha256']
        before = json.loads(raw)
        for item in before['workers'].values():
            entry = item['ledger_snapshot']
            path = Path(entry['path'])
            raw = copy(path, Path('RELOAD/RAW_NATIVE_CONTINUITY') / path.name, records)
            assert sha(raw) == entry['sha256']
        for name in ['monitor_assembled_lb_stdout.log','monitor_assembled_lb_stderr.log']:
            copy(ROOT / 'autonomous' / name, Path('RELOAD') / name, records)
    write(DEST / 'COPY_PROVENANCE.json', dict(UTC=datetime.now(timezone.utc).isoformat(),
        schema='V42_MONITOR_CONTROL_EXACT_COPY_PROVENANCE', payload_files=records,
        Native_optimize_calls=0, model_constructions=0, production_process_mutations=0))
    actual_text = 'Actual production reload is pending; this package has not been sealed.'
    if actual:
        actual_text = ('Actual display replacement receipt verified with one listener, exact current science worker/'
                       'request identities, preserved completed Native prefixes and supervisor identity. '
                       'Replacement display PID: ' + str(value['monitor']['PID']) + '.')
    readme = f'''# Current LB display and exclusive observer bind

The former monitor accepted flat exact LB receipts but rejected the existing assembled wrapper. That error hid both current UB and independently certified LB. The observer adapter recognizes only the existing SHA-bound wrapper, exact current request/case/source/attempt, original domain containment, rational dual and implication proof receipts, and exact Frontier bracket/gap. The original scientific certificate reader remains byte exact.

Owner and independent adapter qualification each passed 97 selected tests; final owner and independent host qualification each passed 103 tests. Gurobi Model, retained constructor and optimize entries were denied after protected preloads; attempted model/Native calls were empty. Frozen Source35 1111 files and repo original 1007 source files match their declarations before and after. Root Source36 execution edits are outside these claims.

Windows had two exactly owned legacy observer PIDs, 102084 and 7340, listening on localhost8794. Three accepted HTTP samples belonged to PID102084 while the metadata last writer was PID7340. The host now uses allow_reuse_address=False and sets SO_EXCLUSIVEADDRUSE before bind. Real isolated socket fixtures prove duplicate refusal without metadata replacement, protected ports 8791/8793 and successful HTTP operation.

Helper01 import failure and Helper02 ownership-assumption failure are retained as FAIL records. Their saved receipts state that failure occurred before process/scientific mutation. Helper03 AST review is static evidence only. Historical earlier owner receipt/XML and single-host helper reviews remain labeled by their original version and do not qualify later source bytes.

{actual_text}

This is control/display evidence. No scientific matrix replay, final date PASS, Global Gap 3% achievement, Actual/Fresh acceptance, solver performance improvement or GUI rendering is claimed. Raw JSON/XML/log/helper bytes are copied without normalization. COPY_PROVENANCE records every external/source origin; SHA_INVENTORY, when present, seals all payload files except itself.
'''
    (DEST / 'README.md').write_text(readme, encoding='utf8')
    if actual:
        inventory = {str(path.relative_to(DEST)).replace('\\','/'):dict(
            bytes=path.stat().st_size, sha256=sha(path.read_bytes()))
            for path in sorted(DEST.rglob('*')) if path.is_file()}
        write(DEST / 'SHA_INVENTORY.json', dict(schema='V42_MONITOR_CONTROL_PACKAGE_INVENTORY',
            UTC=datetime.now(timezone.utc).isoformat(), files=inventory, file_count=len(inventory),
            inventory_excluded_from_payload=True, Native_optimize_calls=0, model_constructions=0,
            production_process_mutations=0))
    print(json.dumps(dict(package=str(DEST), exact_copies=len(records), sealed=bool(actual),
        helper03_static_PASS=review['PASS'], inventory=str(DEST / 'SHA_INVENTORY.json') if actual else None)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--actual')
    args = parser.parse_args()
    prepare(args.actual)
