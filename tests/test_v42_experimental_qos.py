"""Explicit research assumptions and unchanged E0; no Native/AC calls."""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from v42_integration.experimental_qos import (ExperimentalQoSProvider, ExperimentalBudgetReceipt,
    FROZEN_SEED, POLICY_ID, participation_for, bind_experimental_native_job, digest)
from v42_integration.qos import ObservedJob, QoSWindowProvider, TrainingStatistics
from v42_job_capability import Job, Option, Resources, ServiceBoundary, validate


def strict():
    rows = [dict(uid=str(i),submit_seconds=100000,start_seconds=104500,end_seconds=105400,
                 observed_at_seconds=110000,request_provenance='SUBMISSION_VERSION_VERIFIED',
                 qos='normal',protected=False,partition='gpu-h100',gpu=1,requested_walltime_seconds=3600)
            for i in range(100)]
    return QoSWindowProvider(TrainingStatistics.from_records(rows,source_sha='NAMED_FIXTURE_TRAIN'),
                             case_sha='E0_SOURCE_CASE',provider_sha='FROZEN_Q50_PROVIDER')


def selected_uid():
    # Named test identities only; never choose real jobs using May performance.
    return next('FIXTURE-'+str(i) for i in range(1000)
                if participation_for('FIXTURE-'+str(i), 'FIXTURE_EPISODE')['membership']['FLEX20'])


def job(**kwargs):
    return replace(ObservedJob(selected_uid(),0,0,0,900,qos='UNCONFIRMED',protected=None,
        batch_eligible=None,partition='',requested_walltime_seconds=None,
        representation_starts_seconds=tuple(range(0,10801,900)),provider_sha='FROZEN_Q50_PROVIDER',
        reference_sha='FROZEN_CAUSAL_REFERENCE'), **kwargs)


def provider(scenario='E1', flex='FLEX30', receipts=None):
    return ExperimentalQoSProvider(strict(),scenario=scenario,participation=flex,
        case_sha='NEW_EXPERIMENTAL_CASE_'+scenario,receipts=receipts)


def issue(p, observed, authority=None):
    return p.issue(observed,episode_id='FIXTURE_EPISODE',source_authority=authority or {})


def test_E0_is_exact_strict_delegation_without_model_overlay_or_receipt_change():
    base = strict()
    p = ExperimentalQoSProvider(base,scenario='E0')
    observed = job(qos='normal',protected=False,batch_eligible=True,
                   partition='gpu-h100',requested_walltime_seconds=3600)
    expected = base.issue(observed)
    actual = p.issue(observed)
    assert actual is expected and not isinstance(actual,ExperimentalBudgetReceipt)
    assert actual.budget_seconds == 3600
    assert p.to_dict() == base.to_dict() and p.export_ledger() == base.export_ledger()
    assert p.metadata_overlay(observed,actual) == {}


@pytest.mark.parametrize('scenario,qos,budget',[('E1','normal',1800),('E1','standby',3600),
                                             ('E2','normal',3600),('E2','standby',7200)])
def test_explicit_research_caps_are_new_contracts_not_observed_SLAs(scenario,qos,budget):
    p = provider(scenario)
    observed = job(qos=qos,protected=False,batch_eligible=True)
    receipt = issue(p,observed,dict(verified_fields=['qos','protected','batch_eligible'],source_sha='PUBLIC_FIELDS_SHA'))
    assert receipt.budget_seconds == receipt.contract_cap_seconds == budget
    assert receipt.policy_id == POLICY_ID and receipt.contract_is_observed_SLA is False
    assert receipt.allowed_starts_seconds[-1] == budget
    assert 'SOURCE_VERIFIED_QOS' in receipt.model_metadata['source_classes']
    assert 'ASSUMED_EXPERIMENTAL_ADDITIONAL_DELAY_CAP' in receipt.model_metadata['assumption_classes']


