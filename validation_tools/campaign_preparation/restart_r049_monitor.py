"""Refresh the existing monitor and prove that campaign workers were retained."""
import ast,json,os,subprocess,time,urllib.request
from pathlib import Path
import psutil

source=Path('D:/MobileESS_V43/development/monitor_partial/monitor_binding.py')
home=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign005_may08_14/OPERATIONS/R049_MAY23_WEATHER')
ast.parse(source.read_text(encoding='utf-8-sig'))
monitors=[p for p in psutil.process_iter(['cmdline']) if str(source) in (p.info['cmdline'] or []) and (p.info['cmdline'] or [])[-1]=='8795']
assert len(monitors)==1
monitor=monitors[0];cmd=monitor.cmdline();cwd=monitor.cwd()
workers=[dict(pid=p.pid,process_created=p.create_time()) for p in psutil.process_iter(['cmdline']) if '--worker' in (p.info['cmdline'] or []) and any('v44_recovery_' in a for a in (p.info['cmdline'] or []))]
env=dict(os.environ,PYTHONUTF8='1',PYTHONPATH=monitor.environ().get('PYTHONPATH',''))
monitor.terminate();monitor.wait(10)
with (home/'monitor.out.log').open('ab') as out,(home/'monitor.err.log').open('ab') as err:
    proc=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
for w in workers:
    assert psutil.pid_exists(w['pid']) and abs(psutil.Process(w['pid']).create_time()-w['process_created'])<.001
for _ in range(25):
    try:v=json.load(urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=15));break
    except OSError:time.sleep(1)
else:raise RuntimeError('R049_MONITOR_NOT_READY')
assert len(v['case_line_loading']['rows'])==31
assert v['campaign_summary']['B0_parallel_limit']==1
cell=next(r for r in v['case_line_loading']['rows'] if r['day']=='2025-05-23')['cells'][0]
assert cell['state']=='기상복구 · 실행 대기',cell
report=dict(monitor_pid=proc.pid,workers_preserved=workers,date_table_rows=31,may23_B0=cell,summary=v['campaign_summary'],workers=v['workers'])
(home/'MONITOR_VERIFIED.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
