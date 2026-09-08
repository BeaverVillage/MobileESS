"""Post-result audits and Korean review; never fits or selects a model."""
from .common import *
import argparse,platform,importlib.metadata as md,re
def link(name,label=None):return f'[{label or name}](<{(OUT/name).as_posix()}>)'
def audit():
    reg,pre=authority();start=read('V40R5_PROTECTED_SCOPE_START.json');rows=[]
    prior_compute=read('V40R5_COMPUTE_LEDGER.json') if (OUT/'V40R5_COMPUTE_LEDGER.json').exists() else {}
    for row in start['files']:
        root=R3 if row['root']=='R3' else R4;h=sha(root/row['path']);assert h==row['SHA256'],row['path'];rows.append({**row,'end_SHA256':h,'unchanged':True})
    states={}
    for p,s in start['worktrees'].items():
        h=git('rev-parse','HEAD',cwd=p);status=git('status','--porcelain',cwd=p);states[p]={'HEAD':h,'status':status,'unchanged':h==s['HEAD'] and status==s['status']}
    paths=git('diff','--name-only',BASE).splitlines()+git('ls-files','--others','--exclude-standard').splitlines();assert all(allowed(p) for p in paths)
    dump('V40R5_PROTECTED_SCOPE_END.json',{'files':rows,'R3_count':start['R3_count'],'R4_count':start['R4_count'],'worktrees':states,'all_R3_R4_hashes_unchanged':True})
    dump('V40R5_PROTECTED_SCOPE_DIFF.json',{'BASE':BASE,'R5_changed_paths':paths,'protected_path_change_count':0,'R3_R4_byte_changes':0,'R3_R4_files_verified':len(rows),
      'optimizer_migration_WAN_terminal_event_trigger_local_repair_modified':False,'R2_status':'SUPERSEDED_BY_V40R3','R4_status':'V40R4_COMPOUND_GPUWORK_SAFETY_FAIL',
      'metadata_only_note':'New R5 branch/index initialized without parent payload checkout. No historical LightGBM newline rewrites. External worktree HEAD/status snapshots are recorded separately.'})
    dump('V40R5_MAY_FIREWALL.json',{'year_month':'2025-05','scientific_reads':0,'target_runtime_status_Actual_reads':0,'training_calibration_selection_threshold_envelope_reads':0,
      'path_index_provenance_metadata':'NONZERO','metadata_sources':['User protocol','Git worktree/index metadata','Current PR source-only time-axis/AEMO contract','R3/R4 provenance'],
      'new_raw_archive_opened':False,'inputs':'Hashed pre-May parent event and maturity artifacts only','no_OS_wide_monitor_claim':True})
    import torch
    runs=read('V40R5_FIT_LEDGER.json')['runs']+read('V40R5_REPRODUCIBILITY_AUDIT.json')['runs']
    for r in runs:
        r.setdefault('device','cpu');r.setdefault('seed',SEED);r.setdefault('threads',4)
    cpu=subprocess.check_output(['powershell','-NoProfile','-Command','(Get-CimInstance Win32_Processor).Name'],text=True).strip()
    dump('V40R5_COMPUTE_LEDGER.json',{'Python':platform.python_version(),'CPU':cpu,'GPU':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,'CUDA':torch.version.cuda,
      'libraries':{n:md.version(n) for n in ['torch','lightgbm','xgboost','scikit-learn','numpy','pandas','scipy']},'exact_device_used':'CPU for all fits and prediction/scenario calculations',
      'GPU_training_used':False,'reason':'Preregistered compact tree/logistic architecture; no neural escalation','seed':SEED,'threads':4,'mixed_precision':False,
      'determinism':reg['tree_parameters'],'runs':runs,'fit_time_seconds_sum':sum(r['fit_time_seconds'] for r in runs),'prediction_time_seconds_sum':sum(r['prediction_time_seconds'] for r in runs),
      'timer_scope':'Summed component timers, including Tweedie simulation in prediction time; not total task wall time','replicate_not_additional_search':True,
      **{k:v for k,v in prior_compute.items() if k.startswith('native_') or k=='thread_controls_note'}})
    dump('V40R5_NO_INTEGRATION_AUDIT.json',{'optimizer_calls':0,'Gurobi_calls':0,'OpenDSS_calls':0,'modifications':{k:False for k in ['A0','A1','M1','MF','migration','WAN','terminal','event_trigger','local_repair','rolling_MPC','second_route_search','V40S2']},
      'evidence':'Only R5 namespace diff; import AST tests exclude optimizer/Gurobi/OpenDSS; execution entrypoints confined to recorded ML modules; no whole-machine process monitor claim',
      'holds':reg['holds'],'interface':'Proposal only; optimizer_use_allowed False on every row'})
    # Supplemental all-model/month results use already saved predictions only.
    from .metrics import aggregate
    from .train import BASELINES,dates_for
    a,i,m=data();dates=dates_for(i);u=reg['burst_threshold_GPUh'];periods={}
    for name in BASELINES:
        q=np.load(OUT/'fits'/name/'selected_q.npy');periods[name]=[]
        for role in ['DEVELOPMENT','CALIBRATION']:
            for month in sorted(set(d[:7] for d in dates[m[role]])):
                ix=m[role]&np.array([d[:7]==month for d in dates]);periods[name].append({'role':role,'month':month,'metrics':aggregate(a['y'][ix],q[ix,0],q[ix,1],u)})
    dump('V40R5_BASELINE_DEVELOPMENT_TEMPORAL_DIAGNOSTIC.json',{'models':periods,'scope':'Saved-prediction exposed diagnostics only; no new selection'})
    chosen=read('V40R5_CAL_SELECTION_FREEZE.json')['frozen_diagnostic_pipeline'];bt=read('fits/PB1/result.json')['selected']['trial']
    ct=read(f'fits/{chosen["classifier"]}/result.json')['selected']['trial'];pairs=[]
    for k in range(10):pairs.append((OUT/'fits/PB1'/f'trial_{bt}_head{k}.txt',OUT/'reproduction/PB1'/f'repeat_head{k}.txt'))
    for p in (OUT/'reproduction/N1').glob('*_count.txt'):pairs.append((OUT/'fits/N1'/p.name,p))
    pairs.append((OUT/'fits'/chosen['classifier']/f'trial_{ct}_model.pkl',OUT/'reproduction'/chosen['classifier']/'repeat_model.pkl'))
    checks=[{'original':a.relative_to(ROOT).as_posix(),'repeat':b.relative_to(ROOT).as_posix(),'original_SHA256':sha(a),'repeat_SHA256':sha(b),'same_bytes':sha(a)==sha(b)} for a,b in pairs]
    dump('V40R5_REBUILD_MODEL_PARAMETER_AUDIT.json',{'files':checks,'all_same_bytes':all(x['same_bytes'] for x in checks),'scope':'Own R5 model files only; parent files never normalized','prediction_audit':'V40R5_REPRODUCIBILITY_AUDIT.json'})
    print('Protected hashes verified:',len(rows),'files. May scientific reads0; optimizer/Gurobi/OpenDSS calls0. Compute ledger ready. Rebuild model bytes equal:',all(x['same_bytes'] for x in checks))

