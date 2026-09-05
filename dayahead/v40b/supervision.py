"""Task Scheduler process identity and a durable, exclusive campaign lock."""
from contextlib import contextmanager
import os,time,uuid
from .common import *
from dayahead.v39l.infrastructure import _process_rows,_parse_time,current_process_identity,identity_matches,write_exclusive_json

TOKENS=('run_v40b_campaign.py','--orchestrate')
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
