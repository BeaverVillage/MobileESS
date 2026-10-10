"""Read-only operational helper review; writes only this separate audit directory."""
from pathlib import Path
import ast, hashlib, json, subprocess
from datetime import datetime, timezone
import psutil

REPO=Path('D:/MobileESS_v42_autonomous')
ROOT=Path('D:/v42_may_restart_20261010_02')
OUT=Path(__file__).parent
RAW=OUT/'source32_helper_review_raw'
RAW.mkdir(exist_ok=False)
read_cache={}

def receipt(path, data=None):
    path=Path(path).resolve()
    if data is None:data=path.read_bytes()
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())

def capture(path):
    path=Path(path).resolve()
    if path in read_cache:return read_cache[path]
    data=path.read_bytes()
    suffix=path.name
    target=RAW/(f'{len(read_cache):03d}_'+suffix)
    with target.open('xb') as stream:stream.write(data)
    entry=dict(source=receipt(path,data),snapshot=receipt(target,data),source_read_count=1,data=data)
    read_cache[path]=entry
    return entry

def doc(path):return json.loads(capture(path)['data'].decode('utf-8-sig'))
def text(path):return capture(path)['data'].decode('utf-8-sig')

checks=[]
def require(condition, name):
    assert condition,name
    checks.append(dict(name=name,PASS=True))

names=('freeze_sparse_v32.py','smoke_sparse_v32.py','prepare_verified_v32_zero_start_retries.py','build_v32_validation_template.py')
helpers={name:text(ROOT/'autonomous'/name) for name in names}
for name,source in helpers.items():ast.parse(source);checks.append(dict(name='syntax:'+name,PASS=True))
freeze=helpers[names[0]];smoke=helpers[names[1]];prepare=helpers[names[2]];binding=helpers[names[3]]
require("target=Path('D:/v42run32').resolve()" in freeze and 'and not target.exists()' in freeze,'D32 exact nonoverwrite freeze target')
require("sys.path.insert(0,'D:/v42run32')" in smoke and "CODE=Path('D:/v42run32')" in smoke,'D32 import/source smoke root')
require("code=Path('D:/v42run32')" in prepare,'D32 request and execution root')
require('recovery.assert_lease(root,args.lease_token)' in prepare,'owned existing manual lease required')
require("assert not any(x.exists() for x in (manifest_path,validation,prepared))" in prepare,'prepare artifacts not overwritten')
require("Path(row['path']).resolve().relative_to(Path('D:/v42run30')).as_posix()" in binding,'historical Source30 assets rebound by relative path')
require("changed=={'v42_autonomous_b2/f1_basis.py','v42_autonomous_b2/worker.py'}" in binding,'exact two execution changes required')
require("d['source_file_records']==records" in binding and "d['execution_sources']==ex and d['execution_SHA']==sha" in binding,'owner and independent complete declared sources strictly bound')
require("('source_start_end_identical','execution_start_end_identical','test_start_end_identical')" in binding and "d['Native_optimize_calls']==0 and d['real_Native_model_constructions']==0" in binding,'current tests start/end and Native/model zero required')
require("'01':'repair_b2_v27_01_s3','02':'repair_b2_v27_01_s1','03':'repair_b2_v27_01_s2'" in prepare,'first three fallback real Source27 historical attempts')
require("latest_doc.get('PASS') is False" in prepare and "latest_doc.get('identity',{}).get('day')==day" in prepare,'latest current measured FAIL preferred over fallback')
require("previous_attempts=[]" in prepare and "prior_attempts={}" in prepare and "USER_ZERO_START_RETRY_AUTHORIZATION.json" in prepare,'fresh zero authorized request with no prior budget/checkpoint admission')
require('for slot in (1,2,3):' in prepare and 'for short,old_attempt in old_attempts.items():' in prepare,'nine dates by three worker slots prepared')
require("retry_priority=1000 if day[-2:] in ('01','02','03') else 100" in prepare,'first three verified repair priority')
require("with patch.object(gp,'Model',side_effect=AssertionError('NATIVE_MODEL_FORBIDDEN')):" in prepare and "with pricing_cache.create_scope(request,manifest,ROOT):pass" in prepare,'public cache and scoped runner factories model denied')
require("runner=rmp_presolve.scoped_runner(dw.run,routes['output_directory'],routes['write'])" in prepare,'existing scoped RMP factory admitted')
require("runpy.run_module('v42_autonomous_b2.worker',run_name='__main__')" in prepare and "patch.object(canonical_worker,'run',canonical_admission)" in prepare,'actual m CLI dispatch exercised with canonical admission stub')
require("budget=object.__new__(canonical_worker.ReceiptDateBudget)" in prepare and 'type(budget) is rmp_presolve.ReceiptDateBudget' in prepare,'canonical budget exact class without init or ledger')
require("rmp_presolve._method(budget,'optimize',rmp_presolve._ORIGINAL_RECEIPT_OPTIMIZE)" in prepare and "rmp_presolve._method(budget,'native_optimize',rmp_presolve._ORIGINAL_NATIVE_OPTIMIZE)" in prepare,'canonical actual original budget descriptors checked')
require("except SystemExit as exited:assert exited.code is None" in prepare and "assert entered==[sys.argv[1]]" in prepare and "assert not Path(request['output']).exists()" in prepare,'CLI SystemExit consumed and mandatory post assertions retained')
require("expected_unstarted_source=read(root/'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json')['execution_SHA']" in prepare and "assert len(prior_ready)==1 and prior_ready[0]['repair_source_SHA']==expected_unstarted_source" in prepare,'only single unstarted prior Source30 READY supersession candidate')
require('supersede_queue_id=prior_ready[0]' in prepare and 'recovery.enqueue(root,failure,repair,lease_token=args.lease_token,**options)' in prepare,'locked recovery guard owns actual supersession')
require("actual_Source32_Native_performance_pending=True" in binding and 'final_gap_PASS_claimed=False' in binding,'Native0 evidence does not claim actual date PASS or performance')

