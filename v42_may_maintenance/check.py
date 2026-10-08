"""Read-only campaign diagnosis and narrowly verified dead-host recovery.

Code/algorithm repairs are performed by the scheduled Codex task in a separate
version; this inspector never patches frozen source or changes scientific data.
"""
import argparse, csv, json, math, subprocess, sys, traceback, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta
import psutil
from v42_may_campaign.common import atomic, read, sha, record, digest, now, process, same_process, table, d_path, LockBusy, verify_manifest
from v42_may_campaign.coordinator import AXIS, TERMINAL, counts, receipt_valid, command_matches
from v42_may_campaign.windows import task_status, scheduler_process_evidence, reuse_registered_task, run_task
from .session import check_lock

KST=timezone(timedelta(hours=9))


def optional(path, default=None):
    path=Path(path)
    try:return read(path) if path.is_file() else ({} if default is None else default)
    except (OSError,ValueError) as error:return dict(_read_error=str(error),_path=str(path))


def age(stamp):
    return max(0.,datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(stamp).timestamp()) if stamp else None


def tail(path, limit=12000):
    path=Path(path)
    if not path.is_file():return ''
    with path.open('rb') as stream:
        stream.seek(max(0,path.stat().st_size-limit));return stream.read().decode('utf-8',errors='replace')


def source_audit(project, manifest):
    rows=[]
    for name,expected in manifest['sources'].items():
        path=project/name
        actual=sha(path) if path.is_file() else None
        rows.append(dict(path=str(path),expected_SHA=expected,actual_SHA=actual,PASS=actual==expected))
    return dict(PASS=all(r['PASS'] for r in rows),checked=len(rows),files=rows,
        manifest_algorithm_HEAD=manifest.get('source_HEAD'),UTC=now(),active_sources_modified=False)


def runtime_audit(ledger, request, is_live):
    calls=ledger.get('calls',[]);measured=ledger.get('measured_Native_Runtime',0.)
    sum_calls=sum(row.get('Native_Runtime',0.) for row in calls)
    valid=(isinstance(measured,(int,float)) and math.isfinite(measured) and 0<=measured<=5400+1e-6
        and abs(sum_calls-measured)<=1e-6
        and ledger.get('P2_calls')==0
        and ledger.get('wall_ceiling_seconds')==5400 and ledger.get('Native_ceiling_seconds')==5400)
    for row in calls:
        valid=valid and row.get('component')!='P2' and 0<=row.get('effective_TimeLimit',-1)<=5400
    wall=age(request.get('started_UTC')) if is_live else ledger.get('wall_seconds')
    return dict(PASS=bool(valid),Native_Runtime_completed=measured,Native_calls=len(calls),
        actual_dispatch_wall_seconds=wall,remaining_wall_seconds=max(0.,5400-wall) if wall is not None else None,
        inflight=ledger.get('inflight'),runtime_unavailable=any(r.get('runtime_unavailable') for r in calls),
        unknown_runtime_is_conservative_quarantine_not_certified_measurement=True,
        completed_call_Runtime_is_not_live_Runtime=True)


def issue(category, code, **extra):
    return dict(category=category,code=code,**extra)


