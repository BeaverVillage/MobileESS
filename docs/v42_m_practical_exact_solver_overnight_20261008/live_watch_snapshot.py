"""Read-only owned solver observation; no solver API/model/optimize."""
import json,re,os,sys
from pathlib import Path
from datetime import datetime,timezone
import psutil

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1];OLD=ROOT/'docs/v42_m1_exact_solver_redesign_20261008'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def atomic(p,data):
    tmp=p.with_suffix('.json.tmp')
    with tmp.open('w',encoding='utf-8',newline='\n') as f:json.dump(data,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)
def run():
    now=datetime.now(timezone.utc);folder=OUT/'runs/native_production_initial';marker=read(folder/'OPTIMIZE_ONCE.json');receipt=folder/'RESULT.json'
    data=dict(UTC=now.isoformat(),night_remaining_seconds=(datetime.fromisoformat(read(OUT/'IMMUTABLE_DEADLINE.json')['deadline_UTC'])-now).total_seconds(),native_finished=receipt.exists())
    data['native']=read(receipt) if receipt.exists() else dict(wall_since_optimize=(now-datetime.fromisoformat(marker['UTC'])).total_seconds(),last_observed=read(folder/'LIVE.json'))
    rows=[]
    for line in (OLD/'external_nodes/0000/LP.log').read_text(encoding='utf-8',errors='replace').splitlines():
        fields=line.split()
        if len(fields)==5 and fields[0].isdigit() and fields[-1].endswith('s'):
            try:rows.append(dict(iterations=int(fields[0]),objective=float(fields[1]),primal_infeasibility=float(fields[2]),Runtime_log_seconds=float(fields[4][:-1])))
            except ValueError:pass
    data['M0_last_simplex']=rows[-1] if rows else None;data['M0_root_receipt_exists']=(OLD/'external_nodes/0000/RESULT.json').exists()
    processes=[]
    for pid,script in [(marker['PID'],'native_production_runner.py'),(read(OUT/'IMMUTABLE_DEADLINE.json')['existing_M0_process_PID'],'external_bb.py')]:
        try:
            p=psutil.Process(pid)
            if Path(p.cwd()).resolve()==ROOT.resolve() and script in ' '.join(p.cmdline()):processes.append(dict(PID=pid,RSS=p.memory_info().rss,cpu_seconds=p.cpu_times().user+p.cpu_times().system,owned=True))
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    data['owned_processes']=processes;atomic(OUT/'LIVE_WATCH.json',data)
    print(json.dumps(data,ensure_ascii=False))
if __name__=='__main__':run()
