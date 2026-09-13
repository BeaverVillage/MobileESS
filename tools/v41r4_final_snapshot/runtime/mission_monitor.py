"""Independent 5-second UI status publisher and 600-second health recorder."""
from mission_health import *
import subprocess,sys
def publish():
    s=read(RUN/'campaign_progress.json');active={(r['day'],r['phase']):r for r in s['active']};units={}
    for n in range(1,32):
        day=f'2025-05-{n:02}'
        for policy in ('B0','B1','B2','B3'):
            row=dict(day=day,policy=policy,status='WAITING',phase='queued',worker_pid=None)
            da=RUN/day/policy/'dayahead/DAYAHEAD_RECEIPT.json';ac=RUN/day/policy/'actual/ACTUAL_RECEIPT.json'
            if da.exists():row.update(status='DA_COMPLETE',phase='Actual 대기')
            if ac.exists() and read(ac)['status']=='COMPLETE':row.update(status='COMPLETE',phase='complete')
            for phase in (['electrical','domain'] if policy=='B0' else [])+[policy+'_DA',policy+'_AC']:
                if (day,phase) in active:
                    a=active[day,phase]
                    row.update(status='RUNNING',phase={'electrical':'ELECTRICAL_GENERATION','domain':'DOMAIN_PREPARATION'}.get(phase,'actual' if phase.endswith('_AC') else 'dayahead'),worker_pid=a['worker_pid'],log=a['log'])
            for e in s.get('errors',[]):
                if e['day']==day and (e['phase'].startswith(policy) or (policy=='B0' and e['phase'] in ('electrical','domain'))):row.update(status='FAILED',error=e['error'])
            units[day+'|'+policy]=row
    write(RUN/'campaign_state.json',dict(status=s['status'],units=units,updated_at=time.time(),source='MISSION_STATUS_PUBLISHER'))
    write(OUT/'MONITOR_HEARTBEAT.json',dict(pid=os.getpid(),at=time.time(),refresh_seconds=5,health_check_seconds=600))
def main():
    last=0
    while True:
        try:
            publish()
            if time.time()-last>=600:
                result=subprocess.run([sys.executable,str(ROOT/'mission_health.py')],cwd=ROOT,capture_output=True,text=True)
                print(result.stdout,result.stderr,flush=True);last=time.time()
        except Exception:print(traceback.format_exc(),flush=True)
        time.sleep(5)
if __name__=='__main__':
    if sys.argv[1]=='worker':
        log=LOG/'monitor_service.log';LOG.mkdir(parents=True,exist_ok=True)
        sys.stdout=open(log,'a',encoding='utf-8',buffering=1);sys.stderr=sys.stdout;main()
    elif sys.argv[1]=='spawn':
        args=subprocess.list2cmdline([sys.executable,'-u',str(ROOT/'mission_monitor.py'),'worker'])
        quote=lambda s:"'"+s.replace("'","''")+"'"
        command="$missionStartup=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]0;CreateFlags=[uint32]8}\n"
        command+="$missionProc=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine="+quote(args)+";CurrentDirectory="+quote(str(ROOT))+";ProcessStartupInformation=$missionStartup}\n$missionProc | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress"
        r=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,check=True)
        value=json.loads(r.stdout);assert value['ReturnValue']==0;write(OUT/'MONITOR_LAUNCH.json',value);print(r.stdout)
