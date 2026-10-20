from pathlib import Path
import ast,json,os,subprocess,time,urllib.request,psutil
ops=Path(__file__).parent
base=Path('D:/MobileESS_V43/development/monitor_partial')
source=base/'monitor_binding.py'
old=ast.parse((ops/'R047_MONITOR_BEFORE.py').read_text(encoding='utf-8-sig'))
new=ast.parse(source.read_text(encoding='utf-8-sig'))
for name in ('case_loading_table','html'):
    a=next((n for n in old.body if isinstance(n,ast.FunctionDef) and n.name==name),None)
    b=next((n for n in new.body if isinstance(n,ast.FunctionDef) and n.name==name),None)
    assert ast.dump(a)==ast.dump(b) if a is not None else b is None
monitor=psutil.Process(85164);args=monitor.cmdline()
assert str(source) in args and args[-1]=='8795'
workers=[dict(pid=p.pid,created=p.create_time()) for p in psutil.process_iter(['cmdline']) if '--worker' in (p.info['cmdline'] or []) and any('v44_recovery_' in a for a in p.info['cmdline'])]
assert monitor.pid not in [p['pid'] for p in workers]
env=dict(os.environ,PYTHONUTF8='1',PYTHONPATH=monitor.environ().get('PYTHONPATH',''))
cwd=monitor.cwd();metadata=dict(pid=monitor.pid,created=monitor.create_time(),command=args,cwd=cwd,pythonpath=env['PYTHONPATH'])
(ops/'R047_MONITOR_PROCESS_BEFORE.json').write_text(json.dumps(metadata),encoding='utf-8')
monitor.terminate();monitor.wait(10)
with (ops/'r047_monitor.out.log').open('ab') as out,(ops/'r047_monitor.err.log').open('ab') as err:
    proc=subprocess.Popen(args,cwd=cwd,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
for w in workers:assert abs(psutil.Process(w['pid']).create_time()-w['created'])<.001
for _ in range(20):
    try:
        status=json.load(urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=10));break
    except OSError:time.sleep(1)
else:raise RuntimeError('MONITOR_NOT_READY')
(ops/'R047_MONITOR_VERIFIED.json').write_text(json.dumps(dict(monitor_pid=proc.pid,protected_workers=workers,worker_count=len(status['workers']),summary=status.get('campaign_summary'),same_loading_table=True),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(monitor_pid=proc.pid,worker_count=len(status['workers']),summary=status.get('campaign_summary')),ensure_ascii=False))
