from pathlib import Path
import json,hashlib,datetime
A=Path(r'D:\v42_full_lp_warmstart_readonly_review_20261010_01')
R=Path(r'D:\v42_may_restart_20261010_02')
raw=A/'actual_Source30_cap_raw';raw.mkdir(exist_ok=False)
records=[]
def take(p,n):
 data=p.read_bytes();t=raw/n
 with t.open('xb') as f:f.write(data)
 receipt=dict(source_path=str(p),snapshot_path=str(t),bytes=len(data),
  sha256=hashlib.sha256(data).hexdigest(),source_read_count=1,snapshot_bytes_exact=True)
 records.append(receipt)
 return json.loads(data),receipt
cp,cpr=take(R/'SUPERVISOR_STATE.json','SUPERVISOR_STATE.json')
rows=[]
for day in ['2025-05-01','2025-05-02','2025-05-03']:
 worker=cp['workers']['B2/'+day];attempt=Path(worker['request']).parent
 req,rr=take(Path(worker['request']),day+'_request.json')
 ledger,lr=take(attempt/'NATIVE_RUNTIME_LEDGER.json',day+'_NATIVE_RUNTIME_LEDGER.json')
 prog,pr=take(attempt/'progress.json',day+'_progress.json')
 warm,wr=take(attempt/'output/F1_FULL_LP_WARMSTART.json',day+'_F1_FULL_LP_WARMSTART.json')
 entry,er=take(attempt/'output/F1_FULL_LP_COMPUTATIONAL_ENTRY.json',day+'_F1_FULL_LP_COMPUTATIONAL_ENTRY.json')
 cap=next((c for c in ledger['calls'] if c['label']=='CURRENT_DAY_FULL_LP_EXACT_DUAL'),None)
 rows.append(dict(day=day,worker=worker,request_receipt=rr,ledger_receipt=lr,progress_receipt=pr,
  warmstart_receipt=wr,computational_entry_receipt=er,actual_parameters=entry['actual_parameters'],
  basis_mode=warm['mode'],remapped_nonbasic_endpoints=warm['remapped_nonbasic_endpoints'],
  free_zero_superbasics=warm['free_continuous_exact_zero_superbasics_retained'],
  completed_full_LP_call=cap,
  full_LP_inflight=bool(ledger['inflight'] and ledger['inflight']['label']=='CURRENT_DAY_FULL_LP_EXACT_DUAL'),
  progress_timestamp=prog['timestamp_UTC'],progress_iteration_count=prog.get('Native_iteration_count')))
first=rows[0]['completed_full_LP_call']
assert first and first['Native_Runtime']>=300 and first['Native_status']==11 and first['SolCount']==0 and first['error'] is None
manifest=json.loads((R/'B2_V30_ZERO_START_DEPLOYMENT_MANIFEST.json').read_bytes())
immutable=Path(r'D:\v42run30\v42_autonomous_b2\f1_basis.py');data=immutable.read_bytes()
immutable_receipt=dict(path=str(immutable),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
assert immutable_receipt['sha256']==manifest['execution_sources']['v42_autonomous_b2/f1_basis.py']
proposal=dict(schema='V42_SOURCE30_ACTUAL_FULL_LP_300_CAP_AND_SOURCE31_COMPUTATIONAL_CANDIDATE_V1',
 UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),PASS=True,actual_timeout_observed=True,
 actual_timeout_status_is_policy_interrupt_11_not_fabricated_9=True,
 actual_Source30_source_SHA=manifest['execution_SHA'],actual_workers=rows,raw_single_read_receipts=records,
 immutable_Source30_basis_adapter_unchanged=immutable_receipt,
 primary_official_sources=[
  dict(url='https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#lpwarmstart',
   claims=['LPWarmStart1 simplex uses the original unpresolved problem from the provided basis.',
   'LPWarmStart2 derives primal/dual solutions from an original basis, crushes starts, and refines the presolved crash basis; Method0 uses the primal start.',
   'Method0 means primal simplex; Method1 means dual simplex.']),
  dict(url='https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#vbasis',
   claims=['Complete VBasis/CBasis required for an advanced basis; valid starts disable LP presolve by default unless LPWarmStart2.'])],
 observed_mechanism='Actual current F1 COMPLETE_SAME_ATTEMPT_ORIGINAL_BASIS reaches Method0/LPWarmStart1, original matrix/domain/objective guard passes, iterations increase and exactly one original300s call is completed without an adapter exception.',
 causal_hypothesis='LPWarmStart1 prevents LP presolve and reoptimizes the unpresolved full problem; enabling presolved start transport could reduce this observed repeated300s bottleneck.',
 full_root_cause_proved=False,
 unknowns=['No SPX_PRIMINF/SPX_DUALINF telemetry; the disabled solver log contains only a header, so degeneracy, conditioning and primal-feasibility repair cannot be distinguished.',
  'LPWarmStart2 may add crush/factorization cost or numerical sensitivity and may also reach300s.',
  'Original solved F1 basis eligibility remains computational authority only, never independent Global_LB.'],
 candidate=dict(changed_files=['v42_autonomous_b2/f1_basis.py','tests/test_v42_autonomous_b2_f1_basis.py'],
  basis_install=dict(Method=1,LPWarmStart=1),approved_exact_P1_M_LB_entry=dict(Method=0,LPWarmStart=2),
  complete_current_F1_basis_eligibility_unchanged=True,
  original_matrices_domains_RHS_senses_names_ObjCon_objective_unchanged=True,
  original_precision_Threads1_120_300_5400_unchanged=True,
  fallback_current_Method1_primal_dual2_unchanged=True,no_previous_attempt_or_Source27_vectors_admitted=True,
  all_guard_pre_and_post_parameter_expectations_explicit=True,presolved_basis_identity_unchanged_claimed=False,
  independent_full_original_signed_checker_fresh_and_unchanged=True),
 Native_optimize_calls=0,real_Native_model_constructions=0,
 read_only_production_worker_or_queue_or_request_or_immutable_changes=0,
 production_changes_only_authorized_candidate_two_files=True,
 real_Source31_performance_or_Global_LB_or_final_day_PASS_proved=False)
p=A/'SOURCE30_ACTUAL_FULL_LP_CAP_AND_SOURCE31_CANDIDATE_PROPOSAL.json'
data=(json.dumps(proposal,ensure_ascii=False,indent=2)+'\n').encode('utf8')
with p.open('xb') as f:f.write(data)
print(json.dumps(dict(PASS=True,actual_timeout_observed=True,path=str(p),
 sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),
 actual_days=[dict(day=x['day'],full_LP_runtime=x['completed_full_LP_call']['Native_Runtime'] if x['completed_full_LP_call'] else None,
  status=x['completed_full_LP_call']['Native_status'] if x['completed_full_LP_call'] else None,
  inflight=x['full_LP_inflight']) for x in rows]),indent=2))
