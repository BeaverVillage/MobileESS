from contextlib import contextmanager
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import scipy.sparse as sp
import pytest
from v44_recovery_r022.phase_rebuild import Rebuild,ExactCache,key,content_key,install,stage_scope
from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective


def snap():
    return LinearSnapshot(sp.csr_matrix([[1.]]),np.zeros(1),np.ones(1),np.array(['<']),
        np.ones(1),np.array(['C']),(Objective('rho',((0,Fraction(1)),),0),)).require()


def test_cached_result_is_independent_and_bounded():
    cache=ExactCache(100)
    first=cache.call('x',lambda:{'values':[1]});first['values'][0]=7
    second=cache.call('x',lambda:pytest.fail('unnecessary recompute'))
    assert second=={'values':[1]}
    second['values'].append(2)
    assert cache.call('x',lambda:None)=={'values':[1]}
    for i in range(10):cache.call(i,lambda:{'value':'a'*30})
    assert cache.size<=100 and cache.evictions>0


def test_content_key_preserves_all_array_bytes_but_ignores_alias_layout():
    a=np.array([1.,2.]);shared=(a,a)
    assert content_key(shared)==content_key((a.copy(),a.copy()))
    assert content_key(shared)!=content_key((a,a+1))
    assert content_key((np.array([0.]),))!=content_key((np.array([-0.]),))


def test_cached_block_roundtrip_does_not_invalidate_unchanged_projection_proof():
    import pickle
    memo=Rebuild();s=snap();B=sp.csr_matrix([[2.]])
    units=[dict(id='u',uid='u',optional=False,stay_count=False,v={'x':{0:('v',0)}})]
    args=(s,B,units,s,B,units,1)
    assert memo.verify(*args)['PASS']
    other=pickle.loads(pickle.dumps((s,B,units),protocol=5))
    assert memo.verify(s,B,units,*other,1)['PASS'] and memo.proofs.hits==1


def test_native_blocks_hash_actual_graph_and_static_inputs_not_graph_sha():
    memo=Rebuild();calls=[]
    memo.original_block=lambda *args,**kwargs:calls.append((args,kwargs)) or {'matrix':[1]}
    graph=SimpleNamespace(sha='same',events={'y':(1,)})
    data=({'day':'2025-05-03'},{},{},{},{},{},None,{'classes':{'a':('u',)}})
    memo.context=key((data[:5],data[6:]))
    memo.native_block(data,'a',graph,('axis',))
    memo.native_block(data,'a',graph,('axis',))
    assert len(calls)==1
    graph.events['y']=(1,2)
    memo.native_block(data,'a',graph,('axis',))
    memo.native_block(data,'a',graph,('axis',),averaged=False)
    memo.native_block(data,'a',graph,('other',))
    data[0]['day']='2025-05-04';memo.context=key((data[:5],data[6:]))
    memo.native_block(data,'a',graph,('axis',))
    assert len(calls)==5


def test_exact_projection_reused_only_for_byte_identical_proof_inputs():
    memo=Rebuild();s=snap();B=sp.csr_matrix([[2.]])
    units=[dict(id='u',uid='u',optional=False,stay_count=False,v={'x':{0:('v',0)}})]
    args=(s,B,units,s,B,units,1)
    assert memo.verify(*args)['PASS'] and memo.verify(*args)['PASS']
    assert memo.proofs.hits==1 and memo.proofs.misses==1
    with pytest.raises(ValueError,match='COUPLING_COEFFICIENT_LOSS'):
        memo.verify(s,sp.csr_matrix([[3.]]),units,s,B,units,1)
    with pytest.raises(ValueError,match='ROW_SUM_PROJECTION_OBSTRUCTION'):
        memo.verify(replace(s,rhs=np.array([2.])),B,units,s,B,units,1)


def test_intermediate_graph_updates_match_original_and_ledger_is_built_once(monkeypatch):
    from v42_a_stage_phase1 import backend
    from v42_a_stage_domain_v2 import active
    calls=[]
    def ledger(data,domains,records):calls.append(1);return {'graphs':dict(data[5]),'records':records}
    monkeypatch.setattr(backend,'_ledger',ledger);monkeypatch.setattr(active,'_ledger',ledger)
    data=({}, {}, {}, {}, {}, {'u':'old','v':'other'},None,{'classes':{'a':('u',),'b':('v',)}})
    expected=data
    for graph in ['one','two','three']:expected,last=backend.update_graph(expected,{},'a',graph)
    assert len(calls)==3
    memo=Rebuild();actual=data
    for graph in ['one','two','three']:actual,lazy=memo.update_graph(actual,{},'a',graph)
    assert actual==expected and lazy is None and len(calls)==3
    memo.compiled=lambda base,grows,n,axes,data,domains,ledger,candidates:ledger
    assert memo.build(None,(),0,{},actual,{},lazy,[])==last
    assert len(calls)==4 and memo.ledger_rebuilds==1


@pytest.mark.parametrize('arm,stage',[('B1','A2'),('B3','A2'),('B1','A1'),('B0','A1')])
def test_both_arms_a2_route_to_the_same_stage_local_performance_scope(monkeypatch,arm,stage):
    from v44 import worker
    from v44_recovery_r022 import phase_rebuild as module
    entered=[]
    @contextmanager
    def scope(request):entered.append((request['arm'],request['stage']));yield
    monkeypatch.setattr(module,'stage_scope',scope)
    monkeypatch.setattr(worker,'a_stage',lambda request,**kwargs:request['stage'])
    with install():assert worker.a_stage(dict(day='2025-05-03',arm=arm,stage=stage),m1={})==stage
    assert entered==[(arm,stage)]


def test_may02_running_case_is_outside_new_scope(monkeypatch):
    from v44 import worker
    from v44_recovery_r022 import phase_rebuild as module
    monkeypatch.setattr(module,'stage_scope',lambda request:pytest.fail('protected date patched'))
    monkeypatch.setattr(worker,'a_stage',lambda request:True)
    with install():assert worker.a_stage(dict(day='2025-05-02',arm='B3',stage='A2'))


def test_each_stage_has_an_independent_cache_and_restores_all_bindings(tmp_path):
    from v42_a_stage_compact_rowgen import assembly
    from v42_a_stage_canary import phase
    from v42_may_campaign_native90 import a_stage
    original=(assembly.build,phase.build,phase.update_graph,a_stage.group)
    req=dict(root=str(tmp_path),output=str(tmp_path/'OUTPUT'))
    with stage_scope(req) as first:
        assert phase.build.__self__ is first and assembly.build.__self__ is first
        first.proofs.call('x',lambda:1)
    assert original==(assembly.build,phase.build,phase.update_graph,a_stage.group)
    with stage_scope(req) as second:assert second.proofs.hits==0 and not second.proofs.values


def test_fresh_phase_group_freezes_weights_and_preserves_native_solve_body(tmp_path,monkeypatch):
    from v42_a_stage_canary import phase
    from v42_may_campaign_native90 import a_stage
    def run(native,state,day,certified_zero_point=None):
        return elastic_master(state['compact'],state['grows']).weights
    monkeypatch.setattr(phase,'run',run)
    with stage_scope(dict(root=str(tmp_path))):
        ns=a_stage.group(phase,('activate','run'))
        state=dict(reference=snap(),compact=replace(snap(),matrix=sp.csr_matrix([[1024.]])),grows=(0,))
        assert ns['run'](None,state,'2025-05-03')==(Fraction(1),)
