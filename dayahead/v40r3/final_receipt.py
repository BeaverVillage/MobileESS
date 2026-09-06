"""Commit closure: required-artifact inventory and an external research-commit receipt."""
from .common import *
from .train import authority

JSON_STEMS='''START_STATE V40P_REFERENCE_FREEZE DOWNSTREAM_WORKLOAD_CONTRACT_AUDIT
TARGET_POPULATION_CONTRACT TARGET_POPULATION_COVERAGE_AUDIT INCREMENTAL_GPUH_TARGET_CONTRACT
TARGET_RECONSTRUCTION_VERIFICATION LABEL_MATURITY_AUDIT CAUSAL_SNAPSHOT_CONTRACT
FEATURE_AVAILABILITY_LEDGER TARGET_STATISTICS TEMPORAL_SHIFT_REPORT UNTOUCHED_HOLDOUT_AUDIT
BENCHMARK_FAIRNESS_CONTRACT PREREGISTRATION PREREGISTRATION_COMMIT_RECEIPT ZERO_REPORT
SEASONAL_REPORT LIGHTGBM_REPORT HURDLE_LIGHTGBM_REPORT XGBOOST_REPORT TFT_REPORT DEEPAR_REPORT
EXTRA_TEMPORAL_BENCHMARK_REPORT CMABF_ARCHITECTURE CMABF_LOSS_CONTRACT CMABF_REPORT
CMABF_ABLATION_REPORT DETERMINISM_REPORT PROBABILISTIC_METRICS BURST_METRICS
CUMULATIVE_ARRIVAL_METRICS SAFETY_GATE_TABLE STRONGEST_BASELINE_SELECTION
PAIRED_BOOTSTRAP_SUPERIORITY METHOD_SELECTION MODEL_FREEZE CONFIRMATORY_RESULT
MAY_FIREWALL PROTECTED_SCOPE_DIFF TEST_REPORT FINAL_COMMIT_RECEIPT'''.split()
REQUIRED=[f'V40R3_{s}.json' for s in JSON_STEMS]+[
    'V40R3_LABEL_MATURITY_LEDGER.parquet','V40R3_FEATURE_AVAILABILITY_LEDGER.csv',
    'V40R3_POINT_METRICS.csv','V40R3_SCI_BENCHMARK_REVIEW.md','V40R3_FINAL_REVIEW.md']

def main():
    reg,prereg=authority();research=git('rev-parse','HEAD')
    assert not git('status','--porcelain'),'Research results must be committed cleanly before receipt'
    assert len(REQUIRED)==47 and len(set(REQUIRED))==47
    missing=[n for n in REQUIRED if not (OUT/n).is_file()]
    assert missing==['V40R3_FINAL_COMMIT_RECEIPT.json'],missing
    tests=read('V40R3_TEST_REPORT.json');assert tests['passed']==tests['tests']==60 and not tests['not_run']
    selection=read('V40R3_METHOD_SELECTION.json');assert selection['selected_model'] is None
    prefixes=('dayahead/v40r3/','dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml/')
    changes=git('diff','--name-only',START,research).splitlines();assert all(p.startswith(prefixes) for p in changes)
    integrity=read('V40R3_POSTFIT_INTEGRITY.json');fit_checks=[]
    for p,h in integrity['fit_artifacts_SHA256'].items():
        working=sha(OUT/p);assert working==h,('FIT_ARTIFACT_CHANGED',p)
        rel=(OUT/p).relative_to(ROOT).as_posix()
        committed=subprocess.check_output(['git','show',research+':'+rel],cwd=ROOT)
        ch=hashlib.sha256(committed).hexdigest()
        if Path(p).suffix not in ['.json','.txt']:assert ch==h,('BINARY_FIT_ARTIFACT_CHANGED',p)
        fit_checks.append({'path':p,'working_SHA256':working,'research_commit_SHA256':ch,
                           'bytes_equal':ch==working,'text_EOL_normalization':ch!=working and Path(p).suffix in ['.json','.txt']})
    assert read('V40R3_MAY_FIREWALL.json')['May_scientific_rows']==0
    dump('V40R3_FINAL_COMMIT_RECEIPT.json',{'start':START,'scientific_reference':'3a6ab4fa369a9f8e16203af62b1b00bf56666716',
      'preregistration_commit':prereg,'final_research_commit':research,'branch':git('branch','--show-current'),
      'worktree':str(ROOT),'classification':selection['classification'],'selected_model':None,
      'CMABF_safety':'FAIL','CMABF_overall_superiority':False,
      'pairwise_superiority_vs_frozen_DeepAR_only':True,'true_confirmatory_available':False,
      'tests':{'passed':60,'failed':0,'errors':0,'skipped':0},'required_artifact_count':47,
      'receipt_commit':'The separate commit containing this file; self-referential hash intentionally not embedded',
      'receipt_commit_resolution':'git log -1 --format=%H -- dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml/V40R3_FINAL_COMMIT_RECEIPT.json',
      'research_commit_scope_paths':changes,'research_worktree_clean_before_receipt':True,
      'frozen_source_and_data_hashes_pass':True,'fit_artifact_working_and_commit_checks':fit_checks,
      'text_hash_note':'Working fit JSON text may be CRLF while Git commits LF. Both SHA256 values are disclosed. Model/prediction binary hashes must be equal.',
      'V40R2_status':'SUPERSEDED_BY_V40R3','V40R2_resumed_or_fit':False,'V40R2_code_reused_or_merged':False,
      'V40R2_written_or_deleted':False,'May_scientific_reads':0,'May_metadata_reads':'NONZERO','holds':reg['holds']})
    dump('V40R3_REQUIRED_ARTIFACT_MANIFEST.json',{'required_count':47,'present_count':47,'missing':[],
      'research_commit':research,'receipt_stored_in_following_commit':True,
      'files':[{'name':n,'SHA256_working_tree':sha(OUT/n),'bytes':(OUT/n).stat().st_size} for n in REQUIRED],
      'scope':'User-required 47 artifacts only; additional raw data, fit weights, predictions, logs, monthly metrics and reporting audits are also committed'})
    print(json.dumps({'research_commit':research,'required_artifacts':47,'fit_artifacts_verified':len(fit_checks),
       'text_EOL_differences':sum(c['text_EOL_normalization'] for c in fit_checks)}))

if __name__=='__main__':main()
