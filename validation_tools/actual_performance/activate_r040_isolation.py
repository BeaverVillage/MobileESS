"""Arm the tested per-case scheduler at the current worker's natural boundary."""
from pathlib import Path
import sys,subprocess,os,shutil
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r040 import operations as op
from v44.common import read,record,verify,atomic,now

def run():
    op.authority()
    proof=Path('D:/MobileESS_V44/development/R040_PARALLEL_BOOTSTRAP_NATIVE0_20261019/RESULT.json')
    assert read(proof)['PASS'] and read(proof)['parallel_worker_bootstraps']>=2 and read(proof)['Native_optimizer_calls']==0
    out=Path('D:/MobileESS_V44/development/R040_ACTIVATION_20261019');out.mkdir(exist_ok=False)
    active=op.base.workers();protected=[];pins=[]
    for w in active:
        p=psutil.Process(w['pid']);args=w['cmdline'];request=read(args[args.index('--worker')+1])
        pins+=request['sources']+request.get('R039_sources',[])+request.get('R040_sources',[])
        protected.append(dict(pid=p.pid,process_created=p.create_time(),command=args,case_root=request['case_root']))
    verify(pins)
    stop=op.OPS/'STOP_AUTONOMY.json'
    if stop.exists():raise PermissionError('UNRELATED_USER_STOP_PRESERVED')
    atomic(out/'WORKERS_BEFORE.json',protected)
    for stem,function in [('collect_watchdog','collect'),('audit_active_revision','audit')]:
        wrapper=op.OPS/(stem+'_r040.py');assert not wrapper.exists()
        wrapper.write_text("import sys,json\nsys.path.insert(0,'D:/v44_r022_rowgen_20261017')\nfrom v44_recovery_r040.monitor import "+function+"\nv="+function+"()\nprint(json.dumps({k:v[k] for k in ('UTC','PASS','active','pending','active_revision','counts') if k in v},ensure_ascii=False))\n",encoding='utf8')
        route=op.OPS/(stem+'_r032.py');assert str(route).casefold() not in {r['path'].casefold() for r in pins}
        shutil.copy2(route,out/(route.name+'.before'))
        prefix=("# Resolve all preparations and isolate failed cases under user-authorized r040.\nimport json as _r040_json,runpy as _r040_runpy\nfrom pathlib import Path as _r040_Path\n"
            "_r040_ops=_r040_Path(__file__).parent\n_r040_h=_r040_json.loads((_r040_ops/'CURRENT_HANDOFF.json').read_text(encoding='utf-8-sig'))\n"
            "if 'v44_recovery_r040' in (_r040_h.get('active_revision'),_r040_h.get('pending_revision')):\n"
            "    _r040_runpy.run_path(str(_r040_ops/'"+wrapper.name+"'),run_name='__main__')\n    raise SystemExit(0)\n")
        route.write_text(prefix+route.read_text(encoding='utf8'),encoding='utf8')
    old_supervisors=[]
    for p in psutil.process_iter(['pid','cmdline','create_time']):
        try:
            args=p.info['cmdline'] or []
            if '--watchdog' in args and any(entry in args for entry in (op.previous.ENTRY,op.original.ENTRY)):
                assert '--worker' not in args and '--dispatch' not in args and p.pid not in [w['pid'] for w in protected]
                old_supervisors.append(dict(pid=p.pid,process_created=p.create_time(),command=args));p.terminate();p.wait(timeout=10)
        except psutil.NoSuchProcess:pass
    atomic(out/'OLD_WATCHDOGS_STOPPED.json',old_supervisors)
    atomic(stop,dict(UTC=now(),reason=op.HOLD,user_stop=False,current_worker_must_finish=True,authorization=record(op.AMENDMENT)))
    h=read(op.OPS/'CURRENT_HANDOFF.json');atomic(out/'HANDOFF_BEFORE.json',h)
    h.update(UTC=now(),pending_revision='v44_recovery_r040',pending_permit=record(op.AMENDMENT),pending_validation=op.authority()['validation'],
        latest_user_instruction=op.authority()['user_instruction'],next='Finish current preparation naturally, resolve remaining preparations serially, then run every healthy case in parallel; exclude only failed date/arm.')
    atomic(op.OPS/'CURRENT_HANDOFF.json',h)
    with (op.OPS/'r040_handover.log').open('ab') as stream:
        p=subprocess.Popen([sys.executable,'-u','-m',op.ENTRY,'--handover','--algorithm',op.ALGORITHM],
            cwd=Path(__file__).resolve().parents[2],env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    atomic(op.OPS/'R040_HANDOVER_LAUNCH.json',dict(UTC=now(),pid=p.pid,process_created=psutil.Process(p.pid).create_time()))
    verify(pins)
    for w in protected:assert abs(psutil.Process(w['pid']).create_time()-w['process_created'])<.001
    atomic(out/'RESULT.json',dict(UTC=now(),PASS=True,authorization=record(op.AMENDMENT),bootstrap=record(proof),
        current_workers_untouched=protected,only_old_watchdogs_stopped=old_supervisors,handover_pid=p.pid))
    print(dict(PASS=True,handover_pid=p.pid,current_workers=[w['pid'] for w in protected]))

if __name__=='__main__':run()
