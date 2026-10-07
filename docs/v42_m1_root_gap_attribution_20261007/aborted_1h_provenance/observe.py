"""External read-only heartbeat: distinguish fresh clocks from stale solver values."""
import csv,json,os,threading,time
from datetime import datetime,timezone
from pathlib import Path
import psutil
OUT=Path(__file__).resolve().parent
token=json.loads((OUT/'OPTIMIZE_ONCE.json').read_text(encoding='utf-8'))
started=datetime.fromisoformat(token['UTC']).timestamp()
stop=threading.Event()
fields=['UTC','solve_elapsed_wall_seconds','last_callback_UTC','last_observed_Gurobi_Runtime','callback_observation_age_seconds','nodes_last_observed','incumbent_last_observed','bound_last_observed','gap_last_observed','Work_last_observed','PID_exists','result_exists']
with (OUT/'NATIVE_OBSERVATION_HEARTBEAT.csv').open('x',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
    while True:
        now=datetime.now(timezone.utc);rows=[]
        with (OUT/'M1_C3_NATIVE_1H_PROGRESS.csv').open(encoding='utf-8',newline='') as p:
            rows=[r for r in csv.DictReader(p) if r.get('UTC') and r.get('runtime') and r.get('event')]
        last=rows[-1] if rows else {}
        exists=psutil.pid_exists(token['PID']);done=(OUT/'M1_C3_NATIVE_1H_RESULT.json').exists()
        observed=last.get('UTC')
        row=dict(UTC=now.isoformat(),solve_elapsed_wall_seconds=now.timestamp()-started,last_callback_UTC=observed,
            last_observed_Gurobi_Runtime=last.get('runtime'),callback_observation_age_seconds=None if not observed else now.timestamp()-datetime.fromisoformat(observed).timestamp(),
            PID_exists=exists,result_exists=done)
        for field,key in [('nodes_last_observed','nodes'),('incumbent_last_observed','incumbent'),('bound_last_observed','bound'),('gap_last_observed','gap'),('Work_last_observed','Work')]:row[field]=last.get(key)
        w.writerow(row);f.flush()
        if done or not exists:break
        stop.wait(60)
print('READ_ONLY_OBSERVER_FINISHED',flush=True)
