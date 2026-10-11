"""Scientific repair cannot enter a production epoch without numerical evidence."""
from pathlib import Path
from v42_pr134_b1.common import read,record,digest

def validate(root,sources):
    path=Path(root)/'MODEL_VALIDATION_RELEASE_CONTRACT.json'
    if not path.is_file():raise PermissionError('SVR11_GLOBAL_MODEL_REPAIR_NOT_VALIDATED')
    c=read(path)
    if c.get('source_SHA')!=digest(sources) or c.get('model_code_SHA')!=sources['v42_svr11/model.py']:
        raise PermissionError('SVR11_GLOBAL_MODEL_VALIDATION_SOURCE_DRIFT')
    if c.get('model_version') in (None,'V42_SVR11_ELECTRICAL_CERTIFICATE_V1'):
        raise PermissionError('SVR11_GLOBAL_OLD_SENSITIVITIES_CANNOT_BE_MODEL_REPAIR')
    if c.get('Actual_inputs_used_in_Planning')!=0 or c.get('tap_optimization_variables')!=0:
        raise PermissionError('SVR11_GLOBAL_MODEL_CAUSALITY_OR_TAP_VARIABLE_FAILURE')
    if not c.get('independent_Holdout_claim') is False:
        raise PermissionError('SVR11_GLOBAL_DEVELOPMENT_DIAGNOSIS_IS_NOT_HOLDOUT')
    for key in ('root_cause','frozen_plan_prediction','May18_reoptimization','normal_date_validation','regression_validation'):
        r=c['evidence'][key]
        if record(r['path'])!=r:raise PermissionError('SVR11_GLOBAL_MODEL_EVIDENCE_SHA_DRIFT:'+key)
        e=read(r['path'])
        if e.get('synthetic_fixture_only') or e.get('Actual_inputs_used_for_model',0):
            raise PermissionError('SVR11_GLOBAL_MODEL_NUMERICAL_VALIDATION_REQUIRED:'+key)
        if key=='frozen_plan_prediction':
            if not abs(e['new_prediction_pu']-e['Forecast_AC_pu'])<abs(e['old_prediction_pu']-e['Forecast_AC_pu']):
                raise PermissionError('SVR11_GLOBAL_FROZEN_PLAN_ERROR_NOT_IMPROVED')
        elif key in ('May18_reoptimization','normal_date_validation'):
            if not (e.get('Forecast_only') is True and e.get('FULL_feasible_certified') is True
                and e.get('physical_slots')==96 and e.get('voltage_violations')==0
                and e.get('line_current_violations')==0 and e.get('transformer_current_violations')==0
                and e.get('transformer_kVA_violations')==0 and e.get('SVR_rating_violations')==0
                and e.get('AC_converged') is True and e.get('control_complete') is True
                and e.get('controller_settings_changed')==0):
                raise PermissionError('SVR11_GLOBAL_FORECAST_DEVELOPMENT_AC_VALIDATION_INCOMPLETE:'+key)
        elif e.get('PASS') is not True:raise PermissionError('SVR11_GLOBAL_MODEL_DIAGNOSTIC_NOT_PASSED:'+key)
    return record(path)
