from .common import *
import psutil,threading
def inspect(label):
    # Read-only admission check. No process termination or RAM-triggered
    # termination is installed in the native solver.
    own=psutil.Process();excluded={own.pid,*[p.pid for p in own.parents()]};allp=[]
    for p in psutil.process_iter(['pid','name','cmdline','create_time']):
        try:
            if p.pid in excluded:continue
            text=' '.join(p.info['cmdline'] or []);name=(p.info['name'] or '').lower()
            if any(k in name for k in ('python','gurobi','wsl','ssh')) or ('may12' in text.lower() and '--' in text):
                allp.append((p,p.cpu_times().user+p.cpu_times().system,text,p.memory_info().rss))
        except (psutil.AccessDenied,psutil.NoSuchProcess):pass
    cpu0=psutil.cpu_times();time0=time.perf_counter();threading.Event().wait(2.0);dt=time.perf_counter()-time0;processes=[]
    for p,start,text,rss in allp:
        try:
            delta=max(0.,p.cpu_times().user+p.cpu_times().system-start);active_native=(('python' in p.name().lower() or 'gurobi' in p.name().lower()) and delta/dt>.25 and ' host monitor ' not in text)
            try:cwd=p.cwd()
            except psutil.Error:cwd=None
            processes.append(dict(pid=p.pid,creation_epoch=p.create_time(),name=p.name(),command=text,cwd=cwd,RSS=p.memory_info().rss,cpu_seconds_delta=delta,cpu_one_core_fraction=delta/dt,active_native=active_native,protected=True))
        except (psutil.AccessDenied,psutil.NoSuchProcess):pass
    cpu1=psutil.cpu_times();total_delta=sum(cpu1)-sum(cpu0);idle_delta=cpu1.idle-cpu0.idle;busy=1-idle_delta/total_delta if total_delta else None;vm=psutil.virtual_memory()
    expected_peak=2206081024;conflict=bool(busy is not None and busy>.85)
    # Unknown active solver workers are deferred even if current headroom is
    # large: preserve other scientific runs and avoid attributing overlap.
    conflict=conflict or any(x['active_native'] for x in processes)
    snapshot=dict(label=label,wall_sample_seconds=dt,processes=processes,system_memory=vm._asdict(),system_busy_fraction=busy,expected_previous_peak_RSS=expected_peak,admission_policy='Defer for overlapping active native workers or system CPU >85%; RAM is observed only',RAM_based_admission=False,resource_conflict_expected=conflict,admission_PASS=not conflict,other_processes_modified=False,May12_or_A_stage_stopped=False,MemLimit_added=False,SoftMemLimit_added=False,RAM_based_solver_termination_added=False)
    path=REPORTS/'RESOURCE_ISOLATION_AUDIT.json';ledger=read(path) if path.exists() else dict(snapshots=[]);ledger['snapshots'].append(snapshot);ledger['admission_PASS']=not conflict;write(path,ledger);return snapshot
class Monitor:
    def __init__(self):self.stop=threading.Event();self.start=time.perf_counter();self.samples=[];self.thread=threading.Thread(target=self.run,daemon=True)
    def run(self):
        proc=psutil.Process()
        while not self.stop.wait(.25):self.samples.append(dict(wall=time.perf_counter()-self.start,RSS=proc.memory_info().rss,system_available=psutil.virtual_memory().available))
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):self.stop.set();self.thread.join();self.samples.append(dict(wall=time.perf_counter()-self.start,RSS=psutil.Process().memory_info().rss,system_available=psutil.virtual_memory().available));table(WORK/'logs/RESOURCE_TELEMETRY.csv',self.samples)
    @property
    def peak(self):return max((s['RSS'] for s in self.samples),default=0)
