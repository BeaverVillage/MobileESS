from pathlib import Path
import ast,datetime,hashlib,json
A=Path(r'D:\v42_full_lp_warmstart_readonly_review_20261010_01')
ROOT=Path(r'D:\v42_may_restart_20261010_02')
REPO=Path(r'D:\MobileESS_v42_autonomous')
raw=A/'source31_helper_review_raw';raw.mkdir(exist_ok=False)
records=[];checks={}
def take(path,name):
 data=path.read_bytes();target=raw/name
 with target.open('xb') as f:f.write(data)
 receipt=dict(source_path=str(path),snapshot_path=str(target),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),source_read_count=1,snapshot_bytes_exact=True)
 records.append(receipt)
 return data,receipt
scripts={}
for name in ['build_v31_validation_template.py','prepare_verified_v31_zero_start_retries.py','freeze_sparse_v31.py','smoke_sparse_v31.py']:
 data,receipt=take(ROOT/'autonomous'/name,name);scripts[name]=data.decode('utf8');ast.parse(scripts[name])
checks['all_four_helpers_parse_without_execution']=True
prep=scripts['prepare_verified_v31_zero_start_retries.py'];freeze=scripts['freeze_sparse_v31.py'];smoke=scripts['smoke_sparse_v31.py'];build=scripts['build_v31_validation_template.py']
checks['prepare_targets_new_D31']= "code=Path('D:/v42run31')" in prep
checks['freeze_targets_only_new_nonexistent_D31']= "target=Path('D:/v42run31').resolve()" in freeze and "assert str(target)==r'D:\\v42run31' and not target.exists()" in freeze
checks['smoke_loads_D31_and_labels_Source31']= "sys.path.insert(0,'D:/v42run31')" in smoke and "CODE=Path('D:/v42run31')" in smoke and 'V42_SOURCE31_SPARSE_NATIVE_DENIED_IMPORT_SMOKE' in smoke
checks['source27_exhausted_first_three_fallbacks']=all(x in prep for x in ("'01':'repair_b2_v27_01_s3'","'02':'repair_b2_v27_01_s1'","'03':'repair_b2_v27_01_s2'"))
checks['27_fresh_request_three_slots_loop']= "for slot in (1,2,3):" in prep and 'requests[day][str(slot)]=record(path)' in prep and 'previous_attempts=[]' in prep and 'prior_attempts={}' in prep and 'restart_from_zero=True' in prep
checks['new_request_native_denied_original_factory_admission']= "patch.object(gp,'Model',side_effect=AssertionError('NATIVE_MODEL_FORBIDDEN'))" in prep and 'manifest=verify_request(request)' in prep and 'pricing_cache.create_scope(request,manifest,ROOT)' in prep and 'rmp_presolve.scoped_runner' in prep
checks['future_pointer_after_all_27_admissions']=prep.index("registry.update(B2_code_root=str(code)")>prep.index('requests[day][str(slot)]=record(path)')
checks['only_single_Source30_READY_supersession']= "entry['verification_status']=='READY_VERIFIED_REPAIR'" in prep and "len(prior_ready)==1" in prep and "prior_ready[0]['repair_source_SHA']==expected_unstarted_source" in prep and "B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json" in prep
checks['no_supervisor_or_worker_stop_and_no_solve_in_helper_scripts']=all('terminate(' not in t and 'kill(' not in t and '.optimize(' not in t for t in scripts.values())
checks['enqueue_lease_and_queue_lock_verified_by_retained_control']= 'recovery.assert_lease(root,args.lease_token)' in prep and 'recovery.enqueue(root,failure,repair,lease_token=args.lease_token,**options)' in prep
control_data,control_receipt=take(REPO/'v42_autonomous/recovery.py','recovery.py');control=control_data.decode('utf8')
checks['control_rechecks_unstarted_target_under_queue_lock']='with os_lock(root / \'RECOVERY_QUEUE.lock\'):' in control and 'not _unstarted_ready(previous)' in control and 'not _supervisor_preserves_unstarted_target(root,previous)' in control
checks['active_dates_excluded_from_dispatch']= "and row['date'] not in active" in control
checks['only_current_sealed_scientific_accounting_PASS_retires_unstarted_READY']='CURRENT_SEALED_SCIENTIFIC_AND_ACCOUNTING_VERIFIED_PASS' in control and "if proof is not None and _unstarted_ready(row):" in control
checks['explicit_zero_start_authorization_allows_historical_exhausted_cost_without_overwrite']='reset=zero_start_authorization(root,repair)' in control and "if reset is None and failure['arm'] == 'B2' and consumed >= limit:" in control and 'remaining_native_seconds=limit if reset is not None' in control
template_data,template_receipt=take(ROOT/'autonomous/V31_VALIDATION_BINDING_TEMPLATE.json','V31_VALIDATION_BINDING_TEMPLATE.json');template=json.loads(template_data)
union=template['sparse_required_source_union']
checks['union_is1110_relative_path_strings_not_D30_SHA_receipts']=len(union)==1110 and all(isinstance(name,str) and not Path(name).is_absolute() for name in union)
expected={Path(item['path']).relative_to(REPO).as_posix() for field in ('source_files','original_source_files','sparse_required_additional_assets') for item in template[field]}
checks['unchanged_union_exactly_matches_new31_source_membership']=set(union)==expected
freeze_data,freeze_receipt=take(ROOT/'autonomous/V31_SPARSE_IMMUTABLE_FREEZE.json','V31_SPARSE_IMMUTABLE_FREEZE.json');frozen=json.loads(freeze_data)
checks['actual_D31_frozen_historical_source']=frozen['code_root']==r'D:\v42run31' and frozen['commit']=='d9b5c52d3436943a807f0860e2548b029e7f9dc9' and frozen['execution_source_count']==98 and frozen['builder_original_source_count']==1007 and frozen['unique_file_count']==1110
cp_data,cp_receipt=take(ROOT/'SUPERVISOR_STATE.json','SUPERVISOR_STATE.json');cp=json.loads(cp_data)
queue_data,queue_receipt=take(ROOT/'RECOVERY_QUEUE.json','RECOVERY_QUEUE.json');queue=json.loads(queue_data)
registry_data,registry_receipt=take(ROOT/'AUTONOMOUS_MANIFEST.json','AUTONOMOUS_MANIFEST.json');registry=json.loads(registry_data)
source30=json.loads((ROOT/'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json').read_bytes())['execution_SHA']
ready=[{key:row.get(key) for key in ('queue_id','date','repair_source_SHA','retry_attempt_id','new_worker_PID','verification_status')} for row in queue['entries'] if row['verification_status']=='READY_VERIFIED_REPAIR' and row['repair_source_SHA']==source30]
workers=[{key:row.get(key) for key in ('PID','created','command','request','day','arm','source_SHA')} for row in cp['workers'].values()]
checks['Source31_not_deployed_in_registry']=registry['B2_code_root']!=r'D:\v42run31' and registry['B2_source_SHA']!=template['repair_source_SHA']
checks['no_Source31_queue_dispatch_by_this_historical_candidate']=not any(row['repair_source_SHA']==template['repair_source_SHA'] for row in queue['entries'])
doc=dict(schema='V42_SOURCE31_OPERATIONAL_HELPERS_STATIC_READ_ONLY_REVIEW_V1',UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 PASS=all(checks.values()),checks=checks,raw_single_read_receipts=records,
 Source31_frozen_historical_candidate_only=True,Source31_deployed=False,
 actual_Source30_workers=workers,actual_Source30_unstarted_READY=ready,
 dynamic_enqueue_plan='NewSource32/31 date repairs while another source is active are added READY without superseding active records. Only whichever Source30 READY rows remain unstarted at locked enqueue may be superseded; the count must not be fixed to6 after natural dispatch.',
 corrected_review_finding='Earlier reviewer inferred sparse_required_source_union contained D30 paths/SHA records without checking elements. Actual union contains1110 unchanged relative path strings and exactly matches the new Source31 membership; no change is needed.',
 owner_binding_scope='Template checks ownerPASS only; Root declared a separate immutable predeployment sanity receipt will additionally bind owner1105/execution/start-end/tests and1110 membership without rewriting the sealed template.',
 known_scientific_operational_blocker='Actual Source30 May01 RMP_PRESOLVE_ORIGINAL_BUDGET_OR_SCOPE_CLOSURE_DRIFT: CLI __main__.ReceiptDateBudget versus canonical worker class. Source31 retains that worker. Root has explicitly held Source31 deployment and assigned a minimal canonical CLI repair for combined Source32.',
 helper_control_review_is_not_scientific_or_deployment_qualification=True,
 actual_Source31_requests27_not_created_or_admitted_by_reviewer=True,
 Native_optimize_calls=0,real_Native_model_constructions=0,operational_helpers_executed=0,
 production_or_immutable_or_queue_or_process_or_Git_mutations=0)
target=A/'SOURCE31_OPERATIONAL_HELPERS_STATIC_READ_ONLY_REVIEW.json';data=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf8')
with target.open('xb') as f:f.write(data)
print(json.dumps(dict(PASS=doc['PASS'],path=str(target),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),
 failed_checks=[name for name,passed in checks.items() if not passed],Source30_READY_dates=[row['date'] for row in ready],active_dates=[row['day'] for row in workers]),indent=2))
