from .common import *
from scipy.special import logit
import importlib.metadata

def main():
    assert not (OUT/'fits').exists()
    assert read('V40R4_V40R3_TARGET_REPRODUCTION.json')['max_abs_interval_difference_GPUh']==0
    count=read('V40R4_COUNT_DISTRIBUTION_DIAGNOSTIC.json');tail=read('V40R4_TAIL_THRESHOLD_SELECTION.json')
    severity=read('V40R4_SEVERITY_TAIL_DIAGNOSTIC.json');depend=read('V40R4_COUNT_SEVERITY_DEPENDENCE_AUDIT.json')
    assert count['selected_classical_family']=='NB' and severity['selected_simple_body']=='LOGNORMAL'
    assert tail['status']=='EVT_TAIL_NOT_SUPPORTED' and depend['meaningful_dependence']
    a,i,j,m=data();prepared=np.load(OUT/'prepared.npz');z=prepared['severity'];ix=prepared['job_interval'];tr=np.repeat(m['TRAIN'],48)
    z=z[tr[ix]];u=float(prepared['tail_u']);body=np.log(z[z<=u]);tails=np.log(z[z>u])
    def lg(x):return float(logit(np.clip(x,.001,.999)))
    bias=[np.log(prepared['count'][m['TRAIN']].mean()),np.log(count['families']['NB']['dispersion_r']),
       lg((np.log(u)-body.mean())/12),lg((body.std()-.1)/3.9),lg((z>u).mean()),
       lg((tails.mean()-np.log(u))/10),lg((tails.std()-.1)/3.9)]
    mc=[]
    for role in ['TRAIN','CALIBRATION']:
        days=np.flatnonzero(m[role]);selected=days[np.linspace(0,len(days)-1,12).astype(int)]
        mc.extend((selected*48+np.arange(12)*4).tolist())
    architecture={'working_name':'Causal Compound Arrival Forecaster','novelty_claim':False,'count_family':'NB, no forced structural-zero component',
       'context':'Same R3 causal past 336x8 and future48x15 tensors; shared 32-channel convolutional history encoder and 64/32 MLP',
       'count_head':'log mu clipped [-9,9], log r clipped [-7,7]','severity':'Two truncated lognormals spliced at TRAIN job Q95, with learned tail-exceedance probability',
       'body_loc':'log(u)-12*sigmoid(raw)','tail_loc':'log(u)+10*sigmoid(raw)','scales':'.1+3.9*sigmoid(raw)',
       'probability':'sigmoid(raw) clipped [1e-6,1-1e-6]','CDF_continuity':'Body approaches 1-p_tail at u, tail starts at 1-p_tail; density may jump and is reported',
       'EVT_used':False,'u_GPUh':u,'fallback_preregistered_before_fit':True,
       'coupling':'Severity head receives log1p(predicted mu) from the shared model; no realized future N as feature',
       'loss':'Mean NB count NLL + sum individual spliced-lognormal severity NLL per interval / TRAIN mean count. Exact N,sum(logZ),sum(logZ^2) sufficient statistics; no averaging away job likelihood.',
       'dependency_limit':'Marginal scenario intervals conditionally independent; residual temporal dependence remains an explicit approximation'}
    dump('V40R4_CCAF_ARCHITECTURE.json',architecture)
    r={'version':'V40R4','BASE':BASE,'scientific_reference':SCI,'time_UTC':datetime.now(timezone.utc),'candidate_fits_before_commit':0,
      'target':'Exact frozen R3 arriving GPUh at submission intervals, scoped authorized-GPU cohort; no direct-active-GPU target',
      'origin':'D-1 18:00 fixed AEST = D-1 08:00 UTC','interval_minutes':30,'horizons':48,
      'burst_GPUh':read('V40R4_PHASE0_PLAN.json')['burst_threshold_GPUh'],
      'severity_split_u_GPUh':u,'severity_top1_TRAIN_threshold':float(np.quantile(z,.99)),'count_large_threshold':read('V40R4_BURST_CLASSIFICATION_RULE.json')['count_Q95'],
      'families':{'B0':'ZERO','B1':'Causal seasonal same-slot mature 7/14/21/28-day empirical distribution',
        'B2':'R3-style aggregate hurdle LightGBM refit; binary +9 conditional-positive quantile heads, monotone CDF interpolation',
        'B3':'LightGBM Tweedie aggregate mean, TRAIN Pearson dispersion, exact compound Poisson-Gamma scenario law',
        'B4':'Parametric NB context regression + lognormal severity WLS on exact job-log sufficient statistics; no EVT',
        'B5':'LightGBM Poisson mean + TRAIN conditional NB dispersion + ML lognormal severity location; no EVT',
        'B6':'NOT_EXECUTED_EVT_TAIL_NOT_SUPPORTED','P1':'CCAF context NB + explicit exceedance head + spliced lognormal body/tail; no GPD'},
      'trials':{'B0':0,'B1':0,'B2':2,'B3':2,'B4':2,'B5':2,'B6':0,'P1':2},
      'tree_training':{'learning_rates':[.03,.08],'rounds':400,'depth':6,'leaves':31,'min_child_samples':30,'max_bin':127,'L2':1.,'threads':4,'deterministic':True,
        'B3_override':'Two power trials [1.3,1.7], fixed LR .05; same 400 rounds','B4_override':'Two ridge strengths [.1,1.0], three alternating NB mean/dispersion cycles, L-BFGS maxiter300; positive body WLS'},
      'CCAF_initialization':{'u':u,'bias':bias,'source':'TRAIN only'},
      'CCAF_training':{'learning_rates':[.001,.0003],'max_epochs':40,'batch_days':16,'Adam_weight_decay':1e-4,'gradient_clip':1.,
        'early_stopping':'Development joint NLL, patience8, min_delta1e-5; aggregate primary chooses trial/calibration pipeline later',
        'seed':SEED,'independent_repeat':'Selected config retrained once from same fixed seed; report values and metric differences, never select better repeat',
        'AMP':False,'deterministic_algorithms':True,'warn_only':True,'cudnn_deterministic':True,'cudnn_benchmark':False,'TF32':False,'CUBLAS':':4096:8'},
      'temporal_protocol':{'TRAIN':['2024-03-15','2024-08-30'],'DEVELOPMENT':['2024-09-01','2024-10-30'],
        'CALIBRATION':['2024-11-01','2024-11-29'],'EXPOSED_STRESS':['2024-12-01','2025-02-26'],
        'maturity':'Exact inherited R3 masks; TRAIN167/DEV58/CAL26/STRESS88 days',
        'provisional_C1_fit':'September DEV only, label_available_at <=2024-09-30 08:00UTC',
        'pipeline_selection':'October DEV only; choose safety-passing pipeline first, otherwise minimum primary hierarchy for a diagnostic comparator',
        'final_C1_fit':'November CAL only, frozen rule, before Dec/Jan/Feb comparison',
        'blocks':'September/October development roles; December/January/February stress months. Daily rolling causal origins with frozen model weights; no random split or expanding refits.',
        'untouched_confirmation':False},
      'scenario_count':10000,'scenario_seed':SEED,'per_day_seed':'SEED + 7919*operating_day_index, shared across candidates, stable across execution stages',
      'MC_check_flat_intervals':mc,'MC_diagnostic_counts':[1000,2500,5000,10000],
      'MC_acceptance':{'independent_10000_mean_relative_limits_Q50_Q90_Q95':[.10,.10,.15],
         'independent_P95_relative_limits':[.30,.30,.40],'denominator':'1 GPUh + reference quantile','failure':'Ineligible; no post-fit M tuning'},
      'scenario_numerics':{'device':'cuda:0 if available else CPU','dtype':'float64','uniform_open_interval_clip':[1e-12,1-1e-12],
         'count_truncation':False,'severity_chunk_jobs':2000000,'single_scenario_resource_limit_jobs':50000000,
         'resource_limit_action':'Raise failure, never silently truncate counts','Tweedie':'Gamma reproductive property gives exact distribution of sum of N iid Gamma severities'},
      'calibration':{'methods':['C0','C1'],'C0':'No calibration','C1':'Positive-CAL finite-sample .9 quantile of log1p(y)-log1p(rawQ90); allow negative score',
        'application':'Push forward full aggregate CDF by T_s(z)=max(0,expm1(log1p(z)+s)); Q50 also transforms for scenario/quantile coherence',
        'ZERO':'C0 only, stays zero','global_additive_GPUh':False,'secondary_PIT':'Not executed, no additional calibration family',
        'overconservative':'Flag primary worsening >10% unless raw lower coverage failed, all final pooled coverage bands pass, and primary remains <.9',
        'formal_guarantee':'No exchangeability or conditional coverage guarantee under temporal shift; evaluate coverage and sharpness empirically'},
      'primary':'Sum Q90 pinball over positive intervals / sum positive actual GPUh',
      'gates':{'pooled_N_min':100,'overall_coverage':[.9,.95],'positive_coverage':[.9,.95],'burst_coverage':[.9,.975],
        'monthly_burst_N_min':100,'monthly_burst_coverage_min':.9,'small_block':'INSUFFICIENT_SUPPORT, never imputed PASS numeric result',
        'monthly_catastrophic_WAPE_above':2.,'primary_must_be_below_ZERO':.9,'overconservative_calibration_disqualifies':True,
        'MC_convergence_required':True,'authority_required':True,'horizon_crossing':0},
      'selection_hierarchy':['authority/leakage','temporal safety/calibration and MC validity','positive Q90 normalized pinball','missed burst GPUh','cumulative WAPE','simpler registry order'],
      'simplicity_order':['B0','B1','B4','B3','B5','B2','P1'],
      'superiority':{'comparator':'Strongest non-P1 selected using October DEVELOPMENT only; commit before exposed comparison',
        'execute_only_if_P1_safe':True,'bootstrap':'Paired circular 7-day blocks','samples':5000,'seed':SEED,'CI_lower_must_exceed':0,
        'P1_numeric_requirement':'Better than every executed safety-eligible non-P1 selected pipeline','no_eligible_baseline':'Freeze best diagnostic primary comparator; disclose ineligibility'},
      'holds':read('V40R4_START_STATE.json')['holds'],'EVT_decision':tail,'phase0_rule_commit':'abfb9a43be0f442a943535a146344fe954703aad',
      'frameworks':{n:importlib.metadata.version(n) for n in ['numpy','pandas','scipy','lightgbm','torch']}}
    frozen=[*list((ROOT/'dayahead/v40r4').glob('*.py'))]
    frozen=[p for p in frozen if p.name not in ['preregister.py','test_contracts.py','finalize.py']]
    frozen +=[OUT/n for n in ['prepared.npz','compound_labels.npz','V40R4_PHASE0_PLAN.json','V40R4_TAIL_THRESHOLD_SELECTION.json','V40R4_CAUSAL_FEATURE_CONTRACT.json','V40R4_CCAF_ARCHITECTURE.json','V40R4_BURST_CLASSIFICATION_RULE.json']]
    frozen +=list((OUT/'inputs').glob('*'))
    frozen +=[OUT/n for n in ['V40R4_INPUT_IDENTITY.json','V40R4_COUNT_DISTRIBUTION_DIAGNOSTIC.json','V40R4_SEVERITY_TAIL_DIAGNOSTIC.json','V40R4_COUNT_SEVERITY_DEPENDENCE_AUDIT.json','V40R4_LABEL_MATURITY_VERIFICATION.json','V40R4_UNTOUCHED_HOLDOUT_AUDIT.json','V40R4_SCI_BENCHMARK_REVIEW.md']]
    r['frozen_hashes']={p.relative_to(ROOT).as_posix():sha(p) for p in frozen}
    dump('V40R4_PREREGISTRATION.json',r)
    print('Preregistration written; candidate fits still zero. Commit before training.')
if __name__=='__main__':main()
