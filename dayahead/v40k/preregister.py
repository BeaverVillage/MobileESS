from .common import *
from .protocol import SPLIT,REGISTRY,POINT_GATE,SAFE,LGB

FROZEN=['V40K_TEMPORAL_SPLIT_CONTRACT.json','V40K_POINT_ESTIMAND_CONTRACT.json','V40K_CANDIDATE_REGISTRY.json','V40K_SAFE_BOUND_REGISTRY.json','V40K_PREMAY_READ_FIREWALL.json']
def main():
    assert not (OUT/'POINT_SELECTION_ROWS.parquet').exists()
    assert not (OUT/'models').exists(),'PREREGISTRATION_MUST_PRECEDE_NEW_FIT'
    write('V40K_TEMPORAL_SPLIT_CONTRACT.json',SPLIT,immutable=True)
    write('V40K_POINT_ESTIMAND_CONTRACT.json',POINT_GATE,immutable=True)
    write('V40K_CANDIDATE_REGISTRY.json',{'created_at':now(),'candidates':REGISTRY,'LightGBM':LGB,
      'baseline':'Existing pinned 3.2.0 XGBoost environment; old state adapter byte-reproduction plus final causal double fit',
      'feature_contract':FEATURES,'invalid_requested_walltime':'exclude from common scientific cohort and record; no physical cap invented',
      'training_order':'preregister commit, fit locked models/inner weights, commit model lock, open point holdout once',
      'long_history':'not added','source_forensic_SHA':sha(OUT/'V40K_POINT_SWING_ROOT_CAUSE.json'),
      'estimated_compute':'single-thread deterministic fits, double refits; approximately 10-25 minutes on this host, no optimizer campaigns'},immutable=True)
    write('V40K_SAFE_BOUND_REGISTRY.json',SAFE,immutable=True)
    prior=json.loads((J/'V40J_FIREWALL_COUNTERS.json').read_text())
    write('V40K_PREMAY_READ_FIREWALL.json',{'new_May_scientific_counters':{k:0 for k in ['MAY_RUNTIME_OR_STATUS_ROW_READS','MAY_ACTUAL_OUTCOME_READS','MAY_MODEL_BUILDING_READS','MAY_TRAINING_READS','MAY_CALIBRATION_READS','MAY_MODEL_SELECTION_READS','MAY_HYPERPARAMETER_SELECTION_READS']},
      'inherited_V40J_counters_preserved':prior['counters'],'new_April_footer_metadata_operations':1,
      'new_May_path_code_payload_search':False,'session_total_read_zero_claim':False,
      'raw_access':'single allowlisted April member, whole group submit/start/end footer gating before column decoding; May members never opened',
      'temporal_guard':SPLIT['raw_decoder_policy'],'shadow':'both winners frozen, no retune/refit after opening',
      'Python_audit':'V40J read-only, V40K-only writes; native Arrow reads explicitly use audited byte streams or gated row groups',
      'initial_nondata_denials':'SciPy temporary-file probes outside V40K were denied during forensic import; temp directory was moved into V40K before successful audit. No May payload exposed.'},immutable=True)
    write('V40K_PREREGISTRATION_DRAFT.json',{'created_at':now(),'frozen_artifact_sha256':{n:sha(OUT/n) for n in FROZEN},'new_training_started':False,'new_point_holdout_opened':False,'shadow_opened':False})
    event('preregistration_authored',frozen=FROZEN)
    print('PREREGISTRATION_READY_TO_COMMIT',flush=True)
if __name__=='__main__':main()
