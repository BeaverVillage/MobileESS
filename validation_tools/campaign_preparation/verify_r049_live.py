"""Check restored May23 admission without starting its simulation early."""
import sys,subprocess,json
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import v44_recovery_r049
from v44_recovery_r049 import operations as new
from v44.common import read,atomic,record,now
from v44.locks import alive

op=new.op
state=read(op.STATE);before=read(new.HOME/'STATE_BEFORE_RECOVERY.json')
assert alive(state['lease']) and state['lease']['pid']==read(new.HOME/'RUN_LAUNCH.json')['pid']
job=next(j for j in state['jobs'] if j['day']=='2025-05-23')
assert job['status']=='BASELINE_QUEUED' and job['exclusion_reason'] is None and job['weather_recovery']==record(new.AUTH)
for prior in before['jobs']:
    if prior['status']=='PASS':
        current=next(j for j in state['jobs'] if j['day']==prior['day'])
        assert current['status']=='PASS' and current['result']==prior['result']
with new.bindings():request=new.new_request(dict(job),state['lease'])
result=subprocess.run([sys.executable,'-X','utf8','-u','-m',new.ENTRY,'--worker',str(request),'--entry-check'],cwd=Path(new.__file__).parents[1],capture_output=True,text=True,encoding='utf-8')
if result.returncode:raise RuntimeError(result.stdout+result.stderr)
entry=op.HOME/(request.stem+'.ENTRY_CHECK.json');assert read(entry)['PASS']
assert not Path(job['case_root']).exists()
report=dict(PASS=True,UTC=now(),lease=state['lease'],counts=dict(Counter(j['status'] for j in state['jobs'])),may23=job,request=record(request),entry_check=record(entry),preserved_PASS=[j['day'] for j in before['jobs'] if j['status']=='PASS'],workers=state['workers'],Native_calls=0,control_ticks=0)
atomic(new.HOME/'LIVE_REQUEUE_VERIFIED.json',report)
print(json.dumps(report,ensure_ascii=False))
