"""Replace only controller; keep every active scientific process alive."""
from mission_health import *
state=read(RUN/'campaign_progress.json');p=psutil.Process(state['supervisor_pid'])
assert 'v41r4_search_detached.py' in ' '.join(p.cmdline())
assert read(OUT/'TERMINAL_A1_RELEASE.json')['status']=='PASS'
p.suspend()
try:
    state=read(RUN/'campaign_progress.json')
    children=p.children()
    assert {c.pid for c in children}=={r['worker_pid'] for r in state['active']},'WAIT_FOR_STABLE_PHASE_BOUNDARY'
    for r in state['active']:
        child=psutil.Process(r['worker_pid']);assert r['phase']=='B1_DA' and r['day'] in child.cmdline()
    write(OUT/'SUPERVISOR_TAKEOVER.json',dict(**state,reason='Independent failure containment and terminal A1 dispatch; active B1 workers adopted unchanged',takeover_at=time.time(),prior_controller_cmd=p.cmdline()))
    p.terminate();p.wait(15)
    assert all(c.is_running() for c in children)
except BaseException:
    if p.is_running():p.resume()
    raise
print('CONTROLLER_ONLY_REPLACED_WORKERS_PRESERVED', [c.pid for c in children])
