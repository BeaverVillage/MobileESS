"""Read-only separation of frozen FULL security rows; never imports Gurobi.

Sparse binary64 evaluation is a search aid. Each admitted row is eliminated,
transported and evaluated with Fraction arithmetic before outward conversion.
"""
from collections import Counter, defaultdict
from fractions import Fraction as F
from functools import lru_cache
from pathlib import Path
import argparse
import gc
import hashlib
import json
import math
import re
import sys
import time

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
SAVED = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
COEFFICIENTS = Path(r'D:\v42_svr11_may_20261011_16\models\2025-05-01\COEFFICIENTS.npz')
SOURCE = '497609b46faa14ea7e32a9483a333ab32fd264ef'
CASE = '34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
FAMILIES = ('line_thermal_face', 'transformer_kVA', 'voltage_upper', 'voltage_lower', 'NormalAmps')
QUOTAS = dict(line_thermal_face=10, transformer_kVA=2, voltage_upper=2, voltage_lower=2, NormalAmps=0)
EPS = np.finfo(float).eps


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load_data(path):
    with np.load(path, allow_pickle=False) as z:
        return {key: z[key] for key in z.files}


def upward(value):
    native = float(value)
    require(math.isfinite(native), 'NONFINITE_RHS')
    return float(np.nextafter(native, np.inf)) if F(native) < value else native


def row_sha(A, d, i):
    a, b = A.indptr[i:i + 2]
    payload = dict(original_row=int(i), name=str(d['row_names'][i]), sense=str(d['sense'][i]),
                   rhs_hex=float(d['rhs'][i]).hex(),
                   terms=[[int(j), float(w).hex()] for j, w in zip(A.indices[a:b], A.data[a:b])])
    return canonical_sha(payload)


def float_sum_error(weights, values, errors, constant=0.):
    # Safe forward-error search envelope, including multiplication, accumulation,
    # inherited alias/helper errors and final subtraction. Exact adoption follows.
    count = len(weights) + 4
    gamma = count * EPS / (1 - count * EPS)
    magnitude = abs(float(constant)) + sum(abs(float(w) * float(x)) for w, x in zip(weights, values))
    inherited = sum(abs(float(w)) * float(e) for w, e in zip(weights, errors))
    return float(np.nextafter(4 * gamma * magnitude + 2 * inherited, np.inf))


def restore_original(joint, joint_columns, full_d):
    axes = load_data(SAVED / 'CURRENT_C2_AXES.npz')['columns']
    aliases = read(SAVED / 'CURRENT_C2_ALIASES.json')
    require(len(joint) == len(joint_columns), 'JOINT_AXIS_LENGTH')
    size = max(int(axes.max()), max(int(p['column']) for p in aliases)) + 1
    compact, errors = np.zeros(size), np.zeros(size)
    compact[axes[joint_columns]] = joint
    for plan in reversed(aliases):
        ids = [int(j) for j in plan['terms']]
        weights = [float(w) for w in plan['terms'].values()]
        value = float(plan['constant']) + sum(w * compact[j] for j, w in zip(ids, weights))
        errors[int(plan['column'])] = float_sum_error(weights, compact[ids], errors[ids], plan['constant'])
        compact[int(plan['column'])] = value
    full = compact[:len(full_d['names'])].copy()
    full_errors = errors[:len(full_d['names'])].copy()
    physical = np.array([str(n).split('[', 1)[0] in {'arc', 'charge_mode', 'SOC', 'Pch', 'Pdis', 'Q'}
                         for n in full_d['names']])
    binary = physical & (full_d['types'] != 'C')
    integer_error = float(np.max(abs(full[binary] - np.rint(full[binary]))))
    require(integer_error <= 1e-8, 'ORIGINAL_INTEGER_PATTERN_DRIFT')
    require(np.isfinite(full[physical]).all(), 'PHYSICAL_NONFINITE')
    return full, full_errors, axes, aliases, integer_error


