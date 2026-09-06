from .common import SEED,FEATURES

SPLIT={'timezone':'UTC','canonical_cutoff':'2025-05-01T00:00:00+00:00','fixed_AEST_equivalent':'2025-05-01T10:00:00+10:00',
 'interval_convention':'[inclusive start, exclusive end)', 'training_end_known_before':'2025-04-01T00:00:00Z',
 'visible_development':['2025-04-01T00:00:00Z','2025-04-08T00:00:00Z'],
 'calibration':['2025-04-08T00:00:00Z','2025-04-15T00:00:00Z'],
 'selection':['2025-04-15T00:00:00Z','2025-04-24T00:00:00Z'],
 'shadow':['2025-04-24T00:00:00Z','2025-05-01T00:00:00Z'],
 'end_known':'training/support historical end_time strictly before prediction/fitting freeze; block labels end_time strictly before block stop',
 'decoder':'Only whole row groups with submit bounds within authorized block and submit/start/end footer maxima strictly before May cutoff. Never decode a mixed post-cutoff group to filter its outcomes afterwards.',
 'cohort_limitation':'Whole-group exclusions and end-known complete-case selection may omit dates and long jobs. No full-calendar or unconditional population generalization.',
 'shadow_authority':'Require all seven submit UTC dates, overall/H100/strong-support H100-standby N>=100, no abstentions, all coverage gates; unavailable complete shadow is FAIL_HOLD.',
 'censor_authority':'Static retrospective end_time is not a cutoff-time alive snapshot. No May completion decode and no manufactured censor labels; T5/census unavailable without independent causal snapshot.'}
PARAMS={'device':'cpu','tree_method':'hist','nthread':1,'seed':SEED,'max_depth':5,'eta':.05,'min_child_weight':20,'subsample':1.,'colsample_bytree':1.,'max_bin':256,'lambda':1.,'verbosity':0}
BUCKETS=[3600.,21600.,86400.,259200.]
THRESHOLDS=[100,200,500]
EXCESS_ALPHAS=[i/20 for i in range(1,20)]
HIERARCHY=[['hardware','standby','wall_bucket'],['hardware','wall_bucket'],['hardware'],[]]
IDS=['T0','T1','T2','T3_R','T3_D','T4_N100','T4_N200','T4_N500','T5','T6','T7','T8_N100','T8_N200','T8_N500']
REGISTRY={
 'T0':{'method':'K0+5576.44921875 seconds','Q95':'same legacy bound diagnostic only; not claimed calibrated Q95'},
 'T1':{'objective':'reg:quantileerror','target':'ALL signed rolling OOF residual /3600','alphas':[.9,.95],'rounds':400,'features':FEATURES,'output':'K0 + max(0,3600*predicted residual quantile); monotonic repair'},
 'T2':{'objective':'reg:quantileerror','target':'runtime/3600 on pre-April end-known historical GPU jobs','alphas':[.5,.9,.95],'rounds':400,'Q50':'diagnostic only; K0 never replaced','output':'max(K0,direct Q90), then max(T90,direct Q95)'},
 'T3_R':{'base':'T1','calibration':'April08-14 signed one-sided score actual - repaired raw bound, independently at alpha .90/.95; add finite-sample order quantile; repair after correction'},
 'T3_D':{'base':'T2','calibration':'same as T3_R; base variants predeclared and not chosen using April01-07'},
 'T4':{'hierarchy':HIERARCHY,'minimum_support_variants':THRESHOLDS,'scores':'April08-14 actual-K0, full signed residual','quantile':'ceil((n+1)*alpha) order statistic; insufficient order gives +infinity, not clipped sample maximum','fallback':'first support-sufficient level, finally pooled; pooled N<100 means unavailable'},
 'T5':{'objective':'survival:aft','availability':'NOT_EVALUATED_CAUSAL_CENSOR_AUTHORITY_UNAVAILABLE','distribution':'normal','scale':1.,'quantile_formula':'T_alpha=exp(mu(X)+scale*Phi_inverse(alpha)), mu=raw output_margin; then safe monotonic repair','no_May_completion_read':True},
 'T6':{'method':'Reuse SHA-frozen V40K FINAL_K4_INTERVAL_HAZARD.pkl survival curve, CPU prediction only','quantiles':[.9,.95],'training_end_known_before':'2025-04-01T00:00:00Z','no_median_competition':True,'censored_rows_added':0},
 'T7':{'stage1':'binary:logistic on all OOF rows, event residual>0, 300 rounds','stage2':'reg:quantileerror on strictly positive OOF excess/3600, 250 rounds','conditional_alphas':EXCESS_ALPHAS,'reconstruction':'For e>=0, F(e|X)=1-p_plus+p_plus*F_plus(e|X). If alpha<=1-p_plus margin=0; else u=(alpha-1+p_plus)/p_plus and invert conditional CDF. u<=alpha<=.95. Conditional quantile knots monotonic repaired with Q_plus(0)=0; piecewise-linear inverse. Negative residual mass conservatively placed at zero.'},
 'T8':{'variants':THRESHOLDS,'STRONG_SUPPORT':'T1','SPARSE_SUPPORT':'hierarchy first supported parent, omit L1','REGIME_MISMATCH':'maximum supported parent margin L2-L4','OUT_OF_SUPPORT':'ABSTAIN; no invented requested-walltime ceiling authority','abstain_gate':'Any abstention blocks full-cohort winner eligibility; never silently drop from coverage denominator'}}
GATES={'minimum_evaluation_N':100,'support_sufficient_definition':'exact causal feature9 historical count>=100, with end-known support before query; not calibration-group support chosen per candidate',
 'coverage_threshold':.90,'required':['overall','H100','STRONG_SUPPORT H100-standby','GPU_weighted_overall'],
 'missing_required_subgroup':'INSUFFICIENT_SUPPORT and ineligible, never silently drop gate',
 'coverage':'native unrounded Q90, independent of Q95; ties y<=bound covered; GPU weights requested GPU counts',
 'eligibility':'all required coverage gates, no abstentions, finite safe>=K0 and Q95>=Q90, deterministic, provenance PASS',
 'efficiency_order':['overreserved_GPU_hours','mean_safe_inflation_seconds','active_miss_GPU_5min_slots','registry_order'],
 'ordering_reconciliation':'Section10 explicitly includes inflation; use its complete efficiency ordering, followed by Section15 simpler-model tie break. No performance-dependent ordering change.',
 'bootstrap':{'unit':'UTC submission date','resamples':2000,'seed':SEED,'interval':[.025,.975],'interpretation':'descriptive day-dependence sensitivity; no iid or out-of-period coverage guarantee'},
 'no_winner':'V40L_TAIL_MODEL_INSUFFICIENT; shadow remains sealed',
 'shadow_failure':'V40L_FINAL_SHADOW_FAIL_HOLD; no reselection/refit/q/threshold changes',
 'success_mapping':{'T4':'V40L_ML_TAIL_INSUFFICIENT_HIERARCHICAL_CONFORMAL_READY if no ML-containing method eligible, otherwise V40L_CONFORMAL_TAIL_READY','T0':'V40L_CONFORMAL_TAIL_READY','other':'V40L_K0_PLUS_CONDITIONAL_TAIL_READY'},
 'nominal':'Frozen K0 only; acknowledged conditional point bias remains; no point-winner reinterpretation'}
