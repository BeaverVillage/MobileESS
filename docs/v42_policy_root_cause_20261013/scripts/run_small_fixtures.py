"""Controlled B-namespace experiments against the immutable V5 Python snapshot."""
import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
import sys

ROOT = Path('D:/v42_policy_root_cause_20261013')
OUT = ROOT / 'audit'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(ROOT / 'tests'))
spec = importlib.util.spec_from_file_location('frozen_named_fixture', ROOT / 'tests/test_v42_integration_sensitivity_policy.py')
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)
from v42_integration.policy import ReservationLedger
from v42_integration.sensitivity_policy import FrozenSensitivityPolicy


def execute(name, values, metadata, receipt, *, migration=False, capacities=None, wan=None, occupied=False):
    policy = f.compile_fixture(values)
    path = OUT / 'fixtures' / (name + '.json')
    policy.save(path)
    reloaded = FrozenSensitivityPolicy.load(path, bindings=policy.bindings)
    ledger = ReservationLedger(capacities or {'A': 8, 'B': 8}, wan)
    if occupied:
        for site in ('A', 'B'):
            assert ledger.reserve('frozen-background-'+site, [dict(resource='gpu:'+site, begin=0, end=86400, quantity=1)])[0]
    call = reloaded.select_migration if migration else reloaded.select
    selected = call(metadata, receipt, 0, ledger)
    return dict(name=name, named_synthetic_fixture=True, real_May01=False,
                policy_sha=policy.sha, policy_file_sha=hashlib.sha256(path.read_bytes()).hexdigest(),
                reload_identical_policy_sha=policy.sha == reloaded.sha,
                compiler_status=policy.document['status'],
                compiler_metrics=policy.document['metrics'],
                candidate_comparison=policy.document['templates'][0]['scenario_comparisons'],
                selected=selected, reservation_count=len(ledger.reservations))


results = []
values = f.fixture(profile='placement')
values[5].update(compatible_sites=['A'], can_prestart_place=False)
meta = f.metadata()
meta.update(compatible_sites=['A'], can_prestart_place=False)
results.append(execute('DELAY_15', values, meta, f.receipt()))
assert results[-1]['selected']['policy_action'] == 'DELAY_15'

results.append(execute('PREPLACE', f.fixture(profile='placement'), f.metadata(), f.receipt()))
assert results[-1]['selected']['action'] == 'PREPLACE'

values = f.fixture(profile='placement')
values[5].update(compatible_sites=['A'], can_prestart_place=False)
meta = f.metadata()
meta.update(compatible_sites=['A'], can_prestart_place=False)
results.append(execute('START_NOW_ZERO_DELAY_BUDGET', values, meta, f.receipt(0)))
assert results[-1]['selected']['policy_action'] == 'START_NOW'

values = f.fixture(profile='placement', running=True)
capability = dict(source_sha='NAMED_SYNTHETIC_PHYSICAL_CONTRACT', checkpoint_authorized=True,
                  allowed_destinations=['B'], gpu_type_confirmed=True, rack_gang_confirmed=True,
                  data_residency_confirmed=True, wan_path='AB', bandwidth_bytes_per_second=100.,
                  payload_bytes=90000., restart_seconds=900., source_wait_seconds=0.,
                  source_hold_until='transfer_start', destination_hold_from='transfer_end')
values[5].update(accumulated_compute_seconds=1800., migration_capability=capability, wan_capacities={'AB': 100.})
meta = f.metadata()
meta.update(state='RUNNING', current_site='A', t50_seconds=2700., accumulated_compute_seconds=1800.,
            migration_count=0, migration_capability=capability)
results.append(execute('CHECKPOINT_MIGRATE', values, meta, f.receipt(), migration=True, wan={'AB': 100.}))
assert results[-1]['selected']['action'] == 'CHECKPOINT_MIGRATE'
assert results[-1]['selected']['migration']['interruption_seconds'] == 1800

results.append(execute('STAY_SHARED_INTERRUPTION_BUDGET_REJECTION', values, meta, f.receipt(900),
                       migration=True, wan={'AB': 100.}))
assert results[-1]['selected']['action'] == 'STAY'
assert results[-1]['reservation_count'] == 0

results.append(execute('QUEUE_CAPACITY_REJECTION', f.fixture(profile='placement'), f.metadata(),
                       f.receipt(), capacities={'A': 1, 'B': 1}, occupied=True))
assert results[-1]['selected']['action'] == 'QUEUE'
assert results[-1]['reservation_count'] == 2

rebound = f.compile_fixture(f.fixture(destination_slope=0.))
scores = rebound.document['templates'][0]['scenario_comparisons']
start = next(r for r in scores if r['action'] == 'START_NOW')
delay = next(r for r in scores if r['action'] == 'DELAY_15')
assert abs(start['scenario_scores']['NOMINAL_Q50'] - .9) < 1e-9
assert abs(delay['scenario_scores']['NOMINAL_Q50'] - 1.15) < 1e-9
assert not delay['hard_feasible']

required = ['v42_integration/sensitivity_policy.py', 'v42_integration/policy.py',
            'tests/test_v42_integration_sensitivity_policy.py']
body = dict(schema='V42_CONTROL_POLICY_SMALL_FIXTURE_RESULTS_V1', status='PASS',
            scope='CONTROLLED_NAMED_SYNTHETIC_FIXTURE_ONLY_NOT_REAL_MAY01_ACTION_EVIDENCE',
            immutable_snapshot_source_sha=json.loads((OUT/'SOURCE_SNAPSHOT.json').read_text())['source_sha'],
            source_receipts=[dict(path=str(ROOT/name), sha256=hashlib.sha256((ROOT/name).read_bytes()).hexdigest())
                             for name in required],
            runner_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            Native_Optimize_calls=0, global_optimizer_calls=0, Fresh_AC_calls=0,
            real_May01_Actual_runs=0, source_edits=0, fixture_cases=results,
            rebound_counterexample=dict(START_NOW_peak=.9, DELAY_15_peak=1.15,
                                        DELAY_15_hard_feasible=False, remaining_slots=96),
            real_May01_policy_improvement='NOT_ESTABLISHED')
(OUT/'CONTROL_POLICY_SMALL_FIXTURE_RESULTS.json').write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status': body['status'], 'cases': [(r['name'],r['selected']['action']) for r in results]}))
