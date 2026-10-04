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
    production = ROOT / 'docs/v42_may_b1_production_31d'
    binding = read(production/'B1_INPUT_BINDING_AUDIT.json')
    if (not binding['PASS'] or [r['day'] for r in binding['days']] != list(days)
        or any(r['native_raw'] != r['known_physical'] or r['TX_current_rows'] != 120
               or r['coefficients'] != 96 or r['optimization_calls'] != 0 for r in binding['days'])):
        raise ValueError('FULL_CURRENT_NATIVE_INPUT_BINDING_REQUIRED')
    lineage = read(production/'HISTORICAL_LINEAGE_AUDIT.json')
    diagnostic = read(production/'NATIVE_PORT_DIAGNOSTIC.json')
    model = read(production/'NATIVE_MODEL_BINDING_SMOKE.json')
    detached = read(production/'DETACHMENT_SELF_TEST.json')
    tests = read(production/'VALIDATION.json')
    if (not lineage['PASS'] or lineage['historical_decisions_reused'] != 0
        or not diagnostic['adapter_diagnostic_PASS'] or diagnostic['production_days_PASS'] != 0
        or not model['PASS'] or model['NormalAmps_rows'] != 11520 or model['native_optimize_calls'] != 0
        or not detached['PASS'] or not tests['PASS']):
        raise ValueError('PORT_PREFLIGHT_REQUIRED')
    return dict(status='READY_FOR_NEW_DETACHED_B1_PRODUCTION', launch_ready=True,
                base_SHA=BASE, audited_HEAD=head, B0_barrier=b0, scope=scope(), days=list(days),
                scientific_order=list(expected), scheduling='one complete day pipeline at a time',
                B1_all_31_Planning_barrier=False, B1_stage_count=len(nodes), shared_day_inputs=bundles,
                blockers=[], implementation_lineage='PR24 -> PR25 V39E/V39L -> PR26 V39J/V39K; current V42 overrides',
                implementation=[record(ROOT/'v42_b1_production'/n) for n in ('inputs.py','native.py','replay.py','worker.py','coordinator.py','detach.py')],
                current_input_audit=record(production/'B1_INPUT_BINDING_AUDIT.json'),
                validation=[record(production/n) for n in ('HISTORICAL_LINEAGE_AUDIT.json','NATIVE_PORT_DIAGNOSTIC.json','NATIVE_MODEL_BINDING_SMOKE.json','DETACHMENT_SELF_TEST.json','VALIDATION.json')],
                old_decisions_reused=0, B0_reruns=0, B2_calls=0, B3_calls=0, M1_calls=0, M2_calls=0,
                notes='Readiness only; new per-day A1/freeze/Actual/Fresh/validation science runs in the dedicated detached campaign.')


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