def test_missing_or_legacy_model_qos_defaults_normal_without_mutating_source():
    p = provider()
    observed = job(qos='standby')
    before = asdict(observed)
    receipt = issue(p,observed)
    overlay = p.metadata_overlay(observed,receipt)
    assert overlay['qos'] == 'normal' and receipt.budget_seconds == 1800
    assert 'ASSUMED_EXPERIMENTAL_BATCH_CONTRACT' in receipt.model_metadata['assumption_classes']
    assert receipt.model_metadata['source_classes'] == ['UNSUPPORTED_REQUEST_METADATA']
    assert overlay['source_observed_qos_metadata']['qos'] == 'standby'
    assert asdict(observed) == before and receipt.source_observed_metadata == before


@pytest.mark.parametrize('changes',[dict(protected=True),dict(qos='high'),dict(qos='urgent'),dict(batch_eligible=False)])
def test_explicit_source_protection_and_nonbatch_are_never_overwritten(changes):
    p = provider('E2')
    observed = job(**changes)
    receipt = issue(p,observed)
    overlay = p.metadata_overlay(observed,receipt)
    assert not receipt.eligible_for_contract and receipt.budget_seconds == 0
    assert not any(overlay[key] for key in ('Can_TimeShift','Can_Preplace','Can_Checkpoint_Migrate'))
    if changes.get('protected') or changes.get('qos') in ('high','urgent'):
        assert overlay['protected'] is True


def test_hash_participation_is_nested_deterministic_and_not_exact_quota():
    rows = [participation_for('OBSERVED_PUBLIC_'+str(i),'EPISODE_'+str(i)) for i in range(1000)]
    assert rows == [participation_for('OBSERVED_PUBLIC_'+str(i),'EPISODE_'+str(i),seed=FROZEN_SEED) for i in range(1000)]
    assert all(not r['membership']['FLEX20'] or r['membership']['FLEX30'] for r in rows)
    assert all(not r['membership']['FLEX30'] or r['membership']['FLEX40'] for r in rows)
    assert 0 < sum(r['membership']['FLEX20'] for r in rows) < sum(r['membership']['FLEX40'] for r in rows) < 1000
    assert participation_for('same','episode')['membership_sha'] != participation_for('same','other')['membership_sha']


@pytest.mark.parametrize('scenario',['E1','E2'])
def test_known_issue_and_unknown_submit_same_public_inputs_have_same_formula(scenario):
    known, unknown = provider(scenario), provider(scenario)
    observed = job()
    k = issue(known,observed)
    u = issue(unknown,replace(observed,origin_unknown=True))
    assert (k.membership_sha,k.participant,k.budget_seconds,k.allowed_starts_seconds,k.model_metadata) == (
            u.membership_sha,u.participant,u.budget_seconds,u.allowed_starts_seconds,u.model_metadata)
    assert not k.origin_unknown and u.origin_unknown


def test_unobserved_future_job_and_private_context_cannot_issue_assumed_rights():
    with pytest.raises(ValueError,match='INDIVIDUAL_NOT_YET_SUBMITTED'):
        job(submit_seconds=900,event_seconds=0)
    p = provider()
    with pytest.raises(ValueError,match='PRIVATE_REALIZATION'):
        p.register_observed('uid',source_authority={'actual_end_seconds':100})
    with pytest.raises(ValueError,match='FUTURE_SOURCE_QOS_AUTHORITY'):
        issue(p,job(),{'observed_at_seconds':900})


def test_receipt_reuse_state_advance_and_shared_interruption_never_reset_budget():
    p = provider('E2')
    observed = job(qos='standby')
    receipt = issue(p,observed,dict(verified_fields=['qos'],source_sha='PUBLIC_QOS'))
    advanced = replace(observed,state='RUNNING',event_seconds=900)
    assert p.issue(advanced) is receipt and receipt.budget_seconds == 7200
    assert p.allowed_starts(advanced,receipt,interruption_seconds=1800)[-1] == 5400
    assert p.allowed_starts(advanced,receipt,interruption_seconds=7201) == ()
    overlay = p.metadata_overlay(advanced,receipt)
    assert not overlay['Can_Preplace'] and overlay['Can_Checkpoint_Migrate']
    with pytest.raises(ValueError,match='EXPERIMENTAL_OBSERVED_CONTEXT_CHANGED'):
        p.register_observed(observed.uid,episode_id='DIFFERENT_EPISODE')
    with pytest.raises(ValueError,match='EXISTING_EXPERIMENTAL_BUDGET_AUTHORITY_CHANGED'):
        p.issue(replace(advanced,reference_start_seconds=900))


