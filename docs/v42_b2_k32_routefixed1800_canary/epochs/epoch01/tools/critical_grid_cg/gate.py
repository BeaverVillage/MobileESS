"""Stage-two evidence gate. Never solves, loads FULL, or alters an old result."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
OLD_LB = .42547778318693985


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pre_oracle(previous):
    cert = read(previous/'INDEPENDENT_CERTIFICATE.json')
    result = read(previous/'RESULT.json')
    ledger = read(previous.parent/'NATIVE_LEDGER.json')
    inc = cert.get('incumbent_replay') or {}
    checks = dict(
        stage1_final_certificate_PASS=cert['PASS'],
        stage1_inclusion_integrity_PASS=cert.get('FULL_projection_subset_native_Joint', False),
        certified_improvement_at_least_005=cert.get('Global_LB', OLD_LB)-OLD_LB >= .005,
        valid_new_integer_incumbent=(previous/'JOINT_INCUMBENT.npz').exists() and bool(inc)
            and inc.get('binary_violation', 1) <= 1e-8 and inc.get('bound_violation', 1) <= 1e-8
            and inc.get('row_violation', 1) <= 1e-8,
        first_call_safe_and_complete=result['Native_optimize_calls'] == 1
            and result['numerical_bound_candidate_valid'] and not result['memory_stop']
            and not result['callback_errors'] and result['optimize_error'] is None,
        complete_single_call_ledger=len(ledger['calls']) == 1 and ledger['calls'][0]['stage'] == 1
            and ledger['calls'][0]['TimeLimit'] == 180 and ledger['maximum_calls'] == 2
            and ledger['maximum_requested_seconds'] == 360,
        no_stage1_result_hash_drift=cert['file_sha256']['RESULT.json'] == sha(previous/'RESULT.json'),
    )
    return dict(PASS=all(checks.values()), phase='STAGE2_PRE_ORACLE', checks=checks,
                previous_certificate_sha256=sha(previous/'INDEPENDENT_CERTIFICATE.json'),
                stage1_Global_LB=cert.get('Global_LB'), delta_Joint16=cert.get('Global_LB', OLD_LB)-OLD_LB,
                remaining_requested_Native_seconds=180, Native_optimize_calls=0)


def complete(previous, out):
    gate = pre_oracle(previous)
    oracle = read(out/'SEPARATION.json')
    exact = read(out/'INDEPENDENT_NATIVE0.json')
    model = read(out/'NATIVE0.json')
    dims = model['dimensions']
    gate['phase'] = 'STAGE2_PRE_BUILD_ADMISSION'
    gate['checks'].update(
        new_validated_violated_original_rows=oracle['PASS'] and 1 <= oracle['selected_count'] <= 16,
        exact_cut_Native0_PASS=exact['PASS'] and exact['FULL_projection_subset_native_Joint'],
        model_size_PASS=dims['rows'] <= 160000 and dims['columns'] == 244265
            and dims['binary'] == 9322 and dims['nnz'] <= 1800000,
        fresh_resource_HOLD_PASS=read(out/'PRE_LAUNCH_RESOURCE_HOLD.json')['PASS'],
        new_cuts_exclude_previous_incumbent=all(v > 0 for v in model['previous_incumbent_cut_violations']),
    )
    gate['PASS'] = all(gate['checks'].values())
    gate['independent_native0_sha256'] = sha(out/'INDEPENDENT_NATIVE0.json')
    gate['selected_original_rows'] = oracle['selected_original_rows']
    gate['post_build_memory_and_native_readback_required_before_Optimize'] = True
    return gate


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', choices=['pre-oracle', 'complete'], required=True)
    ap.add_argument('--previous', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    result = pre_oracle(args.previous) if args.mode == 'pre-oracle' else complete(args.previous, args.out)
    target = args.out if args.mode == 'pre-oracle' else args.out/'STAGE2_GATE.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