def inspect(campaign, *, source_checker=source_audit, task_reader=task_status, owner_reader=scheduler_process_evidence, manifest_validator=verify_manifest):
    campaign=d_path(campaign);project=campaign.parents[2]
    manifest=read(campaign/'CAMPAIGN_MANIFEST.json');issues=[];checkpoint=optional(campaign/'CHECKPOINT.json')
    audit=source_checker(project,manifest)
    if not audit['PASS']:issues.append(issue('INFRASTRUCTURE','FROZEN_SOURCE_SHA_MISMATCH'))
    try:
        manifest_validator(campaign/'CAMPAIGN_MANIFEST.json');manifest_valid=True;manifest_error=None
    except (OSError,ValueError,PermissionError) as error:
        manifest_valid=False;manifest_error=str(error);issues.append(issue('INFRASTRUCTURE','FROZEN_INPUT_GATE_OR_MANIFEST_FAILURE',error=str(error)))
    expected={a+'/'+d for a,d in AXIS}
    checkpoint_valid=(checkpoint.get('run_id')==manifest['run_id'] and set(checkpoint.get('dates',{}))==expected)
    if not checkpoint_valid:issues.append(issue('INFRASTRUCTURE','CHECKPOINT_RUN_AXIS_INVALID'))
    dates=checkpoint.get('dates',{})
    for name,row in dates.items():
        if name!=str(row.get('arm'))+'/'+str(row.get('day')) or row.get('attempts') not in (0,1):
            checkpoint_valid=False
            issues.append(issue('INFRASTRUCTURE','CHECKPOINT_DATE_IDENTITY_OR_ATTEMPT_INVALID',key=name))
    heartbeat=optional(campaign/'COORDINATOR_HEARTBEAT.json');host=optional(campaign/'COORDINATOR_HOST.json')
    coordinator=heartbeat.get('process',host.get('process',{}));coordinator_alive=same_process(coordinator)
    if coordinator_alive and (age(heartbeat.get('timestamp_UTC')) or 0)>60:
        issues.append(issue('INFRASTRUCTURE','COORDINATOR_HEARTBEAT_STALE_NEEDS_DIAGNOSIS'))
    monitor=optional(campaign/'MONITOR_PROCESS.json');monitor_alive=same_process(monitor)
    actives=optional(campaign/'ACTIVES.json',dict(workers={}))
    if actives.get('run_id',manifest['run_id'])!=manifest['run_id']:
        issues.append(issue('INFRASTRUCTURE','ACTIVES_RUN_ID_INVALID'))
    workers=[];ledger_rows=[];versions=[];seen_slots=set();seen_dates=set();live_arms=set()
    for name,active in actives.get('workers',{}).items():
        identity=active.get('worker',{});live=same_process(identity);arm,day=active.get('arm'),active.get('day')
        canonical=campaign/'dates'/str(arm)/str(day)/'request.json'
        scoped=(name==str(arm)+'/'+str(day) and (arm,day) in AXIS and Path(active.get('request','')).resolve()==canonical)
        request=optional(canonical) if scoped else {}
        scoped=scoped and request.get('run_id')==manifest['run_id'] and request.get('arm')==arm and request.get('day')==day
        scoped=scoped and request.get('manifest_SHA')==sha(campaign/'CAMPAIGN_MANIFEST.json')
        scoped=scoped and Path(request.get('root','')).resolve()==campaign
        scoped=scoped and Path(request.get('input_folder','')).resolve()==Path(manifest['input_folders'].get(name,'')).resolve()
        slot=active.get('worker_slot')
        scoped=scoped and slot==request.get('worker_slot') and type(slot) is int and 1<=slot<=(1 if arm=='B1' else 3)
        scoped=scoped and (not live or command_matches(request.get('worker_command'),identity.get('command')))
        scoped=scoped and all(Path(request.get(field,'')).resolve()==canonical.parent/filename for field,filename in (
            ('output','output'),('progress','progress.json'),('result','RESULT.json'),('error','error.json')))
        if not scoped:issues.append(issue('INFRASTRUCTURE','ACTIVE_WORKER_REQUEST_IDENTITY_MISMATCH',arm=arm,day=day))
        if live:
            if (arm,slot) in seen_slots or (arm,day) in seen_dates:
                issues.append(issue('INFRASTRUCTURE','DUPLICATE_DATE_OR_SLOT',arm=arm,day=day))
            seen_slots.add((arm,slot));seen_dates.add((arm,day));live_arms.add(arm)
        attempt=canonical.parent;progress=optional(attempt/'progress.json') if scoped else {}
        hb=optional(attempt/'HEARTBEAT.json') if scoped else {}
        hb_valid=bool(hb and hb.get('worker')==identity and hb.get('identity',{}).get('day')==day)
        if live and (not hb_valid or (age(hb.get('timestamp_UTC')) or 0)>60):
            issues.append(issue('INFRASTRUCTURE','WORKER_HEARTBEAT_NEEDS_CORROBORATION',arm=arm,day=day))
        ledger=optional(attempt/'NATIVE_RUNTIME_LEDGER.json') if scoped else {}
        runtime=runtime_audit(ledger,request,live) if ledger else dict(PASS=None,status='NOT_YET_CREATED')
        if runtime['PASS'] is False:issues.append(issue('INFRASTRUCTURE','NATIVE_LEDGER_INVALID',arm=arm,day=day))
        resource={}
        if live:
            p=psutil.Process(identity['PID']);cpu=p.cpu_times()
            resource=dict(CPU_seconds=cpu.user+cpu.system,RSS=p.memory_info().rss,information_only=True)
        workers.append(dict(arm=arm,day=day,slot=slot,worker=identity,alive=live,identity_PASS=scoped,
            phase=progress.get('phase'),heartbeat=hb,heartbeat_age_seconds=age(hb.get('timestamp_UTC')),
            progress_age_seconds=age(progress.get('timestamp_UTC')),progress=progress,runtime=runtime,resource=resource,
            Native_log_tails={p.name:tail(p,3000) for p in sorted(attempt.glob('*_NATIVE.log'))[-2:]},
            stdout_tail=tail(attempt/'stdout.log',6000),stderr_tail=tail(attempt/'stderr.log',6000),
            low_CPU_or_unchanged_gap_is_not_error=True))
    b1=counts(checkpoint,'B1') if checkpoint_valid else {};b2=counts(checkpoint,'B2') if checkpoint_valid else {}
    if len(live_arms)>1 or len([w for w in workers if w['alive'] and w['arm']=='B1'])>1 or len([w for w in workers if w['alive'] and w['arm']=='B2'])>3:
        issues.append(issue('INFRASTRUCTURE','WORKER_CONCURRENCY_POLICY_VIOLATION'))
    if 'B2' in live_arms and b1.get('completed')!=31:issues.append(issue('INFRASTRUCTURE','B2_STARTED_BEFORE_B1_TERMINAL'))
    # Actual process inventory closes the dispatch-to-ACTIVES persistence window.
    actual_workers=[]
    for p in psutil.process_iter(['pid','cmdline']):
        try:
            command=p.info['cmdline'] or []
            if 'v42_may_campaign.worker' in command and command[-1].lower().startswith(str(campaign/'dates').lower()):
                actual_workers.append(process(p.pid))
        except psutil.Error:pass
    registered_PIDs={w['worker'].get('PID') for w in workers if w['alive']}
    if {p['PID'] for p in actual_workers}-registered_PIDs:
        issues.append(issue('INFRASTRUCTURE','LIVE_WORKER_NOT_YET_IN_ACTIVES_RECHECK_BEFORE_REPAIR'))
    for name,row in dates.items():
        if row.get('status') not in TERMINAL|{'PENDING','RUNNING'}:
            issues.append(issue('INFRASTRUCTURE','UNKNOWN_DATE_STATUS',arm=row.get('arm'),day=row.get('day')))
        if row.get('status') in TERMINAL and row.get('result'):
            try:
                request=read(row['request']);result=read(row['result'])
                valid=sha(row['result'])==row['result_SHA'] and receipt_valid(campaign,manifest,request,result)
            except (KeyError,OSError,ValueError):valid=False
            if not valid:issues.append(issue('INFRASTRUCTURE','TERMINAL_RESULT_SHA_OR_IDENTITY_FAILURE',arm=row.get('arm'),day=row.get('day')))
        if row.get('attempts'):
            request=optional(campaign/'dates'/row['arm']/row['day']/'request.json')
            ledger=optional(campaign/'dates'/row['arm']/row['day']/'NATIVE_RUNTIME_LEDGER.json')
            if ledger:ledger_rows.append(dict(arm=row['arm'],day=row['day'],status=row['status'],**runtime_audit(ledger,request,row['status']=='RUNNING')))
            versions.append(dict(arm=row['arm'],day=row['day'],status=row['status'],attempts=row['attempts'],
                algorithm_HEAD=manifest.get('source_HEAD'),manifest_SHA=sha(campaign/'CAMPAIGN_MANIFEST.json'),
                case_SHA=row.get('summary',{}).get('fields',{}).get('case_sha'),
                input_SHA=sha(Path(request['input_folder'])/'NATIVE_INPUT.json') if request.get('input_folder') else None))
    if not coordinator_alive and checkpoint.get('state')!='COMPLETE':issues.append(issue('INFRASTRUCTURE','COORDINATOR_DEAD'))
    if not monitor_alive:issues.append(issue('INFRASTRUCTURE','MONITOR_DEAD'))
    ownership={}
    for role,identity in [('coordinator',coordinator),('monitor',monitor)]+[('worker_'+str(w['slot']),w['worker']) for w in workers if w['alive']]:
        if same_process(identity):
            try:ownership[role]=owner_reader(identity)
            except (OSError,PermissionError,subprocess.SubprocessError) as error:ownership[role]=dict(PASS=False,error=str(error))
            if not ownership[role]['PASS']:issues.append(issue('INFRASTRUCTURE','SCHEDULER_OWNERSHIP_UNPROVEN',role=role))
    tasks={role:task_reader(name) for role,name in manifest['tasks'].items()}
    for role,info in tasks.items():
        if info.get('state') not in ('Running','Ready') or info.get('last_task_result',0) not in (0,267009):
            issues.append(issue('INFRASTRUCTURE','TASK_STATE_OR_RESULT_NEEDS_DIAGNOSIS',role=role,task=info))
    try:
        with urllib.request.urlopen('http://127.0.0.1:'+str(manifest.get('monitor_port',8793))+'/api/status',timeout=5) as response:
            http=dict(PASS=response.status==200,status=response.status)
    except Exception as error:http=dict(PASS=False,error=str(error))
    if not http['PASS']:issues.append(issue('INFRASTRUCTURE','MONITOR_HTTP_FAILURE_NEEDS_DIAGNOSIS'))
    # Existing setting is audited, never silently changed in an active Worker.
    policy_path=project/'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json'
    policy=optional(policy_path);heuristics=policy.get('parameters',{}).get('Heuristics')
    heuristic=dict(existing_A_frozen_Heuristics=heuristics,
        builtin_MIP_heuristics_enabled=isinstance(heuristics,(int,float)) and heuristics>0,
        compatible_with_zero_builtin_heuristics=heuristics==0,
        restriction_audit='BUILTIN_HEURISTICS_ENABLED; conflicts with a zero-heuristics policy; no new unverified search heuristic added',
        status='RESTRICTION_CONFLICT_RECORDED_ACTIVE_FROZEN_POLICY_PRESERVED',new_heuristic_added=False,
        policy_evidence=record(policy_path) if policy_path.is_file() else None,
        parameter_definition='https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameterheuristics',
        evidence_scope='Frozen configured policy; no foreign live model queried or altered',
        active_worker_parameter_changes=0,policy_candidate_validation='NOT_TESTED; no candidate promoted',
        future_change_requires=['separate policy version','Native=0 regression','model and certificate equivalence',
            'finite independent performance validation','safe verified dispatch boundary'],
        changed_policy_requires_separate_version_and_validation=True,
        M_actual_parameter_audit='NOT_TESTED_BEFORE_B2_NATIVE; inspect real parameter logs when B2 starts')
    return dict(UTC=now(),KST=datetime.now(KST).isoformat(),run_id=manifest['run_id'],project=str(project),
        campaign_root=str(campaign),state=checkpoint.get('state'),B1=b1,B2=b2,workers=workers,
        coordinator=dict(alive=coordinator_alive,process=coordinator,heartbeat_age_seconds=age(heartbeat.get('timestamp_UTC'))),
        monitor=dict(alive=monitor_alive,process=monitor,http=http),tasks=tasks,ownership=ownership,
        source_audit=audit,manifest_valid=manifest_valid,manifest_error=manifest_error,
        frozen_inputs_and_gates_reverified=manifest_valid,checkpoint_valid=checkpoint_valid,issues=issues,Native_ledger_rows=ledger_rows,
        algorithm_versions=versions,actual_worker_inventory=actual_workers,heuristic_audit=heuristic,
        date_rows=dates,watchdog=optional(campaign/'WATCHDOG_STATUS.json'),transition=optional(campaign/'B1_TO_B2_TRANSITION_VERIFICATION.json'),
        repair_needed=bool(issues),resource=dict(RAM_available=psutil.virtual_memory().available,information_only=True),
        Native_calls_by_maintenance=0,active_source_or_solver_changes=False)


