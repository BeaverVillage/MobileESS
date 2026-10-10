"""Controller liveness under an unending stream of verified repair fixtures.

All workers below are isolated fake process receipts. No model or Native call.
"""
from copy import deepcopy
from pathlib import Path

import pytest

from v42_autonomous import recovery as r
from v42_autonomous import supervisor as s


class Campaign:
    def __init__(self, tmp_path, monkeypatch, arm='B2'):
        self.root=tmp_path
        self.arm=arm
        self.cp=dict(state=arm+'_RUNNING',workers={},dates={
            a+'/'+day:dict(status='PENDING',arm=a,day=day)
            for a in ('B2','B3') for day in s.DAYS})
        self.starts=[]
        self.dead=set()
        self.held=set()
        self.repair_days=s.DAYS[:3] if arm=='B2' else s.DAYS[:1]
        for day in self.repair_days:
            key=arm+'/'+day
            self.cp['dates'][key].update(status='FAIL',Native_Runtime=1.)
            s.first_terminal(self.cp,key)
        if arm=='B3':
            for day in s.DAYS:self.cp['dates']['B2/'+day]['status']='PASS'
            s.initialize_history(self.cp)
            self.cp['first_sweeps_completed']['B2']=dict(dates=31)
        monkeypatch.setattr(s,'same_process',lambda worker:worker['PID'] not in self.dead)
        monkeypatch.setattr(s,'external_workers',lambda cp:[])
        monkeypatch.setattr(s,'dispatch',self.dispatch)
        monkeypatch.setattr(r,'dispatch_ready',self.retry)
        monkeypatch.setattr(r,'queue',lambda root:self.ready())
        monkeypatch.setattr(r,'retire_satisfied_ready',lambda root,cp:self.ready())
        monkeypatch.setattr(r,'sync_worker',lambda root,worker:r.HeartbeatObservationRead({}))
        monkeypatch.setattr(r,'mark_finished',lambda root,queue_id,path:r.read(path))
        monkeypatch.setattr(r,'reconcile_workers',lambda root:[
            deepcopy(worker) for worker in self.cp['workers'].values()
            if worker.get('recovery_queue_id') and worker['PID'] not in self.dead])

    def ready(self):
        # Each failed retry is replaced immediately by a new verified fixture.
        return dict(entries=[dict(arm=self.arm,date=day,queue_id='next_'+day,
            verification_status='READY_VERIFIED_REPAIR',retry_priority=1000-index,
            queued_UTC='2026-01-01') for index,day in enumerate(self.repair_days)])

    def worker(self, arm, day, slot, kind):
        serial=len(self.starts)+1
        attempt=f'{kind}_{serial}'
        directory=self.root/'attempts'/attempt
        request=directory/'request.json'
        result=directory/'RESULT.json'
        r.atomic(request,dict(arm=arm,day=day,attempt_id=attempt,
            implementation_SHA='b'*64,result=str(result)))
        worker=dict(arm=arm,day=day,worker_slot=slot,PID=10000+serial,
            created=float(serial),request=str(request),source_SHA='b'*64)
        if kind=='retry':worker['recovery_queue_id']=attempt
        self.starts.append(dict(kind=kind,arm=arm,day=day,slot=slot,worker=deepcopy(worker)))
        return worker

    def retry(self, root, arm, slot, manifest):
        if arm!=self.arm:return None
        active={worker['day'] for worker in self.cp['workers'].values() if worker['arm']==arm}
        candidate=next((day for day in self.repair_days if day not in active),None)
        return self.worker(arm,candidate,slot,'retry') if candidate else None

    def dispatch(self, root, manifest, cp, arm, day, slot):
        worker=self.worker(arm,day,slot,'initial')
        request=r.read(worker['request'])
        cp['dates'][arm+'/'+day].update(status='RUNNING',current_attempt=request['attempt_id'],
            request=worker['request'],source_SHA=worker['source_SHA'],Native_Runtime=None)
        cp['workers'][arm+'/'+day]=worker

    def cycle(self):
        s.cycle(self.root,{},self.cp)
        r.atomic(self.root/'SUPERVISOR_STATE.json',self.cp)

    def restart(self):
        self.cp=r.read(self.root/'SUPERVISOR_STATE.json')
        before=deepcopy(self.cp.get('first_sweep_retry_streak',{}))
        s.adopt_recovery_workers(self.root,self.cp)
        assert self.cp.get('first_sweep_retry_streak',{})==before

    def finish(self):
        statuses=('FAIL','TIME_LIMIT_FEASIBLE_NOT_CERTIFIED','INFEASIBLE','NUMERICAL','QUARANTINE','PASS')
        for key,worker in self.cp['workers'].items():
            if worker['PID'] in self.held:continue
            request=r.read(worker['request'])
            status='FAIL' if worker.get('recovery_queue_id') else statuses[int(worker['day'][-2:])%len(statuses)]
            r.atomic(request['result'],dict(identity={field:request[field]
                for field in ('arm','day','attempt_id')},source_SHA=worker['source_SHA'],
                status=status,PASS=status=='PASS',Native_Runtime=1.))
            self.dead.add(worker['PID'])


