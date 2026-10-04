"""Read-only B1 launch audit. Never substitutes B0/mock data for B1 science."""
import argparse
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from v42_orchestrator.dag import build_dag, load_dates
from v42_orchestrator.ledger import atomic

BASE = 'c6c2f733d8196e90c0cda5f849f3e894c872697f'
B0_RUN = 'B0_202505_20261004T203131_71a9bf18'
B0_ROOT = Path('C:/v42_b0_runs/71a9bf18')
DOC = ROOT / 'docs/v42_may_b1_launch_preflight'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def record(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)


def barrier(final, state, root):
    flags = final['flags']
    if (final['run_id'] != B0_RUN or state['identity']['run_id'] != B0_RUN
            or flags['B0_DAYS_PASS'] != 31 or flags['B0_EXPECTED_DAYS'] != 31
            or flags['B0_CAMPAIGN_COMPLETE'] is not True
            or flags['B0_SCIENTIFIC_PASS'] is not True
            or final['stage_counts'] != {'PASS': 155}
            or state['identity']['mode'] != 'B0_PRODUCTION'
            or len(state['stages']) != 155):
        raise ValueError('AUTHORITATIVE_B0_BARRIER_FAILED')
    days = set()
    checked = 0
    for sid, row in state['stages'].items():
        path = (root / row['receipt_path']).resolve()
        if (row['status'] != 'PASS' or not sid.startswith('B0/')
                or not path.is_relative_to(root.resolve()) or sha(path) != row['receipt_sha']):
            raise ValueError('B0_STAGE_RECEIPT_DRIFT:' + sid)
        receipt = read(path)
        payload = receipt['payload']
        if payload['run_id'] != B0_RUN or payload['synthetic_only'] is not False:
            raise ValueError('B0_STAGE_PROVENANCE_DRIFT:' + sid)
        for entry in payload['output_files']:
            output = Path(entry['path']).resolve()
            if not output.is_relative_to(root.resolve()) or sha(output) != entry['sha256']:
                raise ValueError('B0_OUTPUT_DRIFT:' + sid)
            checked += 1
        days.add(row['day'])
    if sorted(days) != [f'2025-05-{d:02d}' for d in range(1, 32)]:
        raise ValueError('B0_DATE_AXIS_DRIFT')
    return dict(PASS=True, run_id=B0_RUN, days_PASS=31, stages_PASS=155,
                output_hashes_checked=checked, outputs_reused_as_B1=0)


def scope(arm='B1', workers=1, threads=1, mess=False, ml_off=False):
    if arm != 'B1' or workers != 1 or threads != 1 or mess or ml_off:
        raise PermissionError('B1_ONLY_ONE_WORKER_THREADS1_MESS_OFF_ML_ON')
    return dict(arm='B1', AIDC_present=True, AIDC_grid_flexibility=True,
                MESS_OFF=True, ML_OFF=False, B1_DAY_WORKERS=1, GUROBI_THREADS=1)


def source_evidence(path, predicate):
    lines = path.read_text(encoding='utf8').splitlines()
    return dict(source=record(path), lines=[dict(line=i, text=s.strip())
                for i, s in enumerate(lines, 1) if predicate(s)])


