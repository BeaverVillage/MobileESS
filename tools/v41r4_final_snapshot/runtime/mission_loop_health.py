"""Read-only scientific audit plus isolated campaign health/status outputs."""
from pathlib import Path
import json,time,os,hashlib,shutil,collections,traceback
import psutil
from datetime import datetime
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'frozen_artifacts/v41r4_may'
RUN=BASE/'loop_wall_v4'
OUT=RUN/'audit/mission'
LOG=ROOT/'logs/v41r4_may/loop_wall_v4/mission'
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def timestamp(value):
    return float(value) if isinstance(value,(int,float)) else datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    q=p.with_name(p.name+f'.{os.getpid()}.{time.time_ns()}.tmp');q.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    for attempt in range(30):
        try:os.replace(q,p);return
        except PermissionError:
            if attempt==29:raise
            time.sleep(.1)
def rec(r):
    p=Path(r['path'])
    assert p.stat().st_size==r['bytes'],str(p)
    with p.open('rb') as f: actual=hashlib.file_digest(f,'sha256').hexdigest()
    assert actual==r['sha256'],'HASH_DRIFT: '+str(p)
def refs(x):
    if isinstance(x,dict):
        if all(k in x for k in ('path','sha256','bytes')):rec(x)
        else:
            for v in x.values():refs(v)
    elif isinstance(x,list):
        for v in x:refs(v)
def receipt_check(p):
    x=read(p);assert x['status']=='COMPLETE';refs(x.get('files',{}));refs(x.get('science',{}))
    from dayahead.v41.scientific_archive import verify_manifest
    verify_manifest(p.parent/'SCIENTIFIC_MANIFEST.json')
    return x
