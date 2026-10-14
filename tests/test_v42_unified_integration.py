"""Adversarial common-contract tests, written before joining both agents."""
from copy import deepcopy
from pathlib import Path
import json
import numpy as np
import pytest
from v42_integration.unified_contract import (
    REPORT, BINDING_FIELDS, load_contracts, require_bindings, combine_grid_pq, require_global_bound,
    validate_handoffs)


def test_common_contracts_same_science_case_physics_96_axis():
    manifest=load_contracts()
    require_bindings(manifest['bindings'],manifest['bindings'])
    physics=json.loads((REPORT/'UNIFIED_PHYSICAL_AUTHORITY.json').read_text())
    axis=json.loads((REPORT/'SHARED_TIME_AXIS_CONTRACT.json').read_text())
    assert (physics['IEEE'],physics['installed_GPU'],physics['installed_SVR'])==('IEEE123',780,11)
    assert (axis['slots'],axis['slot_seconds'],axis['planning_native_Dday_slots'])==(96,900,[24,120])
    assert manifest['bindings']['case_sha']!=manifest['historical_reference']['case_sha']
    assert not manifest['reusable_certificates']


def test_user_priority_new_known_hold_and_mess_s1_only():
    from v42_integration.unified_resource import require_heavy_scope
    with pytest.raises(ValueError,match='NEW_KNOWN_A_NATIVE_HOLD'):
        require_heavy_scope('A1_ORIGINAL_P1',dict(stage='A1',arm='B1',day='2025-05-01'))
    require_heavy_scope('MESS:S1:EXACT_REDUCED',dict(planning_stage='M1',scale_stage='S1'))
    for label,context,reason in (
        ('A1_ORIGINAL_P1',dict(stage='A1',arm='B3',day='2025-05-01'),'NEW_KNOWN_A_NATIVE_HOLD'),
        ('A1_ORIGINAL_P1',dict(stage='A1',arm='B1',day='2025-05-02'),'NEW_KNOWN_A_NATIVE_HOLD'),
        ('A2_ORIGINAL_P1',dict(stage='A2'),'FOUR_STAGE'),
        ('MESS:S1:EXACT_REDUCED',dict(planning_stage='M2',scale_stage='S1'),'FOUR_STAGE'),
        ('MESS:S2:EXACT_REDUCED',dict(planning_stage='M1',scale_stage='S2'),'S2_TO_S7')):
        with pytest.raises(ValueError,match=reason):require_heavy_scope(label,context)


@pytest.mark.parametrize('key',BINDING_FIELDS)
def test_a_b_drift_rejected_for_every_shared_binding(key):
    b=load_contracts()['bindings'];bad=dict(b);bad[key]='0'*64
    with pytest.raises(ValueError,match='SHARED_ANCHOR_DRIFT'):require_bindings(bad,b)


def test_contract_file_drift_rejected(tmp_path):
    for p in REPORT.glob('*.json'):(tmp_path/p.name).write_bytes(p.read_bytes())
    with (tmp_path/'UNIFIED_INTERFACE_CONTRACT.json').open('a') as out:out.write(' ')
    with pytest.raises(ValueError,match='CONTRACT_BYTE_DRIFT'):load_contracts(tmp_path)


@pytest.mark.parametrize('key',('physical_sha','interface_sha','time_axis_sha','qos_sha','science_sha','case_sha'))
def test_manifest_cannot_relabel_unchanged_authority_bytes(tmp_path,key):
    for p in REPORT.glob('*.json'):(tmp_path/p.name).write_bytes(p.read_bytes())
    p=tmp_path/'SHARED_SOURCE_CASE_MANIFEST.json';d=json.loads(p.read_text(encoding='utf8'))
    d['bindings'][key]='0'*64;p.write_text(json.dumps(d),encoding='utf8')
    with pytest.raises(ValueError,match='SEMANTIC_SHA_DRIFT|DERIVATION_DRIFT'):load_contracts(tmp_path)


def test_aidc_mess_signed_pq_no_double_count_and_full96_axis():
    a=np.full((96,24),100.);q=np.full((96,24),30.);m=np.zeros_like(a);mq=np.zeros_like(a)
    m[:,0]=20;mq[:,0]=-5;m[:,1]=-10
    p,v=combine_grid_pq(a,q,m,mq)
    assert (p[0,0],v[0,0],p[0,1])==(80,35,110)
    assert p.sum()==a.sum()-m.sum()
    with pytest.raises(ValueError,match='FULL96'):combine_grid_pq(a[:16],q[:16],m[:16],mq[:16])


def test_restricted_and_historical_bound_never_becomes_global():
    case=load_contracts()['bindings']['case_sha']
    for scope in ('ROUTE_FIXED','BEAM_RESTRICTED','ORIGINAL_GLOBAL'):
        with pytest.raises(ValueError,match='NOT_GLOBAL'):
            require_global_bound(dict(value=.4,scope=scope,case_sha=case),case)
    assert require_global_bound(dict(value=.4,scope='REDUCED_CASE_GLOBAL',case_sha=case),case)==.4
    with pytest.raises(ValueError,match='EXACT_CASE'):
        require_global_bound(dict(value=.4,scope='REDUCED_CASE_GLOBAL',case_sha='0'*64),case)


