"""User-authorized, serial May01 V42.2 attempts; no automatic identical retry."""
import os
for _name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[_name]='1'
import argparse
from copy import deepcopy
from contextlib import contextmanager
import gc
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
from time import time
import uuid

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.m_engine import _write,file_record
from v42_integration.a_engine import digest

DAY='2025-05-01'
CAMPAIGN=ROOT/'docs/v42_2_campaign_20261016'
REQUEST=ROOT/'docs/v42_1_freeze_20261016/USER_REQUEST.txt'
OLD=ROOT/'docs/v42_b1_structure_b2_solo_20261015/TRACK_B/MAY01_RUN01/EXECUTIONS/2025-05-01'


def read(path):return json.loads(Path(path).read_text(encoding='utf8'))


def new_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)
    return file_record(path)


def prepare_attempt(arm,number,*,reason,corrective_commit):
    from v42_integration.release_date_case import compile_date_case
    from v42_integration.table_v_flex_planning import compile_table_v_flex_context
    from v42_integration.table_v_run import prepare,ARM_STAGES
    from v42_integration.table_v_budget import SCHEMA,MAIN_CAPS,K48_CAPS
    output=CAMPAIGN/'ATTEMPTS'/arm/f'ATTEMPT{number:03d}'
    if output.exists():raise FileExistsError('ATTEMPT_ALREADY_EXISTS_NEVER_RESET_OR_OVERWRITE')
    with TemporaryDirectory(prefix='v42_2_source_binding_') as scratch:
        basic=compile_date_case(DAY,output=Path(scratch)/'BASIC',call_cap=5400.)
        context=compile_table_v_flex_context(basic,output=Path(scratch)/'FULL_FLEX',call_cap=5400.)
        m=context['manifest'];source=dict(day=DAY,source_sha=m['source_sha'],source_identity=deepcopy(m['identity']))
        del context,basic;gc.collect()
    authority=dict(authority='DIRECT_HUMAN_REQUEST_IN_THIS_CHAT',request=file_record(REQUEST),
        requested_operation='V42.2 independent fresh arm attempt from zero; preserve all previous usage and evidence',
        day=DAY,arm=arm,attempt=number,reason=reason,corrective_commit=corrective_commit,
        run_arms=[arm],Worker=1,Threads=1,P2_calls=0,R2='HOLD',unlimited_stage_budget=False)
    docs={}
    for name,kind,caps in [('PLANNING','PLANNING_NATIVE',MAIN_CAPS),('K48','K48_SEPARATE',K48_CAPS)]:
        archives=[file_record(OLD/(name+'_NATIVE_LEDGER.json'))]
        for previous in sorted((CAMPAIGN/'ATTEMPTS').glob('*/ATTEMPT*/'+name+'_NATIVE_LEDGER.json')):
            prior=read(previous)
            if prior.get('inflight') or prior.get('active_stage_context'):
                raise RuntimeError('PRIOR_ATTEMPT_REQUIRES_NATIVE_RECONCILIATION:'+str(previous))
            archives.append(file_record(previous))
        stages=[arm+':'+('K48_'+s if name=='K48' else s) for s in ARM_STAGES[arm]
                if name=='PLANNING' or s.startswith('M')]
        cycle=arm+f'_{number:03d}_'+uuid.uuid4().hex
        docs[name]=dict(schema=SCHEMA,approved=True,budget_kind=kind,authorization_id='V42_2_'+name+'_'+cycle,
            authorized_ledger_path=str((output/(name+'_NATIVE_LEDGER.json')).resolve()),
            stage_caps_seconds=caps,total_limit_seconds=None,total_limit_enabled=False,
            timeout_basis='CUMULATIVE_GUROBI_NATIVE_OPTIMIZE_PER_ARM_STAGE',P2_calls=0,Worker=1,Threads=1,
            human_approval_reference=authority,source_cases=[source],authorized_arm_stages=stages,
            fresh_native_cycle=dict(schema='TABLE_V_EXPLICIT_FRESH_NATIVE_CYCLE_V1',approved=True,
                start_native_seconds=0,human_approval_reference=authority,cycle_id=cycle,
                archived_native_ledgers=archives,reuse_previous_solution_or_bound=False))
    prepare(output,day=DAY,authorizations=docs)
    new_json(output/'V42_2_ATTEMPT_AUTHORITY.json',authority)
    return output


