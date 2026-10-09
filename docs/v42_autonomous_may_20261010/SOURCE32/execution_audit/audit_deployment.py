"""Independent deployment execution audit; Native/model/process/production read-only."""
from pathlib import Path
import json,hashlib,subprocess,urllib.request
from datetime import datetime,timezone
import psutil

ROOT=Path('D:/v42_may_restart_20261010_02');CODE=Path('D:/v42run32');OUT=Path(__file__).parent
RAW=OUT/'post_deployment_raw';RAW.mkdir(exist_ok=False)
records=[];cache={};checks=[]
SOURCE='9c159a8c64e6a7494aecf41266c0289e16cd65f6ee9eddf3de9f113593156ba9'
COMMIT='6997c0ac54a8d46f345bb99d9b3cf18ffb199a30'
def rec(path,data=None):
    path=Path(path).resolve();data=path.read_bytes() if data is None else data
    return dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
def capture(path):
    path=Path(path).resolve()
    if path in cache:return cache[path]
    data=path.read_bytes();target=RAW/(f'{len(records):03d}_'+path.name)
    with target.open('xb') as stream:stream.write(data)
    row=dict(source=rec(path,data),snapshot=rec(target,data),source_read_count=1)
    records.append(row);cache[path]=(data,row);return cache[path]
def doc(path):return json.loads(capture(path)[0].decode('utf-8-sig'))
def require(value,label):
    assert value,label
    checks.append(dict(PASS=True,name=label))
def same_record(row):return rec(row['path'])==row

baseline=doc(OUT/'SOURCE32_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json')
require(baseline['PASS'] is True,'baseline sealed PASS')
registry=doc(ROOT/'AUTONOMOUS_MANIFEST.json')
manifest_path=ROOT/'B2_V32_ZERO_START_DEPLOYMENT_MANIFEST.json';manifest=doc(manifest_path)
freeze=doc(ROOT/'autonomous/V32_SPARSE_IMMUTABLE_FREEZE.json')
smoke=doc(ROOT/'autonomous/V32_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json')
validation=doc(ROOT/'autonomous/V32_VERIFIED_REPAIR_VALIDATION.json')
preparation=doc(ROOT/'autonomous/V32_ZERO_START_RETRY_PREPARATION.json')
deployment=doc(ROOT/'autonomous/V32_ZERO_START_RETRY_DEPLOYMENT.json')
queue=doc(ROOT/'RECOVERY_QUEUE.json');cp=doc(ROOT/'SUPERVISOR_STATE.json')
resume_observation=doc(OUT/'SOURCE32_ENQUEUE_PARTIAL_RESUME_READ_ONLY_OBSERVATION.json')
require(all(x['PASS'] is True for x in (freeze,smoke,validation,preparation,deployment)),'five actual deployment receipts PASS')
require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=CODE,text=True).strip()==COMMIT,'actual D32 HEAD commit')
require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=CODE,text=True).strip(),'actual D32 tracked source clean')
require(registry['B2_source_SHA']==SOURCE and Path(registry['B2_code_root']).resolve()==CODE,'actual future pointer Source32')
require(Path(registry['B2_deployment_manifest']).resolve()==manifest_path and registry['B2_manifest']==rec(manifest_path),'registry manifest exact SHA')
require(manifest['source_commit']==COMMIT and manifest['execution_SHA']==SOURCE and len(manifest['execution_sources'])==98 and len(manifest['builder_original_sources'])==1007,'current sealed98/1007 manifest identity')
require(manifest['prior_attempts']=={} and manifest['restart_from_zero'] is True,'manifest fresh zero no carry')
old30=doc(ROOT/'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json')
require(manifest['builder_original_sources']==old30['builder_original_sources'],'all1007 original science map unchanged')
require(freeze['commit']==COMMIT and Path(freeze['code_root']).resolve()==CODE and freeze['unique_file_count']==1110,'actual freeze1110 source identity')
for row in freeze['source_files']:require(same_record(row),'frozen SHA '+Path(row['path']).relative_to(CODE).as_posix())
require(len(freeze['source_files'])==1110,'full frozen file inventory1110')
for name,sha in {**manifest['builder_original_sources'],**manifest['execution_sources']}.items():require(rec(CODE/name)['sha256']==sha,'manifest declared file '+name)
require(validation['repair_source_SHA']==SOURCE and validation['repair_commit_SHA']==COMMIT and Path(validation['repair_code_root']).resolve()==CODE,'repair validation current D32 source+commit')
for field,count in (('source_files',98),('original_source_files',1007),('sparse_required_additional_assets',5)):
    require(len(validation[field])==count,'validation exact count '+field)
    for row in validation[field]:require(same_record(row),'validation file '+Path(row['path']).relative_to(CODE).as_posix())