def handoff_fixture():
    b=load_contracts()['bindings'];a=b['aidc_anchor'];m=b['mess_anchor'];rows=[]
    for i,stage in enumerate(('A1','M1','A2','M2')):
        row=dict(stage=stage,producer_anchor_before=dict(AIDC_anchor=a,MESS_anchor=m),
                 unified_input_bindings=dict(b,aidc_anchor=a,mess_anchor=m))
        if stage.startswith('A'):
            row['consumed']=dict(fixed_mess_plan_sha=m);a=str(i+1)*64
        else:
            row['consumed']=dict(fixed_aidc_anchor=a);m=str(i+1)*64
        row.update(result_AIDC_anchor=a,result_MESS_anchor=m);rows.append(row)
    return b,rows


def test_a1_m1_a2_m2_consumes_updated_anchors_and_final_m2():
    b,rows=handoff_fixture()
    result=validate_handoffs(rows,b,b['aidc_anchor'],b['mess_anchor'])
    assert result['final_aidc_anchor']=='3'*64 and result['final_mess_anchor']=='4'*64
    bad=deepcopy(rows);bad[-1]['consumed']['fixed_aidc_anchor']=rows[0]['result_AIDC_anchor']
    with pytest.raises(ValueError,match='AIDC_CONSUMPTION_DRIFT'):
        validate_handoffs(bad,b,b['aidc_anchor'],b['mess_anchor'])


def test_known_unknown_disjoint_and_new_actual_runner_requires_full_shared_contract(tmp_path):
    from v42_integration.fixture_validation import build_fixture
    from v42_integration.coordinator import run_arm
    case=build_fixture(tmp_path/'INPUT')
    b=load_contracts()['bindings'];case.unified_bindings=dict(b)
    # A mismatch is rejected before source/model/Actual use, so an obsolete
    # Known/QoS case cannot silently enter the new live selector.
    with pytest.raises(ValueError,match='SHARED_ANCHOR_DRIFT|CASE_SCIENCE_QOS_DRIFT'):
        run_arm('B3',case,None,tmp_path/'OUT')


def test_original_svr_regcontrol_and_prefix_ac_scope_preserved():
    rows=json.loads((REPORT/'PR230_FRESH16/FRESH_PHYSICAL_SLOTS.json').read_text(encoding='utf8'))
    result=json.loads((REPORT/'PR230_FRESH16_SUMMARY.json').read_text(encoding='utf8'))
    assert result['PASS'] and result['executed_actual_slots']==16
    assert result['full96_Actual_AC_established'] is False
    assert all(r['clock']['manual_tap_or_cap_actions']==0 and r['SVR']['original_seven_AUTO'] for r in rows)
    assert all(len(r['SVR']['devices'])==11 for r in rows)


def test_native_session_cannot_reopen_budget_in_another_ledger(tmp_path):
    from v42_integration.unified_resource import UnifiedResearchBudget
    with pytest.raises(ValueError,match='CANONICAL_SINGLE_LEDGER'):
        UnifiedResearchBudget(tmp_path/'SECOND_AGENT_LEDGER.json')


@pytest.mark.parametrize('label',('A1','A1:REFERENCE_FEASIBILITY_SEED','A1:AUTHORIZED_CHOICES_FEASIBILITY_SEED','A1:FIXED_KNOWN_IIS'))
def test_new_known_native_is_held_for_site_only_scope(label):
    from v42_integration.unified_resource import require_heavy_scope
    with pytest.raises(ValueError,match='NEW_KNOWN_A_NATIVE_HOLD'):
        require_heavy_scope(label,dict(stage='A1',arm='B1',day='2025-05-01'))


@pytest.mark.parametrize('count,slots,partial,axis_bad,nonfinite,expected',[
    (16,16,False,False,False,'EXPLICIT_TIME_AXIS'),
    (16,16,True,False,False,'TEST_AXIS_ACCEPTED'),
    (16,16,True,True,False,'EXPLICIT_TIME_AXIS'),
    (16,16,True,False,True,'FINITE_ACTUAL_PQ'),
    (96,96,True,False,False,'STRICT_PREFIX'),
    (96,16,False,False,False,'TEST_AXIS_ACCEPTED'),
])
def test_fresh_ac_prefix_opt_in_preserves_default_guard(tmp_path,monkeypatch,count,slots,partial,axis_bad,nonfinite,expected):
    from contextlib import contextmanager
    from v42_integration import actual_validation as av
    @contextmanager
    def stop_before_any_ac(*args,**kwargs):
        raise ValueError('TEST_AXIS_ACCEPTED')
        yield
    monkeypatch.setattr(av,'_validated_hardware_context',stop_before_any_ac)
    p=np.zeros((count,12));q=p.copy()
    if nonfinite:p[0,0]=np.nan
    trace=tmp_path/'TRACE.npz'
    np.savez_compressed(trace,PCC_P_kw=p,PCC_Q_kvar=q,sites=np.asarray([f'AIDC{i:02d}' for i in range(1,13)]),
        timestamps_start_epoch_seconds=1746021600.+np.arange(count)*900+(1 if axis_bad else 0))
    source=Path('D:/v42_common_am_qos_integration_20261013/docs/v42_common_am_qos_integration/SOURCE_FREEZE_DDAY_GRID_V5.json')
    with pytest.raises(ValueError,match=expected):
        av.fresh_ac_minimum(Path('D:/v42_may_joint_repair_campaign_20261013/raw/2025-05-01'),tmp_path,tmp_path/'OUT',
            source_freeze=json.loads(source.read_text(encoding='utf8')),
            campaign_manifest=Path('D:/v42_may_joint_repair_campaign_20261013/CAMPAIGN_MANIFEST.json'),
            slots=slots,trace_path=trace,arm='B1',case_scope=dict(partial_actual_trace_authorized=partial))
