"""Independent Source32 source binding and only the four approved Native-denied test modules."""
import ast
import contextlib
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

AUDIT = Path(__file__).resolve().parent
REPO = Path('D:/MobileESS_v42_autonomous')
FROZEN = Path('D:/v42run30')
FROZEN31 = Path('D:/v42run31')
MANIFEST = Path('D:/v42_may_restart_20261010_02/B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json')
TESTS = ['tests/test_v42_autonomous_b2.py', 'tests/test_v42_autonomous_b2_f1_state.py',
    'tests/test_v42_autonomous_b2_f1_basis.py', 'tests/test_v42_autonomous_b2_rmp_presolve.py']
EXPECTED_BASIS_SHA = '87ef6292421aa4122b52356e2fdb09d9ce3d50564aec2fb41758ef2021685165'
EXPECTED_TEST_SHA = 'd8a3850bba4648345f1355c9763e3926380ea7ff2f3a469b542746300bab1398'
EXPECTED_EXECUTION_SHA = '9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9'
EXPECTED_WORKER_SHA = '490776a45c8a8d16c2bc1fc105f3c09d33e146f1ed7470240e04ba36fd7e9782'
EXPECTED_BASE_TEST_SHA = 'e6f03079db1ac2395310712e94709cdb4a7d52645a348d380914fddb9aedac9b'
ROOT31 = Path('D:/v42_may_restart_20261010_02/autonomous/source30_regression_20261009T212753480380/V31_INTEGRATED_NATIVE_DENIED_REGRESSION.json')
ROOT30 = Path('D:/v42_may_restart_20261010_02/autonomous/source30_regression_20261009T204803210200/V30_INTEGRATED_NATIVE_DENIED_REGRESSION.json')
PRIOR31 = Path('D:/v42_b2_v31_independent_review_20261010_01/SOURCE31_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_02.json')
ACTUAL30 = Path('D:/v42_source30_actual_watch_20261010/SOURCE30_CLI_DUPLICATE_BUDGET_IDENTITY_NATIVE0_PROOF.json')
CACHE_TEST = 'tests/test_v42_autonomous_b2_projection_cache.py'

def record(path):
    path = Path(path)
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return {'path': str(path.resolve()), 'sha256': h.hexdigest(), 'bytes': path.stat().st_size}

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=True, allow_nan=False).encode('utf-8')).hexdigest()

def write(name, value):
    path = AUDIT / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return record(path)

def records(names, root=REPO):
    return {name: record(root/name) for name in sorted(names)}

def function(tree, name):
    return next(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)

def dumped(node):
    return ast.dump(node, include_attributes=False)

