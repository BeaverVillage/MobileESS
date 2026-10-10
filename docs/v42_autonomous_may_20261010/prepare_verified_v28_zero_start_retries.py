"""Prepare ahead of healthy workers; activate only evidence-complete repairs."""
from pathlib import Path
import argparse,json,subprocess,sys
sys.path.insert(0,'D:/MobileESS_v42_autonomous')
from v42_b2_seed_recovery_v19.common import read,atomic,record,digest,now
from v42_autonomous import recovery

p=argparse.ArgumentParser()
p.add_argument('--template',required=True)
p.add_argument('--lease-token',required=True)
p.add_argument('--commit',required=True)
p.add_argument('--mode',choices=('prepare','enqueue'),required=True)
args=p.parse_args()
root=Path('D:/v42_may_restart_20261010_02')
code=Path('D:/v42run28')
commit=args.commit
manifest_path=root/'B2_V28_ZERO_START_DEPLOYMENT_MANIFEST.json'
validation=root/'autonomous/V28_VERIFIED_REPAIR_VALIDATION.json'
prepared=root/'autonomous/V28_ZERO_START_RETRY_PREPARATION.json'
recovery.assert_lease(root,args.lease_token)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==commit
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip()

if args.mode=='prepare':
    assert not any(x.exists() for x in (manifest_path,validation,prepared))
    template=read(args.template)
    assert template['PASS'] is True
    for key in recovery.REQUIRED_VALIDATION:assert template[key] is True,key
    for field in ('source_files','original_source_files'):
        bound=[]
        for item in template[field]:
            old_file=Path(item['path']).resolve()
            relative=old_file.relative_to(code) if old_file.is_relative_to(code) else old_file.relative_to(Path('D:/MobileESS_v42_autonomous'))
            new=record(code/relative)
            assert (new['bytes'],new['sha256'])==(item['bytes'],item['sha256']),relative
            bound.append(new)
        template[field]=bound
    assert len(template['source_files'])==96 and len(template['original_source_files'])==1007
    execution={Path(item['path']).relative_to(code).as_posix():item['sha256'] for item in template['source_files']}
    assert digest(execution)==template['repair_source_SHA']
    template.update(repair_commit_SHA=commit,binding_status='BOUND_TO_IMMUTABLE_V28_CHECKOUT',UTC=now(),
        sparse_freeze=record(root/'autonomous/V28_SPARSE_IMMUTABLE_FREEZE.json'),
        sparse_import_smoke=record(root/'autonomous/V28_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json'))
    atomic(validation,template)
    registry=read(root/'AUTONOMOUS_MANIFEST.json');old_path=Path(registry['B2_deployment_manifest']);old=read(old_path)
    new=dict(old,source_commit=commit,execution_sources=execution,execution_SHA=template['repair_source_SHA'],prior_attempts={},
        attempt_id='fresh_b2_v28_01',fresh_attempt_id='fresh_b2_v28_01',algorithm_version='ORIGINAL_V19_FULL_SCOPED_CERTIFICATE_ADAPTERS_V28',
        attempt_ids=['fresh_b2_v28_01']+[f'repair_b2_v28_01_s{s}' for s in (1,2,3)],UTC=now(),
        restart_from_zero=True,reset_authorization=record(root/'USER_ZERO_START_RETRY_AUTHORIZATION.json'),
        historical_deployment_preserved=record(old_path))
    atomic(manifest_path,new)
    requests={}
    old_attempts={'01':'repair_b2_v25_01_s3','02':'repair_b2_v25_01_s1','03':'repair_b2_v25_01_s2',
        '04':'fresh_b2_v22_01','05':'fresh_b2_v22_01','06':'fresh_b2_v22_01',
        '07':'fresh_b2_v23_01','08':'fresh_b2_v23_01','09':'fresh_b2_v23_01'}
    verifier="""import json,sys;from unittest.mock import patch;import gurobipy as gp
with patch.object(gp,'Model',side_effect=AssertionError('NATIVE_MODEL_FORBIDDEN')):
 from v42_autonomous_b2.worker import verify_request
 verify_request(json.load(open(sys.argv[1],encoding='utf-8-sig')))
"""
    for short,old_attempt in old_attempts.items():
        day='2025-05-'+short;original=root/'dates/B2'/day/'attempts'/old_attempt
        requests[day]={}
        for slot in (1,2,3):
            request=dict(read(original/'request.json'));attempt_id=f'repair_b2_v28_01_s{slot}'
            attempt=root/'dates/B2'/day/'attempts'/attempt_id
            request.update(attempt_id=attempt_id,worker_slot=slot,manifest=str(manifest_path),manifest_SHA=record(manifest_path)['sha256'],
                implementation_SHA=new['execution_SHA'],deployment_SHA=new['execution_SHA'],algorithm_version=new['algorithm_version'],
                started_UTC=now(),restart_from_zero=True,reset_authorization=new['reset_authorization'],previous_attempts=[])
            for key,name in (('output','output'),('result','RESULT.json'),('progress','progress.json'),('error','error.json')):request[key]=str(attempt/name)
            path=attempt/'request.json';assert not path.exists();atomic(path,request)
            subprocess.run(['python','-B','-X','utf8','-c',verifier,str(path)],cwd=code,capture_output=True,text=True,check=True)
            requests[day][str(slot)]=record(path)
    registry.update(B2_code_root=str(code),B2_deployment_manifest=str(manifest_path),B2_manifest=record(manifest_path),
        B2_source_SHA=new['execution_SHA'],B2_source_commit=commit)
    atomic(root/'AUTONOMOUS_MANIFEST.json',registry)
    receipt=dict(PASS=True,UTC=now(),deployment=record(manifest_path),validation=record(validation),
        requests_by_day_and_slot=requests,original_attempts=old_attempts,
        all_27_sealed_request_native_denied_admissions_PASS=True,Native_optimize_calls=0,model_constructions=0,
        active_workers_not_modified=True,old_results_and_native_ledgers_preserved=True,final_PASS_not_claimed=True)
    atomic(prepared,receipt)
    print(json.dumps(dict(PASS=True,preparation=record(prepared),requests=sum(map(len,requests.values())))))