def recover_dead_hosts(campaign, health):
    """Only an already-approved same-manifest task can recover a dead host."""
    campaign=d_path(campaign);actions=[]
    if not health['source_audit']['PASS'] or not health['checkpoint_valid'] or not health.get('manifest_valid'):
        return [dict(action='RECOVERY_BLOCKED',reason='SOURCE_OR_CHECKPOINT_UNPROVEN')]
    allowed={'COORDINATOR_DEAD','MONITOR_DEAD'}
    if any(i['code'] not in allowed for i in health['issues']):
        return [dict(action='RECOVERY_BLOCKED',reason='ADDITIONAL_IDENTITY_OR_INTEGRITY_FAILURE')]
    if health['coordinator']['alive'] and health['monitor']['alive']:return []
    manifest=read(campaign/'CAMPAIGN_MANIFEST.json')
    # Original validator is read-only. No checkpoint/result rewriting here.
    from v42_may_campaign.common import verify_manifest
    from v42_may_campaign.coordinator import load_checkpoint,recovery_requests,read_actives
    verify_manifest(campaign/'CAMPAIGN_MANIFEST.json')
    recovery_requests(campaign,manifest,load_checkpoint(campaign,manifest),read_actives(campaign))
    for role in ('coordinator','monitor'):
        identity=health[role]['process']
        if same_process(identity) or role=='coordinator' and health['state']=='COMPLETE':continue
        task=manifest['tasks'][role]
        reuse_registered_task(campaign,role,task,python=manifest.get('Python'))
        run_task(task);actions.append(dict(action='START_VERIFIED_DEAD_'+role.upper(),task=task,UTC=now(),
            verification='REQUESTED; fresh inspection must confirm heartbeat; no Worker retried',
            healthy_workers_terminated=False,checkpoint_modified=False))
    return actions


