"""Fail-closed V2_add stage scheduler. Default is plan/hold, never a campaign."""
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone
import json,os
from .prestart import ROOT,OUT,RUN,read,put,record,digest,SOURCE
from v44.stages import CHAINS

def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    os.replace(tmp,path)

@contextmanager
def owned_lock(root):
    import msvcrt
    root=Path(root);root.mkdir(parents=True,exist_ok=True);p=root/'V2_ADD_PRESTART.lock'
    # OS releases a byte-range lock after a crash; stale filename is harmless.
    f=p.open('a+b');f.seek(0,2)
    if f.tell()==0:f.write(b'0');f.flush()
    f.seek(0)
    try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:f.close();raise RuntimeError('DUPLICATE_V2_ADD_WORKER')
    try:yield
    finally:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1);f.close()

def binding(day,input_sha,scenario_sha,source_sha,acceptance_sha):
    return dict(day=day,input_sha=input_sha,scenario_sha=scenario_sha,source_sha=source_sha,acceptance_sha=acceptance_sha)

def require_reuse(a1,expected):
    if a1.get('binding')!=expected or not a1.get('acceptance_sha') or a1.get('acceptance_sha')!=expected['acceptance_sha']:
        raise ValueError('A1_REUSE_DATE_INPUT_SCENARIO_SOURCE_ACCEPTANCE_MISMATCH')
    if a1.get('FULL_feasible') is not True:raise ValueError('A1_REUSE_ORIGINAL_FULL_REQUIRED')
    return a1

def validate_stage_result(stage,result,identity):
    """Production admission keeps original A/M proofs and physical120 scope."""
    from v44.stages import m_outcome,require_a2
    if result.get('identity')!=identity:raise ValueError('REAL_STAGE_CASE_IDENTITY_REQUIRED')
    if stage in ('A1','A2','A1_REUSE'):
        if (result.get('FULL_feasible') is not True or result.get('independent_Global_LB_validated') is not True
            or not 0<=result.get('certified_gap',1)<=.005 or not result.get('acceptance_sha')):
            raise ValueError('ORIGINAL_FULL_A_ACCEPTANCE_REQUIRED')
        if stage=='A2':require_a2(result,identity['day'])
    elif stage in ('M1','M2'):
        if not m_outcome(result)['allow_downstream']:raise ValueError('ORIGINAL_FULL_M_ACCEPTANCE_REQUIRED')
    elif stage.startswith('K48_'):
        if result.get('LB_origin')!='K48_INDEPENDENT_GLOBAL' or result.get('independent_Global_LB_validated') is not True:
            raise ValueError('ORIGINAL_FULL_K48_LB_REQUIRED')
    elif stage in ('ACTUAL','FRESH'):
        if result.get('full120_security_PASS') is not True or result.get('original_FULL_Job_PASS') is not True:
            raise ValueError('ALL120_TIME_AND_FULL_JOB_REQUIRED')
        if stage=='FRESH' and result.get('independent_new_engine') is not True:raise ValueError('INDEPENDENT_FRESH_ENGINE_REQUIRED')

class Scheduler:
    """Handlers are explicit real stage adapters, not silently imported workers.

    Checkpoints bind complete artifacts and measured stage budgets. Restarting
    never imports another date's incumbent or resets charged Native seconds.
    """
    def __init__(self,root,handlers,identity,budgets,*,diagnostic_fixture=False):
        self.root=Path(root);self.handlers=handlers;self.identity=identity;self.budgets=budgets
        self.diagnostic_fixture=diagnostic_fixture

    def case(self,day,arm):
        chain=CHAINS[arm];context={};folder=self.root/day/arm
        if day not in self.identity:raise ValueError('UNFROZEN_DATE')
        for stage in chain:
            p=folder/(stage+'.checkpoint.json');identity=dict(self.identity[day],day=day,arm=arm,stage=stage)
            old=read(p) if p.exists() else None
            used=0.
            if old:
                if old['identity']!=identity:raise ValueError('CHECKPOINT_IDENTITY_DRIFT')
                if any(record(v['path'])!=v for v in old['artifacts']):raise ValueError('CHECKPOINT_ARTIFACT_DRIFT')
                used=old['Native_seconds']
                if old['status']=='COMPLETE':
                    if old.get('result_sha')!=digest(old['result']):raise ValueError('CHECKPOINT_RESULT_SHA_DRIFT')
                    if not self.diagnostic_fixture:validate_stage_result(stage,old['result'],identity)
                    context[stage]=old['result'];continue
                if old['status']!='LEDGER_RECONCILED_RETRY_ALLOWED':raise ValueError('INFLIGHT_OR_FAILED_NATIVE_RECONCILIATION_REQUIRED_NO_BUDGET_RESET')
            ceiling=self.budgets.get(stage,0.)
            if used>ceiling:raise ValueError('NATIVE_BUDGET_EXHAUSTED')
            checkpoint=dict(identity=identity,status='RUNNING',Native_seconds=used,artifacts=[],result=None)
            atomic(p,checkpoint)
            try:
                if stage not in self.handlers:raise RuntimeError('REAL_STAGE_ADAPTER_NOT_BOUND:'+stage)
                result=self.handlers[stage](dict(identity=identity,parents=context,remaining_Native_seconds=ceiling-used,
                    charged_Native_seconds=used,source_SHA=SOURCE))
                if result.get('PASS') is not True:raise ValueError('STAGE_NOT_ACCEPTED')
                if not self.diagnostic_fixture:validate_stage_result(stage,result,identity)
                charged=float(result.get('Native_seconds',0))
                if charged<0 or used+charged>ceiling:raise ValueError('NATIVE_BUDGET_EXCEEDED')
                checkpoint.update(status='COMPLETE',Native_seconds=used+charged,artifacts=result.get('artifacts',[]),result=result,result_sha=digest(result))
                atomic(p,checkpoint);context[stage]=result
            except Exception as error:
                # Ambiguous failure after a Native call stays unreconciled.
                # The real handler must expose measured accounting atomically.
                checkpoint.update(status='FAILED_REQUIRES_LEDGER_RECONCILIATION',error=repr(error))
                atomic(p,checkpoint)
                return dict(day=day,arm=arm,status='FAILED',stage=stage,error=repr(error))
        return dict(day=day,arm=arm,status='COMPLETE')

    def all_dates(self,days):
        results=[]
        with owned_lock(self.root):
            for day in days:
                for arm in ('B0','B1','B2','B3'):
                    try:result=self.case(day,arm)
                    except Exception as e:result=dict(day=day,arm=arm,status='FAILED',error=repr(e))
                    results.append(result);atomic(self.root/'MONITOR_AND_AGGREGATION.json',dict(cases=results,scheduler_imports_optimizer=False))
        return results