else:
    saved=read(prepared);assert saved['PASS'] is True
    new=read(manifest_path);cp=read(root/'SUPERVISOR_STATE.json');queued=[]
    for day,requests in saved['requests_by_day_and_slot'].items():
        current=cp['dates']['B2/'+day]
        # Use the newest genuine sealed FAIL when available, otherwise preserve
        # the already observed historical failure while current worker continues.
        latest=Path(current.get('result') or '')
        latest_doc=read(latest) if latest.is_file() else {}
        if latest_doc.get('PASS') is False and latest_doc.get('identity',{}).get('day')==day:
            original=latest.parent;old_attempt=latest_doc['identity']['attempt_id'];result=latest_doc
        else:
            old_attempt=saved['original_attempts'][day[-2:]];original=root/'dates/B2'/day/'attempts'/old_attempt;result=read(original/'RESULT.json')
        assert result['PASS'] is False
        failure=dict(date=day,arm='B2',failed_stage='CERTIFIED_PRICING_OR_ADAPTIVE',
            failure_class=result.get('scientific',{}).get('error') or result.get('error') or result['status'],
            original_attempt_id=old_attempt,original_source_SHA=result['source_SHA'],original_native_runtime=result['Native_Runtime'],
            original_result_receipt=record(original/'RESULT.json'),original_ledger_receipt=record(original/'NATIVE_RUNTIME_LEDGER.json'),native_budget_seconds=5400)
        repair=dict(repair_commit_SHA=commit,repair_source_SHA=new['execution_SHA'],
            repair_reason='Verified current-attempt original Native basis transport selects primal Method0/LPWarmStart1 only at the exact original full-LP call, addressing observed Method1 time-cap recurrence while preserving original120/300/5400 budgets, original matrix/domain/objective/precision and independent full certification; prior scoped repairs remain unchanged.',
            validation_receipt=record(validation),repair_code_root=str(code),worker_module='v42_autonomous_b2.worker',
            retry_priority=1000 if day[-2:] in ('01','02','03') else 100,
            retry_request_receipt=requests['1'],retry_request_receipts_by_slot=requests,restart_from_zero=True,reset_authorization=new['reset_authorization'])
        prior_ready=[entry for entry in recovery.queue(root)['entries'] if entry['arm']=='B2' and entry['date']==day and entry['verification_status']=='READY_VERIFIED_REPAIR' and entry['repair_source_SHA']!=''+new['execution_SHA']]
        prior_ready.sort(key=lambda entry:entry['queued_UTC'],reverse=True)
        options=dict(supersede_queue_id=prior_ready[0]['queue_id']) if prior_ready else {}
        queued.append(recovery.enqueue(root,failure,repair,lease_token=args.lease_token,**options))
    receipt=dict(PASS=True,UTC=now(),deployment=record(manifest_path),validation=record(validation),
        queues=[dict(date=x['date'],queue_id=x['queue_id'],status=x['verification_status'],Native_initial=x['initial_native_runtime'],remaining=x['remaining_native_seconds'],priority=x['retry_priority']) for x in queued],
        active_workers_not_modified=True,old_results_and_native_ledgers_preserved=True,final_PASS_not_claimed=True)
    target=root/'autonomous/V28_ZERO_START_RETRY_DEPLOYMENT.json';assert not target.exists();atomic(target,receipt)
    print(json.dumps(receipt,ensure_ascii=False))
