from pathlib import Path
import sys,subprocess,time,json,urllib.request,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r041 import operations as op
from v44.common import atomic,read,record,now

def run():
    target=Path('D:/MobileESS_V43/development/monitor_partial/monitor_binding.py');source=target.read_text(encoding='utf8')
    atomic(op.OPS/'R041_MONITOR_BEFORE.json',dict(source=record(target),text=source))
    old="    note+='\\n'.join(details or ['Worker 배정 대기'])+'\\n\\n날짜별 28 Case\\n'+'\\n'.join(overview)"
    new="""    actual_user_stop=optional(campaign/'AUTONOMOUS_RECOVERY/STOP_AUTONOMY.json').get('stop_running_Actual') is True
    actual_hold=actual_user_stop and r038.get('phase')=='PRE_ACTUAL_USER_HOLD'
    if actual_user_stop:note='Actual 사용자 중단 · Planning 복구/준비만 허용 · Actual 자동 재개 차단\\n'+note
"""+old
    assert source.count(old)==1;source=source.replace(old,new)
    old="status='사용자 요청으로 중단' if stopped else '캠페인 실행 중'"
    assert source.count(old)==1;source=source.replace(old,"status='Planning 준비 완료 · Actual 사용자 보류' if actual_hold else '사용자 요청으로 중단' if stopped else '캠페인 실행 중'")
    old="workers=workers,cases=cases,actual_tick_details=remaining_actual_ticks(campaign),"
    assert source.count(old)==1;source=source.replace(old,"workers=workers,cases=cases,Actual_paused_by_user=actual_user_stop,actual_tick_details=remaining_actual_ticks(campaign),")
    compile(source,str(target),'exec');target.write_text(source,encoding='utf8')
    monitors=[]
    for p in psutil.process_iter(['cmdline']):
        try:
            if str(target) in (p.info['cmdline'] or []) and p.info['cmdline'][-1]=='8795':monitors.append(p)
        except psutil.Error:pass
    assert len(monitors)==1
    p=monitors[0];cmd=p.cmdline();cwd=p.cwd();env=p.environ();p.terminate();p.wait(timeout=10)
    with (target.parent/'r041_monitor.stdout.log').open('ab') as out,(target.parent/'r041_monitor.stderr.log').open('ab') as err:
        process=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(40):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=4) as response:value=json.load(response)
            break
        except (OSError,ValueError):time.sleep(.25)
    else:raise RuntimeError('MONITOR_NOT_READY')
    assert value['Actual_paused_by_user'] is True
    atomic(op.OPS/'R041_MONITOR_UPDATED.json',dict(UTC=now(),PASS=True,monitor_pid=process.pid,Actual_paused_display=True))
    print(dict(PASS=True,Actual_paused=True,monitor_pid=process.pid))

if __name__=='__main__':run()
