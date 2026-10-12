"""Read-only result/epoch/resource audit. No solver import or model construction."""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs/v42_b2_u4_primal_alns_600x3'
INITIAL = .6760534504652341
GLOBAL_LB = .46498486997548166
INITIAL_VECTOR = 'c9d63854a3ec0747a65d2c6724a5d413585f9a4f6754107fc593ba69ea4eda0d'
PARAMS = dict(Threads=1, FeasibilityTol=1e-9, OptimalityTol=1e-9,
              IntFeasTol=1e-8, MIPGap=.005, Method=2, MIPFocus=1,
              NumericFocus=3, ScaleFlag=2, Seed=0, MIPGapAbs=1e-10)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exact_record(rec):
    return Path(rec['path']).is_file() and sha(rec['path']) == rec['sha256']


def audit(resource_path):
    checks, methods, failures, captures = {}, {}, [], []
    comparison = read(DOCS/'COMPARISON.json')
    preservation = read(DOCS/'N1_PRESERVATION_PRE_RESUME_NATIVE0.json')
    checks['N1_epoch01_all_preserved_bytes'] = all(
        (ROOT/name).is_file() and sha(ROOT/name) == rec['sha256']
        and (ROOT/name).stat().st_size == rec['bytes']
        for name, rec in preservation['files'].items())
    sealed = read(DOCS/'EXECUTED_SOURCE_HASHES.json')
    checks['epoch02_executed_code_and_policies_byte_exact'] = all(
        (ROOT/name).is_file() and sha(ROOT/name) == expected for name, expected in sealed.items())
    checks['resume_N1_preserved_once'] = comparison.get('N1_preserved_no_reexecution') is True
    checks['existing_Global_LB_unchanged'] = comparison['existing_Global_LB'] == GLOBAL_LB
    checks['no_new_Global_LB_optimization'] = comparison['new_Global_LB_optimization_calls'] == 0
    checks['ACTUAL_NOT_RUN'] = comparison['ACTUAL'] == 'ACTUAL_NOT_RUN'
    checks['one_worker_one_thread'] = comparison['Native_workers'] == comparison['Threads'] == 1
    resource = read(resource_path)
    checks['fresh_final_resource_source_B1_TASK_audit_PASS'] = resource['PASS'] is True
    actual_total, requested_total = 0., 0.
    process_peaks = dict(Peak_RSS_bytes=0, Peak_Private_Commit_bytes=0)
    native_entered = 0
    for method in ('N1', 'N2', 'N3'):
        ledger_path = DOCS/method/'ALGORITHM_LEDGER.json'
        algo = read(ledger_path) if ledger_path.is_file() else comparison['methods'][method]
        prefix = method + ':'
        checks[prefix+'same_original_U4_start'] = (algo['initial_UB'] == INITIAL
            and algo.get('initial_point_vector_sha256', INITIAL_VECTOR) == INITIAL_VECTOR)
        checks[prefix+'missing_ledger_only_for_unstarted_common_stop'] = (ledger_path.is_file()
            or (not algo['calls'] and algo['actual_Native_sum'] == 0
                and algo.get('stopped_reason') == 'COMMON_INTEGRITY_STOP'))
        checks[prefix+'comparison_preserves_exact_ledger'] = comparison['methods'][method] == algo
        checks[prefix+'all_entered_calls_recorded'] = len(algo['calls']) == len([
            p for p in (DOCS/method).glob('iteration*/native/NATIVE_CALL.json')])
        actual, requested, best = 0., 0., INITIAL
        method_calls = []
        seen_specs, non_native_iterations = set(), []
        for it in algo.get('iterations', []):
            spec_path = DOCS/method/f'iteration{it["index"]:02d}'/'SPEC.json'
            if spec_path.is_file():
                spec = read(spec_path)
                signature = hashlib.sha256(json.dumps(dict(free=sorted(spec['free_binary_columns']),
                    fixed_route=sorted(spec.get('fixed_route_columns', [])), radius=spec['hamming_radius'],
                    center=spec['center_point_vector_sha256']), sort_keys=True).encode()).hexdigest()
                checks[prefix+f'iteration{it["index"]:02d}:exact_math_signature'] = signature == spec['adapter_signature']
                if it.get('state') == 'SKIPPED_IDENTICAL_NEIGHBORHOOD':
                    checks[prefix+f'iteration{it["index"]:02d}:duplicate_skipped_without_Native'] = (
                        signature in seen_specs and it.get('Native_optimize_calls') == 0
                        and 'native_receipt' not in it and not (spec_path.parent/'native').exists())
                else:
                    checks[prefix+f'iteration{it["index"]:02d}:distinct_neighborhood'] = signature not in seen_specs
                    seen_specs.add(signature)
            if 'native_receipt' not in it:
                non_native_iterations.append(dict(index=it['index'], state=it.get('state'),
                    error=it.get('error'), Native_optimize_calls=0,
                    Native_used_before=it['Native_used_before']))
        call_iterations = [it for it in algo.get('iterations',[]) if 'native_receipt' in it]
        checks[prefix+'every_call_has_iteration_receipt'] = len(call_iterations) == len(algo['calls'])
        for index, (call, iteration) in enumerate(zip(algo['calls'], call_iterations)):
            key = prefix+f'call{index+1:02d}:'
            rec = iteration['native_receipt']
            checks[key+'immutable_call_receipt_SHA'] = exact_record(rec) and read(rec['path']) == call
            out = Path(rec['path']).parent
            checks[key+'center_previously_FULL_verified'] = iteration['center_UB'] == best
            if index == 0:
                checks[key+'first_call_original_U4_vector'] = call['center_vector_sha256'] == INITIAL_VECTOR
            checks[key+'worker_exited_before_FULL_replay'] = iteration['Native_worker_exited_before_original_FULL_replay']
            if call['entered_native']:
                native_entered += 1
                runtime = call.get('Native_Runtime')
                valid = isinstance(runtime, (int, float)) and math.isfinite(runtime) and runtime >= 0
                checks[key+'valid_terminal_runtime'] = valid and not call['runtime_unavailable']
                checks[key+'actual_used_before_exact'] = iteration['Native_used_before'] == actual
                checks[key+'next_TL_within_actual_remaining_minus_reserve'] = actual is not None and 0 < call['effective_TimeLimit'] <= 600.-actual-1.+1e-9
                if valid:
                    actual = actual + runtime if actual is not None else None
                else:
                    actual = None
                requested += call['requested_seconds']
                checks[key+'approved_exact_native_parameters'] = all(
                    call['parameter_readback'].get(k) == v for k, v in PARAMS.items())
                checks[key+'TimeLimit_exact_readback'] = call['parameter_readback']['TimeLimit'] == call['effective_TimeLimit']
                callback_violations = [sample for sample in call['resource_samples'] if not sample['safety']['PASS']]
                checks[key+'every_callback_violation_preserved_and_stopped'] = (not callback_violations
                    or bool(call.get('callback_stop_reason')) and algo['stopped_reason'] is not None)
                checks[key+'model_disposed_before_FULL_replay'] = call['Native_Model_disposed_before_FULL_replay']
                checks[key+'not_a_Global_LB'] = call['restricted_ObjBound_is_Global_LB'] is False
                checks[key+'no_unrestricted_global_BB'] = call['unrestricted_Full_global_BB_calls'] == 0
                identity = read(out/'ADAPTER_MODEL_IDENTITY.json')
                checks[key+'exact_original_rows_continuous_and_hamming'] = (
                    identity['PASS'] and identity['original_Dense_rows_exact']
                    and identity['native_hamming_exact'] and identity['added_rows'] == 1
                    and identity['model_rows'] == 715597 and identity['model_columns'] == 354277
                    and identity['total_binary'] == 9322
                    and identity['restrictions']['original_power_SOC_and_all_nonroute_continuous_bounds_exact']
                    and identity['restrictions']['center_always_included'])
                checks[key+'resource_pre_post_model_admission_PASS'] = (
                    read(out/'PRE_BUILD_GATE.json')['PASS'] and read(out/'POST_BUILD_NATIVE_ADMISSION.json')['PASS'])
                for memory in [call['build_memory_before'], call['build_memory_after'],
                               call['after_native_memory'], *[s['sample'] for s in call['resource_samples']]]:
                    for field in process_peaks:
                        process_peaks[field] = max(process_peaks[field], memory.get(field, 0))
            for validated in iteration.get('validated_candidates', []):
                ckey = key+'candidate:'+Path(validated['replay']['path']).stem+':'
                checks[ckey+'raw_and_replay_SHA'] = exact_record(validated['raw']) and exact_record(validated['replay'])
                replay = read(validated['replay']['path'])
                checks[ckey+'FULL_admission_agrees'] = validated['PASS'] == replay['PASS']
                if validated['PASS']:
                    objective = float(Fraction(replay['exact_Global_UB']))
                    checks[ckey+'exact_original_objective'] = objective == validated['verified_UB']
                    best = min(best, objective)
                captures.append(dict(method=method, iteration=index+1, **validated))
            checks[key+'ending_UB_from_only_FULL_PASS'] = iteration.get('ending_verified_UB', best) == best
            method_calls.append(dict(index=index+1, iteration_index=iteration['index'], entered_native=call['entered_native'],
                actual_runtime=call.get('Native_Runtime'), requested=call['requested_seconds'],
                status=call.get('Status'), restricted_ObjBound=call.get('ObjBound')))
        checks[prefix+'actual_budget_sum_exact'] = actual == algo['actual_Native_sum']
        checks[prefix+'requested_diagnostic_sum_exact'] = requested == algo['requested_Native_sum']
        checks[prefix+'actual_budget_le_600'] = actual is not None and actual <= 600.
        checks[prefix+'final_UB_only_FULL_PASS'] = best == algo['final_verified_UB']
        checks[prefix+'Global_gap_uses_retained_certified_LB'] = algo.get('Global_gap_percent',100*(best-GLOBAL_LB)/best) == 100*(best-GLOBAL_LB)/best
        if method == 'N1':
            checks['N1_runtime_exact_preserved'] = actual == preservation['N1_actual_Native_seconds']
            checks['N1_exactly_one_Native_call'] = len(algo['calls']) == preservation['N1_call_count'] == 1
        actual_total = actual_total + actual if actual_total is not None and actual is not None else None
        requested_total += requested
        methods[method] = dict(actual_Native_seconds=actual, requested_TimeLimit_seconds=requested,
            best_FULL_verified_UB=best, call_count=len(algo['calls']), calls=method_calls,
            non_native_iterations=non_native_iterations,
            classification=algo['classification'], stop_reason=algo['stopped_reason'])
    checks['actual_total_exact_and_le_1800'] = actual_total == comparison['total_actual_Native_seconds'] and actual_total is not None and actual_total <= 1800.
    checks['requested_total_diagnostic_exact'] = requested_total == comparison['total_requested_Native_seconds']
    checks['best_UB_from_independent_methods'] = comparison['best_verified_UB'] == min(INITIAL, *[v['best_FULL_verified_UB'] for v in methods.values()])
    failures = [name for name, result in checks.items() if not result]
    return dict(schema='V42_PRIMAL_ALNS_INDEPENDENT_RESULT_RESOURCE_EPOCH_AUDIT_V1',
        PASS=not failures, checks=checks, failures=failures, methods=methods,
        actual_total_Native_seconds=actual_total, requested_total_TimeLimit_diagnostic_seconds=requested_total,
        Native_optimize_calls_entered=native_entered, audited_process_peak_bytes=process_peaks,
        N1_preservation_file_count=len(preservation['files']), FULL_candidate_validation_receipts=captures,
        fresh_final_resource_audit=dict(path=str(resource_path), sha256=sha(resource_path)),
        observed_epoch_seconds=time.time(), Native_optimize_calls_by_auditor=0,
        source_model_builds_by_auditor=0, source_gp_imports_by_auditor=0,
        budget_interpretation='Actual Optimize Runtime accumulates per independent method without reset; requested TimeLimit totals are diagnostic. Every measured overrun is retained.',
        ACTUAL='ACTUAL_NOT_RUN', restricted_bounds_are_Global_LB=False, unchanged_Global_LB=GLOBAL_LB)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resource', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    began = time.perf_counter()
    result = audit(args.resource.resolve())
    result['audit_wall_seconds'] = time.perf_counter()-began
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    print(json.dumps({k:result[k] for k in ('PASS','failures','actual_total_Native_seconds','Native_optimize_calls_entered','audited_process_peak_bytes')}))
    return 0 if result['PASS'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
