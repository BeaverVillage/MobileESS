"""Foreign processes are observed read-only. Cancellation targets own LP only."""
from .common import *
from .native_state import inspect_live
from v42_dw_continuation.resources import WindowsCounters, resource_failures
import psutil
import threading
import time

class Guard:
    def __init__(self, stage, excluded=()):
        self.stage=stage; self.excluded=excluded; self.rows=[]; self.events=[]
        self.windows=WindowsCounters(); self.done=threading.Event(); self.cancel=threading.Event()
        self.active=None; self.failures=[]; self.deadline=float('inf'); self.thread=None
        self.baseline=psutil.swap_memory().used

    def sample(self, processes=False):
        v=psutil.virtual_memory(); s=psutil.swap_memory(); now=time.perf_counter()
        row=dict(stage=self.stage, epoch=time.time(), perf=now, available_RAM=v.available,
                 pagefile_used=s.used, pagefile_delta=s.used-self.baseline,
                 RSS=psutil.Process().memory_info().rss, **self.windows.sample())
        self.rows.append(row); failures=resource_failures(row,self.rows)
        if processes:
            observed, blocked=inspect_live(self.excluded)
            self.events.append(dict(epoch=time.time(), stage=self.stage, processes=observed, confirmed_heavy=blocked))
            if blocked: failures.append('CONFIRMED_FOREIGN_NATIVE_OVERLAP')
        if now >= self.deadline-15: failures.append('CONTINUOUS_WALL_DEADLINE')
        return failures

    def gate(self):
        while True:
            failures=self.sample(True)
            write(OUT/f'{self.stage}_RESOURCE_ADMISSION.json',dict(state='WAIT_RESOURCE' if failures else 'ADMITTED',
                  events=self.events, latest=self.rows[-1], failures=failures, foreign_control_calls=0))
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
        self.sample(True); self.windows.close()
        table(OUT/f'{self.stage}_RESOURCE_LEDGER.csv',self.rows)
        write(OUT/f'{self.stage}_PROCESS_PROOFS.json',dict(events=self.events,failures=self.failures,
              foreign_control_calls=0, guard_interruptions=int(bool(self.failures))))
        return dict(failures=self.failures,peak_RSS=max(r['RSS'] for r in self.rows),
                    min_available_RAM=min(r['available_RAM'] for r in self.rows),
                    max_commit_percent=max(r['commit_percent'] for r in self.rows if r['commit_percent'] is not None))
