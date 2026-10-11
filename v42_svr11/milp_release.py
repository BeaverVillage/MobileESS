"""Require actual full-MILP/Runtime/RAM evidence before the V2 campaign."""
from pathlib import Path
from fractions import Fraction
import math
from v42_pr134_b1.common import read,record,digest
from v42_common_mess import VERSION


def _checked(receipt,reason):
    if record(receipt['path'])!=receipt:raise PermissionError(reason)
    return read(receipt['path'])


def _validate_root180(contract):
    value=_checked(contract['representative_root_validation'],'SVR11_GLOBAL_ROOT180_RECEIPT_DRIFT')
    full=value.get('full',{})
    seconds=full.get('Root_LP_seconds')
    if not (value.get('PASS') is True and value.get('source_SHA')==contract['source_SHA']
            and value.get('classification')=='EXACT_REDUCTION_AND_ROOT180_VALIDATED'
            and value.get('exact_reduction_proven') is True and value.get('root180_validated') is True
            and value.get('Full_native_calls')==1 and value.get('production_results_promoted')==0
            and value.get('old_optimization_results_read')==value.get('old_UB_LB_gap_reused')==0
            and value.get('original_and_LP_and_integer_domains_identical') is True
            and full.get('Root_LP_status')=='NATIVE_LOG_REPORTED'
            and full.get('native_error') is None
            and type(seconds) in (int,float) and math.isfinite(seconds) and 0<seconds<=200):
        raise PermissionError('SVR11_GLOBAL_COMPLETED_ROOT180_AND_EXACT_REDUCTION_REQUIRED')
    proof=_checked(value['C3A_proof'],'SVR11_GLOBAL_ROOT180_EXACT_PROOF_DRIFT')
    if not (proof.get('PASS') is True and proof.get('fresh_current_matrix_certificates') is True
            and proof.get('independent_model_proof_replayed') is True
            and proof.get('objective_and_integer_and_full_LP_domains_preserved') is True
            and proof.get('selected_matrix_SHA256')==value.get('selected_matrix_SHA')
            and value.get('transport',{}).get('pre_C2_security_independent_proof',{}).get('PASS') is True):
        raise PermissionError('SVR11_GLOBAL_ROOT180_EXACT_PROOF_REQUIRED')
    identity=_checked(full['original_model_identity'],'SVR11_GLOBAL_ROOT180_FULL_IDENTITY_DRIFT')
    if not (identity.get('unrestricted_original_C3A_MILP') is True
            and all(identity.get('checks',{}).get(k) is True for k in (
                'original_source_rows_exact','original_RHS_exact','original_senses_exact',
                'original_objective_exact','types_exact','restricted_bounds_exact','original_continuous_bounds_exact'))
            and all(identity.get('unrestricted_checks',{}).get(k) is True for k in (
                'all_original_bounds_exact','all_original_integer_types_exact',
                'all_original_rows_and_no_additional_cuts','no_neighborhood_or_hamming_constraint','original_minimization'))
            and identity.get('spec') is None and identity.get('case_sha')==full.get('case_sha')
            and identity.get('original_model_identity',{}).get('selected_matrix_sha')==value.get('selected_matrix_SHA')
            and identity.get('original_model_identity',{}).get('selected_domain_sha')==value.get('selected_domain_SHA')):
        raise PermissionError('SVR11_GLOBAL_ROOT180_UNRESTRICTED_FULL_REQUIRED')
    replay=_checked(value['final_original_FULL_replay'],'SVR11_GLOBAL_ROOT180_FULL_REPLAY_DRIFT')
    if not (replay.get('PASS') is True
            and replay.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is True
            and replay.get('original_matrix_and_96_slot_physical_replay',{}).get('PASS') is True
            and replay.get('case_sha')==full.get('case_sha')):
        raise PermissionError('SVR11_GLOBAL_ROOT180_ORIGINAL_INTEGER_PHYSICAL_REPLAY_REQUIRED')
    runtime=value.get('Native_Runtime')
    if type(runtime) not in (int,float) or not math.isfinite(runtime) or not 0<runtime<=1800:
        raise PermissionError('SVR11_GLOBAL_ROOT180_MEASURED_NATIVE_BUDGET_REQUIRED')


