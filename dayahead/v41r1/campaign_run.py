"""Detached fixed-four-day supervisor, retaining validated work and original gates."""
import argparse
import json
import shutil
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import psutil
from dayahead.paper_analysis.storage import read,write_json,atomic
from dayahead.v41.preflight import ROOT,OUT,record
from dayahead.v41.data import RUNTIME
from dayahead.v41.reserve import require
from dayahead.v41 import campaign as native
from .campaign_prepare import verify_release,verify_launch_authority

original_verify=native.verify_receipt


def verify_phase(path,frozen=None):
    receipt=read(path)
    if frozen and (receipt['scientific_commit']!=frozen['scientific_commit'] or receipt['science']!=frozen['science']):
        from .migration_retention import validate
        validate(receipt,frozen['science'])
        return original_verify(path,None)
    return original_verify(path,frozen)


class Supervisor(native.Supervisor):
    def save(self):
        with self.lock:self.save_snapshot()

    def save_snapshot(self):
        super().save()
        host=psutil.virtual_memory();workers=[];seen=set()
        for row in self.state['units'].values():
            pid=row.get('worker_pid')
            if not pid or pid in seen:continue
            try:
                parent=psutil.Process(pid);processes=[parent]+parent.children(recursive=True)
                for process in processes:
                    if process.pid in seen:continue
                    seen.add(process.pid);m=process.memory_info()._asdict()
                    workers.append(dict(pid=process.pid,parent_pid=pid,day=row['day'],policy=row['policy'],
                        phase=row.get('phase'),RSS_bytes=m['rss'],private_bytes=m.get('private',m['vms']),
                        peak_RSS_bytes=m.get('peak_wset',m['rss'])))
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
        value=dict(at=time.time(),host_physical_RAM_bytes=host.total,host_available_RAM_bytes=host.available,
            host_used_RAM_bytes=host.total-host.available,workers=workers,swap=psutil.swap_memory()._asdict(),
            fixed_day_workers=4,threads_per_day=4,memory_cap='UNLIMITED',NodefileStart_GB=.5,
            supervisor_pid=os.getpid(),free_SSD_bytes=shutil.disk_usage(ROOT).free)
        write_json(RUNTIME/'campaign_memory.json',value)
        with (RUNTIME/'campaign_memory_history.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(value,separators=(',',':'))+'\n')

    def phase(self,row,phase):
        path=RUNTIME/row['day']/row['policy']/phase/(phase.upper()+'_RECEIPT.json')
        if row['policy']=='B0' and path.exists():
            verify_phase(path,self.frozen)
            with self.lock:
                row[phase+'_receipt']=record(path);row['retained_previously_complete']=True;self.save()
            return
        return super().phase(row,phase)


def adopt_completed_B0():
    from dayahead.v41.scientific_archive import copy_atomic,verify_manifest
    from .migration_retention import validate
    from dayahead.v41.execution import science
    source=RUNTIME/'pilot/2025-05-01/B0';target=RUNTIME/'2025-05-01/B0'
    for phase in ('dayahead','actual'):validate(read(source/phase/(phase.upper()+'_RECEIPT.json')),science())
    verify_manifest(source/'UNIT_SCIENTIFIC_MANIFEST.json')
    for path in sorted(source.rglob('*')):
        if path.is_file():copy_atomic(path,target/path.relative_to(source))
    copy_atomic(source.parent/'COMMON_INPUT_IDENTITY.json',target.parent/'COMMON_INPUT_IDENTITY.json')
    verify_manifest(target/'UNIT_SCIENTIFIC_MANIFEST.json')
    write_json(RUNTIME/'MAY01_B0_ADOPTION.json',dict(status='PASS',source=str(source),target=str(target),
        source_manifest=record(source/'UNIT_SCIENTIFIC_MANIFEST.json'),target_manifest=record(target/'UNIT_SCIENTIFIC_MANIFEST.json'),
        DayAhead_rerun=False,Actual_rerun=False,original_artifact_bytes_preserved=True,
        embedded_paths_continue_to_reference_preserved_originals=True))


def worker(token,git):
    from dayahead.tools.v41_detached_launcher import provision_git
    from dayahead.v41.detached import job_membership
    provision_git(git)
    log=ROOT/'logs/v41r1_migration/full_may_supervisor.log';log.parent.mkdir(parents=True,exist_ok=True)
    sys.stdin=open(os.devnull,'r');sys.stdout=log.open('a',encoding='utf-8',buffering=1);sys.stderr=sys.stdout
    proof=dict(pid=os.getpid(),parent_pid=os.getppid(),in_Windows_job=job_membership(),token=token,
        started_at=time.time(),command_line=psutil.Process().cmdline(),git_executable=git)
    write_json(RUNTIME/'DETACHED_FULL_MAY_PROOF.json',proof)
    require(not proof['in_Windows_job'],'CAMPAIGN_NOT_DETACHED_FROM_CODEX')
    verify_launch_authority();adopt_completed_B0()
    native.frozen_identity=verify_release;native.verify_receipt=verify_phase;native.Supervisor=Supervisor
    native.LOGS=ROOT/'logs/v41r1_migration/full_may'
    sys.argv=[sys.argv[0],'--mode','both'];native.main()


def launch():
    from dayahead.tools.v41_detached_launcher import git_executable
    with native.campaign_lock():
        release=verify_launch_authority()
        require(not (RUNTIME/'STOP_REQUESTED.json').exists(),'PREVIOUS_EXPLICIT_STOP_REQUEST')
        for p in psutil.process_iter(['cmdline']):
            cmd=p.info['cmdline'] or []
            require(not ('dayahead.v41r1.campaign_run' in cmd and 'worker' in cmd),'CAMPAIGN_ALREADY_RUNNING')
    token=uuid.uuid4().hex;args=[sys.executable,'-u','-m','dayahead.v41r1.campaign_run','worker',
        '--token',token,'--git',git_executable()]
    quote=lambda value:"'"+value.replace("'","''")+"'"
    script=("$ErrorActionPreference='Stop'\n"
        "$v41Startup=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]0;CreateFlags=[uint32]8}\n"
        "$v41Created=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine="+
        quote(subprocess.list2cmdline(args))+";CurrentDirectory="+quote(str(ROOT))+";ProcessStartupInformation=$v41Startup}\n"
        "$v41Created | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress\n")
    helper=RUNTIME/'launcher_helpers'/f'full_may_{token}.ps1'
    with atomic(helper) as stream:stream.write(script.encode('utf-8-sig'))
    created=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(helper)],capture_output=True,text=True,check=True)
    value=json.loads(created.stdout);require(value['ReturnValue']==0,'DETACHED_PROCESS_CREATION_FAILED')
    receipt=dict(pid=int(value['ProcessId']),launcher_pid=os.getpid(),token=token,at=time.time(),
        source_commit=release['scientific_commit'],command=args,helper=record(helper),
        expected_workers=4,threads_per_worker=4,mechanism='Independent WMI provider; DETACHED_PROCESS; worker-owned streams',
        log=str(ROOT/'logs/v41r1_migration/full_may_supervisor.log'))
    write_json(RUNTIME/'FULL_MAY_LAUNCH.json',receipt);print(receipt,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['launch','worker'])
    p.add_argument('--token');p.add_argument('--git');a=p.parse_args()
    launch() if a.mode=='launch' else worker(a.token,a.git)
