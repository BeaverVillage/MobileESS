"""Register only a new ordinary-user read-only maintenance monitor task."""
import argparse, subprocess, sys
from pathlib import Path
from xml.etree import ElementTree as ET
from v42_may_campaign.common import atomic,record,now,d_path,same_process,read
from v42_may_campaign.windows import task_definition,NS,powershell,exists,safe_name,run_task

NAME='MobileESS_V42_B1B2_P1_20261009_HourlyMaintenance_Monitor'


def install(campaign,storage):
    campaign=d_path(campaign);storage=d_path(storage);project=campaign.parents[2]
    storage.mkdir(parents=True,exist_ok=True);safe_name(NAME)
    python=Path(sys.executable).with_name('pythonw.exe')
    sid=powershell('[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value').strip()
    tree=task_definition(storage,'monitor',python=str(python),sid=sid)
    command=[ '-B','-X','utf8','-m','v42_may_maintenance.monitor','--campaign',str(campaign),
        '--storage',str(storage),'--port','8794']
    tree.find('.//{'+NS+'}Arguments').text=subprocess.list2cmdline(command)
    tree.find('.//{'+NS+'}WorkingDirectory').text=str(project)
    expected_action={n:tree.find('.//{'+NS+'}'+n).text for n in ('Arguments','WorkingDirectory','Command')}
    source=storage/(NAME+'_TASK.xml');export=storage/(NAME+'_REGISTERED_TASK.xml')
    created=False
    if exists(NAME):
        if not export.is_file():raise PermissionError('OWN_MAINTENANCE_REGISTRATION_RECEIPT_REQUIRED')
        current=powershell("Export-ScheduledTask -TaskName '"+NAME+"'")
        if current.strip()!=export.read_text(encoding='utf-8').strip():raise PermissionError('OWN_MAINTENANCE_TASK_DRIFT')
    else:
        ET.ElementTree(tree).write(source,encoding='utf-16',xml_declaration=True)
        result=subprocess.run(['schtasks.exe','/Create','/TN',NAME,'/XML',str(source)],capture_output=True,text=True,errors='replace')
        if result.returncode:raise PermissionError('MAINTENANCE_MONITOR_TASK_CREATE_FAILED:'+result.stderr)
        current=powershell("Export-ScheduledTask -TaskName '"+NAME+"'")
        export.write_text(current,encoding='utf-8');created=True
    parsed=ET.fromstring(current)
    if any(parsed.find('.//{'+NS+'}'+n).text!=v for n,v in expected_action.items()):raise PermissionError('OWN_MAINTENANCE_TASK_ACTION_DRIFT')
    runlevel=powershell("(Get-ScheduledTask -TaskName '"+NAME+"').Principal.RunLevel").strip()
    if runlevel!='Limited' or parsed.find('.//{'+NS+'}LogonType').text!='InteractiveToken':raise PermissionError('OWN_MAINTENANCE_TASK_PRIVILEGE_DRIFT')
    live=read(storage/'MAINTENANCE_MONITOR_PROCESS.json') if (storage/'MAINTENANCE_MONITOR_PROCESS.json').is_file() else {}
    if not same_process(live):run_task(NAME)
    receipt=dict(PASS=True,name=NAME,created=created,definition=record(export),UTC=now(),read_only=True,
        original_tasks_modified=False,S4U_attempts=0,security_policy_changed=False,
        logoff_persistence='LOGOFF_PERSISTENCE_NOT_PROVEN',URL='http://127.0.0.1:8794/')
    atomic(storage/'MAINTENANCE_MONITOR_REGISTRATION.json',receipt)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--campaign',required=True);p.add_argument('--storage',required=True);a=p.parse_args()
    import json
    print(json.dumps(install(a.campaign,a.storage),ensure_ascii=False),flush=True)
