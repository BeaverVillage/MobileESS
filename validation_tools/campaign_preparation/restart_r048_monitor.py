"""Restart only the existing monitor; retain every campaign worker identity."""
import os,sys,json,subprocess,time,urllib.request,ast
from pathlib import Path
import psutil
base=Path('D:/MobileESS_V43/development/monitor_partial');source=base/'monitor_binding.py'
home=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign005_may08_14/OPERATIONS/R048_MONTH_B0')
ast.parse(source.read_text(encoding='utf-8-sig'))
monitor=psutil.Process(66832);cmd=monitor.cmdline();assert str(source) in cmd and cmd[-1]=='8795'
workers=[dict(pid=p.pid,process_created=p.create_time()) for p in psutil.process_iter(['cmdline']) if '--worker' in (p.info['cmdline'] or []) and any('v44_recovery_' in a for a in (p.info['cmdline'] or []))]
assert monitor.pid not in [p['pid'] for p in workers]
env=dict(os.environ,PYTHONUTF8='1',PYTHONPATH=monitor.environ().get('PYTHONPATH',''));cwd=monitor.cwd()
monitor.terminate();monitor.wait(10)
with (home/'monitor.out.log').open('ab') as out,(home/'monitor.err.log').open('ab') as err:
    proc=subprocess.Popen(cmd,cwd=cwd,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
for w in workers:assert abs(psutil.Process(w['pid']).create_time()-w['process_created'])<.001
for _ in range(25):
    try:v=json.load(urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=15));break
    except OSError:time.sleep(1)
else:raise RuntimeError('R048_MONITOR_NOT_READY')
assert len(v['case_line_loading']['rows'])==31
assert v['campaign_summary']['B0_parallel_limit']==1
assert next(r for r in v['case_line_loading']['rows'] if r['day']=='2025-05-23')['cells'][0]['state']=='실패 제외'
(home/'MONITOR_VERIFIED.json').write_text(json.dumps(dict(monitor_pid=proc.pid,workers_preserved=workers,
    date_table_rows=len(v['case_line_loading']['rows']),summary=v['campaign_summary'],workers=v['workers']),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(monitor_pid=proc.pid,rows=31,workers=len(v['workers']),summary=v['campaign_summary']),ensure_ascii=False))
