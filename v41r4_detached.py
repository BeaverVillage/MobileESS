"""WMI-owned process, no inherited console, handles or Codex Job Object."""
from fast_prepare import *
from v41r4_electrical import MAY_RUN,MAY_OUT
from v41r4_io import install
install()
import os,sys,time,subprocess,uuid,psutil,shutil
from dayahead.paper_analysis.storage import write_json
from dayahead.v41.detached import job_membership

LOGS=ROOT/'logs/v41r4_may'

def worker(kind,token):
    folder=MAY_RUN/'detached_smoke'/token if kind=='smoke' else MAY_RUN
    folder.mkdir(parents=True,exist_ok=True);LOGS.mkdir(parents=True,exist_ok=True)
    log=LOGS/(f'detached_smoke_{token}.log' if kind=='smoke' else 'campaign_supervisor.log')
    sys.stdin=open(os.devnull);sys.stdout=open(log,'a',encoding='utf-8',buffering=1);sys.stderr=sys.stdout
    environment=read(MAY_RUN/'launcher_helpers/RUNTIME_EXECUTABLES.json')
    git=Path(environment['git_executable']);assert git.is_file()
    os.environ['PATH']=str(git.parent)+os.pathsep+os.environ.get('PATH','')
    assert shutil.which('git') and subprocess.check_output(['git','--version'],text=True).startswith('git version')
    proof=dict(pid=os.getpid(),parent_pid=os.getppid(),started_at=time.time(),in_Windows_job=job_membership(),
        command_line=psutil.Process().cmdline(),stdio_owned_by_worker=True,git_executable=str(git))
    write_json(folder/'DETACHED_WORKER_PROOF.json',proof)
    assert not proof['in_Windows_job'],'NOT_DETACHED_FROM_WINDOWS_JOB'
    if kind=='smoke':
        while not (folder/'STOP.json').exists():
            write_json(folder/'heartbeat.json',dict(**proof,at=time.time()));time.sleep(1)
        write_json(folder/'STOPPED.json',dict(clean_shutdown=True));return
    if kind=='campaign_v2':
        from v41r4_campaign_v2 import main
    else:
        from v41r4_campaign import main
    main()

def spawn(kind):
    token=uuid.uuid4().hex[:12];LOGS.mkdir(parents=True,exist_ok=True)
    git=shutil.which('git');assert git,'LAUNCHER_GIT_UNAVAILABLE'
    write_json(MAY_RUN/'launcher_helpers/RUNTIME_EXECUTABLES.json',dict(git_executable=git,python_executable=sys.executable))
    args=[sys.executable,'-u',str(ROOT/'v41r4_detached.py'),'worker',kind,token]
    quote=lambda s:"'"+s.replace("'","''")+"'"
    script=("$ErrorActionPreference='Stop'\n"
        "$r4Startup=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]0;CreateFlags=[uint32]8}\n"
        "$r4Created=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine="+quote(subprocess.list2cmdline(args))+";CurrentDirectory="+quote(str(ROOT))+";ProcessStartupInformation=$r4Startup}\n"
        "$r4Created | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress\n")
    helper=MAY_RUN/'launcher_helpers'/f'{token}.ps1';helper.parent.mkdir(parents=True,exist_ok=True);helper.write_text(script,encoding='utf-8-sig')
    result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(helper)],capture_output=True,text=True,check=True)
    r=json.loads(result.stdout);assert r['ReturnValue']==0,r
    folder=MAY_RUN/'detached_smoke'/token if kind=='smoke' else MAY_RUN
    launch=dict(pid=r['ProcessId'],launcher_pid=os.getpid(),token=token,folder=str(folder),mechanism='Win32_Process.Create; DETACHED_PROCESS; WMI parent',
        lifetime='Independent of Codex and launcher; Windows session remains running')
    write_json(MAY_RUN/('DETACHED_SMOKE_CURRENT.json' if kind=='smoke' else 'campaign_launch_receipt.json'),launch)
    print(json.dumps(launch),flush=True)

def verify(kind):
    p=MAY_RUN/('DETACHED_SMOKE_CURRENT.json' if kind=='smoke' else 'campaign_launch_receipt.json')
    launch=read(p);assert not psutil.pid_exists(launch['launcher_pid']),'LAUNCHER_MUST_EXIT_FIRST'
    folder=Path(launch['folder']);proof=read(folder/'DETACHED_WORKER_PROOF.json')
    assert not proof['in_Windows_job'] and psutil.pid_exists(launch['pid'])
    heart=folder/'heartbeat.json' if kind=='smoke' else MAY_RUN/'campaign_progress.json'
    first=read(heart);time.sleep(4);second=read(heart);assert first!=second,'HEARTBEAT_NOT_ADVANCING'
    proof.update(status='PASS',parent_launcher_exited=True,child_survived=True,heartbeat_advanced=True,Codex_independent=True,
        first_heartbeat=first,second_heartbeat=second)
    write_json(MAY_OUT/('V41R4_DETACHED_SMOKE_TEST.json' if kind=='smoke' else 'V41R4_DETACHED_EXECUTION_VERIFICATION.json'),proof)
    if kind=='smoke':
        write_json(folder/'STOP.json',dict(at=time.time()));psutil.Process(launch['pid']).wait(timeout=15)
        assert read(folder/'STOPPED.json')['clean_shutdown']
    print('DETACHED_VERIFIED',kind,launch['pid'],flush=True)

if __name__=='__main__':
    op=sys.argv[1]
    if op=='worker':worker(sys.argv[2],sys.argv[3])
    elif op=='spawn':spawn(sys.argv[2])
    elif op=='verify':verify(sys.argv[2])
