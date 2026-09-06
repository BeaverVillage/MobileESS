"""Post-experiment audits and Korean report. Does not alter fitted science."""
from .common import *
from .train import authority,NAMES
from .evaluate import REPORT
import argparse

def link(file,label=None):return f'[{label or file}](<{(OUT/file).as_posix()}>)'
def audit():
    reg,commit=authority();r3=[]
    for row in read('V40R4_V40R3_FREEZE_VERIFICATION.json')['files']:
        actual=sha(R3/row['path']);assert actual==row['SHA256_working'],row['path'];r3.append({'path':row['path'],'SHA256':actual,'unchanged':True})
    start=read('V40R4_START_STATE.json');end={}
    for p,s in start['protected_worktrees'].items():
        h=git('rev-parse','HEAD',cwd=p);st=git('status','--porcelain',cwd=p)
        end[p]={'HEAD':h,'status':st,'HEAD_status_unchanged':h==s['HEAD'] and st==s['status']}
    r2=next(v for p,v in end.items() if 'v40r2_' in p);assert r2['HEAD_status_unchanged']
    paths=git('diff','--name-only',BASE).splitlines()+git('ls-files','--others','--exclude-standard').splitlines()
    assert all(p.startswith(('dayahead/v40r4/','dayahead/artifacts/v40r4_compound_gpuwork_arrival/')) for p in paths)
    dump('V40R4_PROTECTED_SCOPE_DIFF.json',{'BASE':BASE,'preregistration_commit':commit,'only_R4_namespace_changes':True,'paths':paths,
      'R3_final_byte_checks':r3,'R3_all_unchanged':True,'protected_worktree_end':end,'protected_write_operations':0,
      'R2_status':'SUPERSEDED_BY_V40R3','R3_status':'V40R3_FUTURE_GPUWORK_SAFETY_FAIL',
      'initial_index_incident':'Own unpublished R4 first commit initially omitted inherited index entries. Corrected before diagnostics/fitting by index-only tree restoration and amendment. No protected worktree files were changed/deleted. Full record: V40R4_INITIAL_INDEX_CORRECTION.json',
      'parallel_worktree_note':'Any external HEAD/status evolution is disclosed separately; this R4 branch never writes those worktrees'})
    dump('V40R4_MAY_FIREWALL.json',{'scope':'V40R4 execution; prohibited month is May 2025','May_scientific_reads':0,
      'May_target_runtime_status_Actual_reads':0,'May_training_calibration_selection_rows':0,'May_B0_B3_outcome_reads':0,
      'May_path_code_footer_metadata':'NONZERO','metadata_details':['User supplied protocol','git worktree names and inherited path/index metadata','R3 provenance/contract text'],
      'raw_archive_opened':False,'new_unexposed_data_opened':False,'data_source':'Copied, hashed already-exposed pre-May R3 artifacts only',
      'inherited_exposure':'Prior V40P/R2 incidents are not erased; no clean-room claim',
      'initial_index_correction':'Restored git tree/index metadata without checking out or decoding protected scientific payloads',
      'OS_wide_access_monitor_claimed':False})
    ledger=[]
    for name in NAMES:
        fit=read(f'fits/{name}/result.json')
        for r in fit['trials']:ledger.append({'model':name,**{k:v for k,v in r.items() if k not in ['history','development_choices']}})
    rep=read('V40R4_REPRODUCIBILITY.json');ledger.append({'model':'P1','role':'independent_repeat',**{k:v for k,v in rep['repeat_training'].items() if k!='history'}})
    dump('V40R4_COMPUTE_LEDGER.json',{'runs':ledger,'candidate_fit_configuration_runs':sum(r.get('parameter_fits',1)>0 for r in ledger),
      'fit_time_sum_seconds':sum(r['fit_time_seconds'] for r in ledger),'libraries':reg['frameworks'],
      'classical_device':'CPU 4 threads','CCAF_device':rep['repeat_training']['device'],'CCAF_GPU':rep['repeat_training']['GPU'],
      'CUDA_runtime':rep['repeat_training']['CUDA'],'CCAF_AMP':False,
      'CCAF_determinism':reg['CCAF_training'],'scenario_sampling':reg['scenario_numerics'],
      'scenario_deterministic_algorithm_flag':'No explicit enable in scenarios(); default False in fresh convergence/evaluation processes; inherits True after neural training in fit process. Fixed random seeds and observed repetitions are reported, no universal bitwise claim.',
      'scenario_seed':reg['scenario_seed'],'per_day_seed':reg['per_day_seed'],'B6_not_fitted':True,
      'phase0_diagnostics_not_counted_as_forecast_fit':'Intercept count families, body MLE, GPD diagnostics/bootstrap only, all TRAIN before registration',
      'timer_scope':'Per-fit timer includes model fit and parameter prediction/checkpoint output; simulation separately logged, summed times are not total task elapsed time'})
    # Report both inherited development months from saved predictions only.
    # These diagnostics cannot alter the already committed pipelines/comparator.
    from .metrics import aggregate,calibrate
    a=np.load(OUT/'prepared.npz');info=pd.read_parquet(OUT/'inputs/V40R3_LABEL_MATURITY_LEDGER.parquet')
    mask=((info.role=='DEVELOPMENT')&info.stage_maturity_eligible).to_numpy()
    dates=info.operating_day.to_numpy()[mask];y=a['target'][mask];development={}
    for name in NAMES:
        s=read(f'fits/{name}/result.json')['selected'];q=np.load(OUT/'fits'/name/f'trial_{s["trial"]}_development_q.npy')
        cq=q if name=='B0' else calibrate(q,s['provisional_score']) if s['method']=='C1' else q
        rows=[]
        for month in sorted(set(d[:7] for d in dates)):
            ix=np.array([d[:7]==month for d in dates]);rows.append({'month':month,'origins':int(ix.sum()),
              'metrics':aggregate(y[ix],cq[ix],reg['burst_GPUh']),
              'role':'EXPOSED_PROVISIONAL_CALIBRATION_DIAGNOSTIC' if month=='2024-09' else 'EXPOSED_PIPELINE_SELECTION_DIAGNOSTIC'})
        development[name]={'frozen_trial':s['trial'],'frozen_method':s['method'],'months':rows}
    dump('V40R4_DEVELOPMENT_TEMPORAL_DIAGNOSTIC.json',{'models':development,
      'source':'Saved selected-trial development predictions; no new fit or simulation',
      'selection_effect':'NONE: reported after all model/calibration choices and final exposed evaluation',
      'limitations':'Both months were used for CCAF epoch selection; mature September labels also set provisional C1, October selected pipelines. These are exposed diagnostics, not untouched or prequential validation.'})
    print('Protected hashes, May firewall, compute ledger, and development monthly diagnostics recorded.')

