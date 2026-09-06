from .common import *
import shutil

def main():
    assert git('rev-parse','HEAD')==BASE
    assert git('merge-base','--is-ancestor',SCI,BASE)==''
    receipt=json.loads(subprocess.check_output(['git','show',BASE+':dayahead/artifacts/v40r3_causal_gpuwork_arrival_ml/V40R3_FINAL_COMMIT_RECEIPT.json'],cwd=ROOT))
    assert receipt['final_research_commit']==SCI
    assert git('branch','--show-current')=='codex/v40r4-compound-gpuwork-arrival'
    assert old('V40R3_METHOD_SELECTION.json')['classification']=='V40R3_FUTURE_GPUWORK_SAFETY_FAIL'
    freeze=[]
    for root in [R3/'dayahead/v40r3',OLD]:
        for p in sorted(root.rglob('*')):
            if p.is_file():freeze.append({'path':p.relative_to(R3).as_posix(),'SHA256_working':sha(p),'bytes':p.stat().st_size})
    protected={}
    for path in [R3,R3.parent/'MobileESS_v40r2_cabo_future_workload_ml',R3.parent/'MobileESS_v40r_causal_dayahead_workload',R3.parent/'MobileESS_v40s2_survival_occupancy_ml',R3.parent/'MobileESS_v40s_direct_runtime_q90']:
        protected[str(path)]={'HEAD':git('rev-parse','HEAD',cwd=path),'status':git('status','--porcelain',cwd=path)}
    dump('V40R4_START_STATE.json',{'BASE':BASE,'scientific_parent':SCI,'receipt_contains_expected_file':True,'receipt_descends_from_scientific':True,
      'branch':git('branch','--show-current'),'worktree':ROOT,'time_UTC':datetime.now(timezone.utc),
      'protected_worktrees':protected,'V40R2_status':'SUPERSEDED_BY_V40R3','V40R3_status':'V40R3_FUTURE_GPUWORK_SAFETY_FAIL',
      'May_scientific_reads':0,'May_path_code_metadata':'NONZERO: supplied requests and git worktree names only; no May payload decoded',
      'holds':{'production_q':'UNCHANGED','PF':.95,'Q_control':False,'electrical':'HOLD','B0_B3_electrical':False,'FULL_MAY':False,'optimizer':False}})
    dump('V40R4_V40R3_FREEZE_VERIFICATION.json',{'BASE':BASE,'scientific':SCI,'files':freeze,'status':'INITIAL_BYTE_INVENTORY_CAPTURED','R3_write_operations':0})
    inputs=['GPU_related_candidates_preMay.parquet','causal_dataset.npz','V40R3_LABEL_MATURITY_LEDGER.parquet',
      'feature_available_at_proofs.parquet','arrival_bins_with_maturity.parquet']
    (OUT/'inputs').mkdir(parents=True,exist_ok=True)
    for n in inputs:shutil.copyfile(OLD/n,OUT/'inputs'/n)
    dump('V40R4_INPUT_IDENTITY.json',{'files':{n:sha(OUT/'inputs'/n) for n in inputs},'source':'Frozen already-exposed V40R3 artifacts; no new raw archive/May read'})
    dump('V40R4_PHASE0_PLAN.json',{
      'candidate_forecast_fits_so_far':0,'scope':'TRAIN-only design diagnostics; V40R3 exposed bursts solely for descriptive failure decomposition',
      'TRAIN':'V40R3 mature TRAIN origins only; same excluded days and cutoff',
      'target_reproduction_tolerance_absolute_GPUh':1e-7,
      'burst_threshold_GPUh':old('V40R3_PREREGISTRATION.json')['burst']['training_positive_Q95_GPUh'],
      'burst_rule':{'count_high':'N strictly above TRAIN all-interval N Q95','severity_high':'max Z strictly above TRAIN positive-interval max Z Q95',
          'COUNT_DRIVEN':'count_high and not severity_high','SEVERITY_DRIVEN':'severity_high and not count_high','MIXED':'both','UNRESOLVED':'neither',
          'tail_exceedance_definition':'Z above TRAIN job-severity Q95, descriptive only; distinct from any selected GPD threshold','use':'Descriptive, never deployment logic'},
      'count_family_rule':'Intercept-only Poisson/NB/ZIP/ZINB maximum likelihood, minimum BIC among converged fits with valid parameters; no forecast candidate fits in phase0',
      'severity_body_rule':'Full TRAIN positive-job Lognormal versus Gamma MLE by BIC; no dev/test values',
      'EVT_rule':{'candidate_quantiles':[.9,.95,.975],'min_exceedances':500,'min_unique_excesses':50,
          'shape_domain_for_admission':[0,.9],'require_shape_CI95_upper_below':1.,'max_neighbor_shape_difference':.2,
          'KS_max':.05,'QQ_log_correlation_min':.98,'uncertainty':'100 operating-day block bootstrap MLE fits at each threshold; threshold itself held fixed',
          'selection':'Lowest threshold satisfying support, valid finite mean, CI, fit and neighboring-shape stability. If none, EVT_TAIL_NOT_SUPPORTED.',
          'GOF_caveat':'Raw KS p-value is not calibrated after fitted parameters; admission uses frozen KS distance and QQ criteria, not a false simple-null p-value'},
      'dependence_rule':'Meaningful if absolute Spearman(N,mean Z) over positive TRAIN intervals >=0.2; permit severity head to depend on predicted mu, never realized future N',
      'seed':SEED})
    print(json.dumps({'BASE':BASE,'frozen_R3_files':len(freeze),'copied_inputs':len(inputs),'candidate_fits':0}))

if __name__=='__main__':main()
