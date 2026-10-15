"""Reload only the owned Table V monitor, never a simulation worker."""
import json
import argparse
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
import psutil

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
SOURCE=ROOT/'docs/v42_unified_aidc_mess_research_20261014/RELEASE_RECOVERY_20261015/RC04/TABLE_V/EXECUTION01'

def main(new_source=None):
    tool=ROOT/'tools/serve_v42_table_v_monitor.py'
    pids={r.pid for r in psutil.net_connections(kind='tcp') if r.status=='LISTEN' and r.laddr.port==8793}
    owned=[]
    for pid in pids:
        candidate=psutil.Process(pid)
        if any(Path(x).resolve()==tool.resolve() for x in candidate.cmdline() if x.endswith('.py')):owned.append(candidate)
    if len(owned)!=1 or len(pids)!=1:raise ValueError('ONE_EXCLUSIVE_OWNED_TABLE_V_MONITOR_REQUIRED')
    old=owned[0];cmd=old.cmdline()
    if not any(Path(x).resolve()==tool.resolve() for x in cmd if x.endswith('.py')):
        raise ValueError('EXACT_TABLE_V_MONITOR_PROCESS_REQUIRED')
    if '--port' not in cmd or cmd[cmd.index('--port')+1]!='8793':raise ValueError('PORT_8793_MONITOR_ONLY')
    parent=SOURCE/'MONITOR_SWITCH01'
    number=1
    while (parent/('SOURCE_RELOAD_'+str(number).zfill(2))).exists():number+=1
    backup=parent/('SOURCE_RELOAD_'+str(number).zfill(2));backup.mkdir(exist_ok=False)
    (backup/tool.name).write_bytes(tool.read_bytes())
    with urlopen('http://127.0.0.1:8793/api/state',timeout=5) as r:(backup/'PREVIOUS_LIVE_STATE.json').write_bytes(r.read())
    old.terminate();old.wait(timeout=10)
    if new_source is not None:
        new_source=Path(new_source).resolve()
        if not (new_source/'MAY01_TABLE_V_FOUR_ARM_CONTRACT.json').is_file():raise ValueError('PREPARED_TABLE_V_CASE_REQUIRED')
        cmd[cmd.index('--source')+1]=str(new_source)
    with (backup/'MONITOR.log').open('ab') as log:
        worker=subprocess.Popen(cmd,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(50):
        try:
            with urlopen('http://127.0.0.1:8793/api/state',timeout=1) as r:state=json.load(r)
            if state.get('schema')=='TABLE_V_LOCAL_READ_ONLY_MONITOR_V1':break
        except Exception:pass
        time.sleep(.2)
    else:raise RuntimeError('TABLE_V_MONITOR_RELOAD_FAILED')
    result=dict(status='PASS',pid=worker.pid,previous_pid=old.pid,source=file_record(tool),
        immutable_source=file_record(backup/tool.name),Native_workers_touched=0,url='http://127.0.0.1:8793/')
    _write(backup/'RELOAD_RECEIPT.json',result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=None)
    main(p.parse_args().source)
