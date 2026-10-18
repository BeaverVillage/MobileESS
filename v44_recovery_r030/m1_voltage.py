"""Tighten only B3 M1 and verify the actual FULL voltage rows and plan."""
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from unittest.mock import patch
import numpy as np
from v44.common import atomic, record, now

LOWER = .955
UPPER = 1.045
LOWER_SQUARED = .912025
UPPER_SQUARED = 1.092025
POLICY = 'V44_R030_B3_M1_VOLTAGE_0955_1045_ALL_DATES'


def selected(request):
    return (request.get('arm'), request.get('stage')) == ('B3', 'M1')


@contextmanager
def scope(request):
    from v42_native import voltage
    from v42_integrated import contract
    before = dict(voltage._MAPPING)
    if not selected(request):
        yield
        return
    if any(request.get(k) for k in ('resume_parent', 'resume_of')):
        raise PermissionError('R030_NEW_M1_MODEL_REQUIRES_FRESH_NATIVE_CLOCKS')
    if (before[voltage.Stage.M1].lower_pu, before[voltage.Stage.M1].upper_pu) != (.95, 1.05):
        raise PermissionError('R030_ORIGINAL_M1_AUTHORITY_REQUIRED')
    tight = voltage.Voltage(POLICY, LOWER, UPPER, LOWER_SQUARED, UPPER_SQUARED)
    original_authority = contract.physical_authority

    @contextmanager
    def physical_authority():
        # Original equipment/hash checks run in full. That context resets all
        # Planning bands; restore this explicitly authorized M1 band afterward.
        with original_authority() as authority:
            voltage._MAPPING[voltage.Stage.M1] = tight
            yield authority

    voltage._MAPPING[voltage.Stage.M1] = tight
    try:
        with patch.object(contract, 'physical_authority', physical_authority):
            yield
    finally:
        voltage._MAPPING.clear()
        voltage._MAPPING.update(before)


def check_rows(case):
    """The global rows use signed RHS; compare against the fixed AIDC anchor."""
    names = list(map(str, case.original_d['row_names']))
    lower = np.array([i for i, name in enumerate(names) if name.startswith('voltage_lower[')], dtype=int)
    upper = np.array([i for i, name in enumerate(names) if name.startswith('voltage_upper[')], dtype=int)
    coefficients = case.coefficients
    expected = sum(len(c.voltage_constant) for c in coefficients)
    if len(lower) != expected or len(upper) != expected:
        raise ValueError('R030_COMPLETE_VOLTAGE_ROW_AXIS_REQUIRED')
    controls = np.asarray(case.anchor['controls'], float)
    offsets = np.concatenate([c.voltage_constant+c.voltage_matrix.T@x for c, x in zip(coefficients, controls)])
    rhs = np.asarray(case.original_d['rhs'], float)
    senses = np.asarray(case.original_d['sense']).astype(str)
    # Original native grid: voltage_lower is >= and voltage_upper is <=.
    if not np.all(senses[lower] == '>') or not np.all(senses[upper] == '<'):
        raise ValueError('R030_ORIGINAL_VOLTAGE_ROW_SENSE_REQUIRED')
    lower_error = float(np.max(np.abs(rhs[lower] - (LOWER_SQUARED-offsets))))
    upper_error = float(np.max(np.abs(rhs[upper] - (UPPER_SQUARED-offsets))))
    if max(lower_error, upper_error) > 1e-12:
        raise ValueError('R030_ACTUAL_FULL_MODEL_VOLTAGE_RHS_DRIFT')
    proof = dict(UTC=now(), PASS=True, policy=POLICY, day=case.identity['day'], arm='B3', stage='M1',
        case_sha=case.case_sha, lower_pu=LOWER, upper_pu=UPPER,
        lower_squared=LOWER_SQUARED, upper_squared=UPPER_SQUARED,
        lower_rows=len(lower), upper_rows=len(upper), max_lower_rhs_error=lower_error,
        max_upper_rhs_error=upper_error, all_voltage_rows_checked=True,
        Q_operating_limit_kvar=250, new_M1_required=True)
    atomic(case.output/'R030_M1_FULL_VOLTAGE_ROWS.json', proof)
    return proof


def check_plan(case, payload, plan):
    from v44_recovery_r029.strict_recovery import voltage_report
    report = voltage_report(case, payload, plan)
    # Re-evaluate from the original coefficient and command arrays at this band.
    sites = list(map(str, payload['planning']['sites']))
    pcc = payload['planning']['PCC_P_kw']
    low = float('inf'); high = -float('inf'); count = 0
    for t, c in enumerate(case.coefficients):
        x = []
        for name in c.control_names:
            site = name.split('[', 1)[1][:-1]
            if name.startswith('aidc_load_kw'): x.append(float(pcc[t, sites.index(site)]))
            elif name.startswith('mess_p_kw'): x.append(float(plan['P_by_site'][site][t]))
            elif name.startswith('mess_q_kvar'): x.append(float(plan['Q_by_site'][site][t]))
            else: raise ValueError('R030_UNKNOWN_GRID_CONTROL')
        squared = np.asarray(c.voltage_constant+c.voltage_matrix.T@np.asarray(x), float)
        if not np.isfinite(squared).all() or np.any(squared < 0):
            raise ValueError('R030_NONFINITE_M1_PLAN_VOLTAGE')
        low = min(low, float(np.sqrt(squared).min()))
        high = max(high, float(np.sqrt(squared).max()))
        count += len(squared)
    proof = dict(UTC=now(), PASS=low >= LOWER-1e-7 and high <= UPPER+1e-7,
        policy=POLICY, lower_pu=LOWER, upper_pu=UPPER, min_voltage_pu=low,
        max_voltage_pu=high, evaluated_node_phase_slots=count, strict_original_voltage_report=report,
        commands_clipped=False, plan_sha=plan['plan_sha'], case_sha=case.case_sha)
    atomic(case.output/'R030_M1_PLAN_VOLTAGE_VALIDATION.json', proof)
    if not proof['PASS']: raise ValueError('R030_TIGHT_M1_PLAN_VOLTAGE_FAILED')
    return proof


@contextmanager
def install(authorize):
    from v44 import worker, q250_m4_v2
    from v44.checkpoints import seal_stage
    old_m, old_bind = worker.m_stage, q250_m4_v2.bind_case
    built = {}

    def bind(case, request):
        case = old_bind(case, request)
        if selected(request):
            check_rows(case)
            built[str(Path(request['root']))] = case
        return case

    @wraps(old_m)
    def m_stage(request, aidc):
        if not selected(request): return old_m(request, aidc)
        authorize(request)
        with scope(request):
            result = old_m(request, aidc)
            key = str(Path(request['root']))
            if key not in built: raise ValueError('R030_FRESH_M1_CASE_REQUIRED')
            case, payload = built[key], aidc
            if result.get('allow_downstream'):
                check_plan(case, payload, result['MESS_plan'])
                result['B3_M1_voltage_policy'] = dict(policy=POLICY, lower_pu=LOWER, upper_pu=UPPER,
                    amendment=request['B3_M1_voltage_amendment'],
                    rows=record(case.output/'R030_M1_FULL_VOLTAGE_ROWS.json'),
                    plan_validation=record(case.output/'R030_M1_PLAN_VOLTAGE_VALIDATION.json'))
                atomic(case.output/'RESULT.json', result)
                seal_stage(case.output, request, result)
            return result

    with patch.object(worker, 'm_stage', m_stage), patch.object(q250_m4_v2, 'bind_case', bind):
        yield
