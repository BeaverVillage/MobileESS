from common12 import *
from regime12 import *
import shutil, platform, lightgbm

def main():
    LOCAL.mkdir(exist_ok=True)
    prior=[]
    for folder in sorted((REPO/'docs').glob('runtime_vnext*')):
        if folder==ROOT or not any(folder.name.startswith(f'runtime_vnext{i}_') for i in range(6,12)):continue
        manifest=read(folder/'DELIVERY_MANIFEST.json')
        for r in manifest['files']:assert sha(folder/r['relative'])==r['sha256'],str(folder/r['relative'])
        prior.append(dict(namespace=folder.name,N=len(manifest['files']),manifest=record(folder/'DELIVERY_MANIFEST.json')))
    write('BASE_PRESERVATION_RECEIPT.json',dict(time=now(),base=BASE,prior=prior,April_payload_decoded=False,May_payload_decoded=False))
    shutil.copyfile('C:/Users/kjw39/.codex/attachments/3fc9ee83-cb2f-4266-ad5e-321ebeb3ade8/붙여넣은 텍스트.txt',ROOT/'USER_REQUEST.txt')
    for name in ['TEMPORAL_FOLD_CONTRACT.json','TEMPORAL_FOLD_SUPPORT.csv','FEATURE_CONTRACT.json','HAZARD_BIN_CONTRACT.json']:
        shutil.copyfile(V9/name,ROOT/name)
    contract=dict(time=now(),global_windows_days=[7,14,30],cohort_windows_days=[14,30],cohort_families=FAMILIES,
                  global_min_N=200,single_min_N=100,cross_min_N=200,min_gt4h_events=20,
                  ratio_min_valid_walltime_N='same as source minimum N',high_GPU_threshold=16,
                  frozen_before_VALID=True,adjusted_from_VALID=False,
                  support='One source supplies all family statistics; N, tail events and valid ratio support must all pass',
                  same_timestamp_rule='end_time < prediction_time; window lower bound inclusive',
                  prior='Frozen earliest TRAIN prefix reaching N200 and20 >4h; unavailable until last prefix completion +1ns',
                  cold_start='NaN statistics, fallback_depth=-1; no zero-imputed runtime or tail rates',
                  fallback='cross -> partition same window -> global same window -> global30 if distinct -> available frozen TRAIN prior; single -> global same window -> global30 -> prior')
    write('REGIME_SUPPORT_CONTRACT.json',contract)
    protocol=dict(time=now(),arms=['EXPANDING_R0','EXPANDING_R1','EXPANDING_R2','EXPANDING_R3','D90_R2'],
                  calibration_states=['C0'],C1='Optional rolling14 state not included; no calibration search',
                  learner=read(V9/'EXPERIMENT_PROTOCOL.json')['D1'],grid=record(V9/'HAZARD_BIN_CONTRACT.json'),
                  R0='Frozen V9 D1 boosters reused with all-row parameter parity; exact same folds; V10 log-space scoring',
                  prediction_time='submit_time for TOTAL; completed outcomes visible strictly before each submission',
                  observation_cutoff='Inherited fold labels including right censoring; no April/May source read',
                  tail_continuation='LAST_RATE with positive hazard clipping1e-7..1-1e-7, unchanged V9 edges',
                  gates=dict(A_pooled_Q90=[.88,.92],B_min_supported_fold_Q90=.85,C_gt4h=.85,D_gt12h=.80,
                             E_gt24h_min_if_supported=.70,tail_support_N=100,fold_support_N=100,
                             F_reservation_to_W0_max=.80,G_finite_NLL=True,H_zero_support=0,I_future_reads=0),
                  gate_E='Catastrophic means <70% with>=100 exact >24h events; otherwise report only',
                  gate_F='Materially lower means at least20% lower slot-rounded GPUh than requested walltime W0',
                  ranking=['Q90_pinball','reservation_actual_GPUh','Q50_MAE','coverage_std','inference_seconds'],
                  ablation='Five grouped removals from best R2/R3 by same rank; failed models diagnostic only; removing a family removes derived trends depending on it',
                  stage_C='Only if TOTAL all gates pass; failed candidates never promoted',April_allowed=False,May_allowed=False)
    write('EXPERIMENT_PROTOCOL.json',protocol)
    write('EXECUTION_ENVIRONMENT.json',dict(python=platform.python_version(),pandas=pd.__version__,numpy=np.__version__,lightgbm=lightgbm.__version__,backend='CPU4 deterministic'))
    source=V9/'.local/PREAPRIL_SOURCE.parquet'
    f=pd.read_parquet(source)
    assert f.submit_time.lt(pd.Timestamp('2025-04-01T00Z')).all() and f.job_id.is_unique
    end=pd.Timestamp(read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['final_information_cutoff'])
    events=completed(f,end)
    p=make_prior(events,pd.Timestamp(prep(1)['fit_cutoff']))
    write('FROZEN_TRAIN_PRIOR.json',p)
    records=[]
    for i in range(1,6):
        for role in ['TRAIN','CAL','VALID']:
            path=V9/'.local'/f'fold{i}'/(role+'.parquet');g=pd.read_parquet(path)
            assert ids(g)==read(ROOT/'TEMPORAL_FOLD_CONTRACT.json')['folds'][i-1]['membership'][role]
            records.append(dict(fold=i,role=role,**record(path)))
    write('SOURCE_MANIFEST.json',dict(time=now(),base=BASE,prior_manifests=prior,source=record(source),roles=records,
                                    event_cutoff=str(end),static_provenance='Kestrel_trace_proxy',April_payload_read=False,May_payload_read=False))
    (ROOT/'.gitignore').write_text('.local/\n__pycache__/\n',encoding='utf-8')
    (ROOT/'.gitattributes').write_text('* -text\nFOLD_MODELS/** linguist-generated=true\n',encoding='utf-8')
    (ROOT/'REGIME_FEATURE_SPEC.md').write_text('''# V12 causal regime specification

TOTAL predicts at submit_time. Each explicit index window contains only completed
episodes with `prediction_time - window <= end_time < prediction_time` and
`submit_time <= start_time <= end_time`. The job cannot contribute to its own
submission features. Simultaneous completions are excluded, regardless of input order.

Global7/14/30d: runtime quantiles25/50/75/90/95; >1/4/8/12/24h prevalence;
completed count, sum(runtime*requested_GPU)/3600, mean requested GPUs, fraction GPUs>=16;
runtime/requested-walltime quantiles50/75/90. Invalid/nonpositive walltimes are
excluded from ratio samples. Runtime quantiles use linear interpolation.

Six cohort families: partition, QoS, walltime buckets <=1h/4h/12h/24h/>24h,
GPU buckets <=1/4/8/16/>16; partition x QoS; partition x walltime.
Missing categories have an explicit sentinel, never an outcome-derived category.
14/30d cohort features: N, runtime Q50/Q90, >4h/>12h rates, ratio Q50.
No other crosses or7d cohorts. Exact raw N and selected support N, tail N, ratio N,
fallback depth and newest/oldest observation ages are retained per family.

Support and fallback are frozen in REGIME_SUPPORT_CONTRACT.json. A prior is
available only after its own newest observation; earlier TRAIN rows remain NaN.
Absolute dates, hour and weekday are excluded. Metadata ages describe observation
freshness. Current unfinished jobs are excluded, so completion-selection lag is a
limitation of the hypothesis, not a label reconstructed from the future.

R0=29 V9 static features; R1 adds global; R2 adds cohorts; R3 adds four trends:
global Q90(7d)-Q90(30d), >4h(7d)- >4h(30d), Q50(7d)/Q50(30d),
ratio Q50(14d)-ratio Q50(30d). Zero-denominator trends remain NaN.
Static descriptors remain archived trace proxies, not verified initial-submit values.

Only C0 raw hazard is preregistered. Positive piecewise rates and last-rate
continuation retain the exact V9 grid; stable log-space interval scores use V10 math.
No additive-seconds or static global probability calibration is used.
''',encoding='utf-8')
    names=['REGIME_FEATURE_SPEC.md','REGIME_SUPPORT_CONTRACT.json','EXPERIMENT_PROTOCOL.json','FROZEN_TRAIN_PRIOR.json','TEMPORAL_FOLD_CONTRACT.json','FEATURE_CONTRACT.json','HAZARD_BIN_CONTRACT.json','regime12.py']
    write('PREREGISTRATION.json',dict(time=now(),files=[record(ROOT/n) for n in names],before_feature_forensic=True,before_training=True))
    write('REGIME_FEATURE_CONTRACT_FREEZE.json',dict(time=now(),files=[record(ROOT/n) for n in ['REGIME_FEATURE_SPEC.md','regime12.py','FROZEN_TRAIN_PRIOR.json']]))
    write('REGIME_SUPPORT_FREEZE.json',dict(time=now(),files=[record(ROOT/'REGIME_SUPPORT_CONTRACT.json')]))
    print('V12_REGISTERED',now(),len(events),flush=True)

if __name__=='__main__':main()
