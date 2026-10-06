"""Exact Task Scheduler definitions, hourly OS monitor and ownership audit."""
import ctypes,time
from datetime import timedelta
from xml.etree import ElementTree as ET
from .common import *

def powershell(script):
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,encoding='utf8',errors='replace',timeout=30)
    if p.returncode:raise RuntimeError(p.stderr or p.stdout)
    return p.stdout

def register(root,mode,name,hourly=False):
    f=read(root/'B1_PRODUCTION_FREEZE_MANIFEST.json');user=powershell('[System.Security.Principal.WindowsIdentity]::GetCurrent().Name').strip()
    sid=powershell('[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value').strip()
    # XML has no execution duration limit and no lower CPU priority, battery
    # admission restriction, resource condition or solver-dependent trigger.
    ns='http://schemas.microsoft.com/windows/2004/02/mit/task'
    ET.register_namespace('',ns)
    def tag(parent,key,text=None):
        node=ET.SubElement(parent,'{'+ns+'}'+key)
        if text is not None:node.text=str(text)
        return node
    task=ET.Element('{'+ns+'}Task',version='1.4');registration=tag(task,'RegistrationInfo');tag(registration,'Description','PR134 frozen B1 '+mode+'; no memory/performance guards')
    triggers=tag(task,'Triggers')
    if hourly:
        # The first periodic trigger is one hour after registration. The
        # initial check is explicitly dispatched after launch verification.
        # This prevents the watcher racing the first coordinator launch.
        trigger=tag(triggers,'TimeTrigger');tag(trigger,'Enabled','true');tag(trigger,'StartBoundary',(datetime.now()+timedelta(hours=1)).replace(microsecond=0).isoformat())
        repeat=tag(trigger,'Repetition');tag(repeat,'Interval','PT1H');tag(repeat,'StopAtDurationEnd','false')
        tag(trigger,'ExecutionTimeLimit','PT0S')
    else:
        trigger=tag(triggers,'LogonTrigger');tag(trigger,'Enabled','true');tag(trigger,'ExecutionTimeLimit','PT0S');tag(trigger,'UserId',sid)
    principal=tag(tag(task,'Principals'),'Principal');principal.set('id','Author');tag(principal,'UserId',sid);tag(principal,'LogonType','InteractiveToken');tag(principal,'RunLevel','LeastPrivilege')
    settings=tag(task,'Settings')
    for key,value in [('MultipleInstancesPolicy','IgnoreNew'),('DisallowStartIfOnBatteries','false'),('StopIfGoingOnBatteries','false'),('AllowHardTerminate','true'),
        ('StartWhenAvailable','true'),('RunOnlyIfNetworkAvailable','false'),('AllowStartOnDemand','true'),('Enabled','true'),('Hidden','true'),('ExecutionTimeLimit','PT0S'),('Priority','4')]:tag(settings,key,value)
    restart=tag(settings,'RestartOnFailure');tag(restart,'Interval','PT1M');tag(restart,'Count','2')
    actions=tag(task,'Actions');actions.set('Context','Author');action=tag(actions,'Exec');tag(action,'Command',f['Python']);tag(action,'Arguments','-X utf8 -m v42_pr134_b1.host '+mode+' "'+str(root)+'"');tag(action,'WorkingDirectory',ROOT)
    path=root/(mode+'_TASK.xml');ET.ElementTree(task).write(path,encoding='utf-16',xml_declaration=True)
    present=powershell(f"@(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).Count").strip()
    if present!='0':raise PermissionError('DEDICATED_TASK_NAME_ALREADY_EXISTS:'+name)
    subprocess.run(['schtasks.exe','/Create','/TN',name,'/XML',str(path)],check=True,capture_output=True)
    definition=powershell(f"Export-ScheduledTask -TaskName '{name}'");(root/(mode+'_REGISTERED_TASK.xml')).write_text(definition,encoding='utf8')
    parsed=ET.fromstring(definition);find=lambda p:parsed.find('.//{'+ns+'}'+p)
    if find('ExecutionTimeLimit').text!='PT0S' or find('Priority').text!='4':raise ValueError('SCHEDULER_POLICY_DRIFT')
    return dict(task=name,mode=mode,registered=now(),definition=record(root/(mode+'_REGISTERED_TASK.xml')),user=user,
        hourly=hourly,repeat_interval='PT1H' if hourly else None,logon_resume=not hourly,execution_limit='PT0S',priority=4,restart_count=2,Hidden=True)

