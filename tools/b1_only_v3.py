"""B1-only operations adapter. All Source18r scientific files remain byte-identical."""
from pathlib import Path
import sys, os, json, time, shutil, subprocess, traceback, statistics
SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(SOURCE / 'tools'))
import psutil
from v42_pr134_b1.common import read, record, atomic, digest, sha, now
from v42_common_campaign.authority import source_files, singleton
from v42_svr11 import DAYS
from v42_svr11.authority import verify, scope
from v42_svr11.processes import identity, live, workers
from v42_svr11.resources import snapshot as memory

BASE_COMMIT = '497609b46faa14ea7e32a9483a333ab32fd264ef'
ORIGIN = Path(r'D:\v42_svr11_may_20261011_16')
DEFAULT_ROOT = Path(r'D:\v42_b1_only_may_20261012_03')
GIB = 1024 ** 3
PORT = 8801

def operations_files():
    return {p.relative_to(SOURCE).as_posix(): sha(p) for p in (Path(__file__).resolve(), SOURCE/'tools/register_b1_only_v3.ps1')}

def verify_only(root):
    m = verify(Path(root)/'CAMPAIGN_MANIFEST.json')
    if not (m.get('B1_only_authorization') == 'USER_EXPLICIT_B1_ONLY_20261012'
            and m['policy_order'] == ['B1'] and m['worker_counts'] == {'B1':1}
            and m['Threads'] == 1 and m['P2_calls'] == 0
            and m['native_A_limit_seconds'] == 5400 and m['A_gap'] == .005
            and m['source_commit'] == BASE_COMMIT and Path(m['code_root']) == SOURCE
            and m['operations_sources'] == operations_files()
            and m['operations_SHA'] == digest(operations_files())):
        raise PermissionError('B1_ONLY_GLOBAL_CONTRACT_OR_OPERATIONS_DRIFT')
    return m

def protected_state():
    baseline = read(r'D:\v42_critical_grid_cg_lb_20261012\docs\v42_critical_grid_cg\POST_RUN_RESOURCE_HOLD.json')
    refs = []
    for row in baseline.get('hold_markers', []):
        if 'path' in row:
            refs.append(record(row['path']))
    return dict(hold_markers=refs, CG_completed=record(r'D:\v42_critical_grid_cg_lb_20261012\docs\v42_critical_grid_cg\FINAL_RESULT.json'),
                original_repositories=[dict(path=r['path'],HEAD=subprocess.check_output(['git','-C',r['path'],'rev-parse','HEAD'],text=True).strip()) for r in baseline['originals']],
                old_tasks=baseline['scheduled_tasks'], state_mutations=0, UTC=now())

