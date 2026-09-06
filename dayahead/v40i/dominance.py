"""Planning structural dominance and independent Actual identity/outcome contracts.

No optimize() calls. A live B1 model is exported completely; unsupported general
constraints fail closed. The production entry requires separately granted gates.
"""
import math
from copy import deepcopy
from dayahead.v40h.identity import require
from dayahead.v40a.invariants import digest

GATE = 'B0_B1_PLANNING_STRUCTURAL_DOMINANCE'
IDENTITIES = ('workload_uids', 'D1_causal_workload', 'common_service_duration', 'common_residual_state',
    'common_terminal_obligation', 'electrical_planning_authority', 'objective_definition')
ACTUAL_IDENTITIES = ('realized_background_load','realized_PV','realized_weather','feeder_mapping','ratings',
    'native_control_state_authority','applicable_electrical_authority','workload_uids','realized_runtime_service_authority')


def export_b1_constraints(model, semantic_by_variable):
    """Capture ALL variable bounds/types, linear, quadratic and indicator constraints."""
    model.update(); variables = model.getVars()
    require(set(semantic_by_variable) == {v.VarName for v in variables}, 'B1_SEMANTIC_VARIABLE_COVERAGE')
    require(len(set(semantic_by_variable.values())) == len(variables), 'B1_DUPLICATE_SEMANTIC_VARIABLE')
    def linear(expr):
        return [[expr.getVar(i).VarName, float(expr.getCoeff(i))] for i in range(expr.size())]
    rows = [{'name': c.ConstrName, 'linear': linear(model.getRow(c)), 'quadratic': [], 'sense': c.Sense,
        'rhs': float(c.RHS)} for c in model.getConstrs()]
    for c in model.getQConstrs():
        expr = model.getQCRow(c)
        rows.append({'name': c.QCName, 'linear': linear(expr.getLinExpr()),
            'quadratic': [[expr.getVar1(i).VarName, expr.getVar2(i).VarName, float(expr.getCoeff(i))] for i in range(expr.size())],
            'sense': c.QCSense, 'rhs': float(c.QCRHS)})
    # Gurobi indicator type 7 and PWL type 8 (the current B1 GPU-to-PCC tables).
    # Other unexported general/SOS constraints fail closed.
    require(model.NumSOS == 0, 'B1_UNSUPPORTED_SOS_CONSTRAINT')
    for c in model.getGenConstrs():
        if c.GenConstrType == 8:
            x,y,xs,ys=model.getGenConstrPWL(c)
            require(len(xs)>=2 and all(a<b for a,b in zip(xs,xs[1:])), 'B1_PWL_STRICT_BREAKPOINTS_REQUIRED')
            rows.append({'name':c.GenConstrName,'pwl':{'x':x.VarName,'y':y.VarName,'x_points':list(xs),'y_points':list(ys)}})
            continue
        require(c.GenConstrType == 7, 'B1_UNSUPPORTED_GENERAL_CONSTRAINT')
        variable, value, expr, sense, rhs = model.getGenConstrIndicator(c)
        rows.append({'name': c.GenConstrName, 'linear': linear(expr), 'quadratic': [], 'sense': sense,
            'rhs': float(rhs), 'indicator': [variable.VarName, int(value)]})
    value = {'schema': 'V40I_COMPLETE_B1_CONSTRAINT_EXPORT_V1',
        'variables': [{'name': v.VarName, 'semantic': semantic_by_variable[v.VarName], 'lb': float(v.LB),
            'ub': float(v.UB), 'type': v.VType} for v in variables], 'constraints': rows,
        'counts': {'variables': model.NumVars, 'linear': model.NumConstrs, 'quadratic': model.NumQConstrs,
            'general': model.NumGenConstrs, 'sos': model.NumSOS}, 'complete_export': True}
    require(model.NumObj <= 1, 'B1_EXPORT_PRIMARY_OBJECTIVE_ONLY_REQUIRED')
    objective = model.getObjective()
    if hasattr(objective,'getLinExpr'):
        lin = objective.getLinExpr()
        quadratic = [[objective.getVar1(i).VarName,objective.getVar2(i).VarName,float(objective.getCoeff(i))] for i in range(objective.size())]
    else:lin=objective;quadratic=[]
    value['objective']={'linear':linear(lin),'quadratic':quadratic,'constant':float(lin.getConstant()),'sense':model.ModelSense}
    require(len(rows) == model.NumConstrs + model.NumQConstrs + model.NumGenConstrs, 'B1_CONSTRAINT_COVERAGE')
    return value


