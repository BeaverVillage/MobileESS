"""Read the existing assembled LB schema without changing scientific readers.

This is a display adapter, not a certificate producer or an independent replay.
Only the current request's SHA-bound frontier can select an assembled receipt.
"""
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
import re

from v42_b2_monitor_v16 import certificates as original


def require(condition, label):
    if not condition:
        raise ValueError('DISPLAY_ASSEMBLED_' + label)


@lru_cache(maxsize=128)
def checked_file(path, expected, mtime, size):
    require(bool(expected) and original.sha(path) == expected, 'FILE_SHA_MISMATCH')
    return True


@lru_cache(maxsize=128)
def sealed(path, expected, mtime, size):
    raw = Path(path).read_bytes()
    require(bool(expected) and hashlib.sha256(raw).hexdigest() == expected, 'FILE_SHA_MISMATCH')
    value = json.loads(raw.decode('utf-8-sig'))
    require(isinstance(value, dict), 'DOCUMENT_REQUIRED')
    return value


def receipt(path, expected, output=None):
    path = original.under(path, output) if output is not None else Path(path).resolve()
    info = path.stat()
    return path, sealed(str(path), expected, info.st_mtime_ns, info.st_size)


@lru_cache(maxsize=32)
def canonical_file_sha(path, expected, mtime, size):
    value = sealed(path, expected, mtime, size)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def request_identity(request, output, day, identity):
    require(isinstance(request, dict), 'CURRENT_REQUEST_REQUIRED')
    root = Path(request['root']).resolve()
    attempt = str(request['attempt_id'])
    expected = root / 'dates' / 'B2' / day / 'attempts' / attempt
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,100}', attempt) is not None
            and request.get('arm') == 'B2' and request.get('day') == day
            and Path(request['output']).resolve() == output == expected / 'output'
            and Path(request['result']).resolve() == expected / 'RESULT.json',
            'CURRENT_ATTEMPT_MISMATCH')
    _, manifest = receipt(request['manifest'], request['manifest_SHA'])
    sources = manifest['execution_sources']
    source = hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(source == manifest.get('execution_SHA') == request.get('implementation_SHA')
            == request.get('deployment_SHA'), 'SOURCE_MISMATCH')
    authority = identity['transport_authority']
    declared = {**manifest['builder_original_sources'], **sources}
    roots = set()
    for name, record in authority['sources'].items():
        path = Path(record['path']).resolve()
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts
                and declared.get(name) == record.get('sha256'), 'TRANSPORT_SOURCE_MISMATCH')
        source_root = path.parents[len(relative.parts) - 1]
        require(source_root / relative == path, 'TRANSPORT_SOURCE_PATH_MISMATCH')
        roots.add(source_root)
        info = path.stat()
        checked_file(str(path), record['sha256'], info.st_mtime_ns, info.st_size)
    require(len(roots) == 1 and bool(authority['sources']), 'TRANSPORT_SOURCE_ROOT_REQUIRED')
    record = authority['certificate']
    _, transport = receipt(record['path'], record['sha256'], output)
    require(transport.get('PASS') is True and transport == identity.get('transport'),
            'TRANSPORT_PASS_REQUIRED')


