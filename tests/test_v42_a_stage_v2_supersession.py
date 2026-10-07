"""Tiny Git provenance fixtures; no scientific model or optimizer runs."""
import json
import subprocess
import pytest
from v42_a_stage_domain_v2 import supersession as seal


@pytest.fixture
def repository(tmp_path,monkeypatch):
    root=tmp_path/'repo';root.mkdir()
    def git(*args):return subprocess.check_output(['git',*args],cwd=root)
    git('init','-q');git('config','user.name','Provenance fixture');git('config','user.email','fixture@example.invalid')
    git('config','core.autocrlf','false')
    path='v42_native/aidc.py';source=root/path;source.parent.mkdir();source.write_bytes(b'old=0\n')
    git('add',path);git('commit','-qm','old source')
    old=source.read_bytes();source.write_bytes(b'old=1\n');git('add',path);git('commit','-qm','exact BASE')
    base=git('rev-parse','HEAD').decode().strip();source.write_bytes(b'old=1\nguard=True\n')
    receipt=tmp_path/'seal.json'
    monkeypatch.setattr(seal,'ROOT',root);monkeypatch.setattr(seal,'BASE',base)
    monkeypatch.setattr(seal,'CHECKPOINT',base);monkeypatch.setattr(seal,'RECEIPT',receipt)
    monkeypatch.setattr(seal,'CHANGES',frozenset([path]))
    monkeypatch.setattr(seal,'ADMIN_BASE_FACTS',frozenset())
    seal.historical_sources.cache_clear()
    manifest=seal.seal()
    yield path,source,receipt,manifest,old
    seal.historical_sources.cache_clear()


def test_source_successor_and_stale_historical_receipt_require_exact_provenance(repository):
    path,source,receipt,manifest,old=repository
    actual=seal.digest(source.read_bytes());previous=seal.digest(old)
    assert seal.assert_successor(path,actual,previous)
    assert seal.assert_historical_source(path,previous)
    assert not manifest['supersession_grants_production_execution']
    assert manifest['historical_production_gates_unchanged']
    assert not seal.assert_successor('unscoped.py',actual)


@pytest.mark.parametrize('corrupt',['current','base','history','diff'])
def test_receipt_claims_cannot_authorize_unproved_hashes(repository,corrupt):
    path,source,receipt,manifest,old=repository
    row=manifest['files'][0]
    key={'current':'current_sha256','base':'base_sha256','history':'historical_sha256','diff':'base_to_current_diff_sha256'}[corrupt]
    row[key]=['0'*64] if corrupt=='history' else '0'*64
    receipt.write_text(json.dumps(manifest))
    with pytest.raises(AssertionError):seal.assert_successor(path,seal.digest(source.read_bytes()),seal.digest(old))


def test_drift_and_fake_previous_digest_are_rejected(repository):
    path,source,receipt,manifest,old=repository
    with pytest.raises(AssertionError,match='UNVERIFIED_HISTORICAL_SHA'):
        seal.assert_successor(path,seal.digest(source.read_bytes()),'0'*64)
    source.write_bytes(source.read_bytes()+b'drift=True\n')
    with pytest.raises(AssertionError,match='UNSEALED_DIFF'):
        seal.assert_successor(path,seal.digest(source.read_bytes()))


def test_unchanged_base_admin_fact_is_sealed_even_with_empty_diff(repository,monkeypatch):
    path,source,receipt,manifest,old=repository
    # The unchanged source stands in for an administrative file in this tiny
    # repository. Its ancestor changed, while current bytes equal exact BASE.
    base=seal.git('show',seal.BASE+':'+path);source.write_bytes(base)
    monkeypatch.setattr(seal,'CHANGES',frozenset())
    monkeypatch.setattr(seal,'ADMIN_BASE_FACTS',frozenset([path]))
    manifest=seal.seal();row=manifest['files'][0]
    assert row['source_policy']=='UNCHANGED_EXACT_BASE_ADMIN_FACT'
    assert row['base_to_current_diff_sha256']==seal.digest(b'')
    assert seal.assert_successor(path,seal.digest(base),seal.digest(old))
    assert seal.assert_historical_source(path,seal.digest(old))
    source.write_bytes(base+b'unapproved=True\n')
    with pytest.raises(AssertionError,match='ADMIN_REQUIRES_UNCHANGED_EXACT_BASE'):
        seal.seal()


def test_admin_checkout_transport_requires_exact_base_derived_bytes(repository,monkeypatch):
    path,source,receipt,manifest,old=repository
    base=seal.git('show',seal.BASE+':'+path)
    (seal.ROOT/'.gitattributes').write_text('*.py text\n')
    source.write_bytes(base.replace(b'\n',b'\r\n'))
    monkeypatch.setattr(seal,'CHANGES',frozenset())
    monkeypatch.setattr(seal,'ADMIN_BASE_FACTS',frozenset([path]))
    row=seal.seal()['files'][0]
    assert row['current_is_verified_BASE_line_ending_transport']
    assert not row['current_is_exact_BASE_blob'] and not row['source_content_changed_from_BASE']
    assert seal.assert_successor(path,seal.digest(source.read_bytes()),seal.digest(old))
