"""Gate-controlled orchestration handoff. Running DA/Fresh children are adopted."""
from pathlib import Path
import os,sys,json,time,hashlib,shutil,subprocess,psutil,ast
HERE=Path(__file__).resolve().parent;OLD=HERE.parent;ROOT=OLD.parents[1]
NEW=ROOT/'frozen_artifacts/v41r4_actual_eta95_qsafe_robust_v2_perf1'
CLASS='PERFORMANCE_ONLY_EXACT_EQUIVALENT_ACCELERATION_PASS'
ENGINE_SHA='9c59ea14a472e7d9308ca5ae6b104347165c2676524ecae2ae24c8a393e2d6e9'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+'.adopt.tmp')
    tmp.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
    for n in range(101):
        try:os.replace(tmp,p);return
        except PermissionError:
            if n==100:raise
            time.sleep(.05)
def stage():
    assert sha(HERE/'cached_engine.py')==ENGINE_SHA
    assert not (NEW/'PERFORMANCE_FREEZE.json').exists(),'ALREADY_FROZEN'
    NEW.mkdir(parents=True,exist_ok=True)
    names=['binding.py','actual_worker.py','robust_search.py','input_adapter.py','METHOD_FREEZE.json','METHOD_CODE_BINDING.json','BATTERY_EFFICIENCY_AUTHORITY.json','COHORTS.json','ACTUAL_METHOD_AUTHORITY.md','report_candidate.py','HANDOFF_SNAPSHOT.json','TEMPORARY_RESOURCE_POLICY.json']
    for name in names:shutil.copy2(OLD/name,NEW/name)
    shutil.copytree(OLD/'frozen_code',NEW/'frozen_code',dirs_exist_ok=True)
    shutil.copy2(HERE/'cached_engine.py',NEW/'cached_engine.py')
    shutil.copy2(HERE/'performance_worker_template.py',NEW/'performance_worker.py')
    source=(OLD/'dispatcher.py').read_text(encoding='utf-8')
    source=source.replace("str(OUT/'actual_worker.py')","str(OUT/'performance_worker.py')")
    assert "[str(OUT/'performance_worker.py'),day,policy]" in source
    # Fresh output starts on May01, independent of development/holdout ordering.
    source=source.replace("days=method['development_days']+method['holdout_days']","days=sorted(method['all_days'])")
    source=source.replace("Actual_method=method['version']","Actual_method=method['version'],Actual_implementation='EXACT_STATE_RESTORE_REUSABLE_ENGINE_PERF1'")
    (NEW/'dispatcher.py').write_text(source,encoding='utf-8');ast.parse(source)
    report=(NEW/'report_candidate.py').read_text(encoding='utf-8')
    report=report.replace('Q runtime includes causal replay and prefix restoration;', 'Q runtime includes causal replay using exact slot-start restoration and a reusable engine;')
    report=report.replace("result=dict(status=status,","result=dict(performance_implementation='EXACT_STATE_RESTORE_REUSABLE_ENGINE_PERF1',performance_freeze_SHA=sha(OUT/'PERFORMANCE_FREEZE.json'),status=status,")
    (NEW/'report_candidate.py').write_text(report,encoding='utf-8');ast.parse(report)
    for name,h in read(OLD/'METHOD_CODE_BINDING.json')['files'].items():assert sha(NEW/name)==h
    for p in (NEW/'frozen_code').rglob('*.py'):assert sha(p)==sha(OLD/'frozen_code'/p.relative_to(NEW/'frozen_code'))
    files={str(p.relative_to(NEW)):sha(p) for p in NEW.rglob('*.py')}
    files.update({n:sha(NEW/n) for n in ['METHOD_FREEZE.json','METHOD_CODE_BINDING.json','BATTERY_EFFICIENCY_AUTHORITY.json']})
    save(NEW/'STAGED_IMPLEMENTATION.json',dict(status='STAGED_NOT_AUTHORIZED_TO_RUN',files=files,scientific_sources_byte_identical=True))
    save(NEW/'ACTUAL_DISPATCH_HOLD.json',dict(status='HOLD',reason='Await May12 B3 exact full-day PASS'))
    save(NEW/'DIAGNOSTIC_QUEUE.json',[])
    print('PERFORMANCE_NAMESPACE_STAGED',NEW,flush=True)

