"""Bounded independent-process replay queue; this script cannot optimize."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import psutil
import shutil
import subprocess
import sys
import time

sys.path.insert(0, 'D:/v42voltage')
from v42_voltage_control.authority import source_files, verify_frozen_infrastructure
from v42_voltage_control.integration import record
from v42_b3_joint.contracts import digest

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write(path, value, *, exclusive=False):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if exclusive:
        with path.open('x',encoding='utf8') as stream: json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
    else:
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
        os.replace(temporary,path)

def utc():
    return datetime.now(timezone.utc).isoformat()

def main(args):
    started=time.perf_counter()
    root=Path(args.output).resolve();root.mkdir(parents=True,exist_ok=True)
    sources=source_files();sha=digest(sources)
    infrastructure={name:record(path) for name,path in [('SVR4',args.svr4),('SVR7',args.svr7)]}
    scenarios={name:verify_frozen_infrastructure(item,sha)[1] for name,item in infrastructure.items()}
    assert len(scenarios['SVR4']['svr']['units'])==4 and len(scenarios['SVR7']['svr']['units'])==7
    assert scenarios['SVR4']['svr']['units']==scenarios['SVR7']['svr']['units'][:4]
    queue=read(args.queue)
    ordered=[next(j for j in queue['jobs'] if j['arm']==arm and j['day']==day) for arm,day in (
        ('B2','2025-05-01'),('B1','2025-05-28'),('B2','2025-05-02'),('B2','2025-05-03'),('B0','2025-05-01'))]
    keys={(j['arm'],j['day']) for j in ordered}
    ordered += [j for j in queue['jobs'] if (j['arm'],j['day']) not in keys]
    jobs=[dict(configuration=name,arm=job['arm'],day=job['day'],priority=number+1,
        path=str(root/name/'days'/job['arm']/job['day']))
        for number,job in enumerate(ordered) for name in ('SVR4','SVR7')]
    proof=dict(schema='V42_SVR4_SVR7_AC_ONLY_DISPATCH_V1',created_UTC=utc(),source_SHA=sha,
        source_map=sources,original_queue=record(args.queue),driver=record(args.driver),dispatcher=record(__file__),
        infrastructure=infrastructure,scenarios={k:v['scenario_SHA'] for k,v in scenarios.items()},
        max_independent_AC_processes=args.workers,eligible_original_frozen_policy_days=len(ordered),
        unavailable_original_frozen_policy_days=124-len(ordered),jobs=jobs,
        Native_optimizer_calls=0,new_Planning_optimization=False,new_E2E_qualified=False,
        original_RegControl7='UNCHANGED_AUTO',original_caps4='FIXED_ON',DSTATCOM_devices=0,CapControl_devices=0,
        measurement_scope='96 chronological final slot states; native automatic due events and delay retained')
    write(root/'DISPATCH_SOURCE_RECEIPT.json',proof,exclusive=True)
    shutil.copyfile(__file__,root/'DISPATCHER_USED.py')
    running={};terminal={};stopped=None
    for job in jobs:
        target=Path(job['path'])/'AC_ONLY_DAY_RESULT.json'
        if target.exists():
            result=read(target)
            if (result.get('source_SHA')!=sha or result.get('scenario_SHA')!=scenarios[job['configuration']]['scenario_SHA']
                or result.get('infrastructure')!=infrastructure[job['configuration']]
                or read(Path(job['path'])/'JOB_SOURCE_PROVENANCE.json')['driver']!=proof['driver']):
                raise PermissionError('ONLY_SAME_SOURCE_SAME_SCENARIO_MEASURED_RESUME_ALLOWED')
            terminal[(job['configuration'],job['arm'],job['day'])]=result
    def snapshot(status):
        counts={name:{key:sum(r['configuration']==name and r['status']==key for r in terminal.values())
            for key in ('PASS','PHYSICAL_FAIL','IMPLEMENTATION_OR_SOURCE_FAILURE')} for name in ('SVR4','SVR7')}
        value=dict(schema='V42_SVR4_SVR7_AC_ONLY_PROGRESS_V1',updated_UTC=utc(),status=status,source_SHA=sha,
            planned_comparisons=len(jobs),completed_comparisons=len(terminal),remaining_comparisons=len(jobs)-len(terminal),
            counts=counts,NOT_TESTED_no_original_plan=124-len(ordered),Native_optimizer_calls=0,
            new_Planning_E2E='NOT_RUN',deployment='HOLD',max_AC_workers=args.workers,
            running=[dict(job=item['job'],PID=item['process'].pid,create_time=item['create_time']) for item in running.values()],
            elapsed_dispatch_seconds=time.perf_counter()-started,stopped_reason=stopped)
        write(root/'DISPATCH_PROGRESS.json',value)
        with (root/'DISPATCH_PROGRESS_HISTORY.jsonl').open('a',encoding='utf8') as stream:
            stream.write(json.dumps(value,ensure_ascii=False,allow_nan=False)+'\n')
        return value
    def launch(job):
        name=job['configuration'];folder=Path(job['path'])
        if folder.exists(): raise PermissionError('PARTIAL_DAY_OUTPUT_REQUIRES_NEW_EPOCH_NEVER_OVERWRITE')
        logs=root/'logs'/name/job['arm'];logs.mkdir(parents=True,exist_ok=True)
        stdout=(logs/(job['day']+'.stdout.log')).open('xb')
        stderr=(logs/(job['day']+'.stderr.log')).open('xb')
        command=[sys.executable,'-B','-X','utf8',args.driver,'--queue',args.queue,
            '--arm',job['arm'],'--day',job['day'],'--configuration',name,'--output',str(folder),
            '--infrastructure',infrastructure[name]['path'],'--ref-scenario',args.ref_scenario,
            '--ref-time-scenario',args.ref_time_scenario]
        process=subprocess.Popen(command,cwd='D:/v42voltage',stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
        creation=psutil.Process(process.pid).create_time()
        key=(name,job['arm'],job['day'])
        running[key]=dict(process=process,create_time=creation,stdout=stdout,stderr=stderr,job=job,started=time.perf_counter())
        write(logs/(job['day']+'.PROCESS.json'),dict(command=command,PID=process.pid,create_time=creation,job=job,source_SHA=sha,started_UTC=utc()),exclusive=True)
        print(json.dumps(dict(event='START',configuration=name,arm=job['arm'],day=job['day'],PID=process.pid),ensure_ascii=False),flush=True)
    # The two required known dates are reproduced serially before expansion.
    required={(name,arm,day) for name in ('SVR4','SVR7') for arm,day in [('B2','2025-05-01'),('B1','2025-05-28')]}
    representatives=required | {(name,arm,day) for name in ('SVR4','SVR7')
        for arm,day in [('B2','2025-05-02'),('B2','2025-05-03'),('B0','2025-05-01')]}
    while len(terminal)<len(jobs):
        if source_files()!=sources: stopped='EXECUTION_SOURCE_MUTATION';snapshot('IMPLEMENTATION_STOP');raise PermissionError(stopped)
        for key,item in list(running.items()):
            code=item['process'].poll()
            if code is None: continue
            item['stdout'].close();item['stderr'].close()
            result_path=Path(item['job']['path'])/'AC_ONLY_DAY_RESULT.json'
            result=read(result_path) if result_path.exists() else dict(configuration=key[0],arm=key[1],day=key[2],status='IMPLEMENTATION_OR_SOURCE_FAILURE',error='PROCESS_WITHOUT_COMPLETE_DAY_RECEIPT',Native_optimizer_calls=0)
            terminal[key]=result;del running[key]
            print(json.dumps(dict(event='COMPLETE',configuration=key[0],arm=key[1],day=key[2],status=result['status'],exit_code=code,wall_seconds=result.get('wall_seconds'),metric=result.get('metric')),ensure_ascii=False),flush=True)
            if code!=0 or result['status']=='IMPLEMENTATION_OR_SOURCE_FAILURE': stopped='DAY_IMPLEMENTATION_FAILURE_PRESERVE_OUTPUTS'
        if stopped:
            snapshot('IMPLEMENTATION_STOP_WAITING_OWNED_ACTIVE_PROCESSES')
            if not running: break
            time.sleep(.5);continue
        first_complete=required.issubset(terminal)
        if first_complete and any(terminal[key]['status']!='PASS' for key in required):
            stopped='REQUIRED_KNOWN_DAY_PHYSICAL_CANARY_FAILED_NO_MONTHLY_EXPANSION'
            snapshot('PHYSICAL_CANARY_STOP_PRESERVE_ALL_EVIDENCE')
            if not running: break
            time.sleep(.5);continue
        representative_complete=representatives.issubset(terminal)
        if representative_complete and any(terminal[key]['status']!='PASS' for key in representatives):
            stopped='REPRESENTATIVE_PHYSICAL_CANARY_FAILED_NO_MONTHLY_EXPANSION'
            snapshot('PHYSICAL_CANARY_STOP_PRESERVE_ALL_EVIDENCE')
            if not running: break
            time.sleep(.5);continue
        limit=args.workers if first_complete else 1
        for job in jobs:
            if len(running)>=limit: break
            key=(job['configuration'],job['arm'],job['day'])
            if key in terminal or key in running: continue
            if not first_complete and key not in required: continue
            if first_complete and not representative_complete and key not in representatives: continue
            # Each SVR7 replay follows its exact SVR4 counterpart.
            if job['configuration']=='SVR7' and ('SVR4',job['arm'],job['day']) not in terminal: continue
            launch(job)
        snapshot('RUNNING_SERIAL_KNOWN_DATES' if not first_complete else
            ('RUNNING_REPRESENTATIVES' if not representative_complete else 'RUNNING_BOUNDED_AC_ONLY'))
        time.sleep(1)
    final=snapshot('COMPLETED_WITH_PHYSICAL_RESULTS' if len(terminal)==len(jobs) else
        ('STOPPED_PHYSICAL_CANARY_FAILURE' if stopped and 'PHYSICAL_CANARY_FAILED' in stopped else 'STOPPED_IMPLEMENTATION_FAILURE'))
    write(root/'DISPATCH_FINAL_RECEIPT.json',dict(**final,source_after_SHA=digest(source_files()),Native_optimizer_calls=0),exclusive=True)
    print(json.dumps(final,ensure_ascii=False),flush=True)
    return 0 if len(terminal)==len(jobs) else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('queue','output','driver','svr4','svr7','ref-scenario','ref-time-scenario'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--workers',type=int,choices=(1,2,3),default=3)
    args=parser.parse_args()
    raise SystemExit(main(args))
