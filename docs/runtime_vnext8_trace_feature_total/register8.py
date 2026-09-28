from common8 import *
import subprocess,platform,importlib.metadata
def main():
    prior=read(V6/'EXPERIMENT_PROTOCOL.json')
    p={k:prior[k] for k in ['logical_freeze_cutoff','TRAIN','DEV','CAL_FIT','CAL_VALID','APRIL']}
    p.update(version='runtime-vnext8-preapril-preregistered-v1',registered_at=now(),base=BASE,
      target='end_time-start_time seconds; execution interval excluding queue; invalid time orders excluded; zero allowed',
      STRICT_CAUSAL_FEATURE_COUNT=0,REQUEST_VERSION_AUTHORITY_FOUND=False,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,
      provenance_mode='Kestrel_trace_proxy',research_authorization='User Runtime-vNext8 request; PR78 unchanged',
      features='F0 resources+shape; F1 adds duration+qos/partition; F2 adds supported account/user/array/identity; F3 deterministic positive stable DEV group permutation pruning',
      identity_screen=dict(train_min_count=20,max_train_cardinality=5000,DEV_unseen_max=.25,CAL_FIT_unseen_max=.25,CAL_VALID_unseen_max=.25,min_rows_in_supported_train_categories=.8),
      identity_exclusions='G class job_type/python/reframe: generation time unknown; clock features excluded; no raw job IDs; no future fields',
      lgbm=dict(n_estimators=400,learning_rate=.04,num_leaves=31,max_depth=8,min_child_samples=150,max_bin=127,reg_lambda=2.,random_state=4008,deterministic=True,force_col_wise=True,n_jobs=4,verbosity=-1),
      family_grid=['M1 raw Q50/Q90 x F0/F1/F2','M2 log1p Q50/Q90 x F0/F1/F2','M3 log((T+1)/(walltime+1)) x F1/F2','M4 F1/F2 probability(T>4h)+short/long conditional quantile CDF mixture'],
      M4=dict(quantile_grid=[.05,.25,.5,.75,.9,.99],regime_boundary_seconds=14400,short_bounds=[0,14400],long_upper='maximum TRAIN runtime',distribution='Monotone conditional quantile knots, piecewise-linear CDF; mixture inverse via deterministic bisection; classifier probabilities not trained on DEV/CAL'),
      M5='Only pre-April two best distinct families if DEV error correlation<0.95 and each wins >=20% of DEV paired pinball rows. Equal quantile average heuristic, calibrated/evaluated explicitly.',
      F3='Best M1/M2/M3 F2 by DEV Q90 pinball; group permutation on DEV first/second chronological halves, one fixed seed; retain positive importance in both halves, otherwise drop group; evaluate one reduced family. No F3 if no group removed.',
      calibration='NONE or signed additive residual rank ceil(.9*(n+1)) fitted on CAL_FIT, after monotone raw Q50/Q90. Q50 unchanged. Choose using CAL_VALID gates and score; calibration is not tuned on April. No arbitrary multiplier.',
      selection='For each candidate/calibration compare DEV raw and CAL_VALID candidate: minimize number of failed predictive gate checks, then average Q90 pinball / B0, then average rounded reservation / W0, then feature count. Failed candidate remains diagnostic-only. At most two compact depth/leaf configurations: base only unless pre-April clear capacity diagnosis is documented before any extension.',
      gates=dict(coverage=[.88,.92],gpu_coverage=[.88,.94],long_gt4h_coverage_min=.85,pinball_to_B0_max=1.0,reservation_to_W0_max=.8,min_stratum_N=100,highGPU_coverage_min=.85,highGPU_insufficient='INSUFFICIENT_SUPPORT; no high-GPU guarantee, separate from aggregate research readiness',Q50_MAE_to_B0_max=1.0,CPU_p99_ms_max=50,CPU_max_ms_max=200,
        queue='same admitted count, W0 exact, V8 in-day starts>=W0, no capacity violation; never gate on prediction-only occupancy without causal overrun stress'),
      reservation='ceil(prediction_seconds/900)*GPU*0.25 hours; also report continuous duration metrics; never confuse with unrounded vNext6 metric',
      uncertainty=dict(unit='UTC submission day paired block bootstrap',draws=1000,seed=800928,interval=.95,min_days=3,metrics=['pinball_difference','MAE_difference','rounded_reservation_ratio_difference','long_underprediction_difference']),
      benchmark=dict(compare=['CPU_SINGLE','CPU_4_THREADS','RTX4060_OpenCL_GPU'],selected_workload='same TRAIN, selected feature set/family, every booster; prediction on DEV',equivalence_max_abs_seconds=.1,equivalence_relative_pinball=.001,equivalence_coverage=.001,GPU_min_speedup=1.2),
      checkpoint=dict(interval_seconds=1800,thresholds_seconds=[900,1800,3600,7200,14400],max_MAE_seconds=3600,min_accuracy=.8,max_overrun_fraction=.15,scope='every actual running checkpoint on mature April jobs, actual runtime isolated in evaluation only; no remaining fit'),
      preapril_only_until_freeze=True,May_payload_allowed=False,April_open_once_after_three_freezes=True,
      final_model='reuse selected serialized TRAIN boosters, never absorb DEV/CAL or refit after April',
      historical_limit='retrospective as-of event-time maturity; archive ingest timing and original submit versions unverified')
    write('EXPERIMENT_PROTOCOL.json',p)
    refs=[]
    for folder in [V6,V7]:
        manifest=read(folder/'DELIVERY_MANIFEST.json')
        assert all(sha(folder/x['relative'])==x['sha256'] for x in manifest['files'])
        refs.append(dict(namespace=folder.name,files=len(manifest['files']),manifest=record(folder/'DELIVERY_MANIFEST.json')))
    write('BASE_PRESERVATION_RECEIPT.json',dict(base=BASE,prior=refs,read_mode='byte hashes only; no April/May feature or outcome payload decoding',time=now()))
    write('ENVIRONMENT_RECEIPT.json',dict(python=platform.python_version(),platform=platform.platform(),packages={n:importlib.metadata.version(n) for n in ['lightgbm','numpy','pandas','pyarrow','scikit-learn']},gpu=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,driver_version','--format=csv,noheader'],capture_output=True,text=True).stdout,
      docs=['https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html','https://lightgbm.readthedocs.io/en/v4.6.0/GPU-Tutorial.html'],docs_scope='Installed LightGBM4.6.0; current stable docs4.7 consulted for semantics, actual availability measured.'))
    print('REGISTERED; prior namespaces byte-identical; no April opened',flush=True)
if __name__=='__main__':main()
