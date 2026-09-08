"""Windows process detachment, smoke worker, and bounded launch verification."""
import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import psutil
from dayahead.paper_analysis.storage import read, write_json
from .preflight import ROOT, OUT, record
from .data import RUNTIME
from .reserve import require


def now(): return datetime.now(timezone.utc).isoformat()


def job_membership():
    result=ctypes.c_int()
    kernel=ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype=ctypes.c_void_p
    kernel.IsProcessInJob.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_int)]
    require(kernel.IsProcessInJob(kernel.GetCurrentProcess(),None,ctypes.byref(result)),'WINDOWS_JOB_QUERY_FAILED')
    return bool(result.value)


def worker(kind, token):
    require(os.name=='nt','WINDOWS_DETACHMENT_REQUIRED')
    root=RUNTIME/'detached_smoke'/token if kind=='smoke' else RUNTIME
    root.mkdir(parents=True,exist_ok=True)
    log=ROOT/'logs/v41_may_campaign'/(f'detached_smoke_{token}.log' if kind=='smoke' else 'campaign_supervisor.log')
    # CIM creation is outside the Codex process tree and has no inherited stdio.
    # Open all streams within the independent worker.
    sys.stdin=open(os.devnull,'r'); sys.stdout=open(log,'a',encoding='utf-8',buffering=1); sys.stderr=sys.stdout
    proof=dict(pid=os.getpid(),parent_pid=os.getppid(),started_at=now(),token=token,
               in_Windows_job=job_membership(),command_line=psutil.Process().cmdline())
    write_json(root/'DETACHED_WORKER_PROOF.json',proof)
    require(not proof['in_Windows_job'],'DETACHED_WORKER_STILL_IN_PARENT_JOB')
    if kind=='smoke':
        while not (root/'STOP.json').exists():
            write_json(root/'heartbeat.json',dict(**proof,timestamp=now(),state='RUNNING'))
            time.sleep(1)
        write_json(root/'STOPPED.json',dict(pid=os.getpid(),stopped_at=now(),clean_shutdown=True)); return
    from .campaign import main
    sys.argv=[sys.argv[0],'--mode','both']; main()


def spawn(kind, token):
    log_root=ROOT/'logs/v41_may_campaign'; log_root.mkdir(parents=True,exist_ok=True)
    log=log_root/(f'detached_smoke_{token}.log' if kind=='smoke' else 'campaign_supervisor.log')
    args=[sys.executable,'-u','-m','dayahead.v41.detached','worker','--kind',kind,'--token',token]
    def quoted(text): return "'"+text.replace("'","''")+"'"
    script=("$ErrorActionPreference='Stop'\n"
        "$v41Startup=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]0;CreateFlags=[uint32]8}\n"
        "$v41Created=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine="+
        quoted(subprocess.list2cmdline(args))+";CurrentDirectory="+quoted(str(ROOT))+";ProcessStartupInformation=$v41Startup}\n"
        "$v41Created | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress\n")
    helper=RUNTIME/'launcher_helpers'/f'{token}.ps1'
    from dayahead.paper_analysis.storage import atomic
    with atomic(helper) as f: f.write(script.encode('utf-8-sig'))
    created=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(helper)],
        capture_output=True,text=True,check=True)
    response=json.loads(created.stdout); require(response['ReturnValue']==0,'CIM_PROCESS_CREATE_FAILED:'+str(response))
    pid=int(response['ProcessId']); time.sleep(.25); require(psutil.pid_exists(pid),'DETACHED_CHILD_START_FAILED:'+str(log))
    return dict(pid=pid,launcher_pid=os.getpid(),started_at=now(),token=token,log_path=str(log),
        mechanism='Win32_Process.Create through independent WMI provider; DETACHED_PROCESS; worker-owned stdio',
        launch_command=args)


def smoke_launch():
    token=uuid.uuid4().hex[:12]; root=RUNTIME/'detached_smoke'/token
    launch=spawn('smoke',token); write_json(root/'LAUNCH.json',launch)
    write_json(RUNTIME/'DETACHED_SMOKE_CURRENT.json',dict(root=str(root),launch=launch))
    print(json.dumps(launch),flush=True)


