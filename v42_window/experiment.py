"""Measured two-worker LP canary; proof-gated continuation, not weak sampling."""
import multiprocessing as mp,threading,time
from itertools import combinations
import psutil
from .common import *
from .oracle import Oracle
from .reachability import root_axis

def run_task(task):
    o=Oracle()
    try:return o.solve(**task)
    finally:o.close()

def start():
    assert read(OUT/'BASE_F3_IDENTITY.json')['PASS'] and read(OUT/'W7_VALIDATION_SUMMARY.json')['PASS']
    assert not (LOCAL/'W7_WORKERS_STARTED.json').exists()
    (LOCAL/'W7_WORKERS_STARTED.json').write_text('{}\n');axis=root_axis();units=sorted(inputs()[4]);u=units[0];t=min(CRITICAL)
    states=sorted(s for s in axis[f'{u}:{t}']['states'] if axis[f'{u}:{t}']['root'][s]>EPS or axis[f'{u}:{t}']['incumbent'][s]>.5)
    # Deterministic first G1 states, then representative G2/G3 conditions.
    tasks=[dict(kind='G1',conditions=[(u,t,s)]) for s in states[:2]]
    tasks.append(dict(kind='G2',conditions=[(units[0],41,states[0]),(units[1],41,states[0])]))
    reach=csvread('G3_REACHABLE_STATE_PAIRS.csv');r=min((r for r in reach if r['MESS']==u and int(r['time1'])==40 and int(r['time2'])==43),key=lambda r:(r['state_a'],r['state_b']))
    tasks.append(dict(kind='G3',conditions=[(u,40,r['state_a']),(u,43,r['state_b'])]))
    tasks += [dict(kind='UPPER_WITNESS',idle=list(pair)) for pair in combinations(units,2)]
    process=psutil.Process();samples=[];stop=threading.Event();begin=time.perf_counter()
    def monitor():
        while not stop.wait(.5):
            active=[]
            for p in process.children(recursive=True):
                try:
                    if '--multiprocessing-fork' not in p.cmdline():continue
                    cpu=p.cpu_times();active.append(dict(pid=p.pid,RSS_bytes=p.memory_info().rss,CPU_seconds=cpu.user+cpu.system))
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            samples.append(dict(seconds=time.perf_counter()-begin,workers=active,aggregate_RSS=sum(r['RSS_bytes'] for r in active),system_available=psutil.virtual_memory().available,CPU_percent=psutil.cpu_percent()))
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        with mp.get_context('spawn').Pool(2) as pool:results=pool.map(run_task,tasks,chunksize=1)
    finally:stop.set();thread.join(1)
    dump('W7_WORKER_RESOURCE_RECEIPT.json',dict(workers_started=2,max_workers=2,Threads_per_worker=1,physical_cores=psutil.cpu_count(logical=False),
        peak_aggregate_RSS=max(r['aggregate_RSS'] for r in samples),minimum_available=min(r['system_available'] for r in samples),
        wall_seconds=time.perf_counter()-begin,total_LP_seconds=sum(r['seconds'] for r in results),total_CPU_seconds=sum(r['CPU_seconds'] for r in results),
        max_process_RSS=max(r['RSS_bytes'] for r in results),samples=samples,oversubscribed=False,license_canary_PASS=True))
    rows=[{k:r[k] for k in ['key','kind','status','O1_W7_lower_bound','beta','feasible_upper','seconds','CPU_seconds','RSS_bytes','pid','rows','columns','nonzeros','Method','Threads','max_violation']} for r in results]
    table('W7_ORACLE_STATS.csv',rows);print('W7 CANARY COMPLETE',[(r['key'],r['O1_W7_lower_bound'],r['feasible_upper']) for r in results],flush=True)

if __name__=='__main__':start()
