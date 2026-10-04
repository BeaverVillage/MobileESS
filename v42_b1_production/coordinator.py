"""Serial five-stage days, durable receipts, independent one-second telemetry."""
import csv
import io
import os
import subprocess
import sys
import time
import uuid
import threading
import psutil
from .common import *
from .worker import valid_receipt
from v42_orchestrator.ledger import CoordinatorLock
from .telemetry import LiveTelemetry


def process_identity(pid):
    p=psutil.Process(pid)
    return dict(PID=pid,creation_time=p.create_time(),command=p.cmdline(),parent_PID=p.ppid())


def same_process(value):
    try:
        p=psutil.Process(value['PID'])
        return p.is_running() and abs(p.create_time()-value['creation_time'])<.1 and p.cmdline()==value['command']
    except (psutil.NoSuchProcess,psutil.AccessDenied,KeyError): return False


def atomic_csv(path,rows,fields):
    # Same fsync/replace discipline as JSON; readers can never see truncation.
    import tempfile
    stream=io.StringIO(newline=''); writer=csv.DictWriter(stream,fields,lineterminator='\n')
    writer.writeheader(); writer.writerows({k:r.get(k) for k in fields} for r in rows)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('w',encoding='utf-8',newline='') as f:
        f.write(stream.getvalue()); f.flush(); os.fsync(f.fileno())
    try:
        for attempt in range(8):
            try: os.replace(temporary,path); break
            except PermissionError:
                if attempt==7: raise
                time.sleep(.01*(attempt+1))
    finally: temporary.unlink(missing_ok=True)


