"""One deterministic algorithmic policy; scientific equations are unchanged."""
from copy import deepcopy
from v42_pr134_b1.common import SETTINGS


SCHEMA = 'A_STAGE_SOLVER_POLICY_V2'
PRESERVED = ('MIPGap','Seed','FeasibilityTol','OptimalityTol','IntFeasTol')


def validate_frozen_policy(policy):
    """The fast successor reuses exactly one frozen scientific/native plan."""
    if policy.get('schema') != SCHEMA or policy.get('PASS') is not True:
        raise PermissionError('A_STAGE_SOLVER_POLICY_V2_REQUIRED')
    original = policy.get('original_authority_parameters')
    if original != SETTINGS:
        raise PermissionError('FROZEN_ORIGINAL_AUTHORITY_SETTINGS_DRIFT')
    expected = dict(original, Threads=1, Method=2, NodeMethod=1, MIPFocus=3,
        Crossover=original.get('Crossover', policy['parameter_support']['Crossover']['default']))
    if policy.get('parameters') != expected or expected['Crossover'] == 0:
        raise PermissionError('FAST_FROZEN_GLOBAL_SOLVER_POLICY_DRIFT')
    if policy.get('parameter_sweep') is not False or policy.get('scientific_model_change') is not False:
        raise PermissionError('FAST_FROZEN_GLOBAL_SOLVER_POLICY_DRIFT')
    if policy.get('preserved_scientific_settings') != {key: original[key] for key in PRESERVED}:
        raise PermissionError('FROZEN_A_STAGE_SCIENTIFIC_TOLERANCE_DRIFT')
    return True


def solver_policy(gp, *, frozen_settings=None):
    original=deepcopy(SETTINGS if frozen_settings is None else frozen_settings)
    version=tuple(gp.gurobi.version())
    supported={name:gp.getParamInfo(name) for name in ('NodeMethod','MIPFocus','Crossover')}
    if supported['NodeMethod'] is None or not (supported['NodeMethod'][3]<=1<=supported['NodeMethod'][4]):
        raise PermissionError('FROZEN_GUROBI_NODEMETHOD1_NOT_SUPPORTED')
    parameters=dict(original,Threads=1,Method=2,NodeMethod=1)
    focus=supported['MIPFocus']
    if focus is not None and focus[3]<=3<=focus[4]:parameters['MIPFocus']=3
    crossover=supported['Crossover']
    if crossover is None:raise PermissionError('FROZEN_GUROBI_CROSSOVER_METADATA_REQUIRED')
    parameters['Crossover']=original.get('Crossover',crossover[5])
    if parameters['Crossover']==0:
        raise PermissionError('DIAGNOSTIC_CROSSOVER0_NOT_PRODUCTION_POLICY')
    for key in PRESERVED:
        if key not in original or parameters[key]!=original[key]:
            raise PermissionError('FROZEN_A_STAGE_SCIENTIFIC_TOLERANCE_DRIFT:'+key)
    return dict(schema=SCHEMA,PASS=True,frozen_gurobi_version=list(version),
        original_authority_parameters=original,parameters=parameters,
        preserved_scientific_settings={key:original[key] for key in PRESERVED},
        parameter_support={key:dict(current=value[2],minimum=value[3],maximum=value[4],default=value[5])
            if value is not None else None for key,value in supported.items()},
        algorithmic_changes=['Threads=1','Method=2','NodeMethod=1']+
            (['MIPFocus=3'] if parameters.get('MIPFocus')==3 else []),
        scientific_model_change=False,parameter_sweep=False,
        cumulative_native_seconds_per_date=3600,build_and_static_verification_outside_native_budget=True,
        crossover_rule='Preserve frozen authority setting or frozen native default; diagnostic LP Crossover=0 is rejected')


def apply_policy(model, policy, gp):
    if policy.get('schema')!=SCHEMA or policy.get('PASS') is not True:
        raise PermissionError('A_STAGE_SOLVER_POLICY_V2_REQUIRED')
    if tuple(policy['frozen_gurobi_version'])!=tuple(gp.gurobi.version()):
        raise PermissionError('FROZEN_GUROBI_VERSION_DRIFT')
    if policy['parameters'].get('Crossover')==0:
        raise PermissionError('DIAGNOSTIC_CROSSOVER0_NOT_PRODUCTION_POLICY')
    for name,value in policy['parameters'].items():model.setParam(name,value)
    return {name:getattr(model.Params,name) for name in policy['parameters']}