def launch_authority(output,arm):
    from v42_integration.table_v_launch import release_identity
    from v42_integration.table_v_campaign import _launch_gate
    m=read(output/'INPUTS/FULL_FLEX/TABLE_V_FLEX_CASE_MANIFEST.json')
    policies={DAY:digest(m['science_derivation']['policy'])}
    budgets={DAY:{n:file_record(output/(n+'_AUTHORIZATION.json')) for n in ('PLANNING','K48')}}
    plan=dict(schema='TABLE_V_FOUR_ARM_PRODUCTION_PLAN_V1',dates=[DAY],run_arms=[arm],
        execution_scope='MAY01_VALIDATION',Worker=1,Threads=1,P2_calls=0,R2='HOLD',automatic_start=False,
        actual_slots=96,execution_roots={DAY:str(output.resolve())},
        case_bindings={DAY:dict(day=DAY,source_sha=m['source_sha'],source_identity=m['identity'])},
        policy_bindings=policies,budget_authorizations=budgets,**release_identity())
    approval=dict(schema='TABLE_V_EXPLICIT_RELEASE_LAUNCH_APPROVAL_V1',approved=True,
        human_approval_reference=read(output/'V42_2_ATTEMPT_AUTHORITY.json'),approved_plan_sha=digest(plan),
        dates=[DAY],execution_scope='MAY01_VALIDATION',approved_release_sha=plan['release_sha'],
        approved_release_git_sha=plan['release_git_sha'],approved_policy_bindings_sha=digest(policies),
        approved_budget_bindings_sha=digest(budgets))
    gate=dict(launch_authorization=new_json(output/'HUMAN_LAUNCH_AUTHORIZATION.json',approval))
    new_json(output/'PRODUCTION_LAUNCH_PLAN.json',plan);new_json(output/'PRODUCTION_LAUNCH_GATE.json',gate)
    _launch_gate(plan,gate)
    return dict(plan=plan,gate=gate)


@contextmanager
def owned_campaign_lock():
    path=Path('D:/V42_2_MAY01_CAMPAIGN.lock');owner=json.dumps(dict(pid=os.getpid(),nonce=uuid.uuid4().hex)).encode()
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    try:os.write(fd,owner);os.fsync(fd)
    finally:os.close(fd)
    try:yield
    finally:
        if path.read_bytes()!=owner:raise RuntimeError('CAMPAIGN_LOCK_OWNERSHIP_DRIFT')
        path.unlink()


def run(arm,number,*,reason,corrective_commit,prepare_only=False,validation_gate=None):
    from v42_integration.table_v_run import run_arm
    from v42_integration.table_v_memory import memory_sample
    from v42_integration.table_v_control import require_running,stop_request
    from v42_integration.table_v_launch import release_identity
    if not prepare_only:
        if validation_gate is None:raise PermissionError('CURRENT_SOURCE_NATIVE0_AND_REGRESSION_GATE_REQUIRED')
        gate=read(validation_gate)
        if gate.get('PASS') is not True or gate.get('release')!=release_identity():
            raise PermissionError('CURRENT_V42_2_VALIDATION_RELEASE_REQUIRED')
        if any(file_record(r['path'])!=r for r in gate.get('evidence',[])) or len(gate.get('evidence',[]))<3:
            raise PermissionError('EXACT_B1_M_NATIVE0_AND_REGRESSION_EVIDENCE_REQUIRED')
    with owned_campaign_lock():
        require_running(CAMPAIGN)
        output=prepare_attempt(arm,number,reason=reason,corrective_commit=corrective_commit)
        if prepare_only:return dict(status='PREPARED_NO_SOLVE',output=str(output))
        authority=launch_authority(output,arm)
        state=dict(arm=arm,attempt=number,output=str(output),pid=os.getpid(),started_epoch_seconds=time(),
            status='RUNNING',validation_gate=file_record(validation_gate),Worker=1,Threads=1)
        stop=threading.Event()
        def observer():
            while not stop.is_set():
                try:
                    if (CAMPAIGN/'CAMPAIGN_STOP_REQUEST.json').exists():stop_request(output,reason='V42_2_USER_STOP')
                    _write(CAMPAIGN/'HEARTBEAT.json',dict(state,epoch_seconds=time(),memory=memory_sample()))
                except Exception:pass
                stop.wait(5.)
        thread=threading.Thread(target=observer,daemon=True);thread.start()
        _write(CAMPAIGN/'STATE.json',state)
        try:
            outcome=run_arm(arm,output,actual_slots=96,launch_authority=authority)
            state.update(status=outcome['status'],outcome=file_record(output/arm/'ARM_OUTCOME.json'),
                finished_epoch_seconds=time(),automatic_identical_retry=False,
                next_action='PRESERVE_PASS_AND_PROCEED_NEXT_ARM' if outcome['status']=='FULL_PASS' else 'ROOT_CAUSE_REPAIR_NATIVE0_THEN_NEW_ATTEMPT')
            _write(CAMPAIGN/'STATE.json',state)
            return state
        finally:
            stop.set();thread.join(timeout=2.)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm',required=True,choices=['B1','B2','B3'])
    p.add_argument('--attempt',required=True,type=int);p.add_argument('--reason',required=True)
    p.add_argument('--corrective-commit',required=True);p.add_argument('--prepare-only',action='store_true')
    p.add_argument('--validation-gate',type=Path)
    a=p.parse_args();answer=run(a.arm,a.attempt,reason=a.reason,corrective_commit=a.corrective_commit,
        prepare_only=a.prepare_only,validation_gate=a.validation_gate)
    print(json.dumps(answer,ensure_ascii=False),flush=True)
