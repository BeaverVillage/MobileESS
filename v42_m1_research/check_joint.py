"""Independent final M1 proof admission; producer flags never certify a bound.

All matrices are reconstructed from the pinned case. Native objectives and
restricted-neighborhood bounds are diagnostics. This module never optimizes.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
from scipy import sparse

from v42_unified.audit import ROOT
from .check_lb import (check_retained_relaxation, check_dual_certificate,
                       check_rational_dual_certificate, check_integer_count_cover)
from .check_ub import validate_candidate

GRID = {'line_thermal_face', 'transformer_kVA', 'voltage_upper', 'voltage_lower'}
HISTORICAL_NATIVE_LB = 0.5687116104049206


def check_case_identity(value, expected):
    """Check every explicit case binding before combining evidence."""
    if isinstance(value, dict):
        if 'case_sha' in value and value['case_sha'] != expected:
            raise ValueError('JOINT_EVIDENCE_SCIENTIFIC_CASE_MISMATCH')
        for child in value.values():
            check_case_identity(child, expected)
    elif isinstance(value, (list, tuple)):
        for child in value:
            check_case_identity(child, expected)


def _number(value, label, *, nonnegative=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('NONFINITE_OR_NONNUMERIC_ACCOUNTING:' + label)
    if nonnegative and value < 0:
        raise ValueError('NEGATIVE_ACCOUNTING:' + label)
    return float(value)


def check_ledger(receipt, case_sha):
    """Recompute all costs and chronological unused transfers, including failures."""
    if receipt.get('case_sha') != case_sha:
        raise ValueError('NATIVE_LEDGER_CASE_MISMATCH')
    check_case_identity(receipt, case_sha)
    if receipt.get('inflight') is not None:
        raise ValueError('NATIVE_LEDGER_STILL_IN_FLIGHT')
    if receipt.get('total_native_limit_seconds') != 5400:
        raise ValueError('COMBINED_NATIVE_LIMIT_DRIFT')
    if receipt.get('Threads') != 1 or isinstance(receipt.get('Threads'), bool):
        raise ValueError('SCIENTIFIC_THREAD_POLICY_DRIFT')
    expected = dict(Threads=1, MIPGap=0.005, FeasibilityTol=1e-8,
                    OptimalityTol=1e-8, IntFeasTol=1e-8)
    if receipt.get('scientific_tolerances') != expected:
        raise ValueError('ORIGINAL_M_SCIENTIFIC_TOLERANCE_DRIFT')
    if any(receipt.get(key) is not False for key in ('memory_limits', 'memory_automatic_stop', 'historical_ledgers_modified')):
        raise ValueError('FORBIDDEN_MEMORY_OR_HISTORICAL_LEDGER_POLICY')
    calls = receipt.get('calls', [])
    track_cost = {'LB': F(0), 'UB': F(0)}
    prefix = [(F(0), dict(track_cost))]
    work = 0.0
    for row in calls:
        if row.get('track') not in track_cost or row.get('state') not in ('FINISHED', 'FAILED'):
            raise ValueError('MISSING_TERMINAL_NATIVE_CALL')
        if row.get('case_sha') != case_sha or row.get('runtime_unavailable'):
            raise ValueError('UNMEASURED_OR_DIFFERENT_CASE_NATIVE_COST')
        runtime = _number(row.get('Native_Runtime'), 'Native_Runtime')
        if row.get('measured_Native_Runtime') != runtime:
            raise ValueError('FAILED_NATIVE_CALL_MEASUREMENT_NOT_ACCOUNTED')
        if row.get('runtime_accounting_scope') != 'MEASURED':
            raise ValueError('NATIVE_RUNTIME_IS_RESERVED_NOT_MEASURED')
        track_cost[row['track']] += F(runtime)
        prefix.append((sum(track_cost.values(), F(0)), dict(track_cost)))
        work += _number(row.get('Native_Work', 0.0), 'Native_Work')
    allocation = {'LB': F(3600), 'UB': F(1800)}
    events = {}
    previous_position = 0
    for transfer in receipt.get('transfers', []):
        source, target = transfer.get('source'), transfer.get('target')
        if {source, target} != {'LB', 'UB'}:
            raise ValueError('INVALID_BUDGET_TRANSFER_TRACKS')
        seconds = F(_number(transfer.get('seconds'), 'transfer_seconds'))
        if not seconds > 0:
            raise ValueError('UNUSED_TRANSFER_MUST_BE_POSITIVE')
        matches = [i for i in range(previous_position, len(prefix))
                   if sum(float(r['Native_Runtime']) for r in calls[:i]) == transfer.get('used_before')
                   and sum(float(r['Native_Runtime']) for r in calls[:i] if r['track']==source) == transfer.get('source_used_before')
                   and sum(float(r['Native_Runtime']) for r in calls[:i] if r['track']==target) == transfer.get('target_used_before')]
        if not matches:
            raise ValueError('TRANSFER_DOES_NOT_MATCH_CALL_PREFIX')
        position = matches[0]
        events.setdefault(position, []).append((source, target, seconds))
        previous_position = position
    for i, (total, spent) in enumerate(prefix):
        if total > 5400 or any(spent[t] > allocation[t] for t in allocation):
            raise ValueError('SPENT_BUDGET_CANNOT_BE_BACKFILLED_BY_TRANSFER')
        for source, target, seconds in events.get(i, []):
            if seconds > min(F(5400)-total, allocation[source]-spent[source]):
                raise ValueError('TRANSFER_USES_ALREADY_SPENT_BUDGET')
            allocation[source] -= seconds
            allocation[target] += seconds
        if i < len(calls):
            row = calls[i]
            allowed = min(F(5400)-total, allocation[row['track']]-spent[row['track']])
            assigned = F(_number(row.get('allocated_native_seconds'), 'allocated_native_seconds'))
            requested = F(_number(row.get('requested_seconds'), 'requested_seconds'))
            if not 0 < assigned <= min(allowed, requested):
                raise ValueError('NATIVE_CALL_WAS_ALLOCATED_BEYOND_REMAINING_BUDGET')
    final_total, final_track = prefix[-1]
    if receipt.get('allocations') != {t: float(v) for t, v in allocation.items()}:
        raise ValueError('FINAL_TRACK_ALLOCATION_DRIFT')
    measured_sum = sum(float(row['Native_Runtime']) for row in calls)
    if receipt.get('Native_Runtime_sum') != measured_sum or receipt.get('native_measured_Runtime_sum') != measured_sum:
        raise ValueError('COMBINED_FAILED_AND_SUCCESSFUL_RUNTIME_SUM_DRIFT')
    if receipt.get('track_Runtime') != {t: sum(float(r['Native_Runtime']) for r in calls if r['track']==t) for t in allocation}:
        raise ValueError('TRACK_NATIVE_RUNTIME_SUM_DRIFT')
    if receipt.get('Native_Work_sum') != work:
        raise ValueError('NATIVE_WORK_SUM_DRIFT')
    native_optimize_wall = sum(_number(row.get('optimize_wall_seconds'), 'native_optimize_wall_seconds') for row in calls)
    derived_costs = []
    for cost in receipt.get('non_native_wall_costs', []):
        recorded = _number(cost.get('wall_seconds'), 'recorded_cost_wall_seconds')
        nested = 0.0
        if cost.get('label') == 'MULTITIME_R_PREPARATION':
            # The runner's enclosing context includes both LP and MILP calls.
            # Preserve its raw receipt and subtract their measured API wall in
            # this derived view; Runtime is a different quantity.
            nested = sum(_number(row.get('optimize_wall_seconds'), 'R_native_optimize_wall_seconds')
                         for row in calls if row.get('label') in ('JOINT_MULTITIME_R_LP', 'JOINT_MULTITIME_R_MILP'))
            if nested > recorded:
                raise ValueError('ENCLOSING_COST_SMALLER_THAN_NESTED_NATIVE_OPTIMIZE_WALL')
        derived_costs.append(dict(kind=cost.get('kind'), label=cost.get('label'), track=cost.get('track'),
                                  raw_recorded_wall_seconds=recorded,
                                  raw_context_includes_native_optimize_wall=cost.get('label')=='MULTITIME_R_PREPARATION',
                                  nested_native_optimize_wall_seconds=nested,
                                  exclusive_non_native_wall_seconds=recorded-nested))
    wall = _number(receipt.get('wall_seconds'), 'stage_wall_seconds')
    practical = wall <= 5400
    if receipt.get('practical_wall_PASS') is not practical:
        raise ValueError('PRACTICAL_WALL_STATUS_DRIFT')
    if receipt.get('native_accounting_PASS') is not True or receipt.get('native_runtime_measurement_complete') is not True:
        raise ValueError('NATIVE_ACCOUNTING_NOT_COMPLETE')
    return dict(PASS=True, case_sha=case_sha, checked_native_calls=len(calls),
                failed_native_calls=sum(r['state']=='FAILED' for r in calls),
                Native_Runtime_sum=measured_sum, Native_Runtime_sum_exact=str(final_total),
                track_Runtime={t:float(v) for t,v in final_track.items()},
                allocations={t:float(v) for t,v in allocation.items()}, Native_Work_sum=work,
                unused_transfers_checked=len(receipt.get('transfers', [])),
                raw_non_native_cost_contexts_are_all_exclusive=not any(c['raw_context_includes_native_optimize_wall'] for c in derived_costs),
                derived_exclusive_non_native_costs=derived_costs,
                measured_native_optimize_wall_seconds=native_optimize_wall,
                recorded_exclusive_non_native_wall_seconds=sum(c['exclusive_non_native_wall_seconds'] for c in derived_costs),
                non_native_wall_costs_separate=True, original_ledger_preserved=True, wall_seconds=wall,
                practical_wall_PASS=practical, native_optimize_calls_by_checker=0)


@dataclass(frozen=True)
class VerifiedBound:
    """Only newly evaluated certificates with an independently established domain."""
    case_sha: str
    exact: F
    scope: str
    label: str


def aggregate_exact_bounds(case_sha, bounds, ub_exact):
    if not bounds:
        raise ValueError('NO_FRESH_FULL_DOMAIN_BOUND_CERTIFICATE')
    allowed = {'FULL_ORIGINAL_C3A', 'ORIGINAL_GRID_DELETION_RELAXATION', 'COMPLETE_INTEGER_COVER'}
    for bound in bounds:
        if not isinstance(bound, VerifiedBound):
            raise ValueError('PRODUCER_METADATA_OR_NATIVE_BOUND_NOT_ELIGIBLE')
        if bound.case_sha != case_sha:
            raise ValueError('JOINT_BOUND_SCIENTIFIC_CASE_MISMATCH')
        if bound.scope not in allowed:
            raise ValueError('RESTRICTED_OR_NATIVE_BOUND_IS_NOT_GLOBAL_LB')
    chosen = max(bounds, key=lambda b: b.exact)
    ub = F(ub_exact)
    if ub == 0 or chosen.exact > ub:
        raise ValueError('JOINT_CERTIFICATE_BOUND_ORDER_OR_ZERO_UB_INVALID')
    gap = (ub-chosen.exact)/abs(ub)
    numeric = float(gap)
    if F(numeric) < gap:
        numeric = math.nextafter(numeric, math.inf)
    percentage = float(100*gap)
    if F(percentage) < 100*gap:
        percentage = math.nextafter(percentage, math.inf)
    lb = float(chosen.exact)
    if F(lb) > chosen.exact:
        lb = math.nextafter(lb, -math.inf)
    return dict(independently_certified_Global_LB=lb, Global_LB_exact=str(chosen.exact),
                independently_validated_integer_Global_UB=float(ub), Global_UB_exact=str(ub),
                certified_Global_Gap_exact=str(gap), certified_Global_Gap_fraction_upper=numeric,
                certified_Global_Gap_percent_upper=percentage,
                selected_full_domain_certificate=chosen.label,
                M1_P1_GAP_CERTIFIED=gap <= F(1, 200), M1_ACCEPTED=False,
                P2_certificate=None, preserved_native_Global_LB=HISTORICAL_NATIVE_LB,
                preserved_native_Global_Gap_percent=100*(float(ub)-HISTORICAL_NATIVE_LB)/abs(float(ub)),
                inherited_native_LB_reclassified_exact=False,
                higher_archived_hull_bound_automatically_inherited=False)


def reconstruct_retained_domain(case, requirement):
    if requirement.get('case_sha') != case.case_sha:
        raise ValueError('MULTITIME_REQUIREMENT_CASE_MISMATCH')
    picked = []
    for record in requirement.get('selected_original_grid_rows', []):
        i = record.get('row')
        if isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < case.A.shape[0]:
            raise ValueError('SELECTED_GRID_ROW_AXIS_DRIFT')
        family = str(case.d['row_names'][i]).split('[', 1)[0]
        if family not in GRID or record.get('family') != family:
            raise ValueError('REQUIREMENT_NOT_ORIGINAL_GRID_ROW')
        a, b = case.A.indptr[i:i+2]
        if record.get('original_coefficients_SHA256') != hashlib.sha256(case.A.data[a:b].tobytes()).hexdigest():
            raise ValueError('REQUIREMENT_ORIGINAL_COEFFICIENT_HASH_DRIFT')
        if record.get('variables') != list(map(int, case.A.indices[a:b])):
            raise ValueError('REQUIREMENT_ORIGINAL_VARIABLE_AXIS_DRIFT')
        if record.get('sense') != str(case.d['sense'][i]) or record.get('rhs') != float(case.d['rhs'][i]):
            raise ValueError('REQUIREMENT_ORIGINAL_AFFINE_RHS_DRIFT')
        picked.append(i)
    if len(picked) != len(set(picked)):
        raise ValueError('DUPLICATE_SELECTED_GRID_REQUIREMENT')
    selected = set(picked)
    keep = np.asarray([i for i, name in enumerate(case.d['row_names'])
                       if str(name).split('[', 1)[0] not in GRID or i in selected], dtype=np.int64)
    R = case.A[keep].tocsr()
    e = dict(case.d, **{key:case.d[key][keep].copy() for key in ('rhs', 'sense', 'row_names')})
    inclusion = check_retained_relaxation(case.A, case.d, R, e, keep, case_sha=case.case_sha)
    return R, e, keep, inclusion


def reconstruct_complete_cover(case, report):
    cover = report.get('cover', {})
    if cover.get('case_sha') != case.case_sha:
        raise ValueError('JOINT_COUNT_CASE_MISMATCH')
    columns = cover.get('original_binary_columns', [])
    rows = cover.get('exact_leaf_rows', [])
    listed = report.get('leaves', [])
    if len(rows) != 2 or len(listed) != 2 or [r.get('leaf') for r in listed] != [0, 1]:
        raise ValueError('JOINT_COUNT_INCOMPLETE_LEAF_COVER')
    split = rows[0].get('rhs')
    if isinstance(split, bool) or not isinstance(split, int):
        raise ValueError('JOINT_COUNT_SPLIT_NOT_INTEGER')
    count = sparse.csr_matrix((np.ones(len(columns)), (np.zeros(len(columns), dtype=int), columns)),
                              shape=(1, case.A.shape[1]))
    B = sparse.vstack([case.A, count], format='csr')
    leaves = []
    for index, row in enumerate(rows):
        expected_sense = ('<', '>')[index]
        if row.get('sense') != expected_sense or row.get('rhs') != split+index:
            raise ValueError('JOINT_COUNT_SPLIT_HAS_HOLE_OR_WRONG_HALFSPACE')
        e = dict(case.d, rhs=np.r_[case.d['rhs'], float(row['rhs'])],
                 sense=np.r_[case.d['sense'], np.asarray([row['sense']], dtype=case.d['sense'].dtype)],
                 row_names=np.r_[case.d['row_names'], np.asarray(['CNT'], dtype=case.d['row_names'].dtype)])
        axis = np.r_[np.arange(case.A.shape[0], dtype=np.int64), -1-index]
        leaves.append(SimpleNamespace(A=B, d=e, retained_rows=axis))
        descriptor = listed[index].get('original_C3A_domain_plus_one_count_row')
        if descriptor is not None:
            expected = dict(case_sha=case.case_sha, original_rows=case.A.shape[0],
                            original_columns=case.A.shape[1], added_columns=columns,
                            added_coefficients=[1.]*len(columns), added_sense=row['sense'], added_rhs=row['rhs'],
                            all_original_rows_bounds_types_objective_unchanged=True)
            if descriptor != expected:
                raise ValueError('COUNT_LEAF_SAVED_DOMAIN_DESCRIPTOR_DRIFT')
    independent = check_integer_count_cover(case.A, case.d, leaves, columns, split,
                                          units=sorted(case.graph[1]), case_sha=case.case_sha)
    return leaves, independent


def _path(path, *, within=None):
    target = Path(path).resolve()
    if target.drive.upper() != 'D:' or not target.is_relative_to(ROOT.resolve()):
        raise ValueError('D_V42_CHECKER_EVIDENCE_REQUIRED')
    if within is not None and not target.is_relative_to(Path(within).resolve()):
        raise ValueError('RUN_EVIDENCE_PATH_ESCAPES_RUN_DIRECTORY')
    return target


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_exact_integer_replay(receipt):
    """Numerical row tolerances do not turn a near-integer vector into a plan."""
    if (receipt.get('C3A', {}).get('integer_pattern_exact') is not True
            or receipt.get('C3A', {}).get('exact_binary_0_1') is not True
            or receipt.get('original_full_matrix', {}).get('integer_pattern_exact') is not True
            or receipt.get('original_full_matrix', {}).get('exact_binary_0_1') is not True):
        raise ValueError('FINAL_UB_RAW_ORIGINAL_INTEGER_PATTERN_NOT_EXACT')
    return True


def evaluate_evidence(A, d, evidence, case_sha, *, run_path, source_rows=None):
    path = _path(evidence['path'], within=run_path)
    if _sha(path) != evidence.get('sha256'):
        raise ValueError('STORED_DUAL_EVIDENCE_HASH_DRIFT')
    if path.suffix == '.npz':
        with np.load(path, allow_pickle=False) as z:
            key = evidence.get('npz_key', 'dual')
            if key not in z.files:
                raise ValueError('STORED_DUAL_MULTIPLIER_KEY_MISSING')
            dual = z[key].copy()
        checked = check_dual_certificate(A, d, dual, case_sha=case_sha, source_rows=source_rows)
    elif path.suffix == '.json':
        checked = check_rational_dual_certificate(A, d, _read(path), case_sha=case_sha, source_rows=source_rows)
    else:
        raise ValueError('UNKNOWN_STORED_DUAL_MULTIPLIER_FORMAT')
    checked['checked_evidence'] = dict(path=str(path), sha256=_sha(path))
    return checked


def evaluate_complete_count_bound(case, joint, *, run_path):
    """Recompute each leaf proof and use min of ALL independently covered leaves."""
    leaves, cover = reconstruct_complete_cover(case, joint)
    if joint.get('row_proof_evidence'):
        proof = joint['row_proof_evidence']
        path = _path(proof['path'], within=run_path)
        if _sha(path) != proof.get('sha256') or _read(path) != joint['cover']:
            raise ValueError('COUNT_ROW_PROOF_SOURCE_HASH_OR_CONTENT_DRIFT')
    checked_leaves = []
    leaf_bounds = []
    for leaf, saved in zip(leaves, joint['leaves']):
        certificates = saved.get('certificates', [])
        if not certificates:
            raise ValueError('ALL_COMPLETE_COVER_LEAVES_REQUIRE_EXACT_CERTIFICATE')
        checked = []
        for entry in certificates:
            if 'dual_evidence' not in entry:
                raise ValueError('LEAF_BOUND_IS_METADATA_WITHOUT_MULTIPLIER_PROOF')
            r = evaluate_evidence(leaf.A, leaf.d, entry['dual_evidence'], case.case_sha,
                                  run_path=run_path, source_rows=leaf.retained_rows)
            checked.append(r)
        largest = max(F(r['exact_bound']) for r in checked)
        leaf_bounds.append(largest)
        checked_leaves.append(dict(leaf=saved['leaf'], exact_leaf_LB=str(largest),
                                   freshly_checked_certificates=checked))
    exact_cover = min(leaf_bounds)
    return (VerifiedBound(case.case_sha, exact_cover, 'COMPLETE_INTEGER_COVER',
                          'NEW_COMPLETE_JOINT_COUNT_ALL_LEAF_MINIMUM'),
            dict(complete_integer_cover=cover, ALL_leaf_certificates=checked_leaves))


def run(run_path, *, case=None):
    """Validate finalized research evidence and independently rebuild its bounds."""
    begin = perf_counter()
    run_path = _path(run_path)
    if case is None:
        from .case import load_case
        case = load_case()
    result = _read(run_path/'RESEARCH_TRACK_RESULTS.json')
    if result.get('case_sha') != case.case_sha:
        raise ValueError('FINAL_RESEARCH_RESULT_CASE_MISMATCH')
    check_case_identity(result, case.case_sha)
    ledger = _read(run_path/'NATIVE_RUNTIME_LEDGER.json')
    accounting = check_ledger(ledger, case.case_sha)
    if result.get('ledger') != ledger:
        raise ValueError('FINAL_NATIVE_LEDGER_SNAPSHOT_DRIFT')
    point_path = run_path/'FINAL_VALID_UB_POINT.npz'
    with np.load(point_path, allow_pickle=False) as z:
        if z.files != ['point']:
            raise ValueError('FINAL_UB_POINT_PACKET_AXIS_DRIFT')
        point = z['point'].copy()
    ub = validate_candidate(case, point)
    if not ub.get('PASS'):
        raise ValueError('FINAL_UB_ORIGINAL_INTEGER_PHYSICAL_REPLAY_FAILED')
    check_exact_integer_replay(ub)
    bounds, checks = [], {}
    if result.get('LB'):
        R, e, keep, inclusion = reconstruct_retained_domain(case, result['LB']['requirements'])
        checks['retained_domain'] = inclusion
        path = run_path/'MULTITIME_R_DUAL.npz'
        if path.exists():
            with np.load(path, allow_pickle=False) as z:
                if z.files != ['dual']:
                    raise ValueError('MULTITIME_R_DUAL_PACKET_DRIFT')
                dual = z['dual'].copy()
            r = check_dual_certificate(R, e, dual, source_rows=keep, case_sha=case.case_sha)
            checks['retained_R_bound'] = r
            bounds.append(VerifiedBound(case.case_sha, F(r['exact_bound']),
                                        'ORIGINAL_GRID_DELETION_RELAXATION', 'NEW_RETAINED_R_EXACT_DUAL'))
    joint = result.get('JOINT_DISJUNCTION', {})
    source = joint.get('original_full_ROOT_source', {})
    if source:
        checks['original_ROOT_certificates'] = []
        for key in ('raw_dual_evidence', 'repaired_dual_evidence'):
            r = evaluate_evidence(case.A, case.d, source[key], case.case_sha, run_path=run_path)
            checks['original_ROOT_certificates'].append(r)
            bounds.append(VerifiedBound(case.case_sha, F(r['exact_bound']),
                                        'FULL_ORIGINAL_C3A', 'NEW_ORIGINAL_ROOT_' + key))
    else:
        # A failed pilot does not prevent checking the completed original
        # archive against this exact C3A case, independently of its old receipt.
        from .case import committed_file
        path, receipt = committed_file('docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz')
        with np.load(path, allow_pickle=False) as z:
            dual = z['Pi'].copy()
        dual[(case.d['sense']=='<') & (dual>0)] = 0.
        dual[(case.d['sense']=='>') & (dual<0)] = 0.
        r = check_dual_certificate(case.A, case.d, dual, case_sha=case.case_sha)
        r['committed_archive_source'] = receipt
        checks['original_ROOT_certificates'] = [r]
        bounds.append(VerifiedBound(case.case_sha, F(r['exact_bound']), 'FULL_ORIGINAL_C3A', 'NEW_CHECK_OF_COMMITTED_ROOT_DUAL'))
    if joint.get('leaves'):
        bound, checked = evaluate_complete_count_bound(case, joint, run_path=run_path)
        checks.update(checked)
        bounds.append(bound)
    elif joint.get('cover', {}).get('original_binary_columns'):
        raise ValueError('REGISTERED_COUNT_COVER_MISSING_LEAF_CERTIFICATES')
    # rho is a single exact objective variable. Calculate UB with the original
    # objective coefficients as rationals, rather than trusting a producer float.
    ub_exact = F(float(np.asarray(case.d['constant']).item())) + sum(
        (F(float(case.d['objective'][j]))*F(float(point[j]))
         for j in np.flatnonzero(case.d['objective'])), F(0))
    if float(ub_exact) != ub['objective']:
        raise ValueError('FINAL_EXACT_RHO_OBJECTIVE_AXIS_DRIFT')
    combined = aggregate_exact_bounds(case.case_sha, bounds, ub_exact)
    return dict(PASS=True, schema='V42_M1_INDEPENDENT_JOINT_RESEARCH_CHECK_V1',
                case_sha=case.case_sha, **combined, original_integer_physical_replay=ub,
                checked_UB_packet=dict(path=str(point_path), sha256=_sha(point_path)),
                independent_domain_and_multiplier_checks=checks, independent_native_accounting=accounting,
                goal_0p5_percent=combined['M1_P1_GAP_CERTIFIED'],
                practical_wall_PASS=accounting['practical_wall_PASS'],
                native_optimize_calls_by_checker=0, checker_wall_seconds=perf_counter()-begin,
                producer_PASS_flags_used_as_proof=False, native_BestBd_used_as_Global_LB=False,
                restricted_neighborhood_LB_used_as_Global_LB=False,
                research_integrity_PASS_is_not_target_success=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_path')
    args = parser.parse_args()
    receipt = run(args.run_path)
    destination = ROOT/'docs/v42_m1_joint_gap_research/INDEPENDENT_JOINT_RESEARCH_CHECK.json'
    destination.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('INDEPENDENT_JOINT_CHECK_PASS', receipt['certified_Global_Gap_percent_upper'], receipt['M1_ACCEPTED'])
