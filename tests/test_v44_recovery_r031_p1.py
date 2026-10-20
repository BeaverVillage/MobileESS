from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from v44.common import atomic, read
from v44_recovery_r031 import p1_expansion as p
from v44_recovery_r031 import operations as op


@pytest.mark.parametrize('day,arm,stage,yes', [
    ('2025-05-02','B3','A2',False), ('2025-05-03','B3','A2',True),
    ('2025-05-07','B3','A2',True), ('2025-05-03','B1','A1',False),
    ('2025-05-03','B3','M1',False), ('2025-05-03','B3','M2',False),
    ('2025-05-03','B3','ACTUAL',False)])
def test_only_next_date_b3_a2(day, arm, stage, yes):
    assert p.selected(dict(day=day,arm=arm,stage=stage)) == yes


def graph(extra=False):
    from v42_compact.graph import Graph
    from v42_a_stage_domain_v2.domain import graph_content_hash
    g = Graph(dict(y=((0,0),(0,1)) if extra else ((0,0),),q=(),w=(),f0=(),f1=()),
              dict(r0=(),h=(),r1=()), {}, {}, {}, None)
    g.sha = graph_content_hash(g)
    return g


def fixture():
    old, full = graph(), graph(True)
    state_data = [None] * 8
    state_data[5] = {'unit': old}
    state_data[7] = {'classes': {'class': ['unit']}}
    snapshot = SimpleNamespace(matrix=SimpleNamespace(shape=(3,5)), fingerprint=lambda: 'snapshot')
    qualified = dict(records=[dict(class_id='class',complete_native_primitive_columns=5,
        complete_graph_sha256=full.sha,external_full_block_cache={'path':'test'})])
    cache = dict(graph=full,snapshot=snapshot)
    candidate = dict(class_id='class',price=-1,graph=old,support_sha256=old.sha)
    return state_data, qualified, cache, candidate


def test_second_negative_admits_complete_graph_without_altering_price(tmp_path):
    data, qualified, cache, candidate = fixture()
    expansion = p.Expansion()
    first = expansion.apply([candidate],data,qualified,tmp_path/'S0',lambda w:cache)
    second = expansion.apply([candidate],data,qualified,tmp_path/'S1',lambda w:cache)
    assert first[0] is candidate and second[0]['graph'] is cache['graph']
    assert second[0]['price'] == candidate['price']
    assert candidate['graph'] is data[5]['unit']  # No mutation of prior state.
    assert expansion.columns == 5
    proof=read(tmp_path/'S1/R031_COMPLETE_NATIVE_EXPANSION.json')
    assert proof['all_classes_full_pricing_unchanged']
    assert not proof['phase_I_changed']


def test_larger_blocks_keep_original_witness(tmp_path):
    data, qualified, cache, candidate = fixture()
    qualified['records'][0]['complete_native_primitive_columns'] = p.MAX_COLUMNS_PER_CLASS+1
    expansion = p.Expansion()
    expansion.seen['class'] = 10
    assert expansion.apply([candidate],data,qualified,tmp_path,lambda w:cache)[0] is candidate


def test_total_and_class_caps_keep_original_witness(tmp_path):
    data, qualified, cache, candidate = fixture()
    for promoted, columns in [(set(range(p.MAX_CLASSES)),0),(set(),p.MAX_TOTAL_COLUMNS)]:
        expansion = p.Expansion();expansion.seen['class']=2
        expansion.promoted=promoted;expansion.columns=columns
        assert expansion.apply([candidate],data,qualified,tmp_path,lambda w:cache)[0] is candidate


@pytest.mark.parametrize('kind', ['events','states','compatible','physical','transfers','fixed'])
def test_no_prior_physical_primitive_can_be_lost(kind):
    old, full = graph(), graph(True)
    if kind == 'fixed': old.fixed = 'different'
    elif kind in ('events','states','compatible'): getattr(old,kind)['missing']=(('unknown',0),)
    else: getattr(old,kind)['missing']='payload'
    with pytest.raises(ValueError): p.contains(full,old)


def test_cache_graph_content_drift_fails_closed(tmp_path):
    data, qualified, cache, candidate = fixture()
    qualified['records'][0]['complete_graph_sha256']='wrong'
    expansion=p.Expansion();expansion.seen['class']=1
    with pytest.raises(ValueError,match='IDENTITY_DRIFT'):
        expansion.apply([candidate],data,qualified,tmp_path,lambda w:cache)


@pytest.mark.parametrize('entry', [op.ALGORITHM,op.previous.ENTRY])
def test_all_child_commands_use_r031_and_retain_boundary_token(entry):
    command=op.command(['python','-u','-m',entry,'--worker','request'])
    assert command[3] == op.ENTRY and command[-2:] == ['--algorithm',op.ALGORITHM]


def test_install_delays_stage_changes_until_original_contexts_are_ready(monkeypatch):
    from v44 import worker
    from v44_recovery_r029 import conditional_campaign
    original=worker.a_stage
    monkeypatch.setattr(op.previous,'install',nullcontext)
    monkeypatch.setattr(conditional_campaign,'run_case',lambda request: worker.a_stage is not original)
    with op.install():
        assert worker.a_stage is original
        assert conditional_campaign.run_case({})
        assert worker.a_stage is original


def test_boundary_requires_terminal_case_and_no_live_worker_or_lease(tmp_path,monkeypatch):
    monkeypatch.setattr(op,'CAMPAIGN',tmp_path)
    atomic(tmp_path/'COORDINATOR_LEASE.json',{})
    auth=dict(protected_case_root=str(tmp_path/'case'))
    monkeypatch.setattr(op.base,'workers',lambda:[])
    monkeypatch.setattr(op,'alive',lambda value:False)
    assert not op.handover_ready(auth)
    atomic(tmp_path/'case/RESULT.json',dict(PASS=True))
    assert op.handover_ready(auth)
    monkeypatch.setattr(op.base,'workers',lambda:[{'pid':1}])
    assert not op.handover_ready(auth)


def test_compiler_changes_only_p1_and_restores_scope(tmp_path,monkeypatch):
    from v44 import worker
    from v44_recovery_r029 import p1_acceleration
    namespaces=[]
    def stage(request):
        ns=dict(full_pricing=lambda *a,**k:({'PASS':True},[]))
        namespaces.append(ns)
        return p1_acceleration.compile_p1(None,ns)
    monkeypatch.setattr(worker,'a_stage',stage)
    monkeypatch.setattr(p1_acceleration,'compile_p1',lambda f,ns:ns['full_pricing'])
    with p.install():
        for day in ('2025-05-02','2025-05-03'):
            original=worker.a_stage(dict(day=day,arm='B3',stage='A2'))
            assert (namespaces[-1]['full_pricing'] is original) == (day == '2025-05-02')
    assert worker.a_stage is stage