@pytest.mark.parametrize('arm',['B2','B3'])
def test_infinite_failed_ready_repairs_cannot_starve_all_first_dates_across_restarts(tmp_path,monkeypatch,arm):
    run=Campaign(tmp_path,monkeypatch,arm)
    first=deepcopy({day:run.cp['dates'][arm+'/'+day]['first_attempt_terminal'] for day in run.repair_days})
    for _ in range(150):
        run.cycle()
        assert len(run.cp['workers'])<=(3 if arm=='B2' else 1)
        assert run.cp['state']!='SOURCE_BLOCKED'
        run.restart()
        if arm in run.cp.get('first_sweeps_completed',{}):break
        run.finish()
    else:pytest.fail('Unending verified repairs starved the 31-date first sweep')
    initial=[event['day'] for event in run.starts if event['kind']=='initial' and event['arm']==arm]
    assert initial==[day for day in s.DAYS if day not in run.repair_days]
    assert all(run.cp['dates'][arm+'/'+day].get('first_attempt_terminal') for day in s.DAYS)
    assert {day:run.cp['dates'][arm+'/'+day]['first_attempt_terminal'] for day in run.repair_days}==first
    assert any(event['kind']=='retry' for event in run.starts)
    assert any(run.cp['dates'][arm+'/'+day]['first_attempt_terminal']['status']=='FAIL' for day in initial)
    if arm=='B2':assert run.cp['state']=='B3_RUNNING'
    else:assert set(run.cp['first_sweeps_completed'])=={'B2','B3'}


def test_two_priority_b2_repairs_start_before_next_initial_slot_and_streak_survives_restart(tmp_path,monkeypatch):
    run=Campaign(tmp_path,monkeypatch)
    run.cycle()
    assert [(event['kind'],event['day']) for event in run.starts]==[
        ('retry',s.DAYS[0]),('retry',s.DAYS[1]),('initial',s.DAYS[3])]
    run.restart()
    assert run.cp['first_sweep_retry_streak']['B2']==0
    run.finish()
    run.cycle()
    assert run.starts[-1]['kind']=='initial' and run.starts[-1]['day']==s.DAYS[4]


def test_counter_at_limit_after_restart_gives_next_free_b2_slot_to_unvisited_date(tmp_path,monkeypatch):
    run=Campaign(tmp_path,monkeypatch)
    run.cp['first_sweep_retry_streak']={'B2':2}
    r.atomic(tmp_path/'SUPERVISOR_STATE.json',run.cp)
    run.restart();run.cycle()
    assert run.starts[0]['kind']=='initial' and run.starts[0]['day']==s.DAYS[3]
    assert [event['kind'] for event in run.starts]==['initial','retry','retry']


@pytest.mark.parametrize('error',[r.LeaseBusy('ISOLATED_OPERATOR_LOCK'),RuntimeError('ISOLATED_FAILED_RETRY_START')])
def test_unstarted_retry_refusal_does_not_spend_persistent_dispatch_count(tmp_path,monkeypatch,error):
    run=Campaign(tmp_path,monkeypatch)
    run.cp['first_sweep_retry_streak']={'B2':1}
    def denied(*args):raise error
    monkeypatch.setattr(r,'dispatch_ready',denied)
    run.cycle()
    assert run.cp['first_sweep_retry_streak']=={'B2':1}
    assert run.starts==[] and not run.cp['workers']
    assert run.cp['state']=='B2_RUNNING'