def extract_b0_incumbent(model, semantic_by_variable):
    """Read a previously authorized solved Planning model, never reoptimize."""
    model.update();variables=model.getVars()
    require(model.SolCount>0,'B0_INCUMBENT_NOT_AVAILABLE')
    require(set(semantic_by_variable)=={v.VarName for v in variables},'B0_SEMANTIC_VARIABLE_COVERAGE')
    require(len(set(semantic_by_variable.values()))==len(variables),'B0_SEMANTIC_DUPLICATE')
    result={semantic_by_variable[v.VarName]:float(v.X) for v in variables}
    require(all(math.isfinite(v) for v in result.values()),'B0_NONFINITE_INCUMBENT')
    return result


def map_b0_incumbent(b0, b1_space):
    require(b1_space.get('complete_export') is True, 'B1_COMPLETE_CONSTRAINT_EXPORT_REQUIRED')
    mapping = {}; variables = b1_space['variables']
    require(len({v['name'] for v in variables}) == len(variables), 'B1_VARIABLE_DUPLICATE')
    require(len({v['semantic'] for v in variables}) == len(variables), 'B1_SEMANTIC_DUPLICATE')
    for v in variables:
        if v['semantic'] in b0: value = b0[v['semantic']]
        elif v['lb'] == v['ub']: value = v['lb']
        else: raise ValueError('B0_TO_B1_MAPPING_MISSING:' + v['semantic'])
        require(math.isfinite(float(value)), 'B0_NONFINITE_INCUMBENT')
        mapping[v['name']] = float(value)
    return mapping


def direct_feasibility(space, values, tolerance):
    require(math.isfinite(tolerance) and tolerance >= 0, 'INVALID_FEASIBILITY_TOLERANCE')
    require(space.get('complete_export') is True, 'B1_COMPLETE_CONSTRAINT_EXPORT_REQUIRED')
    require(set(values) == {v['name'] for v in space['variables']}, 'B1_MAPPING_INCOMPLETE')
    counts = space['counts']
    require(len(space['variables']) == counts['variables'] and counts['sos'] == 0 and
        len(space['constraints']) == sum(counts[k] for k in ('linear', 'quadratic', 'general')), 'B1_EXPORT_COUNT_MISMATCH')
    violations = []
    for v in space['variables']:
        x = values[v['name']]; require(math.isfinite(x), 'B1_NONFINITE_MAPPING')
        require(v['type'] in ('C', 'B', 'I', 'S', 'N'), 'B1_UNKNOWN_VARIABLE_TYPE')
        semi_zero = v['type'] in ('S', 'N') and abs(x) <= tolerance
        if not semi_zero and not v['lb']-tolerance <= x <= v['ub']+tolerance:
            violations.append({'constraint': 'bound:' + v['name'], 'value': x, 'lb': v['lb'], 'ub': v['ub']})
        if v['type'] in ('B', 'I', 'N') and abs(x-round(x)) > tolerance:
            violations.append({'constraint': 'integrality:' + v['name'], 'value': x})
        if v['type'] == 'B' and min(abs(x), abs(x-1)) > tolerance:
            violations.append({'constraint': 'binary:' + v['name'], 'value': x})
    for c in space['constraints']:
        if 'pwl' in c:
            p=c['pwl'];xs=p['x_points'];ys=p['y_points'];x=values[p['x']];y=values[p['y']]
            require(len(xs)==len(ys) and len(xs)>=2 and all(a<b for a,b in zip(xs,xs[1:])), 'B1_INVALID_PWL_POINTS')
            index=next((i for i in range(len(xs)-1) if x<=xs[i+1]),len(xs)-2)
            expected=ys[index]+(x-xs[index])*(ys[index+1]-ys[index])/(xs[index+1]-xs[index])
            require(math.isfinite(expected),'B1_NONFINITE_PWL')
            if abs(y-expected)>tolerance:violations.append({'constraint':c['name'],'lhs':y,'rhs':expected,'violation':abs(y-expected)})
            continue
        if 'indicator' in c:
            name, flag = c['indicator']
            if abs(values[name] - flag) > tolerance: continue
        lhs = sum(values[n]*a for n,a in c['linear']) + sum(values[a]*values[b]*w for a,b,w in c['quadratic'])
        require(math.isfinite(lhs) and math.isfinite(c['rhs']), 'B1_NONFINITE_CONSTRAINT')
        sense = c['sense']; delta = lhs-c['rhs']
        require(sense in ('<', '>', '='), 'B1_UNKNOWN_CONSTRAINT_SENSE')
        error = max(0., delta) if sense == '<' else max(0., -delta) if sense == '>' else abs(delta)
        if error > tolerance: violations.append({'constraint': c['name'], 'lhs': lhs, 'rhs': c['rhs'], 'sense': sense, 'violation': error})
    return {'feasible': not violations, 'violated_B1_constraints': violations, 'checked_constraints': len(space['constraints']),
        'checked_variable_domains': len(space['variables']), 'mapping_SHA': digest(values), 'model_SHA': digest(space)}


