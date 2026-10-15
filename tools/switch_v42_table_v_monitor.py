"""User-requested localhost dashboard switch; preserve predecessor bytes."""
from datetime import datetime,timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
import psutil

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import file_record,_write
SOURCE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/EXECUTION01'

def main():
    # Stage and test the replacement before the only service mutation.
    with urlopen('http://127.0.0.1:8794/api/state',timeout=5) as r:ready=json.load(r)
    if ready.get('schema')!='TABLE_V_LOCAL_READ_ONLY_MONITOR_V1' or ready.get('order')!=['B0','B1','B2','B3']:
        raise ValueError('NEW_TABLE_V_MONITOR_NOT_READY')
    old=psutil.Process(35740);command=old.cmdline()
    expected=Path('D:/v42_may_joint_repair_campaign_20261013/MONITOR_ADAPTER.py').resolve()
    if not (len(command)>=2 and Path(command[-2]).resolve()==expected and command[-1]=='serve'):
        raise ValueError('EXACT_PREDECESSOR_MONITOR_PROCESS_REQUIRED')
    if not any(c.status=='LISTEN' and c.laddr.ip=='127.0.0.1' and c.laddr.port==8793 for c in old.net_connections()):
        raise ValueError('EXACT_8793_LOCALHOST_OWNER_REQUIRED')
    backup=SOURCE/'MONITOR_SWITCH01'
    backup.mkdir(parents=True,exist_ok=False)
    for url,name in [('http://127.0.0.1:8793/','PREVIOUS_SCREEN.html'),
                     ('http://127.0.0.1:8793/api/state','PREVIOUS_API_STATE.json')]:
        with urlopen(url,timeout=10) as r:(backup/name).write_bytes(r.read())
    predecessor=dict(pid=old.pid,command=command,source=file_record(expected),
        saved_screen=file_record(backup/'PREVIOUS_SCREEN.html'),saved_state=file_record(backup/'PREVIOUS_API_STATE.json'))
    _write(backup/'PREDECESSOR.json',predecessor)
    old.terminate();old.wait(timeout=10)
    log=(backup/'TABLE_V_MONITOR.log').open('ab')
    worker=subprocess.Popen([sys.executable,'-u',str(ROOT/'tools/serve_v42_table_v_monitor.py'),
        '--port','8793','--source',str(SOURCE)],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    _write(backup/'NEW_MONITOR_PROCESS.json',dict(pid=worker.pid,port=8793,read_only=True,hidden=True))
    status=None
    for _ in range(50):
        try:
            with urlopen('http://127.0.0.1:8793/api/state',timeout=1) as r:status=json.load(r)
            if status.get('schema')=='TABLE_V_LOCAL_READ_ONLY_MONITOR_V1':break
        except Exception:pass
        time.sleep(.2)
    if not status or status.get('schema')!='TABLE_V_LOCAL_READ_ONLY_MONITOR_V1':
        if worker.poll() is None:worker.terminate();worker.wait(timeout=10)
        restored=subprocess.Popen(command,cwd=expected.parent,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        _write(backup/'SWITCH_FAILED_RESTORED.json',dict(restored_pid=restored.pid))
        raise RuntimeError('MONITOR_SWITCH_FAILED_PREDECESSOR_RESTORED')
    if file_record(expected)!=predecessor['source']:raise ValueError('PREDECESSOR_SOURCE_CHANGED')
    _write(backup/'SWITCH_RECEIPT.json',dict(status='PASS',new_PID=worker.pid,url='http://127.0.0.1:8793/',
        UTC=datetime.now(timezone.utc).isoformat(),predecessor=predecessor,
        predecessor_Source_and_Raw_preserved=True,Native_processes_touched=0,
        source=str(SOURCE),order=status['order'],Actual_phase_line_comparison_table=True))
    print(json.dumps(dict(status='PASS',PID=worker.pid,url='http://127.0.0.1:8793/')),flush=True)

if __name__=='__main__':main()
