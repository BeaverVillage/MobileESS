"""Restart only the read-only HTTP monitor; preserve the running B3 worker."""
from pathlib import Path
import sys,time,json,subprocess,urllib.request,psutil
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import read,record,verify,atomic,now
from v44_recovery_r017.operations import OPS,validate

validate()
base=Path('D:/MobileESS_V43/development/monitor_partial')
out=Path('D:/MobileESS_V44/development/monitor_phi_display_20261017')
stage=Path('D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/2025-05-02/B3/attempt001/A2')
worker=psutil.Process(41800);identity=(worker.pid,worker.create_time())
assert 'v44_recovery_r017.operations' in worker.cmdline() and '--worker' in worker.cmdline()
before_cpu=sum(worker.cpu_times()[:2]);before_affinity=worker.cpu_affinity()
monitor=psutil.Process(43848);command=monitor.cmdline();directory=monitor.cwd();environment=monitor.environ()
assert command[-1]=='8795' and str(base/'monitor_binding.py') in command
assert monitor.pid!=worker.pid
atomic(out/'MONITOR_PROCESS_BEFORE.json',dict(pid=monitor.pid,created=monitor.create_time(),command=command))
monitor.terminate();monitor.wait(timeout=10)
with (base/'phi_display.stdout.log').open('ab') as stdout,(base/'phi_display.stderr.log').open('ab') as stderr:
    process=subprocess.Popen(command,cwd=directory,env=environment,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
status=None
for _ in range(40):
    if process.poll() is not None:raise RuntimeError('MONITOR_EXITED:'+str(process.returncode))
    try:
        with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=3) as response:status=json.load(response)
        if status.get('build',{}).get('detail'):break
    except (OSError,ValueError):pass
    time.sleep(.25)
assert status is not None,'MONITOR_NOT_READY'
detail=status['build']['detail']
line=next(line for line in detail.splitlines() if line.startswith('인공변수:'))
assert '/' not in line and ('Φ≈' in line or '0 검증 PASS' in line)
assert (worker.pid,worker.create_time())==identity and worker.is_running()
assert worker.cpu_affinity()==before_affinity
trace=read(stage/'OUTPUT/PHASE_I_TRACE.json');last=trace['trajectory'][-1]
sys.path.insert(0,str(base));from a_stage_details import phi_display
if '0 검증 PASS' not in line:
    assert 'Φ≈'+phi_display(last['exact_Phi']) in line
validate()
atomic(out/'LIVE_AFTER.json',status)
receipt=dict(UTC=now(),PASS=True,URL='http://127.0.0.1:8795/',
    monitor_new_pid=process.pid,previous_monitor_pid=monitor.pid,only_monitor_restarted=True,
    sources=[record(base/'a_stage_details.py'),record(base/'monitor_binding.py')],
    previous_source=record(base/'backups/phi_display_20261017/a_stage_details.py'),
    tests_PASS=12,regressions=record(out/'REGRESSIONS.xml'),displayed_line=line,
    original_exact_Phi=last['exact_Phi'],raw_trace=record(stage/'OUTPUT/PHASE_I_TRACE.json'),
    scientific_source_modified=False,Native_ledgers_modified=False,worker_interrupted=False,
    worker=dict(pid=worker.pid,created=worker.create_time(),CPU_delta_seconds=sum(worker.cpu_times()[:2])-before_cpu,
        affinity=worker.cpu_affinity()),
    phase_I_zero_assertion_relaxed=False,raw_fraction_preserved=True,whole_campaign_PASS_claimed=False)
atomic(OPS/'MONITOR_PHI_DISPLAY_FIX_20261017.json',receipt)
atomic(out/'RESULT.json',receipt)
print(dict(PASS=True,monitor_pid=process.pid,worker_pid=worker.pid,displayed_line=line))
