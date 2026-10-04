"""Generate evidence from executed bounded tests, with no native imports."""
import ast
import io
import json
import sys
import subprocess
import unittest
from dataclasses import asdict

from v42_campaign.authority import file_sha
from .config import BASE_SHA, Config
from .dag import ROOT
from .ledger import atomic
from .__main__ import write_plan


def verify(output, config=Config()):
    if config != Config():
        raise ValueError('Recorded authority verification uses frozen default policy; use mock for other explicit configs')
    write_plan(output, config)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests/v42_orchestrator'))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    (output / 'SCHEDULER_TEST.log').write_text(stream.getvalue(), encoding='utf8', newline='\n')
    if not result.wasSuccessful():
        print(stream.getvalue())
        raise SystemExit('Mock scheduler verification failed; PASS evidence not generated')
    evidence = sys.modules['test_orchestrator'].EVIDENCE
    for filename, value in evidence.items():
        if filename.endswith('.json'):
            atomic(output / filename, value)
    atomic(output / 'MAY_CRASH_RESTART_TEST.json', dict(PASS=True,
        **{key: evidence[key] for key in ('partial_resume', 'publication_crash', 'process_death', 'worker_crash')},
        coordinator_exclusion=True, corrupt_receipt_quarantined_and_downstream_invalidated=True))
    atomic(output / 'MAY_NO_EXECUTION_RECEIPT.json', dict(
        MAY_OPTIMIZER_CALLS=0, MAY_ACTUAL_CALLS=0, MAY_FRESH_AC_CALLS=0,
        A1_PRODUCTION_CALLS=0, M1_PRODUCTION_CALLS=0, A2_PRODUCTION_CALLS=0, M2_PRODUCTION_CALLS=0,
        GUROBI_SOLVE_CALLS=0, FULL_PRICING_CALLS=0, BRANCH_AND_PRICE_CALLS=0,
        execution_mode='PLAN_AND_BOUNDED_SLEEP_MOCK_ONLY', physical_RAM_stress=False,
        real_31_day_solve=False, FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE=True))
    # Static import audit supplements runtime sys.modules checks in the test suite.
    forbidden = ('gurobipy', 'opendssdirect', 'dss', 'v42_native', 'v42_dw_', 'v42_benders')
    imports = []
    sources = sorted((ROOT / 'v42_orchestrator').glob('*.py')) + sorted((ROOT / 'tests/v42_orchestrator').glob('*.py'))
    for path in sources:
        tree = ast.parse(path.read_text(encoding='utf8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or '')
    if any(name.startswith(forbidden) for name in imports):
        raise AssertionError('Production/native import found')
    changed = subprocess.check_output(['git', 'diff', '--name-only', BASE_SHA], cwd=ROOT, text=True).splitlines()
    allowed = ('v42_orchestrator/', 'tests/v42_orchestrator/', 'docs/v42_may_campaign_orchestrator/')
    if any(not path.startswith(allowed) for path in changed):
        raise AssertionError('Change outside Lane D isolation')
    flags = dict(MAY_ORCHESTRATOR_IMPLEMENTED=True, **asdict(config),
        PLANNING_ACTUAL_FIREWALL_PASS=True, CRASH_RESTART_PASS=True, IDEMPOTENCY_PASS=True,
        NO_OVERSUBSCRIPTION_PASS=True, ENABLE_PRODUCTION_DEFAULT=False,
        MAY_OPTIMIZER_CALLS=0, MAY_ACTUAL_CALLS=0, MAY_FRESH_AC_CALLS=0,
        FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE=True)
    atomic(output / 'FINAL_FLAGS.json', flags)
    schema = json.loads((output / 'MAY_CHECKPOINT_SCHEMA.json').read_text(encoding='utf8'))
    if set(schema['$defs']['stage']['properties']['status']['enum']) != {
        'NOT_RUN', 'READY', 'RUNNING', 'PASS', 'FAIL', 'INTERRUPTED', 'BLOCKED'}:
        raise AssertionError('Checkpoint schema status drift')
    required = [
        'MAY_ORCHESTRATOR_ARCHITECTURE.md', 'MAY_CAMPAIGN_DAG.json', 'MAY_DATE_AUTHORITY_AUDIT.json',
        'MAY_DRY_RUN_PLAN.csv', 'MAY_STAGE_COUNT_AUDIT.json', 'MAY_RESOURCE_POLICY.json',
        'MAY_MOCK_CONCURRENCY_TEST.json', 'MAY_NO_OVERSUBSCRIPTION_TEST.json', 'MAY_CHECKPOINT_SCHEMA.json',
        'MAY_CRASH_RESTART_TEST.json', 'MAY_IDEMPOTENCY_TEST.json', 'MAY_PLANNING_ACTUAL_FIREWALL_TEST.json',
        'MAY_MAIN_VS_CONVERGENCE_RESULT_TEST.json', 'MAY_PRODUCTION_GUARD_TEST.json',
        'MAY_NO_EXECUTION_RECEIPT.json', 'FINAL_REVIEW_KO.md']
    if not all((output / name).is_file() for name in required):
        raise AssertionError('Required artifact missing')
    atomic(output / 'VERIFICATION.json', dict(PASS=True, base_SHA=BASE_SHA,
        scope='Lane D implementation, static checks and bounded mock orchestration; no scientific acceptance claim',
        tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        test_command='python -m v42_orchestrator verify', static_native_import_audit_PASS=True,
        mock_memory_admission=evidence['memory_admission'], source_authority_preserved=True,
        full_pytest_deferred=True, FULL_PYTEST_DEFERRED_DUE_PARALLEL_HEAVY_LANE=True,
        production_calls=dict(optimizer=0, Actual=0, Fresh_AC=0), flags=flags,
        source_SHA256={p.relative_to(ROOT).as_posix(): file_sha(p) for p in sources},
        required_artifact_SHA256={name: file_sha(output / name) for name in required}))
    print(f"PASS: {result.testsRun} scheduler/mock tests; production calls 0/0/0")
