"""Create a single immutable registration after audits, before any fitting."""
from .common import *
from .causal_snapshot import HISTORY,PAST_NAMES,FUTURE_NAMES
import importlib.metadata,platform

def main():
    if (OUT/'V40R3_PREREGISTRATION.json').exists():raise RuntimeError('REGISTRATION_ALREADY_EXISTS')
    assert not list((OUT/'fits').glob('*/trial_*_start.json'))
    import torch
    from .neural import POS_LEVELS
    stats=read('V40R3_TARGET_STATISTICS.json');maturity=read('V40R3_LABEL_MATURITY_AUDIT.json')
    assert read('V40R3_TARGET_RECONSTRUCTION_VERIFICATION.json')['status']=='PASS'
    assert read('V40R3_TARGET_POPULATION_COVERAGE_AUDIT.json')['authorized_missing_end']==0
    architecture={'working_name':'CMABF','novelty_established':False,'encoder':'dual-stream causal dilated TCN',
      'selected_after_target_statistics':True,'history_steps':336,'step_minutes':30,'target_steps':48,
      'hidden_size':32,'dilations':[1,2,4,8],'kernel_size':3,'normalization':'per-position LayerNorm',
      'pooling':'last state concatenated with mean over historical states, linear projection to 32',
      'stream_A':['submission_count','hour_sin','hour_cos','weekday_sin','weekday_cos'],
      'stream_B':['mature_GPUh','mature_flag','maturity_age_hours'],
      'fusion':'sigmoid gate of concatenated stream summaries; g*A+(1-g)*B',
      'decoder':'Shared MLP (32+15)->64 GELU->32 GELU, residual 3-tap convolution over known-future representations',
      'occurrence':'Linear(32,1) then sigmoid','magnitude':'Linear(32,9), softplus nonnegative spacings, cumulative sum / 9',
      'positive_quantile_grid':POS_LEVELS,'unconditional_quantile':'0 if tau<=1-p; else positive quantile at (tau-1+p)/p',
      'interpolation':'piecewise linear; add (u=0,Q=0) endpoint; desired unconditional .5/.9 imply u<=.9',
      'hard_sanitation':'Maturity masking precedes all models and every ablation; no immature actual label is ever supplied',
      'ablations':{'A0':'Single encoder, mask/age information removed, hard value sanitation retained',
        'A1':'No occurrence head in loss; p=1 and grid trained on all targets','A2':'No burst loss term','A3':'FULL'},
      'V40R2_code_or_estimand_reused':False}
    loss={'target_scale':'TRAIN mature positive-target Q95 GPUh','occurrence':'Binary cross entropy on Y>0, coefficient 1',
       'quantile':'.5*(mean pinball_Q50 + mean pinball_Q90), coefficient 1',
       'positive_distribution':'.2*mean positive-only grid pinball; A1 uses all targets instead',
       'burst':'.25*mean[(1+min(Y/Q95_train,3))*pinball_Q90]',
       'alpha':1.,'cap':3.,'lambda_occ':1.,'lambda_q':1.,'lambda_positive':.2,'lambda_burst':.25,
       'peak_loss':None,'target_day_loss_weights_used':False,
       'interpretation':'Outcome weighting is operational emphasis, not a proper conditional quantile guarantee; raw and calibrated coverage separately reported'}
    models={
      'ZERO':{'family':'zero','output':[0.,0.],'trials':0,'Q90_calibration':False},
      'SEASONAL':{'family':'same-slot mature historical profiles','lags_days':[7,14,21,28],'quantiles':[.5,.9],'empty_fallback':0.,'trials':0,'Q90_calibration':True},
      'LIGHTGBM':{'family':'direct quantile gradient boosting','heads':[.5,.9],'objective':'quantile','trials':2},
      'HURDLE_LIGHTGBM':{'family':'binary plus positive quantile boosting','positive_quantiles':POS_LEVELS,'trials':2,'quantile_math':'mixture inverse CDF, not p*Q90'},
      'XGBOOST':{'family':'direct quantile gradient boosting','objective':'reg:quantileerror','quantile_alpha':[.5,.9],'tree_method':'hist','trials':2},
      'TFT':{'family':'upstream TemporalFusionTransformer','hidden_size':32,'lstm_layers':1,'attention_heads':2,'hidden_continuous_size':8,'dropout':.1,'trials':2},
      'DEEPAR':{'family':'upstream DeepAR','hidden_size':32,'rnn_layers':2,'dropout':.1,'likelihood':'Gaussian on scaled continuous GPUh','forecast':'256 autoregressive samples, negative samples censored at zero','trials':2,
          'teacher_forcing':'Allowed only for training likelihood; evaluation uses generated rollouts and no observed decoder targets'},
      'NHITS':{'family':'upstream NHiTS','hidden_size':128,'blocks':[1,1,1],'layers':2,'pooling':[8,4,1],'downsample_frequencies':[8,4,1],'dropout':.1,'naive_level':False,'backcast_loss':0.,'trials':2},
      'CMABF':{'family':'independent dual-stream TCN hurdle','architecture_file':'V40R3_CMABF_ARCHITECTURE.json','trials':2}}
    fairness={'same_cohort':True,'same_target':True,'same_origin':True,'same_label_maturity_exclusions':True,
      'same_train_dev_calibration_evaluation_dates':True,'same_source_information':True,
      'representations':'Trees flatten the exact past tensor and concatenate the exact decoder context; deep models receive the same tensors',
      'no_privileged_CMABF_input':True,'ML_trials_per_family':2,'deep_budget_identical':True,
      'neural_repeat_policy':'Winner independently retrained from the same fixed seed; max/mean prediction difference and metric variation measured, never assume bitwise equality',
      'tree_repeat_policy':'Selected LightGBM/hurdle/XGBoost retrained independently with the same seed',
      'ablation_budget':'Each of A0/A1/A2 gets one configuration using preregistered full-model selected LR plus one independent repeat; secondary only, cannot replace P1 or enlarge primary search',
      'concurrent_execution':'CPU tree fitting may overlap GPU deep fitting; trial/epoch ceilings unchanged, walltime logged'}
    deep={'learning_rates':[.001,.0003],'epochs':40,'batch_size':16,'patience':8,'min_delta':1e-6,'optimizer':'Adam',
      'weight_decay':1e-4,'gradient_clip_norm':1.,'search_seeds':[SEED],'repeat_seed':SEED,
      'forecast_samples':256,'forecast_sampling_seed':SEED+1000,'mixed_precision':False,
      'early_stopping':'Development primary metric, no teacher-forced metric; identical validation rule across families',
      'max_trial_walltime_seconds':1200,'deadline_rule':'Checked at epoch boundary, keep best observed development checkpoint; disclose if reached',
      'device':'cuda:0 when available, CPU fallback otherwise','deterministic_algorithms':True,'warn_only':True,
      'CUBLAS_WORKSPACE_CONFIG':':4096:8','cudnn_deterministic':True,'cudnn_benchmark':False,'TF32':False}
    trees={'learning_rates':[.03,.08],'n_estimators':400,'max_depth':6,'lightgbm_num_leaves':31,'lightgbm_min_child_samples':30,
      'xgboost_min_child_weight':10,'reg_lambda':1.,'max_bin':127,'seed':SEED,'threads':4,'device':'cpu','early_stopping':None,
      'subsample':1.,'feature_fraction':1.,'deterministic_lightgbm':True,'force_col_wise':True}
    dump('V40R3_CMABF_ARCHITECTURE.json',architecture);dump('V40R3_CMABF_LOSS_CONTRACT.json',loss)
    dump('V40R3_BENCHMARK_FAIRNESS_CONTRACT.json',fairness)
    env={'python':platform.python_version(),'python_executable':__import__('sys').executable,
      'frameworks':{p:importlib.metadata.version(p) for p in ['torch','pytorch-forecasting','lightning','pytorch-lightning','numpy','pandas','lightgbm','xgboost']},
      'GPU':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,'CUDA_runtime':torch.version.cuda,
      'CUDA_available_and_tensor_execution_verified':torch.cuda.is_available(),'driver_supported_CUDA_max':'13.0',
      'device':'cuda:0' if torch.cuda.is_available() else 'cpu','training_settings':deep,'fits_before_registration':0}
    dump('V40R3_COMPUTE_ENVIRONMENT.json',env)
    paths=['common.py','causal_snapshot.py','build_dataset.py','ingest.py','neural.py','metrics.py','train.py','evaluate.py']
    files=[ROOT/'dayahead/v40r3'/p for p in paths]
    files += [OUT/p for p in ['causal_dataset.npz','V40R3_LABEL_MATURITY_LEDGER.parquet','V40R3_FEATURE_AVAILABILITY_LEDGER.json',
      'V40R3_TARGET_POPULATION_CONTRACT.json','V40R3_INCREMENTAL_GPUH_TARGET_CONTRACT.json','V40R3_CMABF_ARCHITECTURE.json',
      'V40R3_CMABF_LOSS_CONTRACT.json','V40R3_BENCHMARK_FAIRNESS_CONTRACT.json','V40R3_SCI_BENCHMARK_REVIEW.md']]
    reg={'version':'V40R3','execution_authorized':True,'fits_so_far':0,'start':START,
      'target':'Scoped authorized GPUh increments assigned by SUBMIT, K=48, fixed 30-minute bins; no active-GPU target',
      'splits':{'TRAIN':['2024-03-15','2024-08-30'],'DEVELOPMENT':['2024-09-01','2024-10-30'],'CALIBRATION':['2024-11-01','2024-11-29'],
        'EXPOSED_EVALUATION':['2024-12-01','2025-02-26'],'training_cutoff':maturity['training_cutoff'],
        'selection_cutoff':maturity['development_selection_cutoff'],'calibration_cutoff':maturity['calibration_cutoff'],
        'maturity_counts':maturity['counts'],'random_split':False,'holdout':None},
      'models':models,'deep_training':deep,'tree_training':trees,
      'burst':{'definition':'Y>=positive TRAIN Q95','training_positive_Q95_GPUh':stats['training_positive_Q95'],'source':'Mature TRAIN targets only'},
      'primary_metric':'sum positive-interval Q90 pinball / sum positive actual GPUh',
      'selection_hierarchy':['all required safety gates','primary probabilistic metric','missed burst GPUh','positive WAPE','cumulative WAPE','simpler model'],
      'hyperparameter_selection':'Uncalibrated development primary, tie lower trial index; development labels mature before selection cutoff',
      'strongest_baseline_freeze':'Before bootstrap/evaluation metrics: rank development safety-pass non-CMABF models by hierarchy; if none pass, freeze minimum-primary comparator and disclose diagnostic status',
      'calibration':'Every nonzero family including seasonal: Q90 += max(0, finite-sample .9 quantile of residuals for overall, positive and training-threshold burst calibration subsets). Q50 unchanged. ZERO remains exactly zero.',
      'calibration_claim_limit':'Conservative operational Q90 forecast; conditional calibration does not guarantee future coverage or exact nominal conditional quantiles',
      'postprocessing':'All families: clamp negative increments at zero, then Q90=max(Q90,Q50); raw crossing counts retained. TFT/NHiTS raw head uses softplus. No result-driven repair.',
      'safety':{'overall_Q90':.9,'positive_Q90':.9,'burst_Q90':.9,'minimum_pooled_group_N':100,
        'monthly_gate':'All conditional coverage gates when N>=100, every natural month separately; no pooling away a failure',
        'catastrophic_block':'Overall point WAPE>2 in any month','causal_gate':'Every admitted feature available_at<=origin; no immature history or training label',
        'crossing':'Cumulative horizon crossing=0 and final quantile crossing=0'},
      'bootstrap':{'method':'Paired circular consecutive-day blocks','block_days':7,'replicates':5000,'seed':SEED,'CI':'percentile 2.5/97.5','superiority':'lower95>0'},
      'method_selection':'CMABF only if safety PASS, primary strictly better than every existing benchmark, and paired CI lower>0; otherwise strongest safety-pass existing model. If none safety-pass, safety FAIL.',
      'cumulative':'cumsum nonnegative marginal increments; summed Q90 is a derived scenario, not asserted distributional cumulative Q90',
      'maximum_positive_claim':'PREVALIDATED','confirmatory_available':False,'May_scientific_reads':0,
      'holds':{'PF':.95,'Q_control':False,'electrical_regeneration':'HOLD','B0_B3_electrical':False,'FULL_MAY':False,'optimizer':False,'production_q':'UNCHANGED'},
      'V40R2_status':'SUPERSEDED_BY_V40R3; no resumption/code reuse/merge/fitting/deletion',
      'frozen_source_and_data_SHA256':{p.relative_to(ROOT).as_posix():sha(p) for p in files}}
    dump('V40R3_PREREGISTRATION.json',reg)
    print('Registration written. All fitting remains gated until separate git commit and receipt.')

if __name__=='__main__':main()