worker=text(REPO/'v42_autonomous_b2/worker.py')
require("from v42_autonomous_b2.worker import run as canonical_run" in worker and "raise SystemExit(canonical_run(a.request))" in worker,'production CLI delegates exact canonical worker run')
recovery=text(REPO/'v42_autonomous/recovery.py')
require("with os_lock(root / 'RECOVERY_QUEUE.lock'):" in recovery and 'not _unstarted_ready(previous)' in recovery and 'not _supervisor_preserves_unstarted_target(root,previous)' in recovery,'queue locked plus actual active ownership exclusion')
require('proof is not None and _unstarted_ready(row)' in recovery,'verified PASS retirement only unstarted candidate')

m30=doc(ROOT/'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json')
declared=dict(m30['builder_original_sources']);declared.update(m30['execution_sources'])
records={name:receipt(REPO/name) for name in declared}
execution={name:records[name]['sha256'] for name in m30['execution_sources']}
execution_sha=hashlib.sha256(json.dumps(execution,sort_keys=True,separators=(',',':')).encode()).hexdigest()
changed=[name for name in execution if execution[name]!=m30['execution_sources'][name]]
require(set(changed)=={'v42_autonomous_b2/f1_basis.py','v42_autonomous_b2/worker.py'},'actual current execution two file delta')
require(all(records[name]['sha256']==value for name,value in m30['builder_original_sources'].items()),'all 1007 original sources unchanged')
require(records['v42_autonomous_b2/f1_basis.py']['sha256']=='87ef6292421aa4122b52356e2fdb09d9ce3d50564aec2fb41758ef2021685165','stable Source31 F1 basis byte identical in Source32')
require(len(records)==1105 and len(execution)==98,'actual complete 1105 source and execution98 records')

registry=doc(ROOT/'AUTONOMOUS_MANIFEST.json');cp=doc(ROOT/'SUPERVISOR_STATE.json');queue=doc(ROOT/'RECOVERY_QUEUE.json')
require(Path(registry['B2_code_root']).resolve()==Path('D:/v42run30').resolve(),'actual future source pointer still Source30 at review snapshot')
require(not (ROOT/'B2_V31_ZERO_START_DEPLOYMENT_MANIFEST.json').exists(),'Source31 deployment manifest absent')
require(not (ROOT/'B2_V32_ZERO_START_DEPLOYMENT_MANIFEST.json').exists(),'Source32 deployment manifest absent at static review snapshot')
require(not any(row.get('repair_code_root')=='D:\\v42run31' for row in queue['entries']),'Source31 no current or historical recovery queue from candidate')
freeze31=doc(ROOT/'autonomous/V31_SPARSE_IMMUTABLE_FREEZE.json')
require(freeze31['PASS'] is True and Path(freeze31['code_root']).resolve()==Path('D:/v42run31').resolve(),'Source31 immutable freeze remains historical evidence')
ready=[dict(day=row['date'],source=row['repair_source_SHA'],queue_id=row['queue_id']) for row in queue['entries'] if row.get('verification_status')=='READY_VERIFIED_REPAIR']
actual_workers=[]
for key,entry in cp['workers'].items():
    request=doc(entry['request'])
    pid=entry.get('PID',entry.get('pid',entry.get('process',{}).get('PID')))
    if pid is None:
        # Preserve the entire controller row when process metadata is nested differently.
        actual_workers.append(dict(key=key,controller=entry,request=capture(entry['request'])['source']));continue
    try:
        process=psutil.Process(pid)
        observed=dict(PID=pid,create_time=process.create_time(),cmdline=process.cmdline(),cwd=process.cwd())
    except psutil.Error as error:observed=dict(PID=pid,observation_error=type(error).__name__)
    actual_workers.append(dict(key=key,controller=entry,request=capture(entry['request'])['source'],observed=observed))