class Campaign:
    def __init__(self,root):
        self.root=Path(root).resolve(); self.freeze=read(self.root/'B1_PRODUCTION_FREEZE_MANIFEST.json')
        self.config=Config(**read(self.root/'B1_CAMPAIGN_CONFIG.json'))
        verify_freeze(self.freeze,read(self.root/'B1_CAMPAIGN_CONFIG.json'))
        self.lock=CoordinatorLock(self.root/'COORDINATOR.lock')
        self.me=process_identity(os.getpid()); self.state=read(self.root/'CHECKPOINT.json')
        if self.state['run_id']!=self.freeze['run_id'] or self.state['scientific_SHA']!=self.freeze['scientific_SHA']:
            raise PermissionError('CHECKPOINT_IDENTITY')
        self.status='RUNNING'; self.active=None; self.progress=dict(phase='SOURCE_VERIFICATION'); self.failure=[]
        self.telemetry=LiveTelemetry(self.root,self.config); self.telemetry.start()
        self.stop=threading.Event(); self.last_publish_error=None
        self.publish()
        def loop():
            deadline=time.monotonic()+1
            while not self.stop.wait(max(0,deadline-time.monotonic())):
                try: self.publish()
                except BaseException as e: self.last_publish_error=str(e)
                deadline=max(deadline+1,time.monotonic())
        self.thread=threading.Thread(target=loop,name='B1-status-heartbeat',daemon=True); self.thread.start()

    def publish(self):
        with self.telemetry.lock:
            resource=dict(self.telemetry.samples[-1])
        resource['B1_tree_RSS_GiB']=resource.pop('B1_tree_RSS_GiB')+psutil.Process().memory_info().rss/2**30
        resource['A1_solver_RSS_GiB']=sum(v['RSS_GiB'] for v in resource['worker_trees'].values() if v['stage']=='A1')
        atomic(self.root/'B1_RESOURCE_LIVE.json',resource)
        heartbeat=dict(timestamp_UTC=now(),run_id=self.freeze['run_id'],state=self.status,process=self.me,
                       active=self.active,worker_count=int(bool(self.active and self.active.get('worker'))),B1_DAY_WORKERS=1,Threads=1)
        atomic(self.root/'B1_HEARTBEAT.json',heartbeat)
        rows=[]; stages=[]
        for day in self.freeze['days']:
            day_rows=[]
            for stage in STAGES:
                row=self.state['stages'][day+'/'+stage]; day_rows.append(row)
                stages.append(dict(day=day,stage=stage,status=row['status'],receipt=row.get('receipt'),sha256=row.get('sha256'),attempts=row.get('attempts',0)))
            passed=all(r['status']=='PASS' for r in day_rows)
            failed=any(r['status']=='FAIL' for r in day_rows)
            status='PASS' if passed else 'FAIL' if failed else self.status if self.active and self.active['day']==day else 'NOT_RUN'
            failures=[f for f in self.state['failures'] if f['day']==day and not f['resolved']]
            rows.append(dict(day=day,status=status,stage=self.active['stage'] if self.active and self.active['day']==day else None,
                             reason=failures[-1]['reason'] if failures else None))
        live=dict(run_id=self.freeze['run_id'],state=self.status,timestamp_UTC=now(),process=self.me,
                  active=self.active,progress=self.progress,PASS_days=sum(r['status']=='PASS' for r in rows),days_total=31,
                  stage_PASS=sum(r['status']=='PASS' for r in stages),stage_total=155,
                  day_rows=rows,B1_DAY_WORKERS=1,Threads=1,A1_TimeLimit=1800,
                  B2=0,B3=0,M1=0,M2=0,auto_advance=False)
        atomic(self.root/'B1_LIVE_STATUS.json',live)
        atomic(self.root/'B1_DAY_STATUS.json',dict(run_id=self.freeze['run_id'],days=rows))
        atomic_csv(self.root/'B1_DAY_STATUS.csv',rows,('day','status','stage','reason'))
        atomic_csv(self.root/'B1_STAGE_LEDGER.csv',stages,('day','stage','status','receipt','sha256','attempts'))
        atomic_csv(self.root/'B1_FAILURE_LEDGER.csv',self.state['failures'],('day','stage','reason','UTC','resolved'))

    def checkpoint(self): atomic(self.root/'CHECKPOINT.json',self.state)

    def receipt_ok(self,day,stage,row):
        try:
            return sha(row['receipt'])==row['sha256'] and valid_receipt(read(row['receipt']),identity(self.freeze,day,stage),self.root)
        except (KeyError,OSError,ValueError): return False

    def verify_sources(self):
        if python_environment()!=self.freeze['Python_environment']: raise PermissionError('FROZEN_PYTHON_ENVIRONMENT_DRIFT')
        current=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        if current!=self.freeze['Git_SHA']: raise PermissionError('FROZEN_EXECUTION_GIT_SHA_DRIFT')
        for row in self.freeze['sources']:
            if sha(row['path'])!=row['sha256']: raise PermissionError('SOURCE_SHA_DRIFT:'+row['path'])
        from tools.v42.preflight_b1_may import barrier,B0_ROOT
        gate=barrier(read(ROOT/'docs/v42_may_b0_production_31d/B0_CAMPAIGN_FINAL.json'),read(B0_ROOT/'CAMPAIGN_STATE.json'),B0_ROOT)
        if not gate['PASS']: raise PermissionError('B0_BARRIER_NO_LONGER_VALID')

    def resource_state(self):
        if self.telemetry.get() is None or self.last_publish_error: return 'HARD_GUARD'
        with self.telemetry.lock: return admission(self.telemetry.samples[-1])

    def wait_admission(self,day,stage):
        self.active=dict(day=day,stage=stage,worker=None)
        while True:
            gate=self.resource_state()
            if gate=='SAFE' or (stage!='A1' and gate=='WAIT_RESOURCE'): return
            self.status='WAIT_RESOURCE'
            self.progress=dict(phase='ADMISSION',reason=gate)
            time.sleep(1)

    def run_stage(self,day,stage):
        row=self.state['stages'][day+'/'+stage]
        if row['status']=='PASS' and self.receipt_ok(day,stage,row): return True
        # Recover a worker that outlived the coordinator. Wait for its exact PID
        # identity/result; never spawn a competing day or terminate a foreign PID.
        if row.get('worker') and same_process(row['worker']):
            self.active=dict(day=day,stage=stage,worker=row['worker']); self.status='RUNNING'
            self.telemetry.register(row['worker']['PID'],day,stage)
            while same_process(row['worker']):
                self.load_progress(row); self.enforce_guard(row); time.sleep(1)
            self.telemetry.unregister(row['worker']['PID'])
        if row.get('request'):
            request=read(row['request'])
            if Path(request['result']).exists() and valid_receipt(read(request['result']),identity(self.freeze,day,stage),self.root):
                row.update(status='PASS',receipt=request['result'],sha256=sha(request['result']),worker=None)
                self.checkpoint(); return True
        if row['status']=='FAIL': return False
        dependencies={}
        for prior in STAGES[:STAGES.index(stage)]:
            dep=self.state['stages'][day+'/'+prior]
            if not self.receipt_ok(day,prior,dep): raise PermissionError('CAUSAL_RECEIPT_CHAIN')
            dependencies[prior]=dict(receipt=dep['receipt'],sha256=dep['sha256'])
        while True:
            self.wait_admission(day,stage)
            attempts=row.get('attempts',0)+1
            attempt=self.root/'a'/day.replace('-','')/str(STAGES.index(stage))/str(attempts)
            attempt.mkdir(parents=True,exist_ok=False)
            request=dict(root=str(self.root),day=day,stage=stage,mode='B1_PRODUCTION',identity=identity(self.freeze,day,stage),
                         dependencies=dependencies,output=str(attempt/'o'),progress=str(attempt/'progress.json'),
                         result=str(attempt/'result.json'),error=str(attempt/'error.json'))
            atomic(attempt/'request.json',request)
            # Persist the new attempt before spawn; recovery also discovers its
            # exact process command if a crash occurs before PID publication.
            row.update(status='RUNNING',attempts=attempts,request=str(attempt/'request.json'),worker=None)
            row.pop('guard_started',None)
            self.checkpoint()
            command=[self.freeze['Python'],'-m','v42_b1_production.worker',str(attempt/'request.json')]
            with (attempt/'stdout.log').open('wb') as out,(attempt/'stderr.log').open('wb') as err:
                p=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
            row['worker']=process_identity(p.pid); self.checkpoint()
            self.telemetry.register(p.pid,day,stage); self.active=dict(day=day,stage=stage,worker=row['worker'])
            self.status='RUNNING'; interrupted=False
            while p.poll() is None:
                self.load_progress(row)
                interrupted=self.enforce_guard(row) or interrupted
                time.sleep(1)
            self.telemetry.unregister(p.pid)
            row['worker']=None
            if not interrupted and Path(request['result']).exists() and valid_receipt(read(request['result']),identity(self.freeze,day,stage),self.root):
                for f in self.state['failures']:
                    if f['day']==day and f['stage']==stage: f['resolved']=True
                row.update(status='PASS',receipt=request['result'],sha256=sha(request['result'])); self.checkpoint(); return True
            error=read(request['error']) if Path(request['error']).exists() else dict(error='WORKER_EXIT_'+str(p.returncode))
            reason=error['error']
            infrastructure=('WORKER_EXIT_' in reason or 'LICENSE' in reason.upper() or 'OUT OF MEMORY' in reason.upper() or error.get('type')=='MemoryError')
            recoverable=interrupted or (infrastructure and attempts<=3)
            row['failure_kind']='INFRASTRUCTURE' if infrastructure else 'SCIENTIFIC'
            self.state['failures'].append(dict(day=day,stage=stage,reason=reason,UTC=now(),resolved=False))
            row.update(status='INTERRUPTED' if recoverable else 'FAIL'); self.checkpoint()
            if not recoverable: return False
            self.progress={}

    def load_progress(self,row):
        try: self.progress=read(read(row['request'])['progress'])
        except (OSError,ValueError): self.progress={}

    def enforce_guard(self,row):
        if self.resource_state()!='HARD_GUARD': return False
        request=read(row['request']); atomic(Path(request['output']).parent/'CANCEL.json',dict(reason='RESOURCE_HARD_GUARD',UTC=now()))
        self.status='INTERRUPTING_RESOURCE_GUARD'
        if not row.get('guard_started'): row['guard_started']=time.time()
        # Own registered exact process only. Gurobi callback normally terminates
        # first; a blocked build gets a bounded emergency tree stop.
        if time.time()-row['guard_started']>10 and same_process(row['worker']):
            own=psutil.Process(row['worker']['PID'])
            for child in own.children(recursive=True): child.kill()
            own.kill()
        return True

    def run(self):
        try:
            self.verify_sources()
            # Recover spawn/checkpoint gap from command, never name-only matching.
            for row in self.state['stages'].values():
                if row['status']=='RUNNING' and not row.get('worker') and row.get('request'):
                    for p in psutil.process_iter(['cmdline']):
                        cmd=p.info['cmdline'] or []
                        if 'v42_b1_production.worker' in cmd and row['request'] in cmd: row['worker']=process_identity(p.pid)
            failed_days=[]
            for day in self.freeze['days']:
                for stage in STAGES:
                    if not self.run_stage(day,stage):
                        row=self.state['stages'][day+'/'+stage]
                        if row.get('failure_kind')=='INFRASTRUCTURE':
                            self.status='FAIL'; self.publish()
                            atomic(self.root/'B1_CAMPAIGN_FINAL.json',dict(scientific_PASS=False,state='FAIL',infrastructure_failure=True,failed_day=day,failed_stage=stage,run_id=self.freeze['run_id']))
                            return 0
                        failed_days.append(day)
                        for remaining in STAGES[STAGES.index(stage)+1:]:
                            self.state['stages'][day+'/'+remaining]['status']='BLOCKED_BY_FAILED_STAGE'
                        self.checkpoint()
                        break  # Preserve this day's FAIL, continue other independent dates.
            self.status='FAIL' if failed_days else 'COMPLETE'; self.active=None; self.progress={}; self.publish()
            stage_pass=sum(r['status']=='PASS' for r in self.state['stages'].values())
            atomic(self.root/'B1_CAMPAIGN_FINAL.json',dict(scientific_PASS=not failed_days,state=self.status,
                 run_id=self.freeze['run_id'],days_evaluated=31,failed_days=failed_days,
                 PASS_days=31-len(failed_days),stage_PASS=stage_pass,B2=0,B3=0,M1=0,M2=0))
            return 0
        except BaseException as e:
            self.status='INFRASTRUCTURE_FAILURE'; self.publish()
            atomic(self.root/'COORDINATOR_ERROR.json',dict(error=str(e),type=type(e).__name__,UTC=now()))
            raise
        finally:
            self.stop.set(); self.thread.join(timeout=4); self.telemetry.close(); self.lock.close()


def run(root): return Campaign(root).run()