def assembled_lb(path, output, case, expected_sha, expected_value, identity, request, day):
    path, value = receipt(path, expected_sha, output)
    original.same_case(value, case)
    request_identity(request, output, day, identity)
    require(value.get('PASS') is True and value.get('case_sha') == case
            and value.get('scope') == 'FULL_ORIGINAL_C3A_SIGNED_LAGRANGIAN_LP_DUAL',
            'SCOPE_REQUIRED')
    inclusion = value['independent_decomposition']
    require(inclusion.get('PASS') is True and inclusion.get('case_sha') == case
            and all(inclusion.get(k) is True for k in (
                'all_original_rows_exactly_once', 'all_original_columns_exactly_once',
                'every_original_96_slot_integer_plan_is_in_decomposed_domain',
                'original_coupling_rows_are_relaxed_only_via_signed_multipliers')),
            'ORIGINAL_DOMAIN_REQUIRED')
    transport = identity['transport']
    require(transport.get('PASS') is True
            and transport.get('integer_and_full_LP_domains_identical') is True
            and inclusion.get('original_rows') == transport.get('retained_rows')
            and inclusion.get('original_columns') == transport.get('retained_columns'),
            'ORIGINAL_AXIS_MISMATCH')
    exact = value['independent_exact_certificate']
    require(exact.get('PASS') is True and exact.get('case_sha') == case
            and exact.get('status') == 'EXACT_STORED_RATIONAL_BOUND_CERTIFIED'
            and exact.get('native_objective_used') is False
            and exact.get('native_BestBd_used') is False
            and exact.get('optimality_claimed') is False
            and exact.get('original_checker_byte_preserved') is True
            and exact.get('arbitrary_finite_bounds_used') is False
            and type(value.get('Native_optimize_calls')) is int
            and value['Native_optimize_calls'] == 0
            and all(value.get(k) is False for k in (
                'native_rounded_price_objectives_used_as_proof',
                'restricted_master_objective_used_as_Global_LB',
                'Native_MIP_ObjBound_used_as_exact_Global_LB')),
            'INDEPENDENT_EXACT_BOUND_REQUIRED')
    bound = Fraction(value['exact_Global_LB'])
    require(bound == Fraction(exact['exact_bound']) == Fraction(expected_value),
            'EXACT_BOUND_MISMATCH')
    _, dual = receipt(value['dual_path'], value['dual_sha256'], output)
    require(all(str(int(i)) == i and 0 <= int(i) < inclusion['original_rows']
                and isinstance(v, str) and Fraction(v) != 0 for i, v in dual.items()),
            'DUAL_AXIS_REQUIRED')
    canonical = '\n'.join(f'{i}:{dual[str(i)]}' for i in sorted(map(int, dual))).encode('ascii')
    require(hashlib.sha256(canonical).hexdigest() == value.get('assembled_original_dual_sha256')
            == exact.get('dual_SHA256'), 'DUAL_CONTENT_MISMATCH')
    require(exact.get('certified_domain') == 'CHECKED_ROW_DOMAIN_WITH_FINITE_BOX', 'CERTIFIED_DOMAIN_REQUIRED')
    if exact.get('certified_domain') == 'CHECKED_ROW_DOMAIN_WITH_FINITE_BOX':
        box = exact['finite_box_original_row_implication']
        record = box['proof_file']
        proof_path, proof = receipt(record['path'], record['sha256'], output)
        proof_info = proof_path.stat()
        require(box.get('original_model_bounds_mutated') is False
                and box.get('independent_replay', {}).get('PASS') is True
                and box['independent_replay'].get('all_original_feasible_points_contained') is True
                and proof.get('PASS') is True and proof.get('original_model_bounds_mutated') is False
                and proof.get('original_checker_modified') is False
                and canonical_file_sha(str(proof_path), record['sha256'], proof_info.st_mtime_ns,
                                       proof_info.st_size) == box.get('proof_SHA')
                and proof.get('independent_replay') == box.get('independent_replay'),
                'FINITE_BOX_PROOF_REQUIRED')
    shown = float(bound)
    require(math.isfinite(shown), 'FINITE_BOUND_REQUIRED')
    if Fraction(shown) > bound:
        shown = math.nextafter(shown, -math.inf)
    return dict(exact=str(bound), value=shown, path=str(path), sha256=expected_sha,
                schema='CURRENT_ASSEMBLED_ORIGINAL_EXACT_LB')


def bounds(output, day, request=None, *, source=None, attempt=None):
    output = Path(output).resolve()
    identity = original.optional(output / 'SCIENTIFIC_CASE_IDENTITY.json')
    frontier = original.optional(output / 'frontier/CURRENT_CERTIFIED_STATE.json')
    if not frontier or identity.get('day') != day or identity.get('arm') != 'B2':
        return original.bounds(output, day)
    lb_path = original.under(frontier['LB_certificate_path'], output)
    value = original.read(lb_path)
    if 'independent_exact_certificate' not in value and value.get('scope') != 'FULL_ORIGINAL_C3A_SIGNED_LAGRANGIAN_LP_DUAL':
        return original.bounds(output, day)
    require(isinstance(request, dict), 'CURRENT_REQUEST_REQUIRED')
    require(source is None or source == request.get('implementation_SHA'), 'CURRENT_SOURCE_MISMATCH')
    require(attempt is None or attempt == request.get('attempt_id'), 'CURRENT_ATTEMPT_MISMATCH')
    case = identity['case_sha']
    original.same_case(frontier, case)
    require(frontier.get('case_sha') == case, 'FRONTIER_CASE_REQUIRED')
    result = dict(UB=original.certificate(frontier['UB_certificate_path'], output, case, 'UB',
                  frontier['UB_certificate_sha256'], frontier['exact_UB']))
    result['LB'] = assembled_lb(lb_path, output, case, frontier['LB_certificate_sha256'],
                               frontier['exact_LB'], identity, request, day)
    ub, lb = Fraction(result['UB']['exact']), Fraction(result['LB']['exact'])
    require(ub > 0 and lb <= ub, 'EXACT_BRACKET_INVALID')
    gap = (ub - lb) / abs(ub)
    require(Fraction(frontier['exact_gap']) == gap, 'PUBLISHED_GAP_MISMATCH')
    result['Gap'] = float(gap)
    return result
