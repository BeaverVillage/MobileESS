"""Serial campaign state/return gates; no solver or automatic launch on import."""
from datetime import date,timedelta,datetime
from pathlib import Path
import json
import os

from .unified_contract import digest

STAGES=('INPUT','A1','M1','A2','M2','ACTUAL','FRESH_AC','AUDIT')
STATUSES={'FULL_PASS','PHYSICAL_FAIL','OPTIMALITY_TARGET_UNMET','FEASIBLE_OPTIMALITY_TARGET_UNMET',
    'TIME_LIMIT_NO_FEASIBLE','INFEASIBLE_CERTIFIED','INPUT_UNAVAILABLE','NOT_RUN','NOT_CERTIFIED',
    'PRACTICALITY_TARGET_UNMET'}


def may_dates():return [(date(2025,5,1)+timedelta(days=n)).isoformat() for n in range(31)]


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8')
    os.replace(temp,path)


def input_gate(day,receipt):
    midnight=datetime.fromisoformat(day+'T00:00:00+10:00').timestamp()
    if (receipt.get('day')!=day or receipt.get('initial_state_day')!=day
            or receipt.get('initial_state_epoch_seconds')!=midnight
            or receipt.get('max_initial_submit_seconds',float('inf'))>midnight
            or receipt.get('forecast_available_seconds',float('inf'))>midnight
            or not receipt.get('initial_state_sha') or not receipt.get('case_sha')
            or receipt.get('independent_D0') is not True or receipt.get('prior_day_carry_imported') is not False):
        raise ValueError('DATE_SPECIFIC_CAUSAL_D0_INPUT_REQUIRED')
    return receipt


def launch_gate(plan,approval,gate):
    if (plan.get('Worker')!=1 or plan.get('Threads')!=1 or plan.get('dates')!=may_dates()
            or plan.get('automatic_start') is not False):raise ValueError('SERIAL_MAY_PLAN_REQUIRED')
    if (gate.get('status')!='CAMPAIGN_READY' or gate.get('May01_integrated_Full96_Fresh')!='PASS'
            or gate.get('representative_dates')!={d:'PASS' for d in ('2025-05-02','2025-05-10','2025-05-12')}
            or approval.get('scope')!='MAY31_ALL_FROZEN_STAGES' or approval.get('approved') is not True
            or approval.get('release_sha')!=plan.get('release_sha')
            or approval.get('plan_sha')!=digest(plan)
            or type(approval.get('Native_limit_seconds')) not in (float,int)
            or not 0<approval['Native_limit_seconds']<float('inf')):
        raise PermissionError('MAY01_FULL96_REPRESENTATIVE_DATES_AND_NEW_CAMPAIGN_BUDGET_REQUIRED')


def run_serial(plan,*,approval,gate,folder,executors):
    """Persist every actual stage result; failure skips that date's tail only.

    Production adapters must be supplied explicitly by the frozen release.
    Missing adapters fail closed. Resume checks completed receipt content,
    release/plan identity and the exact prior stage result.
    """
    launch_gate(plan,approval,gate)
    if set(executors)!=set(STAGES):raise ValueError('ALL_FROZEN_STAGE_EXECUTORS_REQUIRED')
    root=Path(folder);root.mkdir(parents=True,exist_ok=True)
    identity=dict(release_sha=plan['release_sha'],plan_sha=digest(plan),approval_sha=digest(approval))
    for day in plan['dates']:
        path=root/day/'DATE_LEDGER.json'
        if path.exists():
            state=json.loads(path.read_text(encoding='utf8'))
            if state['identity']!=identity:raise ValueError('RESUME_SOURCE_CASE_OR_BUDGET_DRIFT')
        else:
            state=dict(day=day,identity=identity,status='NOT_RUN',stages={},Worker=1,Threads=1)
        prior=None;blocked=False
        for stage in STAGES:
            old=state['stages'].get(stage)
            if old and old.get('executed'):
                if old['result_sha']!=digest(old['result']):raise ValueError('RESUME_RECEIPT_BYTES_OR_CONTENT_DRIFT')
                prior=old['result']
                blocked=old['status']!='FULL_PASS'
                if blocked:break
                continue
            if blocked:break
            attempt=root/day/stage
            if attempt.exists():
                # Interrupted attempts require reconciliation; never overwrite
                # raw or silently repeat an unknown-cost optimizer call.
                state['status']='NOT_CERTIFIED';state['interruption']='UNRECONCILED_STAGE_ATTEMPT:'+stage
                save(path,state);blocked=True;break
            attempt.mkdir(parents=True)
            try:
                result=executors[stage](day=day,previous=prior,output=attempt,identity=identity)
                if result.get('status') not in STATUSES:raise ValueError('EXPLICIT_STAGE_RETURN_STATUS_REQUIRED')
                if result.get('day')!=day:raise ValueError('CROSS_DATE_RESULT_FORBIDDEN')
                if stage=='INPUT' and result['status']=='FULL_PASS':input_gate(day,result)
                if prior and result.get('input_result_sha')!=digest(prior):raise ValueError('STAGE_PARENT_RESULT_SHA_REQUIRED')
            except Exception as exc:
                result=dict(day=day,status='INPUT_UNAVAILABLE' if stage=='INPUT' else 'NOT_CERTIFIED',
                    error_type=type(exc).__name__,error=str(exc),raw_preserved=True)
            state['stages'][stage]=dict(executed=True,status=result['status'],result=result,result_sha=digest(result))
            state['status']=result['status'];save(path,state);prior=result
            if result['status']!='FULL_PASS':blocked=True;break
        if blocked:
            for stage in STAGES:
                if stage not in state['stages']:state['stages'][stage]=dict(executed=False,status='NOT_RUN',reason='UPSTREAM_STAGE_NOT_ACCEPTED')
        save(path,state)
    return identity