def static_review():
    root31_tests = {Path(r['path']).relative_to(REPO).as_posix(): r for r in json.loads(ROOT31.read_text(encoding='utf-8'))['test_files']}
    root30_tests = {Path(r['path']).relative_to(REPO).as_posix(): r for r in json.loads(ROOT30.read_text(encoding='utf-8'))['test_files']}
    old = ast.parse((FROZEN/'v42_autonomous_b2/f1_basis.py').read_text(encoding='utf-8'))
    new = ast.parse((REPO/'v42_autonomous_b2/f1_basis.py').read_text(encoding='utf-8'))
    unchanged = {name: dumped(function(old, name)) == dumped(function(new, name))
        for name in ('transport_basis', '_authority_now', '__init__', 'full_lp_adapter')}
    def stripped_install(tree):
        node = copy.deepcopy(function(tree, 'install'))
        node.body = [s for s in node.body if not (isinstance(s, ast.Assign) and
            any(isinstance(t, ast.Name) and t.id == 'receipt' for t in s.targets))]
        return node
    unchanged['install_except_descriptive_receipt_AST_identical'] = dumped(stripped_install(old)) == dumped(stripped_install(new))
    class RestoreApprovedEntry(ast.NodeTransformer):
        def visit_Assign(self, node):
            if any(isinstance(t, ast.Attribute) and t.attr == 'LPWarmStart' for t in node.targets) and isinstance(node.value, ast.Constant) and node.value.value == 2:
                return None
            return self.generic_visit(node)
        def visit_Compare(self, node):
            self.generic_visit(node)
            is_lp_attribute = isinstance(node.left, ast.Attribute) and node.left.attr == 'LPWarmStart'
            is_lp_dictionary_key = (isinstance(node.left, ast.Subscript) and
                isinstance(node.left.slice, ast.Constant) and node.left.slice.value == 'LPWarmStart')
            if is_lp_attribute or is_lp_dictionary_key:
                for value in node.comparators:
                    if isinstance(value, ast.Constant) and value.value == 2:
                        value.value = 1
            return node
        def visit_Constant(self, node):
            if node.value == 'V42_V31_APPROVED_FULL_LP_PRESOLVED_NATIVE_ENTRY':
                node.value = 'V42_V28_APPROVED_FULL_LP_NATIVE_ENTRY'
            return node
    normalized = RestoreApprovedEntry().visit(copy.deepcopy(function(new, '_budget_proxy')))
    unchanged['budget_proxy_AST_only_approved_LPWarmStart2_entry_prepost_and_schema_delta'] = dumped(function(old, '_budget_proxy')) == dumped(normalized)
    unchanged['f1_state_byte_identical_to_immutable_Source30'] = record(REPO/'v42_autonomous_b2/f1_state.py')['sha256'] == record(FROZEN/'v42_autonomous_b2/f1_state.py')['sha256']
    oldworker = ast.parse((FROZEN31/'v42_autonomous_b2/worker.py').read_text(encoding='utf-8'))
    newworker = ast.parse((REPO/'v42_autonomous_b2/worker.py').read_text(encoding='utf-8'))
    unchanged['worker_entire_AST_outside_main_identical_to_Source31'] = dumped(ast.Module(body=oldworker.body[:-1], type_ignores=[])) == dumped(ast.Module(body=newworker.body[:-1], type_ignores=[]))
    expectedmain = ast.parse("if __name__=='__main__':\n from v42_autonomous_b2.worker import run as canonical_run\n p=argparse.ArgumentParser();p.add_argument('request');a=p.parse_args();raise SystemExit(canonical_run(a.request))\n")
    unchanged['worker_main_exact_canonical_import_and_one_original_parser_call'] = dumped(newworker.body[-1]) == dumped(expectedmain.body[0])
    added = {'test_module_cli_dispatches_canonical_run_once_with_original_request_and_exit',
        'test_module_cli_actual_run_uses_exact_guarded_budget_and_restores_input_alias',
        'test_fresh_interpreter_cli_keeps_canonical_budget_identity_without_native_or_ledger'}
    # Sparse immutable runtime roots omit these newer test files. The committed
    # HEAD blob is independently bound to the preserved Root31 test receipt.
    oldtest_raw = subprocess.run(['git','show','HEAD:'+TESTS[0]], check=True, capture_output=True).stdout
    assert hashlib.sha256(oldtest_raw).hexdigest() == root31_tests[TESTS[0]]['sha256']
    oldtest = ast.parse(oldtest_raw.decode('utf-8'))
    newtest = ast.parse((REPO/TESTS[0]).read_text(encoding='utf-8'))
    stripped = ast.Module(body=[n for n in newtest.body if not (isinstance(n, ast.FunctionDef) and n.name in added)], type_ignores=[])
    unchanged['base_tests_AST_identical_except_exact_three_new_CLI_cases'] = dumped(oldtest) == dumped(stripped)
    unchanged['f1_basis_byte_identical_to_Source31_and_basis_test_matches_prior_Root31'] = (record(REPO/'v42_autonomous_b2/f1_basis.py')['sha256'] == record(FROZEN31/'v42_autonomous_b2/f1_basis.py')['sha256'] and record(REPO/TESTS[2])['sha256'] == root31_tests[TESTS[2]]['sha256'])
    unchanged['RMP_typeguards_and_delegate_bytes_unchanged_Source30_and_Source31'] = all(record(REPO/'v42_autonomous_b2/rmp_presolve.py')['sha256'] == record(root/'v42_autonomous_b2/rmp_presolve.py')['sha256'] for root in [FROZEN,FROZEN31])
    unchanged['cache_source_and_120_case_test_bytes_unchanged_Source30_and_Source31'] = (all(record(REPO/'v42_autonomous_b2/pricing_cache.py')['sha256'] == record(root/'v42_autonomous_b2/pricing_cache.py')['sha256'] for root in [FROZEN,FROZEN31]) and record(REPO/CACHE_TEST)['sha256'] == root31_tests[CACHE_TEST]['sha256'] == root30_tests[CACHE_TEST]['sha256'])
    return unchanged

class TestCapture:
    def __init__(self):
        self.collected = 0
        self.outcomes = {'passed': 0, 'failed': 0, 'skipped': 0}
        self.failures = []
        self.passed_nodeids = []
    def pytest_collection_finish(self, session):
        self.collected = len(session.items)
    def pytest_runtest_logreport(self, report):
        if report.when == 'call':
            self.outcomes[report.outcome] += 1
            if report.passed:
                self.passed_nodeids.append(report.nodeid)
        if report.failed:
            self.failures.append({'nodeid': report.nodeid, 'when': report.when, 'longrepr': str(report.longrepr)})

