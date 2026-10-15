"""Full E1 domain/native0 named fixtures; no historical performance transfer."""
from copy import deepcopy
import gzip
import json
from types import SimpleNamespace
import numpy as np
import pytest

from test_v42_aidc_followup import current_fixture
from test_v42_integration_actual import request,capability
from test_v42_release_actual import Probe,observations
from v42_integration.actual import FrozenPowerModel,run_actual
from v42_capacity.actual import Environment
from v42_integration.experimental_qos import ExperimentalQoSProvider,participation_for
from v42_integration.research_presite_contract import ResearchPresiteProvider,make_spec
from v42_integration.research_presite_actual import ObservedSourceAuthority
from v42_integration.release_actual import initial_authority
from v42_integration.m_engine import file_record
from v42_integration.policy import digest
from v42_integration.tablev_fullflex_actual import (TableVFullFlexController,TableVFullFlexPolicy,
    TableVCurrentAC,PhysicalProofStore,StreamingAudit,observed_gpu_intervals,completed_migration_prefix)


def fixture(tmp_path,*,probe=None,source_fields=None,commands=None,gpu=1,q50=1800):
    uid=next(str(n) for n in range(100) if participation_for(str(n),'E')['membership']['FLEX30'])
    raw=dict(job_uid=uid,submit_seconds=0,GPU_gang=gpu,compatible_sites=['A','B'],qos='normal',protected=False)
    raw.update(source_fields or {})
    path=tmp_path/'source.json';path.write_text(json.dumps({'post_issue_arrivals':[raw]}))
    wan=dict(bytes_per_gpu=1000,maximum_active_transfers=1,paths=[],link_capacity_bytes_15min={})
    research=ResearchPresiteProvider(make_spec(scenario='R1',source_records=[file_record(path)],native_wan_sha=digest(wan),
        shared_sites=['A','B']),native_wan=wan)
    strict,old=current_fixture(commands=commands,basic=False)
    qos=ExperimentalQoSProvider(strict,scenario='E1',participation='FLEX30',case_sha=strict.case_sha)
    bindings=dict(old.bindings,qos_sha=qos.stats.sha);old.packet.bindings=bindings
    model=FrozenPowerModel(.1,1.,{'A':8,'B':8},.95,lambda it,w:np.asarray(it),'NAMED_C1')
    oracle=TableVCurrentAC(begin=0,sites=('A','B'),power_model=model,observations=observations(),
        probe=probe or Probe(),proof_records=[file_record(path)])
    policy=TableVFullFlexPolicy(old.reference,old.packet,qos_provider=qos,migration_authority=None,
        research_provider=research,source_authority_lookup=ObservedSourceAuthority(path),variant='C1',oracle=oracle,
        bindings=bindings,expected_bindings=bindings,evidence_scope='NAMED_TABLE_V',
        source_identity={'study_case_sha':'fixture'},site_authority=initial_authority(bindings,'fixture'))
    controller=TableVFullFlexController({'A':8,'B':8},arm='B1',qos_window_provider=qos,frozen_policy=policy,
        known_schedule=commands or {},initial_pending={},backlog_contract={})
    job=request(uid,episode_id='E',source_site=None,q50=q50,gpu=gpu,can_prestart_place=False,qos='normal',protected=False)
    return controller,policy,oracle,job


def test_original_e1_overlay_restores_time_and_checkpoint_without_mutating_source(tmp_path):
    c,p,o,job=fixture(tmp_path);before=deepcopy(job.metadata);c.submit(job,0)
    assert c.metadata[job.uid]['Can_TimeShift'] is True
    assert c.metadata[job.uid]['Can_Checkpoint_Migrate'] is False
    c._overlay(job.uid,'RUNNING')
    assert c.metadata[job.uid]['Can_Checkpoint_Migrate'] is True
    assert c.budgets[job.uid].budget_seconds==1800 and job.metadata==before
    assert p.spec['scope_is_PreSite_only'] is False and p.spec['R2']=='HOLD'