def evaluate(b0, b1, space, *, objective_tolerance, feasibility_tolerance):
    """Day-Ahead Planning formulation only; never optimize or use Actual data."""
    require(math.isfinite(objective_tolerance) and objective_tolerance >= 0, 'INVALID_OBJECTIVE_TOLERANCE')
    require(b0['date'] == b1['date'], 'PLANNING_DAY_MISMATCH')
    diffs = {k: {'B0': b0['identities'].get(k), 'B1': b1['identities'].get(k)} for k in IDENTITIES
        if not b0['identities'].get(k) or not b1['identities'].get(k) or b0['identities'][k] != b1['identities'][k]}
    u0, u1 = set(b0['identities'].get('workload_uids', [])), set(b1['identities'].get('workload_uids', []))
    contamination = any(r.get('stage') != 'Planning' or r.get('fresh_execution') is not True or
        r.get('Actual_informed_policy') is not False for r in (b0,b1))
    reuse = sum(r.get('old_reuse_count', 1) for r in (b0,b1)); cache = sum(r.get('cache_hit_count', 1) for r in (b0,b1))
    j0, j1 = float(b0['objective']), float(b1['objective'])
    require(math.isfinite(j0) and math.isfinite(j1), 'NONFINITE_PLANNING_OBJECTIVE')
    result = {'gate': GATE, 'date': b0['date'], 'J_B0': j0, 'J_B1': j1, 'difference': j1-j0,
        'tolerance': objective_tolerance, 'B0_incumbent_feasible_in_B1': 'UNKNOWN', 'violated_B1_constraints': [],
        'workload_UID_set_diff': {'only_B0': sorted(u0-u1), 'only_B1': sorted(u1-u0)},
        'service_authority_diff': {k:diffs[k] for k in ('common_service_duration','common_residual_state','common_terminal_obligation') if k in diffs},
        'coefficient_identity_diff': diffs.get('electrical_planning_authority'), 'identity_diffs': diffs,
        'objective_component_decomposition': {'B0': b0.get('objective_components'), 'B1': b1.get('objective_components')},
        'solver_incumbent': b1.get('solver_incumbent'), 'solver_best_bound': b1.get('solver_best_bound'),
        'solver_gap': b1.get('solver_gap'), 'termination_reason': b1.get('termination_reason'),
        'A1_primary_objective': b1.get('A1_primary_objective'), 'MF_primary_objective': b1.get('MF_primary_objective'),
        'lower_level_objective_degradation': b1.get('lower_level_objective_degradation'),
        'old_reuse_count': reuse, 'cache_hit_count': cache, 'planning_fresh_actual_contamination': contamination,
        'production_valid_scientific_result': False, 'status': 'B0_B1_PLANNING_IDENTITY_FAIL'}
    if diffs or contamination or reuse or cache: return result
    for row in (b0,b1):
        require(isinstance(row.get('objective_components'), dict) and row['objective_components'], 'OBJECTIVE_DECOMPOSITION_REQUIRED')
        require(abs(sum(row['objective_components'].values())-row['objective']) <= objective_tolerance, 'OBJECTIVE_COMPONENT_SUM_MISMATCH')
    required = ('solver_incumbent','solver_best_bound','solver_gap','termination_reason',
        'A1_primary_objective','MF_primary_objective','lower_level_objective_degradation')
    require(all(b1.get(k) is not None for k in required), 'B1_SOLVER_FORENSIC_INCOMPLETE')
    require(b0.get('reference_candidate_identity') and b0['reference_candidate_identity'] in b1.get('authorized_candidate_identities', []),
        'B0_REFERENCE_NOT_INCLUDED_IN_B1_AUTHORIZED_DOMAIN')
    primary=b1.get('primary_certificate', {})
    require(primary.get('status')=='PASS' and math.isfinite(primary['bound']) and math.isfinite(primary['incumbent']) and
        primary['bound']<=primary['incumbent']+objective_tolerance, 'PRIMARY_OPTIMUM_BOUND_CERTIFICATION_REQUIRED')
    require(abs(primary['incumbent']-b1['A1_primary_objective'])<=objective_tolerance and
        b1['MF_primary_objective']<=b1['A1_primary_objective']+objective_tolerance and
        b1['lower_level_objective_degradation']<=objective_tolerance and
        j1<=primary['incumbent']+objective_tolerance, 'LOWER_LEVEL_PRIMARY_DEGRADATION')
    mapped = map_b0_incumbent(b0['incumbent_by_semantic'], space)
    objective=space['objective'];require(objective['sense']==1,'DOMINANCE_REQUIRES_MINIMIZATION_OBJECTIVE')
    mapped_objective=objective['constant']+sum(mapped[n]*w for n,w in objective['linear'])+sum(mapped[a]*mapped[b]*w for a,b,w in objective['quadratic'])
    require(math.isfinite(mapped_objective) and abs(mapped_objective-j0)<=objective_tolerance,'B0_MAPPED_OBJECTIVE_MISMATCH')
    result['B0_objective_recomputed_in_B1']=mapped_objective
    feasibility = direct_feasibility(space, mapped, feasibility_tolerance)
    result.update(feasibility=feasibility, B0_incumbent_feasible_in_B1='YES' if feasibility['feasible'] else 'NO',
        violated_B1_constraints=feasibility['violated_B1_constraints'])
    if not feasibility['feasible']: result['status'] = 'B0_REFERENCE_B1_PLANNING_FEASIBILITY_FAIL'
    elif j1 > j0 + objective_tolerance: result['status'] = 'B0_B1_PLANNING_STRUCTURAL_DOMINANCE_FAIL'
    else: result.update(status='PASS', production_valid_scientific_result=True)
    return result


