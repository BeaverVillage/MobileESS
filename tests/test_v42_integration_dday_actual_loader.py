"""DD00 public/private boundary regressions; no Actual replay or optimizer."""
from copy import deepcopy
from dataclasses import asdict
import json

import pandas as pd
import pytest

from v42_integration.actual import JobEventController, JobRequest
from v42_integration.actual_validation import _build_dday_actual_inputs, prepare_actual, write
from v42_integration.dday_boundary import build_boundary_candidate, prefix_events
from v42_integration.dday_initialization import initialize_from_candidate
from v42_integration.qos import ObservedJob, QoSWindowProvider, TrainingStatistics
from v42_final.workload import ForecastBook


@pytest.fixture
def boundary_fixture():
    begin = pd.Timestamp('2025-05-01', tz='Etc/GMT-10').timestamp()
    issue = begin-21600
    def row(uid, submit, gpu=1, q50=900):
        return dict(job_uid=uid, submit_time=submit, GPU_gang=gpu, Q50_total_seconds=q50,
            compatible_sites=['A','B'], source_member='NAMED_SYNTHETIC_BOUNDARY_FIXTURE', source_row=len(uid))
    known = [row('fixed-overrun',issue-10000,2,50), row('known-transition',issue-10000),
             row('known-pending',issue-9000), row('gone44',issue-10000)]
    unknown = [row('prefix-running',begin-2000),row('prefix-pending',begin-1200),
               row('prefix-completed',begin-4000),row('future-submit',begin+900)]
    starts = {'fixed-overrun':issue-900,'known-transition':begin-450,
        'known-pending':begin+5000,'gone44':issue-1000,'prefix-running':begin-1000,
        'prefix-pending':begin+1000,'prefix-completed':begin-3000,'future-submit':begin+2000}
    ends = {uid:begin+50000 for uid in starts}
    ends.update(gone44=begin-1,**{'prefix-completed':begin-1})
    truth = {uid:dict(start_time=start,end_time=ends[uid],realized_seconds=ends[uid]-start)
             for uid,start in starts.items()}
    native = dict(known_population=[dict(r,state='RUNNING' if i in (0,3) else 'PENDING',
        current_site_if_running='A' if i==0 else None,
        elapsed_seconds=issue-starts[r['job_uid']] if i in (0,3) else 0) for i,r in enumerate(known)])
    plan = dict(day='2025-05-01',issue_time=issue,known_population=known,
        capacities={'A':8,'B':8},rack_compatibility={'A':[8],'B':[8]},
        forecast_inputs=dict(current_CC4=dict(Q50_GPUh=[1.]*24,Q90_GPUh=[2.]*24)))
    actual = dict(post_issue_arrivals=unknown)
    population = known+unknown
    events = prefix_events(truth,population,begin)
    candidate,_,_ = build_boundary_candidate(plan,native,actual,events,{'gone44'})
    # This synthetic unit fixture has no historical Reference pins. The
    # production recovery audit is tested separately against exact Git bytes.
    freeze = initialize_from_candidate(candidate,plan,native,actual,
        pr129_recovery=dict(audit_completed=True,validated_pins={}))
    stats = TrainingStatistics.from_records([],source_sha='DDAY_BOUNDARY_FIXTURE_ONLY_TRAIN')
    qos = QoSWindowProvider(stats,case_sha='FIXTURE_NEW_DDAY_CASE',provider_sha='FIXTURE_FROZEN_Q50')
    shared = {}
    for i,r in enumerate(known):
        state = native['known_population'][i]['state']
        start = starts[r['job_uid']] if state=='RUNNING' else begin+900
        job = ObservedJob(uid=r['job_uid'],submit_seconds=r['submit_time'],event_seconds=issue,
            reference_start_seconds=start,t50_seconds=r['Q50_total_seconds'],gpu=r['GPU_gang'],
            state=state,qos='UNCONFIRMED',protected=None,batch_eligible=None,
            requested_walltime_seconds=None,provider_sha=qos.provider_sha,reference_sha='D1_FIXED_REFERENCE',
            representation_starts_seconds=tuple(range(int(issue),int(begin+86400)+901,900)),
            nominal_service_seconds=max(r['Q50_total_seconds']-(issue-start),0) if state=='RUNNING' else r['Q50_total_seconds'])
        receipt=qos.issue(job)
        # Reloaded JSON fields exercise tuple/list normalization as well.
        shared[r['job_uid']]=json.loads(json.dumps(dict(observed=asdict(job),receipt=receipt.to_dict())))
    return plan,actual,freeze,truth,qos,shared,begin


