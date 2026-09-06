"""Predeclared protocol. Change only through an explicit amendment."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'dayahead/artifacts/v40j_runtime_redesign'
START = '3f6317efeffac7e3fbc37d9c3c2ddca57357c70f'
DATA_ROOT = Path('C:/Users/kjw39/OneDrive/Desktop/4-2/Mobile ESS/raw데이터/데이터 센터')
ARCHIVE = DATA_ROOT / 'NLR HPC Kestrel Jobs Data/esif.hpc.kestrel.job-anon.zip'
EXTERNAL = DATA_ROOT / 'University_Cordoba_DataCenter_PQ/Dataset_data_center.xlsx'
EXTERNAL_SHA = 'b3c94fe028abff98734c38a828d2227e403c83922a42670672e693a8fecc4591'
LEGACY = Path('C:/Users/kjw39/OneDrive/문서/ChatGPT/Mobile ESS 2/MobileESS_v35r3d_kestrel_runtime_authority_closure')
LEGACY_CACHE = LEGACY / 'dayahead/cache/v35r3d_kestrel_runtime_authority_closure'
LEGACY_PYTHON = Path('C:/Users/kjw39/AppData/Local/MobileESS/venvs/v35r3d-runtime/Scripts/python.exe')
FEATURES9 = ['requested_seconds', 'num_nodes_req', 'num_cores_req', 'num_gpus_req',
             'requested_memory_mib', 'partition', 'qos', 'user', 'account']
FEATURES = FEATURES9 + ['submit_hour', 'submit_dow', 'submit_week', 'hardware', 'standby']
CATEGORICAL = ['partition', 'qos', 'user', 'account', 'hardware']
FORBIDDEN = {'final_status', 'state', 'state_simple', 'job_state', 'actual_runtime',
             'runtime_seconds', 'actual_runtime_seconds', 'end_time', 'start_time',
             'nodelist', 'queue_wait', 'nodes_used', 'processors_used', 'wallclock_used',
             'num_nodes_alloc', 'num_cores_alloc', 'shared_job_count', 'exit_code'}
Q = 5576.44921875
PF = .95
SEED = 4010
SUPPORT = [100, 200, 500]
# Standard duration scales; no special 12h rule.
WALL_BUCKETS = [3600, 21600, 86400, 259200]
SPLIT = {
    'timezone': 'UTC', 'intervals': 'left closed, right open',
    'model_scope': 'submitted GPU jobs, num_gpus_req > 0; no CPU-only claim',
    'training_lookback_days': 120,
    'folds': [
        {'id': 'F1', 'fit_before': '2025-02-08', 'calibration': ['2025-02-08', '2025-02-15'], 'validation': ['2025-02-15', '2025-02-22']},
        {'id': 'F2', 'fit_before': '2025-02-15', 'calibration': ['2025-02-15', '2025-02-22'], 'validation': ['2025-02-22', '2025-03-01']},
        {'id': 'F3', 'fit_before': '2025-02-22', 'calibration': ['2025-02-22', '2025-03-01'], 'validation': ['2025-03-01', '2025-03-08']},
    ],
    'final_fit_before': '2025-03-08',
    'final_calibration': ['2025-03-08', '2025-04-01'],
    'final_shadow': ['2025-04-24', '2025-05-01'],
    'unused_buffer': ['2025-04-01', '2025-04-24'],
    'shadow_isolation': 'April member payload is never opened until winner freeze; metadata census only before freeze',
    'training_rule': 'end_time < fit_before, submit_time < fit_before, end_time >= fit_before - 120d',
    'calibration_rule': 'submit in calibration block and end_time known before following validation/shadow issue',
    'validation_label_deadline': '2025-03-08',
    'shadow_label_deadline': '2025-05-01',
    'censoring': 'unknown/late end is excluded from complete-case metrics and counted; no future runtime computed',
    'shadow_use': 'acceptance only, cannot replace winner; latest seven UTC dates must each have rows, otherwise HOLD',
    'no_may': True,
}
LGB = {'n_estimators': 200, 'num_leaves': 31, 'learning_rate': .05,
       'min_child_samples': 100, 'max_bin': 255, 'random_state': SEED,
       'n_jobs': 1, 'deterministic': True, 'force_col_wise': True, 'verbosity': -1}
CANDIDATES = [
    {'id': 'C0', 'family': 'CURRENT_BASELINE', 'objective': 'exact pinned MoE-XGBoost reg:absoluteerror', 'q': Q},
    {'id': 'C1_L1', 'family': 'CAUSAL_POINT', 'objective': 'regression_l1'},
    {'id': 'C1_LOG', 'family': 'CAUSAL_POINT', 'objective': 'regression', 'target': 'log1p(runtime_seconds)'},
    {'id': 'C1_HUBER', 'family': 'CAUSAL_POINT', 'objective': 'huber', 'alpha': .9, 'target': 'runtime hours'},
    {'id': 'C1_Q50', 'family': 'CAUSAL_POINT', 'objective': 'quantile', 'alpha': .5},
    {'id': 'C2_MIXTURE', 'family': 'MIXTURE', 'early_target': 'FAILED or runtime <= 300 seconds',
     'gate': 'LightGBM binary causal X', 'components': 'log1p runtime regression in early/other historical groups',
     'nominal': 'probability-weighted component runtime expectations; future status never required'},
    {'id': 'C3_QUANTILE', 'family': 'DIRECT_QUANTILE', 'quantiles': [.5, .9, .95], 'repair': 'row-wise cumulative maximum'},
    {'id': 'C4', 'family': 'SURVIVAL_DISTRIBUTIONAL', 'status': 'NOT_EVALUATED_DEPENDENCY_UNAVAILABLE',
     'reason': 'no lifelines or scikit-survival in candidate environment; no package installation'},
]
ENVELOPES = {
    'R0': {'service': 'point', 'hard_occupancy': 'ceil900(point)', 'grid_reserve': '0'},
    'R1': {'service': 'point', 'hard_occupancy': 'ceil900(upper90)', 'grid_reserve': '0'},
    'R2': {'service': 'point', 'hard_occupancy': 'ceil900(point)', 'grid_reserve': 'GPU * (I[0,ceil900(upper90)) - I[0,ceil900(point)))'},
    'R3': {'service': 'point', 'hard_occupancy': 'ceil900(upper90)', 'grid_reserve': 'GPU * (I[0,ceil900(upper95)) - I[0,ceil900(upper90)))'},
}
SELECTION = {
    'priority': ['underprediction safety eligibility', 'GPU-weighted critical active miss',
                 'coverage', 'overreserved GPU-hours', 'point MAE then absolute bias', 'complexity'],
    'target_coverage': .9,
    'critical_groups': ['H100', 'standby', 'H100-standby', 'COMPLETED H100-standby (evaluation only)'],
    'coverage_gate': 'overall and each critical group with N >= selected min_support in every non-overlapping fold and pooled validation',
    'point_gate': 'paired day bootstrap 95% CI strictly below zero for completed H100-standby underprediction difference and absolute mean-bias difference',
    'bootstrap': {'seed': SEED, 'replicates': 2000, 'unit': 'UTC submit day; paired across methods'},
    'gpu_gate': 'predicted-finished-but-actually-active GPU-slots strictly lower than C0 on paired replay',
    'critical_slot_definition': 'all active-miss slots conservatively critical without independent pre-May line-loading authority; grid-specific metric unavailable',
    'conservatism_gate': 'overreserved GPU-hours and reserved GPU-hours <= requested-walltime reference; retain positive savings versus requested-walltime reference',
    'no_feasible_candidate': 'retain current production baseline; report best research candidate without calling it a winner; HOLD',
    'shadow_fail': 'HOLD, never choose another candidate',
    'calibration': {'hierarchy': [['hardware','standby','wall_bucket'], ['hardware','wall_bucket'], ['hardware'], []],
                    'min_support': SUPPORT, 'levels': [.9,.95],
                    'q_rule': 'nonnegative residual finite-sample higher rank ceil((n+1)*coverage), capped at n',
                    'bound': 'max(point, base quantile + nonnegative q); no requested-walltime cap on candidate bounds',
                    'sparse_fallback': 'skip exact group and use maximum q across eligible causal parents; out-of-support additionally uses requested walltime; abstain if request invalid'},
    'support_classes': {'STRONG_SUPPORT': 'exact9 >= min_support', 'SPARSE_SUPPORT': '0 < exact9 < min_support',
                        'REGIME_MISMATCH': 'exact9 == 0 and other8 >= min_support', 'OUT_OF_SUPPORT': 'otherwise'},
    'replay': 'same submit/start anchors for every method; realized start only evaluation anchor, never feature; capacity envelope comparison, no solver or site assignment',
    'envelopes': ENVELOPES,
    'layer_separation': True,
    'production_integration_default': 'NO',
}
