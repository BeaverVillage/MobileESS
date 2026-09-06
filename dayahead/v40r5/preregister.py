from .common import *
import importlib.metadata as md,platform
def main():
    assert not (OUT/'fits').exists(),'No preregistration after any forecast fitting'
    a,i,m=data();threshold=read('V40R5_BURST_THRESHOLD_FREEZE.json');y=a['y'][m['TRAIN']];body=y[y<=threshold['u_B_GPUh']];zero=float((body==0).mean())
    paths=list((ROOT/'dayahead/v40r5').glob('*.py'))+[OUT/'data.npz',OUT/'feature_availability.npz',OUT/'seasonal_maturity_proof.parquet',OUT/'V40R5_15MIN_TARGET_RECONSTRUCTION.parquet']+list((OUT/'inputs').glob('*'))
    paths+=[OUT/n for n in ['V40R5_BURST_THRESHOLD_FREEZE.json','V40R5_PHASE0_PLAN.json','V40R5_15MIN_COUNT_DIAGNOSTIC.json','V40R5_15MIN_SEVERITY_DIAGNOSTIC.json','V40R5_FEATURE_AUTHORITY_AUDIT.json','V40R5_TEMPORAL_SPLIT_CONTRACT.json']]
    # Reporting/test code may be completed after results; science code is immutable.
    paths=[p for p in paths if p.name not in ['finalize.py','preregister.py']]
    reg={'identity':'V40R5_15MIN_SELECTIVE_BURST_GPUWORK','BASE':BASE,'target':'Exogenous arriving GPUh, original submit-event 15min x96','cohort':read('V40R5_15MIN_TARGET_CONTRACT.json'),
      'feature_authority':read('V40R5_15MIN_FEATURE_MATRIX_CONTRACT.json'),'split':read('V40R5_TEMPORAL_SPLIT_CONTRACT.json'),'burst_threshold_GPUh':threshold['u_B_GPUh'],'burst_operator':'>','N_high':threshold['N_high'],
      'baseline_registry':{'B0':'ZERO no fit','B1':'Empirical causal 7/14/21/28-day same 15min mature lags','B2':'Hurdle LightGBM binary occurrence +9 conditional quantiles','B3':'LightGBM Tweedie powers1.3/1.7, TRAIN Pearson dispersion'},
      'body_registry':{'PB1':'Hurdle LightGBM trained only on TRAIN y<=u_B, positive heads only0<y<=u_B; output support clipped[0,u_B]','PB2':'NOT_EXECUTED optional comparator, compact registry'},
      'classifier_registry':{'C0':'Constant TRAIN burst base rate','C1':'Standardized logistic regression C .1/1.','C2':'LightGBM binary natural-frequency loss','C3':'XGBoost binary hist CPU natural-frequency loss'},
      'tuning_budget':{'B0':1,'B1':1,'B2':2,'B3':2,'PB1':2,'N0':1,'N1':1,'C0':1,'C1':2,'C2':2,'C3':2,'extra_models_after_results':False},
      'tree_parameters':{'rounds':300,'learning_rates':[.03,.08],'max_depth':4,'LightGBM_num_leaves':15,'LightGBM_min_child_samples':30,'max_bin':127,'L2':1.,'seed':SEED,'threads':4,'early_stopping':'None, fixed rounds','LightGBM_deterministic':True,'force_col_wise':True},
      'XGBoost_parameters':{'tree_method':'hist','device':'cpu','min_child_weight':5,'subsample':1.,'colsample_bytree':1.,'eval_metric':'logloss','rounds':300,'seed':SEED},
      'linear_parameters':{'C':[.1,1.],'max_iter':1000,'solver':'lbfgs','class_weight':None,'scaler_TRAIN_only':True},
      'count_auxiliary':{'N0':'Mature seasonal empirical mean/P90/exceedance rate','N1':'LightGBM Poisson mean LR.05 +conditional NB r fitted by TRAIN likelihood, log r bounds[-7,7]',
        'classifier_predictors':'N1 log1p predicted mean and predicted P(N>N_high), never realized N','TRAIN_stack':'5 chronological expanding folds; train only labels mature before first destination origin; N0 warm-up if fewer than10 mature days',
        'support_models_not_search':'Up to4 N1 crossfit fits +1 final model; same fold construction in independent repeat'},
      'development_selection':{'baseline_and_body_trials':'Safety first then primary; body uses oracle BODY diagnostics; no eta from DEV','classifier_trials':'Highest DEV PR-AUC, then Brier, then simpler trial','baseline_comparator':'Strongest DEVELOPMENT raw 15min B0-B3 pipeline fixed before CAL hybrid selection; no R4 weights reused'},
      'body_calibration':{'BC0':'none','BC1':'Positive oracle BODY CAL log1p(y)-log1p(raw Q90), finite-sample90% order statistic, transform both Q50/Q90 and clip[0,u_B]',
        'global_additive_GPUh':False,'calibration_window':'November CAL only; no provisional DEV body calibration','methods_selected_on':'CAL only'},
      'eta_rule':{'source':'CAL only','candidate_thresholds':'All unique CAL probabilities, largest satisfying both burst recall>=.9 and GPUh-weighted recall>=.9; inclusive p>=eta','tie':'Same threshold is unique; across pipelines hierarchy below','sensitivity':'.95 recall and GPUh-weighted recall, report only never switch'},
      'robust_envelopes':{'R0':'CAL burst empirical Q90','R1':'CAL burst empirical Q95','R2':'CAL burst conditional Q90; time-of-day 4fixed6h blocks x predicted risk>=TRAIN-crossfit risk Q75; fallback count risk ->time ->global',
        'minimum_group_burst_N':30,'minimum_global_CAL_burst_N':30,'new_Q99_after_results':False,'selected_safe':'body_Q90 if p<eta else robust upper; robust output is NOT body Q90'},
      'body_gates':{'pooled_overall':[.9,.95],'pooled_positive':[.9,.95],'pooled_min_N':100,'monthly_lower':.88,'monthly_min_N':100,'overconservative_warning_above':.975},
      'detector_gates':{'recall_min':.9,'GPUh_weighted_recall_min':.9,'captured_fraction_min':.8,'ECE_max':.05,'ECE':'10 equal-width probability bins, include1inlast','minimum_burst_N':30},
      'hybrid_gates':{'overall':[.9,.95],'positive':[.9,.95],'burst':[.9,.975],'pooled_nonburst_min_N':100,'pooled_burst_min_N':30,'monthly_burst_min_N':100,'monthly_burst_lower':.9,'positive_primary_max_exclusive':.9,'monthly_catastrophic':'Selected-safe envelope WAPE>2.0; evaluate all months, not just Q50 WAPE'},
      'primary':'Sum positive-interval 0.9-pinball / sum positive actual GPUh; hybrid envelope scored with Q90-style loss, not claimed universally calibrated Q90',
      'selection_hierarchy':['causal and target authority','body safety','detector safety','CAL positive coverage','CAL burst coverage','all hybrid coverage and temporal gates','lower positive primary','lower missed burst GPUh','lower overreservation','simpler classifier/envelope/calibration'],
      'no_CAL_safe_combination':'selected_model NONE; freeze best rejected diagnostic pipeline using same hierarchy; permit final exposed diagnostics only; no promotion or retuning',
      'stop_rules':['Target reproduction mismatch >1e-7: STOP all fitting','Feature causality failure: STOP fitting','BODY failure: stop selective promotion, retain registered diagnostics','Detector failure: stop selective promotion','Any mandatory safety failure: no bootstrap'],
      'Tweedie_simulation':{'M':10000,'seed':SEED,'per_day_seed':'seed+7919*day_index','device':'CPU numpy float64','exact_law':'Compound Poisson-Gamma; sum Gamma jump severities using reproductive closure; no count cap','cumulative':'Sum nonnegative increments within each scenario before quantiles'},
      'hybrid_cumulative_and_secondary':'Deterministic sums of selected-safe envelope increments at15/30/60min; reserve curves NOT true cumulative/coarser Q90; scenario cumulative quantiles reported only for Tweedie',
      'superiority':{'enabled_only_if':'CAL selection frozen and all body/detector/hybrid exposed safety and calibration gates pass','bootstrap':'5000paired circular7day blocks','CI':'95% percentile, lower>0','comparator':'DEVELOPMENT-frozen 15min baseline','numeric':'Must beat every executed safety-eligible baseline','no_safety':'NOT_EXECUTED_SAFETY_FAIL'},
      'reproducibility':'One independent same-seed count-crossfit +body+chosen classifier rebuild; same eta/cal/envelope rules, no repeat selection; if NONE repeat frozen rejected diagnostic pipeline and label it',
      'TRAIN_body_gate_feasibility':{'zero_fraction':zero,'minimum_overall_at_positive_90':zero+(1-zero)*.9,'simultaneous_bands_feasible':zero<=.5,'identity':'Nonnegative Q90 covers all zeros: overall=z+(1-z)*positive; no gate relaxation'},
      'frameworks':{name:md.version(name) for name in ['numpy','pandas','scipy','lightgbm','xgboost','scikit-learn','torch']},'Python':platform.python_version(),'compute':'CPU compact trees and logistic models, no new neural model; GPU hardware/CUDA recorded in ledger',
      'holds':{'production_q':'UNCHANGED','PF':.95,'Q_control':False,'electrical':'HOLD','electrical_B0_B3':False,'FULL_MAY':False,'optimizer':False,'V40S2':False,
        'A0':False,'A1':False,'M1':False,'MF':False,'migration':False,'WAN':False,'terminal':False,'event_trigger':False,'local_repair':False,'rolling_MPC':False,'second_route_search':False,'Gurobi':False,'OpenDSS':False},
      'May_scientific_reads':0,'May_metadata':'NONZERO: user protocol, git index/path metadata, source/provenance; no payload','TRUE_CONFIRMATORY_AVAILABLE':'NO',
      'frozen_hashes':{p.relative_to(ROOT).as_posix():sha(p) for p in paths}}
    dump('V40R5_PREREGISTRATION.json',reg);print('Preregistration ready; no candidate fit. TRAIN BODY band feasibility:',reg['TRAIN_body_gate_feasibility'])
if __name__=='__main__':main()
