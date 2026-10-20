import struct
import pytest
from v44_recovery_r025b import cpu_placement as placement


def row(logical,efficiency,group=0,flags=0):
    return dict(logical=logical,core=logical,efficiency_class=efficiency,group=group,flags=flags)


def test_fast_class_within_allowed_mask_only():
    rows=[row(0,1),row(1,1),row(2,0),row(3,0)]
    assert placement.preferred_allowed(rows,[1,2,3])==[1]
    assert placement.preferred_allowed(rows,[2,3])==[2,3]


def test_foreign_reserved_cores_and_multigroup_not_overridden():
    rows=[row(0,1,flags=2),row(1,1,flags=6),row(2,0)]
    assert placement.preferred_allowed(rows,[0,1,2])==[1]
    assert placement.preferred_allowed([row(0,1),row(1,0,group=1)],[0,1])==[0,1]


def test_parser_known_fields_and_truncation():
    raw=struct.pack('<IIIHBBBBBB',32,0,256,0,3,2,0,0,1,0)+b'\0'*12
    parsed=placement.parse_cpu_sets(raw)
    assert parsed[0]['logical']==3 and parsed[0]['efficiency_class']==1
    for invalid in [raw[:7],raw[:23],struct.pack('<II',0,0)]:
        with pytest.raises(ValueError):placement.parse_cpu_sets(invalid)


def test_affinity_and_exception_restore_exact_original(monkeypatch):
    state=[0,1,2,3]
    class Process:
        def cpu_affinity(self,value=None):
            if value is not None:state[:]=value
            return state.copy()
    monkeypatch.setattr(placement.psutil,'Process',Process)
    monkeypatch.setattr(placement,'windows_cpu_sets',lambda:[row(0,1),row(1,1),row(2,0),row(3,0)])
    monkeypatch.setattr(placement,'claim_core',lambda row:object())
    monkeypatch.setattr(placement,'release_core',lambda handle:None)
    with pytest.raises(RuntimeError):
        with placement.actual_cpu_scope() as metadata:
            assert state==[0] and metadata['compute_threads']==1
            raise RuntimeError('original failure')
    assert state==[0,1,2,3] and metadata['restored']


def test_query_failure_fails_closed_and_restores_original_affinity(monkeypatch):
    class Process:
        def cpu_affinity(self,value=None):assert value is None;return [1,3]
    monkeypatch.setattr(placement.psutil,'Process',Process)
    def fail():raise OSError('CPU API unavailable')
    monkeypatch.setattr(placement,'windows_cpu_sets',fail)
    with pytest.raises(OSError,match='CPU API unavailable'):
        with placement.actual_cpu_scope():raise AssertionError('must not dispatch without placement')


def test_four_distinct_physical_cores_p_first_and_smt_deduplicated():
    rows=[row(0,1),dict(row(1,1),core=0),row(2,1),row(4,1),row(6,1),row(8,0)]
    assert [r['logical'] for r in placement.physical_candidates(rows,list(range(10)))]==[0,2,4,6,8]


@pytest.mark.parametrize('busy,expected',[(set(),[0,1,2,3]),({0,1},[2,3,4,5]),({0,1,2,3},[4,5,6,7])])
def test_e_fallback_only_when_performance_capacity_reserved(monkeypatch,busy,expected):
    state=list(range(8));released=[]
    class Process:
        def cpu_affinity(self,value=None):
            if value is not None:state[:]=value
            return state.copy()
    monkeypatch.setattr(placement.psutil,'Process',Process)
    monkeypatch.setattr(placement,'windows_cpu_sets',lambda:[row(i,1 if i<4 else 0) for i in range(8)])
    monkeypatch.setattr(placement,'claim_core',lambda row:None if row['logical'] in busy else row['logical']+1)
    monkeypatch.setattr(placement,'release_core',lambda handle:released.append(handle))
    with placement.compute_cpu_scope(4) as metadata:
        assert state==expected
        with placement.compute_cpu_scope(1) as nested:assert state==expected[:1]
        assert state==expected and nested['restored']
    assert state==list(range(8)) and len(released)==4 and metadata['restored']


def test_real_os_core_lock_conflict_release():
    rows=placement.physical_candidates(placement.windows_cpu_sets(),placement.psutil.Process().cpu_affinity())
    handle=placement.claim_core(rows[-1]);assert handle is not None
    try:assert placement.claim_core(rows[-1]) is None
    finally:placement.release_core(handle)
    handle=placement.claim_core(rows[-1]);assert handle is not None
    placement.release_core(handle)