def _validate_exact_c3a(contract):
    """Current exact reduction needs short fresh evidence, not a repeated 1800s run."""
    receipt=contract['minimal_current_validation']
    current=_checked(receipt,'SVR11_GLOBAL_CURRENT_C3A_VALIDATION_BYTES_DRIFT')
    if not (current.get('PASS') is True and current.get('source_SHA')==contract['source_SHA']
            and current.get('Native_M_limit_seconds')==1800
            and current.get('A1_A2_algorithms_changed') is False
            and current.get('physical_and_forecast_science_bitwise_unchanged') is True
            and current.get('production_results_promoted')==0):
        raise PermissionError('SVR11_GLOBAL_CURRENT_C3A_VALIDATION_BINDING_DRIFT')
    proof=_checked(current['exact_reduction_proof'],'SVR11_GLOBAL_CURRENT_C3A_PROOF_DRIFT')
    if not (proof.get('PASS') is True
            and proof.get('schema')=='V42_CURRENT_EXACT_C3A_PROOF_V1'
            and proof.get('fresh_current_matrix_certificates') is True
            and proof.get('historical_row_indices_read')==0
            and proof.get('objective_and_integer_and_full_LP_domains_preserved') is True):
        raise PermissionError('SVR11_GLOBAL_CURRENT_EXACT_C3A_PROOF_REQUIRED')
    equivalent=_checked(current['original_equivalence_validation'],
        'SVR11_GLOBAL_CURRENT_C3A_EQUIVALENCE_BYTES_DRIFT')
    if equivalent.get('PASS') is not True:
        raise PermissionError('SVR11_GLOBAL_CURRENT_C3A_ORIGINAL_EQUIVALENCE_REQUIRED')
    gap=_checked(current['gap_validation'],'SVR11_GLOBAL_CURRENT_GAP_VALIDATION_DRIFT')
    if not (gap.get('PASS') is True and gap.get('source_SHA')==contract['source_SHA']
            and gap.get('restricted_U4_bound_never_global') is True
            and gap.get('Solver_gap_and_independent_certified_gap_distinct') is True
            and gap.get('full_equivalent_solver_bound_admission') is True
            and gap.get('no_long_LP_or_CG_added') is True):
        raise PermissionError('SVR11_GLOBAL_CURRENT_GAP_VALIDATION_REQUIRED')
    smoke=_checked(current['runtime_smoke'],'SVR11_GLOBAL_C3A_RUNTIME_SMOKE_BYTES_DRIFT')
    runtime=smoke.get('Native_Runtime');limit=smoke.get('effective_TimeLimit')
    if not (smoke.get('PASS') is True and smoke.get('source_SHA')==contract['source_SHA']
            and smoke.get('development_only') is True and smoke.get('production_results_promoted')==0
            and type(runtime) in (int,float) and math.isfinite(runtime) and runtime>0
            and type(limit) in (int,float) and 0<limit<=60
            and smoke.get('cumulative_native_budget_preserved') is True
            and smoke.get('FULL_feasible_certified') is True and smoke.get('UB_nonregression') is True):
        raise PermissionError('SVR11_GLOBAL_C3A_SHORT_REAL_NATIVE_SMOKE_REQUIRED')
    identity=_checked(smoke['original_model_identity'],'SVR11_GLOBAL_C3A_SMOKE_IDENTITY_DRIFT')
    if not (identity.get('PASS') is True and identity.get('unrestricted_original_C3A_MILP') is True
            and all(identity['checks'].values()) and all(identity['unrestricted_checks'].values())
            and identity.get('spec') is None):
        raise PermissionError('SVR11_GLOBAL_C3A_SMOKE_UNRESTRICTED_IDENTITY_REQUIRED')
    ledger=_checked(smoke['native_ledger'],'SVR11_GLOBAL_C3A_SMOKE_NATIVE_LEDGER_DRIFT')
    total=0.
    if ledger.get('inflight') is not None or not ledger.get('calls'):
        raise PermissionError('SVR11_GLOBAL_C3A_SMOKE_NATIVE_LEDGER_REQUIRED')
    for row in ledger['calls']:
        measured=row.get('Native_Runtime')
        if (row.get('runtime_unavailable') or row.get('entered_native') is not True
                or type(measured) not in (int,float) or not math.isfinite(measured) or measured<0
                or not 0<row['effective_TimeLimit']<=min(row['requested_seconds'],1800-total)):
            raise PermissionError('SVR11_GLOBAL_C3A_SMOKE_CUMULATIVE_NATIVE_DRIFT')
        total+=measured
    if not math.isclose(total,runtime,rel_tol=0,abs_tol=1e-9):
        raise PermissionError('SVR11_GLOBAL_C3A_SMOKE_RUNTIME_RESET_OR_DOUBLECOUNT')
    # Historical continuation evidence remains under its actual execution SHA.
    historical=contract['historical_full_milp_validation']
    origin=_checked(historical['contract'],'SVR11_GLOBAL_HISTORICAL_FULL_MILP_PROOF_DRIFT')
    if origin['source_SHA']!=historical['execution_source_SHA']:
        raise PermissionError('SVR11_GLOBAL_HISTORICAL_FULL_MILP_SHA_RELABELLED')
    for receipt in origin['real_validation'].values():
        result=_checked(receipt,'SVR11_GLOBAL_HISTORICAL_FULL_MILP_RESULT_DRIFT')
        if result.get('source_SHA')!=historical['execution_source_SHA'] or result.get('PASS') is not True:
            raise PermissionError('SVR11_GLOBAL_HISTORICAL_FULL_MILP_RESULT_RELABELLED')


