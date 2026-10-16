from copy import deepcopy
from pathlib import Path
import pytest
from v44.common import read,atomic,record,DOC

def test_planning_rejects_svr_coefficients(tmp_path):
    from v44.planning import check_native
    path=tmp_path/'CERT.json';atomic(path,dict(model_version='V42_SVR11_MODEL'))
    native=dict(electrical_certificate=record(path))
    with pytest.raises(PermissionError):check_native(native)
    atomic(path,dict(original_model=True));native['electrical_certificate']=record(path)
    assert check_native(native)==dict(original_model=True)
    with pytest.raises(PermissionError):check_native(dict(native,V44_SVR11=True))

def test_svr12_equipment_is_exact_successful_configuration():
    from v44.svr12 import HARDWARE,ORIGIN
    h=read(HARDWARE/'HARDWARE.json');old=read(ORIGIN/'HARDWARE/HARDWARE.json')
    s=read(h['scenario']['path']);before=read(old['scenario']['path'])
    assert s==before and h['equipment_SHA']==old['equipment_SHA']
    assert (h['SVR_count'],h['RegControl_count'])==(12,43)
    assert len(read(h['thermal']['path'])['rows'])==156
    unit=next(u for u in s['svr']['units'] if u['id']=='IDC01')
    assert unit['cut_element']=='Transformer.mess_idc01_tx' and unit['cut_terminal']==1
    assert unit['sensed_bus']=='mess_idc01_pcc' and unit['phase_kva']==250.
    assert s['svr']['tap_optimization_variables']==0 and s['svr']['Q_injection_devices']==0

def test_svr12_inventory_adapter_changes_only_expected_integer_constants():
    from v44.svr12 import counts
    def example(x):
        a=x+153;b=x+77;c=x+40
        return a,b,c,.95,1.05,'physical equation'
    updated=counts(example,{153:156,77:80,40:43})
    assert updated(0)==(156,80,43,.95,1.05,'physical equation')
    assert updated.__code__.co_code==example.__code__.co_code
    with pytest.raises(ValueError):counts(example,{11:12})

def test_c1_preserves_original_selection_and_scoring():
    from v44.svr12_policy import SVR12CorrectivePolicy
    from v43_corrective.policy import CorrectivePolicy
    assert SVR12CorrectivePolicy.select is CorrectivePolicy.select
    assert SVR12CorrectivePolicy._score is CorrectivePolicy._score
    assert SVR12CorrectivePolicy.current_guard is CorrectivePolicy.current_guard

@pytest.mark.parametrize('slots',[1,25])
def test_production_cannot_shorten_actual_to_canary(slots):
    from v44.execution import actual_slots
    assert actual_slots({})==120
    with pytest.raises(PermissionError):actual_slots(dict(validation_control_slots=slots))

def test_crashed_actual_restarts_in_new_source_context(tmp_path,monkeypatch):
    import v44.campaign as c
    parent=tmp_path/'old';(parent/'ACTUAL').mkdir(parents=True)
    monkeypatch.setattr(c,'stage_request',lambda case,stage:dict(case,stage=stage))
    seen=[]
    result=c.stage_result(dict(resume_of=str(parent),case_root=str(tmp_path/'new')),'ACTUAL',
        lambda request:seen.append(request) or dict(PASS=True))
    assert result['PASS'] and seen[0]['actual_restart_from_independent_source']
    assert 'resume_parent' not in seen[0]

def test_svr12_audit_compaction_retains_raw_proof_and_never_mutates_candidate():
    from v44.svr12 import compact_audit
    from v44.common import digest
    raw=dict(path='fixture_raw.json',bytes=7,sha256='a'*64)
    current=dict(PASS=False,violations=dict(voltage=1),native_state=dict(taps=[1.]),
        full_physical=dict(nodes=[dict(voltage_pu=1.06)]),voltage_nodes=[1.06])
    receipt=dict(PASS=False,current=current,physical_steps=[current,current],
        uid='8632559',input_sha='bound_to_exact_candidate',physical_audit=raw,cache_hit=False)
    original=digest(receipt);compact=compact_audit(receipt)
    assert digest(receipt)==original and 'physical_steps' in receipt
    assert compact['PASS'] is False and compact['current']['violations']==dict(voltage=1)
    assert compact['current']['native_state']==current['native_state']
    assert compact['prefix_proof_reference']==raw and compact['verified_prefix_steps']==1
    assert 'physical_steps' not in compact and 'full_physical' not in compact['current']
    assert 'voltage_nodes' not in compact['current'] and compact['current_candidate_fully_measured']

def test_svr12_cache_hit_keeps_verdict_and_raw_identity_with_compact_storage(monkeypatch):
    from collections import OrderedDict
    from contextlib import nullcontext
    import v44.svr12 as svr
    from v44.svr11_ac import SVR11CurrentAC
    oracle=object.__new__(svr.SVR12CurrentAC);oracle.audit=[];oracle.cache=OrderedDict();oracle.calls=0
    raw=dict(path='fixture_raw',bytes=123,sha256='b'*64)
    def evaluate(self,now,gpu,*,uid=None):
        key='exact_hardware_state_and_input';hit=key in self.cache
        if hit:proof=self.cache[key]
        else:
            self.calls+=1
            proof=dict(PASS=False,current=dict(PASS=False,violations=dict(voltage=1)),
                physical_steps=[dict(PASS=True),dict(PASS=False)],physical_audit=raw)
            self.cache[key]=proof
        result=dict(proof,input_sha=key,uid=uid,time_seconds=now,cache_hit=hit)
        self.audit.append(result);return result
    monkeypatch.setattr(SVR11CurrentAC,'evaluate',evaluate)
    monkeypatch.setattr(svr,'scope',nullcontext)
    first=oracle.evaluate(0,[1],uid='a');second=oracle.evaluate(0,[1],uid='b')
    assert not first['PASS'] and not second['PASS'] and oracle.calls==1
    assert second['uid']=='b' and second['cache_hit']
    assert first['prefix_proof_reference']==second['prefix_proof_reference']==raw
    assert all('physical_steps' not in r for r in oracle.audit+list(oracle.cache.values()))
