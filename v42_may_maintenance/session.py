"""An OS byte lock spans the whole Codex maintenance turn, not just a check.

An abandoned guardian is released only with authoritative owner-thread terminal
evidence. There is no timer that admits an overlapping still-running turn.
"""
import argparse
from contextlib import contextmanager
from pathlib import Path
import os, subprocess, sys, threading, time, uuid
from v42_may_campaign.common import atomic, read, now, process, same_process, exclusive_lock, LockBusy, d_path


def valid(storage, token):
    storage=d_path(storage)
    value=read(storage/'ACTIVE_SESSION.json')
    if (value.get('token')!=token or value.get('status')!='ACTIVE'
            or not same_process(value.get('guardian',{}))):
        raise PermissionError('MAINTENANCE_SESSION_NOT_OWNED_OR_LIVE')
    command=value['guardian']['command']
    if 'v42_may_maintenance.session' not in command or token not in command or 'hold' not in command:
        raise PermissionError('MAINTENANCE_GUARDIAN_COMMAND_DRIFT')
    return value


def hold(storage, token, owner_thread):
    storage=d_path(storage);storage.mkdir(parents=True,exist_ok=True)
    ready=storage/'sessions'/(token+'.json')
    try:
        with exclusive_lock(storage/'MAINTENANCE.lock'):
            previous=read(storage/'ACTIVE_SESSION.json') if (storage/'ACTIVE_SESSION.json').is_file() else {}
            value=dict(status='ACTIVE',token=token,owner_thread_id=owner_thread,
                guardian=process(),started_UTC=now(),previous_token=previous.get('token'),
                no_Native_calls=True,no_expiry_while_owner_may_be_active=True)
            atomic(storage/'ACTIVE_SESSION.json',value);atomic(ready,value)
            release=storage/'sessions'/(token+'.release.json')
            while not release.is_file():
                atomic(storage/'SESSION_HEARTBEAT.json',dict(token=token,guardian=value['guardian'],UTC=now()))
                # Guardian communication polling; never a Solver delay.
                threading.Event().wait(1)
            permission=read(release)
            if permission.get('token')!=token:
                raise PermissionError('SESSION_RELEASE_TOKEN_DRIFT')
            value.update(status='RELEASED',finished_UTC=now(),release=permission)
            atomic(storage/'ACTIVE_SESSION.json',value);atomic(ready,value)
    except LockBusy:
        owner=read(storage/'ACTIVE_SESSION.json') if (storage/'ACTIVE_SESSION.json').is_file() else {}
        atomic(ready,dict(status='SKIP_PREVIOUS_MAINTENANCE_ACTIVE',token=token,owner=owner,UTC=now()))


def begin(storage, owner_thread=None):
    storage=d_path(storage);storage.mkdir(parents=True,exist_ok=True)
    token=uuid.uuid4().hex
    owner_thread=owner_thread or os.environ.get('CODEX_THREAD_ID')
    if not owner_thread:
        raise PermissionError('CODEX_OWNER_THREAD_ID_REQUIRED')
    python=Path(sys.executable).with_name('pythonw.exe')
    command=[str(python if python.exists() else Path(sys.executable)),'-B','-X','utf8',
        '-m','v42_may_maintenance.session','hold','--storage',str(storage),
        '--token',token,'--owner-thread',owner_thread]
    with (storage/'session.stdout.log').open('ab') as out,(storage/'session.stderr.log').open('ab') as err:
        child=subprocess.Popen(command,cwd=Path(__file__).resolve().parents[1],stdout=out,stderr=err,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    ready=storage/'sessions'/(token+'.json');deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        if ready.is_file():
            value=read(ready)
            if value.get('status')=='ACTIVE':valid(storage,token)
            return value
        if child.poll() is not None:
            raise RuntimeError('MAINTENANCE_GUARDIAN_EXIT_BEFORE_ADMISSION:'+str(child.returncode))
        threading.Event().wait(.05)
    raise TimeoutError('MAINTENANCE_GUARDIAN_ADMISSION_NOT_OBSERVED')


def end(storage, token, evidence=None):
    storage=d_path(storage);value=valid(storage,token)
    caller=os.environ.get('CODEX_THREAD_ID')
    if caller!=value['owner_thread_id']:
        if evidence is None:raise PermissionError('AUTHORITATIVE_PREVIOUS_OWNER_END_EVIDENCE_REQUIRED')
        proof=read(evidence)
        if (proof.get('owner_thread_id')!=value['owner_thread_id'] or
                proof.get('owner_status') not in ('idle','completed','archived') or
                proof.get('source')!='mcp__codex_app__read_thread' or not proof.get('response')):
            raise PermissionError('PREVIOUS_OWNER_STILL_RUNNING_OR_UNPROVEN')
    receipt=dict(token=token,UTC=now(),caller_thread_id=caller,
        authoritative_owner_end_evidence=str(evidence) if evidence else None,
        campaign_processes_changed=False)
    atomic(storage/'sessions'/(token+'.release.json'),receipt)
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        current=read(storage/'ACTIVE_SESSION.json')
        if current.get('token')==token and current.get('status')=='RELEASED':break
        threading.Event().wait(.05)
    return dict(status='RELEASE_REQUESTED',token=token,UTC=now())


@contextmanager
def check_lock(storage, token=None):
    if token:
        valid(storage,token)
        with exclusive_lock(d_path(storage)/'CHECK.lock'):
            yield
            valid(storage,token)
    else:
        with exclusive_lock(d_path(storage)/'MAINTENANCE.lock'):
            yield


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['begin','hold','end','validate'])
    parser.add_argument('--storage',required=True);parser.add_argument('--token');parser.add_argument('--owner-thread')
    parser.add_argument('--owner-end-evidence');args=parser.parse_args()
    if args.action=='hold':hold(args.storage,args.token,args.owner_thread);return
    result=(begin(args.storage,args.owner_thread) if args.action=='begin' else
            end(args.storage,args.token,args.owner_end_evidence) if args.action=='end' else valid(args.storage,args.token))
    import json
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