def validate(root,sources):
    path=Path(root)/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json'
    if not path.is_file():raise PermissionError('SVR11_GLOBAL_FULL_MILP_NOT_REAL_VALIDATED')
    contract=read(path)
    if contract.get('source_SHA')!=digest(sources) or contract.get('algorithm_version')!=VERSION:
        raise PermissionError('SVR11_GLOBAL_FULL_MILP_VALIDATION_SOURCE_DRIFT')
    if contract.get('A1_A2_algorithms_changed') is not False or contract.get('M_native_limit_seconds')!=1800:
        raise PermissionError('SVR11_GLOBAL_FULL_MILP_RELEASE_POLICY_DRIFT')
    if contract.get('schema')=='SVR11_ROOT180_EXACT_RELEASE_V1':
        _validate_root180(contract)
        return record(path)
    if contract.get('schema')=='SVR11_CAMPAIGN_REUSE_VALIDATED_ALGORITHM_V1':
        origin=_checked(contract['previous_validated_release'],
            'SVR11_GLOBAL_PREVIOUS_C3A_RELEASE_BYTES_DRIFT')
        _validate_exact_c3a(origin)
        authority=_checked(contract['validated_construction_algorithm'],
            'SVR11_GLOBAL_CONSTRUCTION_ALGORITHM_RECEIPT_DRIFT')
        if not (authority.get('source_SHA')==contract['source_SHA']
                and authority.get('construction_algorithms_unchanged') is True
                and authority.get('user_authorized_no_daily_proof') is True
                and authority.get('previous_source_SHA')==origin['source_SHA']):
            raise PermissionError('SVR11_GLOBAL_CONSTRUCTION_ALGORITHM_REUSE_INVALID')
        return record(path)
    if contract.get('schema')=='SVR11_EXACT_C3A_MINIMAL_RELEASE_V1':
        _validate_exact_c3a(contract)
        return record(path)
    for day in ('2025-05-16','2025-05-18'):
        receipt=contract['real_validation'][day]
        if record(receipt['path'])!=receipt:raise PermissionError('SVR11_GLOBAL_FULL_MILP_PROOF_BYTES_DRIFT')
        result=read(receipt['path'])
        if not (result.get('PASS') is True and result.get('development_only') is True
                and result.get('production_results_promoted')==0 and result.get('Phase2_started') is True
                and result.get('source_SHA')==contract['source_SHA'] and result.get('Phase2_calls',0)>0
                and result.get('FULL_feasible_certified') is True and result.get('UB_nonregression') is True
                and Fraction(result['exact_final_UB'])<=Fraction(result['exact_initial_UB'])
                and result['Native_Runtime']>=1800
                and result['termination_reason']=='NATIVE_1800_SECONDS_EXHAUSTED'):
            raise PermissionError('SVR11_GLOBAL_FULL_MILP_REAL_VALIDATION_INCOMPLETE:'+day)
        ledger_receipt=result['native_ledger']
        if record(ledger_receipt['path'])!=ledger_receipt:raise PermissionError('SVR11_GLOBAL_FULL_MILP_LEDGER_DRIFT')
        ledger=read(ledger_receipt['path']);prior=result['prior_measured_Native_Runtime'];total=prior
        if ledger['inflight'] is not None:raise PermissionError('SVR11_GLOBAL_FULL_MILP_INFLIGHT_QUARANTINE')
        for row in ledger['calls']:
            if (row['runtime_unavailable'] or row['entered_native'] is not True or row['Native_Runtime'] is None
                    or row['track']!='M_FULL_MILP' or row['effective_TimeLimit']!=min(row['requested_seconds'],1800-total)):
                raise PermissionError('SVR11_GLOBAL_FULL_MILP_RUNTIME_OR_LIMIT_DRIFT')
            total+=row['Native_Runtime']
        if abs(total-result['Native_Runtime'])>1e-9:
            raise PermissionError('SVR11_GLOBAL_FULL_MILP_DOUBLECOUNT_OR_RUNTIME_RESET')
        for row in result['Phase2_rows']:
            identity_receipt=row['original_model_identity']
            if record(identity_receipt['path'])!=identity_receipt:raise PermissionError('SVR11_GLOBAL_FULL_MILP_IDENTITY_BYTES_DRIFT')
            identity=read(identity_receipt['path'])
            if not (identity['unrestricted_original_C3A_MILP'] and all(identity['checks'].values())
                    and all(identity['unrestricted_checks'].values()) and identity['spec'] is None
                    and identity['memory_after']['RSS_bytes']>0 and identity['memory_after']['private_bytes']>0
                    and row['effective_MIPGap']==row['effective_MIPGapAbs']==0
                    and row['full_MILP_bound_independently_certified'] is False):
                raise PermissionError('SVR11_GLOBAL_FULL_MILP_DOMAIN_START_OR_MEMORY_PROOF_REQUIRED')
        certificate=result['final_FULL_certificate']
        if record(certificate['path'])!=certificate or read(certificate['path']).get('PASS') is not True:
            raise PermissionError('SVR11_GLOBAL_FULL_MILP_FINAL_FULL_CERTIFICATE_REQUIRED')
    return record(path)