def windows_policy(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.OpenProcess.restype=ctypes.c_void_p
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:raise OSError(ctypes.get_last_error())
    class Memory(ctypes.Structure):_fields_=[('MemoryPriority',ctypes.c_ulong)]
    class Throttle(ctypes.Structure):_fields_=[('Version',ctypes.c_ulong),('ControlMask',ctypes.c_ulong),('StateMask',ctypes.c_ulong)]
    memory=Memory();throttle=Throttle();throttle.Version=1
    kernel.GetProcessInformation.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong]
    if not kernel.GetProcessInformation(handle,0,ctypes.byref(memory),ctypes.sizeof(memory)):raise OSError(ctypes.get_last_error())
    if not kernel.GetProcessInformation(handle,4,ctypes.byref(throttle),ctypes.sizeof(throttle)):raise OSError(ctypes.get_last_error())
    kernel.CloseHandle.argtypes=[ctypes.c_void_p];kernel.CloseHandle(handle)
    return dict(CPU_priority=int(psutil.Process(pid).nice()),MemoryPriority=memory.MemoryPriority,
        execution_speed_throttling=bool(throttle.StateMask&1),throttle_control_mask=throttle.ControlMask)

def ancestry(pid):
    result=[]
    try:
        p=psutil.Process(pid)
        for parent in [p]+p.parents():
            try:result.append(dict(PID=parent.pid,created=parent.create_time(),name=parent.name(),command=parent.cmdline()))
            except psutil.Error:result.append(dict(PID=parent.pid,name=parent.name(),command_unavailable=True))
    except psutil.Error:pass
    return result