require(smoke['execution_SHA']==SOURCE and smoke['Native_optimize_calls']==0 and smoke['model_constructions']==0,'actual sparse Native/model denied import smoke')
require(preparation['all_27_sealed_request_native_denied_admissions_PASS'] is True and preparation['all_27_actual_m_dispatch_canonical_budget_descriptor_admissions_PASS'] is True,'actual all27 public factories and canonical CLI admissions PASS')
require(preparation['Native_optimize_calls']==0 and preparation['model_constructions']==0,'actual preparation Native/models zero')

fresh_requests=[]
for day,by_slot in preparation['requests_by_day_and_slot'].items():
    require(set(by_slot)=={'1','2','3'},'all three slot requests '+day)
    for slot,row in by_slot.items():
        request=doc(row['path']);actual_rec=capture(row['path'])[1]['source']
        require(actual_rec==row,'sealed exact request '+day+'/'+slot)
        attempt=ROOT/'dates/B2'/day/'attempts'/request['attempt_id']
        require(request['day']==day and request['arm']=='B2' and request['worker_slot']==int(slot),'fresh identity '+day+'/'+slot)
        require(request['implementation_SHA']==SOURCE and request['deployment_SHA']==SOURCE and request['manifest_SHA']==rec(manifest_path)['sha256'],'fresh source bindings '+day+'/'+slot)
        require(request['restart_from_zero'] is True and request['previous_attempts']==[] and request['native_budget_seconds']==5400,'fresh authorized Native0/5400 '+day+'/'+slot)
        require(request['reset_authorization']==manifest['reset_authorization'] and same_record(request['reset_authorization']),'sealed reset authorization '+day+'/'+slot)
        require(Path(row['path']).resolve()==attempt/'request.json','exact owned fresh directory '+day+'/'+slot)
        no_started={name: not (attempt/name).exists() for name in ('RESULT.json','NATIVE_RUNTIME_LEDGER.json','progress.json','error.json','output')}
        require(all(no_started.values()),'all request outputs absent before Native '+day+'/'+slot)
        fresh_requests.append(dict(day=day,slot=int(slot),request=actual_rec,output_absence=no_started))
require(len(fresh_requests)==27,'actual all27 distinct fresh requests before Native')

by_id={row['queue_id']:row for row in queue['entries']}
current=[row for row in queue['entries'] if row['repair_source_SHA']==SOURCE]
require(len(current)==9 and {row['date'] for row in current}=={'2025-05-'+f'{n:02d}' for n in range(1,10)},'actual Source32 queued nine dates')
require(all(row['verification_status']=='READY_VERIFIED_REPAIR' for row in current),'actual Source32 all9 READY at audit snapshot')
for first in resume_observation['first_four_existing_queue_ids']:
    require(sum(row['queue_id']==first['queue_id'] and row['date']==first['date'] and row['queued_UTC']==first['queued_UTC'] for row in current)==1,'interrupted enqueue first-four ID preserved exactly once '+first['date'])
for row in current:
    require(row['initial_native_runtime']==0 and row['remaining_native_seconds']==5400 and row['restart_from_zero'] is True,'actual queue fresh0/full5400 '+row['date'])
    require(row['retry_priority']==(1000 if row['date'][-2:] in ('01','02','03') else 100),'actual queue priority '+row['date'])
    require(row['repair_commit_SHA']==COMMIT and Path(row['repair_code_root']).resolve()==CODE,'queue immutable source binding '+row['date'])
    require(same_record(row['validation_receipt']) and row['validation_receipt']==rec(ROOT/'autonomous/V32_VERIFIED_REPAIR_VALIDATION.json'),'queue validation exact '+row['date'])
    require(same_record(row['original_result_receipt']) and same_record(row['original_ledger_receipt']),'preserved historical actual failure bytes '+row['date'])
    require(not row.get('retry_attempt_id') and not row.get('new_worker_PID'),'queue remains unstarted '+row['date'])
old_ready_ids={row['queue_id'] for row in baseline['ready']}
superseded=[row for row in queue['entries'] if row.get('superseded_by_queue_id') in {x['queue_id'] for x in current}]
require({row['queue_id'] for row in superseded}==old_ready_ids and len(superseded)==3,'only pre-enqueue three old Source30 READY superseded')
for row in superseded:require(row['verification_status']=='SUPERSEDED_UNSTARTED_READY' and row['repair_source_SHA']==old30['execution_SHA'],'prior unstarted Source30 preserved as superseded '+row['date'])
require({row['queue_id'] for row in deployment['queues']}=={row['queue_id'] for row in current},'deployment exact nine queue receipt IDs')