def prepare(root):
    root = Path(root).resolve()
    if (root/'CAMPAIGN_MANIFEST.json').exists():
        raise PermissionError('IMMUTABLE_B1_CAMPAIGN_ALREADY_RELEASED')
    root.mkdir(parents=True,exist_ok=True)
    old = read(ORIGIN/'CAMPAIGN_MANIFEST.json'); sources = source_files(); source = digest(sources)
    # Forecast/AIDC/AC algorithms are identical; all changes from Source16 are
    # reviewed M-only algorithms or the old four-policy orchestration.
    changed = {n for n in sources if old['execution_sources'].get(n) != sources[n]}
    allowed = {'v42_b3_joint/m_source.py','v42_common_mess/engine.py','v42_common_mess/telemetry.py',
        'v42_may_campaign_native90/m_model.py','v42_may_campaign_native90/m_stage.py','v42_native/mess.py',
        'v42_supercompact/presolve.py','v42_svr11/controller.py','v42_svr11/milp_release.py',
        'v42_svr11/watchdog.py','v42_ultracompact/current.py','v42_svr11/hold.py',
        'v42_native/mess_domain_verify.py','v42_native/grid_prescreen.py','v42_native/mess_domain.py',
        'v42_ultracompact/native_readback.py','v42_ultracompact/response.py',
        'v42_ultracompact/response_verify.py','v42_ultracompact/security.py','v42_ultracompact/security_verify.py'}
    if changed != allowed: raise PermissionError('B1_GLOBAL_UNREVIEWED_SCIENTIFIC_CHANGE:'+repr(changed))
    atomic(root/'SOURCE18R_B1_SCIENCE_AUDIT.json',dict(PASS=True,source_commit=BASE_COMMIT,source_SHA=source,
        origin_manifest=record(ORIGIN/'CAMPAIGN_MANIFEST.json'),changed_files=sorted(changed),
        B1_A_stage_Forecast_AIDC_QoS_Actual_sources_byte_identical=True,
        all_current_sources=sources, historical_results_promoted=0,UTC=now()))
    # The existing checked copy/rebind and forecast provenance mechanisms are
    # used only for raw input and immutable sensitivities, never solutions.
    import prepare_svr11_epoch14 as h
    h.OLD=ORIGIN; h.ROOT=root
    refs=h.raw_and_hardware(dict(old=old,sources=sources,source_SHA=source))
    import prepare_svr11_epoch16 as f
    f.OLD=ORIGIN; f.ROOT=root
    forecast=f.forecast(old,sources)
    from v42_svr11.model_release import validate
    keep=('schema','svr11_campaign','authorization','origins','equipment_change_contract',
          'original_transformer_current_authority','added_SVR_phase_nameplate_current_guard',
          'original_winding_kVA_guard','retrospective_design','independent_holdout_claim')
    m={k:old[k] for k in keep}
    m.update(root=str(root),code_root=str(SOURCE),run_id='B1_ONLY_MAY2025_'+root.name,
        source_commit=BASE_COMMIT,execution_sources=sources,execution_SHA=source,
        operations_sources=operations_files(),operations_SHA=digest(operations_files()),
        B1_only_authorization='USER_EXPLICIT_B1_ONLY_20261012',
        algorithm_version='B1_SOURCE18R_APPROVED_NATIVE90_A_STAGE',
        policy_order=['B1'],worker_counts={'B1':1},native_A_limit_seconds=5400,A_gap=.005,
        A_anytime_FULL_feasible=True,A_gap_certificate_required=False,Threads=1,P2_calls=0,
        M1_calls=0,M2_calls=0,FAIL_CONTINUE=True,normal_TIMEOUT_restart=False,
        retry_new_attempt_starts_zero=False,retry_max_attempts=1,
        production_campaign=True,development_diagnosis_only=False,
        hardware=record(root/'hardware/HARDWARE.json'),scenario=record(root/'hardware/SCENARIO.json'),
        thermal=record(root/'hardware/THERMAL.json'),input_receipts=refs,
        scientific_model_validation=validate(root,sources),model_checkpoint_reuse_contract=forecast,
        input_folders={'B1/'+d:str(root/'inputs/B1'/d) for d in DAYS},
        builder_original_sources=sources,implementation={'version':old['implementation']['version'],'sources':sources},
        postoptimization_DayAhead_Fresh_AC=False,Planning_AC_status='NOT_EXECUTED',
        Actual_reoptimization=0,Actual_PQ_repair=0,Planning_taps_copied_to_Actual=False,
        B1_all31_fresh_Native_zero=True,optimization_results_reused=0,
        admission=dict(RAM_floor_bytes=4*GIB,Commit_floor_bytes=6*GIB,worker_reservation_bytes=10*GIB,
                       minimum_disk_free_bytes=20*GIB),
        source_isolation='Source18r all scientific Python bytes identical; M Root180 gates are out of scope for B1, never bypassed for M',
        freeze_authority='FULL original integer/physical replay required; 0.5% optimality recorded independently',UTC=now())
    atomic(root/'PROTECTED_STATE_BEFORE.json',protected_state())
    atomic(root/'CAMPAIGN_MANIFEST.json',m)
    verify_only(root)
    atomic(root/'CAMPAIGN_LEDGER.json',dict(schema='V42_B1_ONLY_LEDGER_V1',status='PREFLIGHT_REQUIRED',policy='B1',
        started_UTC=now(),source_SHA=source,operations_SHA=m['operations_SHA'],dates={'B1/'+d:dict(arm='B1',day=d,status='NOT_EXECUTED',attempts=[]) for d in DAYS}))
    print(json.dumps(dict(PASS=True,root=str(root),source_SHA=source,operations_SHA=m['operations_SHA'])))