def test_hard_start_and_completion_contracts_intersect_not_representation_deadline():
    p = provider('E2')
    observed = job(hard_earliest_start_seconds=900,hard_latest_start_seconds=2700,completion_deadline_seconds=2700)
    receipt = issue(p,observed)
    assert receipt.allowed_starts_seconds == (900,1800)
    assert p.allowed_starts(observed,receipt,interruption_seconds=900) == (900,)
    assert job().completion_deadline_seconds is None


def test_restart_ledger_requires_spec_sha_and_untampered_membership_and_budget():
    p = provider('E2')
    observed = job(qos='standby')
    receipt = issue(p,observed,dict(verified_fields=['qos'],source_sha='PUBLIC_QOS'))
    loaded = provider('E2',receipts=p.export_ledger())
    assert loaded.issue(observed).to_dict() == receipt.to_dict()
    corrupted = deepcopy(p.export_ledger())
    corrupted[observed.uid]['budget_seconds'] = 3600
    with pytest.raises(ValueError,match='SHA_MISMATCH'):
        provider('E2',receipts=corrupted)
    corrupted[observed.uid]['receipt_sha'] = digest({k:v for k,v in corrupted[observed.uid].items() if k!='receipt_sha'})
    with pytest.raises(ValueError,match='CONTRACT_OR_MEMBERSHIP'):
        provider('E2',receipts=corrupted)
    with pytest.raises(ValueError,match='AUTHORITY_MISMATCH'):
        provider('E1',receipts=p.export_ledger())
    receipt.model_metadata['qos'] = 'normal'
    with pytest.raises(ValueError,match='MUTATION'):
        p.issue(observed)


def test_new_120_minute_native_domain_binds_existing_physical_validator_without_bypass():
    p = provider('E2')
    observed = job(qos='standby')
    receipt = issue(p,observed,dict(verified_fields=['qos'],source_sha='PUBLIC_QOS'))
    native = Job(observed.uid,'PENDING',24,24,24,'A',1,1,initial_sites=('A','B'),
                 duration_authority='FROZEN_Q50_PROVIDER')
    bound = bind_experimental_native_job(native,receipt,axis_origin_seconds=0,axis_start_slot=24)
    assert bound.qos_budget_seconds == 7200 and bound.qos_allowed_starts[-1] == 32
    boundary = ServiceBoundary('EXPLICIT_PUBLIC_REPRESENTATION',True,True,bound.qos_allowed_starts,37)
    resources = Resources({'A':1,'B':1},{'A':(1,),'B':(1,)},{},{},37,1,{},{},{})
    validate(bound,Option(32,'B',(('B',32,33),)),boundary,resources)
    with pytest.raises(ValueError,match='START_WINDOW'):
        validate(bound,Option(33,'B',(('B',33,34),)),boundary,resources)
    assert native.qos_budget_seconds == 0 and native.qos_policy_id == ''


def test_current_causal_queue_reference_excludes_unavoidable_wait_without_renewing_budget():
    p = provider('E1')
    observed = job(representation_starts_seconds=tuple(range(0,30001,900)))
    receipt = issue(p,observed)
    immutable_before = receipt.to_dict()
    def window(now, consumed):
        return p.execution_window(observed,receipt,causal_reference_start_seconds=now,event_seconds=now,
            consumed_budget_seconds=consumed,reference_proof=dict(kind='OBSERVED_GRID_BLIND_FEASIBLE_REFERENCE_V1',
                uid=observed.uid,observed_at_seconds=now,reference_start_seconds=now))
    first = window(21600,0)
    assert first['allowed_starts_seconds'] == (21600,22500,23400)
    assert first['unavoidable_queue_wait_seconds'] == 21600
    second = window(22500,900)
    assert second['remaining_budget_seconds'] == 900 and second['allowed_starts_seconds'] == (22500,23400)
    assert second['unavoidable_queue_wait_seconds'] == 21600
    third = window(23400,1800)
    assert third['remaining_budget_seconds'] == 0 and third['allowed_starts_seconds'] == (23400,)
    assert window(24300,1801)['allowed_starts_seconds'] == ()
    assert receipt.to_dict() == immutable_before and receipt.budget_seconds == 1800
    running = p.execution_window(observed,receipt,causal_reference_start_seconds=22500,event_seconds=22500,
        consumed_budget_seconds=900,state='RUNNING',reference_proof=dict(kind='OBSERVED_GRID_BLIND_FEASIBLE_REFERENCE_V1',
            uid=observed.uid,observed_at_seconds=22500,reference_start_seconds=22500))
    assert running['unavoidable_queue_wait_seconds'] == 0


