"""Display case exclusions and the resolved healthy Actual subset."""
from pathlib import Path
import sys,shutil,subprocess,time,json,urllib.request
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r040 import operations as op
from v44.common import read,record,verify,atomic,now

def run():
    target=Path('D:/MobileESS_V43/development/monitor_partial/monitor_binding.py')
    out=Path('D:/MobileESS_V44/development/R040_ACTIVATION_20261019')
    source=target.read_text(encoding='utf8');shutil.copy2(target,out/'monitor_binding.before.py')
    pins=[];workers=[]
    for w in op.base.workers():
        args=w['cmdline'];r=read(args[args.index('--worker')+1]);pins+=r['sources']+r.get('R039_sources',[])+r.get('R040_sources',[])
        p=psutil.Process(w['pid']);workers.append(dict(pid=p.pid,process_created=p.create_time()))
    assert str(target).casefold() not in {r['path'].casefold() for r in pins}
    edits={
        "'PRE_ACTUAL_READY':'Actual 준비 완료'":"'PRE_ACTUAL_READY':'Actual 준비 완료','EXCLUDED':'Actual 제외'",
        "finished=sum(r['status'] in ('COMPLETE','FAILED','BLOCKED','INPUT_NOT_READY') for r in cases)":"finished=sum(r['status'] in ('COMPLETE','FAILED','BLOCKED','INPUT_NOT_READY','EXCLUDED') for r in cases)",
        "ready=sum(j['status']=='PREPARED' for j in r038['jobs'])":"ready=sum(j['status']=='PREPARED' for j in r038['jobs'])\n        excluded=sum(j['status']=='EXCLUDED' for j in r038['jobs'])",
        "note=f'r038: 남은 7건 Actual 직전까지 1-worker 순차 준비 · 준비 완료 {ready}/7\\n모두 준비되면 Actual/Fresh 7-worker 병렬 시작\\n'":
        "note=f'남은 7건 Actual 직전까지 1-worker 순차 준비 · 준비 완료 {ready}/7 · 제외 {excluded}건\\n모든 준비 시도 종료 후 정상 건만 P-core Actual/Fresh 병렬 실행 · 한 건 실패는 다른 건을 막지 않습니다.\\n'",
        'note=f"r038: {r038[\'phase\']} · 독립 Actual/Fresh worker {len(workers)}/7\\n전체 P-core 배치 · P코어 6개, 7개 worker 중 2개는 SMT 형제 스레드 사용\\nA/M 계획은 검증된 동일 Case에서 동결 · Actual/Fresh 수학·물리 판정 유지\\n"':
        'note=f"{r038[\'phase\']} · 독립 Actual/Fresh worker {len(workers)} · 제외 {excluded}건\\n검증된 정상 건만 전체 P-core 배치 · 실행 중 오류도 건별 격리\\nA/M 계획은 동일 Case에서 동결 · Actual/Fresh 물리 판정 유지\\n"',
    }
    for old,new in edits.items():
        assert source.count(old)==1,old
        source=source.replace(old,new)
    compile(source,str(target),'exec');target.write_text(source,encoding='utf8')
    matches=[]
    for p in psutil.process_iter(['cmdline']):
        try:
            if str(target) in (p.info['cmdline'] or []) and p.info['cmdline'][-1]=='8795':matches.append(p)
        except psutil.Error:pass
    assert len(matches)==1
    p=matches[0];command=p.cmdline();cwd=p.cwd();env=p.environ();assert p.pid not in [w['pid'] for w in workers]
    p.terminate();p.wait(timeout=10)
    with (out/'monitor.stdout.log').open('ab') as stdout,(out/'monitor.stderr.log').open('ab') as stderr:
        p=subprocess.Popen(command,cwd=cwd,env=env,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(40):
        if p.poll() is not None:raise RuntimeError('MONITOR_EXITED')
        try:
            with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=4) as response:value=json.load(response)
            break
        except (OSError,ValueError):time.sleep(.25)
    else:raise RuntimeError('MONITOR_NOT_READY')
    assert 'excluded' in value['actual_tick_details'] and len(value['actual_tick_details']['rows'])==8
    for w in workers:assert abs(psutil.Process(w['pid']).create_time()-w['process_created'])<.001
    verify(pins);op.authority()
    atomic(out/'MONITOR_UPDATE.json',dict(UTC=now(),PASS=True,monitor_pid=p.pid,worker_untouched=workers,
        sources=[record(target),record(target.with_name('actual_tick_details.py'))],exclusion_display_supported=True))
    print(dict(PASS=True,monitor_pid=p.pid,excluded=value['actual_tick_details']['excluded']))

if __name__=='__main__':run()