def write_reports(storage, health, previous, actions):
    storage=d_path(storage);storage.mkdir(parents=True,exist_ok=True)
    state=optional(storage/'MAINTENANCE_STATE.json',dict(checks=0,pending_issues={},seen_terminal_failures=[]))
    checked=health['UTC'];head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=health['project'],text=True).strip()
    fresh=[];seen=set(state.get('seen_terminal_failures',[]))
    causes=list(csv.DictReader((storage/'FAILURE_ROOT_CAUSE.csv').open(encoding='utf-8'))) if (storage/'FAILURE_ROOT_CAUSE.csv').is_file() else []
    for name,row in health['date_rows'].items():
        if row['status'] in TERMINAL and row['status']!='PASS' and name not in seen:
            category=('OPTIMIZATION_OUTCOME' if row['status'].startswith('TIME_LIMIT') else
                'SCIENTIFIC' if row['status'] in {'PHYSICAL_FAILURE','INFEASIBLE_PROVEN','INPUT_FAILURE','FRESH_AC_FAILURE'} else 'NEEDS_ROOT_CAUSE')
            cause=dict(UTC=checked,arm=row['arm'],day=row['day'],status=row['status'],category=category,
                error=row.get('error',row.get('summary',{}).get('error')),result_SHA=row.get('result_SHA'),
                diagnosis='Preserve original receipt; inspect logs before proposing a repair',retries=0)
            fresh.append(cause);causes.append(cause);seen.add(name)
    pending=state.get('pending_issues',{})
    current={digest(i):i for i in health['issues']}
    for key,value in current.items():
        prior=pending.get(key,{})
        pending[key]=dict(prior,issue=value,first_seen_UTC=prior.get('first_seen_UTC',checked),
            last_seen_UTC=checked,observations=prior.get('observations',0)+1,status='OPEN',
            evidence_preserved=True,next_action=prior.get('next_action','Diagnose from exact logs/PID/SHA; reuse prior evidence'))
    for key in set(pending)-set(current):
        if pending[key].get('kind')!='TERMINAL_TRIAGE':
            pending[key].update(status='RESOLVED_BY_NEW_OBSERVATION',resolved_UTC=checked)
    for cause in fresh:
        key='TERMINAL_TRIAGE_'+digest((cause['arm'],cause['day'],cause['result_SHA']))
        pending[key]=dict(kind='TERMINAL_TRIAGE',status='OPEN',first_seen_UTC=checked,last_seen_UTC=checked,
            issue=cause,next_action='Validate integer/certificate/budget and preserve logs; classify expected outcome or prepare isolated repair')
    complete=health['B1'].get('completed')==31 and health['B2'].get('completed')==31
    open_issues=[k for k,v in pending.items() if v.get('status')=='OPEN']
    state.update(checks=state.get('checks',0)+1,last_check_UTC=checked,last_check_KST=health['KST'],
        run_id=health['run_id'],pending_issues=pending,seen_terminal_failures=sorted(seen),
        completion_ready=complete and not open_issues and not state.get('pending_releases'),
        last_action='HEALTHY_NO_CHANGE' if not health['issues'] and not actions else 'DIAGNOSIS_OR_RECOVERY',
        last_git_HEAD=head,active_workers=[w['worker'] for w in health['workers'] if w['alive']],
        Codex_app_and_local_project_access_required=True,OS_Coordinator_independent=True)
    changes=[]
    for worker in health['workers']:
        old=next((w for w in previous.get('workers',[]) if w['worker']==worker['worker']),{})
        changes.append(dict(arm=worker['arm'],day=worker['day'],same_worker=bool(old),
            previous_UB=old.get('progress',{}).get('UB'),current_UB=worker['progress'].get('UB'),
            previous_Certified_Gap=old.get('progress',{}).get('certified_gap'),current_Certified_Gap=worker['progress'].get('certified_gap'),
            previous_phase=old.get('phase'),current_phase=worker['phase']))
    log=dict(UTC=checked,KST=health['KST'],B1=health['B1'],B2=health['B2'],workers=health['workers'],
        new_terminal_failures=fresh,issues=health['issues'],changes_since_previous_check=changes,
        source_before=head,source_after=head,code_modified=False,Native_calls=0,actual_restart_actions=actions,
        model_equivalence='UNCHANGED_FROZEN_MODEL; no new algorithm promoted',completion_ready=state['completion_ready'])
    with (storage/'HOURLY_CHECK_LOG.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(log,ensure_ascii=False,allow_nan=False)+'\n')
    atomic(storage/'SOURCE_SHA_AUDIT.json',health['source_audit'])
    atomic(storage/'HEURISTICS_POLICY_COMPATIBILITY_AUDIT.json',dict(health['heuristic_audit'],UTC=checked,
        active_workers=[w['worker'] for w in health['workers'] if w['alive']]))
    atomic(storage/'CAMPAIGN_HEALTH_STATUS.json',dict(health,new_terminal_failures=fresh,last_action=state['last_action'],completion_ready=state['completion_ready']))
    atomic(storage/'RESTART_RECOVERY_AUDIT.json',dict(UTC=checked,actions=actions,healthy_Solver_terminated=False,
        active_source_changed=False,checkpoint_reset=False,completed_date_reexecuted=False))
    atomic(storage/'B1_TO_B2_TRANSITION_VERIFICATION.json',dict(health['transition'],maintenance_observed_UTC=checked,
        transition_performed_by='Independent OS Coordinator'))
    atomic(storage/'MAINTENANCE_STATE.json',state)
    table(storage/'FAILURE_ROOT_CAUSE.csv',causes,['UTC','arm','day','status','category','error','result_SHA','diagnosis','retries'])
    repairs=list(csv.DictReader((storage/'AUTO_REPAIR_LEDGER.csv').open(encoding='utf-8'))) if (storage/'AUTO_REPAIR_LEDGER.csv').is_file() else []
    repairs.append(dict(UTC=checked,action=state['last_action'],git_before=head,git_after=head,code_modified=False,
        restart_actions=json.dumps(actions),Native_calls=0,validation='Frozen SHA/checkpoint/PID/ledger observed; no candidate code deployed'))
    table(storage/'AUTO_REPAIR_LEDGER.csv',repairs,['UTC','action','git_before','git_after','code_modified','restart_actions','Native_calls','validation'])
    table(storage/'ALGORITHM_VERSION_LEDGER.csv',health['algorithm_versions'],['arm','day','status','attempts','algorithm_HEAD','manifest_SHA','case_SHA','input_SHA'])
    table(storage/'NATIVE_RUNTIME_AUDIT.csv',health['Native_ledger_rows'],['arm','day','status','PASS','Native_Runtime_completed','Native_calls','actual_dispatch_wall_seconds','remaining_wall_seconds','inflight','runtime_unavailable'])
    return state


def run(campaign,storage,token=None,recover=False):
    with check_lock(storage,token):
        previous=optional(Path(storage)/'CAMPAIGN_HEALTH_STATUS.json')
        health=inspect(campaign)
        actions=recover_dead_hosts(campaign,health) if recover and health['issues'] else []
        if any(a['action'].startswith('START_VERIFIED_DEAD_') for a in actions):
            # No claim of success until real identity/heartbeat is observed.
            actions.append(dict(action='POST_RESTART_VERIFICATION_PENDING',UTC=now()))
        if any(a['action'].startswith('START_VERIFIED_DEAD_') for a in actions):
            health=inspect(campaign)
            for action in actions:
                if action['action'].startswith('START_VERIFIED_DEAD_'):
                    role=action['action'].removeprefix('START_VERIFIED_DEAD_').lower()
                    action['observed_alive_after_dispatch']=health[role]['alive']
            verified=health['coordinator']['alive'] and health['monitor']['alive']
            actions[-1].update(action='POST_RESTART_VERIFIED' if verified else 'POST_RESTART_NOT_YET_VERIFIED')
        state=write_reports(storage,health,previous,actions)
        return dict(PASS=not health['issues'],status=state['last_action'],checks=state['checks'],
            workers=[dict(arm=w['arm'],day=w['day'],PID=w['worker'].get('PID'),phase=w['phase']) for w in health['workers']],
            issues=health['issues'],actions=actions,completion_ready=state['completion_ready'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--campaign',required=True);parser.add_argument('--storage',required=True)
    parser.add_argument('--session-token');parser.add_argument('--recover-dead-hosts',action='store_true');args=parser.parse_args()
    try:result=run(args.campaign,args.storage,args.session_token,args.recover_dead_hosts)
    except LockBusy:result=dict(PASS=None,status='SKIP_PREVIOUS_MAINTENANCE_ACTIVE')
    except Exception as error:
        result=dict(PASS=False,status='CHECK_EXCEPTION_PRESERVED',UTC=now(),error=str(error),traceback=traceback.format_exc())
        atomic(d_path(args.storage)/'CHECK_EXCEPTION.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
