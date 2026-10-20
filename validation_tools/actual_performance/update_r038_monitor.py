"""Display explicit preparation and resumed Actual process identities."""
from pathlib import Path
import sys,shutil,subprocess,time,json,urllib.request,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r038 import operations as op
from v44.common import read,record,verify,atomic,now

base=Path('D:/MobileESS_V43/development/monitor_partial')
target=base/'monitor_binding.py';out=Path('D:/MobileESS_V44/development/R038_DEPLOYMENT_20261018')
protected=read(read(op.OPS/'USER_PRE_ACTUAL_BATCH_BOUNDARY_REQUEST.json')['protected_request']['path'])
assert str(target).casefold() not in {r['path'].casefold() for r in protected['sources']}
source=target.read_text(encoding='utf-8');original=source
edits={
 "process=optional(case/'START.json');is_live=False;rss=None":
 "process=(optional(case/'ACTUAL_START.json') or optional(case/'START.json')) if stage=='ACTUAL_FRESH' else optional(case/'START.json');is_live=False;rss=None",
 "'INTERRUPTED_BY_USER':'사용자 중단'":"'INTERRUPTED_BY_USER':'사용자 중단','PRE_ACTUAL_READY':'Actual 준비 완료'",
}
for old,new in edits.items():
    assert source.count(old)==1,old
    source=source.replace(old,new)
old="    note+='\\n'.join(details or ['Worker 배정 대기'])+'\\n\\n날짜별 28 Case\\n'+'\\n'.join(overview)"
assert source.count(old)==1
new="""    r038=optional(campaign/'AUTONOMOUS_RECOVERY/R038_BATCH_STATE.json')
    if r038:
        ready=sum(j['status']=='PREPARED' for j in r038['jobs'])
        if r038['phase']=='PREPARE_SERIAL':
            note=f'r038: 남은 7건 Actual 직전까지 1-worker 순차 준비 · 준비 완료 {ready}/7\\n모두 준비되면 Actual/Fresh 7-worker 병렬 시작\\n'
        else:
            note=f\"r038: {r038['phase']} · 독립 Actual/Fresh worker {len(workers)}/7\\n전체 P-core 배치 · P코어 6개, 7개 worker 중 2개는 SMT 형제 스레드 사용\\nA/M 계획은 검증된 동일 Case에서 동결 · Actual/Fresh 수학·물리 판정 유지\\n\"
    note+='\\n'.join(details or ['Worker 배정 대기'])+'\\n\\n날짜별 28 Case\\n'+'\\n'.join(overview)"""
source=source.replace(old,new);compile(source,str(target),'exec')
shutil.copy2(target,out/'monitor_binding.before.py');target.write_text(source,encoding='utf-8')
monitors=[]
for p in psutil.process_iter(['pid','cmdline']):
    try:
        command=p.info['cmdline'] or []
        if len(command)>2 and str(target) in command and command[-1]=='8795':monitors.append(p)
    except psutil.Error:pass
assert len(monitors)==1
old_process=monitors[0];command=old_process.cmdline();cwd=old_process.cwd();env=old_process.environ()
old_process.terminate();old_process.wait(timeout=10)
with (out/'monitor.stdout.log').open('ab') as stdout,(out/'monitor.stderr.log').open('ab') as stderr:
    process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
for _ in range(40):
    if process.poll() is not None:raise RuntimeError('MONITOR_EXITED')
    try:
        with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=3) as r:value=json.load(r)
        break
    except (OSError,ValueError):time.sleep(.25)
else:raise RuntimeError('MONITOR_NOT_READY')
verify(protected['sources']);op.validate()
atomic(out/'MONITOR_UPDATE.json',dict(UTC=now(),PASS=True,monitor_PID=process.pid,source=record(target),
    URL='http://127.0.0.1:8795/',actual_resume_identity_supported=True,batch_phase_labels_supported=True,
    scientific_worker_unchanged=True))
print(dict(PASS=True,monitor_PID=process.pid),flush=True)
