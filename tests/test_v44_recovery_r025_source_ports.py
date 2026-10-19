import pytest
from pathlib import Path
from v44.common import record
from v44_recovery_r025.source_io import install as source_io
from v44_recovery_r025.source_ports import install
import v43.common as c43
import v42_pr134_b1.common as c42
import v44.common as c44

def test_all_ports_aliases_keyword_arguments_and_key_order(tmp_path):
    p=tmp_path/'source';p.write_bytes(b'abc');rows=[record(p)]
    aliases=[(m,m.record,m.sha) for m in [c43,c42,c44]]
    with source_io(rows) as pool,install(pool):
        for m,r,s in aliases:
            result=r(**{('p' if m is c42 else 'path'):p})
            assert result==rows[0] and s(**{('p' if m is c42 else 'path'):p})==rows[0]['sha256']
            assert list(result)==(['path','sha256','bytes'] if m is c42 else ['path','bytes','sha256'])
        assert pool.lookups==6

def test_unknown_mutable_paths_reread_each_time(tmp_path):
    p=tmp_path/'source';p.write_bytes(b'abc');data=tmp_path/'data';data.write_bytes(b'one')
    with source_io([record(p)]) as pool,install(pool):
        for m in [c43,c42,c44]:
            before=m.record(data);data.write_bytes(data.read_bytes()+b'x')
            assert m.record(data)!=before and m.sha(data)==record(data)['sha256']

def test_exception_restores_all_codes(tmp_path):
    p=tmp_path/'source';p.write_bytes(b'abc')
    originals=[(getattr(m,name),getattr(m,name).__code__) for m in [c43,c42,c44] for name in ['record','sha']]
    with pytest.raises(RuntimeError):
        with source_io([record(p)]) as pool,install(pool):raise RuntimeError('original')
    assert all(f.__code__ is code for f,code in originals)