def build(fixture):
    return _build_dday_actual_inputs(*fixture[:6])


def test_midnight_roster_history_gangs_queue_and_private_service(boundary_fixture):
    plan,actual,freeze,truth,qos,shared,begin=boundary_fixture
    before=qos.export_ledger()
    result=build(boundary_fixture)
    assert len(result['running'])==3 and sum(r.gpu for r,_,_ in result['running'])==4
    assert result['boundary_consumption_audit']['initial_pending_jobs']==2
    assert result['boundary_consumption_audit']['pending_queue_order']==['known-pending','prefix-pending']
    assert len({r.uid for r in result['requests']}|{r.uid for r,_,_ in result['running']})==6
    assert {r['uid'] for r in result['historical_source_ledger']}=={'gone44','prefix-completed'}
    assert all(r['active_Dday_GPU']==0 and r['CC4_depletions']==0 for r in result['historical_source_ledger'])
    fixed=next((r,s,t) for r,s,t in result['running'] if r.uid=='fixed-overrun')
    assert fixed[1]=='A' and fixed[2]==truth['fixed-overrun']['start_time']
    assert fixed[0].metadata['elapsed_compute_seconds']==begin-fixed[2]>fixed[0].q50
    assert result['environment'].running_completion('fixed-overrun')>begin
    assert result['boundary_consumption_audit']['simulated_slots']==96
    assert not result['boundary_consumption_audit']['preday_queue_replay_executed']
    assert qos.export_ledger()==before
    assert set(qos.receipts)=={r['job_uid'] for r in plan['known_population']}


def test_future_realizations_do_not_change_public_requests_or_reference(boundary_fixture):
    result=build(boundary_fixture)
    changed=list(deepcopy(boundary_fixture))
    begin=changed[-1]
    for values in changed[3].values():
        if values['start_time']>begin:values['start_time']+=10000
        if values['end_time']>begin:values['end_time']+=100000
        values['realized_seconds']=values['end_time']-values['start_time']
    altered=build(changed)
    assert [asdict(r) for r in result['requests']]==[asdict(r) for r in altered['requests']]
    assert [(asdict(r),s,t) for r,s,t in result['running']]==[(asdict(r),s,t) for r,s,t in altered['running']]
    assert result['reference'].to_dict()==altered['reference'].to_dict()
    assert 'future-submit' not in result['reference'].assigned


def test_known_pending_to_running_reuses_budget_without_rewriting_history(boundary_fixture):
    plan,_,_,truth,qos,shared,begin=boundary_fixture
    result=build(boundary_fixture)
    request,site,start=next(row for row in result['running'] if row[0].uid=='known-transition')
    prior=qos.receipts[request.uid]
    assert prior.state_at_issue=='PENDING'
    controller=JobEventController(plan['capacities'],arm='B0',qos_window_provider=qos,reference=result['reference'])
    controller.submit(request,begin)
    assert controller.observed[request.uid].state=='RUNNING'
    assert controller.budgets[request.uid] is prior
    assert controller.observed[request.uid].reference_start_seconds==prior.reference_start_seconds==begin+900
    assert start==truth[request.uid]['start_time']==begin-450
    assert request.metadata['elapsed_compute_seconds']==450
    assert controller.budgets[request.uid].issued_at_seconds==shared[request.uid]['observed']['event_seconds']