def smoke_verify():
    active=read(RUNTIME/'DETACHED_SMOKE_CURRENT.json'); root=Path(active['root']); launch=active['launch']
    require(not psutil.pid_exists(launch['launcher_pid']),'SMOKE_PARENT_LAUNCHER_HAS_NOT_EXITED')
    process=psutil.Process(launch['pid']); require(process.is_running(),'SMOKE_CHILD_DEAD')
    first=read(root/'heartbeat.json'); time.sleep(2.2); second=read(root/'heartbeat.json')
    require(first['timestamp']!=second['timestamp'] and not second['in_Windows_job'],'SMOKE_DETACHMENT_OR_HEARTBEAT_FAILED')
    write_json(root/'STOP.json',dict(requested_at=now()))
    process.wait(timeout=15)
    require(read(root/'STOPPED.json')['clean_shutdown'],'SMOKE_GRACEFUL_STOP_FAILED')
    proof=dict(status='PASS',parent_launcher_exited=True,child_survived=True,heartbeat_changed=True,
        fresh_shell_readback=True,Windows_parent_job_membership=False,clean_stop=True,
        first=first,second=second,launch=launch)
    write_json(OUT/'V41_DETACHED_PROCESS_SMOKE_TEST.json',proof)
    print('DETACHED_SMOKE_PASS',launch['pid'],flush=True)


def launch():
    from .campaign import campaign_lock,frozen_identity
    with campaign_lock():
        frozen=frozen_identity()
        require(read(OUT/'V41_DETACHED_PROCESS_SMOKE_TEST.json')['status']=='PASS','DETACHMENT_SMOKE_NOT_PASS')
        require(not (RUNTIME/'STOP_REQUESTED.json').exists(),'STOP_REQUEST_STILL_PRESENT')
    token=uuid.uuid4().hex
    manifest=dict(scientific_commit=frozen['scientific_commit'],interface_freeze=frozen['freeze'],
        mode='both',target_days=31,policies=['B0','B1','B2','B3'],policy_days=124,
        source=frozen['science'],persistence='V41_COMPLETE_SCIENTIFIC_PERSISTENCE_V1',
        concurrency=dict(day_workers=4,active_solver_workers_per_day=1,Gurobi_threads=4),
        launcher=record(__file__),timestamp=now())
    write_json(OUT/'V41_MAY_CAMPAIGN_LAUNCH_MANIFEST.json',manifest)
    result=spawn('campaign',token); result.update(scientific_commit=frozen['scientific_commit'],manifest=record(OUT/'V41_MAY_CAMPAIGN_LAUNCH_MANIFEST.json'))
    write_json(RUNTIME/'campaign_launch_receipt.json',result)
    write_json(OUT/'V41_MAY_CAMPAIGN_LAUNCH_RECEIPT.json',result)
    print(json.dumps(result),flush=True)


def verify_launch():
    launch=read(RUNTIME/'campaign_launch_receipt.json'); process=psutil.Process(launch['pid'])
    require(not psutil.pid_exists(launch['launcher_pid']),'CAMPAIGN_LAUNCHER_STILL_RUNNING')
    first=read(RUNTIME/'campaign_heartbeat.json'); time.sleep(6); second=read(RUNTIME/'campaign_heartbeat.json')
    proof=read(RUNTIME/'DETACHED_WORKER_PROOF.json')
    require(process.is_running() and not proof['in_Windows_job'],'CAMPAIGN_DETACHMENT_FAILED')
    require(first['timestamp']!=second['timestamp'] and second['scientific_commit']==launch['scientific_commit'],'CAMPAIGN_HEARTBEAT_OR_COMMIT_FAILED')
    require(second['status']=='RUNNING' and second['current'],'FIRST_QUEUE_UNIT_NOT_VISIBLE')
    launch.update(status='RUNNING_VERIFIED',detached_from_Codex=True,heartbeat_first=first,heartbeat_second=second,
        process_proof=proof,verified_at=now(),parent_launcher_exited=True)
    write_json(RUNTIME/'campaign_launch_receipt.json',launch); write_json(OUT/'V41_MAY_CAMPAIGN_LAUNCH_RECEIPT.json',launch)
    print('CAMPAIGN_DETACHED_VERIFIED',process.pid,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('operation',choices=['worker','smoke-launch','smoke-verify','launch','verify-launch'])
    p.add_argument('--kind',choices=['smoke','campaign']); p.add_argument('--token'); a=p.parse_args()
    if a.operation=='worker':
        worker(a.kind,a.token)
    else: {'smoke-launch':smoke_launch,'smoke-verify':smoke_verify,'launch':launch,'verify-launch':verify_launch}[a.operation]()
