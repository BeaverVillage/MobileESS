"""Canonical live proofs and direct saved physical restoration; Native0 only."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import json
from types import SimpleNamespace

import pytest

from test_v42_b3_current_c3a_restore import save_v2_packet
from test_v42_physical_prescreen import domain,original_row_fixture
from test_v42_grid_prescreen import fixture as grid_fixture
from v42_may_campaign_native90 import m_model
from v42_native.contracts import digest
from v42_native.mess_domain import BATTERY_FIELDS
from v42_native.mess_domain_verify import verify_original_rows
from v42_pr134_b1.common import read


def graph_for(value):
    return (value.sites,dict(value.initial),value.arcs,
        SimpleNamespace(**dict(zip(BATTERY_FIELDS,value.battery))),{})


def deny_producer(*args,**kwargs):
    raise AssertionError('PRESCREEN_PRODUCER_WAS_CALLED')


def test_physical_and_grid_freeze_return_exact_persisted_canonical_packets(tmp_path):
    value=domain(H=96);A,d=original_row_fixture(value)
    raw=value.scientific_state()
    assert isinstance(raw['initial'][0],tuple) and isinstance(raw['arcs'][0],tuple)
    authority=m_model._freeze_physical(value,tmp_path,A,d)
    assert authority['proof']==read(tmp_path/'EXACT_PHYSICAL_PRESCREEN.json')
    assert isinstance(authority['proof']['initial'][0],list)
    assert isinstance(authority['proof']['arcs'][0],list)
    grid,A,d=grid_fixture()
    assert isinstance(grid.scientific_state()['current_coefficients_and_fixed_controls'],tuple)
    authority=m_model._freeze_grid_prescreen(grid,tmp_path,A,d,None)
    assert authority['proof']==read(tmp_path/'EXACT_GRID_OUTER_PRESCREEN.json')
    assert isinstance(authority['proof']['current_coefficients_and_fixed_controls'],list)


def test_restore_saved_domain_never_calls_producer_or_BFS(monkeypatch):
    import v42_native.mess_domain as module
    import v42_native.mess_domain_verify as verifier
    value=domain(H=96);proof=value.receipt();graph=graph_for(value)
    monkeypatch.setattr(module,'build_domain',deny_producer)
    monkeypatch.setattr(module,'_unit',deny_producer)
    monkeypatch.setattr(module,'verify_domain',deny_producer)
    monkeypatch.setattr(verifier,'verify_domain',deny_producer)
    restored=m_model.restore_physical_domain(proof,graph)
    assert restored.scientific_state()==value.scientific_state()
    assert restored.state_sha==value.state_sha
    assert isinstance(restored.units[0].global_soc[0][1],Fraction)


@pytest.mark.parametrize('attack',('battery','initial','arc','mask','slot','SOC','aggregate'))
def test_restore_rejects_native_key_or_stored_state_drift(attack):
    value=domain(H=96);proof=deepcopy(value.receipt());graph=list(graph_for(value))
    if attack=='battery':graph[3]=SimpleNamespace(**dict(zip(BATTERY_FIELDS,value.battery)),unrelated=True);graph[3].p_limit=299.
    elif attack=='initial':graph[1]={'MESS01':'B'}
    elif attack=='arc':graph[2]=list(graph[2]);graph[2][0]=('A',0,'A',2,None)
    elif attack=='mask':proof['units'][0]['retained_arc_indices'].pop()
    elif attack=='slot':proof['units'][0]['per_slot'][0]['Pch']+=1
    elif attack=='SOC':proof['units'][0]['global_SOC'][0]['lower_exact']='759'
    else:proof['units'][0]['Pch']+=1
    with pytest.raises(ValueError,match='INPUT_KEY_DRIFT|RESTORED_STATE_DRIFT'):
        m_model.restore_physical_domain(proof,tuple(graph))


def test_resealed_unsafe_mask_still_fails_independent_actual_row_verifier():
    value=domain(H=96);proof=value.receipt();graph=graph_for(value);A,d=original_row_fixture(value)
    restored=m_model.restore_physical_domain(proof,graph)
    unit=replace(restored.units[0],retained=restored.units[0].retained[1:])
    mutated=replace(restored,units=(unit,));mutated=replace(mutated,state_sha=digest(mutated.scientific_state()))
    resealed=json.loads(json.dumps(mutated.scientific_state()))
    resealed.update(state_sha=mutated.state_sha,producer_wall_seconds=0.)
    loaded=m_model.restore_physical_domain(resealed,graph)
    with pytest.raises(ValueError,match='MASK_DRIFT'):verify_original_rows(loaded,A,d)


def test_real_in_memory_V2_case_and_restored_domain_verify_without_producer(tmp_path,monkeypatch):
    import v42_native.mess_domain as module
    case=save_v2_packet(tmp_path)
    # This case has live constructor tuples and has NOT passed through JSON.
    assert case.identity['physical_prescreen_authority']['proof']==read(tmp_path/'EXACT_PHYSICAL_PRESCREEN.json')
    assert case.identity['grid_prescreen_authority']['proof']==read(tmp_path/'EXACT_GRID_OUTER_PRESCREEN.json')
    monkeypatch.setattr(module,'build_domain',deny_producer)
    monkeypatch.setattr(module,'_unit',deny_producer)
    assert m_model.verify_case(case)['PASS']
    case.physical_domain=m_model.restore_physical_domain(case.identity['physical_prescreen_authority']['proof'],case.graph)
    assert m_model.verify_case(case)['PASS']