worker_observations=[]
for before in baseline['workers']:
    key=before['key'];row=cp['workers'].get(key)
    require(row is not None,'normal worker continues '+key)
    request=doc(row['request']);p=psutil.Process(row['PID'])
    observed=dict(PID=p.pid,create_time=p.create_time(),cmdline=p.cmdline(),cwd=p.cwd())
    require(observed==before['process'],'normal same PID/create/cmd/cwd '+key)
    require(capture(row['request'])[1]['source']==before['request']['source'],'normal same sealed request '+key)
    require(request['implementation_SHA']==old30['execution_SHA'],'normal remains own Source30 '+key)
    ledger_path=Path(row['request']).parent/'NATIVE_RUNTIME_LEDGER.json';ledger=doc(ledger_path)
    require(ledger['calls'][:len(before['calls'])]==before['calls'],'normal completed Native cost/call prefix preserved '+key)
    native=ledger.get('measured_native_runtime',ledger.get('measured_Native_Runtime'))
    require(native>=before['Native_Runtime'],'normal cumulative Native nondecreasing '+key)
    worker_observations.append(dict(key=key,process=observed,request=capture(row['request'])[1]['source'],ledger=capture(ledger_path)[1],before_Native=before['Native_Runtime'],after_Native=native,before_calls=len(before['calls']),after_calls=len(ledger['calls']),inflight=ledger.get('inflight')))

supervisor_doc=doc(ROOT/'SUPERVISOR_PROCESS.json')
base_sup=json.loads(Path(baseline['supervisor_record']['snapshot']['path']).read_text(encoding='utf-8-sig'))
require(supervisor_doc==base_sup,'coordinator process record unchanged by deployment')
p=psutil.Process(supervisor_doc['PID'])
require(abs(p.create_time()-supervisor_doc['created'])<.001 and p.cmdline()==supervisor_doc['command'],'actual owned coordinator exact PID/create/cmd')
http=urllib.request.urlopen('http://127.0.0.1:8794/',timeout=10)
require(http.status==200,'monitor HTTP8794 healthy')
http.close()
freeze31=doc(ROOT/'autonomous/V31_SPARSE_IMMUTABLE_FREEZE.json')
require(subprocess.check_output(['git','rev-parse','HEAD'],cwd='D:/v42run31',text=True).strip()==freeze31['commit'],'historical D31 HEAD preserved')
require(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd='D:/v42run31',text=True).strip(),'historical D31 tracked bytes clean')
for row in freeze31['source_files']:require(same_record(row),'historical D31 frozen file preserved '+Path(row['path']).name)
require(not (ROOT/'B2_V31_ZERO_START_DEPLOYMENT_MANIFEST.json').exists() and not any(Path(row['repair_code_root']).resolve()==Path('D:/v42run31') for row in queue['entries']),'Source31 frozen only never deployed or queued')

report=dict(PASS=True,UTC=datetime.now(timezone.utc).isoformat(),schema='V42_SOURCE32_INDEPENDENT_READ_ONLY_DEPLOYMENT_EXECUTION_AUDIT',
    scope='Deployment execution independent audit by adapter author; scientific independent validation belongs to separate reviewer',checks=checks,
    execution_SHA=SOURCE,commit=COMMIT,original_sources=1007,execution_sources=98,additional_assets=5,actual_verified_frozen_files=1110,
    baseline=capture(OUT/'SOURCE32_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json')[1]['source'],
    actual_all27_fresh0_requests=fresh_requests,actual_all9_READY_queues=[dict(date=row['date'],queue_id=row['queue_id'],priority=row['retry_priority'],initial_native_runtime=row['initial_native_runtime'],remaining_native_seconds=row['remaining_native_seconds']) for row in current],
    only_superseded_old_Source30_unstarted_queue_ids=sorted(old_ready_ids),normal_Source30_workers=worker_observations,
    enqueue_interruption_resume_observation=capture(OUT/'SOURCE32_ENQUEUE_PARTIAL_RESUME_READ_ONLY_OBSERVATION.json')[1]['source'],
    enqueue_partial_failure_scope='Parent-reported lease release stopped initial enqueue after first four. Exception not independently captured by reviewer. Exact four existing IDs and timestamps survive completed queue exactly once; raw observation retained separately.',
    coordinator=supervisor_doc,Source31_frozen_preserved_not_deployed=True,
    final_gap_PASS_claimed=False,actual_Source32_Native_or_date_performance_pending=True,
    Native_optimize_calls=0,real_Native_model_constructions=0,production_immutable_queue_manifest_changes=0,process_actions=0,git_mutations=0,
    raw_single_read_records=records,source_script=rec(__file__))
target=OUT/'SOURCE32_DEPLOYMENT_INDEPENDENT_READ_ONLY_EXECUTION_AUDIT.json'
with target.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
print(json.dumps(dict(PASS=True,receipt=rec(target),checks=len(checks),worker_continuity=[dict(day=row['key'],PID=row['process']['PID'],before_Native=row['before_Native'],after_Native=row['after_Native']) for row in worker_observations]),ensure_ascii=False))
