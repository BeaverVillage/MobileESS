"""One guarded handoff after healthy predecessor Workers naturally finish."""
from pathlib import Path
import sys,time,subprocess,json,datetime
import psutil
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tools'))
from v42_pr134_b1.common import read,record,atomic,digest,now
from v42_common_campaign.authority import singleton,source_files
from prepare_svr11_epoch10 import ROOT,OLD,Q,origin_workers,freeze_slots,release_and_reuse,validate_proof

def update_windows_tasks():
    # Resolve exactly the two existing registrations; preserve principal,
    # settings and five-minute/logon triggers, changing only their actions.
    code=f'''$items=foreach($name in @('MobileESS_V42_May_B2_B3_Autonomous_Supervisor','MobileESS_V42_May_B2_B3_Autonomous_Monitor')) {{
      $task=Get-ScheduledTask -TaskName $name -ErrorAction Stop
      if($task.Triggers.Count -ne 2 -or !$task.Settings.Enabled) {{ throw 'EXISTING_WINDOWS_SCHEDULE_DRIFT' }}
      $before=$task.Actions.Arguments
      if($before -notlike '*svr11_monitor_ui.py safeguard {OLD}*') {{ throw 'UNEXPECTED_OLD_WINDOWS_ROOT' }}
      $args='-B -X utf8 {SOURCE}\\tools\\svr11_monitor_ui.py safeguard {ROOT}'
      if($name.EndsWith('_Monitor')) {{$args+=' --monitor-only'}}
      $action=New-ScheduledTaskAction -Execute 'C:\\Users\\kjw39\\AppData\\Local\\Programs\\Python\\Python311\\pythonw.exe' -Argument $args -WorkingDirectory '{SOURCE}'
      Set-ScheduledTask -TaskName $name -Action $action -ErrorAction Stop | Out-Null
      $updated=Get-ScheduledTask -TaskName $name -ErrorAction Stop
      if($updated.Actions.Arguments -ne $args -or $updated.Actions.WorkingDirectory -ne '{SOURCE}' -or $updated.Triggers.Count -ne 2) {{throw 'WINDOWS_SCHEDULE_READBACK_FAILED'}}
      [pscustomobject]@{{TaskName=$name;before=$before;Arguments=$updated.Actions.Arguments;WorkingDirectory=$updated.Actions.WorkingDirectory;Enabled=$updated.Settings.Enabled;TriggerCount=$updated.Triggers.Count}}
    }}; $items | ConvertTo-Json -Depth 3'''
    output=subprocess.check_output(['powershell','-NoProfile','-Command',code],encoding='utf8')
    atomic(ROOT/'WINDOWS_SCHEDULE_REGISTRATION.json',dict(PASS=True,registrations=json.loads(output),
        duplicate_tasks_created=0,observed_execution_pending=True,UTC=now()))

def run():
    with singleton(ROOT/'TRANSFER.lock'):
        intent=read(ROOT/'TRANSFER_INTENT.json');assert intent['execution_SHA']==digest(source_files())
        for r in intent['tools']:assert record(r['path'])==r
        validate_proof();sup=read(OLD/Q)['process']
        while True:
            assert digest(source_files())==intent['execution_SHA']
            p=psutil.Process(sup['PID']);assert p.create_time()==sup['create_time'] and p.cmdline()==sup['command']
            assert p.status()==psutil.STATUS_STOPPED,'PREDECESSOR_DISPATCH_MUST_STAY_QUIESCED'
            peers=origin_workers()
            atomic(ROOT/'TRANSFER_PROGRESS.json',dict(status='WAITING_HEALTHY_PREDECESSOR_DRAIN' if peers else 'FREEZING_REUSABLE_MODELS',
                source_SHA=intent['execution_SHA'],workers=peers,healthy_workers_terminated=0,UTC=now()))
            if not peers:break
            time.sleep(30)
        freeze_slots();release_and_reuse()
        script=SOURCE/'tools/svr11_monitor_ui.py'
        subprocess.run([sys.executable,'-B','-X','utf8',str(script),'release',str(ROOT)],cwd=SOURCE,check=True)
        update_windows_tasks()
        subprocess.run([sys.executable,'-B','-X','utf8',str(script),'safeguard',str(ROOT)],cwd=SOURCE,check=True)
        atomic(ROOT/'TRANSFER_COMPLETE.json',dict(PASS=True,source_SHA=intent['execution_SHA'],root=str(ROOT),
            predecessor_original_results_preserved=True,healthy_workers_terminated=0,
            qualified_date_reuse=True,Windows_registration=record(ROOT/'WINDOWS_SCHEDULE_REGISTRATION.json'),
            hourly_automation_final_binding_pending=True,UTC=now()))
        print('IMMUTABLE_SUCCESSOR_ACTIVATED',str(ROOT),flush=True)

if __name__=='__main__':
    try:run()
    except Exception as error:
        import traceback
        atomic(ROOT/'TRANSFER_ERROR.json',dict(PASS=False,error=repr(error),traceback=traceback.format_exc(),UTC=now()))
        raise
