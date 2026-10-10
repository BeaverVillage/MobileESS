"""Independent Source31 source binding and only the two approved Native-denied tests."""
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
MANIFEST = Path('D:/v42_may_restart_20261010_02/B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json')
TESTS = ['tests/test_v42_autonomous_b2_f1_state.py', 'tests/test_v42_autonomous_b2_f1_basis.py']
EXPECTED_BASIS_SHA = '87ef6292421aa4122b52356e2fdb09d9ce3d50564aec2fb41758ef2021685165'
EXPECTED_TEST_SHA = 'd8a3850bba4648345f1355c9763e3926380ea7ff2f3a469b542746300bab1398'
EXPECTED_EXECUTION_SHA = 'ab7691473aea6d1d5b883afa8bc07ab0d091448c7e3fb0644c4c82f743b3169b'

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
    return unchanged

class TestCapture:
    def __init__(self):
        self.collected = 0
        self.outcomes = {'passed': 0, 'failed': 0, 'skipped': 0}
        self.failures = []
    def pytest_collection_finish(self, session):
        self.collected = len(session.items)
    def pytest_runtest_logreport(self, report):
        if report.when == 'call':
            self.outcomes[report.outcome] += 1
        if report.failed:
            self.failures.append({'nodeid': report.nodeid, 'when': report.when, 'longrepr': str(report.longrepr)})

started = datetime.now(timezone.utc).isoformat()
receipt = {'schema': 'V42_SOURCE31_INDEPENDENT_NARROW_F1_LPWARMSTART2_NATIVE_DENIED_REVIEW',
    'PASS': False, 'started_UTC': started, 'code_root': str(REPO), 'immutable_Source30_root': str(FROZEN),
    'commitpending': True, 'Native_optimize_calls': 0, 'real_Native_model_constructions': 0,
    'modelattempts': [], 'nativeattempts': [], 'actual_full_case_performance_or_final_PASS_claimed': False}
receipt['preserved_first_audit_harness_failure'] = record(AUDIT/'SOURCE31_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json')
receipt['first_audit_harness_failure_reason'] = 'Static normalization omitted the actual_parameters dictionary-key LPWarmStart comparison; stopped before imports or tests. Audit harness only repaired.'
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
    test_start = records(TESTS)
    execution_start = {n: source_start[n]['sha256'] for n in sorted(old_execution)}
    original_mismatch = {n: source_start[n]['sha256'] for n, sha in originals.items() if source_start[n]['sha256'] != sha}
    frozen_manifest_mismatch = {n: frozen_records[n]['sha256'] for n, sha in dict(originals, **old_execution).items() if frozen_records[n]['sha256'] != sha}
    differences = [n for n in sorted(names) if source_start[n]['sha256'] != frozen_records[n]['sha256']]
    assert not original_mismatch and not frozen_manifest_mismatch
    assert differences == ['v42_autonomous_b2/f1_basis.py']
    assert source_start['v42_autonomous_b2/f1_basis.py']['sha256'] == EXPECTED_BASIS_SHA
    assert test_start[TESTS[1]]['sha256'] == EXPECTED_TEST_SHA
    assert digest(execution_start) == EXPECTED_EXECUTION_SHA
    checks = static_review()
    assert all(checks.values()), checks
    diff = subprocess.run(['git', 'diff', '--', 'v42_autonomous_b2/f1_basis.py', TESTS[1]],
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
        raise AssertionError('SOURCE31_INDEPENDENT_REAL_MODEL_CONSTRUCTOR_DENIED')
    def deny_init(*args, **kwargs):
        receipt['modelattempts'].append({'entry': 'retained_real_Model.__init__', 'args_count': len(args), 'keyword_names': sorted(kwargs)})
        raise AssertionError('SOURCE31_INDEPENDENT_RETAINED_REAL_MODEL_INIT_DENIED')
    def deny_optimize(*args, **kwargs):
        receipt['nativeattempts'].append({'entry': 'retained_real_Model.optimize', 'args_count': len(args), 'keyword_names': sorted(kwargs)})
        raise AssertionError('SOURCE31_INDEPENDENT_REAL_NATIVE_OPTIMIZE_DENIED')
    capture = TestCapture()
    wall = time.perf_counter()
    import pytest
    args = ['-q', '-p', 'no:cacheprovider', '--basetemp', str(AUDIT/'pytest_tmp')] + TESTS
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
        execution_sources=execution_start, execution_sources_end=execution_end, execution_source_count=len(execution_start), execution_SHA=digest(execution_start),
        source_start_end_identical=source_start == source_end, execution_start_end_identical=execution_start == execution_end,
        test_file_records=test_start, test_file_records_end=test_end, test_start_end_identical=test_start == test_end,
        protected_preloads_before_Model_denial=loaded, retained_real_Model_constructor_and_optimize_denied=True,
        pytest_args=args, exit_code=exit_code, cases_collected=capture.collected, test_outcomes=capture.outcomes,
        test_failures=capture.failures, test_wall_seconds=time.perf_counter()-wall,
        synthetic_test_model_and_budget_receipts_are_not_real_Native_measurements=True,
        original_F1_120_FULL_LP_300_total5400_Threads1_precision_and_independent_LB_unchanged=True,
        exact_original_complete_same_attempt_basis_only=True, fallback_Method1_PStartDStart2_or_cold_unchanged=True,
        original_state_issuer_token_manifest_source_case_packet_vector_ledger_admission_unchanged=True,
        change_scope='Only eligible exact original FULL_LP Native-entry LPWarmStart1 ->2; Method0 retained; descriptive receipts and five tests updated.',
        no_production_runtime_source30_queue_or_process_edits=True,
        candidate_diff=record(AUDIT/'CANDIDATE_TWO_FILE_DIFF.patch'), test_output=record(AUDIT/'NATIVE_DENIED_TEST_OUTPUT.log'))
    receipt['PASS'] = bool(exit_code == 0 and capture.collected == 98 and capture.outcomes == {'passed':98,'failed':0,'skipped':0}
        and not receipt['modelattempts'] and not receipt['nativeattempts'] and all(checks.values())
        and receipt['source_start_end_identical'] and receipt['execution_start_end_identical'] and receipt['test_start_end_identical'])
except BaseException as exc:
    receipt.update(error=repr(exc), traceback=traceback.format_exc())
receipt['finished_UTC'] = datetime.now(timezone.utc).isoformat()
result = write('SOURCE31_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_02.json', receipt)
print(json.dumps({'PASS':receipt['PASS'], 'receipt':result, 'cases':receipt.get('cases_collected'),
    'test_outcomes':receipt.get('test_outcomes'), 'execution_SHA':receipt.get('execution_SHA'),
    'modelattempts':receipt['modelattempts'], 'nativeattempts':receipt['nativeattempts'], 'error':receipt.get('error')}, indent=2))
raise SystemExit(0 if receipt['PASS'] else 1)
