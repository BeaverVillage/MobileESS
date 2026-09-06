"""Infrastructure wrapper: explicitly provision Git in the WMI child PATH.

Keep the scientific worker, freeze gates, lock, supervisor and stop/resume
implementation unchanged. WMI inherits a service environment, not the launching
shell's PATH, so the child receives only the resolved Git executable path.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from dayahead.paper_analysis.storage import atomic, write_json
from dayahead.v41 import detached
from dayahead.v41.data import RUNTIME
from dayahead.v41.preflight import ROOT, record
from dayahead.v41.reserve import require


def git_executable():
    candidate=shutil.which('git')
    require(candidate is not None, 'LAUNCHER_GIT_NOT_FOUND')
    path=Path(candidate).resolve()
    require(path.is_file(), 'LAUNCHER_GIT_NOT_FILE')
    return str(path)


def provision_git(path):
    executable=Path(path)
    require(executable.is_absolute() and executable.is_file(), 'CHILD_GIT_NOT_ABSOLUTE_FILE')
    os.environ['PATH']=str(executable.parent)+os.pathsep+os.environ.get('PATH','')
    resolved=Path(shutil.which('git') or '').resolve()
    require(resolved==executable.resolve(), 'CHILD_GIT_RESOLUTION_MISMATCH')
    return str(resolved)


def worker_arguments(kind,token,git):
    require(kind in ('smoke','campaign'), 'INVALID_WORKER_KIND')
    return [sys.executable,'-u','-m','dayahead.tools.v41_detached_launcher','worker',
            '--kind',kind,'--token',token,'--git-executable',git]


def spawn(kind,token):
    args=worker_arguments(kind,token,git_executable())
    def quoted(value): return "'"+value.replace("'","''")+"'"
    script=("$ErrorActionPreference='Stop'\n"
        "$v41Startup=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]0;CreateFlags=[uint32]8}\n"
        "$v41Created=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine="+
        quoted(subprocess.list2cmdline(args))+";CurrentDirectory="+quoted(str(ROOT))+";ProcessStartupInformation=$v41Startup}\n"
        "$v41Created | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress\n")
    helper=RUNTIME/'launcher_helpers'/f'{token}.ps1'
    with atomic(helper) as stream: stream.write(script.encode('utf-8-sig'))
    created=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(helper)],
        capture_output=True,text=True,check=True)
    response=json.loads(created.stdout)
    require(response['ReturnValue']==0,'CIM_PROCESS_CREATE_FAILED:'+str(response))
    pid=int(response['ProcessId']);time.sleep(.25)
    require(detached.psutil.pid_exists(pid),'DETACHED_CHILD_START_FAILED')
    log=ROOT/'logs/v41_may_campaign'/(f'detached_smoke_{token}.log' if kind=='smoke' else 'campaign_supervisor.log')
    return dict(pid=pid,launcher_pid=os.getpid(),started_at=detached.now(),token=token,log_path=str(log),
        mechanism='Win32_Process.Create; DETACHED_PROCESS; explicit Git PATH bootstrap; worker-owned stdio',
        launch_command=args,environment_wrapper=record(__file__),git_executable=record(args[-1]))


def worker(kind,token,git):
    resolved=provision_git(git)
    # Prove the same lookup used by all inherited workers succeeds without
    # importing Actual or creating a scientific optimization model.
    sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    root=RUNTIME/'detached_smoke'/token if kind=='smoke' else RUNTIME
    write_json(root/'DETACHED_ENVIRONMENT_PROOF.json',dict(status='PASS',pid=os.getpid(),
        git_executable=record(resolved),scientific_commit=sha,wrapper=record(__file__),
        scope='Process-local PATH only; no system/user environment mutation'))
    detached.worker(kind,token)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['launch','resume','smoke-launch','worker'])
    parser.add_argument('--kind',choices=['smoke','campaign'])
    parser.add_argument('--token');parser.add_argument('--git-executable')
    args=parser.parse_args()
    if args.operation=='worker':
        worker(args.kind,args.token,args.git_executable);return
    # Only replace process creation; retain all existing launch/resume gates.
    detached.spawn=spawn
    if args.operation=='resume':
        from dayahead.v41 import campaign
        sys.argv=[sys.argv[0],'--resume'];campaign.main()
    elif args.operation=='smoke-launch': detached.smoke_launch()
    else: detached.launch()


if __name__=='__main__': main()