def test_causal_execution_window_keeps_source_hard_contract_and_requires_public_proof():
    p = provider()
    observed = job(completion_deadline_seconds=3600)
    receipt = issue(p,observed)
    proof = dict(kind='OBSERVED_GRID_BLIND_FEASIBLE_REFERENCE_V1',uid=observed.uid,
                 observed_at_seconds=2700,reference_start_seconds=2700)
    window = p.execution_window(observed,receipt,causal_reference_start_seconds=2700,event_seconds=2700,
                                reference_proof=proof)
    assert window['allowed_starts_seconds'] == (2700,)
    past_burden = p.execution_window(observed,receipt,causal_reference_start_seconds=2700,event_seconds=2700,
                                     consumed_budget_seconds=900,reference_proof=proof)
    assert past_burden['allowed_starts_seconds'] == (2700,)
    future_pause = p.execution_window(observed,receipt,causal_reference_start_seconds=2700,event_seconds=2700,
                                      consumed_budget_seconds=900,interruption_seconds=900,reference_proof=proof)
    assert future_pause['allowed_starts_seconds'] == ()
    with pytest.raises(ValueError,match='OBSERVED_REFERENCE_PROOF'):
        p.execution_window(observed,receipt,causal_reference_start_seconds=2700,event_seconds=2700)
    with pytest.raises(ValueError,match='PRIVATE_REALIZATION'):
        p.execution_window(observed,receipt,causal_reference_start_seconds=2700,event_seconds=2700,
                           reference_proof=dict(proof,future_completion=3600))


def test_reload_cannot_expand_authorized_start_window_even_with_recomputed_outer_sha():
    p = provider()
    observed = job()
    issue(p,observed)
    ledger = p.export_ledger()
    ledger[observed.uid]['allowed_starts_seconds'] += (9000,)
    ledger[observed.uid]['receipt_sha'] = digest({k:v for k,v in ledger[observed.uid].items() if k!='receipt_sha'})
    with pytest.raises(ValueError,match='PUBLIC_SOURCE_OR_MODEL'):
        provider(receipts=ledger)


def test_native_nonparticipant_has_no_new_assumed_site_or_checkpoint_right():
    uid = next('NONMEMBER_FIXTURE_'+str(i) for i in range(100)
               if not participation_for('NONMEMBER_FIXTURE_'+str(i),'FIXTURE_EPISODE')['membership']['FLEX40'])
    p = provider()
    receipt = issue(p,job(uid=uid))
    native = Job(uid,'PENDING',24,24,24,'A',1,1,initial_sites=('A','B'),duration_authority='FROZEN_Q50_PROVIDER')
    result = bind_experimental_native_job(native,receipt,axis_origin_seconds=0,axis_start_slot=24)
    assert result.initial_sites == ('A',) and not result.checkpoint_authorized
    baseline_right = bind_experimental_native_job(native,receipt,axis_origin_seconds=0,axis_start_slot=24,
                                                  source_can_prestart_place=True)
    assert baseline_right.initial_sites == ('A','B')
    with pytest.raises(ValueError,match='MIGRATION_PHYSICAL_AUTHORITY'):
        bind_experimental_native_job(native,receipt,axis_origin_seconds=0,axis_start_slot=24,
                                     assumed_checkpoint_authorized=True)
