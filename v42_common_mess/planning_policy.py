"""Explicit M-only Planning voltage experiment, before original transport.

Normal builds keep their existing contract. A/Actual voltage authorities and
the original coefficients, objective, MESS domain and replay code are retained.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
import re

import numpy as np
from scipy import sparse
from .storage import write, record

POLICY = 'V42_PLANNING_VMAX_1048_DIAGNOSTIC_V1'
_active = ContextVar('common_M_Planning_voltage_experiment', default=None)


def specification():
    # The user supplied exact decimal squares. Binary exponentiation of 1.048
    # produces the adjacent float and is deliberately not the conversion here.
    return dict(version=POLICY, diagnostic_only=True, Planning_lower_pu=.950,
        Planning_upper_pu=1.048, Planning_lower_squared=float(Decimal('0.950')**2),
        Planning_upper_squared=float(Decimal('1.048')**2),
        exact_decimal_lower_squared='0.902500', exact_decimal_upper_squared='1.098304',
        baseline_Planning_upper_squared=1.1025, voltage_coordinate='SQUARED_PU',
        Actual_lower_pu=.950, Actual_upper_pu=1.050,
        stages=['B2_M','M1','M2'], A1_A2_policy_changed=False,
        post_observed_May01_diagnostic=True, independent_holdout_claim=False)


@contextmanager
def scope(policy, *, baseline_output=None):
    if policy != POLICY:
        raise ValueError('COMMON_M_UNKNOWN_PLANNING_VOLTAGE_POLICY')
    token = _active.set(dict(policy=specification(),
        baseline_output=None if baseline_output is None else str(Path(baseline_output).resolve())))
    try:
        yield specification()
    finally:
        _active.reset(token)


def current():
    state = _active.get()
    return None if state is None else dict(state['policy'])


@contextmanager
def _construction_scope(stage):
    """The original GridAuthority validates this same stage-specific policy."""
    import v42_native.voltage as voltage
    original = voltage.voltage_for
    selected = voltage.Stage.M1 if stage == 'B2_M' else voltage.Stage(stage)
    def routed(requested_stage):
        policy = current()
        if policy is not None and requested_stage == selected:
            return voltage.Voltage(POLICY, policy['Planning_lower_pu'], policy['Planning_upper_pu'],
                policy['Planning_lower_squared'], policy['Planning_upper_squared'])
        return original(requested_stage)
    with patch.object(voltage, 'voltage_for', routed):
        yield


def _equal(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def _same_csr(A, B):
    A, B = A.tocsr(), B.tocsr()
    return A.shape == B.shape and all(_equal(getattr(A,k), getattr(B,k)) for k in ('indptr','indices','data'))


def _load(path):
    with np.load(path, allow_pickle=False) as z:
        return {k:z[k].copy() for k in z.files}


def _digest(value):
    from v42_pr134_b1.common import digest
    return digest(value)


def _full_voltage_audit(case, policy):
    A, d = case.original_A.tocsr(), case.original_d
    names = {str(name):j for j,name in enumerate(d['names'])}
    coefficients = case.coefficients
    expected = {(kind,t,n) for t,c in enumerate(coefficients)
                for n in range(len(c.voltage_constant)) for kind in ('lower','upper')}
    observed = set()
    max_rhs_error = 0.
    counts = dict(lower=0, upper=0)
    row_indices = {'lower':[], 'upper':[]}
    for i, name in enumerate(d['row_names']):
        match = re.fullmatch(r'voltage_(lower|upper)\[(\d+),(\d+)\]', str(name))
        if not match:
            continue
        kind,t,n = match[1],int(match[2]),int(match[3])
        if (kind,t,n) not in expected or (kind,t,n) in observed:
            raise ValueError('COMMON_M_POLICY_VOLTAGE_ROW_AXIS_DRIFT')
        observed.add((kind,t,n)); counts[kind] += 1; row_indices[kind].append(i)
        c = coefficients[t]
        expression_constant = float(c.voltage_constant[n])
        terms = {}
        for j, control in enumerate(c.control_names):
            weight = float(c.voltage_matrix[j,n])
            if control.startswith('aidc_load_kw['):
                expression_constant += weight * float(case.anchor['controls'][t][j])
            elif control.startswith(('mess_p_kw[','mess_q_kvar[')):
                if weight:
                    site = control.split('[',1)[1][:-1]
                    family = 'injection_P' if control.startswith('mess_p_kw[') else 'injection_Q'
                    terms[names[f'{family}[{site},{t}]']] = weight
            else:
                raise ValueError('COMMON_M_POLICY_UNKNOWN_CONTROL_FAMILY')
        a,b = A.indptr[i:i+2]
        actual = dict(zip(map(int,A.indices[a:b]), map(float,A.data[a:b])))
        limit = policy['Planning_'+kind+'_squared']
        error = abs(float(d['rhs'][i]) - (limit-expression_constant))
        max_rhs_error = max(max_rhs_error,error)
        if actual != terms or d['sense'][i] != ('>' if kind == 'lower' else '<') or error > 1e-12:
            raise ValueError('COMMON_M_POLICY_FULL_NATIVE_VOLTAGE_READBACK_DRIFT')
    if observed != expected or not counts['upper']:
        raise ValueError('COMMON_M_POLICY_ALL_VOLTAGE_ROWS_REQUIRED')
    return dict(PASS=True, upper_rows=counts['upper'], lower_rows=counts['lower'],
        original_coefficient_terms_exact=True, upper_squared=policy['Planning_upper_squared'],
        lower_squared=policy['Planning_lower_squared'], maximum_original_affine_RHS_arithmetic_difference=max_rhs_error,
        arithmetic_comparison_tolerance=1e-12, native_optimize_calls=0,
        Native_readback_source='Original FULL builder calls Gurobi getA/getAttr RHS before Compact/Presolve; common Native model additionally reads back exact current C3A coefficients/RHS on every trial.',
        row_indices=row_indices)


def compare_baseline(case, baseline_output, policy=None, *, strict_validator=None):
    """Independent same-input FULL comparison and old strict point rejection."""
    import json
    policy = specification() if policy is None else policy
    root = Path(baseline_output).resolve()
    old_A = sparse.load_npz(root/'FULL_A.npz').tocsr()
    old = _load(root/'FULL_DATA.npz')
    current = case.original_d
    upper = np.array([bool(re.fullmatch(r'voltage_upper\[\d+,\d+\]',str(n))) for n in old['row_names']])
    if (set(old) != set(current) or not _same_csr(old_A,case.original_A)
            or not upper.any() or len(upper) != len(current['rhs'])):
        raise ValueError('COMMON_M_POLICY_BASELINE_FULL_COEFFICIENT_AXIS_DRIFT')
    metadata = {key:_equal(current[key], old[key]) for key in old if key != 'rhs'}
    same_other_rhs = _equal(current['rhs'][~upper],old['rhs'][~upper])
    expected_shift = policy['Planning_upper_squared']-policy['baseline_Planning_upper_squared']
    max_shift_error = float(np.max(abs((current['rhs'][upper]-old['rhs'][upper])-expected_shift)))
    if not all(metadata.values()) or not same_other_rhs or max_shift_error > 1e-12:
        raise ValueError('COMMON_M_POLICY_BASELINE_ONLY_UPPER_RHS_MAY_CHANGE')
    # Recover the preserved point in its own old axes. It is diagnostic evidence
    # only and is never supplied as the new case's MIP start or a bound.
    point_path=root/'BEST_STRICT_UB_POINT.npz'
    certificate=json.loads((root/'BEST_STRICT_UB_CERTIFICATE.json').read_text(encoding='utf-8-sig'))
    if (certificate.get('PASS') is not True
            or certificate.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is not True
            or record(point_path)['sha256'] != certificate['point_file_sha256']):
        raise ValueError('COMMON_M_POLICY_BASELINE_STRICT_PACKET_REQUIRED')
    raw=_load(point_path)['point']; axes=_load(root/'CURRENT_C2_AXES.npz')
    # Every eliminated column is identified explicitly by its old proof packet.
    aliases=json.loads((root/'CURRENT_C2_ALIASES.json').read_text(encoding='utf-8-sig'))
    n=max([len(old['names'])]+[int(j)+1 for j in axes['columns']]+[int(a['column'])+1 for a in aliases])
    lifted=np.zeros(n); lifted[axes['columns']]=raw
    for a in reversed(aliases):
        lifted[a['column']]=a['constant']+sum(w*lifted[int(j)] for j,w in a['terms'].items())
    old_full=lifted[:len(old['names'])]
    violation=np.asarray(case.original_A[upper]@old_full-current['rhs'][upper])
    old_violation=np.asarray(old_A[upper]@old_full-old['rhs'][upper])
    if strict_validator is None:
        from v42_m1_hybrid.final_verify import _strict_ub
        strict_validator = _strict_ub
    replay_path=case.output/'DIAGNOSTIC_OLD1050_POINT_IN_NEW1048_AXES.npz'
    new_axis_point=case.presolve.forward(case.compact.forward(old_full))
    np.savez_compressed(replay_path, point=np.asarray(new_axis_point,dtype=np.float64))
    try:
        strict=strict_validator(case,replay_path,{})
        replay=dict(PASS=bool(strict.get('PASS')), status='INDEPENDENT_NEW_FULL_REPLAY', certificate=strict)
    except ValueError as error:
        replay=dict(PASS=False, status='INDEPENDENT_NEW_FULL_REPLAY_REJECTED', reason=str(error))
    if violation.max()>1e-8 and replay['PASS']:
        raise ValueError('COMMON_M_POLICY_OLD_POINT_STRICT_REJECTION_DRIFT')
    return dict(PASS=True, full_CSR_coefficients_byte_equal=True, all_column_and_row_metadata_byte_equal=metadata,
        objective_byte_equal=metadata['objective'] and metadata['constant'],
        MESS_integer_and_continuous_decision_domain_byte_equal=all(metadata[k] for k in ('names','lower','upper','types')),
        all_non_voltage_upper_RHS_byte_equal=same_other_rhs, changed_upper_rows=int(upper.sum()),
        expected_upper_RHS_shift_squared_pu=expected_shift, maximum_upper_RHS_shift_arithmetic_error=max_shift_error,
        baseline_point_max_voltage_upper_violation_squared_pu=float(old_violation.max()),
        old_strict_point_under_new_FULL_max_voltage_upper_violation_squared_pu=float(violation.max()),
        old_strict_point_rejected_under_new_FULL=bool(violation.max()>1e-8),
        independent_new_case_strict_replay=replay, diagnostic_old_point_packet=record(replay_path),
        rejected_old_point_used_as_start=False, baseline_reads_are_diagnostic_comparison_only=True,
        baseline_files=[record(root/name) for name in ('FULL_A.npz','FULL_DATA.npz','BEST_STRICT_UB_POINT.npz',
            'BEST_STRICT_UB_CERTIFICATE.json','CURRENT_C2_AXES.npz','CURRENT_C2_ALIASES.json')],
        Native_optimize_calls=0, repairs=0, clipping=0, rounding=0)


def build_case(builder, payload, request, progress=None, *, stage, strict_validator=None):
    """One policy-generating interface used by B2 M and B3 M1/M2."""
    policy=current()
    if policy is None:
        return builder(payload,request,progress)
    if stage not in ('B2_M','M1','M2'):
        raise ValueError('COMMON_M_PLANNING_POLICY_CANNOT_CHANGE_A_OR_ACTUAL')
    with _construction_scope(stage):
        case=builder(payload,request,progress)
    audit=_full_voltage_audit(case,policy)
    audit.pop('row_indices')
    full_model_sha=_digest(dict(matrix_sha=case.identity['original_matrix_sha'],
        domain_sha=case.identity['original_domain_sha'], planning_voltage_policy=policy))
    selected_model_sha=_digest(dict(matrix_sha=case.identity['selected_matrix_sha'],
        domain_sha=case.identity['selected_domain_sha'], planning_voltage_policy=policy))
    case.identity.update(planning_voltage_policy=policy, full_model_sha=full_model_sha,
        selected_model_sha=selected_model_sha)
    case.case_sha=_digest(case.identity)
    state=_active.get()
    if state['baseline_output'] is not None:
        audit['baseline_comparison']=compare_baseline(case,state['baseline_output'],policy,
            strict_validator=strict_validator)
    path=case.output/'VMAX1048_MODEL_POLICY_AUDIT.json'
    write(path,dict(schema='V42_VMAX1048_COMMON_M_MODEL_POLICY_AUDIT_V1', PASS=True, stage=stage,
        policy=policy, scientific_case_sha=case.case_sha, original_matrix_sha=case.identity['original_matrix_sha'],
        original_domain_sha=case.identity['original_domain_sha'], selected_matrix_sha=case.identity['selected_matrix_sha'],
        selected_domain_sha=case.identity['selected_domain_sha'], full_model_sha=full_model_sha,
        selected_model_sha=selected_model_sha, original_domain_equivalence=case.identity['transport'],
        model_policy_source=record(Path(__file__)), audit=audit,
        feasible_set_strengthened=True, original_1050_feasible_set_equivalence_claimed=False,
        Native_optimizer_calls=0, source_voltage_constants_changed=False,
        Original_A1_A2_Actual_policy_changed=False))
    case.planning_policy_audit=record(path)
    write(case.output/'SCIENTIFIC_CASE_IDENTITY.json',dict(case_sha=case.case_sha,**case.identity))
    # This source packet also contains case_sha and must describe the new case.
    input_path=case.output/'INPUT_AND_SOURCE_IDENTITY.json'
    if input_path.is_file():
        import json
        value=json.loads(input_path.read_text(encoding='utf-8-sig'))
        value.update(case_sha=case.case_sha, planning_voltage_policy=policy, full_model_sha=full_model_sha)
        write(input_path,value)
    return case
