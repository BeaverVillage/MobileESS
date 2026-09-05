import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from dayahead.v40b.windows_paths import install_beam_paths, native_path


pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Windows native path IO')


@pytest.mark.parametrize('day', [f'2025-05-{n:02}' for n in range(18, 32)])
@pytest.mark.parametrize('case,width', [('B2', 2), ('B2', 4), ('B3', 2), ('B3', 4)])
def test_every_remaining_date_uses_real_writers_beyond_max_path(tmp_path, day, case, width):
    from dayahead.tools.run_v35r3e_r1_beam import _write_csv, _json
    from dayahead.tools.run_v39e_may_day import _install_windows_safe_k_archive
    from dayahead.v37 import runner
    import pandas as pd

    _install_windows_safe_k_archive()
    root = tmp_path / ('deep_workspace_' * 5) / ('cache_context_' * 5) / ('f' * 64)
    marker = {'exact_identity': 'same', 'candidate_cache_root': str(root / 'candidates')}
    seen = []

    def original(actual_case, actual_width, workers):
        assert (actual_case, actual_width, workers) == (case, width, 1)
        assert beam.EXECUTION_CACHE_CONTEXT is marker
        for step in range(1, 5):
            parent = f'{case}-ROOT' if step == 1 else f'{case}-S{step-1}-' + 'a' * 16
            path = (beam.CACHE_ROOT / day / case / f'B{width}' / f's{step}' / parent).resolve()
            assert str(path).startswith('\\\\?\\') and len(str(path)) > 300
            path.mkdir(parents=True, exist_ok=True)
            _write_csv(path / 'RESTRICTED_VALUES.csv', [{'candidate_id': 'x', 'objective': 0.5}])
            _json(path / 'SEEDS.json', {'seeds': [1, 2]})
            _json(path / 'CHILD_1.CACHE.json', marker)
            assert pd.read_csv(path / 'RESTRICTED_VALUES.csv').iloc[0]['objective'] == 0.5
            runner._archive_local_attempt(path, '800')
            assert (path / 'RV.K800.A1.csv').is_file()
            seen.append(path)
        return {'value': 0.5, 'identity': marker}

    beam = SimpleNamespace(CACHE_ROOT=root, EXECUTION_CACHE_CONTEXT=marker, _run_case=original)
    install_beam_paths(beam)
    installed = beam._run_case
    install_beam_paths(beam)
    assert beam._run_case is installed
    assert beam._run_case(case, width, 1) == {'value': 0.5, 'identity': marker}
    assert beam.CACHE_ROOT == root and len(seen) == 4


def test_exception_preserved_and_root_restored(tmp_path):
    error = RuntimeError('solver diagnostic must propagate unchanged')
    def fail(*args):
        raise error
    beam = SimpleNamespace(CACHE_ROOT=tmp_path, _run_case=fail)
    install_beam_paths(beam)
    with pytest.raises(RuntimeError) as caught:
        beam._run_case('B2', 2, 1)
    assert caught.value is error and beam.CACHE_ROOT == tmp_path


def test_existing_file_address_and_identity_unchanged(tmp_path):
    p = tmp_path / 'cached.json'
    p.write_bytes(b'{"exact":true}')
    assert native_path(p).read_bytes() == p.read_bytes()
    assert native_path(native_path(p)) == native_path(p)
    assert native_path(Path(r'\\server\share\cache')) == Path(r'\\?\UNC\server\share\cache')
