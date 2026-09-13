"""Five-second V4 UI publication, independent of lengthy scientific audits."""
import os,sys,time,json,subprocess,traceback
from fast_prepare import ROOT
from v41r4_loop_runtime import MAY_RUN as RUN,MAY_OUT,LOGS
from v41r4_loop_budget import adapted
from mission_loop_health import write,read
import mission_monitor

OUT=MAY_OUT/'mission';LOG=LOGS/'mission'
publish=adapted(mission_monitor.publish,[],dict(RUN=RUN,OUT=OUT))

def main():
    LOG.mkdir(parents=True,exist_ok=True)
    sys.stdout=open(LOG/'ui_publisher.log','a',encoding='utf-8',buffering=1);sys.stderr=sys.stdout
    # Prevent duplicate publishers from racing while a relaunch is attempted.
    from dayahead.v41.campaign import campaign_lock
    with campaign_lock(OUT/'ui_publisher_lock'):
        while True:
            try:
                publish()
                finished=RUN/'CAMPAIGN_FINISHED.json'
                state=read(RUN/'campaign_progress.json')
                if finished.exists() and read(finished).get('finished_at',0)>=state.get('started_at',0):
                    if not state.get('active'):return
            except Exception:print(traceback.format_exc(),flush=True)
            time.sleep(5)

def spawn():
    args=subprocess.list2cmdline([sys.executable,'-u',str(ROOT/'mission_loop_ui.py'),'worker'])
    quote=lambda s:"'"+s.replace("'","''")+"'"
    command="$uiStartup=New-CimInstance -CimClass (Get-CimClass Win32_ProcessStartup) -ClientOnly -Property @{ShowWindow=[uint16]0;CreateFlags=[uint32]8}\n"
    command+="$uiProc=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine="+quote(args)+";CurrentDirectory="+quote(str(ROOT))+";ProcessStartupInformation=$uiStartup}\n$uiProc | Select-Object ProcessId,ReturnValue | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,check=True)
    value=json.loads(result.stdout);assert value['ReturnValue']==0
    write(OUT/'UI_PUBLISHER_LAUNCH.json',value);print(value)

if __name__=='__main__':
    if sys.argv[1]=='worker':main()
    elif sys.argv[1]=='spawn':spawn()
    elif sys.argv[1]=='once':publish()
