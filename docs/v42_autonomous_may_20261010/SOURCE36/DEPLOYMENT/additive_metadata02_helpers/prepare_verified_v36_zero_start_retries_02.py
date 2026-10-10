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
p.add_argument('--mode',choices=('enqueue',),required=True)
args=p.parse_args()
root=Path('D:/v42_may_restart_20261010_02')
code=Path('D:/v42run36')
commit=args.commit
manifest_path=root/'B2_V36_ZERO_START_DEPLOYMENT_MANIFEST.json'
validation=root/'autonomous/V36_VERIFIED_REPAIR_VALIDATION_02.json'
prepared=root/'autonomous/V36_ZERO_START_RETRY_PREPARATION_02.json'
recovery.assert_lease(root,args.lease_token)
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=code,text=True).strip()==commit
assert not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=code,text=True).strip()

assert args.mode=='enqueue'
saved=read(prepared);assert saved['PASS'] is True
new=read(manifest_path);cp=read(root/'SUPERVISOR_STATE.json');queued=[]
expected_unstarted_source=read(root/'B2_V35_ZERO_START_DEPLOYMENT_MANIFEST.json')['execution_SHA']
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
        repair_reason='Actual Source35 same-current strict FULL seed projection installed complete PStart and computational zero DStart, but dual-simplex Method1 with LPWarmStart2/Presolve0 reached the unchanged30-second RMP cap without usable Native Pi. Source36 only selects primal-simplex Method0 after exact complete same-current P/D installation and sealed original plus Native-scaled row and bound violations within literal original1e-9; finite nonfeasible or cold/ineligible starts retain original Method1. Exact source/model/axis/current-point/known-Native and before/after settings/start guards remain closed. Original Presolve0, warm2, Threads1, Crossover and FeasibilityTol/OptimalityTol1e-9/NumericFocus3/ScaleFlag2, single30 call/total5400 budgets, dyadic row/Pi transport and full independent checker are unchanged. Source35 F1 price seed, full-LP, worker and other98 execution modules are byte-identical. No additional Native calls or objective-to-LB authority; actual Source36 performance and final scientific PASS remain pending.',
        validation_receipt=record(validation),repair_code_root=str(code),worker_module='v42_autonomous_b2.worker',
        retry_priority=1000 if day[-2:] in ('01','02','03') else 100,
        retry_request_receipt=requests['1'],retry_request_receipts_by_slot=requests,restart_from_zero=True,reset_authorization=new['reset_authorization'])
    prior_ready=[entry for entry in recovery.queue(root)['entries'] if entry['arm']=='B2' and entry['date']==day and entry['verification_status']=='READY_VERIFIED_REPAIR' and entry['repair_source_SHA']!=''+new['execution_SHA']]
    prior_ready.sort(key=lambda entry:entry['queued_UTC'],reverse=True)
    if prior_ready:
        assert len(prior_ready)==1 and prior_ready[0]['repair_source_SHA']==expected_unstarted_source,'UNEXPECTED_OR_AMBIGUOUS_READY_SUPERSESSION_SOURCE'
    options=dict(supersede_queue_id=prior_ready[0]['queue_id']) if prior_ready else {}
    queued.append(recovery.enqueue(root,failure,repair,lease_token=args.lease_token,**options))
receipt=dict(PASS=True,UTC=now(),deployment=record(manifest_path),validation=record(validation),
    queues=[dict(date=x['date'],queue_id=x['queue_id'],status=x['verification_status'],Native_initial=x['initial_native_runtime'],remaining=x['remaining_native_seconds'],priority=x['retry_priority']) for x in queued],
    active_workers_not_modified=True,old_results_and_native_ledgers_preserved=True,final_PASS_not_claimed=True)
target=root/'autonomous/V36_ZERO_START_RETRY_DEPLOYMENT.json';assert not target.exists();atomic(target,receipt)
print(json.dumps(receipt,ensure_ascii=False))
