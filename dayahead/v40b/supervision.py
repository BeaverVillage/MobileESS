"""Task Scheduler process identity and a durable, exclusive campaign lock."""
from contextlib import contextmanager
from datetime import datetime, timezone
import os,subprocess,time,uuid
from .common import *
from dayahead.v39l.infrastructure import _parse_time,identity_matches,write_exclusive_json

TOKENS=('run_v40b_campaign.py','--orchestrate')


def _process_rows():
    """Enumerate V40B process identities without the blocking Windows CIM API."""
    import psutil

    rows=[]
    attributes=('pid','ppid','create_time','name','exe','cmdline')
    for process in psutil.process_iter(attributes,ad_value=None):
        info=process.info
        created=info.get('create_time')
        command=[str(value) for value in (info.get('cmdline') or [])]
        rows.append({
            'ProcessId':int(info.get('pid') or 0),
            'ParentProcessId':int(info.get('ppid') or 0),
            'CreationDate':datetime.fromtimestamp(float(created),tz=timezone.utc).isoformat() if created is not None else None,
            'Name':info.get('name'),
            'ExecutablePath':info.get('exe'),
            'CommandLine':subprocess.list2cmdline(command) if command else None,
        })
    return rows


def current_process_identity():
    pid=os.getpid()
    row=next((item for item in _process_rows() if int(item.get('ProcessId') or 0)==pid),None)
    if row is None:raise RuntimeError(f'V40B_CURRENT_PROCESS_NOT_FOUND:{pid}')
    return {
        'pid':pid,
        'parent_pid':int(row.get('ParentProcessId') or 0),
        'creation_time_utc':_parse_time(str(row['CreationDate'])).isoformat(),
        'name':row.get('Name'),
        'executable_path':row.get('ExecutablePath'),
        'command_line':row.get('CommandLine'),
    }


def inventory(rows=None):
    result={'orchestrators':[],'workers':[]}
    for row in (_process_rows() if rows is None else rows):
        cmd=str(row.get('CommandLine') or '')
        if str(row.get('Name','')).lower() not in ('python.exe','pythonw.exe'):continue
        if 'run_v40b_campaign.py' not in cmd:continue
        value={'pid':int(row['ProcessId']),'parent_pid':int(row['ParentProcessId']),
           'creation_time_utc':_parse_time(str(row['CreationDate'])).isoformat(),'command_line':cmd}
        if '--orchestrate' in cmd:result['orchestrators'].append(value)
        elif '--day' in cmd:
            value['day']=next((d for d in DAYS if d in cmd),None);result['workers'].append(value)
    return result

def reject_duplicates(records,own_pid):
    others=[r for r in records['orchestrators'] if r['pid']!=own_pid]
    days=[r['day'] for r in records['workers']]
    if others or len(days)!=len(set(days)):raise RuntimeError('DUPLICATE_ORCHESTRATOR_OR_DAY')

@contextmanager
def instance():
    lock=ROOT/'CAMPAIGN_INSTANCE.json';identity=current_process_identity();identity['command_match_tokens']=list(TOKENS)
    records=inventory();reject_duplicates(records,os.getpid())
    if records['workers']:raise RuntimeError('EXISTING_WORKERS_REQUIRE_EXPLICIT_RECOVERY')
    if lock.exists():
        previous=read(lock)
        if any(identity_matches(previous,r) for r in records['orchestrators']):raise RuntimeError('LIVE_INSTANCE_LOCK')
        lock.rename(ROOT/f'STALE_INSTANCE_{time.time_ns()}.json')
    payload={**identity,'token':uuid.uuid4().hex}
    write_exclusive_json(lock,payload)
    try:yield payload
    finally:
        if lock.exists() and read(lock).get('token')==payload['token']:lock.unlink()

def verify_freeze():
    method=read(ROOT/'V40B_V40A_METHOD_FREEZE.json');execution=read(ROOT/'V40B_EXECUTION_FREEZE.json')
    if method['status']!='PASS' or digest(method['identity'])!=method['method_SHA']:raise RuntimeError('METHOD_SHA_INVALID')
    if audit(REPO,method['identity']['V40A_source_files'])['status']!='PASS':raise RuntimeError('METHOD_SOURCE_DRIFT')
    if audit(REPO,execution['source_files'])['status']!='PASS' or digest(execution['identity'])!=execution['execution_SHA']:raise RuntimeError('EXECUTION_SOURCE_DRIFT')
    for name,expected in execution['input_files'].items():
        if sha(REPO/name)!=expected:raise RuntimeError('FROZEN_INPUT_DRIFT:'+name)
    return method,execution

def launch_gate():
    method,execution=verify_freeze()
    auth=read(ROOT/'V40B_REUSE_AUTHORIZATION.json');tests=read(ROOT/'V40B_TEST_REPORT.json')
    if auth['status']!='PASS' or not all(auth['approved'].values()) or auth['OLD_B3_REUSE_APPROVED']:raise RuntimeError('REUSE_GATE')
    if tests['status']!='PASS':raise RuntimeError('TEST_GATE')
    if read(ROOT/'V40B_PRESERVATION_RECHECK.json')['status']!='PASS':raise RuntimeError('PRESERVATION_GATE')
    rows=read(ROOT/'V40B_MAY_EXECUTION_MATRIX.json')['rows']
    if len(rows)!=124 or {(r['day'],r['case']) for r in rows}!={(d,c) for d in DAYS for c in CASES}:raise RuntimeError('MATRIX_INCOMPLETE')
    if any(r['status']!='RUN_REQUIRED' for r in rows if r['case']=='B3'):raise RuntimeError('OLD_B3_SELECTED_OR_ALREADY_EXECUTED')
    return method,execution