def heavy_peers(root):
    found=[]
    for p in psutil.process_iter(['name']):
        try:
            name=(p.info['name'] or '').lower()
            if name not in ('python.exe','pythonw.exe','gurobi_cl.exe'):continue
            args=p.cmdline(); joined=' '.join(args).lower()
            if p.pid==os.getpid():continue
            if str(root).lower() in joined and ('v42_svr11.worker' in joined or 'b1_only.py preflight' in joined):continue
            known=any(x in joined for x in ('.worker','physical_global_lb_pilot.py','critical_grid','validate_svr11_root180','root180_completion.py'))
            modules=[str(x.path).lower() for x in p.memory_maps(grouped=True)]
            if name=='gurobi_cl.exe' or known or any('gurobi130.dll' in x for x in modules):
                found.append(identity(p))
        except psutil.NoSuchProcess:continue
        except psutil.AccessDenied as e:
            found.append(dict(PID=p.pid,unverifiable=True,error=str(e)))
    return found

def admitted(root,m):
    obs=memory(); peers=heavy_peers(root); disk=shutil.disk_usage(root).free; c=m['admission']
    need=c['worker_reservation_bytes']
    ok=(not peers and obs['RAM_available']>=c['RAM_floor_bytes']+need
        and obs['Commit_available']>=c['Commit_floor_bytes']+need and disk>=c['minimum_disk_free_bytes'])
    return ok,dict(memory=obs,heavy_peers=peers,disk_free_bytes=disk,contract=c,UTC=now())

def request(root,m,row,preflight=False):
    if row['arm']!='B1' or row['day'] not in DAYS:raise PermissionError('B1_ONLY_AXIS')
    attempt=root/'dates/B1'/row['day']/'attempts/attempt_01'
    attempt.mkdir(parents=True,exist_ok=True)
    r=dict(root=str(root),campaign_root=str(root),code_root=str(SOURCE),run_id=m['run_id'],svr11_campaign=True,
        arm='B1',day=row['day'],worker_slot=1,attempt_id='attempt_01',manifest=str(root/'CAMPAIGN_MANIFEST.json'),
        manifest_SHA=sha(root/'CAMPAIGN_MANIFEST.json'),source_SHA=m['execution_SHA'],
        input_folder=str(root/'inputs/B1'/row['day']),output=str(attempt/'output'),result=str(attempt/'RESULT.json'),
        progress=str(attempt/'progress.json'),error=str(attempt/'error.json'),source_seal=str(root/'B3_SOURCE_SEAL.json'),
        started_UTC=now(),Threads=1,P2_calls=0,native_budget_seconds=5400,wall_budget_seconds=None,target_gap=.005,
        algorithm_version=m['algorithm_version'],retry_starts_from_native_zero=False,previous_attempts=[])
    path=attempt/'request.json'
    if not path.exists():atomic(path,r)
    else:r=read(path)
    return path,r

def preflight(root):
    root=Path(root).resolve();m=verify_only(root)
    from v42_may_campaign_native90.common import environment
    environment(root/'preflight')
    from v42_may_campaign_native90.preflight import native_zero
    from v42_svr11.stages import inputs,b1_scope
    from v42_may_campaign_native90.a_stage import prepare as build,verify_case
    from v42_svr11.regression import source_paths
    start=time.perf_counter()
    def progress(v):atomic(root/'PREFLIGHT_PROGRESS.json',dict(v,worker=identity(),UTC=now(),wall_seconds=time.perf_counter()-start))
    path,r=request(root,m,dict(arm='B1',day=DAYS[0]))
    r=dict(r,output=str(root/'preflight/A1'))
    with scope(root/'CAMPAIGN_MANIFEST.json'),native_zero() as calls:
        for day in DAYS:
            for ref in m['input_receipts'][day]:
                if record(ref['path'])!=ref:raise PermissionError('B1_GLOBAL_RAW_INPUT_DRIFT:'+day)
        inputs(r,progress)
        with b1_scope(r,m):
            state=build(r,progress); verified=verify_case(state)
        del state
        routes=source_paths()
    if calls or not verified['PASS']:raise PermissionError('B1_GLOBAL_NATIVE0_MODEL_VERIFICATION_FAILED')
    atomic(root/'NATIVE0_PREFLIGHT.json',dict(PASS=True,source_SHA=m['execution_SHA'],operations_SHA=m['operations_SHA'],
        Native_calls=0,denied_native_attempts=calls,case_verification=verified,all31_raw_SHA_verified=True,
        Actual_code_paths=routes,solver_policy=record(SOURCE/'docs/v42_a_stage_fast_active_domain_20261007/SOLVER_POLICY.json'),
        model_build_wall_seconds=time.perf_counter()-start,UTC=now()))

