"""Small public domains only; original geometry, no native model or solve."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from v42_integration import table_v_flex_planning as api
from v42_integration.experimental_qos import participation_for,ExperimentalQoSProvider
from v42_integration.qos import TrainingStatistics
from v42_integration.policy import digest
from v42_job_capability import Job,Resources,checkpoint_records,Option,validate
from v42_native.service import boundary


def uid_member(yes,skip=0):
    return next(str(i) for i in range(skip,skip+1000)
        if participation_for(str(i),str(i)+'_EPISODE')['membership']['FLEX30'] is yes)


def fixture():
    begin=90000.;r=uid_member(True);p=uid_member(True,int(r)+1);n=uid_member(False)
    metadata=dict(qos='UNCONFIRMED',protected=None,batch_eligible=None,partition='',
        requested_walltime_seconds=None,can_prestart_place=False,migration_capability=None,
        request_version_authority='UNVERIFIED_SOURCE_PROXY',release_seconds=None,
        hard_earliest_start_seconds=None,hard_latest_start_seconds=None,completion_deadline_seconds=None,
        representation_starts_seconds=[begin+t*900 for t in range(98)])
    def row(uid,site=None):
        return dict(uid=uid,episode_id=uid+'_EPISODE',site=site,submit_seconds=begin-7200,
            observed_start_seconds=begin-2700 if site else None,elapsed_compute_seconds=2700. if site else 0.,
            gpu=1,q50=7200.,compatible_sites=['A','B'],origin_unknown=False,metadata=deepcopy(metadata))
    state=dict(day='2025-05-01',begin_epoch_seconds=begin,end_epoch_seconds=begin+86400,
        capacities=dict(A=8,B=8),running=[row(r,'A')],pending=[row(p),row(n)],historical_completed=[],
        common_initial_state_sha='a'*64,provider_identifiers=dict(runtime_provider_sha='b'*64))
    resources=Resources(dict(A=8,B=8),dict(A=(8,),B=(8,)),
        {('AB',t):1_000_000. for t in range(24,120)},{('A','B'):('AB',),('B','A'):('AB',)},
        120,100_000.,{},{},{},restart_slots=1,max_active_transfers=1)
    jobs={};bounds={};raw={};windows={};classification=[]
    for key in ('running','pending'):
        for row_ in state[key]:
            uid=row_['uid'];running=key=='running';slots=5 if running else 8
            starts=(24,) if running else tuple(range(24,120))
            jobs[uid]=Job(uid,'RUNNING' if running else 'PENDING',24,24,24,'A',slots,1,
                qos='UNCONFIRMED',initial_sites=('A',) if running else ('A','B'),elapsed_seconds=row_['elapsed_compute_seconds'],
                duration_authority='V10_Q50',qos_policy_id='D0_BASIC',qos_receipt_sha='c'*64,
                qos_allowed_starts=starts,qos_budget_seconds=0.,is_observed=True)
            bounds[uid]=boundary(jobs[uid],starts,'d'*64,'e'*64,H=120)
            windows[uid]=starts
            raw[uid]=dict(job_uid=uid,state=jobs[uid].state,compatible_sites=['A','B'],service_slots=slots,
                GPU_gang=1,planning_site='A',elapsed_seconds=row_['elapsed_compute_seconds'],
                duration_authority='V10_Q50',risk_nominal_completion_issue_slot=24+slots,reference_end=24+slots)
            classification.append(dict(uid=uid))
    bundle=dict(day=state['day'],schema='D0_STATE_CONDITIONED_PLANNING_V1',D0_internal_slot_offset=24,
        D0_source_identity={},capacities=resources.capacities,known_population=list(raw.values()),
        C0_Q50=[1.]*24,C0_Q90=[2.]*24)
    data=(bundle,jobs,bounds,resources,raw,{},{},dict(classes={},preserve_singleton_mixed_flow=()))
    identity=dict(science_sha='1'*64,case_sha='2'*64,initial_state_sha='a'*64,cc4_sha='3'*64,runtime_sha='4'*64)
    base=dict(state=state,data=data,windows=windows,classification=classification,
        manifest=dict(identity=identity,initial_record=dict(sha256='5'*64),source_sha='6'*64),
        forecast=dict(forecast_receipt_sha='7'*64))
    stats=TrainingStatistics.from_records([],source_sha='8'*64)
    return base,stats,dict(running=r,pending=p,nonmember=n)


def compiled():
    base,stats,uids=fixture()
    return api.compile_flex_descriptors(base,strict_stats=stats,source_records=[]),base,uids


def test_fullflex_uses_original_e1_receipts_and_is_not_basic_or_blanket_60min():
    c,b,u=compiled();assert isinstance(c['provider'],ExperimentalQoSProvider)
    assert c['issues']==[] and c['identity']['case_sha']!=b['manifest']['identity']['case_sha']
    assert c['provider'].receipts[u['pending']].budget_seconds==1800
    assert c['provider'].receipts[u['nonmember']].budget_seconds==0
    assert len(c['windows'][u['pending']])==3 and len(c['windows'][u['nonmember']])==1
    assert c['policy']['blanket_60_minute_authority'] is False
    assert c['policy']['R2']=='HOLD' and c['policy']['P2_calls']==0


def test_source_initial_bytes_fields_service_elapsed_and_CC4_preserved():
    base,stats,u=fixture();before=deepcopy(base)
    c=api.compile_flex_descriptors(base,strict_stats=stats,source_records=[])
    assert base['state']==before['state'] and base['data']==before['data']
    assert c['data'][0]['C0_Q50']==base['data'][0]['C0_Q50']
    assert c['data'][0]['C0_Q90']==base['data'][0]['C0_Q90']
    for uid,job in c['data'][1].items():
        assert job.service_slots==base['data'][1][uid].service_slots
        assert job.elapsed_seconds==base['data'][1][uid].elapsed_seconds
    assert c['data'][3]==base['data'][3]


@pytest.mark.parametrize('field,value',[('protected',True),('batch_eligible',False),('qos','urgent')])
def test_explicit_protected_or_nonbatch_never_receives_research_actions(field,value):
    base,stats,u=fixture();base['state']['pending'][0]['metadata'][field]=value
    c=api.compile_flex_descriptors(base,strict_stats=stats,source_records=[])
    rec=c['provider'].receipts[u['pending']]
    assert rec.eligible_for_contract is False and rec.budget_seconds==0
    assert not c['data'][1][u['pending']].checkpoint_authorized


def test_public_episode_membership_and_immutable_reissued_receipt_authority():
    c,b,u=compiled();p=c['provider'];uid=u['pending'];row=b['state']['pending'][0]
    expected=participation_for(uid,row['episode_id'])
    rec=p.receipts[uid]
    assert rec.membership_sha==expected['membership_sha'] and rec.source_context['episode_id']==row['episode_id']
    assert p.issue(c['observed'][uid]) is rec
    with pytest.raises(ValueError,match='CONTEXT_CHANGED'):
        p.register_observed(uid,episode_id='ANOTHER_EPISODE')


def test_original_geometry_contains_checkpoint_migration_with_shared_budget():
    c,b,u=compiled()
    from v42_a_stage_domain_v2.domain import physical_domain
    for uid in (u['running'],u['pending']):
        job=c['data'][1][uid];domain=physical_domain(job,c['data'][2][uid],c['data'][3])
        assert domain.blocks and job.checkpoint_authorized
        assert checkpoint_records(job,job.reference_start,job.reference_start+job.service_slots)
        start,site,cp,physical,dest,gpu,taus=domain.blocks[0]
        transfer=domain.cache.transfer(site,dest,gpu,taus[0])
        option=Option(start,site,((site,start,cp),(dest,transfer.restart,transfer.restart+job.service_slots-(cp-start))),
            cp,physical,dest,taus[0],transfer.end,transfer.restart,transfer.wan)
        validate(job,option,c['data'][2][uid],c['data'][3])
        assert (start-job.reference_start+transfer.restart-cp)*900<=1800
    job=c['data'][1][u['nonmember']]
    assert not physical_domain(job,c['data'][2][job.uid],c['data'][3]).blocks


def test_pending_hard_release_is_respected_without_regranting_budget():
    base,stats,u=fixture();begin=base['state']['begin_epoch_seconds']
    base['state']['pending'][0]['metadata']['release_seconds']=begin+900
    c=api.compile_flex_descriptors(base,strict_stats=stats,source_records=[])
    uid=u['pending'];rec=c['provider'].receipts[uid]
    assert rec.reference_start_seconds==begin+900 and min(c['windows'][uid])==25
    assert rec.budget_seconds==1800 and max(c['windows'][uid])==27


def test_hard_deadline_bounds_migration_completion_and_service_is_not_dropped():
    base,stats,u=fixture();begin=base['state']['begin_epoch_seconds'];uid=u['pending']
    base['state']['pending'][0]['metadata']['completion_deadline_seconds']=begin+8100
    c=api.compile_flex_descriptors(base,strict_stats=stats,source_records=[])
    assert c['data'][2][uid].latest_completion==33
    from v42_a_stage_domain_v2.domain import physical_domain
    domain=physical_domain(c['data'][1][uid],c['data'][2][uid],c['data'][3])
    assert domain.stays and not domain.blocks
    assert c['data'][1][uid].service_slots==8


def test_hard_window_that_excludes_reference_reports_uid_unavailable():
    base,stats,u=fixture();begin=base['state']['begin_epoch_seconds']
    base['state']['pending'][0]['metadata']['hard_latest_start_seconds']=begin-900
    c=api.compile_flex_descriptors(base,strict_stats=stats,source_records=[])
    assert c['issues'] and c['issues'][0]['uid']==u['pending']


def test_no_private_future_metadata_can_enter_public_reference_or_e1_records():
    base,stats,u=fixture();base['state']['pending'][0]['metadata']['future_completion_seconds']=123.
    with pytest.raises(ValueError,match='PRIVATE_REALIZATION'):
        api.compile_flex_descriptors(base,strict_stats=stats,source_records=[])


def test_original_authorized_data_retains_E1_full_geometry_not_basic_hold():
    from v42_integration.a_engine import authorized_data
    c,b,u=compiled()
    case=SimpleNamespace(data=c['data'],qos_receipts=c['receipts'],window_slots=c['windows'],progress=None)
    data,domains=authorized_data(case)
    assert data[7]['full_migration_domain_active'] is True
    assert any(d.blocks for d in domains.values())
    assert all(data[1][uid].qos_budget_seconds==c['provider'].receipts[uid].budget_seconds for uid in data[1])


def test_basic_running_pinned_descriptor_cannot_silently_remove_eligible_migration():
    from v42_integration.a_engine import authorized_data
    base,stats,u=fixture();uid=u['running']
    base['data'][4][uid]['compatible_sites']=['A']
    c=api.compile_flex_descriptors(base,strict_stats=stats,source_records=[])
    case=SimpleNamespace(data=c['data'],qos_receipts=c['receipts'],window_slots=c['windows'],progress=None)
    data,domains=authorized_data(case)
    assert data[1][uid].initial_sites==('A','B')
    assert domains[uid].blocks


def test_new_reference_keeps_original_runtime_completion_offset_exact():
    base,stats,u=fixture()
    base['state']['capacities'].update(A=1,B=1)
    base['data'][3].capacities.update(A=1,B=1)
    before=deepcopy(base['data'][4])
    c=api.compile_flex_descriptors(base,strict_stats=stats,source_records=[])
    assert any(j.reference_start>24 for j in c['data'][1].values())
    for uid,raw in c['data'][4].items():
        assert raw['risk_nominal_completion_issue_slot']-raw['reference_end']==(
            before[uid]['risk_nominal_completion_issue_slot']-before[uid]['reference_end'])


@pytest.mark.parametrize('kind', ['pending', 'nonmember'])
def test_delayed_reference_does_not_remove_original_E1_earlier_legal_starts(kind):
    """The Source receipt, rather than the objective reference, owns timing."""
    from v42_integration.a_engine import authorized_data
    from v42_integration.qos import receipt_slot_domain
    base,stats,u=fixture();uid=u[kind];begin=base['state']['begin_epoch_seconds']
    base['state']['capacities'].update(A=1,B=1)
    base['data'][3].capacities.update(A=1,B=1)
    next(row for row in base['state']['pending'] if row['uid']==uid)['submit_seconds']=begin-3600
    c=api.compile_flex_descriptors(base,strict_stats=stats,source_records=[])
    receipt=c['provider'].receipts[uid]
    expected=receipt_slot_domain(receipt,axis_origin_seconds=begin,axis_start_slot=24)
    assert c['data'][1][uid].reference_start>24
    assert min(expected)==24 and min(expected)<c['data'][1][uid].reference_start
    assert c['windows'][uid]==expected
    assert receipt.budget_seconds==(1800 if kind=='pending' else 0)
    case=SimpleNamespace(data=c['data'],qos_receipts=c['receipts'],window_slots=c['windows'],progress=None)
    data,domains=authorized_data(case)
    assert set(start for start,site in domains[uid].stays)==set(expected)
    assert data[1][uid].service_slots==base['data'][1][uid].service_slots


def test_fullflex_builder_rejects_unadmitted_request_before_model_construction():
    c,b,u=compiled()
    with pytest.raises(ValueError,match='FULL_FLEX_A_CASE'):
        api.build_flex_native_model(SimpleNamespace(),build_admission={})


def test_original_WAN_scalar_and_path_guard_rejects_changes():
    c,b,u=compiled();r=c['data'][3]
    authority=dict(packet_source_sha='s',scalar=dict(bytes_per_GPU=r.bytes_per_gpu,
        maximum_active_transfers_network_wide=1,current_conservative_restart_seconds=900,
        checkpoint_interval_seconds=1800,maximum_migrations_per_job=1),
        routes={'AB':dict(source='A',destination='B',links=['AB']),
                'BA':dict(source='B',destination='A',links=['AB'])},
        links={'AB':dict(bandwidth_bytes_per_second=1_000_000/900)})
    assert api.verify_native_migration_authority(r,authority)['PASS']
    authority['scalar']['bytes_per_GPU']=1.
    with pytest.raises(ValueError,match='NUMERIC_AUTHORITY_DRIFT'):
        api.verify_native_migration_authority(r,authority)