def test_r1_preplace_remains_separate_from_initial_and_actual_start(tmp_path):
    c,p,o,job=fixture(tmp_path);c.submit(job,0);p.observe(0,{'A':0,'B':0},c.metadata);o.observe(0,[])
    assert c.ledger.physical(0)=={'A':0,'B':0}
    decision=p.select(c.metadata[job.uid],c.budgets[job.uid],0,c.reservations,reserve=False)
    assert decision['site']=='B' and decision['action']=='PREPLACE'
    assert p.initial[job.uid]['basic_site']=='A' and not p.initial_events[0]['sensitivity_used']
    assert job.metadata['can_prestart_place'] is False and c.ledger.physical(0)=={'A':0,'B':0}


def test_time_shift_domain_is_evaluated_and_selected_when_public_score_better(tmp_path):
    class DelayProbe(Probe):
        def predicted_score(self,rows):
            first=next(r['slot'] for r in rows if sum(r['GPU'])>0)
            return dict(status='PASS',grid_peak=.2 if first>0 else .9)
    c,p,o,job=fixture(tmp_path,probe=DelayProbe(),source_fields={'can_prestart_place':False})
    c.submit(job,0);p.observe(0,{'A':0,'B':0},c.metadata);o.observe(0,[])
    decision=p.select(c.metadata[job.uid],c.budgets[job.uid],0,c.reservations,reserve=False)
    assert decision['action']=='DELAY' and decision['start_seconds']==900
    assert decision['additional_start_delay_seconds']==900
    assert {r['start_seconds'] for r in p.candidate_events[-1]['candidates']}=={0,900,1800}
    assert decision['time_shift'] and decision['intentional_delay_seconds']==900


def test_explicit_source_forbidden_destination_is_not_overridden_by_e1(tmp_path):
    c,p,o,job=fixture(tmp_path,source_fields={'can_prestart_place':False})
    c.submit(job,0);p.observe(0,{'A':0,'B':0},c.metadata);o.observe(0,[])
    decision=p.select(c.metadata[job.uid],c.budgets[job.uid],0,c.reservations,reserve=False)
    assert decision['site']=='A'
    assert all(r['reason']=='EXPLICIT_SOURCE_PROHIBITION' for r in p.candidate_events[-1]['candidates'] if r['site']=='B')


def test_observed_migration_prefix_preserves_pre_move_source_and_double_hold():
    migration=dict(job_id='J',source='A',destination='B',physical_checkpoint_seconds=900,
        times={'restart_end':2700},segments=[dict(resource='gpu:A',begin=900,end=1800,quantity=2),
            dict(resource='gpu:B',begin=900,end=4500,quantity=2)])
    c=SimpleNamespace(ledger=SimpleNamespace(jobs={'J':dict(start_time=0,completion_observed_time=3150,current_site='B')}),
        migrations=[migration],requests={'J':SimpleNamespace(gpu=2)})
    assert observed_gpu_intervals(c,'J',3600)=={'A':[(0,1800)],'B':[(900,3150)]}
    model=FrozenPowerModel(.1,1.,{'A':8,'B':8},.95,lambda it,w:np.asarray(it),'NAMED_C1')
    c.policy=SimpleNamespace(oracle=SimpleNamespace(begin=0,sites=('A','B'),observations=observations(),model=model))
    prefix=completed_migration_prefix(c,3600)
    np.testing.assert_array_equal([r['GPU'] for r in prefix],[[2,0],[2,2],[0,2],[0,1]])


def test_public_prefix_rejects_future_completion_or_unobserved_checkpoint():
    c=SimpleNamespace(ledger=SimpleNamespace(jobs={'J':dict(start_time=0,completion_observed_time=901,current_site='A')}),
        migrations=[],requests={'J':SimpleNamespace(gpu=1)})
    with pytest.raises(ValueError,match='FUTURE_COMPLETION'):observed_gpu_intervals(c,'J',900)


def test_lossless_stream_and_physical_proof_store_do_not_change_decision_numbers(tmp_path):
    proof=dict(PASS=False,physical_steps=[dict(physical_sha='p',SVR_sha='s',maximum_phase_line_loading=.742)])
    saved=PhysicalProofStore(tmp_path/'proof').save(proof)
    restored=json.loads(gzip.decompress(open(saved['record']['path'],'rb').read()))
    assert restored==proof and digest(restored)==saved['semantic_sha']
    stream=StreamingAudit(tmp_path/'audit.jsonl');stream.append(proof);stream.append(proof)
    assert len(stream)==2 and [json.loads(s) for s in stream.path.read_text().splitlines()]==[proof,proof]


