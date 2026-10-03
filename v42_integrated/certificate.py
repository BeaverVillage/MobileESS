"""Certificate constructor accepts only a result bound to the regenerated model."""
from .governance import NORMALAMPS

def make(identity,result):
    if result.get('old_certificate_used') is not False or result.get('model_identity')!=identity:
        raise ValueError('NEW_MODEL_PROVENANCE_REQUIRED')
    if identity.get('NormalAmps_authority')!=NORMALAMPS or not identity.get('A1_freeze_sha256'):
        raise ValueError('NEW_PHYSICAL_AUTHORITY_REQUIRED')
    ub,lb,gap=(result[k] for k in ('UB','LB','gap'))
    physical=result.get('physical_audit');matrix=result.get('matrix_audit')
    incumbent=bool(matrix and matrix['PASS'] and physical and physical['PASS'])
    valid_lb=lb is not None and not result['callback_errors'] and result.get('status_name') in ('OPTIMAL','TIME_LIMIT','INTERRUPTED')
    accepted=bool(ub is not None and valid_lb and gap is not None and gap<=.005 and incumbent)
    return dict(schema='NEW_INTEGRATED_M1_CERTIFICATE_V1',model_identity=identity,UB=ub,LB=lb,gap=gap,valid_incumbent=incumbent,valid_global_LB=valid_lb,M1_ACCEPTED=accepted,old_certificate='SUPERSEDED_NOT_USED',P1='MIN MAX_LINE_LOADING',P2_order=['movement_energy','movement_count'],P2_execution='NOT_RUN: single P1 bound-oriented run',physical_PASS=bool(physical and physical['PASS']),authority_gates_PASS=True)