def audit():
    subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, 'HEAD'], cwd=ROOT, check=True)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    final_path = ROOT / 'docs/v42_may_b0_production_31d/B0_CAMPAIGN_FINAL.json'
    b0 = barrier(read(final_path), read(B0_ROOT / 'CAMPAIGN_STATE.json'), B0_ROOT)
    days = load_dates()
    if days != tuple(f'2025-05-{d:02d}' for d in range(1, 32)):
        raise ValueError('MAY_2025_DATE_AUTHORITY_REQUIRED')
    dag = build_dag()
    nodes = [n for n in dag['nodes'] if n['arm'] == 'B1']
    expected = ('A1', 'PLANNING_FREEZE', 'ACTUAL', 'FRESH_AC', 'VALIDATION_FREEZE')
    for day in days:
        daily = [n for n in nodes if n['day'] == day]
        if tuple(n['stage'] for n in daily) != expected:
            raise ValueError('FROZEN_B1_CAUSAL_ORDER_DRIFT')
        if daily[0]['fixed_counterpart'] != 'MESS_OFF' or daily[0]['free_decisions'] != ['AIDC']:
            raise ValueError('B1_SCIENTIFIC_SCOPE_DRIFT')
        if daily[2]['required_pass'] != [f'B1/{day}/PLANNING_FREEZE']:
            raise ValueError('UNEXPECTED_B1_ALL_DAYS_PLANNING_BARRIER')
    bundles = []
    for day in days:
        path = ROOT / 'docs/v42_may_b0_zero_margin_holdout/INPUT/BUNDLE' / ('DAY_' + day.replace('-', '')) / 'PLANNING_INPUT_BUNDLE.json'
        value = read(path)
        if value['day'] != day or value['input_gate_PASS'] is not True:
            raise ValueError('SHARED_DAY_INPUT_GATE_FAILED')
        bundles.append(dict(day=day, input=record(path),
                            shared_input_only_not_B1_native_bundle_certification=True))
    # Identify concrete physical backend definitions without importing native code.
    backends = []
    for folder in ROOT.glob('v42_*'):
        if not folder.is_dir():
            continue
        for path in folder.rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == 'reconstruct_physical':
                    concrete = any(not isinstance(s, (ast.Expr, ast.Pass))
                                   or isinstance(s, ast.Expr) and not isinstance(s.value, (ast.Constant, ast.Str))
                                   for s in node.body)
                    backends.append(dict(path=str(path.relative_to(ROOT)), line=node.lineno, concrete_body=concrete))
    historical = Path('C:/codex_mobileess_workspace/MobileESS_v41r2_780gpu_capacity_rebase')
    files = [historical / 'tools/v37/run_may_locked_final.ps1', historical / 'tools/v37/monitor_may.ps1',
             Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v39l/infrastructure.py')]
    evidence = [source_evidence(ROOT / 'v42_single_thread/a1.py', lambda s: '1499' in s or 'census[k]' in s),
                source_evidence(ROOT / 'v42_boundary/boundaries.py', lambda s: 'MAY01_FINAL_NATIVE_INPUT_BUNDLE' in s),
                source_evidence(ROOT / 'v42_temporal/native.py', lambda s: '2025-05-01' in s or 'MAY01_FINAL_NATIVE_INPUT_BUNDLE' in s),
                source_evidence(ROOT / 'v42_native/planning.py', lambda s: 'PLAN_FIELDS' in s or 'unknown_arrival_policy' in s),
                source_evidence(ROOT / 'v42_orchestrator/config.py', lambda s: 'no production adapter' in s),
                source_evidence(ROOT / 'v42_capacity/actual.py', lambda s: "'B0:'" in s),
                source_evidence(Path('C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r3/native_actual.py'),
                                lambda s: "regulator_taps" in s or 'old_apply(odd,voltage,0)' in s)]
    reasons = [
        'Existing current A1 entry asserts 1499 jobs and 2025-05-01, reads one MAY01 native bundle and compares its single-day model census.',
        'No concrete reconstruct_physical implementation was found in current v42_* source; ActualBackend contains only a Protocol declaration.',
        'A1 freeze emits selected_jobs/anchor, without a demonstrated producer for the V42 FrozenDayAheadPlan fields and frozen unknown-arrival policy.',
        'B0 Actual is a fixed source-site FCFS replay; using it for optimized B1 would discard A1 decisions.',
        'Historical V41R3 Actual initialization uses Planning regulator_taps[0]; direct reuse violates the requested no Planning tap replay contract.',
    ]
    return dict(status='NOT_LAUNCHED_SCIENTIFIC_INTEGRATION_REQUIRED', launch_ready=False,
                base_SHA=BASE, audited_HEAD=head, B0_barrier=b0, scope=scope(), days=list(days),
                scientific_order=list(expected), scheduling='one complete day pipeline at a time',
                B1_all_31_Planning_barrier=False, causal_source=record(ROOT / 'v42_campaign/plan.py'),
                PR146_DAG_source=record(ROOT / 'v42_orchestrator/dag.py'),
                frozen_plan=record(ROOT / 'docs/v42_m1_cutpass_loop_campaign/MAY_CAMPAIGN_DRY_RUN_PLAN.json'),
                B1_stage_count=len(nodes), shared_day_inputs=bundles, backend_definitions=backends,
                historical_monitor_and_scheduler=[record(p) for p in files], evidence=evidence,
                blockers=reasons, new_scientific_production_calls=0, B0_reruns=0,
                task_created=False, monitor_launched=False, campaign_PID=None, monitor_PID=None,
                B2_calls=0, B3_calls=0, M1_calls=0, M2_calls=0, Branch_and_Price_calls=0,
                required_next_work=['31 source-backed native A1 input bundles with per-day Runtime/CC4/TS/WAN/electrical authority',
                    'A1 decision -> verified FrozenDayAheadPlan serialization preserving all physical job identities',
                    'Concrete frozen-policy Actual replay and fresh autonomous DSS adapter with all four physical audits',
                    'Production stage receipts/restart hooks followed by detached task and monitor prelaunch tests'],
                notes='This is a failed launch-readiness audit, not a resource wait or an authoritative B1 production run.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DOC / 'B1_LAUNCH_PREFLIGHT.json')
    args = parser.parse_args()
    receipt = audit()
    atomic(args.output, receipt)
    print(json.dumps({k: receipt[k] for k in ('status', 'launch_ready', 'B0_barrier', 'B1_stage_count', 'blockers')}, ensure_ascii=False))
    return 0 if receipt['launch_ready'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