def test_actual_runtime_hold_migration_service_and_prefix_match_original_event_integral(tmp_path):
    c,p,o,job=fixture(tmp_path,source_fields={'can_prestart_place':False})
    job=__import__('dataclasses').replace(job,q50=7200,metadata=dict(job.metadata,
        migration_capability=capability(),qos='normal',protected=False))
    result=run_actual({'A':8,'B':8},[job],Environment({job.uid:3600}),arm='B1',
        qos_window_provider=c.qos,frozen_policy=p,known_schedule={},end=6300,
        controller_class=lambda *a,**kw:TableVFullFlexController(*a,initial_pending={},backlog_contract={},**kw),
        wan_capacities={'AB':100},power_model=o.model,weather=[{'t_wb_c':10,'rh_pct':50}]*7)
    assert len(result['migration_receipts'])==1
    assert result['migration_receipts'][0]['interruption_seconds']==1800
    assert result['receipt']['actual_compute_GPUh']==1
    assert result['receipt']['actual_occupation_GPUh']==1.25
    prefix=result['carryout']['controller']['tablev_state']['prefix']
    np.testing.assert_array_equal(result['occupancy_GPU'],[row['GPU'] for row in prefix])
    np.testing.assert_array_equal(result['physical']['PCC_P_kw'],[row['P'] for row in prefix])
    assert result['qos_ledger'][0]['total_intentional_burden_seconds']==1800
    assert result['receipt']['completed_jobs']==1


def test_approved_known_initial_site_and_timeshift_execute_without_granting_corrective_right(tmp_path):
    uid=next(str(n) for n in range(100) if participation_for(str(n),'E')['membership']['FLEX30'])
    commands={uid:dict(site='B',start_seconds=900,command_type='D0_PENDING_NEW_OPTIMIZED_START')}
    c,p,o,job=fixture(tmp_path,commands=commands)
    job=__import__('dataclasses').replace(job,metadata=dict(job.metadata,origin_unknown=False,reference_start_seconds=0))
    c.production_initial_pending={uid:dict(uid=uid,site=None,gpu=1,q50=1800)}
    c.production_backlog={'pending_source_compatible_placement_research_authorized':True}
    before=deepcopy(job.metadata);c.submit(job,0)
    assert c.metadata[uid]['Can_TimeShift'] and not p.corrective_allowed(c.metadata[uid])
    assert c.admit(0)==[] and c.admit(900)==[uid]
    assert c.metadata[uid]['current_site']=='B' and c.audit[uid]['intentional_delay_seconds']==900
    assert not c.corrective_commands and job.metadata==before and c.known_schedule==commands


def test_zero_action_stream_receipt_is_explicit_empty_evidence(tmp_path):
    stream=StreamingAudit(tmp_path/'none.jsonl')
    assert stream.receipt()['count']==0 and stream.receipt()['record']['bytes']==0


def test_real_event_driver_executes_selected_time_shift_without_resetting_shared_budget(tmp_path):
    class DelayProbe(Probe):
        def predicted_score(self,rows):
            first=next(r['slot'] for r in rows if sum(r['GPU'])>0)
            return dict(status='PASS',grid_peak=.2 if first>0 else .9)
    c,p,o,job=fixture(tmp_path,probe=DelayProbe(),source_fields={'can_prestart_place':False})
    result=run_actual({'A':8,'B':8},[job],Environment({job.uid:900}),arm='B1',qos_window_provider=c.qos,
        frozen_policy=p,end=3600,controller_class=lambda *a,**kw:TableVFullFlexController(*a,
            initial_pending={},backlog_contract={},**kw),power_model=o.model,
        weather=[{'t_wb_c':10,'rh_pct':50}]*4)
    row=result['queue_ledger'][0]
    assert row['admitted_time']==900 and row['intentional_delay_seconds']==900
    assert result['qos_ledger'][0]['total_intentional_burden_seconds']==900
    assert result['carryout']['controller']['tablev_state']['actual_starts'][0]['executed_intentional_time_shift_seconds']==900


