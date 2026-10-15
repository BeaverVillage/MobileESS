"""Windows sharing regression; diagnostics cannot invalidate a valid build."""
import importlib.util
import json
import os
from pathlib import Path
import threading
import pytest

if os.environ.get('V42_PROGRESS_SOURCE_UNDER_TEST'):
    spec = importlib.util.spec_from_file_location('v42_integration.progress_under_test', os.environ['V42_PROGRESS_SOURCE_UNDER_TEST'])
    progress = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(progress)
else:
    from v42_integration import table_v_progress as progress


def test_atomic_snapshot_replaces_a_complete_previous_document(tmp_path):
    path = tmp_path/'LIVE_PROGRESS.json'
    assert progress.write_progress(path, {'phase':'old'})
    assert progress.write_progress(path, {'phase':'new'})
    assert json.loads(path.read_text(encoding='utf8')) == {'phase':'new'}
    assert not list(tmp_path.glob('*.tmp'))


def test_transient_windows_denial_retries_unique_temporary_file(tmp_path, monkeypatch):
    path = tmp_path/'LIVE_PROGRESS.json'
    replace = Path.replace
    calls = []
    def transient(self, target):
        calls.append(self)
        if len(calls) < 3:
            raise PermissionError(13, 'injected sharing violation')
        return replace(self, target)
    monkeypatch.setattr(Path, 'replace', transient)
    monkeypatch.setattr(progress, 'sleep', lambda value: None)
    assert progress.write_progress(path, {'phase':'complete'})
    assert len(calls) == 3 and len(set(calls)) == 1
    assert calls[0].name != 'LIVE_PROGRESS.json.tmp'


def test_persistent_sharing_denial_preserves_snapshot_and_warns_without_aborting(tmp_path, monkeypatch):
    path = tmp_path/'LIVE_PROGRESS.json'
    path.write_text('{"phase":"prior"}', encoding='utf8')
    before = path.read_bytes()
    def denied(*args):
        raise PermissionError(13, 'sharing violation')
    monkeypatch.setattr(Path, 'replace', denied)
    monkeypatch.setattr(progress, 'sleep', lambda value: None)
    assert progress.write_progress(path, {'phase':'next'}) is False
    assert path.read_bytes() == before
    warning = json.loads(path.with_name(path.name+'.warnings.jsonl').read_text(encoding='utf8'))
    assert warning['Raw_or_Native_write'] is False
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.skipif(os.name != 'nt', reason='Windows native reader-sharing regression')
def test_actual_legacy_windows_reader_denial_is_nonfatal_then_recovers(tmp_path):
    path = tmp_path/'LIVE_PROGRESS.json'
    path.write_text('{"phase":"old"}', encoding='utf8')
    with path.open('rb'):
        assert progress.write_progress(path, {'phase':'locked'}) is False
        assert json.loads(path.read_text(encoding='utf8')) == {'phase':'old'}
    assert progress.write_progress(path, {'phase':'recovered'})
    assert json.loads(path.read_text(encoding='utf8')) == {'phase':'recovered'}


def test_display_warning_failure_also_does_not_abort_work(tmp_path, monkeypatch, capsys):
    path = tmp_path/'missing/LIVE_PROGRESS.json'
    def denied(*args, **kwargs):
        raise PermissionError(13, 'directory denied')
    monkeypatch.setattr(Path, 'mkdir', denied)
    assert progress.write_progress(path, {'phase':'next'}) is False
    assert 'TABLE_V_DISPLAY_WRITE_WARNING_V1' in capsys.readouterr().err


def test_concurrent_snapshots_do_not_share_temporary_files(tmp_path):
    path = tmp_path/'LIVE_PROGRESS.json'
    results = []
    threads = [threading.Thread(target=lambda i=i: results.append(progress.write_progress(path, {'writer':i}))) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(results) and len(results) == 8
    assert json.loads(path.read_text(encoding='utf8'))['writer'] in range(8)
    assert not list(tmp_path.glob('*.tmp'))


def test_durable_raw_writer_still_raises_on_replace_failure(tmp_path, monkeypatch):
    from v42_integration.m_engine import _write
    def denied(*args):
        raise PermissionError(13, 'durable write denied')
    monkeypatch.setattr(Path, 'replace', denied)
    with pytest.raises(PermissionError):
        _write(tmp_path/'NATIVE_LEDGER.json', {'calls':[]})


def test_invalid_snapshot_value_is_a_programming_error(tmp_path):
    with pytest.raises(ValueError):
        progress.write_progress(tmp_path/'LIVE_PROGRESS.json', {'value':float('nan')})


def test_snapshot_retains_existing_numpy_and_path_serialization(tmp_path):
    import numpy as np
    path = tmp_path/'LIVE_PROGRESS.json'
    assert progress.write_progress(path, {'rows':np.int64(23), 'path':tmp_path})
    assert json.loads(path.read_text(encoding='utf8')) == {'rows':23, 'path':str(tmp_path)}
