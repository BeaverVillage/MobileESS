"""Persist the sealed latency overlay in monitoring and Windows startup."""
from pathlib import Path
import sys,subprocess,psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r039 import operations as op
from v44.common import read,record,atomic,now

def run():
    op.authority()
    protected=[]
    for w in op.base.workers():
        args=w['cmdline'];protected+=read(args[args.index('--worker')+1])['sources']
    for stem,function in [('collect_watchdog','collect'),('audit_active_revision','audit')]:
        target=op.OPS/(stem+'_r039.py')
        assert not target.exists()
        target.write_text("import sys,json\nsys.path.insert(0,'D:/v44_r022_rowgen_20261017')\nfrom v44_recovery_r039.monitor import "+function+"\nv="+function+"()\nprint(json.dumps({k:v[k] for k in ('UTC','PASS','active','pending','active_revision','counts') if k in v},ensure_ascii=False))\n",encoding='utf-8')
        route=op.OPS/(stem+'_r032.py')
        assert str(route).casefold() not in {r['path'].casefold() for r in protected}
        atomic(op.OPS/(route.name+'.R039_BEFORE.json'),dict(source=record(route),content=route.read_text(encoding='utf-8')))
        prefix=("# Explicit r039 latency overlay and parallel B1 Actual.\nimport json as _r039_json,runpy as _r039_runpy\nfrom pathlib import Path as _r039_Path\n"
            "_r039_ops=_r039_Path(__file__).parent\n_r039_h=_r039_json.loads((_r039_ops/'CURRENT_HANDOFF.json').read_text(encoding='utf-8-sig'))\n"
            "if 'v44_recovery_r039' in (_r039_h.get('active_revision'),_r039_h.get('pending_revision')):\n"
            "    _r039_runpy.run_path(str(_r039_ops/'"+target.name+"'),run_name='__main__')\n    raise SystemExit(0)\n")
        route.write_text(prefix+route.read_text(encoding='utf-8'),encoding='utf-8')
    with (op.OPS/'r039_watchdog.log').open('ab') as log:
        p=subprocess.Popen([sys.executable,'-u','-m',op.ENTRY,'--watchdog','--algorithm',op.previous.ALGORITHM],
            cwd=Path(__file__).resolve().parents[2],stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    atomic(op.OPS/'R039_WATCHDOG_LAUNCH.json',dict(UTC=now(),pid=p.pid,process_created=psutil.Process(p.pid).create_time()))
    print(dict(PASS=True,watchdog_pid=p.pid))

if __name__=='__main__':run()