def blocked_result(result):
    sci=result.get('scientific',{})
    if result.get('source_global_integrity_block') or sci.get('classification') in ('IMPLEMENTATION_FAILURE','INPUT_OR_SOURCE_FAILURE','INPUT_FAILURE'):
        return True
    reason=str(result.get('reason',''))+' '+str(sci.get('error',''))
    # Physical/QoS failures may be ValueError in the original source. Preserve
    # their date-local classification; only explicit integrity tokens block.
    if any(x in reason for x in ('SHA_DRIFT','SOURCE_DRIFT','AXIS','DATE_IDENTITY','BUNDLE','INPUT_FAILURE','GLOBAL_')):
        return True
    if any(x in reason.upper() for x in ('CONTROL_ACTIONS_INCOMPLETE','AC_NONCONVERGENCE',
            'AC_NON_CONVERGENCE','QOS_FAILURE','QOS_VIOLATION','WAN_VIOLATION','DEADLINE_VIOLATION',
            'VOLTAGE_VIOLATION','LINE_CURRENT_VIOLATION','TRANSFORMER_KVA_VIOLATION','SVR_RATING_VIOLATION')):
        return False
    if sci.get('classification') in ('PHYSICAL_FAILURE','TIME_LIMIT_NO_FEASIBLE','TIME_LIMIT_NO_VALID_INCUMBENT',
            'TIME_LIMIT_FEASIBLE_NOT_CERTIFIED','INCONCLUSIVE'):
        return False
    return bool(result.get('traceback') and not sci)

def summarized(row,result_path):
    from v42_svr11.controller import record_terminal
    result=record_terminal(row,result_path)
    row.update(planning_freeze_allowed=result.get('scientific',{}).get('accepted',False),
        Actual_fresh_AC_PASS=result.get('AC_status')=='AC PASS',original_result=record(result_path))
    return result

def reports(root,ledger,m):
    rows=list(ledger['dates'].values()); terminal=[r for r in rows if r['status'] in ('PASS','FAIL')]
    results=[read(r['result']) for r in terminal]
    actual=[r.get('metrics',{}).get('environments',{}).get('ACTUAL',{}) for r in rows]
    values=[a['maximum_line_loading'] for a in actual if a.get('maximum_line_loading') is not None]
    runtimes=[r.get('Native_Runtime') for r in results]
    report=dict(campaign_id=m['run_id'],status=ledger['status'],completed=len(terminal),total=31,
        PASS=sum(r['status']=='PASS' for r in rows),FAIL=sum(r['status']=='FAIL' for r in rows),
        all31_executed=len(terminal)==31,all31_PASS=len(terminal)==31 and all(r['status']=='PASS' for r in rows),
        maximum_Actual_line_loading=max(values) if values else None,
        mean_Actual_maximum_line_loading=statistics.mean(values) if values else None,
        physics_population='Every date with measured Actual, including physical FAIL; unavailable dates excluded',
        total_known_Native_Runtime=sum(r.get('known_completed_Native_Runtime',0) for r in results),
        total_Native_Runtime=None if any(x is None for x in runtimes) else sum(runtimes),
        wall_seconds=time.time()-ledger.get('start_epoch',time.time()),source_SHA=m['execution_SHA'],operations_SHA=m['operations_SHA'],
        hardware=m['hardware'],scenario=m['scenario'],thermal=m['thermal'],raw_input_SHA=m['input_receipts'],
        dates=rows,failures=[dict(day=r['day'],reason=r.get('reason'),result=r.get('result')) for r in rows if r['status']=='FAIL'],
        historical_B0_B1_comparison_status='Historical provenance only; different-source physics must remain explicitly labelled',UTC=now())
    atomic(root/'REPORT.json',report)
    lines=['# Source18r B1-only May 2025',f"{len(terminal)}/31 terminal; {report['PASS']} PASS; {report['FAIL']} FAIL.",
        'FULL feasibility, 0.5% global gap, Planning Freeze, and Actual Fresh AC are separate assertions.',
        f"Scientific source SHA: {m['execution_SHA']}",f"Operations SHA: {m['operations_SHA']}",
        '| Date | Status | FULL feasible | Gap certified | Freeze | Actual AC | Native s | Reason |',
        '|---|---|---|---|---|---|---|---|']
    for r in rows:lines.append('| '+' | '.join(str(x) for x in (r['day'],r['status'],r.get('FULL_feasible_certified'),r.get('global_gap_certified'),r.get('planning_freeze_allowed'),r.get('Actual_fresh_AC_PASS'),r.get('Native_Runtime'),r.get('reason','')))+' |')
    (root/'REPORT.md').write_text('\n\n'.join(lines)+'\n',encoding='utf8')
    return report

