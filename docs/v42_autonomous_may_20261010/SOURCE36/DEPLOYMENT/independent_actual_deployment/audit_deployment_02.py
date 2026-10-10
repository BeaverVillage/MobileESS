"""Read-only saved Source36 deployment audit; no science imports or admissions."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import traceback
import psutil

OUT=Path(__file__).resolve().parent
ROOT=Path('D:/v42_may_restart_20261010_02'); AUTO=ROOT/'autonomous'; CODE=Path('D:/v42run36')
INDEP=Path('D:/v42_source36_independent_review_20261010_01/SOURCE36_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT_01.json')
def rec(path,raw=None):
    p=Path(path); data=p.read_bytes() if raw is None else raw
    return dict(path=str(p.resolve()),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def check_record(v):
    actual=rec(v['path']); assert actual['sha256']==v['sha256'] and actual['bytes']==v['bytes']; return actual
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
r=dict(schema='V42_SOURCE36_DEPLOYMENT_INDEPENDENT_SAVED_EVIDENCE_READONLY_AUDIT',PASS=False,
    started_UTC=datetime.now(timezone.utc).isoformat(),Native_optimize_calls=0,real_Native_model_constructions=0,
    modelattempts=[],nativeattempts=[],science_modules_imported=False,admissions_or_helpers_executed=False,
    queue_lease_runtime_source_Git_or_production_process_changes=0,actual_Source36_performance_or_final_PASS_claimed=False)
try:
    evidence_names=['V36_ZERO_START_RETRY_DEPLOYMENT.json','V36_ZERO_START_RETRY_PREPARATION_02.json','V36_ZERO_START_RETRY_PREPARATION.json',
        'V36_SPARSE_IMMUTABLE_FREEZE.json','V36_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json','V36_VALIDATION_BINDING_TEMPLATE.json',
        'V36_VERIFIED_REPAIR_VALIDATION_02.json','V36_VERIFIED_REPAIR_VALIDATION.json','SOURCE36_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json','SOURCE36_POST_ENQUEUE_NATIVE_CONTINUITY_VERIFICATION.json']
    evidence_raw={n:(AUTO/n).read_bytes() for n in evidence_names}
    evidence={n:json.loads(raw) for n,raw in evidence_raw.items()}
    for n,raw in evidence_raw.items():(OUT/('RAW_'+n)).write_bytes(raw)
    assert all(v['PASS'] is True for v in evidence.values())
    deployment=evidence['V36_ZERO_START_RETRY_DEPLOYMENT.json']; prep=evidence['V36_ZERO_START_RETRY_PREPARATION_02.json']
    freeze=evidence['V36_SPARSE_IMMUTABLE_FREEZE.json']; smoke=evidence['V36_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json']
    validation=evidence['V36_VERIFIED_REPAIR_VALIDATION_02.json']; baseline=evidence['SOURCE36_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json']
    template=evidence['V36_VALIDATION_BINDING_TEMPLATE.json']
    for document in (deployment,prep):
        check_record(document['deployment']);check_record(document['validation'])
    assert deployment['deployment']==prep['deployment'] and deployment['validation']==prep['validation']
    manifest=read(deployment['deployment']['path']); independent=read(INDEP)
    assert independent['PASS'] is True
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=CODE,check=True,capture_output=True,text=True).stdout.strip()
    clean=subprocess.run(['git','status','--porcelain','--untracked-files=no'],cwd=CODE,check=True,capture_output=True,text=True).stdout
    assert not clean and commit==manifest['source_commit']==freeze['commit']=='68b8903c1184a958c16dd7976044716bdff091c6'
    original=manifest['builder_original_sources']; execution=manifest['execution_sources']
    assert len(original)==1007 and len(execution)==99 and not set(original)&set(execution)
    assert digest(execution)==manifest['execution_SHA']==smoke['execution_SHA']==independent['execution_SHA']=='4f1a5980ae897ce1dcfc1ca0fc35836d2a17eddcf3e15df5d587de9f9bd0bf39'
    scientific={n:rec(CODE/n) for n in sorted(set(original)|set(execution))}
    assert len(scientific)==1106
    assert all(scientific[n]['sha256']==v for n,v in (original|execution).items())
    assert all(scientific[n]['sha256']==v['sha256'] and scientific[n]['bytes']==v['bytes'] for n,v in independent['source_file_records'].items())
    frozen={str(Path(v['path']).relative_to(CODE)).replace('\\','/'):check_record(v) for v in freeze['source_files']}
    assets={str(Path(v['path']).relative_to(CODE)).replace('\\','/'):check_record(v) for v in validation['sparse_required_additional_assets']}
    assert len(frozen)==1111 and len(assets)==5 and set(frozen)==set(scientific)|set(assets)
    for v in validation['source_files']+validation['original_source_files']:check_record(v)
    assert validation['repair_code_root']==str(CODE) and validation['repair_commit_SHA']==commit and validation['repair_source_SHA']==digest(execution)
    assert validation['full_LP_computational_entry_required_Method']==6 and validation['full_LP_computational_entry_required_LPWarmStart']==2
    assert (validation['PDHGAbsTol'],validation['PDHGRelTol'],validation['PDHGConvTol'],validation['PDHGGPU'])==(1e-9,0.,1e-9,0)
    assert validation['original_Crossover_preserved'] is True and validation['original_fallback_Method1_primal_dual_pair_LPWarmStart2_unchanged'] is True
    assert 'RMP_Method' not in validation
    assert (validation['original_RMP_budget_entry_Method'],validation['eligible_current_complete_start_RMP_Native_Method'],validation['cold_ineligible_or_nonfeasible_RMP_fallback_Method'])==(1,0,1)
    assert (validation['RMP_Presolve'],validation['RMP_LPWarmStart'],validation['RMP_original_required_seconds'])==(0,2,30.)
    assert validation['metadata_only_correction'] is True
    check_record(validation['historical_validation_with_ambiguous_RMP_Method'])
    check_record(validation['metadata_finalizer_source_script'])
    assert all(check_record(row) for row in validation['original_executed_helper_records'].values())
    oldprep=evidence['V36_ZERO_START_RETRY_PREPARATION.json'];oldvalidation=evidence['V36_VERIFIED_REPAIR_VALIDATION.json']
    assert oldvalidation['RMP_Method']==1
    assert prep['original_preparation']['sha256']=='35e43065bcfe3fc5012bac3109c555a4f571a11583b0aa2972613c9d0b989814'
    check_record(prep['original_preparation']);check_record(prep['original_validation'])
    assert prep['requests_by_day_and_slot']==oldprep['requests_by_day_and_slot'] and prep['deployment']==oldprep['deployment']
    assert prep['admissions_rerun_by_metadata_finalizer'] is False and prep['new_Native_calls_or_models_by_metadata_finalizer']==0
    assert prep['original_prepare_exit_code_confirmed_by_operator']==0
    assert check_record(template['source_script'])['sha256']=='3c7499660720a9cb1304ba5f446896565bb8d0d66b16170096db93c0bc9fdd82'
    pinned={'V36_ZERO_START_RETRY_DEPLOYMENT.json':'6a6320699efe7452243e1625b8b41b29c1a7adc445a92f2567607a2233f84536','V36_ZERO_START_RETRY_PREPARATION_02.json':'1d58a1db37afefa46cff3fc5d1a3e0bac3d64267ca997713423cb1aeb16f1417','V36_VERIFIED_REPAIR_VALIDATION_02.json':'016b629f39a22c33814e943cb67f9df5a9f8f8f8b46d11ad2c8fb08423969c15','SOURCE36_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json':'443be4d5ef7f3b70985fe82acec522e3d64d4f9a7e5f08ad459495a294b2f931','SOURCE36_POST_ENQUEUE_NATIVE_CONTINUITY_VERIFICATION.json':'c53e42007e9822106c835f3f88f627449546e11bd90174e8af39e654a1c20456'}
    assert all(rec(AUTO/name)['sha256']==sha for name,sha in pinned.items())
    assert deployment['deployment']['sha256']=='ca3840a26a3da80393c5416728ef17b398572366274a7c812fa5cbda8c5a100e'
    for flag in ['RMP_model_local_only_original_cold_fallback_for_ineligible_start_required',
        'RMP_same_attempt_current_point_nonunit_and_current_seed_catalog_projection_required',
        'RMP_explicit_computational_zero_DStart_is_not_Native_Pi_or_bound',
        'RMP_no_post_Native_start_setter_update_or_start_readback_required',
        'RMP_original_owned_model_finally_disposal_required','RMP_missing_Native_Pi_remains_missing_and_not_zero_dual']:
        assert validation[flag] is True
    for doc,expected_sha in [(validation['current_source_selected_production_regressions'],'3ff0607e176918b08d63aeeced4667e687609dc72e33180321a82ba8924557ac'),
        (validation['independent_production_review'],'c74bc9a9c721106e3bba4ee8094a2cad3a7ad46b61702aaf0af07f61f4187605')]:
        check_record(doc);assert doc['sha256']==expected_sha
        saved=read(doc['path']);assert saved['PASS'] is True and saved['execution_SHA']==digest(execution)
        assert saved['execution_sources']==execution and len(saved['source_file_records'])==1106
        if 'tests_passed' in saved:
            assert saved['tests_passed']==369 and saved['modelattempts']==saved['nativeattempts']==[]
        else:
            assert saved['tests']==369 and saved['failures']==saved['errors']==0
            assert saved['model_attempts']==saved['native_attempts']==[] and saved['pytest_exit_code']==0
            check_record(saved['raw_xml'])
        assert saved['Native_optimize_calls']==saved['real_Native_model_constructions']==0
        assert all(saved[k] is True for k in ['source_start_end_identical','execution_start_end_identical','test_start_end_identical'])
        assert all(scientific[n]['sha256']==v['sha256'] and scientific[n]['bytes']==v['bytes'] for n,v in saved['source_file_records'].items())
        assert template['current_source_selected_production_regressions']==validation['current_source_selected_production_regressions']
        assert template['independent_production_review']==validation['independent_production_review']
    assert validation['actual_Source36_Native_performance_pending'] is True and validation['actual_Source36_Global_Gap_PASS_pending'] is True
    assert validation['final_gap_PASS_claimed'] is False and validation['production_qualification_claimed'] is False
    check_record(smoke['validation_template'])
    assert smoke['Native_optimize_calls']==smoke['model_constructions']==0 and smoke['real_model_constructor_attempts']==[]
    assert manifest['prior_attempts']=={} and manifest['restart_from_zero'] is True and manifest['native_budget_seconds']==5400
    assert manifest['Threads']==1 and manifest['P2_calls']==0 and manifest['target_gap']==.03
    requests={}; request_rows=[]
    for day,slots in prep['requests_by_day_and_slot'].items():
        assert set(slots)=={'1','2','3'}
        requests[day]={}
        for slot,ref in slots.items():
            requests[day][slot]=check_record(ref); request=read(ref['path'])
            assert request['day']==day and request['worker_slot']==int(slot) and request['arm']=='B2'
            assert request['attempt_id']=='repair_b2_v36_01_s'+slot and request['manifest_SHA']==deployment['deployment']['sha256']
            assert Path(request['manifest'])==Path(deployment['deployment']['path'])
            assert request['implementation_SHA']==request['deployment_SHA']==digest(execution)
            assert request['native_budget_seconds']==5400 and request['wall_budget_seconds'] is None and request['previous_attempts']==[]
            assert request['Threads']==1 and request['P2_calls']==0 and request['target_gap']==.03 and request['restart_from_zero'] is True
            check_record(request['reset_authorization'])
            assert not Path(request['output']).exists() and not Path(request['result']).exists()
            request_rows.append(dict(day=day,slot=int(slot),attempt=request['attempt_id'],request=ref,Native_initial=0,previous_attempts=[]))
    assert len(request_rows)==27 and len(requests)==9
    for flag in ['all_27_sealed_request_native_denied_admissions_PASS','all_27_current_source_cache_and_RMP_factory_admissions_PASS',
        'all_27_current_source_price_seed_unmodified_production_factory_admissions_PASS',
        'all_27_actual_m_dispatch_canonical_budget_descriptor_admissions_PASS','no_scientific_output_or_prior_checkpoint_created_by_admission']:
        assert prep[flag] is True
    assert prep['Native_optimize_calls']==prep['model_constructions']==0
    lease_raw=(ROOT/'REPAIR_LEASE.json').read_bytes(); lease=json.loads(lease_raw)
    (OUT/'RELEASED_REPAIR_LEASE_SNAPSHOT.json').write_bytes(lease_raw)
    assert lease['token']=='de36f19fd14e4710af54525dfb15b48c' and lease['state']=='RELEASED' and lease['owner'] is None
    assert datetime.fromisoformat(deployment['UTC']) < datetime.fromisoformat(lease['released_UTC'])
    queue_raw=(ROOT/'RECOVERY_QUEUE.json').read_bytes(); queue=json.loads(queue_raw)
    (OUT/'RECOVERY_QUEUE_SNAPSHOT.json').write_bytes(queue_raw)
    rows=queue['entries']; new=[v for v in rows if v.get('repair_code_root')==str(CODE)]
    assert len(new)==9 and {v['queue_id'] for v in new}=={v['queue_id'] for v in deployment['queues']}
    new_by_day={v['date']:v for v in new}
    for day,row in new_by_day.items():
        assert row['verification_status']=='READY_VERIFIED_REPAIR' and row['new_worker_PID'] is None
        assert row['retry_priority']==(1000 if day in sorted(requests)[:3] else 100)
        assert row['native_budget_seconds']==row['remaining_native_seconds']==5400 and row['initial_native_runtime']==0
        assert row['restart_from_zero'] is True and row['previous_checkpoint_reuse'] is False and row['previous_native_budget_carry'] is False
        assert row['retry_request_receipts_by_slot']==requests[day]
    old=[v for v in rows if v.get('repair_code_root')=='D:\\v42run35']
    superseded=[v for v in old if v['verification_status']=='SUPERSEDED_UNSTARTED_READY']
    assert len(old)==9 and len(superseded)==6 and {v['date'] for v in superseded}==set(sorted(requests)[3:])
    active_old=[v for v in old if v['verification_status']=='WORKER_ENTERED'];assert len(active_old)==3 and {v['date'] for v in active_old}==set(sorted(requests)[:3])
    for row in superseded:
        assert row['new_worker_PID'] is None and row['superseded_by_queue_id']==new_by_day[row['date']]['queue_id']
        assert row['superseded_reason']=='NEW_INDEPENDENTLY_VERIFIED_REPAIR_SOURCE'
    assert (AUTO/'SOURCE36_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json').read_bytes()==evidence_raw['SOURCE36_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json']
    cp_raw=(ROOT/'SUPERVISOR_STATE.json').read_bytes(); cp=json.loads(cp_raw)
    (OUT/'SOURCE35_CURRENT_SUPERVISOR_STATE_SNAPSHOT.json').write_bytes(cp_raw)
    continuity={}
    for key,b in baseline['source35_workers'].items():
        worker=b['worker'];current=cp['workers'][key]
        assert all(current[field]==worker[field] for field in worker)
        process=psutil.Process(worker['PID']); actual=dict(PID=process.pid,created=process.create_time(),command=process.cmdline(),cwd=process.cwd())
        assert actual==b['actual_process'] and process.is_running()
        check_record(b['request']);check_record(b['ledger_snapshot'])
        prior_ledger_raw=Path(b['ledger_snapshot']['path']).read_bytes()
        (OUT/('RAW_SOURCE36_PRE_ENQUEUE_'+worker['day']+'_NATIVE.json')).write_bytes(prior_ledger_raw)
        previous=read(b['ledger_snapshot']['path']); current_raw=Path(b['original_ledger']).read_bytes(); ledger=json.loads(current_raw)
        snapshot=OUT/('SOURCE35_CURRENT_'+worker['day']+'_NATIVE.json');snapshot.write_bytes(current_raw)
        before=previous['calls'];after=ledger['calls']
        assert after[:len(before)]==before and ledger['measured_Native_Runtime']>=previous['measured_Native_Runtime']
        original_row=next(v for v in rows if v['queue_id']==worker['recovery_queue_id'])
        assert original_row['repair_code_root']=='D:\\v42run35' and original_row['new_worker_PID']==worker['PID'] and original_row['verification_status']!='SUPERSEDED_UNSTARTED_READY'
        continuity[key]=dict(actual_process=actual,current_worker=current,request=rec(b['request']['path']),
            completed_Native_prefix_identical=True,preserved_completed_calls=len(before),current_completed_calls=len(after),
            baseline_Native_Runtime=previous['measured_Native_Runtime'],current_measured_Native_Runtime=ledger['measured_Native_Runtime'],
            current_inflight_observation=ledger['inflight'],current_ledger_snapshot=rec(snapshot))
    supervisor=baseline['supervisor']; live=psutil.Process(supervisor['PID'])
    assert live.is_running() and live.create_time()==supervisor['created'] and live.cmdline()==supervisor['command']
    end={n:rec(CODE/n) for n in scientific}
    assert scientific==end
    assert all(check_record(row) for row in frozen.values())
    assert len(continuity)==3
    post=evidence['SOURCE36_POST_ENQUEUE_NATIVE_CONTINUITY_VERIFICATION.json']
    assert post['supervisor_PID']==supervisor['PID'] and post['exact9_READY_Verified_Repair'] is True
    assert all(post['workers'][key]['PID']==v['actual_process']['PID'] and post['workers'][key]['completed_Native_prefix_preserved'] is True and v['current_measured_Native_Runtime']>=post['workers'][key]['current_known_Native'] for key,v in continuity.items())
    assert all((AUTO/n).read_bytes()==raw for n,raw in evidence_raw.items())
    r.update(PASS=True,scientific_HEAD=commit,scientific_git_tracked_clean=True,
        execution_SHA=digest(execution),execution_source_count=99,original_source_count=1007,frozen_unique_source_asset_count=1111,
        scientific_source_file_records=scientific,scientific_source_file_records_end=end,source_start_end_identical=scientific==end,
        frozen_declared_file_records=frozen,all27_saved_request_records=requests,all27_record_SHA_and_fresh_parameters_verified=True,
        all27_saved_canonical_admission_receipt_verified=True,admission_is_not_scientific_performance_or_final_PASS=True,
        new_queue_rows=new,superseded_unstarted_Source35_rows=superseded,active_Source35_continuity=continuity,
        supervisor_identity_unchanged=supervisor,repair_lease_released=lease,
        saved_evidence_records={n:rec(AUTO/n) for n in evidence},independent_scientific_source_review=rec(INDEP),
        raw_saved_producer_evidence_records={n:rec(OUT/('RAW_'+n)) for n in evidence},saved_producer_evidence_start_end_identical=True,
        queue_snapshot=rec(OUT/'RECOVERY_QUEUE_SNAPSHOT.json'),released_lease_snapshot=rec(OUT/'RELEASED_REPAIR_LEASE_SNAPSHOT.json'),
        static_current_algorithm_binding={k:validation[k] for k in ['Method','LPWarmStart','PDHGAbsTol','PDHGRelTol','PDHGConvTol','PDHGGPU','original_Crossover_preserved','original_fallback_Method1_primal_dual_pair_LPWarmStart2_unchanged','original_RMP_budget_entry_Method','eligible_current_complete_start_RMP_Native_Method','cold_ineligible_or_nonfeasible_RMP_fallback_Method','RMP_Presolve','RMP_LPWarmStart','RMP_original_required_seconds']},
        HTTP_8794_not_independently_queried_by_this_audit=True)
except BaseException as error:r.update(error=repr(error),traceback=traceback.format_exc())
r['preliminary_external_harness_wrong_independent_receipt_folder']=rec(OUT/'SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT.json')
r['finished_UTC']=datetime.now(timezone.utc).isoformat()
receipt=OUT/'SOURCE36_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT_02.json'
assert not receipt.exists()
receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=r['PASS'],receipt=rec(receipt),error=r.get('error'),counts={k:r.get(k) for k in ['execution_source_count','original_source_count','frozen_unique_source_asset_count']}),indent=2))
raise SystemExit(0 if r['PASS'] else 1)
