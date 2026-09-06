from .common import SEED

SPLIT={'timezone':'UTC','intervals':'[inclusive start, exclusive stop)',
 'canonical_cutoff':'2025-05-01T00:00:00+00:00','fixed_AEST_equivalent':'2025-05-01T10:00:00+10:00',
 'inner_folds':[{'id':'I1','fit_before':'2025-02-22','validation':['2025-02-22','2025-03-01'],'C0_state':'C0_F3'},
                {'id':'I2','fit_before':'2025-03-01','validation':['2025-03-01','2025-03-08'],'C0_state':'C0_F3'}],
 'development_label_deadline':'2025-03-08','final_point_fit_before':'2025-04-01',
 'point_selection':['2025-04-01','2025-04-08'],'safe_fit':['2025-04-08','2025-04-15'],
 'safe_selection':['2025-04-15','2025-04-24'],'final_shadow':['2025-04-24','2025-05-01'],
 'labels_known_by':'Each block stop; exclude later completions from complete-case metrics and all later training/support.',
 'point_model_refit_after_selection':False,'lookback_days':120,
 'new_holdout_reason':'V40J March08-21 entered its baseline reproduction input; use previously footer-only April.',
 'raw_decoder_policy':'Only decode whole Parquet row groups whose submit min/max are within the authorized block and whose submit/start/end maxima are all before May cutoff. Exclude boundary-crossing and post-cutoff-containing groups before value-array decoding. Then apply row timestamp and end-known filters.',
 'cohort_limitation':'Whole-group firewall is deliberately conservative and may omit otherwise eligible jobs and dates. Report omitted groups/counts and no full-period generalization. Missing final-shadow dates forces HOLD; never relax this policy after outcomes.',
 'shadow_requirement':'Both nonnull point and safe freezes required; all seven UTC submit dates and N>=100 overall/critical group required for readiness; no retune/refit/reselection.'}
LGB={'n_estimators':400,'num_leaves':31,'learning_rate':.05,'min_child_samples':100,
 'max_bin':255,'random_state':SEED,'n_jobs':1,'deterministic':True,'force_col_wise':True,'verbosity':-1}
IDS=['K0','K1_L1_RESIDUAL','K1_HUBER_RESIDUAL','K1_Q50_RESIDUAL','K2_NORMALIZED_Q50','K3_SOFT_CDF_MEDIAN','K4_INTERVAL_HAZARD','K5_STACKING']
STACK=IDS[:6]
HAZARD_EDGES=[60.,300.,900.,3600.,14400.,43200.,86400.,172800.,604800.]
REGISTRY=[
 {'id':'K0','family':'Existing pinned MoE-XGBoost absolute-error recipe, end-known 120-day training; unchanged q baseline diagnostic'},
 {'id':'K1_L1_RESIDUAL','objective':'L1 on (actual - rolling OOF C0)/3600; output max(0,C0+3600*correction)'},
 {'id':'K1_HUBER_RESIDUAL','objective':'Huber alpha=.9 on (actual - rolling OOF C0)/3600; exploratory central candidate evaluated by Q50 gates'},
 {'id':'K1_Q50_RESIDUAL','objective':'quantile .5 on (actual - rolling OOF C0)/3600'},
 {'id':'K2_NORMALIZED_Q50','objective':'quantile .5 on log((runtime+1)/(requested+1)); inverse max(0,exp(z)*(requested+1)-1); no smearing, no walltime cap'},
 {'id':'K3_SOFT_CDF_MEDIAN','early_label':'FAILED OR duration<=300 seconds; historical label only',
  'gate':'binary LightGBM on causal X; no hard branch',
  'components':'log1p runtime regressions on two historical groups; empirical log residual CDFs on internal last-7-day chronological block',
  'fit':'gate and component training end-known before internal CDF block; residual labels end-known before model fit date; minimum 30 per component or candidate unavailable',
  'quantile':'inf t>=0 such that p*F_short(t)+(1-p)*F_service(t)>=.5; 64 log-domain bisections; no component-mean mixing'},
 {'id':'K4_INTERVAL_HAZARD','family':'one LightGBM binary model on expanded at-risk interval records',
  'interval_uppers_seconds':HAZARD_EDGES,'binary_trees':160,'tail':'exponential beyond last edge with mean observed training excess, or last-edge scale if no tail observations; quantile is not clipped to a walltime cap',
  'quantile':'survival product of (1-h); uniform interpolation within finite interval, exponential beyond final edge'},
 {'id':'K5_STACKING','base_ids':STACK,'weights':'nonnegative sum1, sparse linear-program pinball objective on I1/I2 OOF predictions only; no hand weights',
  'no_available_component':'exclude unavailable components by predeclared availability, not performance'}]
POINT_GATE={'estimand':'CONDITIONAL_MEDIAN_RUNTIME_Q50','primary':['Q50 pinball','MAE','abs(P(actual>Q50)-0.5)'],
 'mean_signed_error':'diagnostic only, never a gate',
 'requirements':['strictly improve pooled pinball','strictly improve pooled MAE','strictly improve pooled median calibration error','strictly improve COMPLETED H100-standby median calibration error','no catastrophic subgroup MAE regression','independent deterministic refit'],
 'critical_subgroups':['H100','standby','H100-standby','COMPLETED H100-standby'],
 'catastrophic_rule':'No >=100-row critical subgroup, terminal-status group or walltime bucket has MAE > 1.25 times K0 MAE; required retrospective subgroup N>=100 otherwise insufficient',
 'pinball_MAE_identity':'Q50 pinball=0.5*MAE; report both, do not pretend they are independent evidence',
 'winner':'minimum pooled pinball among eligible; within 0.1% of minimum use simpler registry order',
 'no_winner':'V40K_POINT_MODEL_INSUFFICIENT; no point freeze, safe fit or shadow',
 'support_threshold':100,'wall_buckets':[3600,21600,86400,259200],
 'OOF_C0_source':'existing V40J F1/F2/F3 end-known models and out-of-fit predictions; latest causal fit per query, label known before each correction fit; never in-sample C0 predictions'}
SAFE={'ids':['S0','S1','S2','S3'],'minimum_support':100,'target_coverage':.9,
 'groups':{'S0':[[]],'S1':[['hardware','wall_bucket'],['hardware'],[]],
 'S2':[['hardware','standby','wall_bucket'],['hardware','wall_bucket'],['hardware'],[]],
 'S3':[['hardware','standby','wall_bucket'],['hardware','wall_bucket'],['hardware'],[]]},
 'q':'nonnegative one-sided residual order ceil((n+1)*.9), capped n; native point+q, no ceil at coverage gate',
 'fallback':'S0/S1/S2 first support-sufficient group then pooled; S3 reuse causal exact9/other8 support classes, skip leaf when sparse/mismatched, conservative parent max; OOD at least requested walltime, invalid request abstains',
 'gate':'overall >=.90 and support-sufficient H100 and H100-standby >=.90; at least 100 pooled rows, deterministic fallback, chronology PASS',
 'winner':'minimum native-bound overreserved GPU-hours among eligible, then registry order',
 'shadow':'same point gates versus K0 and safe coverage gates; all seven dates, no retuning',
 'optimization_integration':'NONE; workload duration metrics only'}
