"""Fail-closed, Native=0 qualification of one specific Pricing failure.

Result/Native ledger bytes remain original. This audit authorizes date-local
dispatch only; it cannot authorize retries, a stronger scientific result,
integer feasibility, freeze, or Actual execution.
"""
from pathlib import Path
from fractions import Fraction
import sys
import numpy as np
import scipy.sparse as sp
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v42_pr134_b1.common import read, record, digest, now
from v42_common_campaign.authority import source_files
from v42_svr11.authority import verify
from v42_a_stage_phase1.oracle import validate_coverage
from v42_a_stage_phase1.runner import load_cache, block_folder
from v42_a_stage_phase1.producer import price_snapshot
from v42_a_stage_phase1.core import primal_replay, verify_sign_convention
from v42_a_stage_practical.policy import POLICY

SCIENCE = '146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8'
ERROR = "ValueError('P1_UNRESOLVED_INTERVAL_WITHOUT_NEGATIVE_SUPPORT')"
DISPOSITION = 'DATE_LOCAL_PRICING_CERTIFICATION_INCOMPLETE'


def checked(ref):
    assert record(ref['path']) == ref, ref['path']
    return Path(ref['path'])


def audit(result_path):
    result_path = Path(result_path); original = record(result_path); result = read(result_path)
    sci = result['scientific']
    assert sci['classification'] == 'IMPLEMENTATION_FAILURE' and sci['error'] == ERROR
    assert result['status'] == 'FAIL' and result['PASS'] is False and sci['accepted'] is False
    assert not result.get('source_global_integrity_block') and not result['Native_Runtime_uncertain']
    assert result['source_SHA'] == SCIENCE == digest(source_files())
    assert not result['FULL_feasible_certified'] and not result['global_gap_certified']
    assert result['AC_status'] == 'NOT_EXECUTED' and sci['P2_calls'] == 0
    assert sci['MESS_optimization_calls'] == 0 and sci['all_MESS_PQ_zero'] is True
    assert sci['Native_budget_reset'] == 0 and not sci['scientific_infeasibility_proven']
    request = read(checked(result['request'])); manifest = verify(request['manifest'])
    assert manifest['execution_SHA'] == SCIENCE and manifest['Threads'] == 1
    assert manifest['policy_order'] == ['B1'] and manifest['worker_counts'] == {'B1': 1}
    assert request['arm'] == result['arm'] == 'B1' and request['day'] == result['day']
    assert request['source_SHA'] == SCIENCE and request['Threads'] == 1
    from v42_pr134_b1.common import sha
    assert sha(request['manifest']) == request['manifest_SHA']
    for ref in manifest['input_receipts'][request['day']]: checked(ref)
    output = Path(request['output']); prepared = read(output/'A_PREPARE_RECEIPT.json')
    assert prepared['PASS'] and prepared['verification']['PASS'] and prepared['Native_calls'] == 0
    checked(prepared['state'])
    ledger = read(result_path.parent/'NATIVE_RUNTIME_LEDGER.json')
    checked(result['native_ledgers'][0]['receipt'])
    assert ledger['inflight'] is None and ledger['P2_calls'] == 0
    calls = ledger['calls']
    assert len(calls) == sci['native_calls'] and len(calls) > 1
    assert all(c['entered_native'] and c['status'] == 'FINISHED' and c['error'] is None
               and c['Native_Runtime'] is not None and not c['runtime_unavailable'] for c in calls)
    measured = sum(c['Native_Runtime'] for c in calls)
    assert abs(measured-result['Native_Runtime']) < 1e-9 and measured <= 5400
    iterations = list((output/'P1').glob('S*/PRICE/FULL_PRICING_RESULT.json'))
    assert iterations
    latest = max(iterations, key=lambda p: int(p.parent.parent.name[1:]))
    folder = latest.parent.parent; priced = read(latest)
    compiled = read(folder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json')
    identity = read(folder/'MODEL_IDENTITY.json'); native = read(folder/'NATIVE_RESULT.json')
    assert compiled['PASS'] and compiled['differing_matrix_coefficients'] == 0
    assert identity['original_snapshot_sha256'] == compiled['original_snapshot_sha256']
    assert identity['solver_policy_unchanged'] and not identity['bound_variables_relaxed']
    assert native['status'] == 2 and native['native_error'] is None
    checked(native['model_identity']); checked(native['raw_attributes'])
    a = sp.load_npz(checked(identity['matrix'])); attrs = np.load(checked(identity['attributes']))
    raw = np.load(native['raw_attributes']['path'])
    assert all(np.all(np.isfinite(raw[k])) for k in ('X', 'Pi', 'RC'))
    assert a.shape == (len(raw['Pi']), len(raw['X']))
    activity = a@raw['X']; sense = attrs['senses']; rhs = attrs['rhs']
    residual = np.maximum(0, np.where(sense == '<', activity-rhs,
                         np.where(sense == '>', rhs-activity, abs(activity-rhs))))
    bounds = np.maximum(0, np.maximum(attrs['lower']-raw['X'], raw['X']-attrs['upper']))
    assert residual.max(initial=0) <= 1e-6 and bounds.max(initial=0) <= 1e-6
    rebuilt = attrs['objective']-a.T@raw['Pi']
    assert np.all(abs(rebuilt-raw['RC']) <= 1e-7+1e-10*np.maximum(abs(rebuilt), abs(raw['RC'])))
    parameters = read(folder/'SOLVER_PARAMETERS.json')['effective']
    assert parameters['Threads'] == 1 and parameters['FeasibilityTol'] == 1e-6
    assert parameters['OptimalityTol'] == 1e-6 and parameters['Method'] == 2
    qualified = read(output/'BLOCK_PRICING_ORACLE_VERIFICATION.json')
    assert qualified['PASS'] and qualified['producer'] == 'UNCHANGED_MAY19_FULL_NATIVE_BUILDER'
    required = {r['class_id']: r for r in qualified['records']}
    receipts = []
    for declared in priced['block_certificates']:
        f = block_folder(latest.parent, declared['class_id'])
        receipt = read(f/'EXACT_COMPLETE_BLOCK_CERTIFICATE.json')
        assert all(receipt[k] == v for k, v in declared.items())
        cache = load_cache(required[receipt['class_id']])
        if cache['snapshot'].matrix.shape[1]:
            local_native = read(f/'NATIVE_RESULT.json')
            assert local_native['status'] == 2 and local_native['native_error'] is None
            lp = np.load(checked(local_native['raw_attributes']))
            assert np.array_equal(lp['Pi'], receipt['local_raw_pi'])
            priced_snapshot = price_snapshot(cache['snapshot'], cache['B'], receipt['global_coupling_pi'])
            assert primal_replay(priced_snapshot, lp['X'])['PASS']
            assert verify_sign_convention(priced_snapshot, lp['Pi'], lp['RC'])['PASS']
            local_compiled = read(f/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json')
            assert local_compiled['PASS'] and local_compiled['differing_matrix_coefficients'] == 0
        receipts.append(receipt)
    assert len(receipts) == len(required) == priced['classes']
    validate_coverage(required, receipts, receipts[0]['global_coupling_pi'])
    epsilon = Fraction(POLICY['price_epsilon'])
    unresolved = [r for r in receipts if Fraction(r['minimum_rc_lower_bound']) < -epsilon]
    assert unresolved and not priced['no_negative_omitted_block_certified'] and priced['negative_blocks'] == 0
    assert all(Fraction(r['oracle_point_price']) >= -epsilon for r in receipts)
    assert priced['full_domain_phase1_lower_bound'] is not None
    assert record(result_path) == original
    return dict(PASS=True, disposition=DISPOSITION, original_result=original,
        original_scientific_classification=sci['classification'], original_scientific_error=sci['error'],
        original_FAIL_preserved=True, source_SHA=SCIENCE, auditor=record(__file__),
        request=result['request'], manifest=record(request['manifest']), prepared=record(output/'A_PREPARE_RECEIPT.json'),
        compiler=record(folder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'),
        matrix=identity['matrix'], attributes=identity['attributes'], raw=native['raw_attributes'],
        full_pricing=record(latest), complete_classes_revalidated=len(receipts),
        unresolved_classes=[dict(class_id=r['class_id'], minimum_rc_lower_bound=r['minimum_rc_lower_bound'],
                                 oracle_point_price=r['oracle_point_price']) for r in unresolved],
        original_primal_PASS=True, original_dual_PASS=True, original_pricing_verifier_PASS=True,
        Native_Runtime=measured, Native_calls=len(calls), additional_Native_calls=0,
        negative_support_nonexistence_proven=False, FULL_feasible_certified=False,
        global_gap_certified=False, Planning_Freeze_allowed=False, Actual_executed=False,
        date_retry_authorized=False, UTC=now())


if __name__ == '__main__':
    import json
    from v42_pr134_b1.common import atomic
    proof = audit(sys.argv[1]); atomic(sys.argv[2], proof)
    print(json.dumps(dict(PASS=True, disposition=proof['disposition'], classes=proof['complete_classes_revalidated'],
                         unresolved=len(proof['unresolved_classes']), additional_Native_calls=0)))
