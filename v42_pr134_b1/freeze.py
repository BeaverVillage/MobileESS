"""Immutable scientific, input and operational run authority after all gates."""
import shutil,uuid,sys
from .common import *

def prepare(root):
    root=Path(root);OUT.mkdir(parents=True,exist_ok=True)
    for name in ['MAY31_INPUT_IDENTITY.json','ALL_EXISTING_DATE_REUSE_CASES.json','DATE_REUSE_AUDIT.csv','REUSE_IMPORT_PLAN.json',
                 'INFRASTRUCTURE_REGRESSION.json','OPERATIONS_PORT_VALIDATION.json']:
        shutil.copyfile(root/name,OUT/name)
    inputs=read(root/'MAY31_INPUT_IDENTITY.json')
    if not inputs['all_ready'] or len(inputs['days'])!=31:raise ValueError('ALL_31_ORIGINAL_INPUT_AUTHORITIES_REQUIRED')
    if not read(root/'INFRASTRUCTURE_REGRESSION.json')['PASS'] or not read(root/'OPERATIONS_PORT_VALIDATION.json')['PASS']:raise ValueError('OPERATIONS_VALIDATION_REQUIRED')
    build=read(root/'PRODUCTION_STATIC_MAY01_VALIDATION/BUILD_RECEIPT.json')
    if not build['PASS'] or not build['verification']['FULL_LP_equivalence']:raise ValueError('PRODUCTION_EQUIVALENCE_REQUIRED')
    shutil.copyfile(root/'PRODUCTION_STATIC_MAY01_VALIDATION/BUILD_RECEIPT.json',OUT/'PRODUCTION_A1_IDENTITY_FREEZE.json')
    (OUT/'PREREGISTRATION.md').write_text('''# PR134 supercompact May B1 production

Scientific base is exact PR134 52ef855a59144a7c561df44b81dc2ad265babdbd. Phase-I accepted witness, exhaustive full-LP/integer/objective proofs and bounded P1 comparison are frozen before production. PR150/151 provide only the fixed replay/monitor/orchestration pattern.

Each new date starts from zero native runtime and no old incumbent/start/bound/lock. Four original objectives are rho, migration count, absolute shift, prestart relocation. Original locks are P1 +1e-7 and each intervention component +1e-8. Method1, Threads1, Seed20260929, MIPGap.005, native default Presolve/Cuts/Heuristics/NumericFocus and tolerances are frozen. The four native solves share 3600 seconds; there is no budget extension or parameter sweep. This production authorization does not authorize a full paired development benchmark.

Complete exact-compatible dates are reused; incompatible or unproved dates are recomputed. Missing/invalid GPU or impossible whole-gang source records follow the existing PR134 current physical-modelability contract and remain in explicit ledgers. Reference windows, service and workload are never pruned based on May outcomes. Source one-slot display floors do not replace frozen Q50 service. Original R0 seed-date namespace is accepted only with matching producer, capacity, migration and payload SHA receipts.

One failing date does not terminate later independent dates. TIME_LIMIT is TIMEOUT, never proof of infeasibility. Valid UB and original native global LB/gap/Work/runtime/raw point/physical certificate are retained. Unsupported incumbents never receive PASS. Numerical, Fresh and validation failures retain evidence and enter the repair queue. Native INFEASIBLE is INCONCLUSIVE unless an independent scientific certificate is later obtained.

Infrastructure retries are at most two, from a complete valid stage checkpoint. Interrupted A1 restarts as a new attempt at native time zero without partial warm starts. PID/create-time/command matching and OS locks prevent duplicate workers. Completed receipts and payloads are SHA checked. Healthy solves are never cancelled because of CPU, memory, commit, paging or old solver telemetry. Memory/CPU telemetry is read-only.

Task Scheduler owns coordinator, monitor and hourly watchdog, with logon resume, PT0S duration and normal CPU/memory priority. The newest user instruction explicitly authorizes this OS hourly watchdog and supersedes the old Windows-repeat ban. No headless agent, algorithm retuning, root CG/B&P, M-stage, B2 or B3 is dispatched.

All 31 independent dates are attempted before the repair queue is finalized. Proven safe infrastructure defects can be repaired with focused tests, scientific identity proof, a new implementation commit and affected-date compatibility review. Unproved scientific changes and silent deadline/capacity/Runtime/CC4/voltage/gap changes are prohibited. Timeouts retain the original budget and are not repeatedly retried. Terminal evidence distinguishes PASS, timeout, independently proven infeasible and unresolved defects. OS tasks publish the fixed evidence namespace and final commit without invoking an unattended coding agent.
''',encoding='utf8')
    plan=[dict(day=r['day'],reuse=r['classification']=='REUSED',action='REUSE_COMPLETE' if r['classification']=='REUSED' else 'FRESH_A1_FROM_ZERO',native_budget=3600,Actual_reoptimization=0,PQ_repair=0) for r in read(root/'REUSE_IMPORT_PLAN.json')['days']]
    # A compatibility case must be imported before launch. This is a fail-closed
    # guard against accidentally recomputing a date already proved reusable.
    if any(r['reuse'] for r in plan):raise ValueError('VERIFIED_REUSE_IMPORT_REQUIRED_BEFORE_LAUNCH')
    table(root/'DATE_EXECUTION_PLAN.csv',plan,list(plan[0]));shutil.copyfile(root/'DATE_EXECUTION_PLAN.csv',OUT/'DATE_EXECUTION_PLAN.csv')
    shutil.copyfile(SC_OUT/'V42_A_STAGE_SUPERCOMPACT_AUTHORITY.json',OUT/'A_STAGE_AUTHORITY.json')
    atomic(OUT/'DETACHED_EXECUTION_AUTHORITY.json',dict(scientific_base=BASE,OS_owner='Windows Task Scheduler',coordinator_worker_independent=True,
        hourly_OS_watchdog=True,verified_launch_pending=True,logon_resume=True,ExecutionTimeLimit='PT0S',Priority=4,memory_guards=False,
        healthy_worker_kill=False,artificial_slowdown=False,resource_adaptive_solver=False,app_close_experiment_performed=False))
    atomic(OUT/'PRODUCTION_AUTHORITY.json',dict(scientific_base=BASE,compression='A2SC',Phase_I=record(SC_OUT/'V42_A_STAGE_SUPERCOMPACT_AUTHORITY.json'),
        solver=SETTINGS,native_budget=BUDGET,inputs=record(root/'MAY31_INPUT_IDENTITY.json'),reuse_count=0,dates=31,
        four_original_objectives=True,full_LP_equivalence=True,production_A0_matrix_equals_accepted_PR134=True,
        Stage_I_paired_full_benchmark_executed=False,Actual_reoptimization=0,PQ_repair=0,memory_guards=False,artificial_slowdown=False,parameter_sweep=False))
    atomic(OUT/'VERIFICATION.json',dict(Phase_I_PASS=True,production_static_equivalence_PASS=True,operations_port_PASS=True,all_31_inputs_ready=True,
        campaign_launched=False,all_31_attempted=False,all_31_PASS=False))
    pending=[dict(day=d,status='PENDING',stage='',attempts=0,infra_retries=0,error='',reused=False) for d in DAYS]
    for name in ('MAY_B1_PROGRESS.csv','MAY_B1_FINAL_DATE_STATUS.csv'):
        table(OUT/name,pending,['day','status','stage','attempts','infra_retries','error','reused'])
    table(OUT/'MAY_B1_REPAIR_QUEUE.csv',[],['day','status','priority','stage','attempts','infra_retries','error','resolution'])
    table(OUT/'MAY_B1_ERROR_REPAIR_LEDGER.csv',[],['timestamp','date','failure_class','error','root_cause','code_changed','scientific_model_changed','tests','old_SHA','new_SHA','action','rerun_required','resolution'])
    table(OUT/'MAY_B1_RESOURCE_LEDGER.csv',[],['UTC','day','stage','worker_PID','RSS','CPU_seconds','available_RAM','total_RAM','telemetry_only','admission_or_cancellation_action'])
    for name in ('FINAL_VALIDATION_SUMMARY.json','FINAL_CAMPAIGN_RESULT.json'):
        atomic(OUT/name,dict(state='NOT_YET_LAUNCHED',all_31_attempted=False,all_31_scientific_PASS=False,Actual_reoptimization=0,PQ_repair=0))
    (OUT/'FINAL_REVIEW_KO.md').write_text('''# PR134 supercompact May B1 통합 상태

Phase I 전수 압축·독립 verifier·원본 accepted witness 왕복 및 전체 행·4개 목적 검증 PASS. 운영 포트에서 fixed Actual/Fresh 96/96 수렴과 위반0을 확인했다. 이 테스트 계획은 production 날짜 재사용이나 old warm start가 아니다.

기존 32개 campaign checkpoint를 읽기 전용으로 감사했다. 완료 파일이 없는 경우 또는 정확 source/model/input/objective/validation 호환성을 입증하지 못한 경우는 재사용하지 않는다. 현재 증명된 전체 날짜 재사용은 0이다. 자세한 원인은 ALL_EXISTING_DATE_REUSE_CASES.json과 DATE_REUSE_AUDIT.csv에 있다.

31개 날짜의 원본 R0·현재 frozen Runtime/CC4/C0/C1·grid authority를 동결했다. scientific source는 PR134이며 PR150/151 입력 재구성은 사용하지 않는다. production은 별도의 Scheduler 소유 실행으로 시작한 뒤 실제 PID/생성시각/명령과 서비스 소유 계통을 검증한다. 아직 월 완료를 주장하지 않는다. 각 날짜의 실패·timeout은 기록하고 다음 날짜로 이동한다.
''',encoding='utf8')
    atomic(OUT/'SHA256_MANIFEST.json',dict(files=[record(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256_MANIFEST.json']))

def freeze(root):
    root=Path(root)
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():raise PermissionError('CLEAN_COMMITTED_SOURCE_REQUIRED')
    git=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
    frozen=read(root/'MAY31_INPUT_IDENTITY.json');assert frozen['all_ready']
    paths=[]
    for p in ROOT.glob('v42*/**/*.py'):
        if '__pycache__' not in p.parts:paths.append(p)
    ownhtml=ROOT/'v42_pr134_b1/monitor_index.html';paths.append(ownhtml)
    sources=[record(p) for p in sorted(paths)];scientific=digest(sources)
    uid=uuid.uuid4().hex[:8];run_id='B1_PR134_SC_202505_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'_'+uid
    suffix=datetime.now().strftime('%Y%m%dT%H%M')+'_'+uid
    static=read(SC_OUT/'PR134_BASE_IDENTITY.json');interface=read(SC_OUT/'SCIENTIFIC_INTERFACE_CAPTURE_AUDIT.json')
    artifacts=[record(SC_OUT/'V42_A_STAGE_SUPERCOMPACT_AUTHORITY.json'),record(SC_OUT/'A2SC_DELETION_PROOFS.npz'),static['matrix'],static['attributes'],static['original_data'],interface['descriptor']]
    artifacts.extend(record(root/n) for n in ('MAY31_INPUT_IDENTITY.json','REUSE_IMPORT_PLAN.json','INFRASTRUCTURE_REGRESSION.json','OPERATIONS_PORT_VALIDATION.json'))
    aux={d:[record(root/'inputs'/d/n) for n in ('WINDOWS.json','OPERATIONS.json')] for d in DAYS}
    f=dict(run_id=run_id,worktree=str(ROOT),Git_SHA=git,branch=branch,scientific_base=BASE,scientific_SHA=scientific,source_files=sources,immutable_artifacts=artifacts,
        day_input_SHA={r['day']:r['bundle']['sha256'] for r in frozen['days']},day_auxiliary=aux,solver=SETTINGS,native_budget=BUDGET,Python=str(Path(sys.executable)),
        task_name='MobileESS_V42_PR134_SC_B1_'+suffix,monitor_task='MobileESS_V42_PR134_SC_Monitor_'+suffix,watchdog_task='MobileESS_V42_PR134_SC_Hourly_'+suffix,
        memory_guards=False,artificial_slowdown=False,parameter_sweep=False,Actual_reoptimization=False,PQ_repair=False,mode='B1_PRODUCTION',created_UTC=now())
    atomic(root/'B1_PRODUCTION_FREEZE_MANIFEST.json',f)
    from .coordinator import load_checkpoint,save_checkpoint,export
    cp=load_checkpoint(root,f);save_checkpoint(root,cp);export(root,f,cp)
    atomic(root/'ACTIVE.json',{})
    atomic(root/'RUN_IDENTITY.json',dict(run_id=run_id,source_commit=git,scientific_SHA=scientific,partial_resume=False,old_incumbent_start_clock_bound_loaded=False))
    return f

if __name__=='__main__':
    import sys
    root=Path(sys.argv[1])
    if '--commit-ready' in sys.argv:prepare(root)
    else:freeze(root)
