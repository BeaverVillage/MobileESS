"""Bounded-run contracts; no heavy Optimize or May performance claim."""
from dataclasses import replace
from pathlib import Path
import hashlib,subprocess
import pytest
from v42_integration.partial_canary import (freeze_variant,preregister_coverage,coverage_estimate,classify_a1,
    CORE_FILES,PARENT)
from v42_integration.policy import ReservationLedger
from test_v42_known_unknown_contract import frozen,participant
from test_v42_experimental_control import metadata

CONTRACTS=('REAL_B1_A1_KNOWN_FREEZE','UNKNOWN_PREPLANNED_POLICY_ONLY','MAY01_12_AIDC_SOURCE_BINDING',
 'NO_ACTUAL_FUTURE_UID_AT_PLANNING','PARTIAL_WINDOW_NO_FALSE_FULL96_PASS','SAME_INITIAL_STATE_R0_R1_R2_R3',
 'PREPLACE_VS_MIGRATION_ABLATION','KNOWN_UNKNOWN_UID_METRICS_DISJOINT','NO_DOUBLE_COUNTED_GPUH',
 'SAME_ROW_FALLBACK_EXECUTED','NO_UNAUTHORIZED_MIGRATION','ORIGINAL_FRESH_AC_SOURCE_PRESERVED')


@pytest.mark.parametrize('contract',CONTRACTS,ids=CONTRACTS)
def test_canary_contract(contract,tmp_path,monkeypatch):
    root=Path(__file__).resolve().parents[1]
    if contract=='REAL_B1_A1_KNOWN_FREEZE':
        assert classify_a1({'FULL_feasible':False})[0]=='A1_NO_ACCEPTABLE_INCUMBENT'
        assert classify_a1(dict(FULL_feasible=True,rho=.65,local_bound=.64,P2_calls=0))[0]=='PARTIAL_A1_FEASIBLE_NOT_CERTIFIED'
        for name in CORE_FILES:
            assert (root/'v42_integration'/name).read_bytes()==subprocess.check_output(['git','show',PARENT+':v42_integration/'+name],cwd=root)
        return
    if contract in ('PARTIAL_WINDOW_NO_FALSE_FULL96_PASS','ORIGINAL_FRESH_AC_SOURCE_PRESERVED'):
        for name in ('coordinator.py','actual_validation.py','dday_boundary.py'):
            assert (root/'v42_integration'/name).read_bytes()==subprocess.check_output(['git','show',PARENT+':v42_integration/'+name],cwd=root)
        return
    if contract=='KNOWN_UNKNOWN_UID_METRICS_DISJOINT':
        from test_v42_known_unknown_contract import test_NO_FUTURE_LEAKAGE_NO_DUPLICATE_CC4_DEPLETION_KNOWN_UNKNOWN_DISJOINT_ACTION_LEDGER
        test_NO_FUTURE_LEAKAGE_NO_DUPLICATE_CC4_DEPLETION_KNOWN_UNKNOWN_DISJOINT_ACTION_LEDGER();return
    if contract=='SAME_ROW_FALLBACK_EXECUTED':
        from test_v42_frozen_alternatives import test_FIRST_FEASIBLE_FROZEN_FALLBACK_SELECTED
        test_FIRST_FEASIBLE_FROZEN_FALLBACK_SELECTED(monkeypatch);return
    if contract=='NO_UNAUTHORIZED_MIGRATION':
        from test_v42_known_unknown_contract import test_unknown_frozen_checkpoint_all_links_and_pinned_destination_guard
        test_unknown_frozen_checkpoint_all_links_and_pinned_destination_guard();return
    provider,p=frozen();job,receipt=participant(provider);m=metadata(provider,job,receipt)
    if contract in ('MAY01_12_AIDC_SOURCE_BINDING','NO_ACTUAL_FUTURE_UID_AT_PLANNING'):
        caps={'AIDC'+str(i):65 for i in range(12)};racks={s:(65,) for s in caps}
        records={'K':replace(job,uid='K',origin_unknown=False)}
        conditions,audit=preregister_coverage(records,caps,racks)
        assert len(audit['compatible_destinations'])==12 and sum(caps.values())==780
        assert all(len(r['compatible_sites'])==12 and r['time_slots']==list(range(16)) for r in conditions)
        assert coverage_estimate(caps,racks)['candidate_variants']>1000000
        with pytest.raises(ValueError,match='NO_ACTUAL_FUTURE'):preregister_coverage({job.uid:job},caps,racks)
    elif contract=='UNKNOWN_PREPLANNED_POLICY_ONLY':
        v=freeze_variant(p,'FROZEN');v.set_current_resources(0,{'A':0,'B':0})
        monkeypatch.setattr(v.packet,'evaluate',lambda *a,**k:(_ for _ in ()).throw(AssertionError('new objective')))
        assert v.select(m,receipt,0,ReservationLedger({'A':8,'B':8}))['online_grid_horizon_evaluations']==0
    elif contract=='SAME_INITIAL_STATE_R0_R1_R2_R3':
        variants=[freeze_variant(p,mode) for mode in ('REFERENCE_ONLY','REFERENCE_ONLY','FROZEN','NO_PREPLACE')]
        assert all(v.bindings==p.bindings and v.packet is p.packet for v in variants)
        assert variants[2].sha!=variants[3].sha
        for i,v in enumerate(variants):
            path=tmp_path/(str(i)+'.json');v.save(path);assert type(v).load(path,bindings=p.bindings).sha==v.sha
    elif contract=='PREPLACE_VS_MIGRATION_ABLATION':
        v=freeze_variant(p,'NO_PREPLACE')
        assert all(r['action']!='PREPLACE' for t in v.expanded_document()['templates'] for r in t['ordered_actions'])
        assert [(t['template_id'],[r['action'] for r in t['ordered_actions']]) for t in v.expanded_document()['templates'] if t['state']=='RUNNING']==[
            (t['template_id'],[r['action'] for r in t['ordered_actions']]) for t in p.expanded_document()['templates'] if t['state']=='RUNNING']
    elif contract=='NO_DOUBLE_COUNTED_GPUH':
        from v42_integration.action_metrics import unknown_actual_metrics
        m.update(experimental_contract=dict(eligible_for_contract=True,participant=True),reference_start_seconds=0,
            additional_start_delay_seconds=900)
        actual=dict(carryout={'controller':{'metadata':{job.uid:m},'decisions':{}}},rule_consumption_receipt=[],
            queue_ledger=[dict(job_uid=job.uid,admitted_time=900,policy_action='PREPLACE',migration_count=0)],qos_ledger=[])
        result=unknown_actual_metrics(actual)
        assert result['Unknown_Actual_Changed_UID']==1 and result['Unknown_Actual_TimeShift_UID']==1 and result['Unknown_Actual_Preplace_UID']==1
        assert result['Changed_Nominal_GPUh']==m['gpu']*m['t50_seconds']/3600
