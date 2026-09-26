"""Fresh production Actual using the validated implementation-only caches."""
import actual_worker as worker
import actual_electrical_speed as speed
from actual_speed_runner import bind
from pathlib import Path
import traceback

def run(policy,ns,authority):
    gate=worker.read(worker.BASE/'ACTUAL_SPEED_PREFLIGHT_20260922/BENCHMARK_PASS.json')
    assert gate['status']=='PASS' and gate['source_sha256']==worker.sha(Path(speed.__file__))
    assert worker.read(worker.BASE/'ACTUAL_SPEED_PREFLIGHT_20260922/CACHE_EQUIVALENCE_PASS.json')['status']=='PASS'
    runner=bind(worker,ns);speed.install();return runner(policy,ns,authority)

if __name__=='__main__':
    worker.run_policy=run
    try:worker.main()
    except BaseException as e:
        worker.H.mkdir(exist_ok=True)
        worker.save(worker.H/'FAILURE_FAST.json',dict(error=repr(e),traceback=traceback.format_exc()));raise
