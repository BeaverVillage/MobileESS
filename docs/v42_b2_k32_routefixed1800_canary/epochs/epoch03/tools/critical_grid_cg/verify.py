"""Independent exact cut and numerical solver-contract validator.

No builder/oracle imports, Gurobi imports, model generation, or optimization.
Stored binary64 coefficients are exact dyadic mathematical authority.  The
exact inclusion proof is separate from Gurobi's numerical global-bound contract.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from fractions import Fraction
import gc
import hashlib
import json
import math
from pathlib import Path
import re
import time
import traceback

import numpy as np
from scipy import sparse

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(r'D:\v42_dense_response_development_repair_20261011\dates\B2\2025-05-01\attempts\native0_restored\output')
PREVIOUS = ROOT/'docs/v42_joint_critical_grid_lb_pilot/native360'
OUT = ROOT/'docs/v42_critical_grid_cg_lb_pilot'
CERT = Path(r'D:\v42_svr11_may_20261011_16\models\2025-05-01\ELECTRICAL_CERTIFICATE.json')
SOURCE18R = '497609b46faa14ea7e32a9483a333ab32fd264ef'
PR210 = '6a8fd44f59f1f461c60d2d14f5f5be605e4ed640'
CASE = '34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292'
FULL_MATRIX = '0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec'
FULL_DOMAIN = '9247e42b8119f60ef149d0963e31dd8a697af5426a5aaeec9450b2a2f246481e'
UB = .6760534504652341
LB_OLD = .42547778318693985
FAMILIES = {'line_thermal_face', 'transformer_kVA', 'NormalAmps', 'voltage_upper', 'voltage_lower'}
PHYSICAL = {'arc', 'charge_mode', 'SOC', 'Pch', 'Pdis', 'Q', 'node_activity'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(path)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def npz(path):
    with np.load(path, allow_pickle=False) as packet:
        return {key: packet[key].copy() for key in packet.files}


def dyadic(value):
    require(math.isfinite(float(value)), 'NONFINITE_STORED_COEFFICIENT')
    return Fraction(float(value))


def upward(value):
    result = float(value)
    require(math.isfinite(result), 'NONFINITE_NATIVE_RHS')
    return float(np.nextafter(result, np.inf)) if Fraction(result) < value else result


def axis(value):
    match = re.fullmatch(r'([^\[]+)(?:\[([^\]]+)\])?', str(value))
    require(match is not None, 'INVALID_AXIS_NAME')
    return match[1], [] if match[2] is None else match[2].split(',')


def canonical_data(data):
    answer = dict(data)
    for key, choices in {'c':('c','objective'), 'lb':('lb','lower'), 'ub':('ub','upper'),
                         'vtypes':('vtypes','types'), 'senses':('senses','sense')}.items():
        present = [name for name in choices if name in data]
        require(len(present) == 1, 'AMBIGUOUS_OR_MISSING_KEY_'+key)
        answer[key] = data[present[0]]
    return answer


def digests(matrix, data):
    h = hashlib.sha256(np.asarray(matrix.shape, dtype='<i8').tobytes())
    for value in (matrix.indptr, matrix.indices, matrix.data):
        h.update(value.dtype.str.encode('ascii'))
        h.update(np.ascontiguousarray(value).tobytes())
    q = hashlib.sha256()
    for key in sorted(data):
        value = np.asarray(data[key])
        q.update(key.encode())
        q.update(value.dtype.str.encode())
        q.update(np.asarray(value.shape, dtype='<i8').tobytes())
        q.update(value.tobytes())
    return h.hexdigest(), q.hexdigest()


def original_row_sha(A, d, row):
    start, end = A.indptr[row:row+2]
    packet = {'original_row':int(row), 'name':str(d['row_names'][row]),
              'sense':str(d['senses'][row]), 'rhs_hex':float(d['rhs'][row]).hex(),
              'terms':[[int(c), float(v).hex()] for c,v in zip(A.indices[start:end], A.data[start:end])]}
    return hashlib.sha256(json.dumps(packet, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Geometry:
    """Independent recursive elimination of original helper equalities."""

    def __init__(self, A, d):
        self.A, self.d = A, d
        self.definitions, self.cache, self.used = {}, {}, set()
        for row, value in enumerate(d['row_names']):
            family, coordinates = axis(value)
            if not (family.endswith('_binding') and family.startswith(('injection_', 'response_'))):
                continue
            require(d['senses'][row] == '=', 'NON_EQUALITY_HELPER_DEFINITION')
            start, end = A.indptr[row:row+2]
            pivots = [int(c) for c,v in zip(A.indices[start:end], A.data[start:end])
                      if axis(d['names'][c])[0]+'_binding' == family and v == 1.]
            require(len(pivots) == 1, 'HELPER_PIVOT_NOT_UNIQUE_POSITIVE_ONE')
            col = pivots[0]
            require(col not in self.definitions, 'DUPLICATE_HELPER_DEFINITION')
            _, pivot_coordinates = axis(d['names'][col])
            require(not coordinates or coordinates == pivot_coordinates, 'HELPER_AXIS_MISMATCH')
            if family.startswith('injection_'):
                expected = {'Pch', 'Pdis'} if family == 'injection_P_binding' else {'Q'}
                require(family in ('injection_P_binding', 'injection_Q_binding'), 'UNKNOWN_INJECTION')
                require(d['rhs'][row] == 0., 'NONZERO_INJECTION_CONSTANT')
                for c,v in zip(A.indices[start:end], A.data[start:end]):
                    if int(c) == col:
                        continue
                    other_family, other_axis = axis(d['names'][c])
                    require(other_family in expected and other_axis[1:] == pivot_coordinates,
                            'INJECTION_SITE_SLOT_AXIS_MISMATCH')
                    require(v == (1. if other_family == 'Pch' else -1.), 'INJECTION_PQ_SIGN_MISMATCH')
            self.definitions[col] = row

    def expand(self, col, stack=()):
        if col in self.cache:
            return self.cache[col]
        require(col not in stack, 'HELPER_DEFINITION_CYCLE')
        if col not in self.definitions:
            family,_ = axis(self.d['names'][col])
            require(family in PHYSICAL or str(self.d['names'][col]) == 'rho_max',
                    'UNELIMINATED_GLOBAL_HELPER')
            answer = Fraction(0), {col:Fraction(1)}
        else:
            row = self.definitions[col]
            self.used.add(row)
            start,end = self.A.indptr[row:row+2]
            constant = dyadic(self.d['rhs'][row])
            terms = defaultdict(Fraction)
            for c,v in zip(self.A.indices[start:end], self.A.data[start:end]):
                c = int(c)
                if c == col:
                    continue
                offset,pieces = self.expand(c, stack+(col,))
                coefficient = -dyadic(v)
                constant += coefficient*offset
                for leaf,weight in pieces.items():
                    terms[leaf] += coefficient*weight
            answer = constant,{c:v for c,v in terms.items() if v}
        self.cache[col] = answer
        return answer

    def security(self, row):
        family,_ = axis(self.d['row_names'][row])
        require(family in FAMILIES, 'NOT_ORIGINAL_SECURITY_ROW')
        sense = self.d['senses'][row]
        require(sense in ('<','>'), 'SECURITY_SENSE_INVALID')
        sign = Fraction(1 if sense == '<' else -1)
        constant,terms = Fraction(0),defaultdict(Fraction)
        start,end = self.A.indptr[row:row+2]
        for c,v in zip(self.A.indices[start:end], self.A.data[start:end]):
            offset,pieces = self.expand(int(c))
            coefficient = sign*dyadic(v)
            constant += coefficient*offset
            for leaf,weight in pieces.items():
                terms[leaf] += coefficient*weight
        return sign*dyadic(self.d['rhs'][row])-constant,constant,{c:v for c,v in terms.items() if v}


class CompactMap:
    """Independent original Compact inverse aliases, from frozen proof packets."""

    def __init__(self, source, axes, names):
        c2 = npz(source/'CURRENT_C2_AXES.npz')['columns']
        c3a = npz(source/'CURRENT_C3A_AXES.npz')['columns']
        require(np.array_equal(c3a, np.arange(len(c2))), 'C3A_COLUMN_AXIS_CHANGED')
        require(len(set(map(int, axes))) == len(axes), 'JOINT_COLUMN_AXIS_DUPLICATE')
        self.direct = {int(c2[c]):joint for joint,c in enumerate(axes)}
        records = read(source/'CURRENT_C2_ALIASES.json')
        self.aliases = {int(item['column']):item for item in records}
        require(len(records) == len(self.aliases) == 14618 and
                not set(self.direct) & set(self.aliases), 'STATIC_ALIAS_CENSUS_OR_AXIS_CHANGED')
        self.names,self.cache = names,{}

    def expand(self, col, stack=()):
        if col in self.cache:
            return self.cache[col]
        require(col not in stack, 'COMPACT_ALIAS_CYCLE')
        if col in self.direct:
            answer = Fraction(0),{self.direct[col]:Fraction(1)}
        else:
            require(col in self.aliases, 'ORIGINAL_COORDINATE_HAS_NO_JOINT_PROJECTION')
            record = self.aliases[col]
            constant,terms = dyadic(record['constant']),defaultdict(Fraction)
            for c,v in record['terms'].items():
                offset,pieces = self.expand(int(c),stack+(col,))
                coefficient = dyadic(v)
                constant += coefficient*offset
                for leaf,weight in pieces.items():
                    terms[leaf] += coefficient*weight
            answer = constant,{c:v for c,v in terms.items() if v}
        self.cache[col] = answer
        return answer

    def row(self, rhs, constant, terms):
        result = defaultdict(Fraction)
        for c,v in terms.items():
            offset,pieces = self.expand(c)
            rhs -= v*offset
            constant += v*offset
            for leaf,weight in pieces.items():
                result[leaf] += v*weight
        return rhs,constant,{c:v for c,v in result.items() if v}


def metadata_identity(name, coefficient_axes):
    family,parts = axis(name)
    require(family in FAMILIES, 'UNRECOGNIZED_ROW_FAMILY')
    slot = int(parts[0])
    require(0 <= slot < 96, 'SECURITY_SLOT_OUTSIDE_HORIZON')
    facet,index = None,None
    if family in ('line_thermal_face','transformer_kVA'):
        require(len(parts) == 3, 'SECURITY_THERMAL_ROW_AXIS')
        index,facet = int(parts[1]),int(parts[2])
        label = str(coefficient_axes['branch_names'][index])
        require(0 <= facet < 16, 'FACET_OUTSIDE_PCS16')
        require('::' in label, 'BRANCH_PHASE_AXIS_MISSING')
        asset,phase = label.rsplit('::',1)
    elif family in ('voltage_upper','voltage_lower'):
        require(len(parts) == 2, 'SECURITY_VOLTAGE_ROW_AXIS')
        index = int(parts[1])
        label = str(coefficient_axes['node_names'][index])
        require('.' in label, 'VOLTAGE_PHASE_AXIS_MISSING')
        asset,phase = label.rsplit('.',1)
    else:
        require(len(parts) == 2, 'SECURITY_NORMALAMPS_ROW_AXIS')
        require('::' in parts[1], 'NORMALAMPS_PHASE_AXIS_MISSING')
        asset,phase = parts[1].rsplit('::',1)
    if family == 'transformer_kVA':
        rating = float(coefficient_axes['transformer_ratings'][index])
        require(math.isfinite(rating) and rating > 0, 'INVALID_ORIGINAL_TRANSFORMER_RATING')
        unit,scale,basis = 'kVA',rating*math.cos(math.pi/16),'original transformer nameplate kVA*cos(pi/16) facet rating'
    elif family.startswith('voltage_'):
        unit,scale,basis = 'voltage_squared_pu',1.,'1 pu squared voltage; ranked only within family'
    elif family == 'NormalAmps':
        unit,scale,basis = 'current_loading_pu',1.,'original normalized current rating=1'
    else:
        unit,scale,basis = 'thermal_loading_pu',1.,'original line utilization normalized rating=1'
    return {'family':family,'slot':slot,'index':index,'asset':asset,'phase':phase,'facet':facet,
            'unit':unit,'scale':scale,'normalization_basis':basis}


def exact_native_row(record, expected, d):
    """Validate a certificate against independently derived exact coordinates."""
    for key in ('original_row','name','original_sense','source_row_sha256'):
        require(record[key] == expected[key], 'CUT_'+key.upper()+'_MISMATCH')
    require(dyadic(record['original_rhs']) == expected['original_rhs'], 'CUT_ORIGINAL_RHS_SIGN_MISMATCH')
    for key,value in expected['metadata'].items():
        require(record['metadata'][key] == value, 'CUT_METADATA_'+key.upper()+'_MISMATCH')
    require(record['normalized_sense'] == '<', 'CUT_NORMALIZED_SENSE_MISMATCH')
    require(Fraction(record['exact_rhs']) == expected['exact_rhs'], 'CUT_EXACT_RHS_MISMATCH')
    require(Fraction(record['eliminated_constant']) == expected['eliminated_constant'], 'CUT_FIXED_CONSTANT_MISMATCH')
    require({int(c):Fraction(v) for c,v in record['original_terms'].items()} == expected['original_terms'],
            'CUT_ORIGINAL_PHYSICAL_COEFFICIENT_MISMATCH')
    terms = {int(c):Fraction(v) for c,v in record['terms'].items()}
    require(terms == expected['terms'], 'CUT_COMPACT_COEFFICIENT_MISMATCH')
    error,reverse = Fraction(0),Fraction(0)
    native = {}
    for c,v in sorted(terms.items()):
        require(0 <= c < len(d['names']), 'CUT_TARGET_AXIS_OUTSIDE_DOMAIN')
        coefficient = float(v)
        require(math.isfinite(coefficient) and coefficient != 0., 'CUT_NONFINITE_OR_DROPPED_TINY_COEFFICIENT')
        delta = Fraction(coefficient)-v
        error += max(delta*dyadic(d['lb'][c]),delta*dyadic(d['ub'][c]))
        reverse += max(-delta*dyadic(d['lb'][c]),-delta*dyadic(d['ub'][c]))
        native[c] = coefficient
    target = expected['exact_rhs']+error
    native_rhs = upward(target)
    require(float(record['native_rhs']) == native_rhs and dyadic(record['native_rhs']) >= target,
            'CUT_RHS_NOT_MINIMAL_CONSERVATIVE_UPWARD')
    require(Fraction(record['error_upper_bound']) == error and
            Fraction(record['rhs_outward_extra']) == Fraction(native_rhs)-target,
            'CUT_OUTWARD_ROUNDING_CERTIFICATE_MISMATCH')
    return native,native_rhs,error,reverse


def adversarial(record, expected, d, packet_source_check):
    tests = {}
    mutations = {
        'Row_ID':lambda row:row.update(original_row=row['original_row']+1),
        'Phase':lambda row:row['metadata'].update(phase=str(row['metadata']['phase'])+'_MUTATED'),
        'RHS_sign':lambda row:row.update(original_rhs=-float(row['original_rhs'])),
        'Coefficient':lambda row:row['terms'].update({next(iter(row['terms'])):str(Fraction(next(iter(row['terms'].values())))+1)}),
        'Rounding_direction':lambda row:row.update(native_rhs=float(np.nextafter(float(row['native_rhs']),-np.inf))),
    }
    for name,mutate in mutations.items():
        altered = deepcopy(record)
        mutate(altered)
        try:
            exact_native_row(altered,expected,d)
        except (ValueError,KeyError) as error:
            tests[name] = {'rejected':True,'reason':str(error)}
        else:
            tests[name] = {'rejected':False}
    try:
        packet_source_check(SOURCE18R[:-1]+'0')
    except ValueError as error:
        tests['Source_SHA'] = {'rejected':True,'reason':str(error)}
    else:
        tests['Source_SHA'] = {'rejected':False}
    require(all(value['rejected'] for value in tests.values()), 'ADVERSARIAL_CUT_MUTATION_WAS_ACCEPTED')
    return tests


def replay(A,d,x,tolerance=1e-8):
    require(x.shape == (A.shape[1],) and np.all(np.isfinite(x)), 'INVALID_REPLAY_POINT')
    residual = A@x-d['rhs']
    violation = np.where(d['senses'] == '=',abs(residual),np.where(d['senses'] == '<',residual,-residual))
    row = float(max(0.,np.max(violation)))
    bound = float(max(0.,np.max(d['lb']-x),np.max(x-d['ub'])))
    binary = d['vtypes'] == 'B'
    integer = float(np.max(abs(x[binary]-np.rint(x[binary]))))
    require(row <= tolerance and bound <= 1e-8 and integer <= 1e-8, 'POINT_REPLAY_FAILED')
    return {'row_violation':row,'bound_violation':bound,'binary_violation':integer,'rho':float(x[-1]),
            'FULL_UB_claim':False,'Actual_PASS_claim':False}


def source_code_check(value):
    require(value == SOURCE18R, 'SOURCE18R_COMMIT_SHA_MISMATCH')


def native0(source,previous,out):
    """Validate exact rows first, release FULL, then audit nested Joint CSR."""
    packet = read(out/'CUTS_EXACT.json')
    source_code_check(packet['source'])
    require(packet['case_sha'] == CASE, 'CUT_CASE_SHA_MISMATCH')
    parent_certificate = read(previous/'INDEPENDENT_CERTIFICATE.json')
    require(parent_certificate['PASS'], 'PREVIOUS_INDEPENDENT_CERTIFICATE_NOT_PASS')
    parent_native0 = read(previous/'INDEPENDENT_NATIVE0.json')
    require(parent_native0['PASS'], 'PREVIOUS_EXACT_NATIVE0_NOT_PASS')
    for name,expected_sha in parent_native0['file_sha256'].items():
        require(sha(previous/name) == expected_sha, 'PREVIOUS_FROZEN_ARTIFACT_SHA_CHANGED_'+name)
    require(parent_certificate.get('exact_numeric_BB_trace_certificate', False) is False,
            'PREVIOUS_SOLVER_CERTIFICATE_SCOPE_CHANGED')
    old_raw = npz(previous/'JOINT_DATA.npz')
    old = canonical_data(old_raw)
    axes = npz(previous/'JOINT_AXES.npz')['columns']
    identity = read(source/'SCIENTIFIC_CASE_IDENTITY.json')
    require(identity['case_sha'] == CASE and identity['original_matrix_sha'] == FULL_MATRIX and
            identity['original_domain_sha'] == FULL_DOMAIN, 'FROZEN_FULL_IDENTITY_DRIFT')
    for record in identity['transport_authority']['sources'].values():
        require(sha(record['path']) == record['sha256'], 'SCIENTIFIC_SOURCE_BYTES_CHANGED')
    immutable_records = read(ROOT/'docs/v42_physical_global_lb_pilot/NATIVE0.json')['source_records']
    for name in ('FULL_A.npz','FULL_DATA.npz','CURRENT_C2_AXES.npz','CURRENT_C2_ALIASES.json',
                 'FIXED_AIDC_ANCHOR.json','SCIENTIFIC_CASE_IDENTITY.json','FRESH_U4/RAW_00.npz','FRESH_U4/RAW_00.REPLAY.json'):
        require(sha(source/name) == immutable_records[str(source/name)], 'FROZEN_PR209_SOURCE_BYTES_CHANGED_'+name)
    cert = read(CERT)
    coefficient_record = cert['outputs']['planning_coefficients']
    input_identity = read(source/'INPUT_AND_SOURCE_IDENTITY.json')
    require(sha(CERT) == input_identity['electrical_certificate']['sha256'] and
            sha(coefficient_record['path']) == coefficient_record['sha256'], 'PLANNING_COEFFICIENT_AUTHORITY_DRIFT')
    with np.load(coefficient_record['path'],allow_pickle=False) as z:
        coefficient_axes = {key:z[key].copy() for key in ('branch_names','node_names','transformer_ratings')}
    A = sparse.load_npz(source/'FULL_A.npz').tocsr()
    raw = npz(source/'FULL_DATA.npz')
    require(digests(A,raw) == (FULL_MATRIX,FULL_DOMAIN), 'ACTUAL_FULL_MATRIX_DOMAIN_SHA_MISMATCH')
    d = canonical_data(raw)
    geometry = Geometry(A,d)
    mapping = CompactMap(source,axes,old['names'])
    rows = packet['rows']
    require(1 <= len(rows) <= 16 and len({record['original_row'] for record in rows}) == len(rows),
            'CUT_COUNT_OR_DUPLICATE_ROW_GATE_FAILED')
    previous_names = set(map(str,old['row_names']))
    expected_rows,rounding = [],[]
    u4 = npz(previous/'JOINT_START.npz')['x']
    require(Path(packet['incumbent_path']).resolve() == (previous/'JOINT_INCUMBENT.npz').resolve(),
            'SEPARATION_INCUMBENT_NOT_PREVIOUS_CERTIFIED_POINT')
    incumbent = npz(previous/'JOINT_INCUMBENT.npz')['x']
    require(incumbent.shape == (len(old['names']),) and np.all(np.isfinite(incumbent)),
            'SEPARATION_INCUMBENT_INVALID')
    for record in rows:
        row = int(record['original_row'])
        require(0 <= row < A.shape[0] and str(d['row_names'][row]) not in previous_names,
                'CUT_NOT_NEW_ORIGINAL_ROW')
        rhs,constant,original_terms = geometry.security(row)
        joint_rhs,joint_constant,terms = mapping.row(rhs,constant,original_terms)
        require(Fraction(record['helper_constant']) == constant and
                Fraction(record['alias_constant']) == joint_constant-constant, 'CUT_HELPER_OR_ALIAS_CONSTANT_MISMATCH')
        require(all(axis(d['names'][col])[0] in {'Pch','Pdis','Q'} or d['names'][col]=='rho_max'
                    for col in original_terms), 'CUT_ORIGINAL_PQ_COORDINATE_SCOPE_MISMATCH')
        expected = {'original_row':row,'name':str(d['row_names'][row]),
                    'original_sense':str(d['senses'][row]),'original_rhs':dyadic(d['rhs'][row]),
                    'source_row_sha256':original_row_sha(A,d,row),
                    'metadata':metadata_identity(d['row_names'][row],coefficient_axes),
                    'original_terms':original_terms,'terms':terms,
                    'exact_rhs':joint_rhs,'eliminated_constant':joint_constant}
        native,rhs_float,error,reverse = exact_native_row(record,expected,old)
        exact_incumbent = sum((value*dyadic(incumbent[col]) for col,value in terms.items()),Fraction(0))-joint_rhs
        native_incumbent = sum((dyadic(value)*dyadic(incumbent[col]) for col,value in native.items()),Fraction(0))-dyadic(rhs_float)
        require(Fraction(record['exact_violation']) == exact_incumbent and exact_incumbent > 0 and
                Fraction(record['native_incumbent_violation_exact']) == native_incumbent and native_incumbent > 0,
                'CUT_DOES_NOT_EXCLUDE_CERTIFIED_PREVIOUS_INCUMBENT')
        exact_u4 = sum((value*dyadic(u4[col]) for col,value in terms.items()),Fraction(0))-joint_rhs
        require(float(exact_u4) <= 1e-8, 'ORIGINAL_U4_CUT_REPLAY_FAILED')
        for helper in record['helper_rows']:
            hrow = int(helper['original_row'])
            require(hrow in geometry.definitions.values() and helper['name']==str(d['row_names'][hrow]) and
                    helper['source_row_sha256']==original_row_sha(A,d,hrow), 'CUT_HELPER_ROW_PROVENANCE_MISMATCH')
        rho = len(old['names'])-1
        if expected['metadata']['family'] == 'line_thermal_face':
            require(terms.get(rho) == -1, 'THERMAL_RHO_SIGN_SCALE_MISMATCH')
        expected_rows.append({'name':expected['name'],'terms':native,'rhs':rhs_float})
        rounding.append({'original_row':row,'name':expected['name'],'exact_U4_violation':str(exact_u4),
                         'exact_terms':len(terms),'error_upper_bound':str(error),
                         'rhs_outward_extra':str(Fraction(rhs_float)-(joint_rhs+error)),
                         'conservative_native_row_loss':str(Fraction(rhs_float)-joint_rhs+reverse),
                         'FULL_projection_stays_feasible':True})
    # Replay the first row independently for adversarial mutations.
    first = rows[0]; r=int(first['original_row'])
    r_rhs,r_constant,r_original = geometry.security(r)
    r_rhs,r_constant,r_terms = mapping.row(r_rhs,r_constant,r_original)
    first_expected = {'original_row':r,'name':str(d['row_names'][r]),'original_sense':str(d['senses'][r]),
                      'original_rhs':dyadic(d['rhs'][r]),'source_row_sha256':original_row_sha(A,d,r),
                      'metadata':metadata_identity(d['row_names'][r],coefficient_axes),'original_terms':r_original,
                      'terms':r_terms,'exact_rhs':r_rhs,'eliminated_constant':r_constant}
    attacks = adversarial(first,first_expected,old,source_code_check)
    helper_rows = [{'row':row,'sha256':original_row_sha(A,d,row)} for row in sorted(geometry.used)]
    census = Counter(str(name).split('[',1)[0] for name in d['row_names'])
    full_census = {family:census[family] for family in FAMILIES}
    del A,raw,d,geometry,mapping,coefficient_axes
    gc.collect()
    old_A = sparse.load_npz(previous/'JOINT_A.npz').tocsr()
    require(digests(old_A,old_raw) == (parent_native0['joint_actual_matrix_sha256'],
            parent_native0['joint_actual_domain_sha256']), 'PREVIOUS_JOINT_ACTUAL_MODEL_SHA_CHANGED')
    previous_incumbent_replay = replay(old_A,old,incumbent,tolerance=1e-6)
    J = sparse.load_npz(out/'JOINT_A.npz').tocsr()
    joint_raw = npz(out/'JOINT_DATA.npz');j=canonical_data(joint_raw)
    old_count = old_A.shape[0]
    require(J.shape == (old_count+len(rows),old_A.shape[1]), 'APPENDED_JOINT_DIMENSIONS_MISMATCH')
    prefix = J[:old_count]
    require(all(np.array_equal(getattr(prefix,key),getattr(old_A,key)) for key in ('indptr','indices','data')),
            'PREVIOUS_PHYSICS_OR_SECURITY_CSR_CHANGED')
    for key in ('names','lb','ub','vtypes','c','constant'):
        require(np.array_equal(j[key],old[key]), 'PREVIOUS_DOMAIN_OR_OBJECTIVE_CHANGED_'+key)
    for key in ('row_names','rhs','senses'):
        require(np.array_equal(j[key][:old_count],old[key]), 'PREVIOUS_ROW_DATA_CHANGED_'+key)
    require(sha(out/'JOINT_AXES.npz') == sha(previous/'JOINT_AXES.npz') and
            sha(out/'JOINT_START.npz') == sha(previous/'JOINT_START.npz'), 'AXES_OR_U4_START_BYTES_CHANGED')
    require(J.shape[1] == 244265 and np.count_nonzero(j['vtypes']=='B') == 9322 and
            J.shape[0] <= 160000 and J.nnz <= 1800000, 'CG_SIZE_GATE_FAILED')
    require(float(j['constant']) == 0 and j['names'][-1]=='rho_max' and j['c'][-1]==1 and
            np.count_nonzero(j['c'])==1 and j['lb'][-1]==0 and j['ub'][-1]==1,'RHO_OR_OBJECTIVE_CHANGED')
    for offset,expected_native in enumerate(expected_rows):
        row = old_count+offset
        actual = J.getrow(row)
        require(dict(zip(map(int,actual.indices),map(float,actual.data))) == expected_native['terms'],
                'NEW_NATIVE_CSR_COEFFICIENT_MISMATCH')
        require(j['senses'][row]=='<' and j['row_names'][row]==expected_native['name'] and
                float(j['rhs'][row])==expected_native['rhs'],'NEW_NATIVE_RHS_NAME_OR_SENSE_MISMATCH')
    u4_replay = replay(J,j,u4)
    matrix_sha,domain_sha = digests(J,joint_raw)
    return {'PASS':True,'schema':'V42_CRITICAL_GRID_CG_INDEPENDENT_V1','phase':'Native0',
            'source18r':SOURCE18R,'PR210':PR210,'case_sha':CASE,'Native_optimize_calls':0,
            'Gurobi_imported':False,'FULL_CSR_released_before_Joint_CSR_load':True,
            'FULL_matrix_sha256':FULL_MATRIX,'FULL_domain_sha256':FULL_DOMAIN,
            'joint_actual_matrix_sha256':matrix_sha,'joint_actual_domain_sha256':domain_sha,
            'previous_model_rows':old_count,'new_rows':len(rows),'K16_and_all_previous_rows_bitwise_preserved':True,
            'bounds_types_columns_objective_unchanged':True,'FULL_projection_subset_native_Joint':True,
            'same_rho_and_original_objective':True,'all_cut_signs_RHS_constants_helpers_exact':True,
            'minimal_outward_rounding_verified':True,'previous_certified_LB_inheritance_valid':True,
            'source_security_family_census':full_census,'helper_definitions_used':helper_rows,
            'rounding_rows':rounding,'adversarial_tests':attacks,'U4_replay':u4_replay,
            'previous_incumbent_joint_replay':previous_incumbent_replay,
            'dimensions':{'rows':J.shape[0],'columns':J.shape[1],'binary':9322,'nnz':int(J.nnz)},
            'file_sha256':{name:sha(out/name) for name in ('JOINT_A.npz','JOINT_DATA.npz','JOINT_AXES.npz','JOINT_START.npz','CUTS_EXACT.json')},
            'previous_files_sha256':{name:sha(previous/name) for name in ('JOINT_A.npz','JOINT_DATA.npz','JOINT_AXES.npz','JOINT_START.npz','INDEPENDENT_CERTIFICATE.json')},
            'exact_BB_trace_certificate':False,
            'proof_scope':'Exact original helper elimination, certified Compact inverse mapping, nested physical/security domain, and conservative binary64 cut transport. Numerical U4 replay; no solver run.'}


def final(previous,out):
    """Audit one consumed native call, without an exact rational B&B claim."""
    zero = read(out/'INDEPENDENT_NATIVE0.json')
    require(zero['PASS'] and zero['phase']=='Native0' and zero['source18r']==SOURCE18R and
            zero['case_sha']==CASE and zero['FULL_projection_subset_native_Joint'], 'INDEPENDENT_NATIVE0_GATE_FAILED')
    build = read(out/'NATIVE0.json')
    require(build['PASS'] and build['Native_optimize_calls']==0 and build['full_MILP_calls']==0,
            'BUILDER_NATIVE0_GATE_FAILED')
    require(build['matrix_sha']==zero['joint_actual_matrix_sha256'] and
            build['domain_sha']==zero['joint_actual_domain_sha256'] and
            build['file_sha256']==zero['file_sha256'], 'BUILDER_INDEPENDENT_MODEL_HASH_MISMATCH')
    for name,expected in zero['file_sha256'].items():
        require(sha(out/name)==expected, 'FROZEN_MODEL_CHANGED_AFTER_NATIVE0_'+name)
    for name,expected in zero['previous_files_sha256'].items():
        require(sha(previous/name)==expected, 'PREVIOUS_FROZEN_MODEL_CHANGED_'+name)
    parent=read(previous/'INDEPENDENT_CERTIFICATE.json')
    require(parent['PASS'], 'PREVIOUS_BOUND_CERTIFICATE_FAILED')
    previous_lb=float(parent['Global_LB'])
    require(math.isfinite(previous_lb) and LB_OLD <= previous_lb <= UB,
            'PREVIOUS_CERTIFIED_BOUND_INVALID')
    result=read(out/'RESULT.json')
    if result['Native_optimize_calls']==0:
        require(result['classification']=='CG_RESOURCE_OR_NUMERIC_STOP' and not (out/'PILOT_STARTED.json').exists(),
                'INVALID_NO_NATIVE_STOP_RECORD')
        return {'PASS':False,'phase':'Final','classification':'CG_RESOURCE_OR_NUMERIC_STOP','Global_LB':None,
                'Native_calls_audited':0,'exact_domain_and_outward_cut_certificate_PASS':True,
                'LB_previous_fact':previous_lb,'reason':result.get('reason'),'exact_numeric_BB_trace_certificate':False}
    hold=read(out/'PRE_LAUNCH_RESOURCE_HOLD.json')
    require(hold['PASS'], 'PRE_LAUNCH_RESOURCE_HOLD_GATE_FAILED')
    if 'checks' in hold:
        require(all(hold['checks'].values()), 'PRE_LAUNCH_HOLD_CHECK_FALSE')
    peers=read(out/'PRE_OPTIMIZE_PEERS.json')
    require(peers['PASS'] and not peers['errors'] and not peers['heavy_peers'], 'OTHER_HEAVY_GUROBI_GATE_FAILED')
    readback=read(out/'NATIVE_READBACK.json')
    require(readback['PASS'] and all(readback['checks'].values()), 'ACTUAL_GUROBI_READBACK_GATE_FAILED')
    required={'matrix','rhs','senses','lower','upper','types','objective','ObjCon','ModelSense','Rows','Columns','Binary','NNZ'}
    require(required <= set(readback['checks']), 'REQUIRED_NATIVE_READBACK_CHECK_ABSENT')
    require(readback['matrix_sha']==zero['joint_actual_matrix_sha256'], 'ACTUAL_NATIVE_MATRIX_HASH_CHANGED')
    params={'Threads':1,'TimeLimit':180.,'MIPGap':.03,'MIPFocus':3,'Seed':42,
            'FeasibilityTol':1e-8,'IntFeasTol':1e-8,'OptimalityTol':1e-8}
    require(readback['parameters']==params, 'NATIVE_PARAMETERS_NOT_AUTHORIZED')
    latch=read(out/'PILOT_STARTED.json')
    require(latch['Native_optimize_max']==1 and result['Native_optimize_calls']==1 and
            latch['parameters']==params and latch['files']==zero['file_sha256'], 'EXCLUSIVE_SINGLE_CALL_LATCH_FAILED')
    if 'independent_native0_sha256' in latch:
        require(latch['independent_native0_sha256']==sha(out/'INDEPENDENT_NATIVE0.json'),
                'INDEPENDENT_NATIVE0_CHANGED_AFTER_EXECUTION_LATCH')
    for key in ('full_MILP_calls','separate_LP_calls','campaign_calls'):
        require(result[key]==0, 'UNAUTHORIZED_FULL_OR_EXTRA_SOLVER_'+key)
    require(result['exact_numeric_BB_certificate'] is False and result['incumbent_is_full_UB'] is False,
            'NUMERICAL_BOUND_OR_REDUCED_INCUMBENT_SCOPE_MISLABELLED')
    stage=int(result['stage'])
    require(stage in (1,2) and result['TimeLimit']==180 and build['stage']==stage,
            'NATIVE_STAGE_IDENTITY_MISMATCH')
    ledger=read(out.parent/'NATIVE_LEDGER.json')
    require(ledger['maximum_calls']==2 and ledger['maximum_requested_seconds']==360 and
            len(ledger['calls'])==stage and sum(call['TimeLimit'] for call in ledger['calls'])==180*stage,
            'GLOBAL_NATIVE_REQUEST_LEDGER_INVALID')
    require([call['stage'] for call in ledger['calls']]==list(range(1,stage+1)) and
            all(call['TimeLimit']==180 for call in ledger['calls']), 'GLOBAL_NATIVE_CALL_LEDGER_NOT_SEQUENTIAL')
    require(Path(ledger['calls'][-1]['out']).resolve()==out.resolve() and
            ledger['calls'][-1]['pid']==latch['pid'], 'STAGE_NATIVE_LEDGER_LATCH_MISMATCH')
    if stage==2:
        gate=read(out/'STAGE2_GATE.json')
        require(gate['PASS'], 'STAGE2_ADMISSION_FAILED')
        require(previous_lb-LB_OLD >= .005 and parent.get('incumbent_replay') is not None,
                'STAGE2_INDEPENDENT_IMPROVEMENT_OR_INTEGER_POINT_GATE_FAILED')
        previous_result=read(previous/'RESULT.json')
        require(previous_result['Native_optimize_calls']==1 and
                previous_result['numerical_bound_candidate_valid'] and not previous_result['memory_stop'] and
                not previous_result['callback_errors'] and previous_result['optimize_error'] is None,
                'STAGE1_NATIVE_LEDGER_NOT_COMPLETE_OR_UNSAFE')
    admission=read(out/'MEMORY_ADMISSION.json')
    require(admission['PASS'] and admission['RAM_reserve_bytes']==4*1024**3 and
            admission['commit_reserve_bytes']==6*1024**3 and
            admission['estimated_additional_bytes']==max(2*1024**3,4*admission['observed_model_build_private_growth_bytes']),
            'MEMORY_ADMISSION_CONTRACT_CHANGED')
    sample=admission['sample']['system']
    require(sample['RAM_available'] >= admission['RAM_reserve_bytes']+admission['estimated_additional_bytes'] and
            sample['Commit_available'] >= admission['commit_reserve_bytes']+admission['estimated_additional_bytes'],
            'POST_BUILD_MEMORY_GROWTH_GATE_FAILED')
    trace=read(out/'MEMORY_TRACE.json');samples=trace['samples']
    require(len(samples)>=2, 'NO_NATIVE_CONTINUOUS_MEMORY_TRACE')
    require(result['minimum_RAM_available']==min(s['system']['RAM_available'] for s in samples) and
            result['minimum_commit_available']==min(s['system']['Commit_available'] for s in samples),
            'SYSTEM_MEMORY_SUMMARY_MISMATCH')
    require(result['peak_process_RSS_bytes']==max(s['Peak_RSS_bytes'] for s in samples) and
            result['peak_private_commit_bytes']==max(s['Peak_Private_Commit_bytes'] or s['Private_Commit_bytes'] for s in samples) and
            result['peak_sampled_private_commit_bytes']==max(s['Private_Commit_bytes'] for s in samples),
            'PROCESS_RSS_OR_PRIVATE_COMMIT_SUMMARY_MISMATCH')
    require(bool(trace['unsafe_samples'])==result['memory_stop'], 'MEMORY_TERMINATION_TRACE_MISMATCH')
    runtime=float(result['Runtime'])
    require(math.isfinite(runtime) and runtime>=0 and math.isfinite(float(result['optimize_wall_seconds'])) and
            float(result['optimize_wall_seconds'])>=0, 'NATIVE_RUNTIME_INVALID')
    log=(out/'NATIVE.log').read_text(encoding='utf-8',errors='replace')
    complete=any(line.startswith('Root relaxation:') and 'objective' in line for line in log.splitlines())
    summary=[line for line in log.splitlines() if line.startswith(('Presolve removed','Presolved:','Root relaxation:','Explored ','User MIP start'))]
    require(complete==result['root_relaxation_completed'] and summary==result['presolve_summary'], 'ROOT_OR_PRESOLVE_LOG_SUMMARY_MISMATCH')
    numeric_failure=any(message.lower() in log.lower() for message in ('Numerical trouble','Out of memory','Numeric error'))
    bound=result.get('ObjBound')
    candidate=(result['Status'] in (2,9,11) and bound is not None and math.isfinite(float(bound)) and
               abs(float(bound))<1e100 and not result['callback_errors'] and result['optimize_error'] is None and not numeric_failure)
    require(result['numerical_bound_candidate_valid']==candidate, 'NATIVE_BOUND_VALIDITY_FLAG_MISMATCH')
    if not candidate:
        require(result['classification']=='CG_RESOURCE_OR_NUMERIC_STOP', 'INVALID_BOUND_MISCLASSIFIED')
        return {'PASS':False,'phase':'Final','classification':'CG_RESOURCE_OR_NUMERIC_STOP','Global_LB':None,
                'Native_calls_audited':1,'exact_domain_and_outward_cut_certificate_PASS':True,
                'LB_previous_fact':previous_lb,'solver_bound_valid':False,'numeric_failure_in_log':numeric_failure,
                'solver_status':result['Status'],'reported_ObjBound':bound,'exact_numeric_BB_trace_certificate':False}
    bound=float(bound)
    require(bound<=UB+1e-8 and result['UB']==UB and result['LB_old']==LB_OLD and
            result['LB_previous']==previous_lb and result['goal_LB']==UB*.97, 'ORIGINAL_UB_OR_BOUND_REFERENCES_CHANGED')
    published=max(previous_lb,bound);gap=(UB-published)/UB
    classification=('CG_RESOURCE_OR_NUMERIC_STOP' if result['memory_stop'] else
                    'CG_GLOBAL_GAP_3PCT_PASS' if published>=UB*.97 else
                    'CG_LB_MATERIAL_IMPROVEMENT' if published-LB_OLD>=.005 else 'CG_LB_NONMATERIAL')
    require(result['Global_LB']==published and result['LB_published']==published and
            result['global_gap']==gap and result['classification']==classification and
            result['delta_Joint16']==published-LB_OLD and result['goal_3percent']==(published>=UB*.97),
            'PUBLISHED_BOUND_GAP_OR_CLASSIFICATION_MISMATCH')
    incumbent_replay=None
    if result['SolCount']:
        require(result['ObjVal'] is not None and math.isfinite(float(result['ObjVal'])) and
                float(result['ObjVal'])>=bound-1e-8, 'REDUCED_INCUMBENT_BOUND_ORDER_INVALID')
        scope=result['incumbent_joint_replay']
        require(scope['full_feasibility_tested'] is False and scope['promoted_to_UB'] is False,
                'REDUCED_INCUMBENT_PROMOTED_TO_FULL_UB')
        J=sparse.load_npz(out/'JOINT_A.npz').tocsr()
        d=canonical_data(npz(out/'JOINT_DATA.npz'))
        x=npz(out/'JOINT_INCUMBENT.npz')['x']
        incumbent_replay=replay(J,d,x,tolerance=1e-6)
        require(abs(float(x[-1])-float(result['ObjVal']))<=1e-12 and float(x[-1])==scope['rho'],
                'REDUCED_INCUMBENT_OBJECTIVE_REPLAY_MISMATCH')
        del J,d,x
        gc.collect()
    files=('INDEPENDENT_NATIVE0.json','NATIVE0.json','NATIVE_READBACK.json','PRE_LAUNCH_RESOURCE_HOLD.json',
           'PRE_OPTIMIZE_PEERS.json','MEMORY_ADMISSION.json','PILOT_STARTED.json','RESULT.json','MEMORY_TRACE.json',
           'NATIVE_EVENTS.json','NATIVE.log')
    return {'PASS':True,'schema':'V42_CRITICAL_GRID_CG_INDEPENDENT_V1','phase':'Final',
            'classification':classification,'Global_LB':published,'LB_new_certified':bound,
            'LB_previous':previous_lb,'LB_old':LB_OLD,'LB_published':published,'stage':stage,
            'native_source_attribute':'ObjBound','Native_calls_audited':1,'total_new_calls_audited':stage,
            'total_requested_Native_seconds':180*stage,'verifier_Native_optimize_calls':0,
            'Full_MILP_calls':0,'separate_LP_calls':0,'source18r':SOURCE18R,'PR210':PR210,'case_sha':CASE,
            'exact_domain_and_outward_cut_certificate_PASS':True,'FULL_projection_subset_native_Joint':True,
            'previous_certified_LB_inheritance_valid':True,'actual_Gurobi_readback_PASS':True,
            'memory_admission_and_continuous_trace_audited':True,'memory_stop':result['memory_stop'],
            'solver_status':result['Status'],'Native_Runtime':runtime,'root_relaxation_completed':complete,
            'NodeCount':result['NodeCount'],'ObjVal_reduced_model_only':result.get('ObjVal'),
            'incumbent_replay':incumbent_replay,'UB':UB,'global_gap':gap,'Gap_percent':100*gap,
            'delta_Joint16':published-LB_OLD,'goal_LB':UB*.97,'goal_3percent':published>=UB*.97,
            'exact_numeric_BB_trace_certificate':False,
            'solver_bound_contract':'Gurobi numerical minimization B&B ObjBound is relied on after independent domain/source/readback/ledger/status checks. No exact rational B&B trace or extra LP optimization is claimed.',
            'mathematical_statement':'Every original FULL-feasible point projects to the bitwise-preserved physical/K16 domain and satisfies every normalized original cut after exact helper/Compact substitution and outward binary64 transport. Thus each valid native ObjBound <= min(FULL), and max of inherited valid bounds remains a valid Global LB.',
            'monotonicity_scope':'Exact nested reduced optimum cannot decrease. An unfinished solver ObjBound may decrease; only the certified published max is nondecreasing.',
            'file_sha256':{name:sha(out/name) for name in files},'global_ledger_sha256':sha(out.parent/'NATIVE_LEDGER.json')}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=('native0','final'),required=True)
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--previous',type=Path,default=PREVIOUS)
    parser.add_argument('--out',type=Path,default=OUT)
    args=parser.parse_args()
    output=args.out/('INDEPENDENT_NATIVE0.json' if args.mode=='native0' else 'INDEPENDENT_CERTIFICATE.json')
    started=time.perf_counter()
    try:
        answer=native0(args.source,args.previous,args.out) if args.mode=='native0' else final(args.previous,args.out)
        answer['wall_seconds']=time.perf_counter()-started
        write(output,answer)
        print(json.dumps({k:answer.get(k) for k in ('PASS','phase','classification','Global_LB','wall_seconds')}))
    except Exception as error:
        write(output,{'PASS':False,'phase':args.mode,'Native_optimize_calls':0,'error':str(error),
                      'traceback':traceback.format_exc(),'wall_seconds':time.perf_counter()-started})
        raise


if __name__=='__main__':
    main()
