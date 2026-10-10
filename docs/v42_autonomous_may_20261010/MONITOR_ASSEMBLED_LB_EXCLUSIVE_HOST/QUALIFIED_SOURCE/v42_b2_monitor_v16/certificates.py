"""Observe certificates already produced by this worker; no optimization."""
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
import math
from v42_pr134_b1.common import read, sha


def optional(path):
    try:
        return read(path) if Path(path).is_file() else {}
    except (OSError, ValueError):
        return {}


def under(path, output):
    path = Path(path).resolve()
    if not path.is_relative_to(Path(output).resolve()):
        raise ValueError('DISPLAY_CERTIFICATE_OUTSIDE_CURRENT_WORKER')
    return path


@lru_cache(maxsize=128)
def point_sha(path, mtime, size):
    return sha(path)


def same_case(value, case):
    if isinstance(value, dict):
        if 'case_sha' in value and value['case_sha'] != case:
            raise ValueError('DISPLAY_CERTIFICATE_CASE_MISMATCH')
        for child in value.values():
            same_case(child, case)
    elif isinstance(value, list):
        for child in value:
            same_case(child, case)


def certificate(path, output, case, kind, expected_sha=None, expected_value=None):
    path = under(path, output)
    if expected_sha and sha(path) != expected_sha:
        raise ValueError('DISPLAY_CERTIFICATE_SHA_MISMATCH')
    value = read(path)
    same_case(value, case)
    if value.get('PASS') is not True:
        raise ValueError('DISPLAY_CERTIFICATE_PASS_REQUIRED')
    if kind == 'UB':
        replay = value.get('original_matrix_and_96_slot_physical_replay', {})
        if (value.get('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact') is not True
                or replay.get('PASS') is not True or replay.get('case_sha') != case):
            raise ValueError('DISPLAY_STRICT_UB_REPLAY_REQUIRED')
        point = under(value['point_path'], output)
        stat = point.stat()
        if point_sha(str(point), stat.st_mtime_ns, stat.st_size) != value['point_file_sha256']:
            raise ValueError('DISPLAY_UB_POINT_SHA_MISMATCH')
        exact = Fraction(value['exact_Global_UB'])
    else:
        if (value.get('case_sha') != case or value.get('status') != 'EXACT_STORED_RATIONAL_BOUND_CERTIFIED'
                or value.get('native_objective_used') is not False
                or value.get('native_BestBd_used') is not False):
            raise ValueError('DISPLAY_INDEPENDENT_LB_REQUIRED')
        exact = Fraction(value.get('exact_Global_LB', value['exact_bound']))
    if expected_value is not None and exact != Fraction(expected_value):
        raise ValueError('DISPLAY_PUBLISHED_BOUND_MISMATCH')
    shown = float(exact)
    if not math.isfinite(shown):
        raise ValueError('DISPLAY_FINITE_BOUND_REQUIRED')
    if (kind == 'LB' and Fraction(shown) > exact) or (kind == 'UB' and Fraction(shown) < exact):
        shown = math.nextafter(shown, -math.inf if kind == 'LB' else math.inf)
    return dict(exact=str(exact), value=shown, path=str(path), sha256=sha(path))


