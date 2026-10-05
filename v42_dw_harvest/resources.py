"""Other lanes are observed only. Runtime cancellation touches owned calls."""
from .common import *
from datetime import datetime,timezone
import threading,time,psutil
from v42_dw_continuation.resources import WindowsCounters,resource_failures
from .native_state import inspect_live


class Monitor:
    def __init__(self,owned,evidence_dir=None):
        self.owned=owned;self.rows=[];self.phase='BUILD';self.failures=[]
        self.cancel=threading.Event();self.done=threading.Event();self.active=None
        self.budget_used=None
        self.evidence_dir=evidence_dir
        self.process_events=[];self.last_process_probe=0.;self.last_process_rows=[];self.last_blocked=[]
        self.deadline=float(os.environ.get('V42_DW_PAIR_DEADLINE_PERF','inf'))
        self.lock=threading.Lock()
        self.process_lock=threading.Lock()
        self.windows=WindowsCounters();self.thread=threading.Thread(target=self.watch,daemon=True)
        self.thread.start()

    def sample(self):
        with self.lock:return self._sample()

    def _sample(self):
        vm=psutil.virtual_memory();rss=0
        for pid in [os.getpid(),*list(self.owned)]:
            try:rss+=psutil.Process(pid).memory_info().rss
            except psutil.NoSuchProcess:pass
        r=dict(UTC=datetime.now(timezone.utc).isoformat(),perf=time.perf_counter(),phase=self.phase,
               available_RAM=vm.available,total_tree_RSS=rss,pagefile_used=psutil.swap_memory().used,**self.windows.sample())
        self.rows.append(r)
        return r

    def watch(self):
        while not self.done.wait(.5):
            try:
                r=self.sample();problems=resource_failures(r,self.rows)
                if time.perf_counter()>=self.deadline-20:
                    problems.append('CONTINUOUS_PAIR_WALL_RESERVE_STOP')
                if self.phase in ('PRICING','RMP'):
                    if self.budget_used is not None and self.budget_used()>=295:
                        problems.append('LEG_NATIVE_BUDGET_RESERVE_STOP')
                    _,blocked=self.process_probe()
                    if blocked:problems.append('CONFIRMED_FOREIGN_NATIVE_SOLVE')
                    if problems:
                        self.failures.extend(problems);self.cancel.set()
                        if self.active is not None:self.active.terminate()
            except Exception as e:
                self.failures.append('TELEMETRY_ERROR:'+repr(e));self.cancel.set()
                if self.active is not None:self.active.terminate()

    def gate(self,label):
        self.phase='WAIT_RESOURCE';last=0
        while True:
            if time.perf_counter()>=self.deadline-20:
                raise TimeoutError('CONTINUOUS_PAIR_WALL_RESERVE_STOP')
            r=self.sample();rows,blocked=self.process_probe(force=True);problems=resource_failures(r,self.rows)
            if not blocked and not problems:
                self.phase='BUILD';self.cancel.clear()
                return dict(label=label,UTC=r['UTC'],available_RAM=r['available_RAM'],commit_percent=r['commit_percent'],processes=rows,blocked=[],PASS=True)
            if time.perf_counter()-last>=30:
                print('WAIT_RESOURCE',label,len(blocked),problems,flush=True);last=time.perf_counter()
            time.sleep(2)

    def process_probe(self,force=False):
        with self.process_lock:
            return self._process_probe(force)

    def _process_probe(self,force=False):
        if force or time.perf_counter()-self.last_process_probe>=2:
            rows,blocked=inspect_live(self.owned)
            self.last_process_probe=time.perf_counter()
            self.last_process_rows=rows;self.last_blocked=blocked
            event=dict(UTC=datetime.now(timezone.utc).isoformat(),phase=self.phase,
                       processes=rows,confirmed_foreign_native=blocked,
                       other_lane_control_calls=0)
            self.process_events.append(event)
            if self.evidence_dir is not None:
                write(self.evidence_dir/'PROCESS_OPTIMIZE_STATE.json',dict(events=self.process_events))
        return self.last_process_rows,self.last_blocked

    def close(self):
        self.done.set();self.thread.join();self.sample();self.windows.close()

    def summary(self):
        return dict(sampled_peak_tree_RSS_GiB=max(r['total_tree_RSS'] for r in self.rows)/1024**3,
                    min_available_RAM_GiB=min(r['available_RAM'] for r in self.rows)/1024**3,
                    max_commit_percent=max(r['commit_percent'] for r in self.rows if r['commit_percent'] is not None),
                    guard_failures=sorted(set(self.failures)),samples=len(self.rows),sampled_not_exact_peaks=True,
                    confirmed_foreign_native_events=sum(bool(e['confirmed_foreign_native']) for e in self.process_events),
                    other_lane_kill_calls=0,other_lane_terminate_calls=0)