def test_local_initial_admission_failure_visits_date_and_releases_retry_turn(tmp_path,monkeypatch):
    run=Campaign(tmp_path,monkeypatch)
    run.cp['first_sweep_retry_streak']={'B2':2}
    def failed_initial(root,manifest,cp,arm,day,slot):raise ValueError('ISOLATED_DAILY_ADMISSION_FAILURE')
    monkeypatch.setattr(s,'dispatch',failed_initial)
    run.cycle()
    row=run.cp['dates']['B2/'+s.DAYS[3]]
    assert row['first_attempt_terminal']['status']=='FAIL'
    assert row['new_attempt_native_runtime']==0. and row['Native_Runtime']==0.
    assert [event['kind'] for event in run.starts]==['retry','retry']
    assert run.cp['state']=='B2_RUNNING'


def test_common_source_block_does_not_consume_or_reset_dispatch_turn(tmp_path,monkeypatch):
    run=Campaign(tmp_path,monkeypatch)
    run.cp['first_sweep_retry_streak']={'B2':2}
    def blocked(*args):raise r.SourceBlocked('GLOBAL_SOURCE_INTEGRITY_FAILURE:ISOLATED_FIXTURE')
    monkeypatch.setattr(s,'dispatch',blocked)
    run.cycle()
    assert run.cp['state']=='SOURCE_BLOCKED'
    assert run.cp['first_sweep_retry_streak']=={'B2':2}
    assert run.starts==[]
    assert 'first_attempt_terminal' not in run.cp['dates']['B2/'+s.DAYS[3]]


def test_healthy_third_worker_and_native_prefix_are_preserved_while_free_slots_advance(tmp_path,monkeypatch):
    run=Campaign(tmp_path,monkeypatch)
    worker=run.worker('B2',s.DAYS[4],3,'initial')
    run.cp['workers']['B2/'+s.DAYS[4]]=worker
    run.cp['dates']['B2/'+s.DAYS[4]].update(status='RUNNING',Native_Runtime=17.)
    run.held.add(worker['PID'])
    ledger=tmp_path/'HEALTHY_NATIVE_PREFIX.json'
    r.atomic(ledger,dict(measured_Native_Runtime=17.,calls=[dict(Native_Runtime=17.,entered_native=True)]))
    before=ledger.read_bytes();owned=deepcopy(worker);row=deepcopy(run.cp['dates']['B2/'+s.DAYS[4]])
    run.cp['first_sweep_retry_streak']={'B2':2}
    run.cycle()
    assert run.cp['workers']['B2/'+s.DAYS[4]]==owned
    assert run.cp['dates']['B2/'+s.DAYS[4]]==row
    assert ledger.read_bytes()==before
    assert len(run.cp['workers'])==3
    assert run.starts[-2]['kind']=='initial' and run.starts[-2]['day']==s.DAYS[3]
    assert run.starts[-1]['kind']=='retry'


def test_both_completed_sweeps_have_no_artificial_repair_delay(tmp_path,monkeypatch):
    run=Campaign(tmp_path,monkeypatch)
    for row in run.cp['dates'].values():row['status']='FAIL'
    s.initialize_history(run.cp)
    run.cp['first_sweeps_completed']={arm:dict(dates=31) for arm in ('B2','B3')}
    run.cp['first_sweep_retry_streak']={'B2':2,'B3':1}
    run.cycle()
    assert [(event['kind'],event['day']) for event in run.starts]==[
        ('retry',s.DAYS[0]),('retry',s.DAYS[1]),('retry',s.DAYS[2])]
    assert run.cp['state']=='B2_REPAIRING' and len(run.cp['workers'])==3
    assert run.cp['first_sweep_retry_streak']=={'B2':2,'B3':1}


@pytest.mark.parametrize('invalid',[True,-1,3,'2'])
def test_invalid_persistent_dispatch_accounting_is_not_silently_reset(tmp_path,monkeypatch,invalid):
    run=Campaign(tmp_path,monkeypatch)
    run.cp['first_sweep_retry_streak']={'B2':invalid}
    with pytest.raises(PermissionError,match='FIRST_SWEEP_DISPATCH_ACCOUNTING_DRIFT'):run.cycle()
    assert run.starts==[] and not run.cp['workers']
