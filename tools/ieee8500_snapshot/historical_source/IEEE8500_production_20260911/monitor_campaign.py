"""Read-only campaign observer; no policy or authority mutation."""
import json,time
from pathlib import Path
import psutil
H=Path(__file__).resolve().parent
pid=int((H/'CAMPAIGN_V2_PID.txt').read_text().strip())
output=H/'PROCESS_MONITOR.jsonl'
last_stage=None;stage_started=time.monotonic()
while True:
    status=json.loads((H/'CAMPAIGN_STATUS.json').read_text(encoding='utf-8'));stage=status['status']
    if stage!=last_stage:stage_started=time.monotonic();last_stage=stage
    row=dict(timestamp_UTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),stage=stage,observed_stage_seconds=time.monotonic()-stage_started)
    try:
        memory=psutil.Process(pid).memory_info();row.update(RSS_bytes=memory.rss,OS_peak_working_set_bytes=getattr(memory,'peak_wset',None))
    except psutil.NoSuchProcess:row['process_exists']=False
    p=H/'policies'/('B3_A1' if stage.startswith('B3_A1') else 'B1')/'LIVE_STATUS.json'
    if stage.startswith(('B1_','B3_A1_')) and p.exists():
        x=json.loads(p.read_text(encoding='utf-8'));m=x['metrics'];row.update(loop_minutes=round(x['elapsed_seconds']/60,2),P1=x['P1'],updates=x['incumbent_updates'],MILP=m['neighborhood_LP_MILP']['count'],AC=m['exact_AC_validation']['count'])
    with output.open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
    print(json.dumps(row),flush=True)
    if stage in ('COMPLETE','STOPPED_ERROR'):break
    time.sleep(50)