started = datetime.now(timezone.utc).isoformat()
receipt = {'schema': 'V42_SOURCE32_INDEPENDENT_CANONICAL_WORKER_CLI_NATIVE_DENIED_REVIEW',
    'PASS': False, 'started_UTC': started, 'code_root': str(REPO), 'immutable_Source30_root': str(FROZEN),
    'commitpending': True, 'Native_optimize_calls': 0, 'real_Native_model_constructions': 0,
    'modelattempts': [], 'nativeattempts': [], 'actual_full_case_performance_or_final_PASS_claimed': False}
receipt['preserved_first_audit_harness_failure'] = record(AUDIT/'SOURCE32_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json')
receipt['first_audit_harness_failure_reason'] = 'Sparse immutable Source31 omits newer test files. Stopped before protected imports/tests. Historical test comparison now binds HEAD blob and current hashes to retained Root31/Root30 test receipts.'
try:
    os.chdir(REPO)
    sys.path.insert(0, str(REPO))
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    sys.dont_write_bytecode = True
    m = json.loads(MANIFEST.read_text(encoding='utf-8'))
    originals, old_execution = m['builder_original_sources'], m['execution_sources']
    assert len(originals) == 1007 and len(old_execution) == 98 and not set(originals) & set(old_execution)
    names = set(originals) | set(old_execution)
    source_start = records(names)
    frozen_records = records(names, FROZEN)
    frozen31_records = records(names, FROZEN31)
    test_start = records(TESTS)
    execution_start = {n: source_start[n]['sha256'] for n in sorted(old_execution)}
    original_mismatch = {n: source_start[n]['sha256'] for n, sha in originals.items() if source_start[n]['sha256'] != sha}
    frozen_manifest_mismatch = {n: frozen_records[n]['sha256'] for n, sha in dict(originals, **old_execution).items() if frozen_records[n]['sha256'] != sha}
    differences = [n for n in sorted(names) if source_start[n]['sha256'] != frozen_records[n]['sha256']]
    assert not original_mismatch and not frozen_manifest_mismatch
    assert differences == ['v42_autonomous_b2/f1_basis.py', 'v42_autonomous_b2/worker.py']
    differences31 = [n for n in sorted(names) if source_start[n]['sha256'] != frozen31_records[n]['sha256']]
    assert differences31 == ['v42_autonomous_b2/worker.py']
    assert source_start['v42_autonomous_b2/f1_basis.py']['sha256'] == EXPECTED_BASIS_SHA
    assert test_start[TESTS[2]]['sha256'] == EXPECTED_TEST_SHA
    assert source_start['v42_autonomous_b2/worker.py']['sha256'] == EXPECTED_WORKER_SHA
    assert test_start[TESTS[0]]['sha256'] == EXPECTED_BASE_TEST_SHA
    assert digest(execution_start) == EXPECTED_EXECUTION_SHA
    checks = static_review()
    assert all(checks.values()), checks
    diff = subprocess.run(['git', 'diff', '--', 'v42_autonomous_b2/worker.py', TESTS[0]],
        check=True, capture_output=True, encoding='utf-8').stdout
    (AUDIT/'CANDIDATE_TWO_FILE_DIFF.patch').write_text(diff, encoding='utf-8')
    preloads = ['v42_autonomous_b2.pricing_cache', 'v42_autonomous_b2.rmp_presolve',
        'v42_autonomous_b2.worker', 'v42_autonomous_b2.f1_basis']
    loaded = []
    for module in preloads:
        importlib.import_module(module)
        loaded.append(module)
    import gurobipy as gp
    real_model = gp.Model
    retained_init, retained_optimize = real_model.__init__, real_model.optimize
    def deny_model(*args, **kwargs):
        receipt['modelattempts'].append({'entry': 'gp.Model', 'args_count': len(args), 'keyword_names': sorted(kwargs)})
        raise AssertionError('SOURCE32_INDEPENDENT_REAL_MODEL_CONSTRUCTOR_DENIED')
    def deny_init(*args, **kwargs):
        receipt['modelattempts'].append({'entry': 'retained_real_Model.__init__', 'args_count': len(args), 'keyword_names': sorted(kwargs)})
        raise AssertionError('SOURCE32_INDEPENDENT_RETAINED_REAL_MODEL_INIT_DENIED')
    def deny_optimize(*args, **kwargs):
        receipt['nativeattempts'].append({'entry': 'retained_real_Model.optimize', 'args_count': len(args), 'keyword_names': sorted(kwargs)})
        raise AssertionError('SOURCE32_INDEPENDENT_REAL_NATIVE_OPTIMIZE_DENIED')
    capture = TestCapture()
    wall = time.perf_counter()
    import pytest
    basetemp = REPO/'tmp/pytest_v32_independent_20261010_01'
    assert basetemp.resolve().is_relative_to((REPO/'tmp').resolve()) and not basetemp.exists()
    args = ['-q', '-p', 'no:cacheprovider', '--basetemp', str(basetemp)] + TESTS
    with (AUDIT/'NATIVE_DENIED_TEST_OUTPUT.log').open('w', encoding='utf-8') as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            with patch.object(real_model, '__init__', deny_init), patch.object(real_model, 'optimize', deny_optimize), patch.object(gp, 'Model', deny_model):
                exit_code = int(pytest.main(args, plugins=[capture]))
    source_end = records(names)
    test_end = records(TESTS)
    execution_end = {n: source_end[n]['sha256'] for n in sorted(old_execution)}
    receipt.update(manifest=record(MANIFEST), candidate_HEAD=subprocess.run(['git','rev-parse','HEAD'], check=True, capture_output=True, text=True).stdout.strip(),
        source_file_records=source_start, source_file_records_end=source_end, source_file_count=len(source_start),
        scientific_original_sources=originals, scientific_original_count=len(originals), scientific_original_SHA_matches=True,
        immutable_Source30_file_records=frozen_records, immutable_Source30_manifest_SHA_matches=True,
        immutable_Source30_differences=differences, static_guard_checks=checks,
        immutable_Source31_file_records=frozen31_records, immutable_Source31_differences=differences31,
        execution_sources=execution_start, execution_sources_end=execution_end, execution_source_count=len(execution_start), execution_SHA=digest(execution_start),
        source_start_end_identical=source_start == source_end, execution_start_end_identical=execution_start == execution_end,
        test_file_records=test_start, test_file_records_end=test_end, test_start_end_identical=test_start == test_end,
        protected_preloads_before_Model_denial=loaded, retained_real_Model_constructor_and_optimize_denied=True,
        pytest_args=args, exit_code=exit_code, cases_collected=capture.collected, test_outcomes=capture.outcomes,
        test_failures=capture.failures, passed_test_nodeids=capture.passed_nodeids, test_wall_seconds=time.perf_counter()-wall,
        synthetic_test_model_and_budget_receipts_are_not_real_Native_measurements=True,
        original_F1_120_FULL_LP_300_total5400_Threads1_precision_and_independent_LB_unchanged=True,
        exact_original_complete_same_attempt_basis_only=True, fallback_Method1_PStartDStart2_or_cold_unchanged=True,
        original_state_issuer_token_manifest_source_case_packet_vector_ledger_admission_unchanged=True,
        change_scope='Beyond approved Source31, only __main__ CLI dispatch imports/calls canonical worker.run; three Native-denied CLI regression tests added. All other worker AST unchanged.',
        no_production_runtime_source30_queue_or_process_edits=True,
        pytest_basetemp_within_authorized_repo_tmp=str(basetemp),
        carried_prior_Source31_independent_98=record(PRIOR31), carried_Root_Source31_305=record(ROOT31),
        carried_Root_Source30_300=record(ROOT30),
        carried_projection_cache_120_source_and_test_records=records(['v42_autonomous_b2/pricing_cache.py', CACHE_TEST]),
        projection_cache_120_not_rerun=True, carried_305_is_prior_Source31_not_new_Source32_run=True,
        actual_Source30_duplicate_CLI_budget_class_diagnostic=record(ACTUAL30),
        strict_RMP_budget_model_delegate_guards_not_weakened=True,
        fresh_interpreter_CLI_case_in_selected_run=True,
        fresh_interpreter_case_asserts_canonical_budget_exact_delegate_identity_no_model_native_attempts_and_no_request_file=True,
        candidate_diff=record(AUDIT/'CANDIDATE_TWO_FILE_DIFF.patch'), test_output=record(AUDIT/'NATIVE_DENIED_TEST_OUTPUT.log'))
    receipt['PASS'] = bool(exit_code == 0 and capture.collected == 188 and capture.outcomes == {'passed':188,'failed':0,'skipped':0}
        and not receipt['modelattempts'] and not receipt['nativeattempts'] and all(checks.values())
        and receipt['source_start_end_identical'] and receipt['execution_start_end_identical'] and receipt['test_start_end_identical'])
except BaseException as exc:
    receipt.update(error=repr(exc), traceback=traceback.format_exc())
receipt['finished_UTC'] = datetime.now(timezone.utc).isoformat()
result = write('SOURCE32_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_02.json', receipt)
print(json.dumps({'PASS':receipt['PASS'], 'receipt':result, 'cases':receipt.get('cases_collected'),
    'test_outcomes':receipt.get('test_outcomes'), 'execution_SHA':receipt.get('execution_SHA'),
    'modelattempts':receipt['modelattempts'], 'nativeattempts':receipt['nativeattempts'], 'error':receipt.get('error')}, indent=2))
raise SystemExit(0 if receipt['PASS'] else 1)