def test_unknown_current_admission_ignores_future_known_booking_and_observed_overrun_holds_gpu(tmp_path):
    commands={'K':dict(site='A',start_seconds=900,protected_segments=[dict(resource='gpu:A',begin=900,end=1800,quantity=8)])}
    c,p,o,job=fixture(tmp_path,commands=commands,source_fields={'can_prestart_place':False},gpu=8,q50=450)
    known=request('K',gpu=8,q50=900,origin_unknown=False,reference_start_seconds=900,
        qos='normal',protected=False,can_prestart_place=False)
    result=run_actual({'A':8,'B':8},[job,known],Environment({job.uid:2250,'K':900}),arm='B1',
        qos_window_provider=c.qos,frozen_policy=p,known_schedule=commands,end=4500,
        controller_class=lambda *a,**kw:TableVFullFlexController(*a,initial_pending={},backlog_contract={},**kw),
        power_model=o.model,weather=[{'t_wb_c':10,'rh_pct':50}]*5)
    rows={r['job_uid']:r for r in result['queue_ledger']}
    assert rows[job.uid]['admitted_time']==0 and rows['K']['admitted_time']==2700
    assert rows['K']['intentional_delay_seconds']==0
    assert result['occupancy_GPU'][1,0]==8 and result['occupancy_GPU'][2,0]==4
    runtime=result['carryout']['controller']['current_event_state']['runtime_events']
    assert any(r['event']=='OVERRUN_RUNNING_HOLD' and r['uid']==job.uid for r in runtime)


def test_original_known_temporal_wan_commitments_remain_but_not_future_gpu_veto(tmp_path):
    c,p,o,job=fixture(tmp_path)
    c.reservations.capacities['wan:AB']=100
    c.reservations.known_plans['K']=[dict(resource='gpu:A',begin=900,end=1800,quantity=8),
        dict(resource='wan:AB',begin=900,end=1800,quantity=100)]
    assert c.reservations.feasible([dict(resource='gpu:A',begin=0,end=2700,quantity=8)]) is None
    assert c.reservations.feasible([dict(resource='wan:AB',begin=900,end=1800,quantity=1)])=='NO_CAPACITY'


def test_real_full_flex_stage_gate_precedes_private_truth_io(tmp_path,monkeypatch):
    from v42_integration import table_v_flex_planning,tablev_actual
    from v42_integration.tablev_fullflex_actual import run_fullflex_actual
    from v42_integration.release_ac_contract import CONTRACT
    monkeypatch.setattr(table_v_flex_planning,'require_flex_context',lambda c:None)
    monkeypatch.setattr(tablev_actual,'prepare_reference_inputs',lambda *a,**k:pytest.fail('private truth read'))
    with pytest.raises(ValueError,match='EXACT_P1_ONLY_FULL_STAGE_ACCEPTANCE'):
        run_fullflex_actual(context={'manifest':{'identity':{}}},arm='B1',a_result={},a_acceptance={},
            reference_result={},reference_acceptance={},output=tmp_path/'no',
            gate={'Gate_contract':CONTRACT,'official_contract_authorized':True})
    assert not (tmp_path/'no').exists()


def test_literal_full_parent_body_must_match_point_native_matrix_and_current_source():
    from v42_integration.tablev_fullflex_actual import require_full_a_parent
    context={'input_audit':{'a_input_sha':'input'}}
    binding=dict(rows=7,columns=5,objective_sense=1)
    result=dict(case_sha='stage',aidc_anchor='aidc',input_MESS_anchor='off',native_binding=binding,
        FULL_point_replay={'PASS':True,'point_sha256':'point'})
    receipt=dict(arm='B1',stage_case_sha='stage',D0_input_sha='input',AIDC_anchor='aidc',MESS_anchor='off',
        native_binding=binding,point_sha256='point',Original_FULL=dict(PASS=True,FULL_max_residual=1e-10,
            point_sha256='point',rows=7,columns=5))
    assert require_full_a_parent(context,'B1',result,receipt) is receipt
    for field,value in [('PASS','True'),('FULL_max_residual',float('nan')),('point_sha256','other'),('rows',8)]:
        changed=deepcopy(receipt);changed['Original_FULL'][field]=value
        with pytest.raises(ValueError,match='LITERAL_ORIGINAL_A_FULL'):
            require_full_a_parent(context,'B1',result,changed)
