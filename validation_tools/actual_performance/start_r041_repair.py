from pathlib import Path
import sys,subprocess,os,shutil
import psutil
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from v44_recovery_r041 import operations as op
from v44.common import read,record,verify,atomic,now

def run():
    op.authority();assert op.allowed() and not op.base.workers()
    proof=Path('D:/MobileESS_V44/development/R041_REUSED_A1_NATIVE0_20261019/RESULT.json');assert read(proof)['PASS'] and not read(proof)['Actual_executed']
    state=read(op.STATE);atomic(op.OPS/'R041_BATCH_BEFORE_RETRY.json',state)
    retry={tuple(k) for k in op.authority()['retry_cases']}
    for i,j in enumerate(state['jobs']):
        if op.key(j) in retry:
            assert j['status'] in ('EXCLUDED','PRE_FAILED','ACTUAL_FAILED')
            state['jobs'][i]=dict(day=j['day'],arm=j['arm'],status='PENDING')
    state.update(phase='PREPARE_SERIAL',R041_authorization=record(op.AMENDMENT),Actual_paused_by_user=True)
    atomic(op.STATE,state)
    h=read(op.OPS/'CURRENT_HANDOFF.json');h.update(active_revision='v44_recovery_r041',active_operational_entry=op.ENTRY,active_operational_permit=record(op.AMENDMENT),
        Actual_paused_by_user=True,pending_revision=None,pending_permit=None,latest_user_instruction=op.authority()['user_instruction'],
        collector=str(op.OPS/'collect_watchdog_r041.py'),active_source_auditor=str(op.OPS/'audit_active_revision_r041.py'),
        entry=f'python -m {op.ENTRY} --watchdog --algorithm {op.ALGORITHM}',next='Retry failed preparations only. Actual is stopped and stays paused after all preparations.')
    atomic(op.OPS/'CURRENT_HANDOFF.json',h)
    for stem,fn in [('collect_watchdog','collect'),('audit_active_revision','audit')]:
        path=op.OPS/(stem+'_r041.py');assert not path.exists()
        code="import sys,json\nsys.path.insert(0,'D:/v44_r022_rowgen_20261017')\nfrom v44_recovery_r041 import operations as op\nfrom v44_recovery_r040.monitor import "+fn+"\nfrom v44.common import read,verify,record\nop.authority()\nv="+fn+"()\n"
        if fn=='audit':
            code+="for w in op.base.workers():\n a=w['cmdline']\n if op.ENTRY in a:\n  r=read(a[a.index('--worker')+1]);verify(r['R041_sources']);assert r['R041_authorization']==record(op.AMENDMENT);assert r['r038_phase']=='PREPARE_SERIAL'\n"
        code+="v['Actual_paused_by_user']=True\nprint(json.dumps({k:v[k] for k in ('UTC','PASS','active','pending','active_revision','counts','Actual_paused_by_user') if k in v},ensure_ascii=False))\n"
        path.write_text(code,encoding='utf8')
        route=op.OPS/(stem+'_r032.py');shutil.copy2(route,op.OPS/(route.name+'.before_r041'))
        prefix=("# User stop: preparation-only r041 repair.\nimport json as _r041j,runpy as _r041r\nfrom pathlib import Path as _r041P\n_r041o=_r041P(__file__).parent\n_r041h=_r041j.loads((_r041o/'CURRENT_HANDOFF.json').read_text(encoding='utf-8-sig'))\nif 'v44_recovery_r041' in (_r041h.get('active_revision'),_r041h.get('pending_revision')):\n    _r041r.run_path(str(_r041o/'"+path.name+"'),run_name='__main__')\n    raise SystemExit(0)\n")
        route.write_text(prefix+route.read_text(encoding='utf8'),encoding='utf8')
    with (op.OPS/'r041_watchdog.log').open('ab') as stream:
        p=subprocess.Popen([sys.executable,'-u','-m',op.ENTRY,'--watchdog','--algorithm',op.ALGORITHM],cwd=Path(__file__).resolve().parents[2],env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1'),stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    atomic(op.OPS/'R041_REPAIR_RELEASE.json',dict(UTC=now(),PASS=True,watchdog_pid=p.pid,process_created=psutil.Process(p.pid).create_time(),
        retry_cases=list(map(list,retry)),Actual_paused_by_user=True,authorization=record(op.AMENDMENT),real_preparation_validation=record(proof)))
    print(dict(PASS=True,watchdog_pid=p.pid,Actual_paused=True))

if __name__=='__main__':run()