def main():
    now=time.time();OUT.mkdir(parents=True,exist_ok=True);LOG.mkdir(parents=True,exist_ok=True)
    previous=read(OUT/'HEALTH_LATEST.json') if (OUT/'HEALTH_LATEST.json').exists() else {}
    state=read(RUN/'campaign_progress.json');alerts=[];processes=[]
    finished=read(RUN/'CAMPAIGN_FINISHED.json') if (RUN/'CAMPAIGN_FINISHED.json').exists() else None
    terminal=bool(finished and finished['status']=='COMPLETE' and not finished.get('errors'))
    expected=([] if terminal else [dict(worker_pid=state['supervisor_pid'],phase='supervisor')])+state['active']
    prior={x['pid']:x for x in previous.get('processes',[])}
    for row in expected:
        pid=row['worker_pid']
        try:
            p=psutil.Process(pid);cmd=p.cmdline();assert any('v41r4_' in s or 'mission_' in s for s in cmd),'PID_REUSED'
            cpu=sum(p.cpu_times()[:2]);old=prior.get(pid,{});delta=cpu-old.get('cpu_seconds',cpu)
            latest=Path(row['log']).stat().st_mtime if row.get('log') else (RUN/'campaign_progress.json').stat().st_mtime
            if row.get('day'):
                policy=row['phase'].split('_')[0]
                folder=RUN/row['day']/policy
                latest=max([latest]+[p.stat().st_mtime for p in folder.rglob('*') if p.is_file()])
            children=[]
            for c in p.children(recursive=True):
                try:children.append(dict(pid=c.pid,created_at=c.create_time(),cpu_seconds=sum(c.cpu_times()[:2])))
                except psutil.NoSuchProcess:pass
            prior_children={c['pid']:c for c in old.get('children',[])}
            child_delta=sum(max(0,c['cpu_seconds']-prior_children.get(c['pid'],{}).get('cpu_seconds',0)) for c in children)
            activity=now if delta>0 or child_delta>0 else old.get('last_cpu_progress_time',previous.get('checked_at',now))
            entry=dict(pid=pid,created_at=p.create_time(),cmd=cmd,cpu_seconds=cpu,cpu_delta_seconds=delta,child_cpu_delta_seconds=child_delta,last_cpu_progress_time=activity,last_progress_time=latest,children=children,**{k:v for k,v in row.items() if k not in ('worker_pid','created_at')})
            if old and now-max(activity,latest)>1200:alerts.append(dict(kind='STALE_SUSPECT',pid=pid,idle_seconds=now-max(activity,latest)))
            processes.append(entry)
        except (psutil.NoSuchProcess,AssertionError) as e:
            done=RUN/'audit'/row.get('day','')/f"PHASE_{row.get('phase')}.json"
            if not (done.exists() and read(done)['status']=='PASS'):alerts.append(dict(kind='EXPECTED_PROCESS_MISSING',pid=pid,error=str(e)))
    if not terminal and now-state['updated_at']>60:alerts.append(dict(kind='SUPERVISOR_HEARTBEAT_STALE',age=now-state['updated_at']))
    for e in state.get('errors',[]):alerts.append(dict(kind='PHASE_FAILURE',detail=e))
    probes=[]
    for folder in (OUT,LOG):
        probe=folder/f'.write_probe_{os.getpid()}';probe.write_text('write verification',encoding='utf-8');assert probe.read_text()=='write verification';probe.unlink();probes.append(str(folder))
    disk=shutil.disk_usage(ROOT)
    if disk.free<10*1024**3:alerts.append(dict(kind='LOW_DISK',free_bytes=disk.free))
    release=read(RUN/'audit/MAY_CAMPAIGN_RELEASE_V4.json')
    assert [release[k] for k in ('alpha_BG','AIDC_GPU','MESS_vehicles','MESS_kW','MESS_kVA','MESS_kWh')]==[1.15,780,4,300,400,1200]
    refs(release['source'])
    inputs=[]
    for p in (BASE/'audit').glob('2025-05-*/INPUT_PREPARATION.json'):
        try:
            x=read(p);assert x['status']=='PASS' and x['raw_Q90_and_H4_exact']
            if x['day']=='2025-05-04':
                assert x['new_snapshot']['sha256']==x['raw_prediction_source']['sha256'] and x['ML_prediction_calls']==0
                snap=read(x['new_snapshot']['path']);assert {sum(row) for row in snap['future_service_capacity_gpu']}=={780} and set(snap['H4_CAP_PHYS'])=={3120}
            else:
                assert x['physical_GPU']==780 and x['H4_physical_GPUh']==3120
                assert x['ML_retrain_count']==x['ML_recalibration_count']==x['ML_model_change_count']==0
            refs(x);inputs.append(str(p))
        except Exception as e:alerts.append(dict(kind='INPUT_VALIDATION_FAILURE',path=str(p),error=repr(e)))
    write(OUT/'INPUT_REUSE_VALIDATION.json',dict(checked_at=now,validated_inputs=inputs,count=len(inputs)))
    electrical=[]
    from dayahead.v41.electrical import verify_generation_proof
    for p in (BASE/'e').glob('*/V41_ELECTRICAL_CERTIFICATE.json'):
        try:
            c=read(p);verify_generation_proof(c)
            assert c['input_identity']['identity']['inputs']['V41R4_FINAL_DATE_BINDING']['alpha_BG']==1.15
            refs(c['input_identity']);refs(c['outputs']);refs(c['mapper_audit'])
            electrical.append(dict(path=str(p),status='VALIDATED_ALPHA_1_15',old_cache_reuse=0))
        except Exception as e:alerts.append(dict(kind='ELECTRICAL_VALIDATION_FAILURE',path=str(p),error=repr(e)))
    units=[];inventory=[];active={(r.get('day'),r.get('phase')):r for r in processes}
    for day in release['days']:
        for policy in release['policies']:
            da=RUN/day/policy/'dayahead/DAYAHEAD_RECEIPT.json';ac=RUN/day/policy/'actual/ACTUAL_RECEIPT.json'
            row=dict(day=day,policy=policy,status='NOT_STARTED',pid=None,start_time=None,last_progress_time=None,retry_count=0,runtime_seconds=0,artifact_path=str(RUN/day/policy),dayahead_complete=False,actual_complete=False)
            preserved_failures=list(OUT.glob(f'PRESERVED_PHASE_{day}_{policy}_*_FAILURE.json'))
            row['retry_count']=len(preserved_failures)
            if preserved_failures and not ac.exists():row['status']='FAILED_RETRYING'
            receipt_starts=[];receipt_ends=[];producer_runtime=0.
            row['blocked_duplicate_attempts']=int(policy=='B1' and (OUT/f'{day}_DUPLICATE_DISPATCH_FAILURE.json').exists())
            for phase in ('electrical','domain') if policy=='B0' else ():
                if (day,phase) in active:
                    a=active[day,phase];row.update(status='RUNNING',pid=a['pid'],start_time=a.get('started_at'),last_progress_time=a['last_progress_time'],phase=phase)
            phases=[]
            for phase in (policy+'_DA',policy+'_AC'):
                p=RUN/'audit'/day/f'PHASE_{phase}.json'
                if p.exists():
                    x=read(p);phases.append(x);row['runtime_seconds']+=x.get('elapsed_seconds',0)
                    if x['status']!='PASS':row['status']='FAILED_RETRYING';alerts.append(dict(kind='FAILED_RECEIPT',path=str(p),error=x.get('error')))
                if (day,phase) in active:
                    a=active[day,phase];row.update(status='RUNNING',pid=a['pid'],start_time=a.get('started_at'),last_progress_time=a['last_progress_time']);row['runtime_seconds']+=now-a.get('started_at',now)
            try:
                if da.exists():
                    d=receipt_check(da);row['dayahead_complete']=True
                    begin=timestamp(d['started_at']);end=timestamp(d['completed_at']);assert end>=begin
                    receipt_starts.append(begin);receipt_ends.append(end);producer_runtime+=end-begin
                    planning=read(da.parent/'PLANNING_RESULT.json');assert planning['Actual_reads']==0
                    assert not read(da.parent/'JOINT_FREEZE_RECEIPT.json')['Actual_data_opened']
                    row['fresh_status']=read(da.parent/'FRESH_RESULT.json')['summary']['convergence_count'];assert row['fresh_status']==96
                    if row['status']=='NOT_STARTED':row['status']='COMPLETE'
                if ac.exists():
                    a=receipt_check(ac);assert d['decision_SHA']==a['decision_SHA']
                    begin=timestamp(a['started_at']);end=timestamp(a['completed_at']);assert end>=begin
                    receipt_starts.append(begin);receipt_ends.append(end);producer_runtime+=end-begin
                    result=read(ac.parent/'ACTUAL_RESULT.json');assert result['Actual_optimizer_calls']==0 and result['decision_SHA']==d['decision_SHA']
                    boundary=read(ac.parent/'ACTUAL_BOUNDARY_RECEIPT.json')
                    imported=RUN/'audit'/day/f'CACHED_ACTUAL_IMPORT_{policy}.json'
                    if imported.exists():
                        cache=read(imported);assert policy in ('B0','B2') and cache['status']=='PASS'
                        refs(cache)
                        assert cache['original_receipt']['sha256']==hashlib.sha256(ac.read_bytes()).hexdigest()
                        assert set(cache['all_four_new_DA_freezes'])==set(release['policies'])
                        for cp,cr in cache['all_four_new_DA_freezes'].items():
                            assert Path(cr['path']).resolve()==(RUN/day/cp/'dayahead/DAYAHEAD_RECEIPT.json').resolve()
                        boundary=cache
                    assert all(read(RUN/day/p/'dayahead/DAYAHEAD_RECEIPT.json')['completed_at']<=boundary['opened_at'] for p in release['policies'])
                    native=read(ac.parent/'grid/NATIVE_ACTUAL_STATE_CONTINUITY.json');assert native['status']=='PASS' and native['independent_resets_after_D00']==0
                    from v41r4_report import grid_summary
                    for folder in (da.parent,ac.parent):assert grid_summary(folder)['convergence_count']==96
                    if policy=='B3':
                        audit=read(da.parent/'A1/V41R4_A1_B1_EQUIVALENCE_AUDIT.json')
                        assert all(audit[k]=='YES' for k in ('A1_B1_EQUIVALENT_ALGORITHM','A1_MESS_FIXED','COMPOUND_NET_EFFECT_USED_IN_A1'))
                    row.update(status='COMPLETE_VALIDATED',actual_complete=True)
            except Exception as e:row.update(status='FAILED_RETRYING',validation_error=repr(e));alerts.append(dict(kind='ARTIFACT_VALIDATION_FAILURE',day=day,policy=policy,error=repr(e)))
            if phases:
                starts=[p['started_at'] for p in phases if 'started_at' in p];ends=[p['completed_at'] for p in phases if 'completed_at' in p]
                if starts:row['start_time']=min(starts)
                if ends:row['last_progress_time']=max(row['last_progress_time'] or 0,max(ends))
            if receipt_starts:row['start_time']=min(receipt_starts+[row['start_time']] if row['start_time'] else receipt_starts)
            if receipt_ends:row['last_progress_time']=max(receipt_ends+[row['last_progress_time'] or 0])
            row['completed_producer_runtime_seconds']=producer_runtime
            row['runtime_seconds']=max(row['runtime_seconds'],producer_runtime)
            units.append(row)
            for root in (BASE,RUN):
                p=root/day/policy/'dayahead/DAYAHEAD_RECEIPT.json'
                if p.exists():inventory.append(dict(day=day,policy=policy,path=str(p),classification='CURRENT' if root==RUN else 'REUSE_B0_B2' if policy in ('B0','B2') else 'SUPERSEDED_RUNTIME_OR_A1_FIX',status=read(p)['status']))
    result=dict(checked_at=now,status='ATTENTION_REQUIRED' if alerts else 'HEALTHY_RUNNING',processes=processes,alerts=alerts,free_disk_bytes=disk.free,writable_paths=probes,counts=dict(collections.Counter(r['status'] for r in units)),dayahead_complete=sum(r['dayahead_complete'] for r in units),actual_complete=sum(r['actual_complete'] for r in units),campaign_status=state['status'],electrical_validated=len(electrical))
    write(OUT/'ELECTRICAL_REUSE_VALIDATION.json',dict(checked_at=now,certificates=electrical))
    write(OUT/'CAMPAIGN_STATUS_TABLE.json',dict(updated_at=now,units=units))
    write(OUT/'ARTIFACT_INVENTORY.json',dict(checked_at=now,policy_receipts=inventory,electrical_certificates=[str(p) for p in (BASE/'e').glob('*/V41_ELECTRICAL_CERTIFICATE.json')],input_preparations=[str(p) for p in (BASE/'audit').glob('2025-05-*/INPUT_PREPARATION.json')]))
    write(OUT/'HEALTH_LATEST.json',result);write(LOG/f'health_{int(now)}.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='processes'},ensure_ascii=False))
if __name__=='__main__':main()
