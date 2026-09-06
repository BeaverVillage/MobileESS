from copy import deepcopy
from pathlib import Path
import pytest
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v40h.identity import bind, file_record, IntegrityError
from dayahead.v40i import electrical as e


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(e, 'git', lambda *args: 'committed-source')
    source = tmp_path / 'source.py'; source.write_text('frozen')
    frozen = tmp_path / 'freeze.json'
    write_json(frozen, {'freeze_completed_at': '2026-01-01T00:00:00+00:00'})
    identity = bind('TEST', {'source': file_record(source)}, ['source'])
    run = tmp_path / 'run'; run.mkdir()
    metadata = dict(repository=str(tmp_path), isolated_run_path=str(run), git_commit='committed-source',
        source_input_freeze=file_record(frozen), date='2025-05-01')
    def producer(pre):
        assert read(run / 'PRE_GENERATION_IDENTITY.json')['input_identity'] == identity
        assert read(run / 'GENERATION_STARTED.json')['pre_generation_identity_completed_before_start']
        outputs = {}
        for name in e.OUTPUT_NAMES:
            path = run / name; path.write_text('fresh'); outputs[name] = path
        return outputs, {'fresh_output_paths_were_absent': True, 'old_result_cache_reuse_count': 0,
            'fresh_generation_total_SolveSnap_calls': 23234}
    return identity, metadata, producer, source


def test_durable_pre_freeze_before_actual_generation(tmp_path, monkeypatch):
    pre, meta, producer, _ = fixture(tmp_path, monkeypatch)
    cert = e.certify_run(tmp_path / 'cert.json', lambda: pre, producer, metadata=meta)
    assert cert['pre_generation_freeze_completed_at'] <= cert['pre_generation_identity_completed_at'] <= cert['generation_started_at']
    assert cert['generation_finished_at'] <= cert['post_generation_verification_completed_at'] <= cert['certificate_issued_at']
    assert cert['pre_generation_input_hashes'] == cert['post_generation_input_hashes']


@pytest.mark.parametrize('fault', ['no_solve', 'cache', 'existing'])
def test_old_coefficient_cannot_be_recertified(tmp_path, monkeypatch, fault):
    pre, meta, producer, _ = fixture(tmp_path, monkeypatch)
    def bad(identity):
        outputs, proof = producer(identity)
        if fault == 'no_solve': proof['fresh_generation_total_SolveSnap_calls'] = 0
        elif fault == 'cache': proof['old_result_cache_reuse_count'] = 1
        else: proof['fresh_output_paths_were_absent'] = False
        return outputs, proof
    with pytest.raises(IntegrityError, match='EXECUTION_PROOF'):
        e.certify_run(tmp_path / 'cert.json', lambda: pre, bad, metadata=meta)
    assert not (tmp_path / 'cert.json').exists()


def test_post_input_mutation_preserves_actual_failure_hashes(tmp_path, monkeypatch):
    pre, meta, producer, source = fixture(tmp_path, monkeypatch)
    def bad(identity):
        result = producer(identity); source.write_text('mutated'); return result
    with pytest.raises(IntegrityError, match='PRE_POST_INPUT_MISMATCH'):
        e.certify_run(tmp_path / 'cert.json', lambda: pre, bad, metadata=meta)
    post = read(Path(meta['isolated_run_path']) / 'POST_GENERATION_IDENTITY.json')
    assert post['source_input_hashes'][0]['sha256'] == file_record(source)['sha256']
    assert not post['pre_post_hashes_match']


def test_generation_head_change_never_certified(tmp_path, monkeypatch):
    pre, meta, producer, _ = fixture(tmp_path, monkeypatch)
    def bad(identity):
        result = producer(identity); monkeypatch.setattr(e, 'git', lambda *args: 'changed'); return result
    with pytest.raises(IntegrityError, match='FROZEN_HEAD_CHANGED'):
        e.certify_run(tmp_path / 'cert.json', lambda: pre, bad, metadata=meta)
    assert read(Path(meta['isolated_run_path']) / 'POST_GENERATION_IDENTITY.json')['git_HEAD'] == 'changed'


def test_freeze_after_generation_start_rejected(tmp_path, monkeypatch):
    pre, meta, producer, _ = fixture(tmp_path, monkeypatch)
    path = Path(meta['source_input_freeze']['path'])
    write_json(path, {'freeze_completed_at': '9999-01-01T00:00:00+00:00'})
    meta['source_input_freeze'] = file_record(path)
    with pytest.raises(IntegrityError, match='BEFORE_INPUT_FREEZE'):
        e.certify_run(tmp_path / 'cert.json', lambda: pre, producer, metadata=meta)


def test_previous_certificate_copy_forbidden(tmp_path, monkeypatch):
    pre, meta, producer, _ = fixture(tmp_path, monkeypatch)
    cert = tmp_path / 'cert.json'; cert.write_text('{}')
    with pytest.raises(IntegrityError, match='RECERTIFICATION'):
        e.certify_run(cert, lambda: pre, producer, metadata=meta)


def test_missing_certificate_blocks_31_day_aggregate(tmp_path):
    result = e.aggregate(tmp_path)
    assert result['CERTIFIED_DAYS'] == 0 and result['certificate_status'] == 'FAIL'
    assert len(result['days']) == 31
