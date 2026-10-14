"""User's named contracts with explicit native0 witnesses and traps."""
from copy import deepcopy
import numpy as np
import pytest
from v42_integration.policy import ReservationLedger
from v42_integration.frozen_unknown import FrozenUnknownPolicy,coverage_grammar
from test_v42_known_unknown_contract import frozen,participant,NeverUnknown
from test_v42_experimental_control import metadata,observed,policy,research_provider
from test_v42_integration_actual import request,qos
from v42_integration.actual import JobEventController,run_actual
from v42_capacity.actual import Environment


CONTRACTS=(
 'KNOWN_PLANNING_SCHEDULE_PRESERVED','KNOWN_NEVER_USES_UNKNOWN_SELECTOR','UNKNOWN_ONLY_POLICY_LOOKUP',
 'UNKNOWN_NO_FUTURE_UID_AT_PLANNING','PLANNING_POLICY_CREATED_BEFORE_ACTUAL','FROZEN_POLICY_SHA_RELOAD_EQUIVALENCE',
 'ALL_COMPATIBLE_SITE_CANDIDATES_COVERED','ALL_AUTHORIZED_15MIN_DELAY_OPTIONS_COVERED','GPU_RUNTIME_QOS_BUCKET_BOUNDARIES_SAFE',
 'PREPLACE_ZERO_DELAY_NOT_FALSE_BATCH_REJECT','FIRST_FEASIBLE_FROZEN_FALLBACK_SELECTED','ACTUAL_NO_NEW_GRID_OBJECTIVE_SCORING',
 'ACTUAL_NO_GLOBAL_OPTIMIZATION','KNOWN_HARD_RESERVATION_PROTECTED','RUNNING_OVERRUN_CAPACITY_PROTECTED',
 'UNKNOWN_TENTATIVE_BOOKING_CAUSAL_REBIND','NO_FUTURE_HARD_CAPACITY_VIOLATION','EXACT_RACK_GPU_WAN_CHECKS',
 'MIGRATION_FIRST_CHECKPOINT_ONLY','UNKNOWN_RUNTIME_OVERRUN_NOT_FALSE_COMPLETION','SHARED_QOS_BUDGET_NOT_REFUNDED',
 'NO_CC4_DOUBLE_DEPLETION','Q50_SERVICE_AND_Q90_EXTRA_MASS_CONSERVATION','NO_D24_ABSOLUTE_COMPLETION_DEADLINE',
 'B1_MESS_OFF','B3_FINAL_A2_M2_POLICY_BINDING','NO_SOURCE_OR_RAW_MUTATION')


