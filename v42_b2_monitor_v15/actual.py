"""Read completed Fresh AC arrays; never replay, solve, or edit a result."""
from functools import lru_cache
from pathlib import Path
import math
import os
import numpy as np
from v42_pr134_b1.common import read, sha


def stamp(path):
    stat = Path(path).stat()
    return stat.st_mtime_ns, stat.st_size


def sealed(path, expected):
    if sha(path) != expected:
        raise ValueError('ACTUAL_DISPLAY_ARTIFACT_SHA_MISMATCH')
    return read(path)


@lru_cache(maxsize=128)
def receipt(path, expected, file_stamp):
    return sealed(path, expected)


def record_for(result, path):
    # Records already carry absolute paths. Resolve would probe the filesystem
    # for every unrelated model artifact on every poll.
    key = os.path.normcase(os.path.abspath(path))
    matches = [r for r in result.get('files', [])
               if os.path.normcase(os.path.abspath(r['path'])) == key]
    if len(matches) != 1:
        raise ValueError('ACTUAL_DISPLAY_SEALED_ARTIFACT_REQUIRED')
    return matches[0]


@lru_cache(maxsize=128)
def evidence_paths(result_path, result_sha, result_stamp):
    result = receipt(result_path, result_sha, result_stamp)
    evaluation = result.get('evaluation') or result.get('fields', {}).get('Fresh_AC') or {}
    folder = evaluation.get('Fresh', {}).get('folder')
    if not folder:
        return None
    fresh = Path(folder) / 'FRESH_RESULT.json'
    arrays = Path(folder) / 'fresh' / 'OPENDSS_PHASE_ARRAYS.npz'
    return fresh, arrays, record_for(result, fresh), record_for(result, arrays)


@lru_cache(maxsize=128)
def measured(result_path, result_sha, result_stamp, fresh_path, fresh_sha, fresh_stamp,
             arrays_path, arrays_sha, arrays_stamp, arm, day):
    result = sealed(result_path, result_sha)
    if result.get('identity', {}).get('arm') != arm or result.get('identity', {}).get('day') != day:
        raise ValueError('ACTUAL_DISPLAY_RESULT_IDENTITY_MISMATCH')
    fresh = sealed(fresh_path, fresh_sha)
    summary = fresh.get('summary', {})
    if (summary.get('case') != arm or summary.get('day') != day or summary.get('namespace') != 'ACTUAL'
            or fresh.get('NormalAmps_current') is not True):
        raise ValueError('ACTUAL_DISPLAY_FRESH_AUTHORITY_REQUIRED')
    if (fresh.get('converged') is not True or summary.get('convergence_count') != 96
            or summary.get('OpenDSS_solve_count') != 96):
        return dict(available=False, reason='96슬롯 AC 수렴 미확인')
    if sha(arrays_path) != arrays_sha:
        raise ValueError('ACTUAL_DISPLAY_ARRAY_SHA_MISMATCH')
    with np.load(arrays_path, allow_pickle=False) as archive:
        kinds = archive['branch_kinds']
        names = archive['branch_names']
        ratios = archive['phase_current_loading_pu']
        convergence = archive['convergence']
        line = kinds == 'line'
        if (ratios.shape != (96, len(names)) or kinds.shape != names.shape
                or convergence.shape != (96,) or not convergence.all()
                or not line.any() or not np.isfinite(ratios[:, line]).all()
                or (ratios[:, line] < 0).any()
                or any(not str(n).lower().startswith('line.') for n in names[line])):
            raise ValueError('ACTUAL_DISPLAY_EXACT_LINE_AXIS_REQUIRED')
        loading = float(ratios[:, line].max())
        if not math.isclose(loading, summary['rho_max_AC'], rel_tol=0, abs_tol=1e-12):
            raise ValueError('ACTUAL_DISPLAY_SUMMARY_ARRAY_MISMATCH')
    return dict(available=True, loading_pu=loading, percent=100 * loading,
                converged_slots=96, line_phase_count=int(line.sum()), transformer_excluded=True,
                source=dict(result_path=result_path, result_SHA=result_sha,
                            arrays_path=arrays_path, arrays_SHA=arrays_sha, fresh_SHA=fresh_sha))


def metric(row):
    if not row.get('result') or not row.get('result_SHA'):
        return dict(available=False, reason='Actual 평가 대기')
    try:
        result_path = Path(row['result'])
        result_stamp = stamp(result_path)
        evidence = evidence_paths(str(result_path), row['result_SHA'], result_stamp)
        if not evidence:
            return dict(available=False, reason='Actual 평가 결과 없음')
        fresh, arrays, fresh_record, arrays_record = evidence
        return measured(str(result_path), row['result_SHA'], result_stamp,
                        str(fresh), fresh_record['sha256'], stamp(fresh),
                        str(arrays), arrays_record['sha256'], stamp(arrays), row['arm'], row['day'])
    except (ValueError, OSError, KeyError, TypeError) as error:
        return dict(available=False, reason='Actual 근거 확인 필요', error=str(error))


def comparison(dates):
    lookup = {(r['arm'], r['day']): r for r in dates.values()}
    rows = []
    for day in sorted({r['day'] for r in dates.values()}):
        values = {arm: metric(lookup.get((arm, day), {})) for arm in ('B1', 'B2')}
        difference = (values['B2']['percent'] - values['B1']['percent']
                      if all(values[a]['available'] for a in ('B1', 'B2')) else None)
        rows.append(dict(day=day, B1=values['B1'], B2=values['B2'], difference_pp=difference,
                         B1_status=lookup.get(('B1', day), {}).get('status', 'PENDING'),
                         B2_status=lookup.get(('B2', day), {}).get('status', 'PENDING')))
    return dict(rows=rows, B1_available=sum(r['B1']['available'] for r in rows),
                B2_available=sum(r['B2']['available'] for r in rows),
                paired=sum(r['difference_pp'] is not None for r in rows),
                definition='max over 96 Actual AC slots and line phases of abs(current_A) / Line NormalAmps',
                unit='percent', difference_unit='percentage_points', transformer_excluded=True,
                required_converged_slots=96)
