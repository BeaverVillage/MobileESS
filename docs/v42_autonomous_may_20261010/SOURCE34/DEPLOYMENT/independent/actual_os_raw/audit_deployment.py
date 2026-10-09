"""Read-only saved Source34 deployment audit; no science imports or admissions."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import traceback
import psutil

OUT=Path(__file__).resolve().parent
ROOT=Path('D:/v42_may_restart_20261010_02'); AUTO=ROOT/'autonomous'; CODE=Path('D:/v42run34')
INDEP=Path('D:/v42_source34_independent_review_20261010_01/SOURCE34_INDEPENDENT_NATIVE_DENIED_REVIEW_RECEIPT.json')
def rec(path,raw=None):
    p=Path(path); data=p.read_bytes() if raw is None else raw
    return dict(path=str(p.resolve()),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def check_record(v):
    actual=rec(v['path']); assert actual['sha256']==v['sha256'] and actual['bytes']==v['bytes']; return actual
def digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()
r=dict(schema='V42_SOURCE34_DEPLOYMENT_INDEPENDENT_SAVED_EVIDENCE_READONLY_AUDIT',PASS=False,
    started_UTC=datetime.now(timezone.utc).isoformat(),Native_optimize_calls=0,real_Native_model_constructions=0,
    modelattempts=[],nativeattempts=[],science_modules_imported=False,admissions_or_helpers_executed=False,
    queue_lease_runtime_source_Git_or_production_process_changes=0,actual_Source34_performance_or_final_PASS_claimed=False)
try:
    evidence_names=['V34_ZERO_START_RETRY_DEPLOYMENT.json','V34_ZERO_START_RETRY_PREPARATION.json',
        'V34_SPARSE_IMMUTABLE_FREEZE.json','V34_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json','V34_VALIDATION_BINDING_TEMPLATE.json',
        'V34_VERIFIED_REPAIR_VALIDATION.json','SOURCE34_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json']
    evidence_raw={n:(AUTO/n).read_bytes() for n in evidence_names}
    evidence={n:json.loads(raw) for n,raw in evidence_raw.items()}
    for n,raw in evidence_raw.items():(OUT/('RAW_'+n)).write_bytes(raw)
    assert all(v['PASS'] is True for v in evidence.values())
    deployment=evidence['V34_ZERO_START_RETRY_DEPLOYMENT.json']; prep=evidence['V34_ZERO_START_RETRY_PREPARATION.json']
    freeze=evidence['V34_SPARSE_IMMUTABLE_FREEZE.json']; smoke=evidence['V34_SPARSE_NATIVE_DENIED_IMPORT_SMOKE.json']
    validation=evidence['V34_VERIFIED_REPAIR_VALIDATION.json']; baseline=evidence['SOURCE34_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json']
    template=evidence['V34_VALIDATION_BINDING_TEMPLATE.json']
    for document in (deployment,prep):
        check_record(document['deployment']);check_record(document['validation'])
    assert deployment['deployment']==prep['deployment'] and deployment['validation']==prep['validation']
    manifest=read(deployment['deployment']['path']); independent=read(INDEP)
    assert independent['PASS'] is True
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=CODE,check=True,capture_output=True,text=True).stdout.strip()
    clean=subprocess.run(['git','status','--porcelain','--untracked-files=no'],cwd=CODE,check=True,capture_output=True,text=True).stdout
    assert not clean and commit==manifest['source_commit']==freeze['commit']=='cae08b21cb83864887e397805c0a6a8944da7f83'
    original=manifest['builder_original_sources']; execution=manifest['execution_sources']
    assert len(original)==1007 and len(execution)==98 and not set(original)&set(execution)
    assert digest(execution)==manifest['execution_SHA']==smoke['execution_SHA']==independent['execution_SHA']=='dd14a820e9b65f35e13827d89143bca22e656abd10365fe5b96dd04b40160016'
    scientific={n:rec(CODE/n) for n in sorted(set(original)|set(execution))}
    assert len(scientific)==1105
    assert all(scientific[n]['sha256']==v for n,v in (original|execution).items())
    assert all(scientific[n]['sha256']==v['sha256'] and scientific[n]['bytes']==v['bytes'] for n,v in independent['source_file_records'].items())
    frozen={str(Path(v['path']).relative_to(CODE)).replace('\\','/'):check_record(v) for v in freeze['source_files']}
    assets={str(Path(v['path']).relative_to(CODE)).replace('\\','/'):check_record(v) for v in validation['sparse_required_additional_assets']}
    assert len(frozen)==1110 and len(assets)==5 and set(frozen)==set(scientific)|set(assets)
    for v in validation['source_files']+validation['original_source_files']:check_record(v)
    assert validation['repair_code_root']==str(CODE) and validation['repair_commit_SHA']==commit and validation['repair_source_SHA']==digest(execution)
    assert validation['full_LP_computational_entry_required_Method']==6 and validation['full_LP_computational_entry_required_LPWarmStart']==2
    assert (validation['PDHGAbsTol'],validation['PDHGRelTol'],validation['PDHGConvTol'],validation['PDHGGPU'])==(1e-9,0.,1e-9,0)
    assert validation['original_Crossover_preserved'] is True and validation['original_fallback_Method1_primal_dual_pair_LPWarmStart2_unchanged'] is True
    assert (validation['RMP_Method'],validation['RMP_Presolve'],validation['RMP_LPWarmStart'],validation['RMP_original_required_seconds'])==(1,0,2,30.)
    for flag in ['RMP_model_local_only_original_cold_fallback_for_ineligible_start_required',
        'RMP_same_attempt_current_point_nonunit_and_current_seed_catalog_projection_required',
        'RMP_explicit_computational_zero_DStart_is_not_Native_Pi_or_bound',
        'RMP_no_post_Native_start_setter_update_or_start_readback_required',
        'RMP_original_owned_model_finally_disposal_required','RMP_missing_Native_Pi_remains_missing_and_not_zero_dual']:
        assert validation[flag] is True
    for doc,expected_sha in [(validation['current_source_selected_production_regressions'],'c505fb66aede0c513025530aae9ee69df1ce07fdf7662b2b69a5adbed62cf665'),
        (validation['independent_production_review'],'a7539f596e4bf64f13f2412e4fff6e7d8b80b1dc19a10fc457a348c32323bce7')]:
        check_record(doc);assert doc['sha256']==expected_sha
        saved=read(doc['path']);assert saved['PASS'] is True and saved['execution_SHA']==digest(execution)
        assert saved['execution_sources']==execution and len(saved['source_file_records'])==1105
        assert saved['tests_passed']==244 and saved['modelattempts']==saved['nativeattempts']==[]
        assert saved['Native_optimize_calls']==saved['real_Native_model_constructions']==0
        assert all(saved[k] is True for k in ['source_start_end_identical','execution_start_end_identical','test_start_end_identical'])
        assert all(scientific[n]['sha256']==v['sha256'] and scientific[n]['bytes']==v['bytes'] for n,v in saved['source_file_records'].items())
        assert template['current_source_selected_production_regressions']==validation['current_source_selected_production_regressions']
        assert template['independent_production_review']==validation['independent_production_review']
    assert validation['actual_Source34_Native_performance_pending'] is True and validation['actual_Source34_Global_Gap_PASS_pending'] is True
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
            assert request['attempt_id']=='repair_b2_v34_01_s'+slot and request['manifest_SHA']==deployment['deployment']['sha256']
            assert Path(request['manifest'])==Path(deployment['deployment']['path'])
            assert request['implementation_SHA']==request['deployment_SHA']==digest(execution)
            assert request['native_budget_seconds']==5400 and request['wall_budget_seconds'] is None and request['previous_attempts']==[]
            assert request['Threads']==1 and request['P2_calls']==0 and request['target_gap']==.03 and request['restart_from_zero'] is True
            check_record(request['reset_authorization'])
            assert not Path(request['output']).exists() and not Path(request['result']).exists()
            request_rows.append(dict(day=day,slot=int(slot),attempt=request['attempt_id'],request=ref,Native_initial=0,previous_attempts=[]))
    assert len(request_rows)==27 and len(requests)==9
    for flag in ['all_27_sealed_request_native_denied_admissions_PASS','all_27_current_source_cache_and_RMP_factory_admissions_PASS',
        'all_27_actual_m_dispatch_canonical_budget_descriptor_admissions_PASS','no_scientific_output_or_prior_checkpoint_created_by_admission']:
        assert prep[flag] is True
    assert prep['Native_optimize_calls']==prep['model_constructions']==0
    lease_raw=(ROOT/'REPAIR_LEASE.json').read_bytes(); lease=json.loads(lease_raw)
    (OUT/'RELEASED_REPAIR_LEASE_SNAPSHOT.json').write_bytes(lease_raw)
    assert lease['token']=='dd083b8daa3f407ebf4ce58d1d87e939' and lease['state']=='RELEASED' and lease['owner'] is None
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
    old=[v for v in rows if v.get('repair_code_root')=='D:\\v42run33']
    superseded=[v for v in old if v['verification_status']=='SUPERSEDED_UNSTARTED_READY']
    assert len(old)==9 and len(superseded)==9 and {v['date'] for v in superseded}==set(requests)
    for row in superseded:
        assert row['new_worker_PID'] is None and row['superseded_by_queue_id']==new_by_day[row['date']]['queue_id']
        assert row['superseded_reason']=='NEW_INDEPENDENTLY_VERIFIED_REPAIR_SOURCE'
    assert (AUTO/'SOURCE34_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json').read_bytes()==evidence_raw['SOURCE34_PRE_ENQUEUE_NATIVE_CONTINUITY_BASELINE.json']
    cp_raw=(ROOT/'SUPERVISOR_STATE.json').read_bytes(); cp=json.loads(cp_raw)
    (OUT/'SOURCE32_CURRENT_SUPERVISOR_STATE_SNAPSHOT.json').write_bytes(cp_raw)
    continuity={}
    for key,b in baseline['source32_workers'].items():
        worker=b['worker'];current=cp['workers'][key]
        assert all(current[field]==worker[field] for field in worker)
        process=psutil.Process(worker['PID']); actual=dict(PID=process.pid,created=process.create_time(),command=process.cmdline(),cwd=process.cwd())
        assert actual==b['actual_process'] and process.is_running()
        check_record(b['request']);check_record(b['ledger_snapshot'])
        prior_ledger_raw=Path(b['ledger_snapshot']['path']).read_bytes()
        (OUT/('RAW_SOURCE34_PRE_ENQUEUE_'+worker['day']+'_NATIVE.json')).write_bytes(prior_ledger_raw)
        previous=read(b['ledger_snapshot']['path']); current_raw=Path(b['original_ledger']).read_bytes(); ledger=json.loads(current_raw)
        snapshot=OUT/('SOURCE32_CURRENT_'+worker['day']+'_NATIVE.json');snapshot.write_bytes(current_raw)
        before=[v for v in previous['calls'] if v.get('status')=='FINISHED'];after=[v for v in ledger['calls'] if v.get('status')=='FINISHED']
        assert after[:len(before)]==before and ledger['measured_Native_Runtime']>=previous['measured_Native_Runtime']
        original_row=next(v for v in rows if v['queue_id']==worker['recovery_queue_id'])
        assert original_row['repair_code_root']=='D:\\v42run32' and original_row['new_worker_PID']==worker['PID'] and original_row['verification_status']!='SUPERSEDED_UNSTARTED_READY'
        continuity[key]=dict(actual_process=actual,current_worker=current,request=rec(b['request']['path']),
            completed_Native_prefix_identical=True,preserved_completed_calls=len(before),current_completed_calls=len(after),
            baseline_Native_Runtime=previous['measured_Native_Runtime'],current_measured_Native_Runtime=ledger['measured_Native_Runtime'],
            current_inflight_observation=ledger['inflight'],current_ledger_snapshot=rec(snapshot))
    supervisor=baseline['supervisor']; live=psutil.Process(supervisor['PID'])
    assert live.is_running() and live.create_time()==supervisor['created'] and live.cmdline()==supervisor['command']
    end={n:rec(CODE/n) for n in scientific}
    assert scientific==end
    assert all((AUTO/n).read_bytes()==raw for n,raw in evidence_raw.items())
    r.update(PASS=True,scientific_HEAD=commit,scientific_git_tracked_clean=True,
        execution_SHA=digest(execution),execution_source_count=98,original_source_count=1007,frozen_unique_source_asset_count=1110,
        scientific_source_file_records=scientific,scientific_source_file_records_end=end,source_start_end_identical=scientific==end,
        frozen_declared_file_records=frozen,all27_saved_request_records=requests,all27_record_SHA_and_fresh_parameters_verified=True,
        all27_saved_canonical_admission_receipt_verified=True,admission_is_not_scientific_performance_or_final_PASS=True,
        new_queue_rows=new,superseded_unstarted_Source33_rows=superseded,active_Source32_continuity=continuity,
        supervisor_identity_unchanged=supervisor,repair_lease_released=lease,
        saved_evidence_records={n:rec(AUTO/n) for n in evidence},independent_scientific_source_review=rec(INDEP),
        raw_saved_producer_evidence_records={n:rec(OUT/('RAW_'+n)) for n in evidence},saved_producer_evidence_start_end_identical=True,
        queue_snapshot=rec(OUT/'RECOVERY_QUEUE_SNAPSHOT.json'),released_lease_snapshot=rec(OUT/'RELEASED_REPAIR_LEASE_SNAPSHOT.json'),
        static_current_algorithm_binding={k:validation[k] for k in ['Method','LPWarmStart','PDHGAbsTol','PDHGRelTol','PDHGConvTol','PDHGGPU','original_Crossover_preserved','original_fallback_Method1_primal_dual_pair_LPWarmStart2_unchanged','RMP_Method','RMP_Presolve','RMP_LPWarmStart','RMP_original_required_seconds']},
        HTTP_8794_not_independently_queried_by_this_audit=True)
except BaseException as error:r.update(error=repr(error),traceback=traceback.format_exc())
r['finished_UTC']=datetime.now(timezone.utc).isoformat()
receipt=OUT/'SOURCE34_DEPLOYMENT_INDEPENDENT_READONLY_AUDIT.json'
receipt.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(dict(PASS=r['PASS'],receipt=rec(receipt),error=r.get('error'),counts={k:r.get(k) for k in ['execution_source_count','original_source_count','frozen_unique_source_asset_count']}),indent=2))
raise SystemExit(0 if r['PASS'] else 1)