@pytest.mark.parametrize('contract',CONTRACTS,ids=CONTRACTS)
def test_required_contract(contract,tmp_path,monkeypatch):
    # Run specialized independent witnesses for protected transactional paths.
    from test_v42_frozen_alternatives import (
        test_FIRST_FEASIBLE_FROZEN_FALLBACK_SELECTED,test_KNOWN_HARD_RESERVATION_PROTECTED,
        test_RUNNING_OVERRUN_CAPACITY_PROTECTED,test_NO_FUTURE_HARD_CAPACITY_VIOLATION)
    special={'FIRST_FEASIBLE_FROZEN_FALLBACK_SELECTED':lambda:test_FIRST_FEASIBLE_FROZEN_FALLBACK_SELECTED(monkeypatch),
        'UNKNOWN_TENTATIVE_BOOKING_CAUSAL_REBIND':lambda:test_FIRST_FEASIBLE_FROZEN_FALLBACK_SELECTED(monkeypatch),
        'KNOWN_HARD_RESERVATION_PROTECTED':test_KNOWN_HARD_RESERVATION_PROTECTED,
        'RUNNING_OVERRUN_CAPACITY_PROTECTED':test_RUNNING_OVERRUN_CAPACITY_PROTECTED,
        'NO_FUTURE_HARD_CAPACITY_VIOLATION':test_NO_FUTURE_HARD_CAPACITY_VIOLATION}
    if contract in special:special[contract]();return
    if contract in ('B1_MESS_OFF','B3_FINAL_A2_M2_POLICY_BINDING'):
        from test_v42_known_unknown_contract import test_final_A_stage_known_handoff_transport_only
        test_final_A_stage_known_handoff_transport_only(tmp_path,monkeypatch,'B1' if contract=='B1_MESS_OFF' else 'B3');return
    if contract in ('KNOWN_PLANNING_SCHEDULE_PRESERVED','KNOWN_NEVER_USES_UNKNOWN_SELECTOR'):
        from test_v42_known_unknown_contract import test_KNOWN_NEVER_ENTERS_UNKNOWN_POLICY,test_known_commands
        test_KNOWN_NEVER_ENTERS_UNKNOWN_POLICY();test_known_commands(dict(start_seconds=900,site='A'),900,'A','DELAY');return
    if contract=='NO_CC4_DOUBLE_DEPLETION':
        from test_v42_known_unknown_contract import test_NO_FUTURE_LEAKAGE_NO_DUPLICATE_CC4_DEPLETION_KNOWN_UNKNOWN_DISJOINT_ACTION_LEDGER
        test_NO_FUTURE_LEAKAGE_NO_DUPLICATE_CC4_DEPLETION_KNOWN_UNKNOWN_DISJOINT_ACTION_LEDGER();return
    if contract=='Q50_SERVICE_AND_Q90_EXTRA_MASS_CONSERVATION':
        from test_v42_frozen_alternatives import test_Q50_SERVICE_AND_Q90_EXTRA_MASS_CONSERVATION
        test_Q50_SERVICE_AND_Q90_EXTRA_MASS_CONSERVATION();return
    if contract=='EXACT_RACK_GPU_WAN_CHECKS':
        from test_v42_known_unknown_contract import test_PHYSICAL_GPU_RACK_WAN_GRID_GUARDS,test_unknown_frozen_checkpoint_all_links_and_pinned_destination_guard
        test_PHYSICAL_GPU_RACK_WAN_GRID_GUARDS();test_unknown_frozen_checkpoint_all_links_and_pinned_destination_guard();return
    provider,p=frozen();job,receipt=participant(provider);m=metadata(provider,job,receipt)
    p.set_current_resources(0,{'A':0,'B':0});ledger=ReservationLedger({'A':8,'B':8});saved=p.document
    if contract=='UNKNOWN_NO_FUTURE_UID_AT_PLANNING':
        with pytest.raises(ValueError,match='UNKNOWN_NOT_PRESENT'):frozen(conditions=[dict(uid='FUTURE')])
    elif contract=='UNKNOWN_ONLY_POLICY_LOOKUP':
        m['origin_unknown']=False
        with pytest.raises(ValueError,match='KNOWN_NEVER'):p.select(m,receipt,0,ledger)
    elif contract=='PLANNING_POLICY_CREATED_BEFORE_ACTUAL':
        assert p.document['metrics']['bounded_candidates']>0 and p.document['Actual_future_UID_inputs']==0
        p.select(m,receipt,0,ledger);assert p.document==saved
    elif contract=='FROZEN_POLICY_SHA_RELOAD_EQUIVALENCE':
        path=tmp_path/'freeze.json';p.save(path);loaded=FrozenUnknownPolicy.load(path,bindings=p.bindings)
        assert loaded.document==saved and loaded.sha==p.sha
        assert loaded.expanded_document()['templates']==p.expanded_document()['templates']
    elif contract=='ALL_COMPATIBLE_SITE_CANDIDATES_COVERED':
        for t in p.expanded_document()['templates']:
            if t['state']=='PENDING':assert {r['site'] for r in t['scenario_comparisons']}=={'A','B'}
    elif contract=='ALL_AUTHORIZED_15MIN_DELAY_OPTIONS_COVERED':
        for t in p.expanded_document()['templates']:
            if t['state']=='PENDING':assert {r['delay_seconds'] for r in t['scenario_comparisons']}==set(range(0,(1800 if t['qos']=='normal' else 3600)+1,900))
    elif contract=='GPU_RUNTIME_QOS_BUCKET_BOUNDARIES_SAFE':
        assert p.lookup(m,receipt,0)[0]
        assert p.lookup(dict(m,nominal_service_seconds=900.001),receipt,0)[0] is None
        assert p.lookup(dict(m,gpu=3),receipt,0)[0] is None
    elif contract=='PREPLACE_ZERO_DELAY_NOT_FALSE_BATCH_REJECT':
        m.update(batch_eligible=False,Can_TimeShift=False,can_prestart_place=True,Can_Preplace=True)
        rows,_=p.candidates(m,receipt,0)
        assert any(r['action']=='PREPLACE' and r['start_seconds']==0 for r in rows)
    elif contract in ('ACTUAL_NO_NEW_GRID_OBJECTIVE_SCORING','ACTUAL_NO_GLOBAL_OPTIMIZATION'):
        before=p.packet.evaluation_calls
        monkeypatch.setattr(p.packet,'evaluate',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Actual scoring')))
        result=p.select(m,receipt,0,ledger)
        assert result['online_global_optimizer_calls']==0 and p.packet.evaluation_calls==before
    elif contract=='MIGRATION_FIRST_CHECKPOINT_ONLY':
        m.update(state='RUNNING',current_site='A',Can_Checkpoint_Migrate=True,accumulated_compute_seconds=1800)
        p.set_current_resources(1800,{'A':1,'B':0});ledger.retain_running(job.uid,'A',1800,2700,1)
        p.select_migration(m,receipt,1800,ledger)
        result=p.select_migration(m,receipt,3600,ledger)
        assert result['reason']=='FIRST_CHECKPOINT_ONLY'
    elif contract=='UNKNOWN_RUNTIME_OVERRUN_NOT_FALSE_COMPLETION':
        result=run_actual({'A':8,'B':8},[],Environment({'R':9000},{'R':9000}),arm='B0',qos_window_provider=qos(),
            running=[(request('R',submit=-900,q50=1,elapsed_compute_seconds=900),'A',-900)],begin=0,end=1800)
        assert result['receipt']['completed_jobs']==0 and result['receipt']['carryout_jobs']==1 and np.any(result['occupancy_GPU']>0)
    elif contract=='SHARED_QOS_BUDGET_NOT_REFUNDED':
        m['additional_start_delay_seconds']=1800;m['cumulative_migration_interruption_seconds']=900
        assert not p.candidates(m,receipt,0)[0] and receipt.budget_seconds==1800
    elif contract=='NO_D24_ABSOLUTE_COMPLETION_DEADLINE':
        assert all(r.get('completion_deadline_seconds') is None for r in p.document['coverage'])
        assert 'completion_deadline_seconds' not in m or m['completion_deadline_seconds'] is None
    elif contract=='NO_SOURCE_OR_RAW_MUTATION':
        raw=deepcopy(m);p.select(m,receipt,0,ledger,reserve=False)
        assert m==raw and p.document==saved
    else:raise AssertionError(contract)
