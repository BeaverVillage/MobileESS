from copy import deepcopy
from types import SimpleNamespace

import pytest

from v43.common import record
from v43_followup import physical_cache as cache


@pytest.fixture
def relocation(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    pins = {}
    for relative in (*cache.PRODUCERS, cache.WRITER):
        path = new / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(('original ' + relative).encode())
        pins[relative] = record(path)
    def historical(relative):
        return dict(pins[relative], path=str((old / relative).resolve()))
    raw = dict(producer_sources=[historical(r) for r in cache.PRODUCERS],
        cache_writer=historical(cache.WRITER), cache={'sha256': 'unaltered'},
        complete_domain_hashes={'uid': 'full-domain-not-a-solver-point'})
    return old, new, pins, raw


def test_only_source_locations_change_and_original_receipt_is_preserved(relocation):
    old, new, pins, raw = relocation
    saved = deepcopy(raw)
    mapped, aliases = cache.relocated_receipt(raw, historical_root=old,
        current_root=new, pinned_sources=pins)
    assert raw == saved
    assert mapped['cache'] == raw['cache']
    assert mapped['complete_domain_hashes'] == raw['complete_domain_hashes']
    assert mapped['producer_sources'] == [pins[r] for r in cache.PRODUCERS]
    assert len(aliases) == 4
    # Returned metadata cannot mutate the original in-memory receipt either.
    mapped['cache']['sha256'] = 'different'
    assert raw == saved


def test_changed_source_with_the_same_relative_path_is_rejected(relocation):
    old, new, pins, raw = relocation
    (new / cache.PRODUCERS[0]).write_bytes(b'new mathematical domain')
    with pytest.raises(ValueError, match='RELOCATION_BYTES_DRIFT'):
        cache.relocated_receipt(raw, historical_root=old, current_root=new, pinned_sources=pins)


def test_changed_historical_sha_cannot_be_hidden_by_path_relocation(relocation):
    old, new, pins, raw = relocation
    raw['producer_sources'][1]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='RELOCATION_BYTES_DRIFT'):
        cache.relocated_receipt(raw, historical_root=old, current_root=new, pinned_sources=pins)


@pytest.mark.parametrize('replacement', ['other/domain.py', '../escape/domain.py'])
def test_same_basename_or_path_escape_is_not_an_allowed_relocation(relocation, replacement):
    old, new, pins, raw = relocation
    raw['producer_sources'][0]['path'] = str(old / replacement)
    with pytest.raises(ValueError, match='RELATIVE_PATH_DRIFT'):
        cache.relocated_receipt(raw, historical_root=old, current_root=new, pinned_sources=pins)


def test_cache_writer_is_pinned_as_well_as_the_three_physical_producers(relocation):
    old, new, pins, raw = relocation
    (new / cache.WRITER).write_bytes(b'different cache serialization')
    with pytest.raises(ValueError, match='RELOCATION_BYTES_DRIFT'):
        cache.relocated_receipt(raw, historical_root=old, current_root=new, pinned_sources=pins)


def test_an_extra_unrecognized_producer_is_rejected(relocation):
    old, new, pins, raw = relocation
    raw['producer_sources'].append(deepcopy(raw['producer_sources'][0]))
    with pytest.raises(ValueError, match='EXACT_THREE'):
        cache.relocated_receipt(raw, historical_root=old, current_root=new, pinned_sources=pins)


def test_same_bytes_in_an_unpinned_new_source_are_rejected(relocation):
    old, new, pins, raw = relocation
    pins[cache.PRODUCERS[0]] = dict(pins[cache.PRODUCERS[0]], sha256='1' * 64)
    with pytest.raises(ValueError, match='RELOCATION_BYTES_DRIFT'):
        cache.relocated_receipt(raw, historical_root=old, current_root=new, pinned_sources=pins)


def test_live_golden_is_rejected_even_when_result_documents_claim_pass(monkeypatch):
    monkeypatch.setattr(cache.psutil, 'Process', lambda pid: SimpleNamespace(
        create_time=lambda: 123., is_running=lambda: True))
    with pytest.raises(PermissionError, match='LIVE_GOLDEN'):
        cache._completed(dict(pid=77, process_created=123.),
            dict(Gate_A_PASS=True, PR189_NUMERICAL_REPRODUCTION='PASS', finished_UTC='finished'),
            dict(inflight=None, Native_runtime_known=True))


def test_inflight_native_or_missing_numerical_certificate_blocks_reuse():
    for result, reconciliation in [
        (dict(Gate_A_PASS=False), dict(inflight=None, Native_runtime_known=True)),
        (dict(Gate_A_PASS=True, PR189_NUMERICAL_REPRODUCTION='PASS'),
         dict(inflight={'component': 'PHASE_I'}, Native_runtime_known=True)),
    ]:
        with pytest.raises(ValueError, match='COMPLETED_GOLDEN|TERMINATED_RECONCILED'):
            cache._completed(dict(pid=77, process_created=123.), result, reconciliation)


def test_terminated_native0_failure_can_only_prove_local_domains(monkeypatch):
    def absent(pid):
        raise cache.psutil.NoSuchProcess(pid)
    monkeypatch.setattr(cache.psutil, 'Process', absent)
    result = dict(Gate_A_PASS=False, finished_UTC='finished')
    reconciliation = dict(inflight=None, Native_runtime_known=True, calls=0)
    cache._terminated(dict(pid=77, process_created=123.), result, reconciliation)
    with pytest.raises(ValueError, match='NUMERICAL_PASS_REQUIRED'):
        cache._completed(dict(pid=77, process_created=123.), result, reconciliation)
