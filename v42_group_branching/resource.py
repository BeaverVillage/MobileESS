from .common import *
import psutil,threading

def inspect(label,owned=()):
    own=psutil.Process();excluded={own.pid,*owned,*[p.pid for p in own.parents()]};first=[]
    for p in psutil.process_iter(['pid','name','cmdline','create_time']):
        try:
            if p.pid in excluded or not any(k in (p.info['name'] or '').lower() for k in ('python','gurobi','wsl','ssh')):continue
            first.append((p,p.cpu_times().user+p.cpu_times().system))
        except psutil.Error:pass
    baseline=psutil.cpu_times();begin=time.perf_counter();threading.Event().wait(2);dt=time.perf_counter()-begin;records=[]
    for p,cpu in first:
        try:
            text=' '.join(p.cmdline());fraction=max(0.,p.cpu_times().user+p.cpu_times().system-cpu)/dt
            idle_monitor='.host monitor ' in text
            static=any(s in text for s in ('verify_stay_batch','v42_group_branching.mapping','v42_group_branching.repair'))
            known_solver=('gurobi' in p.name().lower() or any(s in text for s in ('.runner ','.root ','.canary ','.benchmark ','.worker ')))
            native=False if idle_monitor or static else True if known_solver and fraction>.25 else None
            unknown_active=not idle_monitor and not static and not known_solver and fraction>.25
            records.append(dict(pid=p.pid,creation_epoch=p.create_time(),executable=p.exe(),command=text,cwd=p.cwd(),
                CPU_one_core_fraction=fraction,RSS=p.memory_info().rss,actual_native_solver=native,
                classification='IDLE_MONITOR' if idle_monitor else 'KNOWN_READONLY_VERIFICATION' if static else 'SOLVER_ENTRY_POINT' if known_solver else 'UNCONFIRMED',
                active_unconfirmed_worker=unknown_active,owned_by_this_pilot=False,modified=False))
        except psutil.Error:pass
    end=psutil.cpu_times();total=sum(end)-sum(baseline);busy=1-(end.idle-baseline.idle)/total if total else 0
    # Presence alone does not prove resource isolation impossible. Keep other
    # workloads intact; admit two single-thread workers only with CPU headroom.
    conflict=busy>.85 or any(r['active_unconfirmed_worker'] for r in records)
    snapshot=dict(label=label,admission_PASS=not conflict,processes=records,owned_worker_PIDs=list(owned),
        system_busy_fraction=busy,system_memory_observation=psutil.virtual_memory()._asdict(),
        RAM_based_admission=False,other_processes_modified=False,MemLimit_added=False,SoftMemLimit_added=False,
        admission_policy='CPU busy <= 85%; independently owned Threads=1 workers; other known native tasks observed and untouched',
        other_native_tasks_present=any(r['actual_native_solver'] is True for r in records),
        actual_CPU_activity_not_automatically_native=True,controller_sample_seconds=dt)
    path=REPORTS/'PROCESS_ISOLATION_AUDIT.json';ledger=read(path) if path.exists() else dict(snapshots=[])
    ledger['snapshots'].append(snapshot);ledger['admission_PASS']=snapshot['admission_PASS'];write(path,ledger)
    return snapshot