prep30=doc(ROOT/'autonomous/V30_ZERO_START_RETRY_PREPARATION.json')
failures=[]
for short in ('01','02','03'):
    day='2025-05-'+short
    candidates=[]
    for row in prep30['requests_by_day_and_slot'][day].values():
        path=Path(row['path']).parent/'RESULT.json'
        if path.is_file():candidates.append(path)
    require(len(candidates)==1,'exact one Source30 completed result '+day)
    path=candidates[0];result=doc(path);ledger=doc(path.parent/'NATIVE_RUNTIME_LEDGER.json')
    require(result['PASS'] is False and result['source_SHA']==m30['execution_SHA'] and result['identity']['day']==day,'real current Source30 failure '+day)
    failures.append(dict(day=day,status=result['status'],PASS=result['PASS'],Native_Runtime=result['Native_Runtime'],scientific_error=result.get('scientific',{}).get('error'),result=capture(path)['source'],ledger=capture(path.parent/'NATIVE_RUNTIME_LEDGER.json')['source']))

snapshots=[{key:value for key,value in entry.items() if key!='data'} for entry in read_cache.values()]
report=dict(schema='V42_SOURCE32_OPERATIONAL_HELPERS_STATIC_READ_ONLY_REVIEW_V1',UTC=datetime.now(timezone.utc).isoformat(),PASS=True,
    scope='Static read-only operational review, not scientific independent review, factory execution, deployment or actual date PASS',
    checks=checks,helpers={name:capture(ROOT/'autonomous'/name)['source'] for name in names},
    execution_SHA=execution_sha,execution_sources=execution,source_file_records=records,
    original_source_count=1007,execution_source_count=98,changed_from_Source30=changed,
    Source31_status='FROZEN_PRESERVED_NOT_DEPLOYED_KNOWN_CLI_FAILURE_UNREPAIRED',Source32_status='STATIC_HELPERS_REVIEWED_OWNER_AND_INDEPENDENT_TESTS_PENDING_DEPLOYMENT_NOT_EXECUTED_BY_REVIEWER',
    Source30_current_real_first_three_failures=failures,current_worker_snapshot=actual_workers,
    current_READY_snapshot=ready,supersession_scope='Dynamic existing unstarted Source30 READY only; current active May04/05/06 excluded by recovery lock and OS ownership guards',
    CLI_admission_semantics='actual -m dispatch enters canonical run stub; object.__new__ checks class/delegates without budget init or ledger; catches SystemExit(None) then asserts exact call and output absence',
    CLI_factory_diagnostic_limits='Admission factory creates no Native models; dispatcher stub verifies canonical entry and descriptors, not a full real RMP Native run or final certification',
    validation_scope='Current owner/independent complete1105/execution98/start-end/model0 receipt checks are required by template. Unchanged historical cache120/RMP72 tests are explicitly carried, not claimed rerun.',
    Native_optimize_calls=0,real_Native_model_constructions=0,helpers_executed=0,
    production_code_changes=0,immutable_changes=0,queue_or_manifest_changes=0,process_actions=0,git_mutations=0,
    actual_Source32_Native_performance_pending=True,final_gap_PASS_claimed=False,
    raw_single_read_snapshots=snapshots,source_script=receipt(__file__))
target=OUT/'SOURCE32_OPERATIONAL_HELPERS_STATIC_READ_ONLY_REVIEW.json'
with target.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps(dict(PASS=True,receipt=receipt(target),checks=len(checks),execution_SHA=execution_sha,ready=len(ready),failures=failures),ensure_ascii=False))