def require_campaign(approval_path):
    final=read(OUT/'FINAL_PRESTART_GO_NO_GO.json')
    if final['status']!='READY_FOR_USER_CAMPAIGN_APPROVAL':raise PermissionError('PRESTART_BLOCKED_WITH_EVIDENCE')
    permit=read(approval_path)
    if (permit.get('explicit_human_campaign_approval') is not True or permit.get('prestart_certificate_sha')!=record(OUT/'FINAL_PRESTART_GO_NO_GO.json')['sha256']):
        raise PermissionError('MATCHING_FUTURE_EXPLICIT_USER_CAMPAIGN_APPROVAL_REQUIRED')
    if not read(OUT/'B0_B1_B2_B3_STAGE_WIRING_CERTIFICATION.json')['real_FULL_stage_adapters_bound']:
        raise PermissionError('REAL_FULL_STAGE_ADAPTERS_NOT_BOUND')
    return permit

def plan():
    from v44 import config
    hold=dict(status='HOLD_NO_CAMPAIGN_EXECUTION',auto_run=False,Native_long_solver_authorized=False,
        reason='All seven gates must pass and a separate future human campaign approval must match the final certificate.',
        runtime=str(RUN/'official_may01_07'),Python=str(RUN.parents[1]/'.venv/Scripts/python.exe'),
        preparation_command='python -m v2_add_preflight.prestart_execution plan',
        future_campaign_command='python -m v2_add_preflight.prestart_execution campaign --approval <explicit-human-approval.json>',
        command_runnable_now=False,worker_count=1,simultaneous_heavy_Native_workers=0,
        existing_worker_processes_priority_affinity_or_locks_mutated=False,
        original_policy=config.policy(),budgets_by_stage=dict(A1=config.A_SECONDS,A2=config.A_SECONDS,
            K48_M1=config.K48_SECONDS,K48_M2=config.K48_SECONDS,M1=config.JOINT_SECONDS,M2=config.JOINT_SECONDS),
        estimates=dict(total_native_per_B1_seconds=config.A_SECONDS,total_native_per_B2_seconds=config.K48_SECONDS+config.JOINT_SECONDS,
            total_native_per_B3_seconds=config.A_SECONDS+2*(config.K48_SECONDS+config.JOINT_SECONDS),
            label='Configured budget ceilings, not measured runtime forecasts; Actual/Fresh/build wall time separate'),
        pre_launch_checks=['seven gates PASS','same-date same-input acceptance hashes','certified FULL adapters and independent validators',
            'original r043 policy overlay/Threads/call caps bound','held production locks available; no bypass',
            'resource reserve and single-worker OS lease','unambiguous prior Native ledgers; no budget reset','future explicit user approval'])
    put('CAMPAIGN_EXECUTION_HOLD.json',hold)
    return put('B0_B1_B2_B3_STAGE_WIRING_CERTIFICATION.json',dict(chains={k:list(v) for k,v in CHAINS.items()},
        scheduler_implemented=True,checkpoint_artifact_hash_binding=True,crash_requires_ledger_reconciliation=True,
        independent_date_failures_supported=True,real_FULL_stage_adapters_bound=False,
        A1_reuse='same date/input/scenario/source/acceptance SHA and original FULL required',
        A_stage_acceptance_adapter='prestart_acceptance.execute_a_stage; original Job validation plus same-case grid and Global LB/gap',
        source_stage_entrypoints={
            'A1':'v44.worker.a_stage','M1':'v44.worker.m_stage','A2':'v44.worker.a_stage(m1=...)','M2':'v44.worker.m_stage',
            'K48':'v43_mess.prepared.run_prepared_k48','Actual':'v44.worker.actual','Fresh':'v44.campaign.run_case independent Actual replay'},
        unsupported='Source entries retain IEEE123 physical authority/case/budget permits; no guard bypass or fake8500 binding installed.',
        fixture_native_calls='ORIGINAL_NATIVE_STAGE_FIXTURE_CALLS.json',campaign_started=False))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['plan','campaign']);p.add_argument('--approval');a=p.parse_args()
    if a.mode=='plan':plan()
    else:
        require_campaign(a.approval)
        raise RuntimeError('REAL_FULL_IEEE8500_STAGE_HANDLERS_REQUIRED_BEFORE_EXECUTION')
