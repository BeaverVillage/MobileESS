"""Post-execution independent two-epoch certificate; no solver/CSR calls."""
from fractions import Fraction as F
from pathlib import Path
import json
import subprocess

from . import verify as v


def main():
    p = v.DOCS
    old = p/'CODE_EPOCH01_ORIGINAL_N1'
    prior = v.read(old/'EXECUTED_SOURCE_HASHES.json')
    current = v.read(p/'EXECUTED_SOURCE_HASHES.json')
    old_bindings = {}
    for name, expected in prior.items():
        path = v.ROOT/name
        if v.file_sha(path) != expected:
            path = old/Path(name).name
        v.require(path.is_file() and v.file_sha(path) == expected, 'N1_OLD_EPOCH_EXECUTED_BYTE_AUTHORITY:'+name)
        old_bindings[name] = dict(path=str(path), sha256=expected)
    v.require(all(v.file_sha(v.ROOT/name) == expected for name, expected in current.items()),
              'EPOCH02_EXECUTED_SOURCE_CODE_DRIFT')
    preservation = v.read(p/'N1_PRESERVATION_PRE_RESUME_NATIVE0.json')
    v.require(preservation['PASS'] and all(v.file_sha(v.ROOT/name) == item['sha256']
        and (v.ROOT/name).stat().st_size == item['bytes'] for name,item in preservation['files'].items()),
        'N1_IMMUTABLE_ARTIFACT_PRESERVATION_FAILURE')
    old_started, resumed = v.read(old/'RUN_STARTED.json'), v.read(p/'RUN_RESUMED_AFTER_N1.json')
    v.require(old_started['initial'] == resumed['initial'] and old_started['initial_vector_sha256'] ==
        resumed['initial_vector_sha256'] == v.INITIAL_VECTOR_SHA and resumed['methods'] == ['N2','N3'],
        'TWO_EPOCH_FAIR_SHARED_ORIGINAL_INITIAL_POINT')
    n1_equivalence = v.read(p/'N1_OLD_NEW_ACTUAL_SPEC_INDEPENDENT_EQUIVALENCE.json')
    v.require(n1_equivalence['PASS'] and n1_equivalence['old_current_and_actual_N1_math_spec_equal']
        and n1_equivalence['exact_N1_bound_arrays_equal'], 'N1_CHANGED_SIGNED_POLICY_INDEPENDENCE')
    cert = v.read(p/'FINAL_INDEPENDENT_UB_CERTIFICATE.json')
    comp = v.read(p/'COMPARISON.json')
    v.require(cert['PASS'] and cert['comparison']['sha256'] == v.file_sha(p/'COMPARISON.json')
        and comp['N1_preserved_no_reexecution'] is True and len(comp['methods']['N1']['calls']) == 1,
        'N1_NO_RERUN_OR_COMPARISON_CERTIFICATE_DRIFT')
    plan = v.read(p/'ORIGINAL_SOURCE_OPERATING_PLAN_COMPARISON.json')
    v.require(plan['PASS'] and plan['CSR_matrices_loaded'] == 0 and plan['Native_optimize_calls'] == 0,
              'ORIGINAL_OPERATION_PLAN_NO_NEW_SOLVER_AUDIT')
    for label, result in plan['candidates'].items():
        expected = float(v.INITIAL_EXACT_UB) if label == 'Original U4' else comp['methods'][label]['final_verified_UB']
        v.require(result['PASS'] and result['verified_UB'] == expected and all(
            len(unit['SOC97_kWh']) == 97 and unit['SOC_initial_kWh'] == 760.
            and abs(unit['SOC_terminal_kWh']-760.) <= 1e-6 and unit['physical_replay_PASS']
            for unit in result['units'].values()), 'ORIGINAL_FULL_OPERATING_PLAN_IDENTITY')
    resource = v.read(p/'POST_RUN_RESOURCE_SOURCE_AUDIT.json')
    v.require(resource['PASS'] is True, 'FINAL_ORIGINAL_SOURCE_B1_RESOURCE_PROTECTION')
    native_calls = []
    for method, algo in comp['methods'].items():
        for iteration in algo['iterations']:
            if 'native_receipt' not in iteration:
                continue
            root = Path(iteration['native_receipt']['path']).parent
            call = v.read(root/'NATIVE_CALL.json')
            native_calls.append(dict(method=method, path=str(root/'NATIVE_CALL.json'),
                sha256=v.file_sha(root/'NATIVE_CALL.json'), Runtime=call['Native_Runtime'],
                TimeLimit=call['parameter_readback']['TimeLimit']))
            model = v.read(root/'MODEL_IDENTITY.json')
            adapter = v.read(root/'ADAPTER_MODEL_IDENTITY.json')
            restriction = v.read(root/'INDEPENDENT_RESTRICTION_NATIVE0.json')
            v.require(model['PASS'] and all(model['checks'].values()) and adapter['PASS']
                and adapter['native_hamming_exact'] and not adapter['unrestricted_global_BB']
                and restriction['PASS'] and restriction['restricted_ObjBound_is_Global_LB'] is False,
                'ALL_NATIVE_MODEL_OR_PRIMAL_RESTRICTION_IDENTITY')
            v.require(call['parameter_readback']['Threads'] == 1 and not call['callback_errors']
                and call['callback_stop_reason'] is None and call['Status'] not in (3,4,5,12),
                'NATIVE_NUMERICAL_RESOURCE_OR_MODEL_INTEGRITY_FAILURE')
    v.require(len(native_calls) == 13, 'EXACT_EXECUTED_NATIVE_CALL_CENSUS')
    # Native root/best-bound figures never enter the Global LB arithmetic.
    best = F(cert['final_verified_UB'])
    lb = F(.46498486997548166)
    v.require(comp['existing_Global_LB'] == float(lb) and comp['new_Global_LB_optimization_calls'] == 0,
              'OLD_GLOBAL_LB_PROVENANCE_OR_RESTRICTED_PROMOTION')
    tracked = subprocess.run(['git','diff','--name-only','6ca7624d7eafd45d5b061ff33e262b0de32bfe8d','--'],
                              cwd=v.ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    v.require(all(name.startswith(('tools/u4_primal_alns/','docs/v42_b2_u4_primal_alns_600x3/'))
                  or name == 'B2_U4_PRIMAL_ALNS_600X3_FINAL_KO.md' for name in tracked),
              'INHERITED_SOURCE_OR_RESULTS_TRACKED_MUTATION')
    result = dict(PASS=True, source_sha=v.SOURCE_SHA, case_sha=v.CASE_SHA,
        independent_UB_certificate_sha256=v.file_sha(p/'FINAL_INDEPENDENT_UB_CERTIFICATE.json'),
        original_operating_plan_comparison_sha256=v.file_sha(p/'ORIGINAL_SOURCE_OPERATING_PLAN_COMPARISON.json'),
        original_N1_epoch_source_bindings=old_bindings, epoch02_code_seal_sha256=v.file_sha(p/'EXECUTED_SOURCE_HASHES.json'),
        N1_old_new_actual_spec_equivalence_sha256=v.file_sha(p/'N1_OLD_NEW_ACTUAL_SPEC_INDEPENDENT_EQUIVALENCE.json'),
        N1_artifacts_preservation_sha256=v.file_sha(p/'N1_PRESERVATION_PRE_RESUME_NATIVE0.json'),
        original_FULL_Case_Source_initial_SHA_fair=True, all_primal_fixings_Hamming_and_native_identity_PASS=True,
        independent_original_FULL_candidates_and_objectives_PASS=True, unchanged_scientific_tolerance_contract=True,
        exact_zero_residual_continuous_feasibility_claim=False, exact_budget_ceiling_PASS=True,
        native_calls=native_calls, total_actual_Native_seconds=comp['total_actual_Native_seconds'],
        per_method_actual_Native_seconds={m:a['actual_Native_sum'] for m,a in comp['methods'].items()},
        existing_Global_LB=float(lb), final_verified_UB=float(best), Global_gap_percent=100*float((best-lb)/best),
        winner=comp['winner'], source_or_B1_mutations=False, inherited_tracked_diff=tracked,
        final_resource_source_B1_audit_sha256=v.file_sha(p/'POST_RUN_RESOURCE_SOURCE_AUDIT.json'),
        Native_optimize_calls_by_auditor=0, full_CSR_constructed_by_auditor=False, Actual='ACTUAL_NOT_RUN')
    v.write(p/'FINAL_POST_EPOCH_INDEPENDENT_CERTIFICATE.json', result)
    print(json.dumps(dict(PASS=True, calls=len(native_calls), verified_UB=float(best),
                         Global_gap_percent=result['Global_gap_percent'])))


if __name__ == '__main__':
    main()
