"""Foreign processes are observed read-only. Cancellation targets own LP only."""
from .common import *
from v42_m1_accel_vnext.native_state import inspect_live
from v42_dw_continuation.resources import WindowsCounters, resource_failures
import psutil
import threading
import time

class Guard:
    def __init__(self, stage, excluded=(), foreign_policy='wait'):
        assert foreign_policy in ('wait', 'observe')
        self.foreign_policy=foreign_policy; self.foreign_seen=False
        self.stage=stage; self.excluded=excluded; self.rows=[]; self.events=[]
        self.windows=WindowsCounters(); self.done=threading.Event(); self.cancel=threading.Event()
        self.active=None; self.failures=[]; self.deadline=float('inf'); self.thread=None
        self.baseline=psutil.swap_memory().used

    def sample(self, processes=False):
        v=psutil.virtual_memory(); s=psutil.swap_memory(); now=time.perf_counter()
        rss=psutil.Process().memory_info().rss
        for pid in list(self.excluded):
            try:rss+=psutil.Process(pid).memory_info().rss
            except psutil.NoSuchProcess:pass
        row=dict(stage=self.stage, epoch=time.time(), perf=now, available_RAM=v.available,
                 pagefile_used=s.used, pagefile_delta=s.used-self.baseline,
                 RSS=rss, **self.windows.sample())
        self.rows.append(row); failures=resource_failures(row,self.rows)
        if processes:
            observed, blocked=inspect_live(self.excluded)
            self.events.append(dict(epoch=time.time(), stage=self.stage, processes=observed, confirmed_heavy=blocked))
            if blocked:
                self.foreign_seen=True
                if self.foreign_policy=='wait':failures.append('CONFIRMED_FOREIGN_NATIVE_OVERLAP')
        if now >= self.deadline-15: failures.append('CONTINUOUS_WALL_DEADLINE')
        return failures

    def gate(self):
        while True:
            failures=self.sample(True)
            write(OUT/f'{self.stage}_RESOURCE_ADMISSION.json',dict(state='WAIT_RESOURCE' if failures else 'ADMITTED',
                  events=self.events, latest=self.rows[-1], failures=failures,
                  foreign_policy=self.foreign_policy, foreign_control_calls=0))
            if not failures: return
            print('WAIT_RESOURCE',self.stage,failures,flush=True)
            time.sleep(5)

    def start(self, deadline):
        self.deadline=deadline
        def watch():
            last=0.
            while not self.done.wait(.5):
                now=time.perf_counter()
                try:
                    failures=self.sample(now-last>=2)
                    if now-last>=2:last=now
                    if failures:
                        self.failures.extend(f for f in failures if f not in self.failures)
                        self.cancel.set()
                        if self.active is not None:self.active.terminate()
                except Exception as exc:
                    self.failures.append('OBSERVATION_ERROR:'+repr(exc));self.cancel.set()
                    if self.active is not None:self.active.terminate()
        self.thread=threading.Thread(target=watch,daemon=True); self.thread.start()

    def close(self):
        self.done.set()
        if self.thread:self.thread.join()
        terminal_failures=self.sample(True)
        self.failures.extend(f for f in terminal_failures if f not in self.failures)
        if self.foreign_seen and 'CONFIRMED_FOREIGN_NATIVE_OVERLAP' not in self.failures:
            self.failures.append('CONFIRMED_FOREIGN_NATIVE_OVERLAP')
        self.windows.close()
        table(OUT/f'{self.stage}_RESOURCE_LEDGER.csv',self.rows)
        write(OUT/f'{self.stage}_PROCESS_PROOFS.json',dict(events=self.events,failures=self.failures,
              foreign_control_calls=0, foreign_policy=self.foreign_policy,
              guard_interruptions=int(self.cancel.is_set())))
        return dict(failures=self.failures,peak_RSS=max(r['RSS'] for r in self.rows),
                    min_available_RAM=min(r['available_RAM'] for r in self.rows),
                    max_commit_percent=max(r['commit_percent'] for r in self.rows if r['commit_percent'] is not None))
