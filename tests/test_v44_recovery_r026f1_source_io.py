from pathlib import Path
import mmap,os
import pytest
from v44 import common
from v44_recovery_r026f1.source_io import install,SourceIO

@pytest.fixture
def source(tmp_path):
    p=tmp_path/'pinned'/'module.py';p.parent.mkdir();p.write_bytes(b'alpha\r\n'+bytes(range(128))*500)
    return p

def test_exact_record_and_imported_alias_every_call_rehashes(source):
    from v44.common import record as alias
    expected=common.record(source);code=alias.__code__
    with install([expected]) as pool:
        for _ in range(3):
            assert alias(source)==expected
            common.verify([expected])
        assert pool.report()['record_lookups']==6
        assert pool.report()['full_content_hashes']==6
        assert pool.report()['bytes_hashed']==6*expected['bytes']
        assert not pool.report()['digest_memoization']
    assert alias.__code__ is code

def test_empty_source_and_duplicate_identical_record(source):
    source.write_bytes(b'');r=common.record(source)
    with install([r,r]) as pool:assert common.record(source)==r and len(pool.files)==1

def test_write_delete_and_replace_source_denied_during_scope(source,tmp_path):
    r=common.record(source);other=tmp_path/'replacement';other.write_bytes(b'x')
    with install([r]):
        with pytest.raises(OSError):source.write_bytes(b'bad')
        with pytest.raises(OSError):source.unlink()
        with pytest.raises(OSError):os.replace(other,source)
        assert common.record(source)==r
    source.write_bytes(b'new');assert source.read_bytes()==b'new'

def test_parent_rename_denied_and_released(source):
    target=source.parent.with_name('moved')
    with install([common.record(source)]):
        with pytest.raises(OSError):source.parent.rename(target)
    source.parent.rename(target);assert (target/source.name).exists()

def test_unknown_mutable_runtime_uses_original_live_io(source,tmp_path):
    data=tmp_path/'result.json';data.write_bytes(b'first')
    with install([common.record(source)]) as pool:
        first=common.record(data);data.write_bytes(b'second');second=common.record(data)
        assert first['sha256']!=second['sha256'] and pool.fallbacks==2

def test_prestart_hash_drift_rejected(source):
    row=common.record(source);source.write_bytes(b'drift')
    with pytest.raises(ValueError,match='SOURCE_SHA_DRIFT'):SourceIO([row]).open()
    source.write_bytes(b'released')

def test_failure_restores_original_alias_and_closes_handles(source):
    original=common.record.__code__;r=common.record(source)
    with pytest.raises(RuntimeError,match='test'):
        with install([r]):raise RuntimeError('test')
    assert common.record.__code__ is original
    source.unlink()

def test_existing_writable_mapping_never_hides_content_drift(source):
    row=common.record(source)
    with source.open('r+b') as f:writable=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_WRITE)
    try:
        try:scope=install([row]);pool=scope.__enter__()
        except OSError:return # an existing writer denied the source lease
        try:
            writable[0:1]=b'B';writable.flush()
            with pytest.raises(ValueError,match='SOURCE_SHA_DRIFT'):common.verify([row])
        finally:scope.__exit__(None,None,None)
    finally:writable.close()

def test_nested_scope_fails_closed(source):
    r=common.record(source)
    with install([r]):
        with pytest.raises(PermissionError,match='DUPLICATE_SOURCE_IO_SCOPE'):
            with install([r]):pass

def test_record_path_and_digest_match_for_bytes_and_multiple_sources(source,tmp_path):
    q=tmp_path/'other.py';q.write_bytes(bytes(range(256))*17)
    rows=[common.record(p) for p in [source,q]]
    with install(rows):assert [common.record(Path(r['path'])) for r in rows]==rows

def test_other_process_write_denied_and_manifest_metadata_preserved(source):
    import subprocess,sys,json
    r=common.record(source);manifest=dict(r,relative='test_source.py')
    with install([manifest]):
        assert common.record(source)==r
        code="from pathlib import Path;import sys\ntry: Path(sys.argv[1]).write_bytes(b'tamper')\nexcept PermissionError: sys.exit(7)\n"
        child=subprocess.run([sys.executable,'-c',code,str(source)],capture_output=True)
        assert child.returncode==7
        common.verify([manifest])