class Geometry:
    def __init__(self, A, d):
        self.A, self.d = A, d
        self.definitions = {}
        self.cache = {}
        for i, name in enumerate(d['row_names']):
            family = str(name).split('[', 1)[0]
            if not (family.startswith(('response_', 'injection_')) and family.endswith('_binding')):
                continue
            require(d['sense'][i] == '=', 'HELPER_NOT_EQUALITY')
            a, b = A.indptr[i:i + 2]
            pivots = [int(j) for j, w in zip(A.indices[a:b], A.data[a:b])
                      if w == 1. and str(d['names'][j]).split('[', 1)[0] + '_binding' == family]
            require(len(pivots) == 1 and pivots[0] not in self.definitions, 'HELPER_PIVOT_AMBIGUOUS')
            self.definitions[pivots[0]] = i

    def numerical(self, x, errors):
        done, visiting = set(), set()
        def value(j):
            if j not in self.definitions or j in done:
                return x[j]
            require(j not in visiting, 'HELPER_CYCLE')
            visiting.add(j)
            i = self.definitions[j]
            a, b = self.A.indptr[i:i + 2]
            ids = [int(k) for k in self.A.indices[a:b] if k != j]
            weights = [float(w) for k, w in zip(self.A.indices[a:b], self.A.data[a:b]) if k != j]
            for k in ids:
                value(k)
            x[j] = float(self.d['rhs'][i]) - sum(w * x[k] for k, w in zip(ids, weights))
            errors[j] = float_sum_error(weights, x[ids], errors[ids], self.d['rhs'][i])
            done.add(j); visiting.remove(j)
            return x[j]
        for j in self.definitions:
            value(j)

    def expand(self, j, used, visiting=None):
        if j not in self.definitions:
            return F(0), {j: F(1)}
        used.add(self.definitions[j])
        if j in self.cache:
            constant, terms, dependency_rows = self.cache[j]
            used.update(dependency_rows)
            return constant, terms
        visiting = set() if visiting is None else visiting
        require(j not in visiting, 'EXACT_HELPER_CYCLE')
        visiting.add(j)
        i = self.definitions[j]
        a, b = self.A.indptr[i:i + 2]
        constant = F(float(self.d['rhs'][i]))
        terms = defaultdict(F)
        dependency = {i}
        for k, coefficient in zip(self.A.indices[a:b], self.A.data[a:b]):
            k = int(k)
            if k == j:
                continue
            c0, pieces = self.expand(k, dependency, visiting)
            factor = -F(float(coefficient))
            constant += factor * c0
            for q, value in pieces.items():
                terms[q] += factor * value
        visiting.remove(j)
        answer = {q: value for q, value in terms.items() if value}
        self.cache[j] = constant, answer, dependency
        used.update(dependency)
        return constant, answer

    def project(self, i):
        require(self.d['sense'][i] in ('<', '>'), 'SECURITY_NON_INEQUALITY')
        sign = F(1) if self.d['sense'][i] == '<' else F(-1)
        a, b = self.A.indptr[i:i + 2]
        constant, terms, used = F(0), defaultdict(F), set()
        for j, coefficient in zip(self.A.indices[a:b], self.A.data[a:b]):
            c0, pieces = self.expand(int(j), used)
            factor = sign * F(float(coefficient))
            constant += factor * c0
            for q, value in pieces.items():
                terms[q] += factor * value
        rhs = sign * F(float(self.d['rhs'][i])) - constant
        return {j: c for j, c in terms.items() if c}, rhs, constant, used