def test_prefix_origin_unknown_observed_once_without_cc4_day_debit(boundary_fixture):
    plan,_,_,_,qos,_,begin=boundary_fixture
    result=build(boundary_fixture)
    request=next(r for r in result['requests'] if r.uid=='prefix-pending')
    forecast=ForecastBook(tuple([1.]*24),tuple([2.]*24),begin)
    controller=JobEventController(plan['capacities'],arm='B0',qos_window_provider=qos,
        reference=result['reference'],forecast=forecast)
    controller.submit(request,begin)
    assert controller.observed[request.uid].origin_unknown
    assert not forecast.submissions and not controller.cc4_ledger
    with pytest.raises(ValueError,match='SUBMISSION_AUTHORITY'):controller.submit(request,begin)
    assert len(controller.ledger.jobs)==1 and len(controller.events)==1


def test_public_request_or_budget_tampering_rejected_before_registration(boundary_fixture):
    plan,_,freeze,_,qos,_,begin=boundary_fixture
    changed=list(deepcopy(boundary_fixture))
    changed[2]['running'][0]['gpu']+=1
    with pytest.raises(ValueError,match='REQUEST_CONTRACT_DRIFT'):build(changed)
    result=build(boundary_fixture)
    request=next(r for r,_,_ in result['running'] if r.uid=='known-transition')
    request.metadata['nominal_service_seconds']+=900
    controller=JobEventController(plan['capacities'],arm='B0',qos_window_provider=qos,reference=result['reference'])
    with pytest.raises(ValueError,match='PLANNING_QOS_METADATA_CHANGED'):controller.submit(request,begin)
    assert not controller.requests and not controller.ledger.jobs and not controller.pending


def test_pre_midnight_known_start_is_not_replayed(boundary_fixture):
    plan,_,_,_,qos,_,begin=boundary_fixture
    result=build(boundary_fixture)
    request=next(r for r in result['requests'] if r.uid=='known-pending')
    controller=JobEventController(plan['capacities'],arm='B1',qos_window_provider=qos,
        reference=result['reference'],known_schedule={request.uid:dict(start_seconds=begin-900,site='B')})
    controller.submit(request,begin)
    decision=controller._known_decision(request.uid,begin)
    assert decision['status']=='PRE_DDAY_START_COMMAND_NOT_REPLAYED'
    assert decision['action']=='QUEUE' and 'start_seconds' not in decision
    assert decision['plan_start_seconds']==begin-900


def test_public_loader_requires_intact_freeze_before_private_join(boundary_fixture,tmp_path):
    freeze=deepcopy(boundary_fixture[2])
    freeze['pending'][0]['gpu']+=1
    path=tmp_path/'V42_MAY01_DDAY_INITIAL_STATE_FREEZE.json'
    write(path,freeze)
    with pytest.raises(ValueError,match='FREEZE_SHA_DRIFT'):
        prepare_actual(tmp_path,source_freeze={'files':[]},strict_stats=boundary_fixture[4].stats,
            case_sha='FIXTURE_NEW_DDAY_CASE',provider_sha='FIXTURE_FROZEN_Q50',initial_state_freeze=path,
            planning_provider=boundary_fixture[4],planning_known_receipts=boundary_fixture[5])


@pytest.mark.parametrize('arm',['B0','B2'])
def test_common_fcfs_does_not_backfill_later_compatible_small_gang(arm):
    stats=TrainingStatistics.from_records([],source_sha='FCFS_BOUNDARY_FIXTURE_ONLY')
    qos=QoSWindowProvider(stats,case_sha='fixture',provider_sha='fixture')
    controller=JobEventController({'A':1,'B':1},arm=arm,qos_window_provider=qos)
    def request(uid,submit,site):
        return JobRequest(uid,submit,1,(site,),900,site,
            dict(representation_starts_seconds=(0,900,1800),qos='UNCONFIRMED',protected=None))
    occupant=request('occupant',0,'A');head=request('head',0,'A');tail=request('tail',1,'B')
    controller.submit(occupant,900)
    controller.ledger.start('occupant','A',900,'FIXTURE_OBSERVED')
    controller.pending.remove((occupant.submit,occupant.uid))
    controller.submit(head,900);controller.submit(tail,900)
    assert controller.admit(900)==[]
    assert controller.ledger.jobs['head']['latest_observed_state']=='PENDING'
    assert controller.ledger.jobs['tail']['latest_observed_state']=='PENDING'
    assert controller.ledger.physical(900)=={'A':1,'B':0}
