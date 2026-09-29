from common16 import *
import importlib.metadata as meta

assert not list(LOCAL.glob('native_fold?/*.json')),'Cannot preregister after metrics'
assert (ROOT/'RADDIT_CROSSWALK_SUMMARY.json').exists()
family=dict(time=now(),family='LightGBM quantile with label-free TRAIN-only categorical encoding',catboost_installed=False,
    environment=str(Path(sys.executable)),versions={p:meta.version(p) for p in ['numpy','pandas','scipy','scikit-learn','lightgbm','pyarrow']},
    reason='CatBoost is absent from frozen environment. Ordered target statistics based on submission order alone do not certify outcome completion before each query. Use explicitly authorized LightGBM fallback; no target categorical encoding.',
    same_information_architecture_comparison='H0/H1 in gated Kestrel bridge; no CatBoost-superiority claim',
    sources=['https://catboost.ai/docs/en/references/training-parameters/common','https://catboost.ai/docs/en/concepts/algorithm-main-stages_cat-to-numberic'])
write('MODEL_FAMILY_DECISION.json',family)
pr=dict(time=now(),before_any_new_model_fit=True,base=BASE,audit_contract_sha256=sha(ROOT/'AUDIT_PROTOCOL.json'),
    folds=read(ROOT/'NATIVE_FOLD_CONTRACT.json')['folds'],target='wallclock_used_sec',native_scope='HISTORICAL_DIAGNOSTIC_ONLY; all jobs, not GPU-only',
    lightgbm_parameters=dict(n_estimators=240,num_leaves=63,learning_rate=.05,min_child_samples=50,max_bin=127,
        max_cat_threshold=32,cat_smooth=20,reg_lambda=1,n_jobs=4,random_state=1601,deterministic=True,force_col_wise=True,verbosity=-1),
    quantiles=[.5,.9],target_transform='none; direct seconds',prediction_support='clip Q50>=0 and Q90>=Q50; no requested-walltime cap',
    calibration='NONE; no validation-dependent recalibration, sweep or early stopping',
    arms={'D0':'four resource/request columns only','D1':'D0 + eight opaque/structured identity categories',
        'D2':'D1 + modules/conda bundle categories AND all TRAIN-observed token multi-hot membership; explicit unseen count',
        'D3':'D2 + label-free TRAIN frequency and user/script, account/script, user/submit_line cooccurrence',
        'D4':'D2 + strictly completed TRAIN-neighbor statistics at k16/64'},
    predeclared_contrasts={'IDENTITY_ONLY':'D0 + user/account/name/script categories','SOFTWARE_STACK':'D0 + full modules/conda categories and TRAIN-token membership'},
    contrasts_scope='Two explicit information contrasts requested by section34, not open-ended D5+ architecture search.',
    recurrence='Label-free TRAIN fitted frequencies only; full TRAIN fit state, not target statistics or claims of per-row online ingestion replay.',
    controls={'A':'D2 jointly permute all rich fields within TRAIN UTC submission days, seed1601; validation unchanged; all3folds',
        'B':'SHA256 seeded bijection of user/account/script; exact TRAIN and VALID design-matrix equality; same frozen model predictions. Invariance control, not information-destroying null.',
        'C':'Future-metadata poisoning: current feature and prediction unchanged',
        'D':'Strict payload whitelist rejects all outcome/future/unknown keys',
        'E':'Neighbor end >= query submit rejected, including equality'},
    neighbor={'pool':'TRAIN only, including TRAIN queries with strict end_i<submit_j; no VALID outcome may enter features',
        'retrieval':'Union of latest16 completed matches per each10 metadata fields and latest64 global completed TRAIN jobs; deduplicate',
        'ranking':'8 identity equality scores + 2 software token Jaccards + exp(-mean absolute TRAIN-IQR-normalized log-resource distance), divided by11; deterministic pool-row tie break',
        'search_claim':'Bounded approximate global retrieval; exact ranking within candidate union; no claim of exhaustive global nearest neighbors',
        'k':[16,64],'statistics':['Q50','Q75','Q90','mean_log_runtime','long4h_fraction','long12h_fraction','support_count','nearest_similarity','mean_similarity'],
        'empty_pool':'support0; other values missing, not fake zero outcomes'},
    embedding={'arm':'D_EMB_DIAGNOSTIC_ONLY','dimensions':4096,'representation':'All directly stored numeric coordinates; no SVD/private inverse transform',
        'mapping':'Require both unique T0 EKEY2 embedding->historic AND unique exact historic->Kestrel RESEARCH_PROXY_CROSSWALK. Ambiguous mappings and comparable holdout conflicts excluded.',
        'TRAIN_cap':100000,'sampling':'seed1601+fold uniform without replacement from mapped mature TRAIN rows; no label stratification',
        'VALID':'all unique-mapped native VALID rows',
        'paired_baselines':['EMB_D0','EMB_D2'],'all_paired_models_same_rows':True,'production_selectable':False,
        'limitations':'Capped TRAIN diagnostic and exported-completion subset; does not prove latent representation lacks signal if model fails.'},
    information_success='Any D1-D4 min-fold gain>=.05 AND pooled >4h gain>=.05 AND Q90pinball ratio<=1.05 vs D0',
    consistent_temporal_gain='At least2of3 folds improve BOTH >4h coverage and pinball, with no fold >4h loss exceeding.05',
    program_stop='ALL D1-D4 have min-fold gain<.03, >4h gain<.03, >12h gain<.03, relative pinball improvement<.03, and no consistent temporal gain',
    gray_zone='If strict success and full-stop both false, freeze LIMITED_OR_MIXED_INFORMATION_VALUE. Do not mislabel strong success or no-information. Bridge requires strict success; no adaptive search to cross threshold.',
    ablation_trigger='Any D1-D4 min-fold gain>=.05 OR >4h gain>=.05, with pinball ratio<=1.05. Best qualifying arm by lowest pinball; ties D1,D2,D3,D4. Six fixed group omissions on all3folds; absent group is NOT_APPLICABLE, not a new fit.',
    ablation_groups={'A':'resource request','B':'scheduler qos/partition','C':'user/account','D':'name/script/submit_line/job_type','E':'modules/conda','F':'neighbor statistics'},
    bridge={'trigger':'Strict native success; source authority filter before any fit','R0':'exact V13 EXPANDING_S4 / H0','R15':'V15 R2 diagnostic lower-pinball reference, never selected',
        'R16-A':'same H0 hazard + approved rich categories / H1','R16-B':'same-information LightGBM direct Q50/Q90','R16-C':'best approved A/B + causal neighbors, fixed k16/64',
        'H2':'H1 + modules/conda only if source-certified deployable; otherwise NOT_RUN_NOT_DEPLOYABLE',
        'folds':'exact existing five pre-April Runtime folds','max_new_challengers':3,
        'distribution_gate':'Preserve V13 finite proper interval-NLL gate. Two-quantile outputs alone do not define a distribution and cannot claim that gate passed.'},
    safety_gates={'pooled_Q90':[.88,.92],'minimum_fold':.85,'gt4h':.85,'gt12h':.80,'gt24h_supported':.70,
        'proper_score':'exact V13 finite proper interval NLL, no invented density','invalid_support':0,'reservation':'exact frozen V13 gate',
        'causality':True,'unseen_callability':True},
    remaining='NOT_RUN_TOTAL_GATE_FAILURE unless every TOTAL gate passes',
    cc4={'C0':'exact frozen T0/B0 hourly submitted-GPUh LightGBM; T2_F0/T3_F2 stay research',
        'trigger':'Runtime material benefit (same >=5pp min OR >4h and <=5%pinball degradation), OR strict native success plus deployable Runtime narrowly fails (min>=.80,gt4>=.80,gt12>=.75,gt24>=.65 and nominal/proper-score/causality pass)',
        'C3':'C0 + approved past-only metadata; submit<t0','C4':'C3 + compact class composition only when C3 shows lower pinball with no existing coverage gate regression',
        'selection':'existing frozen CC4 evaluation gates; no new target/resolution/model family'},
    firewall={'April_selection':False,'May_2025_opened':False,'April_boundary':'UTC spill in March source read only for exclusion; never fitted or selected',
        'May_2024':'historical TRAIN allowed'},
    forbidden_actions=['optimizer','MESS','OpenDSS','workload flexibility branch','private exporter reconstruction','private vector transform'],
    no_information_vs_deployability_vs_safety='Three separate questions and verdicts required')
write('PREREGISTRATION.json',pr)
md('CAUSAL_NEIGHBOR_SPEC.md','# Causal completed-history neighbors\n\n'+json.dumps(pr['neighbor'],indent=2)+'\n\nAll target statistics use TRAIN-only candidates satisfying strict completion before submission. Category vocabularies and resource scaling are fitted on TRAIN without labels. Unknown categories cannot retrieve same-ID candidates. Exact outcome keys are rejected by the predictor boundary. Row-level selected neighbor IDs and completion-margin audits remain local and SHA-bound.\n')
files=['PREREGISTRATION.json','MODEL_FAMILY_DECISION.json','features16.py','neighbors16.py','train_native16.py','embedding16.py','test16.py']
write('PREREGISTRATION_HASH.json',dict(time=now(),before_any_new_fit=True,files={p:sha(ROOT/p) for p in files}))
print('PREREGISTERED',sha(ROOT/'PREREGISTRATION.json'),flush=True)