def metadata(name, coefficients):
    family = name.split('[', 1)[0]
    body = name.split('[', 1)[1][:-1].split(',')
    slot, index, facet = int(body[0]), None, None
    if family == 'NormalAmps':
        asset, phase = body[1].rsplit('::', 1)
        return dict(family=family, slot=slot, index=None, asset=asset, phase=phase,
                    facet=None, unit='current_loading_pu', scale=1., normalization_basis='original normalized current rating=1')
    index = int(body[1])
    if family.startswith('voltage_'):
        asset, phase = str(coefficients['node_names'][index]).rsplit('.', 1)
        return dict(family=family, slot=slot, index=index, asset=asset, phase=phase,
                    facet=None, unit='voltage_squared_pu', scale=1., normalization_basis='1 pu squared voltage; ranked only within family')
    asset, phase = str(coefficients['branch_names'][index]).rsplit('::', 1)
    facet = int(body[2])
    if family == 'transformer_kVA':
        rating = float(coefficients['transformer_ratings'][index])
        require(math.isfinite(rating) and rating > 0, 'TRANSFORMER_RATING_MISSING')
        scale = rating * math.cos(math.pi / 16)
        unit, basis = 'kVA', 'original transformer nameplate kVA*cos(pi/16) facet rating'
    else:
        scale, unit, basis = 1., 'thermal_loading_pu', 'original line utilization normalized rating=1'
    return dict(family=family, slot=slot, index=index, asset=asset, phase=phase,
                facet=facet, unit=unit, scale=scale, normalization_basis=basis)


def existing_rows(path):
    value = read(path)
    if isinstance(value, dict):
        value = value.get('original_rows', value.get('rows'))
    return {int(v.get('original_row', v.get('row'))) if isinstance(v, dict) else int(v) for v in value}