def launch(root):
    root=Path(root);f=read(root/'B1_PRODUCTION_FREEZE_MANIFEST.json');verify_freeze(f)
    receipts=[register(root,'coordinator',f['task_name']),register(root,'monitor',f['monitor_task']),register(root,'watchdog',f['watchdog_task'],True)]
    atomic(root/'TASK_SCHEDULER_RECEIPT.json',dict(tasks=receipts))
    atomic(root/'HOURLY_WATCHDOG_AUTHORITY.json',dict(task=f['watchdog_task'],interval='PT1H',independent_OS_owner=True,
        latest_user_attachment_authorizes_OS_hourly=True,previous_Windows_repeat_ban_superseded=True,healthy_solver_kill=False,
        memory_guards=False,scientific_parameter_adaptation=False,bounded_coordinator_restart=2,completed_SHA_checks=True))
    subprocess.run(['schtasks.exe','/Run','/TN',f['task_name']],check=True,capture_output=True)
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        if (root/'B1_HEARTBEAT.json').exists() and same_process(read(root/'B1_HEARTBEAT.json').get('process',{})):break
        time.sleep(1)
    else:raise RuntimeError('DETACHED_COORDINATOR_START_FAILED')
    # Retire only the verified old read-only monitor at the same occupied port.
    old=Path('C:/v42_vnext2_execution_20261005_final/web_monitor_20261005/server.py')
    retired=[]
    for p in psutil.process_iter(['pid','create_time','cmdline']):
        try:
            cmd=p.info['cmdline'] or []
            if any(Path(arg).resolve()==old.resolve() for arg in cmd[1:] if arg.endswith('.py')):
                row=process(p.pid);p.terminate();p.wait(timeout=10);retired.append(row)
        except psutil.Error:pass
    subprocess.run(['schtasks.exe','/Run','/TN',f['monitor_task']],check=True,capture_output=True)
    time.sleep(2)
    from urllib.request import urlopen
    first=json.loads(urlopen('http://127.0.0.1:8791/api/status',timeout=5).read());time.sleep(1.1)
    second=json.loads(urlopen('http://127.0.0.1:8791/api/status',timeout=5).read())
    if first['run_id']!=f['run_id'] or second['snapshot_timestamp']==first['snapshot_timestamp']:raise RuntimeError('CURRENT_MONITOR_CONNECTION_OR_REFRESH_FAILED')
    hb=read(root/'B1_HEARTBEAT.json');coor=hb['process'];active=read(root/'ACTIVE.json') if (root/'ACTIVE.json').exists() else {};policies={};chains={}
    for role,row in [('coordinator',coor),('worker',active.get('worker',{})),('monitor',read(root/'MONITOR_PROCESS.json'))]:
        if not row:continue
        if not same_process(row):raise ValueError('DETACHED_PROCESS_IDENTITY_CHANGED')
        policies[role]=windows_policy(row['PID']);chains[role]=ancestry(row['PID'])
        if policies[role]['CPU_priority']!=int(psutil.NORMAL_PRIORITY_CLASS) or policies[role]['MemoryPriority']!=5 or policies[role]['execution_speed_throttling']:raise ValueError('DETACHED_RESOURCE_PRIORITY_POLICY')
        names=[r['name'].lower() for r in chains[role]]
        if not any(n in ('svchost.exe','taskeng.exe','taskhostw.exe') for n in names):raise ValueError('SCHEDULER_SERVICE_OWNERSHIP_NOT_PROVEN')
    evidence=dict(PASS=True,run_id=f['run_id'],processes=dict(coordinator=coor,worker=active.get('worker'),monitor=read(root/'MONITOR_PROCESS.json')),
        ancestry=chains,resource_policy=policies,app_close_experiment_performed=False,Codex_owned_process=False,TaskScheduler_owned=True,
        monitor_run_connected=True,snapshot_changes_each_second=True,old_read_only_monitors_retired=retired)
    atomic(root/'INDEPENDENT_LAUNCH_VERIFICATION.json',evidence);atomic(root/'RESOURCE_LIMIT_AUDIT.json',dict(PASS=True,memory_guards=False,RAM_commit_paging_gate=False,
        healthy_worker_cancellation=False,CPU_throttling=False,artificial_delay=False,resource_adaptive_solver=False,policies=policies))
    # Point legacy entry points to the verified new independent run.
    atomic(Path('C:/v42_vnext2_execution_20261005_final/CURRENT_PRODUCTION.json'),dict(run_id=f['run_id'],root=str(root),worktree=str(ROOT),Git_SHA=f['Git_SHA'],task=f['task_name'],scientific_base=BASE))
    # Preserve superseded definitions, but prevent an old logon trigger from
    # launching another campaign or reclaiming the monitor port later.
    superseded=[]
    for name in ('MobileESS_V42_B1_Independent_NoMemory_20261006T0139',
                 'MobileESS_V42_B1_Independent_Reuse9_NoMemory_20261006T0912',
                 'MobileESS_V42_B1_Monitor_AsyncRefresh_20261006T0206',
                 'MobileESS_V42_B1_UserFreshZero_fresh_zero_may11_only_20261006T003426'):
        present=powershell(f"@(Get-ScheduledTask -TaskName '{name}' -ErrorAction SilentlyContinue).Count").strip()
        if present=='0':continue
        definition=powershell(f"Export-ScheduledTask -TaskName '{name}'")
        preserved=root/'superseded_tasks'/(name+'.xml');preserved.parent.mkdir(parents=True,exist_ok=True);preserved.write_text(definition,encoding='utf8')
        subprocess.run(['schtasks.exe','/Change','/TN',name,'/DISABLE'],check=True,capture_output=True)
        superseded.append(dict(task=name,definition=record(preserved),action='DISABLED_SUPERSEDED_LOGON_TRIGGER'))
    atomic(root/'SUPERSEDED_TASK_RETIREMENT.json',dict(tasks=superseded,definitions_preserved=True))
    subprocess.run(['schtasks.exe','/Run','/TN',f['watchdog_task']],check=True,capture_output=True)
    return evidence

if __name__=='__main__':
    import sys
    launch(Path(sys.argv[1]))