def adopt():
    gate=HERE/'MAY12_FINAL_EQUIVALENCE_GATE.json';g=read(gate)
    assert g['status']=='PASS' and g['classification']==CLASS and g['slots']==96
    assert all(g['checks'].values()) and g['performance_engine_SHA']==ENGINE_SHA==sha(HERE/'cached_engine.py')
    assert g['scientific_method_SHA']==sha(OLD/'METHOD_FREEZE.json')==sha(NEW/'METHOD_FREEZE.json')
    staged=read(NEW/'STAGED_IMPLEMENTATION.json');assert all(sha(NEW/p)==h for p,h in staged['files'].items())
    for p,h in g['files'].items():assert sha(p)==h,('GATE_EVIDENCE_DRIFT',p)
    if (NEW/'ADOPTION_COMPLETE.json').exists():return read(NEW/'ADOPTION_COMPLETE.json')
    evidence=NEW/'evidence';evidence.mkdir(exist_ok=True)
    for name in ['MAY12_FINAL_EQUIVALENCE_GATE.json','MAY12_FINAL_EQUIVALENCE_REPORT.md','AUDIT_REDUCTION_AUTHORITY.json','SELECTED_Q_GATE_AUTHORITY.json','RESULT.json','FULL_EQUIVALENCE_RESULT.json']:
        shutil.copy2(HERE/name,evidence/name)
    implementation={p:h for p,h in staged['files'].items() if p.endswith('.py')}
    freeze=dict(status='FROZEN_PERFORMANCE_ONLY_IMPLEMENTATION',classification=CLASS,at=time.time(),validation_scope=g.get('validation_scope'),old_full_day_search_selection_equivalence_not_claimed=g.get('old_full_day_search_selection_equivalence_not_claimed',False),gate_SHA=sha(gate),gate_path=str(evidence/gate.name),performance_engine_SHA=ENGINE_SHA,scientific_method_SHA=g['scientific_method_SHA'],implementation_files=implementation,scientific_search_unchanged=True,heavy_prefix_fallback='FAIL_CLOSED_DISABLED',maximum_Actual_workers=2,common_worker_cap=4,temporary_DA_Actual_split=[2,2])
    save(NEW/'PERFORMANCE_FREEZE.json',freeze)
    binding=read(OLD/'EXECUTION_BINDING.json');binding.update(status='SEALED_PERFORMANCE_ONLY_EXACT_EQUIVALENT',sealed_at=time.time(),classification=CLASS,files=implementation,performance_freeze_SHA=sha(NEW/'PERFORMANCE_FREEZE.json'))
    save(NEW/'EXECUTION_BINDING.json',binding)
    # Read-only bootstrap verification: imports and dependency binding, no replay.
    env=os.environ.copy();env['PYTHONPATH']=str(ROOT);env['PYTHONDONTWRITEBYTECODE']='1'
    for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='1'
    with (NEW/'BOOTSTRAP_VERIFICATION.log').open('x',encoding='utf-8') as log:
        subprocess.run([sys.executable,'-c','import performance_worker; performance_worker.install(); print("BINDING_PASS_NO_REPLAY")'],cwd=NEW,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    oldstate=read(OLD/'DISPATCHER_STATE.json');parent=psutil.Process(oldstate['supervisor_pid'])
    assert any(str(x).replace('\\','/')==str(OLD/'dispatcher.py').replace('\\','/') for x in parent.cmdline())
    parent.suspend()
    try:
        oldstate=read(OLD/'DISPATCHER_STATE.json');save(NEW/'PRE_HANDOFF_STATE.json',oldstate)
        live=[]
        for r in oldstate['active']:
            try:p=psutil.Process(r['worker_pid'])
            except psutil.NoSuchProcess:continue
            if p.create_time()!=r['created_at']:continue
            if r['kind']=='DIAGNOSTIC_ONLY':
                assert r['worker_pid']==os.getpid(),'UNEXPECTED_RUNNING_AUDIT_AT_ADOPTION'
                continue
            assert r['kind']=='DA_FRESH','UNEXPECTED_HEAVY_ACTUAL_AT_ADOPTION'
            live.append(r)
        assert len(live)<=4
        resumed={**oldstate,'active':live,'external_workers':[],'Actual_completed_units':0,'blocked':[r for r in oldstate['blocked'] if not r[1].startswith(('FINAL_96_GATE','EXACT_'))],'errors':[r for r in oldstate['errors'] if not r['phase'].startswith(('FINAL_96_GATE','EXACT_'))]}
        save(NEW/'DISPATCHER_STATE.json',resumed)
        save(NEW/'SWITCH_STATUS.json',dict(legacy_coordinator_suspended_pid=parent.pid,expensive_workers_untouched=True))
        shutil.copy2(OLD/'TEMPORARY_RESOURCE_POLICY.json',NEW/'TEMPORARY_RESOURCE_POLICY.json')
        save(NEW/'ACTUAL_DISPATCH_HOLD.json',dict(status='RELEASED_AFTER_PASS',classification=CLASS,gate_SHA=sha(gate),at=time.time()))
        parent.terminate();parent.wait(timeout=10)
    except BaseException:
        try:parent.resume()
        except psutil.NoSuchProcess:pass
        raise
    pointer=ROOT/'frozen_artifacts/v41r4_may/audit/ACTUAL_EXECUTION_METHOD_CURRENT.json'
    prior=read(pointer);save(NEW/'PREVIOUS_ACTUAL_METHOD_POINTER.json',prior)
    for name in ['ACTUAL_METHOD_AUTHORITY.md']:
        with (NEW/name).open('a',encoding='utf-8') as f:f.write('\n\nPerformance implementation: '+CLASS+'. Approved by the user-reduced May12 B3 gate: lightweight search once and exact old-engine validation of the selected 96 Q vectors. Old full-day search selection identity is not claimed. Scientific search unchanged; slot-start state restoration and reusable engine only. Unsupported acceleration state fails closed without heavy replay.\n')
    updated={**prior,'namespace':str(NEW),'implementation':'EXACT_STATE_RESTORE_REUSABLE_ENGINE_PERF1','performance_classification':CLASS,'performance_freeze_SHA':sha(NEW/'PERFORMANCE_FREEZE.json'),'source_binding_SHA':sha(NEW/'EXECUTION_BINDING.json'),'authority_document':str(NEW/'ACTUAL_METHOD_AUTHORITY.md'),'report':str(NEW/'ACTUAL_METHOD_REPORT.html'),'dispatcher_state':str(NEW/'DISPATCHER_STATE.json'),'updated_at':time.time()}
    save(pointer,updated)
    second=ROOT/'frozen_artifacts/v41r4_may/loop_wall_v4/audit/ACTUAL_EXECUTION_METHOD_CURRENT.json'
    save(second,updated)
    with (NEW/'dispatcher.stdout.log').open('x',encoding='utf-8') as out,(NEW/'dispatcher.stderr.log').open('x',encoding='utf-8') as err:
        proc=subprocess.Popen([sys.executable,'-u',str(NEW/'dispatcher.py')],cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
    result=dict(status='COMPLETE',classification=CLASS,new_namespace=str(NEW),new_supervisor_pid=proc.pid,adopted_DA_Fresh_workers=[r['worker_pid'] for r in live],hard_killed_DA_Fresh_workers=0,at=time.time(),start_from='2025-05-01',max_Actual_workers=2,total_worker_cap=4)
    save(NEW/'ADOPTION_COMPLETE.json',result);save(HERE/'LIGHTWEIGHT_ADOPTION_COMPLETE.json',result)
    return result

if __name__=='__main__':
    if sys.argv[1:] == ['--stage']:stage()
    else:print(json.dumps(adopt()),flush=True)