def bounds(output, day):
    output = Path(output)
    identity = optional(output / 'SCIENTIFIC_CASE_IDENTITY.json')
    if identity.get('day') != day or identity.get('arm') != 'B2':
        return {}
    case = identity['case_sha']
    frontier = optional(output / 'frontier/CURRENT_CERTIFIED_STATE.json')
    result = {}
    if frontier:
        same_case(frontier, case)
        if frontier.get('case_sha') != case:
            raise ValueError('DISPLAY_FRONTIER_CASE_REQUIRED')
        for kind in ('UB', 'LB'):
            result[kind] = certificate(frontier[kind+'_certificate_path'], output, case, kind,
                frontier[kind+'_certificate_sha256'], frontier['exact_'+kind])
        if Fraction(result['UB']['exact']) <= 0 or Fraction(result['LB']['exact']) > Fraction(result['UB']['exact']):
            raise ValueError('DISPLAY_EXACT_BRACKET_INVALID')
        exact_gap = (Fraction(result['UB']['exact'])-Fraction(result['LB']['exact']))/abs(Fraction(result['UB']['exact']))
        if Fraction(frontier['exact_gap']) != exact_gap:
            raise ValueError('DISPLAY_PUBLISHED_GAP_MISMATCH')
        result['Gap'] = float(exact_gap)
        return result
    for kind, names in (
        ('UB', ('BEST_STRICT_UB_CERTIFICATE.json','INITIAL_STRICT_UB_CERTIFICATE.json','SAME_DAY_NATIVE_SEED_STRICT_REPLAY.json')),
        ('LB', ('BEST_EXACT_LB_CERTIFICATE.json','INITIAL_EXACT_LB_CERTIFICATE.json'))):
        path = next((output / name for name in names if (output / name).is_file()), None)
        if path:
            result[kind] = certificate(path, output, case, kind)
    if 'UB' in result and 'LB' in result:
        ub, lb = Fraction(result['UB']['exact']), Fraction(result['LB']['exact'])
        if ub <= 0 or lb > ub:
            raise ValueError('DISPLAY_EXACT_BRACKET_INVALID')
        result['Gap'] = float((ub-lb)/abs(ub))
    return result


def enrich(worker):
    request = optional(worker.get('request', ''))
    output = request.get('output')
    ledger = optional(Path(request['result']).parent/'NATIVE_RUNTIME_LEDGER.json') if request.get('result') else {}
    active = ledger.get('inflight') or {}
    track = active.get('track')
    label = ('초기 정수해 탐색' if track == 'M_SEED' else
             '최초 독립 하한 계산' if track == 'M_LB' else None)
    status = dict(UB_reason='독립 물리 검증을 마친 해 대기',
                  LB_reason='독립 하한 인증서 대기', phase_label=label,
                  solver_bounds_available=False,
                  solver_bounds_reason='현재 워커 콜백이 Solver UB·LB·Gap을 보고하지 않음')
    try:
        evidence = bounds(output, worker['day']) if output else {}
        # The certificate may precede the next algorithm progress callback.
        for kind, field in (('UB','UB'),('LB','independent_Global_LB')):
            if kind in evidence:
                worker[field] = evidence[kind]['value']
                status[kind+'_reason'] = '현재 날짜 독립 인증서 확인'
                status[kind+'_certificate'] = evidence[kind]
        if 'Gap' in evidence:
            worker['Certified_Gap'] = evidence['Gap']
            worker['global_gap_display'] = dict(available=True,value=evidence['Gap'],
                reason='현재 날짜 검증된 해와 독립 하한 인증서 기준',
                UB=worker['UB'],independent_Global_LB=worker['independent_Global_LB'],
                target=.03,source='CURRENT_WORKER_CERTIFICATE_FILES')
        elif not worker.get('global_gap_display',{}).get('available'):
            if track == 'M_SEED':
                status.update(UB_reason='첫 정수해 탐색 중 · 독립 물리 검증 전',
                              LB_reason='초기 해 검증 후 독립 하한 계산')
            worker['global_gap_display']['reason'] = ('UB·LB 인증 전 · 초기 정수해 탐색 중' if track == 'M_SEED' else
                '독립 LB 인증 대기' if 'UB' in evidence else 'UB·LB 독립 인증 대기')
    except (OSError, ValueError, KeyError, TypeError, ZeroDivisionError) as error:
        status['certificate_error'] = str(error)
        worker['global_gap_display'] = dict(available=False,value=None,reason='인증 근거 확인 필요',target=.03)
        worker.update(UB=None,independent_Global_LB=None,Certified_Gap=None)
    worker['bound_status'] = status
    return worker