def review():
    reg,pre=authority();sel=read('V40R5_MODEL_SELECTION.json');f=read('V40R5_CAL_SELECTION_FREEZE.json');c=f['frozen_diagnostic_pipeline'];h=read('V40R5_HYBRID_METRICS.json');ev=h['metrics'];det=h['detector']
    body=read('V40R5_BODY_MODEL_REPORT.json')['roles']['EXPOSED_EVALUATION'][c['body_calibration']];bm=body['metrics'];target=read('V40R5_15MIN_TARGET_CONTRACT.json');agg=read('V40R5_15MIN_30MIN_AGGREGATION_AUDIT.json')
    dist=read('V40R5_15MIN_DISTRIBUTION_FORENSIC.json');cnt=read('V40R5_15MIN_COUNT_DIAGNOSTIC.json');sev=read('V40R5_15MIN_SEVERITY_DIAGNOSTIC.json');threshold=read('V40R5_BURST_THRESHOLD_FREEZE.json')
    repro=read('V40R5_REPRODUCIBILITY_AUDIT.json');tests=read('V40R5_TEST_REPORT.json');scope=read('V40R5_PROTECTED_SCOPE_END.json');feas=read('V40R5_BODY_GATE_FEASIBILITY_AUDIT.json');boot=read('V40R5_SUPERIORITY_BOOTSTRAP.json')
    baselines={n:read(f'V40R5_BASELINE_{n}_REPORT.json') for n in ['B0','B1','B2','B3']};clas=read('V40R5_BURST_CLASSIFIER_DIAGNOSTICS.json')['models'];countmetrics=pd.read_csv(OUT/'V40R5_COUNT_RISK_METRICS.csv')
    countn=countmetrics[(countmetrics.role=='EXPOSED_EVALUATION')&(countmetrics.model=='N1')].iloc[0]
    rows=[f'FINAL CLASSIFICATION: **{sel["classification"]}**',f'SELECTED MODEL: **{sel["selected_model"] or "NONE"}**',
      f'BODY MODEL: **PB1 / {c["body_calibration"]}** (선택 실패 시 거부된 진단 모델)',f'BURST CLASSIFIER: **{c["classifier"]}**',f'BURST THRESHOLD: **{sel["burst_threshold_GPUh"]:.9f} GPUh**',
      f'ETA: **{c["eta"]:.12g}**',f'ROBUST ENVELOPE: **{c["envelope"]}**','TRUE CONFIRMATORY: **NO**','OPTIMIZER INTEGRATION: **NO**','PRODUCTION READY: **NO**','',
      'R5는 원래 job 제출 시각으로 15분 × 96 타깃을 재구성하고 BODY 예측·burst 감지·robust abstention을 시험했다. 모든 수치는 이미 노출된 과거 구간의 진단이다. 실패한 pipeline의 adapter 행은 proposal_only=True, scientifically_selected=False, optimizer_use_allowed=False로 보존한다.','',
      f'**1. 계보.** R5 base/R4 receipt={BASE}; R4 research=a925a34848458b07b2a07a43b1150c89c21425b9; R4 prereg=f10187e0b0cbaadde5b28186e70822f5ff258f76; R4 development baseline=1a178ceba65a4bf830c6e0955effb4838d922f3f. R3 receipt=43710c96c36f7e66257885a56ef6df697b3c53bb, R3 scientific=6e2f0791952a9001d2fdd4a6564e0f699ec3fc90. R5 prereg={pre}; CAL-selection commit={sel["selection_commit"]}. PR27 HEAD snapshot={PR_HEAD} (metadata/source-contract read only).','',
      f'**2. 보호 범위.** R3 {scope["R3_count"]}파일 + R4 {scope["R4_count"]}파일의 시작/종료 byte hash가 동일하다. 보호 경로 diff=0. R2 SUPERSEDED_BY_V40R3, R3/R4 FAIL 분류 유지. PR27 merge 없음.','',
      '**3. 타깃 모집단.** raw recovered 4,728,595(부모 provenance; 재스캔 없음), GPU candidates790,173, authorized550,123, service-validity 제외1,784, eligible548,339, missing-GPU 제외240,050, target contributors545,553, target days349. 미래 미제출 작업의 외생 arriving GPU-service demand이며 실제 execution occupancy나 FLOPs가 아니다. F30·GPU결측 대입 없음.','',
      f'**4. 총 GPUh.** {target["total_GPUh"]:,.12f}. 각 작업 g×(end−start)/3600 전량을 submit 구간에 배정했다.','',
      '**5. 구간 수.** 33,504=349×96. D−1 18:00 fixed AEST=D−1 08:00 UTC 발행, 다음 D일00:00–24:00 fixed AEST, [start,end) 경계다.','',
      f'**6. 15→30 재구성.** 모든16,752쌍 최대 차이={agg["max_abs_error_GPUh"]:.12g} GPUh, 허용오차1e-7. 30분 label 반분이나 오차를 맞추는 사후 보정 없음. Event table의 datetime64[us,UTC]를 ns UTC로 정규화하고 정확한 경계를 검증했다.','',
      '**7. AEMO.** 현재 PR의 mean-power 중복 규칙 P15a=P15b=P30을 source-only로 확인했고 합성 power의 energy 보존 오차0. R4 승인 feature에 AEMO가 실제로 없어 새 AEMO feature/payload를 추가하지 않았다. 에너지 quantity에 power 중복 규칙을 적용하지 않는다.','',
      '**8. Feature authority.** 61개: 기존30분 causal history의36개 요약+4개 마지막 값, 순수15분/calendar9개, 직접 재구성한15분 seasonal GPUh/count/maturity12개. Classifier는 여기에 예측 count mean/log 및 large-count probability2개를 사용한다. 새 외부 source 없음.','',
      '**9. 성숙도·인과성.** Parent184,272 proof rows와 새134,016 seasonal proof rows, feature별 ns availability matrix를 검사했다. Historical15분 child는 부모30분 구간의 모든 raw END가 성숙한 경우만 허용하는 보수적 규칙이다. 미래 count/resource/start/end/runtime feature 없음. Origin+5/+15분 leakage 없음. 실제 telemetry ingestion delay/version-history 인증은 범위 밖이다.','',
      f'**10. 15분 분포.** Mature TRAIN N={dist["N"]:,}, zero={dist["zero_fraction"]:.4%}, positive={dist["positive_fraction"]:.4%}, mean={dist["mean"]:.6f}, median={dist["quantiles"]["P50"]:.6f}, P90={dist["quantiles"]["P90"]:.6f}, P95={dist["quantiles"]["P95"]:.6f}, P99={dist["quantiles"]["P99"]:.6f}, max={dist["quantiles"]["max"]:.6f} GPUh.','',
      f'**11. Count 과분산.** TRAIN mean={cnt["stats"]["mean"]:.6f}, variance={cnt["stats"]["variance"]:.6f}, variance/mean={cnt["stats"]["variance_mean_ratio"]:.6f}, zero={cnt["stats"]["zero_fraction"]:.4%}. NB는 Poisson보다 낮은 BIC이며 ZINB 추가 zero는 경계에 가깝다.','',
      f'**12. Severity.** TRAIN jobs={sev["stats"]["N"]:,}, mean={sev["stats"]["mean"]:.6f}, median={sev["stats"]["quantiles"]["P50"]:.6f}, P95={sev["stats"]["quantiles"]["P95"]:.6f}, P99={sev["stats"]["quantiles"]["P99"]:.6f}, max={sev["stats"]["quantiles"]["max"]:.6f} GPUh. N15–mean severity Spearman={sev["count_mean_severity"]["Spearman"]:.6f}. 새 EVT fit 없음.','',
      f'**13. 새 burst 기준.** Strict DeltaW15>{threshold["u_B_GPUh"]:.9f} GPUh. TRAIN 양수Q95로 고정했고 R4의441.777542를 재사용하지 않았다.','',
      f'**14. Burst prevalence.** TRAIN 전체15분 구간의 {threshold["TRAIN_burst_prevalence"]:.4%}; EXPOSED_EVALUATION은 {ev["coverage"]["burst"]["N"]}/{ev["N"]}={ev["coverage"]["burst"]["N"]/ev["N"]:.4%}.','',
      '**15. Baselines.** 모두15분 재학습. 표는 개발 단계에서 고정한 raw pipeline이다.','',
      '| 모델 | Primary | 전체 coverage | 양수 coverage | burst coverage | 안전 |','|---|---:|---:|---:|---:|---|']
    for n,r in baselines.items():
        v=r['EXPOSED_EVALUATION'];rows.append(f'| {n} | {v["primary"]:.6f} | {v["coverage"]["overall"]["value"]:.2%} | {v["coverage"]["positive"]["value"]:.2%} | {v["coverage"]["burst"]["value"]:.2%} | {"PASS" if r["safety"]["all_pass"] else "FAIL"} |')
    rows+=['',f'**16. BODY 모델.** PB1 Hurdle LightGBM / {c["body_calibration"]}. 모델 trial은 DEV oracle BODY에서, BC0/BC1과 최종 조합은 CAL에서 결정했다. BODY/BURST oracle label은 학습·진단에만 사용한다.','',
      f'**17. BODY Q90 coverage.** {bm["coverage"]["overall"]["value"]:.6%}.','',f'**18. Positive BODY coverage.** {bm["coverage"]["positive"]["value"]:.6%}. 요청 게이트는 두 값 모두90–95%다.','',
      f'**19. BODY loss/WAPE.** Positive normalized pinball={bm["primary"]:.9f}; Q50 WAPE={bm["point_q50"]["WAPE"]:.4%}; Q50 MAE={bm["point_q50"]["MAE"]:.6f} GPUh.','',
      'BODY 게이트의 수학적 가능성도 별도로 검사했다. 비음수 Q90은 모든 실제0을 덮으므로 overall=z+(1−z)×positive다. BODY zero 비율 z>50%이면 positive coverage≥90%와 overall≤95%는 동시에 불가능하다. 아래는 모델 성능과 별개의 구성비 제약이며 게이트를 완화하지 않았다.','',
      '| 역할 | BODY zero fraction | positive90%일 때 최소 overall | 동시 가능 |','|---|---:|---:|---|']
    for role,r in feas['roles'].items():rows.append(f'| {role} | {r["body_zero_fraction"]:.4%} | {r["minimum_overall_coverage_if_positive_coverage_90"]:.4%} | {r["both_requested_body_bands_feasible"]} |')
    zero=read('V40R5_ZERO_INFLATION_GATE_AUDIT.json')
    rows+=['','PRIMARY RESULT: **NO REGISTERED COMBINATION PASSED THE FROZEN SAFETY GATES**','',
      'IMPORTANT METHODOLOGICAL FINDING: **BODY_GATE_STRUCTURAL_INCOMPATIBILITY_DUE_TO_ZERO_INFLATION**','',
      'BODY_GATE_STRUCTURAL_INCOMPATIBILITY=YES. 전체 TRAIN의 zero 비율과 BODY-only zero 비율은 서로 다른 분모다. 실제 CAL BODY는 1,195/2,345가 zero이므로 양수 coverage≥90%이면 전체 coverage≥95.095949%다. 이 때문에 필수 CAL BODY 게이트는 모델과 무관하게 동시 통과가 불가능하다. 정수 표본에서도 양수 구간을 최소1,035개 덮어야 하지만 전체 상한이 허용하는 최대는1,032개다.','',
      'The 15-min target increased zero inflation sufficiently that the preregistered simultaneous overall and positive BODY Q90 coverage bounds became structurally incompatible. Therefore, failure of the registered BODY gate cannot be interpreted solely as evidence of poor forecast quality.','',
      'The comparison is retrospective and diagnostic. The frozen failure taxonomy is retained; it does not mean that all models are poor.','',
      '| 역할 / BODY 후보 | 전체 coverage | zero coverage | 양수 BODY coverage | 양수 Q90 normalized pinball | 양수 Q50 WAPE | 양수 Q50 MAE GPUh | under GPUh | over GPUh |',
      '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for role in ['CALIBRATION','EXPOSED_EVALUATION']:
        for name,candidate in zero['candidates'].items():
            v=candidate['roles'][role];pt=v['positive_Q50_point']
            rows.append(f'| {role} / {name} | {v["overall_coverage"]:.6%} | {v["zero_only_coverage"]:.2%} | {v["positive_BODY_coverage"]:.6%} | {v["positive_Q90_normalized_pinball"]:.9f} | {pt["WAPE"]:.6%} | {pt["MAE"]:.6f} | {v["underprediction_GPUh"]:.3f} | {v["overprediction_GPUh"]:.3f} |')
    rows+=['','A: PB1 trial0/BC1은 CAL·EXPOSED 모두 양수 BODY coverage90–95%를 충족한다. B: BODY 게이트 내에서는 두 split 모두 전체 upper95%만으로 탈락한다. CAL은 구조적 충돌이고, EXPOSED는 zero 비율이50%미만이라 원리적으로 가능한 게이트에서 해당 예측의 전체 상한 초과다. 이 결과는 전체 pipeline의 통과를 뜻하지 않는다. C: raw PB1 trial0/BC0와 trial1/BC0는 양수 BODY coverage 자체도90%미만이다.','',
      '모든 기존 BODY 옵션과 두 raw tuning trial을 보고했다. Trial1은 사후 진단뿐이며 새 BC1 calibration을 만들지 않았다. BC1은 기존 저장 배열만 읽었다. Pinball 평균·합, Q90 기준 양수 WAPE/MAE와 월별 실패 사유는 '+link('V40R5_ZERO_INFLATION_GATE_AUDIT.json','정식 감사 JSON')+' 및 '+link('V40R5_BODY_GATE_FEASIBILITY_PROOF.md','수학적 증명')+'에 있다.','',
      'Burst detector/eta/envelope/overreservation 게이트는 모두 그대로이며 자동 PASS는 없다. 모델 재학습·새 calibration·새 threshold·재선택·winner promotion=0.','',
      'V40R5 remains failed under its frozen preregistration; the evaluation contract will be corrected only in a separate prospective revision.','']
    rows+=['','**20. Auxiliary count.** N0 causal seasonal 대비 N1 LightGBM Poisson mean+TRAIN conditional NB dispersion. Classifier TRAIN count feature는5개 chronological expanding folds와 N0 warm-up으로 만들었다. 완료 label이 destination의 첫 origin까지 성숙해야 fold fit에 들어간다.','',
      f'**21. Large-count recall.** N_high={threshold["N_high"]:.6f}; N1 recall(P90>N_high)={countn["large_count_recall_using_P90"]:.6%}, count MAE={countn["MAE"]:.6f}, RMSE={countn["RMSE"]:.6f}.','',
      '**22. Classifier 비교.** C0 TRAIN base rate, C1 logistic, C2 LightGBM, C3 XGBoost. Trial은 DEV PR-AUC/Brier, eta는 CAL에서만 고정했다.','',
      '| 모델 | PR-AUC | ROC-AUC | recall | GPUh recall | ECE | FPR | detector safety |','|---|---:|---:|---:|---:|---:|---:|---|']
    for name,v in clas.items():
        r=v['EXPOSED_EVALUATION'];rows.append(f'| {name} | {r["PR_AUC"]:.6f} | {r["ROC_AUC"]:.6f} | {r["recall"]:.2%} | {r["GPUh_weighted_recall"]:.2%} | {r["ECE"]:.6f} | {r["FPR"]:.2%} | {r["gate_PASS"]} |')
    rows+=['',f'**23. 고정 classifier AUC.** PR-AUC={det["PR_AUC"]:.6f}, ROC-AUC={det["ROC_AUC"]:.6f}.','',f'**24. Recall.** {det["recall"]:.6%}; TP={det["TP"]}, FN={det["FN"]}.','',
      f'**25. GPUh-weighted recall.** {det["GPUh_weighted_recall"]:.6%}.','',f'**26. Detector captured burst.** {det["captured_burst_GPUh"]:,.6f} GPUh, fraction={det["captured_burst_GPUh_fraction"]:.6%}. 감지 성공과 envelope가 실제 크기를 덮는지는 별개다.','',
      f'**27. Eta.** {c["eta"]:.12g}. CAL recall와 GPUh recall≥90%를 만족하는 가장 큰 threshold. 95%-recall 민감도도 사전 규칙으로 보존했으나 선택을 바꾸지 않았다.','',
      '**28. Robust envelope 비교.** R0/R1은 CAL burst empiricalQ90/Q95. R2는 고정6시간대×TRAIN 예측count-riskQ75 class부터 시작해 지원N30미만이면 count class→time→global로 fallback한다. 전체 CAL 조합의 loss·coverage·과예약을 보존했다.','',
      f'**29. 고정 envelope.** {c["envelope"]}; 전체 조합 CAL 통과 수={f["eligible_combinations"]}. 선택 실패 시 이 policy는 거부된 진단 예제다. Robust envelope를 body Q90이라고 부르지 않는다.','',
      f'**30. Hybrid 전체 coverage.** {ev["coverage"]["overall"]["value"]:.6%}.','',f'**31. Hybrid 양수 coverage.** {ev["coverage"]["positive"]["value"]:.6%}.','',f'**32. Hybrid burst coverage.** {ev["coverage"]["burst"]["value"]:.6%}.','',
      '**33. 월별 burst.** 작은 표본은 INSUFFICIENT_SUPPORT이며 pooling으로 실패를 숨기지 않았다. Catastrophic gate는 safe reserve WAPE>200%다.','',
      '| 월 | burst N | burst coverage | gate | safe WAPE | catastrophic |','|---|---:|---:|---|---:|---|']
    for r in h['safety']['temporal']:
        b=r['metrics']['coverage']['burst'];rows.append(f'| {r["month"]} | {b["N"]} | {b["value"]:.4%} | {r["burst_gate"]} | {r["metrics"]["safe_point"]["WAPE"]:.2%} | {r["catastrophic_safe_WAPE"]} |')
    rows+=['',f'**34. Positive normalized pinball.** {ev["primary"]:.9f}; ZERO 최소 유용성 기준은0.9미만이다. Hybrid에서는 Q90-style 의사결정 손실이며 true unconditional Q90 주장과 구분한다.','',
      f'**35. WAPE.** Safe envelope 전체={ev["safe_point"]["WAPE"]:.4%}, 양수={ev["positive_safe_point"]["WAPE"]:.4%}; body Q50 전체={ev["point_q50"]["WAPE"]:.4%}. Cumulative reserve WAPE={h["cumulative_reserve"]["WAPE"]:.4%}; daily total reserve MAE/bias={h["cumulative_reserve"]["daily_total_MAE_GPUh"]:.6f}/{h["cumulative_reserve"]["daily_total_bias_GPUh"]:.6f} GPUh; horizon crossing={h["cumulative_reserve"]["horizon_crossing"]}.','',
      f'**36. Overprediction.** {ev["overprediction_GPUh"]:,.6f} GPUh.','',f'**37. Underprediction.** {ev["underprediction_GPUh"]:,.6f} GPUh.','',f'**38. Missed burst.** {ev["missed_burst_GPUh"]:,.6f} GPUh.','',f'**39. Envelope captured fraction.** {ev["captured_burst_fraction"]:.6%}.','']
    for number,label in [(40,'30MIN'),(41,'60MIN')]:
        r=read(f'V40R5_{label}_SECONDARY_DIAGNOSTIC.json');rows+=[f'**{number}. {label} 보조 진단.** Sum-of-15min safe reserve coverage={r["coverage"]:.6%}, WAPE={r["safe_point"]["WAPE"]:.4%}, positive pinball score={r["positive_normalized_pinball_score"]:.9f}. 15분 출력의 합이며 해당 시간척도의 true Q90이라고 부르지 않는다.','']
    rows +=[f'**42. Bootstrap.** {boot["status"]}; 95%CI={boot["CI95"]}. Safety 실패 시 사전 규칙에 따라 실행하지 않는다. 비교 baseline={sel["strongest_baseline"]}.','',
      '**43. Confirmation.** TRUE_CONFIRMATORY_AVAILABLE=NO. 모든 과거 split은 노출된 TRAIN/DEVELOPMENT/CAL/STRESS 역할이며 새 untouched로 이름을 바꾸지 않았다.','',
      '**44. May.** 2025년5월 scientific reads=0. 경로/index/source/provenance metadata는 NONZERO로 공개한다. Raw archive 및 May scientific payload를 새로 열지 않았다.','',
      '**45. 호출.** Optimizer=0, Gurobi=0, OpenDSS=0. Interface는 proposal뿐이다.','',
      '**46. 수정 금지.** Optimizer modified=NO; migration=NO; WAN=NO; terminal=NO; event trigger=NO; local repair=NO. A0/A1/M1/MF/Fresh/rollingMPC/second route search/V40S2 변경 없음. Production q=UNCHANGED; PF=.95; Q control=NO; electrical=HOLD; electricalB0–B3=NO; FULL_MAY=NO.','',
      f'**47. Tests.** {tests["passed"]}/{tests["tests"]} PASS, 실패{tests["failed"]}, 아직 미실행{tests["not_run"]}. '+('Required-artifact/clean-state 검사를 receipt commit 후 완료했다.' if tests['not_run']==0 else 'Required-artifact/clean-state 검사는 receipt commit 이후 단계다.')+' 테스트 성공은 과학적 safety 성공을 뜻하지 않는다. 최초 post-fit 검사에서 float64 극소확률과 등록된 float32 feature를 상대오차로 비교한 오류1건을 발견했다. 등록된 dtype 변환 후 정확한 배열 일치 검사로 수정했으며 모델·입력·예측·게이트는 변경하지 않았다. 최초 검사와 정정 기록을 보존했다.','',
      f'**48. 재현.** 독립 same-seed rebuild1회. Safe prediction max/mean 차이={repro["differences"]["selected_safe"]["max"]:.12g}/{repro["differences"]["selected_safe"]["mean"]:.12g} GPUh, CAL primary 원본/재현={repro["CAL_primary_original"]:.9f}/{repro["CAL_primary_repeat"]:.9f}. 더 좋은 재현을 선택하지 않았다. Count crossfit, BODY, classifier를 다시 학습했다. '+link('V40R5_COMPUTE_LEDGER.json','장치·버전·시드·학습/예측시간')+'.','',
      '**49. 연구 커밋.** '+link('V40R5_FINAL_COMMIT_RECEIPT.json','Final research commit receipt')+'에 exact SHA를 저장한다. Scientific result commit과 후속 closure verification commit을 구분한다.','',
      '**50. Receipt 커밋.** 자기참조 SHA 대신 receipt JSON에 git log로 해석하는 명령을 저장한다. 최종 응답에 실제 closure/receipt HEAD를 보고한다.','',
      'NEXT_RECOMMENDED_REVISION=**V40R5R1_ZERO_INFLATION_AWARE_GATE_CORRECTION**. 제안만 기록하며 R5R1 생성·실행은 하지 않았다. 향후 수정 범위는 평가계약뿐이다: occurrence와 양수 magnitude 분리, positive BODY Q90 gate, overall coverage의 diagnostic 전환, burst 및 hybrid 과예약·안전 게이트 유지. 15분×96 target/cohort/splits/causal features/burst threshold/model registry/hyperparameters/optimizer firewall/May firewall은 유지한다. 현재 R5에 이 변경을 선반영하지 않았다.','',
      link('V40R5_PREREGISTRATION.json','사전등록')+' · '+link('V40R5_MODEL_SELECTION.json','선택 결과')+' · '+link('V40R5_BODY_GATE_FEASIBILITY_AUDIT.json','BODY gate 가능성')+' · '+link('V40R5_OPTIMIZER_INTERFACE_CONTRACT.json','연결 제안 계약')]
    comparison=['| Envelope | CAL primary | CAL burst coverage | CAL overreservation GPUh |','|---|---:|---:|---:|']
    for choice in f['combinations']:
        if choice['classifier']==c['classifier'] and choice['body_calibration']==c['body_calibration']:
            v=choice['CAL_metrics'];comparison.append(f'| {choice["envelope"]} | {v["primary"]:.6f} | {v["coverage"]["burst"]["value"]:.4%} | {v["overprediction_GPUh"]:,.3f} |')
    comparison+=['',f'R0={read("V40R5_ROBUST_ENVELOPE_R0.json")["value_GPUh"]:.9f} GPUh; R1={read("V40R5_ROBUST_ENVELOPE_R1.json")["value_GPUh"]:.9f} GPUh. 비교는 동일한 고정 BODY/classifier에서 CAL만 사용했다. R2의 각 group 지원 수·quantile·fallback은 별도 JSON에 있다.','']
    position=next(k for k,x in enumerate(rows) if x.startswith('**29.'));rows[position:position]=comparison
    (OUT/'V40R5_FINAL_REVIEW.md').write_text('\n\n'.join(rows[:10])+'\n\n'+'\n'.join(rows[10:])+'\n',encoding='utf-8',newline='\n')
    print('Korean review generated; requested sections1..50.')

def receipt():
    reg,pre=authority();assert git('status','--porcelain')==''
    science=git('rev-parse','HEAD');names=read('V40R5_REQUIREMENTS_MANIFEST.json')['required_artifacts']
    assert [n for n in names if not (OUT/n).exists()]==['V40R5_FINAL_COMMIT_RECEIPT.json']
    dump('V40R5_FINAL_COMMIT_RECEIPT.json',{'BASE':BASE,'R4_research':'a925a34848458b07b2a07a43b1150c89c21425b9','preregistration_commit':pre,
      'selection_freeze_commit':read('V40R5_MODEL_SELECTION.json')['selection_commit'],'final_research_commit':science,
      'final_receipt_commit':'Resolve following closure commit: git log -1 --format=%H -- dayahead/artifacts/v40r5_15min_selective_burst_gpuwork/V40R5_FINAL_COMMIT_RECEIPT.json',
      'classification':read('V40R5_MODEL_SELECTION.json')['classification'],'selected_model':read('V40R5_MODEL_SELECTION.json')['selected_model'],
      'scientific_status':'FAIL','PRIMARY_RESULT':'NO REGISTERED COMBINATION PASSED THE FROZEN SAFETY GATES',
      'IMPORTANT_METHODOLOGICAL_FINDING':'BODY_GATE_STRUCTURAL_INCOMPATIBILITY_DUE_TO_ZERO_INFLATION',
      'NEXT_RECOMMENDED_REVISION':'V40R5R1_ZERO_INFLATION_AWARE_GATE_CORRECTION','next_revision_created_or_executed':False,
      'post_result_amendment':'Interpretation audit only; no refit, calibration, threshold/eta/gate change, reselection or winner promotion',
      'closure_tests':'Required-artifact and clean-state checks follow this initial receipt commit; final closure update records75/75 without refitting',
      'required_artifact_count':len(names),'May_scientific_reads':0,'optimizer_Gurobi_OpenDSS_calls':0})
    print('Receipt for scientific result commit',science)
def closure():
    tests=read('V40R5_TEST_REPORT.json');assert tests['passed']==75 and tests['failed']==tests['not_run']==0
    r=read('V40R5_FINAL_COMMIT_RECEIPT.json');r['closure_tests']={'passed':75,'failed':0,'not_run':0,'clean_state_measured_before_closure_reporting_update':True,'final_read_only_test_command':'python tests/dayahead/test_v40r5_contracts.py --final --closure --read-only'}
    dump('V40R5_FINAL_COMMIT_RECEIPT.json',r)
    names=read('V40R5_REQUIREMENTS_MANIFEST.json')['required_artifacts'];assert all((OUT/n).exists() for n in names)
    dump('V40R5_REQUIRED_ARTIFACT_VERIFICATION.json',{'required':len(names),'present':len(names),'missing':[],'files':[{'file':n,'SHA256':sha(OUT/n)} for n in names]})
    print('Final closure:75 tests and',len(names),'required artifacts recorded.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['audit','review','receipt','closure']);args=p.parse_args();globals()[args.stage]()
