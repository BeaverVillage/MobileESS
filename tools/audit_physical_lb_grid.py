"""Read-only coefficient/Forecast provenance replay for the frozen LB weights.

No solver or coefficient producer is imported. Stored FULL dyadic coefficients
remain mathematical authority; numerical NPZ replay separately reports assembly
rounding instead of replacing those coefficients with a recomputed expression.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
import hashlib
import json
import math
import re
import subprocess
import time
import traceback

import numpy as np
from scipy import sparse


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/v42_physical_global_lb_pilot'
SAVED = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
CERT = Path(r'D:\v42_svr11_may_20261011_16\models\2025-05-01\ELECTRICAL_CERTIFICATE.json')
BASE = '497609b46faa14ea7e32a9483a333ab32fd264ef'
UNITS = ('MESS01', 'MESS02', 'MESS03', 'MESS04')
F = Fraction


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def file_record(path):
    path = Path(path)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path.resolve()), bytes=path.stat().st_size, sha256=sha)


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def write(value):
    path = OUT / 'GRID_PROVENANCE_AUDIT.json'
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def audit():
    began = time.perf_counter()
    zero = read(OUT / 'NATIVE0.json')
    weights = read(OUT / 'WEIGHTS.json')
    case = read(SAVED / 'SCIENTIFIC_CASE_IDENTITY.json')
    inp = read(SAVED / 'INPUT_AND_SOURCE_IDENTITY.json')
    anchor_path = SAVED / 'FIXED_AIDC_ANCHOR.json'
    fixed_anchor = read(anchor_path)
    cert = read(CERT)
    coefficient_ref = cert['outputs']['planning_coefficients']
    coefficient_path = Path(coefficient_ref['path'])
    require(file_record(CERT) == inp['electrical_certificate'], 'ELECTRICAL_CERTIFICATE_IDENTITY_DRIFT')
    require(file_record(coefficient_path) == coefficient_ref, 'COEFFICIENT_NPZ_BYTES_DRIFT')
    require(file_record(anchor_path)['sha256'] == zero['source_records'][str(anchor_path)], 'FIXED_ANCHOR_FILE_SHA_DRIFT')
    require(canonical_sha(fixed_anchor) == case['anchor_sha'], 'FIXED_ANCHOR_CANONICAL_SHA_DRIFT')
    require(zero['base_commit'] == BASE and zero['case_sha'] == case['case_sha'] == inp['case_sha'], 'CURRENT_CASE_DRIFT')
    for name in ('FULL_A.npz', 'FULL_DATA.npz'):
        require(file_record(SAVED / name)['sha256'] == zero['source_records'][str(SAVED / name)], 'FULL_BYTES_DRIFT:' + name)

    # Source16 rebinds the unchanged forecast/PCC bytes and reference source
    # identity to this execution input folder. Its route-table record can still
    # name the original immutable input archive.
    input_folder = CERT.parents[2] / 'inputs/B2/2025-05-01'
    frozen = read(input_folder / 'B2_FIXED_AIDC.json')
    planning_path = input_folder / 'PLANNING_INPUT_BUNDLE.json'
    planning = read(planning_path)
    require(frozen['identity'] == fixed_anchor['independent_AIDC_identity'] == case['input_identity'] == inp['input_identity'], 'FIXED_AIDC_FORECAST_IDENTITY_DRIFT')
    require(file_record(planning_path)['sha256'] == frozen['identity']['input_SHA'], 'FORECAST_PLANNING_BUNDLE_SHA_DRIFT')
    require(file_record(frozen['physical']['path']) == frozen['physical'], 'FIXED_AIDC_PHYSICAL_BYTES_DRIFT')
    with np.load(frozen['physical']['path'], allow_pickle=False) as z:
        aidc_sites = list(map(str, z['sites']))
        pcc = z['PCC_P_kw'].copy()
    control_names = fixed_anchor['control_names']
    fixed = np.asarray(fixed_anchor['controls'], dtype=float)
    require(fixed.shape == (96, 60) and pcc.shape == (96, 12), 'CONTROL_OR_PCC_HORIZON_DRIFT')
    fixed_columns = [j for j, n in enumerate(control_names) if n.startswith('aidc_load_kw[')]
    require(fixed_columns == fixed_anchor['fixed_AIDC_control_columns'], 'FIXED_COLUMN_AXIS_DRIFT')
    for j, name in enumerate(control_names):
        site = name.split('[', 1)[1][:-1]
        if j in fixed_columns:
            require(np.array_equal(fixed[:, j], pcc[:, aidc_sites.index(site)]), 'FROZEN_PCC_CONTROL_DRIFT')
        else:
            require(np.array_equal(fixed[:, j], np.zeros(96)), 'MESS_CONTROL_FIXED_OFFSET_DRIFT')
    require(planning['day'] == cert['day'] == fixed_anchor['day'] == '2025-05-01', 'DAY_DRIFT')
    require(planning['forecast_inputs']['complete'] is True and planning['future_actual_arrival_IDs_present'] is False, 'FORECAST_AUTHORITY_DRIFT')

    with np.load(coefficient_path, allow_pickle=False) as z:
        fields = ('flow_p_constant', 'flow_q_constant', 'flow_p_matrix', 'flow_q_matrix', 'current_constant', 'current_matrix', 'branch_limits', 'anchor_control', 'branch_names', 'control_names')
        c = {k: z[k].copy() for k in fields}
    require(list(map(str, c['control_names'])) == control_names, 'COEFFICIENT_CONTROL_AXIS_DRIFT')
    A = sparse.load_npz(SAVED / 'FULL_A.npz').tocsr()
    with np.load(SAVED / 'FULL_DATA.npz', allow_pickle=False) as z:
        d = {k: z[k].copy() for k in ('names', 'row_names', 'rhs', 'sense')}
    prefixes = ('Pch[', 'Pdis[', 'Q[', 'injection_P[', 'injection_Q[', 'response_line_')
    cols = {str(n): j for j, n in enumerate(d['names']) if str(n) == 'rho_max' or str(n).startswith(prefixes)}
    row_targets = {f'response_line_{family}_binding[{t},{k}]'
        for row in weights['rows'] for t, k, _ in [tuple(map(int, re.fullmatch(r'line_thermal_face\[(\d+),(\d+),(\d+)\]', row['name']).groups()))]
        for family in ('P', 'Q', 'correction')}
    helper_rows = {str(n): i for i, n in enumerate(d['row_names']) if str(n) in row_targets}
    injection_rows = {}
    for i, name in enumerate(d['row_names']):
        if str(name) not in ('injection_P_binding', 'injection_Q_binding'):
            continue
        a, b = A.indptr[i:i + 2]
        pivot = [int(j) for j, w in zip(A.indices[a:b], A.data[a:b]) if w == 1. and str(d['names'][j]).startswith(('injection_P[', 'injection_Q['))]
        require(len(pivot) == 1 and pivot[0] not in injection_rows, 'INJECTION_PIVOT_DRIFT')
        injection_rows[pivot[0]] = i

    def row_values(i):
        a, b = A.indptr[i:i + 2]
        return {int(j): float(w) for j, w in zip(A.indices[a:b], A.data[a:b])}

    cosine = np.cos(2 * np.pi * np.arange(16) / 16)
    sine = np.sin(2 * np.pi * np.arange(16) / 16)
    results = []
    for row in weights['rows']:
        match = re.fullmatch(r'line_thermal_face\[(\d+),(\d+),(\d+)\]', row['name'])
        require(match is not None, 'WEIGHT_ROW_AXIS')
        t, k, facet = map(int, match.groups())
        i = row['row']
        require(str(d['row_names'][i]) == row['name'] and d['sense'][i] == '<', 'ORIGINAL_ROW_DRIFT')
        ap = np.asarray(c['branch_limits'][t]) * math.cos(math.pi / 16)
        wp_all, wq_all = c['flow_p_matrix'][t], c['flow_q_matrix'][t]
        linearization_anchor = c['anchor_control'][t]
        pa = c['flow_p_constant'][t] + wp_all @ linearization_anchor
        qa = c['flow_q_constant'][t] + wq_all @ linearization_anchor
        raw = (pa[:, None] * cosine + qa[:, None] * sine) / ap[:, None]
        active = np.argmax(raw, axis=1)
        gradient = (cosine[active, None] * wp_all + sine[active, None] * wq_all) / ap[:, None]
        correction_all = c['current_matrix'][t].T - gradient
        bias_all = c['current_constant'][t] + c['current_matrix'][t].T @ linearization_anchor - np.max(raw, axis=1)
        wp, wq, correction = wp_all[k], wq_all[k], correction_all[k]
        fixed_p = sum(float(wp[j]) * float(fixed[t, j]) for j in fixed_columns)
        fixed_q = sum(float(wq[j]) * float(fixed[t, j]) for j in fixed_columns)
        correction_anchor = float(-correction @ linearization_anchor)
        fixed_correction = sum(float(correction[j]) * float(fixed[t, j]) for j in fixed_columns)
        expected_constants = {'P': float(c['flow_p_constant'][t, k]) + fixed_p, 'Q': float(c['flow_q_constant'][t, k]) + fixed_q, 'correction': correction_anchor + fixed_correction}
        expected_responses = {'P': wp, 'Q': wq, 'correction': correction}
        original = row_values(i)
        expected_original = {cols[f'response_line_P[{t},{k}]']: float(cosine[facet] / ap[k]), cols[f'response_line_Q[{t},{k}]']: float(sine[facet] / ap[k]), cols[f'response_line_correction[{t},{k}]']: 1., cols['rho_max']: -1.}
        require(set(original) == set(expected_original), 'ORIGINAL_THERMAL_HELPER_SUPPORT_DRIFT')
        response_records = {}
        injection_coefficients = defaultdict(F)
        exact_b = -F(float(d['rhs'][i]))
        helper_residual = 0.
        for family in ('P', 'Q', 'correction'):
            j = cols[f'response_line_{family}[{t},{k}]']
            h = helper_rows[f'response_line_{family}_binding[{t},{k}]']
            stored = row_values(h)
            require(d['sense'][h] == '=' and stored.pop(j) == 1., 'RESPONSE_BINDING_PIVOT_DRIFT')
            expected = {}
            for q, name in enumerate(control_names):
                if q in fixed_columns or expected_responses[family][q] == 0:
                    continue
                site = name.split('[', 1)[1][:-1]
                prefix = 'P' if name.startswith('mess_p_kw[') else 'Q'
                expected[cols[f'injection_{prefix}[{site},{t}]']] = -float(expected_responses[family][q])
            require(set(stored) == set(expected), 'RESPONSE_BINDING_CONTROL_SUPPORT_DRIFT')
            coeff_error = max((abs(stored[q] - expected[q]) for q in stored), default=0.)
            const_error = abs(float(d['rhs'][h]) - expected_constants[family])
            helper_residual = max(helper_residual, coeff_error, const_error)
            exact_b += F(original[j]) * F(float(d['rhs'][h]))
            for q, value in stored.items():
                injection_coefficients[q] -= F(original[j]) * F(value)
            response_records[family] = dict(row=h, name=str(d['row_names'][h]), original_RHS=float(d['rhs'][h]), NPZ_expected_constant=expected_constants[family], maximum_coefficient_residual=coeff_error, constant_residual=const_error)
        physical = defaultdict(F)
        injection_checks = 0
        for j, value in injection_coefficients.items():
            h = injection_rows[j]
            stored = row_values(h)
            require(d['sense'][h] == '=' and stored.pop(j) == 1. and float(d['rhs'][h]) == 0., 'INJECTION_BINDING_DRIFT')
            name = str(d['names'][j])
            prefix = 'P' if name.startswith('injection_P[') else 'Q'
            site, slot = name.split('[', 1)[1][:-1].split(',')
            require(int(slot) == t, 'INJECTION_TIME_DRIFT')
            expected = {}
            for unit in UNITS:
                families = (('Pch', 1.), ('Pdis', -1.)) if prefix == 'P' else (('Q', -1.),)
                for family, sign in families:
                    q = cols.get(f'{family}[{unit},{site},{t}]')
                    if q is not None:
                        expected[q] = sign
            require(stored == expected, 'PHYSICAL_INJECTION_SIGN_OR_OWNERSHIP_DRIFT')
            for q, coefficient in stored.items():
                physical[q] -= value * F(coefficient)
            injection_checks += 1
        physical = {j: value for j, value in physical.items() if value}
        require(exact_b == F(row['b']) and physical == {int(j): F(v) for j, v in row['terms'].items()}, 'EXACT_STORED_ROW_WEIGHTS_PROJECTION_DRIFT')
        expected_b = (cosine[facet] * expected_constants['P'] + sine[facet] * expected_constants['Q']) / ap[k] + expected_constants['correction'] + bias_all[k]
        expected_all = (cosine[facet] * wp + sine[facet] * wq) / ap[k] + correction
        groups = defaultdict(dict)
        physical_residual = 0.
        for j, value in physical.items():
            family, unit, site, slot = re.fullmatch(r'(Pch|Pdis|Q)\[([^,]+),([^,]+),(\d+)\]', str(d['names'][j])).groups()
            control = f'mess_q_kvar[{site}]' if family == 'Q' else f'mess_p_kw[{site}]'
            expected = float(expected_all[control_names.index(control)]) * (-1. if family == 'Pch' else 1.)
            error = abs(float(value) - expected)
            physical_residual = max(physical_residual, error)
            groups[unit, site, int(slot)][family] = dict(FULL_column=j, exact_stored_fraction=str(value), stored_float=float(value), NPZ_expected_coefficient=expected, numeric_residual=error)
        thermal_residual = max(abs(original[j] - expected_original[j]) for j in original)
        rhs_residual = abs(float(d['rhs'][i]) + float(bias_all[k]))
        b_residual = abs(float(exact_b) - float(expected_b))
        max_residual = max(thermal_residual, rhs_residual, helper_residual, physical_residual, b_residual)
        require(max_residual <= 1e-12, 'NPZ_TO_STORED_ASSEMBLY_RESIDUAL_EXCEEDED')
        results.append(dict(row=i, name=row['name'], slot=t, interval_from_midnight_minutes=15*t, branch_index=k, branch_name=str(c['branch_names'][k]), facet=facet, angle_degrees=22.5*facet, weight=row['weight'], active_linearization_facet=int(active[k]), branch_limit=float(c['branch_limits'][t,k]), ap=float(ap[k]), bias=float(bias_all[k]), original_RHS=float(d['rhs'][i]), original_thermal_coefficients={str(d['names'][j]): v for j,v in original.items()}, response_bindings=response_records, flow_P_constant=float(c['flow_p_constant'][t,k]), flow_Q_constant=float(c['flow_q_constant'][t,k]), fixed_AIDC_flow_P_contribution=fixed_p, fixed_AIDC_flow_Q_contribution=fixed_q, correction_anchor_term=correction_anchor, fixed_AIDC_correction_contribution=fixed_correction, source_exact_b=str(exact_b), NPZ_expected_b=float(expected_b), b_numeric_residual=b_residual, injection_binding_rows_checked=injection_checks, exact_original_projection_equals_WEIGHTS=True, maximum_numeric_residual=max_residual, vehicle_site_time_coefficients=[dict(unit=u,site=s,slot=tt,coefficients=coefficients) for (u,s,tt),coefficients in sorted(groups.items())]))

    formula_sources = {}
    for relative in ('v42_m1_sparse/grid.py', 'v42_may_campaign_native90/m_model.py'):
        raw = subprocess.run(['git', '-C', str(ROOT), 'show', BASE + ':' + relative], capture_output=True, check=True).stdout
        frozen_source = Path(r'D:\v42_svr11_epoch18r_20261011') / relative
        record = file_record(frozen_source)
        require(record['sha256'] == hashlib.sha256(raw).hexdigest(), 'FROZEN_SOURCE_FORMULA_DRIFT:' + relative)
        checkout_raw = (ROOT / relative).read_bytes()
        require(checkout_raw.replace(b'\r\n', b'\n') == raw.replace(b'\r\n', b'\n'), 'CHECKOUT_SOURCE_FORMULA_DRIFT:' + relative)
        formula_sources[relative] = dict(frozen_source=record, checkout_source=file_record(ROOT / relative), source18r_git_blob_SHA256=hashlib.sha256(raw).hexdigest(), checkout_equals_Source18r_after_CRLF_normalization=True, checkout_EOL_only_difference=checkout_raw != raw)
    forecasts = planning['forecast_inputs']
    aemo = forecasts['AEMO']
    cc4 = forecasts['current_CC4']
    result = dict(schema='V42_PHYSICAL_GLOBAL_LB_GRID_COEFFICIENT_PROVENANCE_V1', PASS=True, observed_UTC=datetime.now(timezone.utc).isoformat(), observed_Asia_Seoul=datetime.now(timezone(timedelta(hours=9))).isoformat(), case_sha=case['case_sha'], source18r=BASE, Native_optimize_calls=0, model_builds=0, coefficient_producer_calls=0, Actual_inputs_read=0, original_files_mutated=0, records={name:file_record(path) for name,path in [('weights',OUT/'WEIGHTS.json'),('electrical_certificate',CERT),('planning_coefficients',coefficient_path),('fixed_AIDC_anchor',anchor_path),('B2_FIXED_AIDC',input_folder/'B2_FIXED_AIDC.json'),('PLANNING_PHYSICAL',frozen['physical']['path']),('PLANNING_INPUT_BUNDLE',planning_path)]}, source_formulas=formula_sources, anchor_canonical_sha=case['anchor_sha'], forecast_identity=dict(input_SHA=frozen['identity']['input_SHA'],reference_SHA=frozen['identity']['reference_SHA'],job_ids_SHA=frozen['identity']['job_ids_SHA'],rule=frozen['identity']['rule'],planning_issue_time=planning['issue_time'],AEMO={key:aemo[key] for key in ('cutoff_fixed_aest','demand_issue','demand_source_sha256','pv_issue','pv_source_sha256')},CC4={key:cc4[key] for key in ('target_day','issue_time','prediction_index')}), fixed_AIDC_PCC_controls_exact=True, fixed_AIDC_controls_checked=96*len(fixed_columns), fixed_AIDC_sites=aidc_sites, coefficient_linearization_anchor_is_distinct_from_frozen_B2_controls=True, fixed_term_is_forecast_plus_grid_constants_plus_correction=True, original_formula='ap=branch_limits*cos(pi/16); raw=(flowP(anchor)*cos+flowQ(anchor)*sin)/ap; active=argmax(raw); grad=(cos(active)*flowP_matrix+sin(active)*flowQ_matrix)/ap; correction=current_matrix.T-grad; bias=current_constant+current_matrix.T@coefficient_anchor-max(raw); b=(cos(f)*fixed_responseP+sin(f)*fixed_responseQ)/ap+fixed_correction+bias; injection=(cos(f)*flowP_matrix+sin(f)*flowQ_matrix)/ap+correction', stored_FULL_and_exact_WEIGHTS_are_authority=True, maximum_numeric_assembly_residual=max(r['maximum_numeric_residual'] for r in results), numeric_provenance_tolerance=1e-12, numerical_replay_is_not_a_new_mathematical_region=True, selected_rows=results, wall_seconds=time.perf_counter()-began)
    write(result)
    print(json.dumps(dict(PASS=True,selected_rows=len(results),maximum_numeric_assembly_residual=result['maximum_numeric_assembly_residual'],wall_seconds=result['wall_seconds'],Native_optimize_calls=0),indent=2))


if __name__ == '__main__':
    try:
        audit()
    except BaseException as error:
        write(dict(schema='V42_PHYSICAL_GLOBAL_LB_GRID_COEFFICIENT_PROVENANCE_V1',PASS=False,error=repr(error),traceback=traceback.format_exc(),Native_optimize_calls=0,model_builds=0,coefficient_producer_calls=0,original_files_mutated=0))
        raise