def separate(previous, incumbent, existing_ids, out):
    started = time.perf_counter()
    previous, incumbent, out = Path(previous), Path(incumbent), Path(out)
    require(not (out / 'SEPARATION.json').exists(), 'SEPARATION_ALREADY_SEALED')
    out.mkdir(parents=True, exist_ok=True)
    A = sparse.load_npz(SAVED / 'FULL_A.npz').tocsr()
    d = load_data(SAVED / 'FULL_DATA.npz')
    from v42_m1_hybrid.blocks import matrix_sha
    from v42_may_campaign_native90.m_model import _domain_sha
    identity = read(SAVED / 'SCIENTIFIC_CASE_IDENTITY.json')
    require(identity['case_sha'] == CASE and matrix_sha(A) == identity['original_matrix_sha'], 'FULL_MATRIX_IDENTITY')
    require(_domain_sha(d) == identity['original_domain_sha'], 'FULL_DOMAIN_IDENTITY')
    prior_manifest = read(ROOT / 'docs/v42_physical_global_lb_pilot/NATIVE0.json')['source_records']
    for name in ['FULL_A.npz', 'FULL_DATA.npz', 'CURRENT_C2_AXES.npz', 'CURRENT_C2_ALIASES.json']:
        require(sha(SAVED / name) == prior_manifest[str(SAVED / name)], 'FROZEN_SOURCE_FILE:' + name)
    with np.load(incumbent, allow_pickle=False) as z:
        joint = z['x'].copy()
    joint_d = load_data(previous / 'JOINT_DATA.npz')
    joint_columns = load_data(previous / 'JOINT_AXES.npz')['columns']
    require(len(joint_d['names']) == len(joint) == 244265, 'JOINT_COLUMNS')
    x, error, c2_axes, aliases, integer_error = restore_original(joint, joint_columns, d)
    geometry = Geometry(A, d)
    geometry.numerical(x, error)
    activity = A @ x
    residual = activity - d['rhs']
    violation = np.where(d['sense'] == '<', residual, np.where(d['sense'] == '>', -residual, abs(residual)))
    abs_A = abs(A)
    magnitude = abs_A @ abs(x) + abs(d['rhs'])
    propagated = abs_A @ error
    n = np.diff(A.indptr) + 4
    envelope = np.nextafter(4 * (n * EPS / (1 - n * EPS)) * magnitude + 2 * propagated, np.inf)
    del abs_A, magnitude, propagated
    with np.load(COEFFICIENTS, allow_pickle=False) as z:
        coefficients = {key: z[key].copy() for key in ('node_names', 'branch_names', 'transformer_ratings')}
    require(sha(COEFFICIENTS) == 'b3370e37a375d6b358ba0695feeb5bad26da4d043447669f5d2d3024ad20eba8', 'PLANNING_COEFFICIENTS_SHA')
    previous_rows = existing_rows(existing_ids)
    candidates, census, uncertain = [], {}, {}
    for family in FAMILIES:
        ids = np.array([i for i, name in enumerate(d['row_names']) if str(name).startswith(family + '[')], dtype=int)
        missing = ids[~np.isin(ids, list(previous_rows))]
        confirmed = missing[violation[missing] - envelope[missing] > 1e-8]
        ambiguous = missing[(violation[missing] + envelope[missing] > 0) & (violation[missing] - envelope[missing] <= 1e-8)]
        census[family] = dict(original_rows=len(ids), missing_rows=len(missing), numerical_positive_over_1e8=int(sum(violation[missing] > 1e-8)),
                              screened_positive=len(confirmed), maximum_raw_violation=float(max(violation[missing])) if len(missing) else None)
        uncertain[family] = dict(count=len(ambiguous), row_ids=ambiguous.tolist(),
                                 reason='search interval intersects zero or positive violation <=1e-8; no exact completeness claim')
        for i in confirmed:
            i = int(i); name = str(d['row_names'][i]); meta = metadata(name, coefficients)
            candidates.append(dict(original_row=i, name=name, metadata=meta,
                original_sense=str(d['sense'][i]), original_rhs=float(d['rhs'][i]), source_row_sha256=row_sha(A, d, i),
                raw_violation=float(violation[i]), normalized_violation=float(violation[i] / meta['scale']),
                search_error_upper=float(envelope[i]), search_violation_lower=float(violation[i] - envelope[i]),
                existing_K_duplicate=i in previous_rows, selected=False, reason='OUTSIDE_FIXED_FAMILY_QUOTA_OR_LOWER_WITHIN_FAMILY_RANK'))
    compact_to_local = {int(c2_axes[c]): j for j, c in enumerate(joint_columns)}
    alias_by_column = {int(p['column']): p for p in aliases}
    @lru_cache(maxsize=None)
    def transport(j):
        if j in compact_to_local:
            return F(0), {compact_to_local[j]: F(1)}
        require(j in alias_by_column, 'NONPHYSICAL_OR_UNRESTORABLE_COORDINATE:' + str(j))
        plan = alias_by_column[j]
        constant, result = F(float(plan['constant'])), defaultdict(F)
        for k, weight in plan['terms'].items():
            c0, pieces = transport(int(k)); w = F(float(weight)); constant += w * c0
            for q, value in pieces.items():
                result[q] += w * value
        return constant, {q: value for q, value in result.items() if value}
    with np.load(SAVED / 'FRESH_U4/RAW_00.npz', allow_pickle=False) as z:
        u4 = z['point'][joint_columns].copy()
    selected, failures, seen = [], [], set()
    # Existing source rows enter duplicate signatures, while never being added.
    for i in previous_rows:
        terms, rhs, _, _ = geometry.project(i)
        seen.add(canonical_sha(dict(rhs=str(rhs), terms={str(j):str(c) for j,c in sorted(terms.items())})))
    pools = {family: sorted([c for c in candidates if c['metadata']['family'] == family],
                            key=lambda c: (-c['normalized_violation'], c['original_row'])) for family in FAMILIES}
    represented = set()
    def admit(candidate, quota_reason, require_diversity=True):
        meta = candidate['metadata']; key = meta['family'], meta['asset'], meta['phase'], meta['slot']
        if require_diversity and key in represented:
            candidate['reason'] = 'DEFERRED_SAME_ASSET_PHASE_SLOT_FACET_FOR_REPRESENTATIVE_FIRST_PASS'
            return False
        i = candidate['original_row']
        try:
            original_terms, exact_rhs, c0, used = geometry.project(i)
            require(all(str(d['names'][j]).split('[',1)[0] in {'Pch','Pdis','Q'} or str(d['names'][j]) == 'rho_max' for j in original_terms), 'RESIDUAL_NONPQ_COORDINATE')
            signature = canonical_sha(dict(rhs=str(exact_rhs), terms={str(j):str(c) for j,c in sorted(original_terms.items())}))
            if signature in seen:
                candidate['reason'] = 'EXACT_PROJECTED_ROW_DUPLICATE'; return False
            local_terms, alias_c0 = defaultdict(F), F(0)
            for j, coefficient in original_terms.items():
                offset, pieces = transport(j); alias_c0 += coefficient * offset
                for q, value in pieces.items():
                    local_terms[q] += coefficient * value
            local_terms = {j:c for j,c in local_terms.items() if c}
            exact_rhs -= alias_c0
            exact_violation = sum((c * F(float(joint[j])) for j,c in local_terms.items()), F(0)) - exact_rhs
            require(exact_violation > 0, 'EXACT_VIOLATION_NOT_POSITIVE')
            coefficient_error, native_terms = F(0), {}
            for j, coefficient in local_terms.items():
                native = float(coefficient)
                require(math.isfinite(native) and native != 0, 'COEFFICIENT_OVERFLOW_OR_UNDERFLOW')
                require(math.isfinite(joint_d['lb'][j]) and math.isfinite(joint_d['ub'][j]), 'UNBOUNDED_ROUNDING_BOX')
                delta = F(native) - coefficient
                coefficient_error += max(delta * F(float(joint_d['lb'][j])), delta * F(float(joint_d['ub'][j])))
                native_terms[j] = native
            native_rhs = upward(exact_rhs + coefficient_error)
            native_violation_exact = sum((F(c) * F(float(joint[j])) for j,c in native_terms.items()), F(0)) - F(native_rhs)
            require(native_violation_exact > 0, 'OUTWARD_ROW_DOES_NOT_EXCLUDE_INCUMBENT')
            u4_violation = sum((c * F(float(u4[j])) for j,c in local_terms.items()), F(0)) - exact_rhs
            native_u4 = sum((F(c) * F(float(u4[j])) for j,c in native_terms.items()), F(0)) - F(native_rhs)
            require(native_u4 <= F(1,10**8), 'FROZEN_U4_CUT_REPLAY_FAILED')
            packet = dict(candidate, normalized_sense='<', original_terms={str(j):str(c) for j,c in sorted(original_terms.items())},
                          terms={str(j):str(c) for j,c in sorted(local_terms.items())}, exact_rhs=str(exact_rhs),
                          helper_constant=str(c0), alias_constant=str(alias_c0), eliminated_constant=str(c0+alias_c0),
                          native_rhs=native_rhs, error_upper_bound=str(coefficient_error),
                          rhs_outward_extra=str(F(native_rhs)-(exact_rhs+coefficient_error)), exact_violation=str(exact_violation),
                          native_incumbent_violation_exact=str(native_violation_exact), U4_exact_violation=str(u4_violation),
                          U4_native_violation_exact=str(native_u4), projected_signature_sha256=signature,
                          helper_rows=[dict(original_row=h, name=str(d['row_names'][h]), source_row_sha256=row_sha(A,d,h)) for h in sorted(used)],
                          selected=True, reason=quota_reason)
            selected.append(packet); seen.add(signature); represented.add(key)
            candidate.update(selected=True, reason=quota_reason, exact_violation=str(exact_violation), projected_signature_sha256=signature)
            return True
        except ValueError as exc:
            candidate['reason'] = 'NOT_AUTOMATICALLY_ADMITTED:' + str(exc)
            failures.append(dict(original_row=i, error=str(exc)))
            return False
    # Fixed family quotas avoid comparing unlike units. Representative first pass
    # never removes a mathematically distinct row from later refill consideration.
    for family in FAMILIES:
        count = 0
        for candidate in pools[family]:
            if count >= QUOTAS[family]:
                break
            count += int(admit(candidate, 'FIXED_FAMILY_QUOTA_WITHIN_FAMILY_NORMALIZED_RANK'))
    for diversity in (True, False):
        for family in FAMILIES:
            for candidate in pools[family]:
                if len(selected) >= 16:
                    break
                if not candidate['selected'] and not candidate['reason'].startswith(('EXACT_PROJECTED_ROW_DUPLICATE', 'NOT_AUTOMATICALLY_ADMITTED')):
                    admit(candidate, 'UNUSED_QUOTA_REFILL_WITHIN_FAMILY_RANK', diversity)
            if len(selected) >= 16:
                break
        if len(selected) >= 16:
            break
    ii, jj, values = [], [], []
    for r, packet in enumerate(selected):
        for j, value in packet['terms'].items():
            ii.append(r); jj.append(int(j)); values.append(float(F(value)))
    cuts = sparse.coo_matrix((values,(ii,jj)),shape=(len(selected),len(joint))).tocsr()
    sparse.save_npz(out / 'CUTS_A.npz', cuts)
    np.savez_compressed(out / 'CUTS_DATA.npz', rhs=np.array([r['native_rhs'] for r in selected]),
                        senses=np.full(len(selected),'<'), row_names=np.array([r['name'] for r in selected]))
    write(out / 'CUTS_EXACT.json', dict(schema='V42_CRITICAL_GRID_CG_CUTS_V1', source=SOURCE, case_sha=CASE,
          previous_model_directory=str(previous), incumbent_path=str(incumbent), existing_original_rows=sorted(previous_rows),
          rows=selected, columns=len(joint), Native_optimize_calls=0,
          rounding_policy='ceil_binary64(exact_rhs + sum max((native_c-exact_c)*lb,(native_c-exact_c)*ub))'))
    write(out / 'CANDIDATES.json',dict(schema='V42_CRITICAL_GRID_CG_CANDIDATES_V1', candidates=candidates))
    helper_residual = max((abs(float(residual[i])) for i in geometry.definitions.values()), default=0.)
    report = dict(PASS=True, source=SOURCE, case_sha=CASE, scan_original_security_rows=sum(v['original_rows'] for v in census.values()),
                  families=census, uncertainty=uncertain, candidate_count=len(candidates), selected_count=len(selected),
                  selected_original_rows=[r['original_row'] for r in selected], helper_equalities=len(geometry.definitions),
                  helper_numerical_replay_max_residual=helper_residual, original_integer_pattern_max_residual=integer_error,
                  rho=float(joint[-1]), source_files={str(p):sha(p) for p in [SAVED/'FULL_A.npz',SAVED/'FULL_DATA.npz',SAVED/'CURRENT_C2_AXES.npz',SAVED/'CURRENT_C2_ALIASES.json',COEFFICIENTS,incumbent,previous/'JOINT_AXES.npz',previous/'JOINT_DATA.npz']},
                  files={p:sha(out/p) for p in ['CUTS_A.npz','CUTS_DATA.npz','CUTS_EXACT.json','CANDIDATES.json']},
                  fixed_family_quotas=QUOTAS, family_refill_order=list(FAMILIES),
                  selection='family-specific normalized rank, exact-duplicate rejection, asset/phase/slot representatives, then unused-quota refill',
                  failures=failures, Native_optimize_calls=0, full_model_builds=0, full_solver_calls=0,
                  authority='stored FULL binary64 interpreted as exact Fraction; frozen Planning coefficients metadata only',
                  exact_completeness_claim=False, wall_seconds=time.perf_counter()-started)
    write(out / 'SEPARATION.json',report)
    del A, d, geometry
    gc.collect()
    print(json.dumps({k:report[k] for k in ['PASS','scan_original_security_rows','candidate_count','selected_count','wall_seconds']}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--previous',type=Path,required=True)
    parser.add_argument('--incumbent',type=Path,required=True)
    parser.add_argument('--existing-row-ids',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    separate(args.previous,args.incumbent,args.existing_row_ids,args.out)