def authorized_future_validation(authorization, *args, **kwargs):
    require(authorization.get('V40I_prerequisites') == 'PASS' and
        authorization.get('B2_B3_AUTHORIZED') == 'YES' and authorization.get('FULL_MAY_AUTHORIZED') == 'YES' and
        authorization.get('FRESH_B0_B1_ACTUAL_EXECUTION_AUTHORIZED') == 'YES', 'FUTURE_ACTUAL_EXECUTION_NOT_AUTHORIZED')
    return evaluate(*args, **kwargs)


def actual_replay_identity(b0, b1, *, accounting_tolerance=1e-8):
    """Hard gate for comparable frozen-policy realized replay, never outcome sign."""
    require(math.isfinite(accounting_tolerance) and accounting_tolerance>=0,'INVALID_ACCOUNTING_TOLERANCE')
    differences={k:{'B0':b0.get('identities',{}).get(k),'B1':b1.get('identities',{}).get(k)} for k in ACTUAL_IDENTITIES
        if not b0.get('identities',{}).get(k) or not b1.get('identities',{}).get(k) or
        b0['identities'][k]!=b1['identities'][k]}
    reasons=[]
    if b0.get('date')!=b1.get('date'):reasons.append('ACTUAL_DAY_MISMATCH')
    for name,row in (('B0',b0),('B1',b1)):
        if row.get('stage')!='Actual' or row.get('fresh_execution') is not True:reasons.append(name+':NAMESPACE_OR_FRESHNESS_INVALID')
        for field in ('Actual_reoptimization','Actual_informed_policy_selection','Actual_informed_parameter_tuning'):
            if row.get(field) is not False:reasons.append(name+':'+field)
        if row.get('old_reuse_count')!=0 or row.get('cache_hit_count')!=0:reasons.append(name+':OLD_OR_CACHE_REUSE')
        for field in ('GPU_service_conservation_error','runtime_service_conservation_error'):
            value=row.get(field)
            if value is None or not math.isfinite(value) or abs(value)>accounting_tolerance:reasons.append(name+':'+field)
    return {'gate':'B0_B1_ACTUAL_REPLAY_IDENTITY','status':'PASS' if not differences and not reasons else 'FAIL',
        'identity_differences':differences,'failure_reasons':reasons,'actual_outcome_sign_required':False,
        'actual_execution_intervals_may_differ_under_frozen_policies':True,'actual_reoptimization_performed':False}


def actual_outcome(b0, b1):
    """Scientific observation. A negative B0-B1 delta is not an integrity failure."""
    a,b=float(b0['rho']),float(b1['rho']);require(math.isfinite(a) and math.isfinite(b),'NONFINITE_ACTUAL_OUTCOME')
    delta=a-b
    return {'name':'B0_B1_ACTUAL_OUTCOME','Actual_rho_B0':a,'Actual_rho_B1':b,'delta_B0_minus_B1':delta,
        'relative_delta':delta/a if a else None,'direction':'IMPROVED' if delta>0 else 'DEGRADED' if delta<0 else 'UNCHANGED',
        'classification':'ACTUAL_GENERALIZATION_DEGRADATION_OBSERVED' if delta<0 else 'ACTUAL_GENERALIZATION_IMPROVEMENT_OBSERVED' if delta>0 else 'ACTUAL_OUTCOME_UNCHANGED',
        'critical_line':{'B0':b0.get('critical_line'),'B1':b1.get('critical_line')},
        'critical_phase':{'B0':b0.get('critical_phase'),'B1':b1.get('critical_phase')},
        'critical_slot':{'B0':b0.get('critical_slot'),'B1':b1.get('critical_slot')},
        'current_voltage_loading':{'B0':{k:b0.get(k) for k in ('current','voltage','loading')},'B1':{k:b1.get(k) for k in ('current','voltage','loading')}},
        'is_hard_gate':False,'actual_outcome_sign_required':False,'integrity_failure_due_to_outcome_sign':False,
        'Actual_informed_retuning':False}
