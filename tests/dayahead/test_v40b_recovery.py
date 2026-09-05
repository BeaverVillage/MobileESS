import json
from pathlib import Path

import pytest

from dayahead.v40b import recovery as r


def test_path_failure_requires_exact_infrastructure_signature():
    failure = r.read(r.REPAIR / 'before/days/2025-05-18/FAILURE.json')
    assert r.is_path_failure(failure)
    assert not r.is_path_failure({'error': 'INFEASIBLE', 'traceback': failure['traceback']})
    assert not r.is_path_failure({'error': 'FileNotFoundError', 'traceback': "No such file or directory: 'missing.json'"})


def test_real_shortened_windows_beam_path_can_write_and_replace():
    import ast
    failure = r.read(r.REPAIR / 'before/days/2025-05-18/FAILURE.json')
    original = ast.literal_eval(failure['traceback'].splitlines()[-1].split('directory: ', 1)[1])
    path = Path(original.replace(r.OLD_PASS, r.SHORT_PASS)).with_name('RESTRICTED_DIAG.csv.tmp')
    assert len(str(path)) < 260
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path.with_suffix('.ok')
    try:
        path.write_text('preserved result bytes', encoding='utf-8')
        path.replace(target)
        assert target.read_text(encoding='utf-8') == 'preserved result bytes'
    finally:
        path.unlink(missing_ok=True)
        target.unlink(missing_ok=True)


def test_cache_copy_keeps_stage_bytes_and_rejects_collisions(tmp_path, monkeypatch):
    monkeypatch.setattr(r, 'REPO', tmp_path)
    monkeypatch.setattr(r, 'REPAIR', tmp_path / 'repair')
    root = tmp_path / 'dayahead/cache/v37_may_locked_final'
    src = root / r.OLD_PASS / 'beam' / ('a' * 64) / '2025-05-18/B2/B2/STAGE_1.json'
    # Use Win32 extended paths because pytest's temporary directory is long.
    src = r.extended_path(src)
    src.parent.mkdir(parents=True)
    src.write_bytes(b'{"completed_vehicles":1}')
    rows = r.copy_baseline_cache('2025-05-18')
    assert len(rows) == 1
    dst = Path(rows[0]['target'])
    assert dst.read_bytes() == src.read_bytes()
    assert len(r.copy_baseline_cache('2025-05-18')) == 1
    dst.write_text('bad')
    with pytest.raises(RuntimeError, match='CACHE_COPY_COLLISION'):
        r.copy_baseline_cache('2025-05-18')


def test_preserved_day_rejects_replaced_certificate(tmp_path, monkeypatch):
    monkeypatch.setattr(r, 'ROOT', tmp_path)
    day = '2025-05-01'
    folder = tmp_path / 'days' / day
    folder.mkdir(parents=True)
    cases = {}
    for case in r.CASES:
        p = folder / (case + '.json')
        p.write_text(json.dumps({'status': 'PASS', 'day': day, 'case': case, 'method_SHA': 'frozen'}))
        cases[case] = {'status': 'COMPLETE_NEW_V40A', 'certificate': str(p), 'certificate_SHA': r.sha(p)}
    (folder / 'DAY_CERTIFICATE.json').write_text(json.dumps({'status': 'PASS', 'day': day, 'method_SHA': 'frozen', 'cases': cases}))
    assert r.certified_day(day, 'frozen')['status'] == 'PASS'
    (folder / 'B3.json').write_text('{}')
    with pytest.raises(RuntimeError, match='DAY_CASE_CERTIFICATE_DRIFT'):
        r.certified_day(day, 'frozen')


@pytest.mark.parametrize('count,slots', [(0, 4), (1, 3), (4, 0), (5, 0)])
def test_adopted_workers_consume_existing_capacity(count, slots):
    assert r.available_slots(dict.fromkeys(range(count))) == slots


def test_new_b3_certificate_prevents_second_search():
    method = r.read(r.ROOT / 'V40B_V40A_METHOD_FREEZE.json')['method_SHA']
    result = r.completed_case('2025-05-01', 'B3', method)
    assert result['status'] == 'COMPLETE_NEW_V40A'