def review():
    reg,commit=authority();sel=read('V40R4_METHOD_SELECTION.json');tests=read('V40R4_TEST_REPORT.json')
    assert tests['failed']==tests['errors']==tests['not_run']==0
    pop=read('V40R4_V40R3_TARGET_REPRODUCTION.json');ct=read('V40R4_COUNT_DISTRIBUTION_DIAGNOSTIC.json');st=read('V40R4_SEVERITY_TAIL_DIAGNOSTIC.json')
    tail=read('V40R4_TAIL_THRESHOLD_SELECTION.json');dep=read('V40R4_COUNT_SEVERITY_DEPENDENCE_AUDIT.json');decomp=read('V40R4_V40R3_BURST_FAILURE_DECOMPOSITION.json')
    reports={n:read(f'V40R4_{REPORT[n]}_REPORT.json') for n in NAMES};p=reports['P1'];metric=p['selected'];prob=metric['probabilistic']
    cum=p['cumulative']['selected'];boot=read('V40R4_PAIRED_BOOTSTRAP_SUPERIORITY.json');mc=read('V40R4_MONTE_CARLO_CONVERGENCE.json');repro=read('V40R4_REPRODUCIBILITY.json')
    baseline_primary=reports[sel['strongest_development_baseline']]['selected']['primary']
    lines=[f'- 최종 분류: **{sel["classification"]}**',f'- 선택 모델: **{sel["selected_model"] or "NONE"}**',
      f'- CCAF: **{"PASS" if sel["CCAF_PASS"] else "FAIL"}**',f'- CCAF superiority: **{"YES" if sel["CCAF_superiority"] else "NO"}**',
      f'- 개발 단계 고정 최강 기준모델: **{sel["strongest_development_baseline"]}**',
      '- EVT tail supported: **NO**','- Untouched confirmation: **NO**','',
      'ML은 외생 arriving GPU-service demand를 예측하고 optimizer는 이후 내생 service timing을 결정한다. 이 역할 분리, R3 타깃·코호트·F30 제거·GPU 결측 처리·성숙도·30분 증분 구조를 유지했다. R2는 SUPERSEDED_BY_V40R3, R3는 V40R3_FUTURE_GPUWORK_SAFETY_FAIL이며 원본을 수정하지 않았다.','',
      f'**1. Target reproduction.** 적격 {pop["eligible_cohort_jobs"]:,} jobs, GPU 결측 제외 {pop["missing_GPU_excluded"]:,}, 349개 운영일 기여 {pop["target_contributing_jobs"]:,} jobs / {pop["target_GPUh"]:,.9f} GPUh. 16,752개 30분 구간의 R3 대비 최대 절대 차이는 {pop["max_abs_interval_difference_GPUh"]} GPUh이다(고정 허용오차 1e-7). 발행은 D−1 18:00 fixed AEST=D−1 08:00 UTC이며 다음 운영일 48구간을 예측한다. Z=g×(end−start)/3600을 제출 구간에 전량 배정한다. GPUh는 관측 서비스 proxy이며 FLOPs나 하드웨어 독립 작업량이 아니다.','',
      f'**2. Count distribution.** 성숙 TRAIN 8,016구간에서 N 평균 {ct["stats"]["mean"]:.6f}, 분산 {ct["stats"]["variance"]:.6f}, 분산/평균 {ct["variance_mean_ratio"]:.4f}, zero {ct["zero_rate"]:.4%}. Poisson 예상 zero는 {ct["Poisson_expected_zero_rate"]:.3g}. N의 중앙값/P90/P95/P99/max=2/160/255/476.85/2067. BIC는 NB를 선택했다. ZINB의 추가 zero 확률은 거의 0 경계로 수렴했다. 이는 marginal 진단이며 조건부 예측 성능 보장이 아니다.','',
      f'**3. Severity heavy tail.** TRAIN 양수 jobs {st["positive_severity"]["N"]:,}개, 평균 {st["positive_severity"]["mean"]:.6f}, 중앙값 {st["positive_severity"]["quantiles"]["P50"]:.6f}, P90/P95/P97.5/P99/P99.5=0.972222/2.506750/9.325278/36.212556/56.478211, max 6,145.208889 GPUh. Lognormal이 Gamma보다 낮은 TRAIN BIC를 보였다. Mean-excess, log-severity, Hill 민감도, QQ 자료를 보존했다. Heavy tail을 곧바로 특정 power law의 증명으로 해석하지 않는다.','',
      '**4. Tail threshold.** GPD용 선택 임계값은 없음이다. P1의 비-EVT spliced-lognormal 분기점은 별도로 사전등록한 TRAIN job Q95=2.506750 GPUh다. 이를 EVT가 지지된 threshold로 표현하지 않는다.','',
      '**5. GPD/EVT diagnostic.** 사전 Phase-0 규칙의 support·shape·finite-mean CI·인접 threshold 안정성·KS distance·QQ를 통과한 threshold가 없었다. B6는 EVT_TAIL_NOT_SUPPORTED로 미실행했다.','',
      '| TRAIN quantile | u GPUh | exceedance N | xi | xi 95% CI | sigma | KS | 허용 |','|---|---:|---:|---:|---|---:|---:|---|']
    for r in st['GPD_thresholds']:lines.append(f'| {r["TRAIN_quantile"]:.3f} | {r["threshold_GPUh"]:.6f} | {r["exceedance_N"]:,} | {r["xi"]:.6f} | [{r["xi_CI95"][0]:.6f}, {r["xi_CI95"][1]:.6f}] | {r["sigma"]:.6f} | {r["KS_distance"]:.6f} | FAIL |')
    lines+=['','Q90/Q95의 shape 추정은 finite-mean 안정성을 충족하지 못했고, Q97.5도 인접 xi 차이와 KS 기준에서 실패했다. CI는 운영일 단위 100회 bootstrap이며 고정 threshold 조건부 불확실성이다. Fitted-parameter KS의 잘못된 simple-null p-value를 제시하지 않았다.','',
      f'**6. Count–severity dependence.** 양수 TRAIN 구간에서 Spearman(N,평균 Z)={dep["positive_interval_correlations"]["mean"]["Spearman"]:.6f}, Pearson={dep["positive_interval_correlations"]["mean"]["Pearson"]:.6f}. CCAF는 predicted mu를 severity head에 넣으며 realized future N은 넣지 않는다. 관측 연관성이며 인과 효과가 아니다. 시간대 평균 제거 후 residual ΔW lag1 상관 {dep["residual_cross_interval_correlation_after_TRAIN_hour_mean"]["1"]:.6f}가 남으므로 조건부 독립 시나리오의 joint daily 해석에는 한계가 있다.','',
      '**7. January 12 misses.** R3의 102/114 coverage에서 빠진 12개는 COUNT_DRIVEN 8, SEVERITY_DRIVEN 2, MIXED 1, UNRESOLVED 1이다. TRAIN N Q95=255, 양수 구간 max Z Q95=146.529889를 사용했다. 다음 분류는 설명용이며 배포 규칙이 아니다.','',
      '| 일자 | slot | ΔW GPUh | N | 최대 Z GPUh | top1 share | top3 share | 분류 |','|---|---:|---:|---:|---:|---:|---:|---|']
    for r in decomp['January_misses']:lines.append(f'| {r["day"]} | {r["slot"]} | {r["total"]:.3f} | {r["count"]} | {r["max"]:.3f} | {r["top1_share"]:.2%} | {r["top3_share"]:.2%} | {r["classification"]} |')
    lines+=['','모든 R3 burst 구간의 mean/median/max, top3, TRAIN-tail 초과 수 및 percentile은 '+link('V40R4_V40R3_BURST_FAILURE_DECOMPOSITION.csv','전체 분해 CSV')+'에 있다.','',
      '**8. Candidate registry.** B0 ZERO; B1 causal seasonal; B2 R3-style aggregate Hurdle LightGBM 재학습; B3 Tweedie aggregate; B4 parametric NB+Lognormal; B5 ML NB+Lognormal; B6 body+EVT 미실행; P1 CCAF NB+tail-exceedance+spliced-lognormal. 두 LR/설정 탐색은 B2/B3/B4/B5/P1에 동일하게 2개이며 P1만 모델 선택용으로 더 많은 설정을 탐색하지 않았다. B0/B1은 parameter fitting이 없다. 여기의 B0–B6는 ML 비교 모델 ID이며 금지된 전기 B0–B3 실험을 실행한 것이 아니다.','',
      '**9. Count model results.** 아래는 raw component diagnostics다. B0–B3 aggregate 모델에는 실제 job-count head가 없으므로 NOT_APPLICABLE로 명시했다.','',
      '| 모델 | Count MAE | RMSE | bias | mean log likelihood | 관측/예측 zero | P90/P95 coverage | large-count recall |','|---|---:|---:|---:|---:|---|---|---:|']
    for name in ['B4','B5','P1']:
        r=reports[name]['count_metrics'];lines.append(f'| {name} | {r["MAE"]:.4f} | {r["RMSE"]:.4f} | {r["bias"]:.4f} | {r["mean_predictive_log_likelihood"]:.4f} | {r["actual_zero_rate"]:.2%} / {r["predicted_zero_rate"]:.2%} | {r["P90_coverage"]:.2%} / {r["P95_coverage"]:.2%} | {r["large_count_recall_using_predicted_P90"]:.2%} |')
    lines+=['','NB deviance·zero Brier도 count metrics에 저장했다. 최종 모델 선택은 count 점수가 아니라 aggregate GPUh 점수로 한다. P1은 pooled count P90 coverage가 높아도 실제 large-count 125구간의 recall은 0%다. 큰 arrival count를 구분하는 능력이 부족했음을 보여준다.','',
      '**10. Severity results.** 같은 인과 구간 문맥으로 모든 미래 jobs의 분포를 예측한다. 미래 GPU/walltime/partition/QoS/hardware/cores/memory는 predictor가 아니다. Lognormal 충분통계를 통해 개별 job likelihood를 보존했다.','',
      '| 모델 | log MAE | median abs log error | Q90 pinball | Q90 coverage | tail probability error | TRAIN top1% Q90 coverage |','|---|---:|---:|---:|---:|---:|---:|']
    for name in ['B4','B5','P1']:
        r=reports[name]['severity_metrics'];lines.append(f'| {name} | {r["log_MAE"]:.6f} | {r["median_absolute_log_error"]:.6f} | {r["Q90_pinball"]:.6f} | {r["Q90_coverage"]:.2%} | {r["exceedance_probability_calibration_error"]:.6f} | {r["top1_unconditional_Q90_coverage"]:.2%} |')
    lines+=['','Tail conditional quantile pinball·coverage와 conditional log likelihood를 별도 저장해 body 성능에 tail 실패가 가려지지 않도록 했다. P1의 u 초과 예측 확률 평균은 5.0126%, 실제는 20.3522%였다. Tail-conditional Q90 coverage는 96.5216%지만 TRAIN top-1% severity 2,950 jobs의 unconditional Q90 coverage는 0%다. 이 지표들을 함께 보면 tail 발생 확률의 과소예측과 severity 분포 변화가 aggregate burst 실패의 주요 설명이라는 해석이 가능하다. 이는 사후 진단이며 인과 효과나 새 모델 선택 근거로 사용하지 않았다.','',
      '**11. Aggregate results.** 표는 DEVELOPMENT에서 고정한 trial/calibration 조합만 대상으로 한다. C0는 무보정, C1은 positive-CAL log-ratio 보정이다.','',
      '| 모델 | 고정 보정 | Primary | 양수 WAPE | 전체 coverage | 양수 coverage | burst coverage | 안전 |','|---|---|---:|---:|---:|---:|---:|---|']
    for name,r in reports.items():
        e=r['selected'];pp=e['probabilistic'];lines.append(f'| {name} | {r["calibration"]["frozen_method"]} | {e["primary"]:.6f} | {e["positive_point"]["WAPE"]:.2%} | {pp["overall"]["coverage"]:.2%} | {pp["positive"]["coverage"]:.2%} | {pp["burst"]["coverage"]:.2%} | {"PASS" if r["safety"]["all_pass"] else "FAIL"} |')
    lines+=['','B6: EVT_TAIL_NOT_SUPPORTED, 미실행이며 성적을 만들어 넣지 않았다. B4는 January/February point WAPE가 각각 2,450.04%/2,480.81%로 catastrophic gate에도 실패했다. 높은 aggregate 오차를 누락하거나 결과를 본 후 예측 상한을 추가하지 않았다.','',
      '**12. Raw Q90 coverage.** 아래 raw/C1 열은 모든 후보의 진단 비교이며 최종 결과를 보고 calibration 종류를 바꾸지 않았다. C1은 전체 aggregate CDF의 변환이므로 Q50도 바뀐다. 원시 compound sum과 보정된 aggregate scenarios를 구분한다.','',
      '| 모델 | Raw primary | C1 primary | Raw 전체 coverage | C1 전체 coverage | C1 score (log units) | C1 overconservative |','|---|---:|---:|---:|---:|---:|---|']
    for name,r in reports.items():
        c=r['calibration'];lines.append(f'| {name} | {c["C0"]["primary"]:.6f} | {c["C1"]["primary"]:.6f} | {c["C0"]["probabilistic"]["overall"]["coverage"]:.2%} | {c["C1"]["probabilistic"]["overall"]["coverage"]:.2%} | {c["C1_log_score"]:.6f} | {c["C1_gate"]["OVERCONSERVATIVE_CALIBRATION"]} |')
    lines+=['',f'**13. Calibrated Q90 coverage.** P1 C1 전체/양수/burst coverage는 {p["calibration"]["C1"]["probabilistic"]["overall"]["coverage"]:.6%}/{p["calibration"]["C1"]["probabilistic"]["positive"]["coverage"]:.6%}/{p["calibration"]["C1"]["probabilistic"]["burst"]["coverage"]:.6%}, primary는 {p["calibration"]["C1"]["primary"]:.9f}다. Burst gate는 여전히 실패한다. 최종 고정 pipeline은 {p["calibration"]["frozen_method"]}이며 C1 결과로 사후 교체하지 않았다.','',
      f'**14. Positive coverage.** P1 고정 pipeline은 {prob["positive"]["coverage"]:.6%}; 허용 범위는 90–95%다.','',
      f'**15. Burst coverage.** P1 {prob["burst"]["coverage"]:.6%}, N={prob["burst"]["N"]}; 허용 범위는 90–97.5%다. Burst 기준 441.777542 GPUh는 R3 TRAIN에서 고정한 그대로다.','',
      '**16. Monthly stability.** 아래는 P1 결과다. 모든 모델의 December/January/February primary/coverage/burst miss/WAPE/bias는 temporal report에 별도 저장했다. September/October도 '+link('V40R4_DEVELOPMENT_TEMPORAL_DIAGNOSTIC.json','개발 월별 진단')+'에 보존했다. 해당 두 달은 epoch/calibration/pipeline 선택에 사용된 노출 자료이므로 미노출·순차적 검증이라고 주장하지 않는다. N<100의 월별 burst는 숫자를 기록하되 INSUFFICIENT_SUPPORT로 처리한다.','',
      '| 월 | Primary | 전체 coverage | burst N | burst coverage | missed burst GPUh | WAPE | bias GPUh |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in p['safety']['temporal']:
        e=r['metrics'];lines.append(f'| {r["month"]} | {e["primary"]:.6f} | {e["probabilistic"]["overall"]["coverage"]:.2%} | {r["burst_N"]} | {r["burst_coverage"]:.2%} | {e["missed_burst_GPUh"]:.3f} | {e["point"]["WAPE"]:.2%} | {e["point"]["bias"]:.3f} |')
    lines+=['',f'**17. Calibration error.** P1 전체/양수/burst 절대 오차는 각각 {100*prob["overall"]["calibration_error"]:.4f}/{100*prob["positive"]["calibration_error"]:.4f}/{100*prob["burst"]["calibration_error"]:.4f} percentage points다. Coverage가 90%를 넘는 것만으로 우수하다고 판정하지 않는다.','',
      f'**18. Positive normalized Q90 pinball.** P1 {metric["primary"]:.9f}; 과학적 유용성의 최소 기준은 ZERO의 0.9 미만이다.','',
      f'**19. Overprediction.** P1 고정 pipeline의 Q90 overprediction 합 {metric["overprediction_GPUh"]:,.6f} GPUh, underprediction 합 {metric["underprediction_GPUh"]:,.6f} GPUh.','',
      f'**20. Missed burst.** P1 {metric["missed_burst_GPUh"]:,.6f} GPUh, captured fraction {metric["captured_burst_fraction"]:.4%}, mean shortfall {metric["mean_burst_shortfall_GPUh"]:.6f} GPUh. Worst20 및 모든 miss의 COUNT/SEVERITY/MIXED/UNRESOLVED 분류는 개별 candidate report에 있다.','',
      f'**21. Cumulative WAPE.** P1 {cum["WAPE"]:.6%}. 각 시나리오의 비음수 increments를 먼저 합산하고 누적량의 quantile을 계산했다. Marginal Q90들의 합을 true cumulative Q90이라고 부르지 않는다. 단, 조건부 독립 시나리오 law 자체의 적합성은 별도 한계다.','',
      f'**22. Daily total.** P1 MAE {cum["daily_total_MAE_GPUh"]:,.6f} GPUh, bias {cum["daily_total_bias_GPUh"]:,.6f} GPUh; 최대 누적 underforecast {cum["maximum_cumulative_underforecast_GPUh"]:,.6f} GPUh.','',
      f'**23. Horizon crossing.** P1={cum["horizon_crossing_count"]}. 모든 모델에 비음수 scenario increments를 적용했고 각 누적 quantile의 시간 단조성을 검사했다.','',
      f'**24. Strongest baseline.** {sel["strongest_development_baseline"]}를 October DEVELOPMENT에서 고정하고 commit {boot["baseline_commit"]}에 저장한 다음 최종 노출 비교를 시작했다. DEVELOPMENT에서 안전 적격 baseline은 없었으며 B2는 비교 기준으로만 고정됐다. 최종 B2 primary {baseline_primary:.9f} 대비 P1 {metric["primary"]:.9f}의 수치상 차이는 {baseline_primary-metric["primary"]:.9f}다. 양측 모두 안전 실패이므로 우월성 근거로 해석하지 않는다. September provisional calibration은 October 시작 전에 성숙한 label만 사용했다. 최종 C1 score는 November CAL에서만 계산했다.','',
      f'**25. Bootstrap.** 상태 {boot["status"]}. '+(f'Δ={boot["delta"]:.9f}, 95% CI=[{boot["CI95"][0]:.9f}, {boot["CI95"][1]:.9f}], 5,000회 paired circular 7-day blocks.' if boot['CI95'] is not None else 'CCAF가 안전/보정 gate를 통과하지 못했으므로 사전 규칙에 따라 실행하지 않았다. CI를 사후 계산해 종합 우위처럼 제시하지 않는다.'),'',
      f'**26. Selection.** {sel["selected_model"] or "NONE"}; {sel["classification"]}. Authority→temporal safety/calibration 및 MC→primary→burst miss→cumulative WAPE→단순성 순서를 적용했다. 안전에 실패한 모델은 점수가 좋아도 선택하지 않는다.','',
      '**27. Confirmation.** TRUE_CONFIRMATORY_AVAILABLE=NO. R3의 모든 과거 구간은 이미 노출되어 DEVELOPMENT/STRESS이며 미노출 확인으로 이름을 바꾸지 않았다. 최대 긍정 표현은 PREVALIDATED다.','',
      '**28. May.** 2025년 5월 scientific reads=0. 새 raw archive 및 미노출 기간을 열지 않았다. User protocol, git 경로/index, R3 provenance의 metadata 접근은 NONZERO다. 과거 V40P/R2 노출 이력은 지우지 않았다.','',
      f'**29. Tests/compute.** Final {tests["passed"]}/{tests["tests"]} PASS, 실패·오류·미실행 0. Synthetic gradient 검사는 optimizer step 없이 했다. 테스트 PASS와 모델 safety PASS를 구분한다. Monte Carlo는 10,000개로 고정했고 TRAIN/CAL 24개 문맥에서 1,000/2,500/5,000/10,000 및 독립 10,000개를 비교했다. 수렴 gate 결과: '+', '.join(f'{n}={"PASS" if r["convergence_pass"] else "FAIL"}' for n,r in mc['models'].items())+'.','',
      f'CCAF 독립 동일-seed 학습 2회(원본+재현)의 예측 max/mean 차이는 {repro["prediction_max_difference_GPUh"]:.9f}/{repro["prediction_mean_difference_GPUh"]:.9f} GPUh, development raw primary는 {repro["primary_original"]:.9f}/{repro["primary_repeat"]:.9f}다. 더 좋은 재현을 선택하지 않았다. GPU bitwise 동일성을 일반적으로 주장하지 않는다. 장치·CUDA·library 버전·seed·threads·epoch·실제 fit time은 '+link('V40R4_COMPUTE_LEDGER.json','compute ledger')+'에 있다. 추가 결과 검증의 첫 실행에서 날짜 object-array 로더 오류 1건이 발생했다. 자체 생성 NPZ의 문자열 읽기만 정정 후 63개를 재실행했으며 모델/평가 결과는 변경하지 않았다. 최초 실행과 정정 기록도 보존했다.','',
      '**30. Protected scope.** 변경은 R4 두 namespace만이다. R3 source/artifact 234파일의 초기 byte hash를 종료 시점까지 확인했다. R2는 재개·학습·merge/reuse·수정·삭제하지 않았다. R3의 SAFETY_FAIL 분류와 V40S/S2를 변경하지 않았다. 초기 R4 index 누락은 분석 전 index-only 복구 후 자체 미공개 커밋을 정정했고 원본 worktree 파일은 삭제되지 않았다. 첫 타깃 시각 정밀도 오류도 진단 전에 중단·정정했으며 재검증 오차는 0이다. 두 기술 정정 기록을 숨기지 않았다.','',
      '**31. Holds.** production q=UNCHANGED; PF=0.95; Q control=NO; electrical regeneration=HOLD; electrical B0/B1/B2/B3=NO; FULL_MAY=NO; optimizer=NO. V40S2 integration도 하지 않았다.','',
      f'시작 receipt {BASE}, V40R3 scientific {SCI}, V40R4 preregistration **{commit}**. '+link('V40R4_FINAL_COMMIT_RECEIPT.json','최종 연구 및 receipt 기록')+'.',
      '',link('V40R4_SCI_BENCHMARK_REVIEW.md','문헌 근거')+' · '+link('V40R4_PREREGISTRATION.json','사전등록')+' · '+link('V40R4_SAFETY_GATE_TABLE.json','모델별 안전 gate')]
    (OUT/'V40R4_FINAL_REVIEW.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    print('Korean final review written.')

def receipt():
    reg,pre=authority();assert not git('status','--porcelain')
    research=git('rev-parse','HEAD');names=read('V40R4_REQUIREMENTS_MANIFEST.json')['required_artifacts'];assert len(names)==46
    assert [n for n in names if not (OUT/n).exists()]==['V40R4_FINAL_COMMIT_RECEIPT.json']
    sel=read('V40R4_METHOD_SELECTION.json');t=read('V40R4_TEST_REPORT.json')
    checks=[]
    for p in (OUT/'fits').rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(ROOT).as_posix();b=subprocess.check_output(['git','show',research+':'+rel],cwd=ROOT)
        gitsha=hashlib.sha256(b).hexdigest();working=sha(p)
        if p.suffix not in ['.txt','.json']:assert working==gitsha
        checks.append({'path':rel,'working_SHA256':working,'commit_SHA256':gitsha,'same_bytes':working==gitsha})
    dump('V40R4_FINAL_COMMIT_RECEIPT.json',{'BASE':BASE,'V40R3_scientific':SCI,'preregistration_commit':pre,
      'development_baseline_commit':read('V40R4_PAIRED_BOOTSTRAP_SUPERIORITY.json')['baseline_commit'],'final_research_commit':research,
      'receipt_commit':'Separate following commit containing this receipt; no self-referential hash embedded',
      'resolve_receipt_commit':'git log -1 --format=%H -- dayahead/artifacts/v40r4_compound_gpuwork_arrival/V40R4_FINAL_COMMIT_RECEIPT.json',
      'classification':sel['classification'],'selected_model':sel['selected_model'],'tests':{k:t[k] for k in ['tests','passed','failed','errors','not_run']},
      'required_artifact_count':46,'May_scientific_reads':0,'protected_scope_unchanged_by_R4':True,
      'fit_artifact_checks':checks,'text_normalization_note':'LightGBM text files may be CRLF in working tree and LF in commit; both hashes disclosed. Prediction/model binaries must match.',
      'holds':reg['holds']})
    dump('V40R4_REQUIRED_ARTIFACT_VERIFICATION.json',{'required':46,'present':46,'missing':[],
      'files':[{'file':n,'SHA256':sha(OUT/n)} for n in names],'research_commit':research,'receipt_follows_research_commit':True})
    print('Receipt written for research commit',research)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['audit','review','receipt']);args=p.parse_args()
    {'audit':audit,'review':review,'receipt':receipt}[args.stage]()
