"""Bind the completed research commit to a separately committed receipt."""
from .common import *
from .backtest import PREREG
from .finalize import read

REQUIRED='''V40P_START_STATE.json
V40P_MODEL_SOURCE_CENSUS.json
V40P_MODEL_LINEAGE.json
V40P_MODEL_SHA_VERIFICATION.json
V40P_DATASET_IDENTITY_AUDIT.json
V40P_FACILITY_MIXING_AUDIT.json
V40P_TARGET_CONTRACT.json
V40P_FORECAST_ORIGIN_CONTRACT.json
V40P_HORIZON_CONTRACT.json
V40P_FEATURE_AVAILABILITY_LEDGER.csv
V40P_FEATURE_AVAILABILITY_LEDGER.json
V40P_LEAKAGE_AUDIT.json
V40P_PREPROCESSING_LEAKAGE_AUDIT.json
V40P_TEMPORAL_SPLIT_AUDIT.json
V40P_TRUE_HOLDOUT_AUDIT.json
V40P_FROZEN_INFERENCE_REPRODUCTION.json
V40P_BACKTEST_PREREGISTRATION.json
V40P_ROLLING_BACKTEST_REPORT.json
V40P_FUTURE_ARRIVAL_METRICS.csv
V40P_FUTURE_ARRIVAL_METRICS.json
V40P_FIXED_LOAD_METRICS.csv
V40P_FIXED_LOAD_METRICS.json
V40P_BASELINE_SKILL_REPORT.json
V40P_BLOCK_BOOTSTRAP_REPORT.json
V40P_BURST_FORECAST_REPORT.json
V40P_UNDERPREDICTION_RISK_REPORT.json
V40P_TEMPORAL_SHIFT_REPORT.json
V40P_HORIZON_CONSISTENCY_REPORT.json
V40P_KNOWN_FUTURE_DOUBLECOUNT_AUDIT.json
V40P_FIXED_FLEXIBLE_SEPARATION_AUDIT.json
V40P_DAYAHEAD_INTEGRATION_AUDIT.json
V40P_MAY_READ_FIREWALL.json
V40P_PROTECTED_SCOPE_DIFF.json
V40P_TEST_REPORT.json
V40P_FINAL_REVIEW.md
V40P_FINAL_COMMIT_RECEIPT.json'''.splitlines()

def main():
    assert not git('status','--porcelain'),'Commit research outputs first'
    research=git('rev-parse','HEAD')
    scope=git('diff','--name-only',START,research).splitlines()
    assert all(p.startswith(('dayahead/v40p/','dayahead/artifacts/v40p_lightgbm_forecast_forensic/')) for p in scope)
    receiptname='V40P_FINAL_COMMIT_RECEIPT.json'
    absent=[n for n in REQUIRED if n!=receiptname and not (OUT/n).is_file()]
    assert not absent,absent
    blobs=[]
    for p in scope:
        data=subprocess.check_output(['git','show',research+':'+p],cwd=ROOT)
        blobs.append({'path':p,'committed_bytes':len(data),'committed_content_SHA256':hashlib.sha256(data).hexdigest()})
    bypath={r['path']:r for r in blobs}
    prefix=OUT.relative_to(ROOT).as_posix()+'/'
    census=read('V40P_MODEL_SOURCE_CENSUS.json')
    for r in census['models']:
        assert bypath[prefix+'frozen_models/'+r['model_id']+'.txt']['committed_content_SHA256']==r['model_SHA256']
    for r in read('source_snapshots.json'):
        assert bypath[Path(r['snapshot']).as_posix()]['committed_content_SHA256']==r['sha256']
    tests=read('V40P_TEST_REPORT.json');firewall=read('V40P_MAY_READ_FIREWALL.json')
    dump(receiptname,{'branch':git('branch','--show-current'),'worktree':ROOT,'starting_commit':START,'preregistration_commit':PREREG,'final_research_commit':research,'receipt_commit':'This file is committed separately immediately after final_research_commit; obtain its own commit from git log. A commit cannot contain its own SHA.','required_artifact_count':len(REQUIRED),'required_artifacts':REQUIRED,'missing_required_artifacts_except_this_receipt':absent,'committed_model_and_source_bytes_verified':True,'frozen_model_SHAs':read('V40P_MODEL_SHA_VERIFICATION.json'),'tests':{k:tests[k] for k in ['tests_run','passed','expected_scientific_failures','unexpected_failures','scientific_all_gates_pass']},'protected_scope_outside_changes':[],'MAY_SCIENTIFIC_OUTCOME_READS':firewall['MAY_SCIENTIFIC_OUTCOME_READS'],'May_counter_unit':firewall['counter_unit'],'MAY_SCIENTIFIC_OUTCOME_DATA_ROWS_DECODED':0,'MAY_METADATA_CODE_DISCOVERY':'NONZERO','scientific_classification':'V40P_FORECAST_CAUSALITY_FAIL','integrity_holds':read('V40P_START_STATE.json')['integrity_holds'],'research_committed_files':blobs})
    print(json.dumps({'final_research_commit':research,'required_artifacts':len(REQUIRED),'research_files':len(blobs),'receipt':str(OUT/receiptname)},ensure_ascii=False))

if __name__=='__main__':main()
