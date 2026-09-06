"""Metadata census and immutable protocol, before any V40J model fitting."""
import importlib.metadata
import json
import subprocess
import zipfile
from .contracts import *
from .firewall import sha, write, member_allowed

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True, encoding='utf-8').strip()

def main():
    assert git('rev-parse','HEAD') == START
    authorities = [ROOT/'dayahead/artifacts/v40i_authority_electrical_closure'/x for x in
       ['dual_forensic/V40I_FINAL_FORENSIC_REVIEW.md', 'dual_forensic/V40I_NEXT_REVISION_DECISION.md', 'V40I_FINAL_FORENSIC_COMMIT_RECEIPT.json']]
    tracked = git('ls-tree','-r',START).splitlines()
    stat_inventory = {}
    for line in tracked:
        path = ROOT / line.split('\t',1)[1]
        if path.exists():
            st = path.stat()
            stat_inventory[str(path.relative_to(ROOT)).replace('\\','/')] = [st.st_size, st.st_mtime_ns]
    write('V40J_START_STATE.json', {
      'starting_HEAD': START, 'git_log3': git('log','-3','--oneline').splitlines(),
      'status_file': 'START_WORKTREE_STATUS.txt', 'source_inventory': 'START_TRACKED_TREE.txt',
      'protected_tree_hashes': {p:git('rev-parse',START+':'+p) for p in ['dayahead/v40i','dayahead/artifacts/v40i_authority_electrical_closure','dayahead/v40h']},
      'protected_worktree_stat_inventory': stat_inventory,
      'authority_documents_motivation_only': {str(p.relative_to(ROOT)): sha(p) for p in authorities},
      'frozen_conclusions': ['POINT_SYSTEMATIC_UNDERPREDICTION_CONFIRMED','POOLED_Q_CONDITIONAL_INSUFFICIENCY_CONFIRMED','MULTI_REGIME',
         'FAILED_SHORT_DIRECT_EFFECT_PLAUSIBLE_NOT_PROVEN','12H_SPARSE','HISTORICAL_MAY_REGIME_MISMATCH',
         'HYBRID_PREDICTOR_CALIBRATION_ROBUST','RETAIN_FIXED_PF'],
      'authority_missing':72, 'electrical_regeneration':'HOLD','B2_B3':'NO','FULL_MAY':'NO',
      'discovery_exception': 'One initial rg content search included May-related source paths because exclusion globs were ineffective. No candidate was fitted and no returned outcome value used. Session-wide source read count cannot be certified zero; guarded model-building counter is separate.',
      'raw_archive_sha256': sha(ARCHIVE), 'archive_hash_only_note': 'Full compressed-container integrity hashing is not member decoding; only allowlisted pre-May member payloads may enter model building.',
      'external_sha256': sha(EXTERNAL), 'external_sha_PASS':sha(EXTERNAL)==EXTERNAL_SHA,
      'environment': {p:importlib.metadata.version(p) for p in ['numpy','pandas','pyarrow','lightgbm','scikit-learn','pytest']}
    }, immutable=True)
    with zipfile.ZipFile(ARCHIVE) as z:
        members = [{'path': i.filename, 'bytes': i.file_size, 'CRC32': i.CRC} for i in z.infolist() if member_allowed(i.filename,shadow=True)]
    write('V40J_PREMAY_RUNTIME_DATA_CENSUS.json', {'stage':'METADATA_ONLY_PRE_REGISTRATION', 'members':members,
      'available_month_partitions':['2023-08','2025-04'], 'row_census':'emitted separately by guarded extraction',
      'April_payload_opened':False, 'known_causal':FEATURES9+['submit_time'],
      'retrospective':['state_simple','end_time','start_time','wallclock_used'],
      'unavailable_at_submit':['realized queue_wait','nodelist','resource utilization','actual queue state history'],
      'hardware_rule':'requested partition gpu-h100 only; no allocated-node inference',
      'standby_rule':'requested QoS equals standby', 'identity_metadata':'existing anonymized user/account only; no re-identification'}, immutable=True)
    write('V40J_CAUSAL_FEATURE_CONTRACT.json', {'features':FEATURES,'baseline_features':FEATURES9,'forbidden':sorted(FORBIDDEN),
      'categorical':CATEGORICAL,'metadata':'submit timestamp derives UTC hour/day/week; hardware from requested partition, standby from QoS',
      'production_api':'accept exact feature names/order; reject unknown or retrospective columns, not silently strip',
      'causality_limitation':'source is retrospective sacct export; request fields assumed immutable as original nine-input authority; no historical request-edit ledger',
      'status_use':'historical mixture target or evaluation strata only', 'PF':PF}, immutable=True)
    write('V40J_TEMPORAL_SPLIT_CONTRACT.json',SPLIT,immutable=True)
    write('V40J_CANDIDATE_REGISTRY.json',{'seed':SEED,'candidates':CANDIDATES,'lightgbm':LGB,'support_thresholds':SUPPORT,
      'walltime_bucket_upper_seconds':WALL_BUCKETS,'candidate_addition_after_results':'FORBIDDEN','dependencies_install':'NO',
      'envelopes':ENVELOPES},immutable=True)
    write('V40J_MODEL_SELECTION_HIERARCHY.json',SELECTION,immutable=True)
    write('V40J_PREMAY_READ_FIREWALL.json', {'scope':'training/model selection/calibration/final shadow subprocesses',
      'mechanism':'Python audit hook allowlist plus ZIP year/month rejection plus projected Arrow bytes; no V40I data artifacts in model allowlist',
      'model_building_may_read_count':0,'count_state':'NOT_STARTED; final counters in V40J_FIREWALL_EXECUTION_REPORT.json',
      'historical_motivation_reads':[str(p.relative_to(ROOT)) for p in authorities],
      'discovery_source_search_exception':True,'session_wide_zero_read_claim':False,
      'shadow_month_open_gate':'V40J_SELECTION_FREEZE.json must exist before April member payload read',
      'legacy_regression_process':'separate post-selection verification; never a candidate-selection input',
      'raw_member_rule':'2023-08 through 2025-03 during building; 2025-04 after winner freeze; >=2025-05 denied',
      'row_rule':'no May submit rows; labels must be end-known by declared pre-May deadline',
      'writes':'V40J namespace only; no production model or PF changes'},immutable=True)
    names=['V40J_CAUSAL_FEATURE_CONTRACT.json','V40J_TEMPORAL_SPLIT_CONTRACT.json','V40J_CANDIDATE_REGISTRY.json','V40J_MODEL_SELECTION_HIERARCHY.json','V40J_PREMAY_READ_FIREWALL.json']
    write('V40J_PREREGISTRATION_REVIEW.json',{'files':{n:sha(OUT/n) for n in names},'review':'PASS',
      'checks':['causal-only inputs','chronological purged training','April payload isolated','C0 reproduction before candidate fit','four required families plus explicit C4 skip',
      'frozen 90% coverage/min-support/formulas','safety before accuracy','shadow cannot select winner','no production authorization'],
      'limits':['session discovery exception retained','complete-case shadow cannot prove censored-runtime safety','no grid-specific authority fabricated']},immutable=True)
    print('PREREGISTRATION_READY')

if __name__ == '__main__':
    main()
