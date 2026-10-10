"""Seal handoff only after real 37-date evidence and live recovery bindings."""
from pathlib import Path
import sys,json,sqlite3,datetime,urllib.request,subprocess
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,now
from v42_svr11.authority import verify
from v42_svr11.processes import live,workers
from verify_svr11_handoff37 import run

def finish(root):
    root=Path(root).resolve();m=verify(root/'CAMPAIGN_MANIFEST.json');h=run(root)
    assert h['PASS'] and h['verified_PASS']==37 and h['final_all_receipt_bytes_reverified'], 'HANDOFF_37_ACTUAL_PASS_REQUIRED'
    supervisor=read(root/'SUPERVISOR_PROCESS.json');assert live(supervisor)
    peers=workers(root,m['execution_SHA'])
    with urllib.request.urlopen('http://127.0.0.1:8796/api/state',timeout=10) as response:s=json.load(response)
    assert s['source_SHA']==m['execution_SHA'] and Path(s['root']).resolve()==root
    assert s['status']=='RUNNING' and 0<len(peers)<=m['worker_counts'][s['policy']]
    assert {p['PID'] for p in peers}=={p['PID'] for p in s['workers']}
    monitor=read(root/'MONITOR_PROCESS.json');assert live(monitor)
    from svr11_monitor_ui import verify_ui
    verify_ui(root)
    c=sqlite3.connect('file:C:/Users/kjw39/.codex/sqlite/codex-dev.db?mode=ro',uri=True);c.row_factory=sqlite3.Row
    a=dict(c.execute('select id,status,rrule,next_run_at,last_run_at,target_thread_id,prompt from automations where id=?',
        ('v42-may-b2-b3-autonomous-recovery',)).fetchone());c.close()
    assert a['status']=='ACTIVE' and a['rrule']=='FREQ=HOURLY;INTERVAL=1'
    assert str(root) in a['prompt'] and m['execution_SHA'] in a['prompt'] and 'B0→B2→B1→B3' in a['prompt']
    assert a['next_run_at'] is not None
    tz=datetime.timezone(datetime.timedelta(hours=9))
    a['next_run_KST']=datetime.datetime.fromtimestamp(a['next_run_at']/1000,tz).isoformat()
    a['next_execution_is_observed_schedule_not_claimed_completed']=True
    script="""$items=foreach($name in @('MobileESS_V42_May_B2_B3_Autonomous_Supervisor','MobileESS_V42_May_B2_B3_Autonomous_Monitor')) {
      $task=Get-ScheduledTask -TaskName $name -ErrorAction Stop
      $info=Get-ScheduledTaskInfo -TaskName $name -ErrorAction Stop
      [pscustomobject]@{TaskName=$name;Enabled=$task.Settings.Enabled;State=[string]$task.State;Arguments=$task.Actions.Arguments;WorkingDirectory=$task.Actions.WorkingDirectory;LastRun=$info.LastRunTime.ToString('o');NextRun=$info.NextRunTime.ToString('o');LastResult=$info.LastTaskResult;TriggerCount=$task.Triggers.Count}
    }; $items | ConvertTo-Json -Depth 3"""
    task_data=json.loads(subprocess.check_output(['powershell','-NoProfile','-Command',script],encoding='utf-8'))
    clock=datetime.datetime.now(tz)
    for task in task_data:
        expected=f'-B -X utf8 {SOURCE}\\tools\\svr11_monitor_ui.py safeguard {root}'
        if task['TaskName'].endswith('_Monitor'):expected+=' --monitor-only'
        assert task['Enabled'] and task['Arguments']==expected and Path(task['WorkingDirectory']).resolve()==SOURCE
        assert task['LastResult']==0 and task['TriggerCount']==2
        assert datetime.timedelta(0)<=clock-datetime.datetime.fromisoformat(task['LastRun'])<datetime.timedelta(minutes=15)
        assert datetime.datetime.fromisoformat(task['NextRun'])>clock
    atomic(root/'WINDOWS_SCHEDULE_OBSERVED_EXECUTION.json',task_data)
    receipt=dict(schema='SVR11_VERIFIED_37_ACTIVE_CAMPAIGN_HANDOFF_V1',PASS=True,
        source_SHA=m['execution_SHA'],equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],root=str(root),
        handoff37=record(root/'HANDOFF_37_VALIDATION.json'),supervisor=supervisor,workers=peers,monitor=monitor,
        monitor_URL='http://127.0.0.1:8796',monitor_HTTP=200,counts=s['counts'],policy=s['policy'],
        hourly=a,Windows_tasks=task_data,campaign_processes_terminated=0,
        monthly_campaign_complete=False,chat_handoff_only=True,UTC=now())
    atomic(root/'HANDOFF_RECEIPT.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('hourly','workers','Windows_tasks')},ensure_ascii=False))
    print('HOURLY_NEXT_KST',a['next_run_KST'])
    return receipt

if __name__=='__main__':finish(sys.argv[1])
