"""Require actual full-MILP/Runtime/RAM evidence before the V2 campaign."""
from pathlib import Path
from fractions import Fraction
from v42_pr134_b1.common import read,record,digest
from v42_common_mess import VERSION


def validate(root,sources):
    path=Path(root)/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json'
    if not path.is_file():raise PermissionError('SVR11_GLOBAL_FULL_MILP_NOT_REAL_VALIDATED')
    contract=read(path)
    if contract.get('source_SHA')!=digest(sources) or contract.get('algorithm_version')!=VERSION:
        raise PermissionError('SVR11_GLOBAL_FULL_MILP_VALIDATION_SOURCE_DRIFT')
    if contract.get('A1_A2_algorithms_changed') is not False or contract.get('M_native_limit_seconds')!=1800:
        raise PermissionError('SVR11_GLOBAL_FULL_MILP_RELEASE_POLICY_DRIFT')
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
