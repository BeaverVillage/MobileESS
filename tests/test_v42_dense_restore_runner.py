"""Small restore-authority attacks; no native model or optimization calls."""
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import validate_svr11_dense_restore as runner


def transition(monkeypatch):
    previous={'v42_may_campaign_native90/m_model.py':'old-adapter',
        'v42_ultracompact/current_verify.py':'same-math'}
    monkeypatch.setattr(runner,'GENERATION_SHA',runner.digest(previous))
    monkeypatch.setattr(runner,'GENERATION_COMMIT','generation-commit')
    monkeypatch.setattr(runner,'REVIEWED_ADAPTER_SHA','reviewed-canonical-adapter')
    started=dict(source_SHA=runner.GENERATION_SHA,source_commit=runner.GENERATION_COMMIT,
        execution_sources=previous)
    current=dict(previous);current['v42_may_campaign_native90/m_model.py']=runner.REVIEWED_ADAPTER_SHA
    return started,current


def test_only_reviewed_adapter_transition_is_allowed(monkeypatch):
    started,current=transition(monkeypatch)
    current['v42_may_campaign_native90/m_model.py']='reviewed-canonical-adapter'
    result=runner.generation_transition(started,current)
    assert result['changed_execution_files']==['v42_may_campaign_native90/m_model.py']
    assert result['unchanged_C3A_Dense_Physical_Grid_and_static_mathematical_sources']


@pytest.mark.parametrize('attack',['math','set','seal','generation'])
def test_transition_rejects_unsupported_changes(monkeypatch,attack):
    started,current=transition(monkeypatch)
    if attack=='math':current['v42_ultracompact/current_verify.py']='different-math'
    elif attack=='set':current['new.py']='new-source'
    elif attack=='seal':started['execution_sources']=dict(current,other='tamper')
    else:started['source_commit']='different-generation'
    with pytest.raises(PermissionError):runner.generation_transition(started,current)


def test_adapter_transition_rejects_unreviewed_adapter(monkeypatch):
    started,current=transition(monkeypatch)
    current['v42_may_campaign_native90/m_model.py']='unreviewed-adapter'
    with pytest.raises(PermissionError,match='REVIEWED_METADATA_REPAIR'):
        runner.generation_transition(started,current)


def test_self_consistent_but_unreviewed_case_is_rejected(monkeypatch):
    original=dict(matrix='known',domain='known')
    monkeypatch.setattr(runner,'GENERATION_CASE_SHA',runner.digest(original))
    assert runner.checked_generation_identity(dict(original,case_sha=runner.GENERATION_CASE_SHA))==original
    altered=dict(original,matrix='forged')
    with pytest.raises(PermissionError,match='UNREVIEWED_GENERATION_CASE'):
        runner.checked_generation_identity(dict(altered,case_sha=runner.digest(altered)))


def authority(tmp_path,proof=None):
    output=tmp_path/'output';output.mkdir()
    path=output/'DENSE_RESPONSE_EQUIVALENCE.json'
    proof=proof or dict(PASS=True,axes=[1,2])
    runner.atomic(path,proof)
    section=dict(proof=proof,state_sha='math-state',certificate=runner.record(path),
        sources={'v42_ultracompact/response_verify.py':dict(sha256='math-code')})
    return output,{'response_authority':section}


def test_checked_packet_canonical_tuple_list_equivalence(tmp_path):
    output,identity=authority(tmp_path,dict(PASS=True,axes=(1,2)))
    proof=runner.checked_packet_authority(identity,'response_authority',output,
        {'v42_ultracompact/response_verify.py':'math-code'})
    assert proof['axes']==[1,2]


@pytest.mark.parametrize('attack',['bytes','math_source','payload','outside','fail'])
def test_checked_packet_rejects_invalid_authority(tmp_path,attack):
    output,identity=authority(tmp_path);section=identity['response_authority']
    sources={'v42_ultracompact/response_verify.py':'math-code'}
    if attack=='bytes':(output/'DENSE_RESPONSE_EQUIVALENCE.json').write_text('{}',encoding='utf-8')
    elif attack=='math_source':sources['v42_ultracompact/response_verify.py']='changed'
    elif attack=='payload':section['proof']['axes']=[9]
    elif attack=='outside':section['certificate']['path']=str(tmp_path/'DENSE_RESPONSE_EQUIVALENCE.json')
    else:section['proof']['PASS']=False
    with pytest.raises(PermissionError):runner.checked_packet_authority(identity,'response_authority',output,sources)


def security(tmp_path,duplicate=False):
    compact=SimpleNamespace(d=dict(names=np.asarray(['Q[MESS01,S,0]','SOC[MESS01,0]']),
        lower=np.asarray([-np.inf,0.]),upper=np.asarray([np.inf,10.])))
    bound=dict(column=0,name='Q[MESS01,S,0]',old_lower='-inf',old_upper='inf',
        new_lower=-.25,new_upper=.25,proof='SAVED_STRUCTURAL_BOUND')
    runner.atomic(tmp_path/'CURRENT_SECURITY_PRE_C2_ROW_CERTIFICATES.json',[])
    runner.atomic(tmp_path/'CURRENT_SECURITY_PRE_C2_BOUND_CERTIFICATES.json',[bound,bound] if duplicate else [bound])
    runner.atomic(tmp_path/'CURRENT_SECURITY_PRE_C2_SUMMARY.json',dict(removed_security_families={}))
    return compact


def test_saved_security_applies_only_copy_of_original_domain(tmp_path):
    compact=security(tmp_path);battery=object()
    pre=runner.saved_security(compact,(None,None,None,battery),tmp_path)
    assert pre['lower'][0]==-.25 and pre['upper'][0]==.25 and pre['battery'] is battery
    assert np.isneginf(compact.d['lower'][0]) and np.isposinf(compact.d['upper'][0])


def test_saved_security_duplicate_bound_attack(tmp_path):
    compact=security(tmp_path,duplicate=True)
    with pytest.raises(PermissionError,match='BOUND_AXIS'):
        runner.saved_security(compact,(None,None,None,object()),tmp_path)


def test_original_model_and_domain_producers_are_denied():
    import gurobipy as gp
    import v42_native.mess as native
    import v42_native.mess_domain as domain
    original_model=gp.Model;original_native=native.solve;original_domain=domain._cached
    with runner.restore_only_guard() as attempts:
        for function in (gp.Model,native.solve,domain._cached):
            with pytest.raises(PermissionError,match='PRODUCER_DENIED'):function()
        assert len(attempts)==3
    assert gp.Model is original_model and native.solve is original_native and domain._cached is original_domain


def test_run_guard_rejects_changed_immutable_predecessor(tmp_path,monkeypatch):
    original=tmp_path/'old-proof.json';original.write_text('immutable',encoding='utf-8')
    copied=[dict(original=runner.record(original))]
    monkeypatch.setattr(runner,'source_files',lambda:{'runtime':'same'})
    original.write_text('changed',encoding='utf-8')
    with pytest.raises(PermissionError,match='IMMUTABLE_PREDECESSOR_DRIFT'):
        runner.seal_run_guard({'runtime':'same'},{},{},copied,{'PASS':True},[],tmp_path)
