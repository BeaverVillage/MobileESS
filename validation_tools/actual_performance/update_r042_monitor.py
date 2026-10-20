from pathlib import Path
import sys,subprocess,time,json,urllib.request,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r042 import operations as op
from v44.common import read,record,atomic,now

def run():
    file=Path('D:/MobileESS_V43/development/monitor_partial/monitor_binding.py');source=file.read_text(encoding='utf8')
    atomic(op.OPS/'R042_MONITOR_BEFORE.json',dict(source=record(file),text=source))
    old="    if actual_user_stop:note='Actual 사용자 중단 · Planning 복구/준비만 허용 · Actual 자동 재개 차단\\n'+note"
    new="""    actual_auto_start=bool(optional(campaign/'AUTONOMOUS_RECOVERY/CURRENT_HANDOFF.json').get('Actual_auto_start_authorization')) and optional(campaign/'AUTONOMOUS_RECOVERY/STOP_AUTONOMY.json').get('reason')=='USER_ACTUAL_PAUSED_PREPARATION_REPAIR_ALLOWED'
    if actual_user_stop:note=('Actual 현재 대기 · 모든 Planning 준비 시도 종료 후 정상 건만 최대 7-worker 자동 시작\\n' if actual_auto_start else 'Actual 사용자 중단 · Planning 복구/준비만 허용 · Actual 자동 재개 차단\\n')+note"""
    assert source.count(old)==1;source=source.replace(old,new)
    old="status='Planning 준비 완료 · Actual 사용자 보류' if actual_hold else"
    assert source.count(old)==1;source=source.replace(old,"status=('Planning 준비 완료 · Actual 자동 시작 대기' if actual_auto_start else 'Planning 준비 완료 · Actual 사용자 보류') if actual_hold else")
    old='Actual_paused_by_user=actual_user_stop,actual_tick_details='
    assert source.count(old)==1;source=source.replace(old,'Actual_paused_by_user=actual_user_stop,Actual_auto_start_armed=actual_auto_start,actual_tick_details=')
    compile(source,str(file),'exec');file.write_text(source,encoding='utf8')
    matches=[]
    for p in psutil.process_iter(['cmdline']):
        try:
            if str(file) in (p.info['cmdline'] or []) and p.info['cmdline'][-1]=='8795':matches.append(p)
        except psutil.Error:pass
    assert len(matches)==1
    p=matches[0];cmd=p.cmdline();cwd=p.cwd();env=p.environ();p.terminate();p.wait(timeout=10)
    with (file.parent/'r042_monitor.stdout.log').open('ab') as out,(file.parent/'r042_monitor.stderr.log').open('ab') as err:
        process=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=out,stderr=err,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(40):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=4) as response:value=json.load(response)
            break
        except (OSError,ValueError):time.sleep(.25)
    else:raise RuntimeError('MONITOR_NOT_READY')
    assert value['Actual_auto_start_armed'] is True
    atomic(op.OPS/'R042_MONITOR_UPDATED.json',dict(UTC=now(),PASS=True,monitor_pid=process.pid,Actual_auto_start_armed=True))
    print(dict(PASS=True,monitor_pid=process.pid,Actual_auto_start_armed=True))

if __name__=='__main__':run()
