"""Dispatch the gated campaign to the proven V39L Task Scheduler launcher."""
from pathlib import Path
import sys,subprocess,time,shutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40b.common import *
from dayahead.v40b.supervision import launch_gate,inventory
from dayahead.v39l.infrastructure import register_one_shot_task,run_task_from_terminating_shell,process_inventory

def main():
    method,execution=launch_gate();old=process_inventory();live=inventory()
    if old['orchestrators'] or old['workers'] or live['orchestrators'] or live['workers']:raise RuntimeError('PRELAUNCH_PROCESS_CONFLICT')
    receipt=ROOT/'V40B_DETACHED_LAUNCH_RECEIPT.json'
    if receipt.exists():raise RuntimeError('ALREADY_LAUNCHED_NO_DUPLICATE_DISPATCH')
    git_path=shutil.which('git')
    if not git_path:raise RuntimeError('GIT_EXECUTABLE_MISSING_BEFORE_DETACH')
    git_directory=Path(git_path).resolve().parent
    task='MobileESS_V40A_May_'+time.strftime('%Y%m%d_%H%M%S');cmd=ROOT/'V40A_SCHEDULED_MAY.cmd';log=ROOT/'ORCHESTRATOR.log'
    monitor_script=ROOT/'V40A_OPEN_MONITOR.ps1'
    monitor_path=REPO/'dayahead/tools/monitor_v40a_may_campaign.ps1'
    monitor_script.write_text(
       "$m=Start-Process -FilePath powershell.exe -ArgumentList @('-NoProfile','-NoExit','-ExecutionPolicy','Bypass','-File',"+
       f"'{monitor_path}') -WindowStyle Normal -PassThru\n"+
       f"@{{pid=$m.Id;started_at_utc=[DateTime]::UtcNow.ToString('o');launcher_pid=$PID;detached_parent='Task Scheduler'}} | ConvertTo-Json | Set-Content -LiteralPath '{ROOT/'V40B_MONITOR_LAUNCH.json'}' -Encoding UTF8\n",encoding='utf-8')
    cmd.write_text('@echo off\n'+f'cd /d "{REPO}"\n'+
       f'set "PATH={git_directory};%PATH%"\n'+
       'set "OMP_NUM_THREADS=1"\nset "OPENBLAS_NUM_THREADS=1"\nset "MKL_NUM_THREADS=1"\n'+
       f'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{monitor_script}"\n'+
       f'"{sys.executable}" -u "{REPO / "dayahead/tools/run_v40b_campaign.py"}" --orchestrate >> "{log}" 2>&1\nexit /b %ERRORLEVEL%\n',encoding='utf-8')
    registration=register_one_shot_task(task,cmd)
    client=run_task_from_terminating_shell(task,ROOT/'V40B_LAUNCH_CLIENT.json')
    # Disable the timer trigger after the explicit launch; running task persists.
    disabled=subprocess.run(['schtasks.exe','/Change','/TN',task,'/DISABLE'],text=True,capture_output=True,encoding='utf-8',errors='replace',check=True)
    write(receipt,{'status':'DISPATCHED','task':registration,'client':client,'method_SHA':method['method_SHA'],
       'execution_SHA':execution['execution_SHA'],'launcher_cmd_SHA':sha(cmd),'monitor_launcher_SHA':sha(monitor_script),'automatic_second_trigger_disabled':True,
       'disable_output':disabled.stdout.strip(),'parent_lifetime':'WINDOWS_TASK_SCHEDULER; initiating shell exited',
       'git_executable':git_path,'git_executable_SHA':sha(Path(git_path)),'dispatched_at_utc':now_utc()})
    print(task,flush=True)

if __name__=='__main__':main()
