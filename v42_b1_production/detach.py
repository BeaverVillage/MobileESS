"""TaskScheduler and visible monitor port of accepted V39L detach semantics."""
import argparse
import subprocess
import time
import psutil
from .common import *


def powershell(script):
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
    if p.returncode: raise RuntimeError(p.stderr or p.stdout)
    return p.stdout


def launch(root):
    root=Path(root).resolve(); freeze=read(root/'B1_PRODUCTION_FREEZE_MANIFEST.json')
    Config(**read(root/'B1_CAMPAIGN_CONFIG.json'))
    verify_freeze(freeze,read(root/'B1_CAMPAIGN_CONFIG.json'))
    if Path(freeze['worktree'])!=ROOT or freeze['mode']!='B1_PRODUCTION': raise PermissionError('LAUNCH_IDENTITY')
    task=freeze['task_name']
    if not task.startswith('MobileESS_V42_B1_May_Production_B1_202505_'): raise PermissionError('TASK_SCOPE')
    # Never overwrite another registered task. Relaunch uses the explicit receipt.
    existing=powershell(f"@(Get-ScheduledTask -TaskName '{task}' -ErrorAction SilentlyContinue).Count").strip()
    if existing!='0': raise PermissionError('DEDICATED_TASK_ALREADY_EXISTS')
    command=root/'campaign.cmd'
    command.write_text('@echo off\r\ncd /d "'+str(ROOT)+'"\r\n"'+freeze['Python']+'" -m v42_b1_production run --root "'+str(root)+'" 1>>"'+str(root/'production.stdout.log')+'" 2>>"'+str(root/'production.stderr.log')+'"\r\nexit /b %errorlevel%\r\n',encoding='ascii')
    # Explicitly call the audited historical registration/terminating-shell code.
    import sys
    sys.path.insert(0,str(CODE))
    from dayahead.v39l.infrastructure import register_one_shot_task,run_task_from_terminating_shell
    receipt=register_one_shot_task(task,command)
    settings=powershell("$s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1); "
        f"$t=Get-ScheduledTask -TaskName '{task}'; $trigger=New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name); "
        f"Set-ScheduledTask -TaskName '{task}' -Settings $s -Trigger (@($t.Triggers)+@($trigger)) | Out-Null; "
        f"Export-ScheduledTask -TaskName '{task}'")
    (root/'TASK_DEFINITION.xml').write_text(settings,encoding='utf-8')
    receipt.update(run_id=freeze['run_id'],Git_SHA=freeze['Git_SHA'],Python=freeze['Python'],worktree=str(ROOT),
                   configuration=record(root/'B1_CAMPAIGN_CONFIG.json'),command=record(command),
                   machine_restart_resume='AtLogOn current user; StartWhenAvailable; OS releases coordinator lock',
                   infrastructure_restart='999 retries at 1 minute; scientific FAIL is terminal',statements=STATEMENTS)
    atomic(root/'B1_TASK_RECEIPT.json',receipt)
    initiation=run_task_from_terminating_shell(task,root/'INITIATING_SHELL.json')
    receipt['initiating_shell']=initiation; atomic(root/'B1_TASK_RECEIPT.json',receipt)
    monitor=ROOT/'tools/v42/monitor_b1_may.ps1'
    # Start-Process Normal is the explicitly requested visible standalone window.
    script=f"$p=Start-Process powershell.exe -WindowStyle Normal -PassThru -ArgumentList @('-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-File','{monitor}','-Root','{root}'); $p.Id"
    pid=int(powershell(script).strip())
    atomic(root/'B1_MONITOR_RECEIPT.json',dict(run_id=freeze['run_id'],PID=pid,creation_time=psutil.Process(pid).create_time(),
                command=psutil.Process(pid).cmdline(),title='Mobile ESS V42 May B1 Production Monitor',
                readonly=True,WindowStyle='Normal',campaign_owner=False,statements=STATEMENTS))
    time.sleep(7)
    heartbeat=read(root/'B1_HEARTBEAT.json'); before=heartbeat.get('timestamp_UTC')
    time.sleep(2)
    heartbeat=read(root/'B1_HEARTBEAT.json')
    from .coordinator import same_process
    if before==heartbeat.get('timestamp_UTC') or not same_process(heartbeat.get('process',{})) or not psutil.pid_exists(pid):
        raise RuntimeError('DETACHED_HEARTBEAT_OR_PROCESS_VERIFICATION_FAILED')
    probe=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(monitor),'-Root',str(root),'-Once','-Json'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
    if probe.returncode: raise RuntimeError('MONITOR_READ_PROBE_FAILED:'+probe.stderr)
    frame=json.loads(probe.stdout)
    if frame['Liveness']['Orchestrator']!='ALIVE' or frame['Liveness']['State']!='RUNNING': raise RuntimeError('MONITOR_LIVENESS_FAILED')
    receipt.update(state=heartbeat['state'],campaign_process=heartbeat['process'],heartbeat_advancing=True,
                   task_verified=powershell(f"(Get-ScheduledTask -TaskName '{task}').State").strip(),
                   independent_of_Codex=True,verified_UTC=now())
    atomic(root/'B1_TASK_RECEIPT.json',receipt)
    mr=read(root/'B1_MONITOR_RECEIPT.json'); mr.update(read_status_verified=True,liveness=frame['Liveness'],independent_of_Codex=True)
    atomic(root/'B1_MONITOR_RECEIPT.json',mr)
    print(json.dumps(dict(root=str(root),run_id=freeze['run_id'],task=task,state=heartbeat['state'],campaign_PID=heartbeat['process']['PID'],monitor_PID=pid),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--root',required=True); launch(p.parse_args().root)