def sample_worker(root,row):
    try:
        p=psutil.Process(row['worker']['PID']);info=p.memory_info()
        obs=dict(identity(p),RSS_bytes=info.rss,Private_Commit_bytes=getattr(info,'private',None),
            peak_RSS_bytes=getattr(info,'peak_wset',info.rss),peak_Private_Commit_bytes=getattr(info,'peak_pagefile',None),memory=memory())
        atomic(root/'CURRENT_RESOURCE_SAMPLE.json',obs)
        with (root/'RESOURCE_HISTORY.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(obs)+'\n')
    except psutil.NoSuchProcess:pass

def run(root):
    root=Path(root).resolve();m=verify_only(root)
    if not read(root/'NATIVE0_PREFLIGHT.json')['PASS']:raise PermissionError('B1_PREFLIGHT_REQUIRED')
    with singleton(root/'SUPERVISOR.lock'):
        atomic(root/'SUPERVISOR_PROCESS.json',dict(identity(),root=str(root),source_SHA=m['execution_SHA'],operations_SHA=m['operations_SHA']))
        ledger=read(root/'CAMPAIGN_LEDGER.json');ledger.setdefault('start_epoch',time.time());last_report=0
        while True:
            try:
                verify_only(root)
                if (root/'STOP_REQUEST.json').exists():return
                peers=workers(root,m['execution_SHA'])
                if len(peers)>1 or any(p['arm']!='B1' for p in peers):raise PermissionError('B1_ONLY_GLOBAL_PEER_CONFLICT')
                running=[r for r in ledger['dates'].values() if r['status']=='RUNNING']
                for row in running:
                    r=read(row['request']); result=Path(r['result'])
                    if any(p['request']==row['request'] for p in peers):
                        row['worker']=next(p for p in peers if p['request']==row['request']);sample_worker(root,row);continue
                    if result.exists():
                        outcome=summarized(row,result)
                        if blocked_result(outcome):raise PermissionError('B1_ONLY_GLOBAL_IMPLEMENTATION_FAILURE:'+outcome.get('reason',''))
                    else:
                        native=[dict(receipt=record(p),ledger=read(p)) for p in result.parent.rglob('NATIVE_RUNTIME_LEDGER.json')]
                        atomic(result,dict(PASS=False,status='FAIL',arm='B1',day=row['day'],reason='PROCESS_EXIT_WITHOUT_RESULT',
                            Native_Runtime=None,unknown_inflight_runtime=True,preserved_native_ledgers=native,UTC=now()))
                        summarized(row,result)
                pending=[r for r in ledger['dates'].values() if r['status']=='NOT_EXECUTED']
                if not pending and not peers:
                    ledger.update(status='COMPLETE',UTC=now());atomic(root/'CAMPAIGN_LEDGER.json',ledger)
                    reports(root,ledger,m);atomic(root/'CAMPAIGN_COMPLETION.json',dict(all_dates_terminal=True,total=31,no_policy_transition=True,UTC=now()));return
                if not peers and pending:
                    ok,obs=admitted(root,m);atomic(root/'LATEST_ADMISSION.json',dict(obs,admitted=ok))
                    if not ok:ledger.update(status='WAIT_RESOURCE',resource_wait=obs)
                    else:
                        row=pending[0];path,r=request(root,m,row)
                        if row['attempts']:raise PermissionError('B1_GLOBAL_DUPLICATE_DATE_ATTEMPT')
                        row.update(status='RUNNING',request=str(path),attempts=[str(path)])
                        atomic(root/'CAMPAIGN_LEDGER.json',ledger)
                        with (path.parent/'WORKER_STDOUT.log').open('ab') as log:
                            p=subprocess.Popen([sys.executable,'-B','-X','utf8','-m','v42_svr11.worker',str(path)],cwd=SOURCE,
                                stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS)
                        peer=dict(identity(psutil.Process(p.pid)),arm='B1',day=row['day'],worker_slot=1,request=str(path))
                        row['worker']=peer;peers=[peer];ledger['status']='RUNNING'
                elif peers:ledger['status']='RUNNING'
                ledger.update(active_workers=peers,supervisor=identity(),UTC=now());atomic(root/'CAMPAIGN_LEDGER.json',ledger)
                atomic(root/'SUPERVISOR_HEARTBEAT.json',dict(identity(),policy='B1',source_SHA=m['execution_SHA'],operations_SHA=m['operations_SHA'],UTC=now()))
                if time.monotonic()-last_report>60:reports(root,ledger,m);last_report=time.monotonic()
                time.sleep(5)
            except Exception as e:
                ledger.update(status='GLOBAL_INTEGRITY_ERROR',error=repr(e),UTC=now());atomic(root/'CAMPAIGN_LEDGER.json',ledger)
                atomic(root/'GLOBAL_SYSTEM_ERROR.json',dict(error=repr(e),traceback=traceback.format_exc(),UTC=now()));reports(root,ledger,m);raise

def safeguard(root):
    root=Path(root).resolve();m=verify_only(root)
    with singleton(root/'WATCHDOG.lock'):
        if (root/'STOP_REQUEST.json').exists() or (root/'GLOBAL_SYSTEM_ERROR.json').exists():return
        if (root/'CAMPAIGN_COMPLETION.json').exists():return
        receipt=read(root/'SUPERVISOR_PROCESS.json') if (root/'SUPERVISOR_PROCESS.json').exists() else {}
        if not live(receipt):
            with (root/'SUPERVISOR_STDOUT.log').open('ab') as log:
                subprocess.Popen([sys.executable,'-B','-X','utf8',str(__file__),'run',str(root)],cwd=SOURCE,
                    stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS)
        receipt=read(root/'MONITOR_PROCESS.json') if (root/'MONITOR_PROCESS.json').exists() else {}
        if not live(receipt):
            with (root/'MONITOR_STDOUT.log').open('ab') as log:
                subprocess.Popen([sys.executable,'-B','-X','utf8',str(__file__),'monitor',str(root)],cwd=SOURCE,
                    stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS)
        atomic(root/'WATCHDOG_LAST_RUN.json',dict(identity(),source_SHA=m['execution_SHA'],UTC=now()))

def monitor(root):
    import v42_svr11.monitor as ui
    ui.ORDER=('B1',)
    ui.PAGE=ui.PAGE.replace('/ 124','/ 31').replace('B0 → B2 → B1 → B3','B1 only').replace('<option>B0</option>','').replace('<option>B2</option>','').replace('<option>B3</option>','')
    original=ui.snapshot
    def enhanced(root):
        v=original(root);v.update(memory=memory(),disk_free_bytes=shutil.disk_usage(root).free,
            campaign_id=read(Path(root)/'CAMPAIGN_MANIFEST.json')['run_id'],supervisor_heartbeat=read(Path(root)/'SUPERVISOR_HEARTBEAT.json') if (Path(root)/'SUPERVISOR_HEARTBEAT.json').exists() else None)
        for peer in v['workers']:
            row=next(r for r in v['dates'] if r['day']==peer['day']);r=read(row['request']);p=read(r['progress']) if Path(r['progress']).exists() else {}
            scientific_path=Path(r['output'])/'A_RESULT.json'
            sci=read(scientific_path) if scientific_path.exists() else p
            peer.update(CPU_seconds=identity(psutil.Process(peer['PID']))['CPU_seconds'],heartbeat=p.get('UTC'),
                Native_remaining_seconds=p.get('native_remaining_seconds'),FULL_feasible_certified=sci.get('FULL_feasible_certified'),
                global_gap_certified=sci.get('global_gap_certified'),Planning_rho_max=sci.get('UB'),
                resource_sample=read(Path(root)/'CURRENT_RESOURCE_SAMPLE.json') if (Path(root)/'CURRENT_RESOURCE_SAMPLE.json').exists() else None)
        return v
    ui.snapshot=enhanced
    ui.PAGE=ui.PAGE.replace('</main><script>','<details><summary>RAM / Commit · CPU · Heartbeat · Native budget · certificates</summary><pre id="telemetry"></pre></details></main><script>')
    ui.PAGE=ui.PAGE.replace('days()}catch(e)',"days();telemetry.textContent=JSON.stringify({campaign:state.campaign_id,memory:state.memory,disk_free_bytes:state.disk_free_bytes,supervisor:state.supervisor_heartbeat,workers:state.workers},null,2)}catch(e)")
    ui.serve(root,PORT)

if __name__=='__main__':
    command=sys.argv[1];root=Path(sys.argv[2]) if len(sys.argv)>2 else DEFAULT_ROOT
    globals()[command](root)


