from pathlib import Path
import sys,subprocess,psutil,json,time,urllib.request
sys.path.insert(0,'D:/v44_may01_07_prepare_20261016')
from v44.common import atomic,record,now
from v44_recovery_r017.operations import OPS
monitor=psutil.Process(55724);cmd=monitor.cmdline();cwd=monitor.cwd();env=monitor.environ()
assert cmd[-1]=='8795' and 'D:\\MobileESS_V43\\development\\monitor_partial\\monitor_binding.py' in cmd
monitor.terminate();monitor.wait(timeout=10)
folder=Path(cwd)
with (folder/'checkpoint_resume.stdout.log').open('ab') as stdout,(folder/'checkpoint_resume.stderr.log').open('ab') as stderr:
    process=subprocess.Popen(cmd,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
for _ in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8795/api/status',timeout=3) as response:value=json.load(response)
        break
    except OSError:time.sleep(.2)
else:raise RuntimeError('MONITOR_NOT_READY')
atomic(OPS/'MONITOR_A2_CHECKPOINT_DISPLAY_20261017.json',dict(UTC=now(),PASS=True,monitor_pid=process.pid,
    only_monitor_restarted=True,scientific_source_or_Native_ledger_modified=False,
    source=record(folder/'a_stage_details.py'),regressions=record('D:/MobileESS_V44/development/r018_monitor_regressions.xml'),
    display_policy='Show cumulative previous-run wall and inherited Native seconds explicitly when ledger.checkpoint_resume is true.'))
print(dict(PASS=True,monitor_pid=process.pid))
