"""Independent JSON-only post-Native fairness, replay and budget certificate."""
from fractions import Fraction as F
import json
from pathlib import Path
import sys

from . import verify as v


def record_check(record):
    path = Path(record['path'])
    v.require(path.is_file() and v.file_sha(path) == record['sha256'], 'SEALED_ARTIFACT_FILE_SHA_DRIFT:'+path.name)
    return path


def main():
    comp = v.read(v.DOCS/'COMPARISON.json')
    started = v.read(v.DOCS/'RUN_STARTED.json')
    initial = v.read(record_check(started['initial_FULL_replay']))
    initial_point = v.load_point(record_check(started['initial']))
    v.require(v.vector_sha(initial_point) == v.INITIAL_VECTOR_SHA and initial['PASS'] is True
        and initial['point_vector_sha256'] == v.INITIAL_VECTOR_SHA
        and F(initial['exact_Global_UB']) == v.INITIAL_EXACT_UB, 'SHARED_INITIAL_FULL_U4_AUTHORITY')
    code = v.read(v.DOCS/'EXECUTED_SOURCE_HASHES.json')
    for name, expected in code.items():
        v.require(v.file_sha(v.ROOT/name) == expected, 'FROZEN_EXECUTED_SOURCE_SHA_DRIFT:'+name)
    v.authority()
    audited = {}
    total = F(0)
    for method in ('N1', 'N2', 'N3'):
        algo = comp['methods'][method]
        v.require(algo['initial_UB'] == float(v.INITIAL_EXACT_UB)
                  and algo.get('initial_point_vector_sha256') == v.INITIAL_VECTOR_SHA,
                  'ALGORITHM_FAIR_INITIAL_CENTER_DRIFT:'+method)
        used = F(0)
        requested = F(0)
        best = v.INITIAL_EXACT_UB
        best_record = started['initial']
        best_replay = started['initial_FULL_replay']
        center_vector = v.INITIAL_VECTOR_SHA
        signatures, calls, admitted, rejected = set(), [], [], []
        for iteration in algo['iterations']:
            v.require(v.vector_sha(v.load_point(record_check(iteration['center_point']))) == center_vector,
                      'CROSS_ALGORITHM_OR_UNVERIFIED_CENTER')
            v.require(F(iteration['center_UB']) == best, 'OWN_CENTER_OBJECTIVE_DRIFT')
            if 'native_receipt' not in iteration:
                v.require('error' in iteration, 'MISSING_NATIVE_OR_REJECTION_EVIDENCE')
                continue
            call = v.read(record_check(iteration['native_receipt']))
            v.require(call == algo['calls'][len(calls)], 'CALL_LEDGER_CONTENT_DRIFT')
            calls.append(call)
            v.require(call['method'] == method and call['Native_worker'] == 1 and call['Threads'] == 1
                      and call['restricted_ObjBound_is_Global_LB'] is False,
                      'RESTRICTED_NATIVE_CALL_POLICY_DRIFT')
            v.require(call.get('Native_Model_disposed_before_FULL_replay') is True
                      and iteration.get('Native_worker_exited_before_original_FULL_replay') is True,
                      'ORIGINAL_FULL_REPLAY_NATIVE_OVERLAP')
            native_path = Path(iteration['native_receipt']['path']).parent
            spec = v.read(native_path/'NEIGHBORHOOD.json')
            signature = spec['adapter_signature']
            v.require(signature not in signatures, 'DUPLICATE_FAILED_NEIGHBORHOOD')
            signatures.add(signature)
            proof = v.read(native_path/'INDEPENDENT_RESTRICTION_NATIVE0.json')
            v.require(proof['PASS'] is True and proof['center_point_vector_sha256'] == center_vector
                      and proof['original_power_SOC_and_all_nonroute_continuous_bounds_exact'] is True
                      and proof['restricted_ObjBound_is_Global_LB'] is False,
                      'INDEPENDENT_NATIVE0_RESTRICTION_BINDING')
            center_replay_path = record_check(spec['center_full_replay'])
            center_replay = v.read(center_replay_path)
            v.require(center_replay['PASS'] and center_replay['point_vector_sha256'] == center_vector,
                      'CENTER_SEALED_FULL_REPLAY_DRIFT')
            if call['entered_native']:
                v.require(call['runtime_unavailable'] is False and call['Native_Runtime'] is not None,
                          'UNMEASURED_NATIVE_RUNTIME')
                v.require(0 < call['requested_seconds'] <= 600.-float(used), 'CUMULATIVE_NATIVE_REQUEST_BUDGET')
                p = call['parameter_readback']
                v.require(p['Threads'] == 1 and p['TimeLimit'] == call['requested_seconds'], 'NATIVE_PARAMETER_READBACK')
                requested += F(call['requested_seconds'])
                used += F(call['Native_Runtime'])
            for candidate in iteration.get('validated_candidates', []):
                raw = record_check(candidate['raw'])
                replay_path = record_check(candidate['replay'])
                replay = v.read(replay_path)
                v.require(bool(candidate['PASS']) == bool(replay['PASS']), 'VALIDATED_CANDIDATE_RESULT_DRIFT')
                x = v.load_point(raw)
                v.require(replay['point_file_sha256'] == v.file_sha(raw)
                          and replay['point_vector_sha256'] == v.vector_sha(x), 'RAW_FULL_REPLAY_PACKET_BINDING')
                if not candidate['PASS']:
                    rejected.append(dict(raw=candidate['raw'], replay=candidate['replay'], error=replay.get('error'),
                                         integrality_faults=replay.get('raw_integrality_faults')))
                    continue
                v.require(replay['source_sha'] == v.SOURCE_SHA and replay['case_sha'] == v.CASE_SHA
                          and replay['strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact'] is True
                          and replay['original_matrix_and_96_slot_physical_replay']['PASS'] is True
                          and replay['solver_and_original_objective_bit_equal'] is True,
                          'STRICT_ORIGINAL_FULL_UB_ADMISSION_REQUIRED')
                objective = F(replay['exact_Global_UB'])
                admitted.append(dict(exact_verified_UB=str(objective), raw=candidate['raw'], replay=candidate['replay']))
                if objective < best:
                    best, best_record, best_replay = objective, candidate['raw'], candidate['replay']
                    center_vector = v.vector_sha(x)
        v.require(len(calls) == len(algo['calls']) and float(used) == algo['actual_Native_sum']
                  and float(requested) == algo['requested_Native_sum'], 'ACTUAL_RUNTIME_LEDGER_SUM_DRIFT')
        v.require(used <= 600, 'ALGORITHM_ACTUAL_NATIVE_CEILING_EXCEEDED')
        v.require(F(algo['final_verified_UB']) == best and algo['best_point'] == best_record,
                  'FINAL_UB_OR_BEST_PACKET_DRIFT')
        total += used
        audited[method] = dict(PASS=True, exact_verified_UB=str(best), verified_UB=float(best),
            best_point=best_record, best_FULL_replay=best_replay, actual_Native_seconds=float(used),
            requested_Native_seconds=float(requested), calls=len(calls), admitted_candidates=admitted,
            rejected_candidates=rejected, original_source_case_and_same_initial_U4=True,
            Global_LB_from_restricted_ObjBound=False)
    v.require(total <= 1800 and float(total) == comp['total_actual_Native_seconds'], 'TOTAL_NATIVE_LEDGER_CEILING')
    best = min(F(a['exact_verified_UB']) for a in audited.values())
    old_lb = F(.46498486997548166)
    v.require(comp['existing_Global_LB'] == float(old_lb) and comp['new_Global_LB_optimization_calls'] == 0,
              'FORBIDDEN_NEW_OR_RESTRICTED_GLOBAL_LB_PROMOTION')
    v.require(F(comp['best_verified_UB']) == best, 'BEST_VERIFIED_UB_COMPARISON_DRIFT')
    v.require('gurobipy' not in sys.modules, 'INDEPENDENT_FINAL_AUDIT_SOLVER_IMPORT')
    result = dict(PASS=True, source_sha=v.SOURCE_SHA, case_sha=v.CASE_SHA,
        comparison={'path':str(v.DOCS/'COMPARISON.json'),'sha256':v.file_sha(v.DOCS/'COMPARISON.json')},
        executed_sources_sha256=v.file_sha(v.DOCS/'EXECUTED_SOURCE_HASHES.json'),
        same_initial_point_vector_sha256=v.INITIAL_VECTOR_SHA, algorithms=audited,
        total_actual_Native_seconds=float(total), existing_Global_LB=float(old_lb),
        final_verified_UB=float(best), Global_gap_percent=100*float((best-old_lb)/best),
        no_new_Global_LB_optimization=True, scientific_FULL_validation_tolerances_unchanged=True,
        exact_literal_integers_and_objective_transport=True, exact_rational_continuous_feasibility_claim=False,
        Native_optimize_calls_by_auditor=0, Actual='ACTUAL_NOT_RUN')
    v.write(v.DOCS/'FINAL_INDEPENDENT_UB_CERTIFICATE.json', result)
    print(json.dumps(dict(PASS=True, verified_UB=float(best), Native_seconds=float(total))))


if __name__ == '__main__':
    main()
