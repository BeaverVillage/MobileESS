from common11 import *
import numpy as np,pandas as pd
def table(f,cols):
    def fmt(v):
        if pd.isna(v):return '—'
        if isinstance(v,(float,np.floating)):return f'{v:.4f}'
        return str(v).replace('|','/')
    return '| '+' | '.join(cols)+' |\n| '+' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(fmt(v) for v in row)+' |' for row in f[cols].itertuples(index=False,name=None))
def main():
    t=read(ROOT/'TOTAL_SELECTION_RESULT.json');c=read(ROOT/'TAIL_CLASSIFIER_VERDICT.json');a=read(ROOT/'STAGE_A_VERDICT.json');stop=read(ROOT/'STOP_CONDITION_RECEIPT.json')
    s=pd.read_csv(ROOT/'TOTAL_GATING_COMPARISON.csv').set_index('arm').loc['GATE0_L0'];cmp=pd.read_csv(ROOT/'TOTAL_BASE_MODEL_COMPARISON.csv');gating=pd.read_csv(ROOT/'TOTAL_GATING_COMPARISON.csv')
    folds=pd.read_csv(ROOT/'TOTAL_FOLD_METRICS.csv');folds=folds[folds.arm.eq('GATE0_L0')]
    labels=pd.read_csv(ROOT/'FOLD_DISTRIBUTION_SUMMARY.csv');label=labels[labels.field.eq('runtime_seconds')]
    long=pd.read_csv(ROOT/'FOLD_LONG_TAIL_PREVALENCE.csv');prev=long[(long.role.isin(['TRAIN','VALID']))&long.threshold_seconds.isin([14400,43200,86400])]
    shifts=pd.read_csv(ROOT/'FOLD_FEATURE_SHIFT.csv');f4=shifts[(shifts.fold==4)&shifts.type.eq('categorical')]
    tail=pd.read_csv(ROOT/'TAIL_EXPERT_METRICS.csv');short=tail[tail.cohort.eq('le4h')].groupby('weight').agg(N=('N','sum'),reserved_GPUh=('reserved_GPUh','sum'),actual_GPUh=('actual_GPUh','sum')).reset_index()
    short['reservation_change_vs_L0']=short.reserved_GPUh/float(short[short.weight.eq('L0')].reserved_GPUh.iloc[0])-1
    short.to_csv(ROOT/'TAIL_SHORT_RESERVATION_ABLATION.csv',index=False)
    baseref=pd.read_csv(ROOT/'TOTAL_REFERENCE_COMPARISON.csv');v10=baseref[baseref.arm.eq('V10')].iloc[0]
    checkpoints=read(ROOT/'CHECKPOINT_SAMPLE_AUDIT.json')['rows'];nvalid=sum(z['checkpoint_N'] for z in checkpoints if z['role']=='VALID')
    cls=pd.read_csv(ROOT/'TAIL_CLASSIFIER_METRICS.csv');q=pd.read_csv(ROOT/'PREAPRIL_TOTAL_QUEUE_REPLAY.csv')
    worst=lambda z:z.sort_values('coverage_std').iloc[0]
    stable=worst(cmp);rec=pd.read_csv(ROOT/'FOLD_RECENCY_DIAGNOSTIC.csv')
    items=[
      ('Fold4가 왜 어려웠는가?',f"판정은 MIXED다. TRAIN/CAL/VALID runtime 중앙값은 74/25/673초이고 Q90은 8,839/4,831.9/59,862초다. 짧은 CAL의 관계를 STATIC 보정으로 VALID에 이전한 V10은 raw 88.33%에서 39.56%로 악화됐다. 요청 mix, label marginal, 지원 손실 및 공통 exact-x 내 차이가 함께 존재한다. 단일 인과 원인이 입증된 것은 아니다. exact-x 공통 VALID mass {100*a['fold_classifications'][3]['exact_x_common_VALID_mass']:.2f}%, 그 안의 가중 KS {a['fold_classifications'][3]['within_exact_x_weighted_KS']:.4f}다."),
      ('Fold1과 Fold4 문제 원인은 같은가?',"같다고 단정할 수 없다. Fold1은 expanding TRAIN runtime 중앙값56초→VALID3,624초, raw V10부터 coverage66.47%였다. Fold4는 TRAIN74초→VALID673초이지만 특히 CAL25초가 더 짧아 STATIC 보정의 실패가 컸다. Fold1은 요청 지원 손실 기준을 넘지 않았고 fold4는 partition unseen10.36%를 포함한다."),
      ('실제 runtime distribution이 시기별로 얼마나 달라지는가?',table(label,['fold','role','N','Q50','Q90','Q99','mean','zero_rate','censored_rate'])+"\n\n전체 Q10/Q25/Q50/Q75/Q90/Q95/Q99는 FOLD_DISTRIBUTION_SUMMARY.csv에 있다. exact completed subset의 비교이며 censored/unresolved maturity selection 차이를 없앤 causal-population 추정은 아니다."),
      ('>4h/>12h/>24h prevalence가 어떻게 변하는가?',table(prev,['fold','role','threshold_seconds','N','long_N','rate'])+"\n\nrate는 fraction이다. >15m/30m/1h/2h/8h/48h도 FOLD_LONG_TAIL_PREVALENCE.csv에 보존했다."),
      ('requested walltime-runtime 관계가 시기별로 달라지는가?',f"그렇다. runtime/requested walltime CDF의 TRAIN→VALID KS는 "+', '.join(f"fold{int(r.fold)}={r.KS:.4f}" for r in pd.read_csv(ROOT/'FOLD_LABEL_SHIFT.csv').query("field=='runtime_walltime_ratio'").itertuples())+"다. ratio marginal 변화만으로 conditional shift를 선언하지 않고, 9개 raw 요청값 exact cell TRAIN≥50/VALID≥30의 within-cell KS를 별도 비교했다. 관측상 conditional 변화와 일치하는 증거이지 숨은 실행 종류나 archive revision 원인을 식별한 것은 아니다."),
      ('QoS/partition/account mix가 달라졌는가?',table(f4,['field','JS_divergence','total_variation','unseen_rate','rare_rate'])+"\n\n이는 fold4 표다. 모든 fold의 category별 TRAIN/VALID N·share·unseen/rare는 FOLD_CATEGORY_SUPPORT.csv에 있다. array status도 비교했다."),
      ('expanding vs 180/90/60/30-day training 중 무엇이 안정적인가?',f"fold coverage 표준편차만 보면 {stable.arm}가 가장 작다({100*stable.coverage_std:.2f}pp). 하지만 어느 후보도 모든 안전 gate를 통과하지 못했다. 사전 실패 gate 수→pinball→reservation→MAE→std 순서에서 진단 후보 D60_RAW를 선택했다. 최종 배포용 window 검증이 아니다.\n\n"+table(cmp,['arm','Q90_coverage','min_fold_coverage','coverage_std','gt4h_coverage','Q90_pinball','reservation_actual_GPUh'])),
      ('최근 데이터만 쓰는 것이 실제로 generalization을 개선했는가?', "일관되게 개선하지 못했다. 최근30일 label CDF는 fold1·fold4에 더 가깝지만 fold3에서는 오히려 더 멀다. window 비교의 최저 coverage도 모두85% 미만이다. DOES_RECENCY_MATTER는 Stage A에서 INCONCLUSIVE로 고정했다.\n\n"+table(rec,['fold','expanding_KS','recent30_KS','relative_reduction'])),
      ('base total model 중 raw/log/relative 무엇이 나았는가?',f"선택된 D60_RAW의 pooled pinball은 {s.Q90_pinball:.2f}초다. RAW는 T, LOG는 log1p(T), REL은 V8의 log((T+1)/(walltime+1))를 쓴다. 가중치·threshold·global multiplier는 VALID coverage를 맞추려고 조정하지 않았다. 각 window에서 두 분위수300-tree 고정 learner만 사용했다. 모든15 base 후보 실패로 RAW의 일반적 우월성을 주장할 수 없다."),
      ('tail classifier의 >4h recall은?',f"사전 fixed threshold0.5에서 pooled recall {100*c['recall']:.2f}%, precision {100*c['precision']:.2f}%, >12h recall {100*c['gt12h_recall']:.2f}%다. 높은 pooled recall만으로 안전성을 통과시키지 않았다.\n\n"+table(cls,['fold','N','long4_N','ROC_AUC','PR_AUC','recall','precision','gt12h_recall'])),
      ('tail classifier probability는 잘 calibrated되는가?',f"아니다. pooled Brier {c['Brier']:.6f}는 TRAIN prevalence 상수의 {c['TRAIN_constant_Brier']:.6f}보다 나쁘고 skill은 {c['Brier_skill']:.4f}다. pooled ROC-AUC {c['ROC_AUC']:.4f}, PR-AUC {c['PR_AUC']:.4f} 및 prevalence 대비 lift {c['PR_prevalence_lift']:.2f}는 평균적 구분력을 보여주지만 fold3 ROC-AUC {c['min_fold_AUC']:.4f}가 등록 최소0.55 아래다. 요청42절의 'tail classifier cannot meaningfully distinguish long jobs' 중단 조건을 temporal robustness 기준으로 적용했다. 모든 fold가 무구분이라는 주장이 아니다. calibration curve는 fixed10 bins이며 April로 보정하지 않았다."),
      ('tail expert가 >4h coverage를 얼마나 개선했는가?',f"base {100*s.gt4h_coverage:.2f}%에서 가장 높은 smooth L2가 {100*gating.gt4h_coverage.max():.2f}%로 약 {100*(gating.gt4h_coverage.max()-s.gt4h_coverage):.2f}pp 개선했지만85%와 큰 차이가 남았다. tail 전문가의 보편적 안전성 개선은 검증되지 않았다.\n\n"+table(gating,['arm','Q90_coverage','min_fold_coverage','gt4h_coverage','gt12h_coverage','Q90_pinball','reservation_actual_GPUh'])),
      ('long weighting은 short-job reservation을 얼마나 악화시켰는가?', "전체 TRAIN의 tail 가중치 최대4로 제한했다. 아래는 실제 T≤4h job에 unconditional tail Q90 expert를 적용한 진단 비교이며 gating 결과와 구분한다. reservation_change_vs_L0는 상대 증가 fraction이다.\n\n"+table(short,list(short.columns))),
      ('hard gate와 smooth gate 중 어떤 방식이 나았는가?', "둘 다 실패했다. L2에서 smooth가 >4h64.24%로 hard63.59%보다 높고 Q90 pinball4479.25초로 hard4501.37초보다 낮았지만 예약 비율은 더 높았다. Gate0 base만의 pinball4477.36초보다 개선되지 않았고 classifier temporal 실패 때문에 최종 tail 사용을 중단했다. threshold0.5/alpha=p는 TRAIN 전에 등록했다."),
      ('실제 long label을 inference에 사용했는가?', "NO. 역사적으로 cutoff 전에 완결된 TRAIN label만 classifier target과 weight에 썼다. gating은 predicted p_long4만 사용했다. 실제 T>4h는 VALID 결과 집계에만 사용했고 feature에 넣지 않았다. quantile feature 생성은 기존9개 raw field whitelist만 읽는다."),
      ('최종 TOTAL Q90 pooled coverage는?',f"진단 선택 D60_RAW/GATE0_L0의 pre-April coverage는 {100*s.Q90_coverage:.2f}% (N={int(s.N):,})다. 중단 때문에 final provider 학습은 하지 않았으므로 '최종 provider 성능'은 아니다."),
      ('TOTAL 최저 fold coverage는?',f"{100*s.min_fold_coverage:.2f}%로85% 미달이다.\n\n"+table(folds,['fold','N','Q90_coverage','Q90_pinball','Q50_MAE','reservation_actual_GPUh','VALID_censored_N','quantile_repair_N'])),
      ('TOTAL >4h coverage는?',f"{100*s.gt4h_coverage:.2f}% / N={int(s.gt4h_N):,};85% gate 실패다."),
      ('TOTAL >12h/>24h coverage는?',f"각각 {100*s.gt12h_coverage:.2f}% / N={int(s.gt12h_N):,}, {100*s.gt24h_coverage:.2f}% / N={int(s.gt24h_N):,}다. >8h는 {100*s.gt8h_coverage:.2f}%다."),
      ('TOTAL reservation/actual GPUh는?',f"{s.reservation_actual_GPUh:.4f}; W0 대비 {100*(1-s.reservation_to_W0):.2f}% 작아20% 감소 gate만은 통과했다. 양의 실제 runtime에서 median Q90/actual {s.median_Q90_actual_positive_ratio:.2f}, P90 {s.P90_Q90_actual_positive_ratio:.2f}로 짧은 job의 과도한 예약은 남아 있다."),
      ('V10보다 total runtime이 실제로 개선됐는가?',f"일부 지표만 개선됐다. V10 대비 min-fold {100*v10.min_fold_coverage:.2f}%→{100*s.min_fold_coverage:.2f}%, pinball {v10.Q90_pinball:.2f}→{s.Q90_pinball:.2f}초지만 >4h {100*v10.gt4h_coverage:.2f}%→{100*s.gt4h_coverage:.2f}%, >24h {100*v10.gt24h_coverage:.2f}%→{100*s.gt24h_coverage:.2f}%로 악화했다. 연구 provider 검증 실패다. B0/V8/Bconst의 과거 예측은 일부 또는 전체가 retrospective라 선택 기준의 causal baseline으로 사용하지 않았다."),
      ('checkpoint row를 어떻게 생성했는가?',f"read-only generator 감사에서 start+1800*k < known end인 시점만 만들었다. 타깃은 T−elapsed>0이고 모든 완결은 fold cutoff 전에 관측돼 있어야 한다. VALID의 {nvalid:,}개 checkpoint를 검사했다. unresolved remaining label은 만들지 않았다. 생성기 검사만 완료했고 Stage C 모델 학습/점수 산출은 중단했다. future checkpoint count는 feature가 아니다."),
      ('같은 job checkpoint가 TRAIN/VALID 양쪽에 들어갔는가?', "NO. episode ID의 TRAIN/CAL/VALID 역할을 먼저 결정한 뒤 확장했으며 각 fold의 교집합0을 확인했다. 기존 expanding chronology 때문에 과거 VALID job이 완료 후 미래 fold TRAIN으로 들어갈 수는 있다. 이것을 동일 fold 내 label leakage와 혼동하지 않는다."),
      ('elapsed_seconds가 remaining prediction에 얼마나 중요한가?', "V11의 정량 효과는 미평가다. R3_RAW/R4_LOG 및 R3_NO_ELAPSED ablation은 등록했지만 사용자 stop 조건으로 학습하지 않았다. 이미12시간 생존했다는 정보가 신규 제출 때 없다는 물리적 차이는 맞지만 효과 크기를 결과 없이 주장하지 않는다."),
      ('remaining direct model이 total-minus-elapsed보다 나은가?', "미평가. remaining 모델을 학습하지 않았으므로 R0/R1 대비 개선을 주장할 수 없다. REMAINING_MODEL_COMPARISON.csv는 NOT_RUN_USER_STOP_CONDITION 상태를 명시한다."),
      ('remaining direct model이 V9/V10 conditional survival보다 나은가?', "미평가. V9/V10의 기존 수치로 V11의 결과를 대신하지 않았다. 기존 hazard/CDF/finite-support 수치 구현과 산출물은 바이트 그대로 보존했다."),
      ('remaining Q90 coverage는 88–92%인가?', "미평가이므로 통과 아님. REMAINING_Q90_GATE_PASS=FALSE는 fail-closed 상태이며 측정 coverage가0이라는 뜻이 아니다."),
      ('elapsed 0.5–1h와 >12h에서 모두 안정적인가?', "미평가. elapsed0.5–1/1–2/2–4/4–8/8–12/12–24/>24h 및 actual-remaining strata는 등록했지만 성능표를 만들어내지 않았다."),
      ('overrun extension은 감소했는가?', "V11 total-only pre-April stress는 queue gate를 통과하지 못했다. FORECAST 예약과 CAUSAL_CURRENT_SLOT_STRESS를 별도 행으로 보존했다. 완성된 TOTAL+REMAINING V11 시스템의 감소 여부는 미평가다. RUNNING GPU 유지/900초 연장/STAY 규칙을 바꾸지 않았다.\n\n"+table(q[(q.arm=='V11_STOPPED_TOTAL')],['fold','phase','start_lt_H','start_ge_H','reserved_GPUh','actual_GPUh','queue_wait_seconds','overrun_extensions','capacity_violations'])),
      ('April total regression 결과는?', "미실행. Stage B 중단 후 final fit/provider가 없어 April을 열지 않았다. APRIL_EXPOSED_TOTAL_METRICS.csv에는 NOT_RUN 상태만 있다. 기존에 노출된 April의 성격은 EXPOSED_REGRESSION_ONLY로 유지한다."),
      ('April remaining regression 결과는?', "미실행. V11 remaining 모델이 없고 April을 평가하지 않았다. V10의94.12%를 V11 결과로 재사용하지 않았다."),
      ('April2 start<H는 W0/B0/V8/V9/V10/V11 각각 몇 개인가?', "이 V11 실행에서는 재평가하지 않았다. 이전에 확인된 reference는150/47/111/127/91이고 V11은 NOT_RUN이다. 마지막 값을0으로 기록하거나 기존 예측을 V11이라고 부르지 않는다."),
      ('April 결과를 보고 수정했는가?', "NO. 이 실행에서는 April payload를 읽지 않았고 V11 April 결과도 없다. 중단 결정은 pre-April classifier 결과와 사전 판정 기준으로만 내렸다."),
      ('May를 열었는가?', "NO. 파일 payload 조회, 예측, descriptive table, calibration 모두 수행하지 않았다."),
      ('V42 research Runtime provider로 승격 가능한가?', "아니다. TOTAL의 min-fold·>4h·>12h·queue gate 및 classifier temporal 구분력 실패, Stage C/최종 provider 미구현이다. RUNTIME_PROVIDER는 NOT_BUILT 설명만 담는다. 6개 이름의 freeze 파일 중 remaining/provider는 미실행 상태를 동결한 것이며 April 실행 허가가 아니다."),
      ('strict causal provider가 여전히 FALSE인 이유는?', "Kestrel public archive의 requested walltime/GPU/nodes/cores/memory/QoS/partition/account/array descriptor가 최초 submit 당시 immutable 요청값임을 증명할 version authority가 없다. 29 engineered/9 raw 연구 descriptor를 그대로 사용했고 STRICT_CAUSAL_FEATURE_COUNT=0, REQUEST_VERSION_AUTHORITY_FOUND=FALSE다. elapsed는 RUNNING 이후 관측 가능한 값이지만 submit-time 요청 provenance 문제를 해결하지 않는다.")
    ]
    report='# Runtime-vNext11 최종 검토 — 사용자 stop 조건으로 Stage B 뒤 중단\n\n'
    report+='**결론: 비승격, Stage C/최종 provider/April 미실행.** pooled 성능으로 temporal classifier 실패를 가리지 않았다. 요청서42절의 중단 조건과 데이터 확인 전에 등록한 최소 fold AUC0.55 규칙을 적용했다. Pooled AUC0.793이 모든 시기에서의 성공을 뜻하지 않으며 fold3는0.495였다. 판정 문턱을 사후에 낮추지 않았다.\n\n'
    report+=f'기준 {BASE}, PR #82. 기존 v6–v10 과학 파일810개와 manifest5개를 그대로 유지한다. 이번 변경은 docs/runtime_vnext11_total_remaining에 한정된다. V42/CC4/MESS/kernel/optimizer/May를 변경하지 않았다.\n\n'
    report+='Stage A를 완료·동결한 뒤 15개 base window/target 조합(5fold, Q50/Q90), 선택 D60_RAW의 classifier와 L1/L2 expert 및5개 gate 후보를 비교했다. 이 순차 설계는 사전 등록됐으며 모든 window/target/tail 조합을 망라한 탐색은 아니다. 모든 TOTAL 후보가 안전 gate를 실패했다. 이후 작업은 새 모델 학습이 아닌 체크포인트 생성기/ID 분리 감사와 결과 보존뿐이었다.\n\n'
    report+='\n\n'.join(f'## {i}. {question}\n\n{answer}' for i,(question,answer) in enumerate(items,1))
    report+='\n\n## 실행 및 재현 한계\n\nCPU4 고정 learner, 독립 모델 최대2개 동시 학습을 사용했다. GPU trial은 생략했으며 backend를 혼합하지 않았다. 직접 quantile은 cutoff 전 exact completed labels만 학습하므로 administrative censor/maturity selection 한계가 남는다. 모든 window에서 등록한 최소 completed5,000/>4h200/>12h100 지원은 충족했다. 양의 Q50 및 Q90≥Q50 ordering은 등록된 deterministic repair로 처리했고 빈도를 기록했다. V11은 전체 CDF를 정의하지 않으므로 V10 proper NLL을 V11에 붙이지 않는다.\n\n'
    report+='실행 순서: prepare11.py → forensic11.py → train_total11.py → tail11.py → STOP → close_stopped11.py → review11.py → verify_delivery11.py. checkpoint11.py의 생성기만 검사했으며 train_remaining11.py는 미실행 scaffold이고 stop guard가 새 학습을 차단한다. JSON은 exclusive-create이고 완료 연구 디렉터리에서 덮어쓰기 재실행하지 않는다. 후보 base75개 model-pair는 local hash-pinned cache에, 선택 base5개와 tail booster는 FOLD_MODELS에 보존했다. BASE_MODEL_FIT_RECEIPTS.json과 FOLD_MEMBERSHIP_REFERENCE.json을 이용해 재현한다. April 또는 May 데이터 없이 이번까지의 연구를 재현할 수 있다.\n'
    (ROOT/'FINAL_REVIEW_KO.md').write_text(report,encoding='utf-8')
    (ROOT/'README.md').write_text('# Runtime-vNext11: stopped negative result\n\nRead FINAL_REVIEW_KO.md (36 Korean answers), STOP_CONDITION_RECEIPT.json and FINAL_VERDICT.json first.\n\nStage A and Stage B diagnostics completed. User section42 stop triggered by temporally uninformative tail classifier; Stage C, final model fitting, provider construction and April evaluation were not run. Remaining/April CSVs explicitly contain NOT_RUN status, not measurements. RUNTIME_PROVIDER is documentation only. No runtime integration or deployment.\n\nFOLD_MODELS preserves diagnostic total/tail bytes only. Same source-backed limitations and frozen V6–V10 artifacts remain. May unopened.\n',encoding='utf-8')
    print('KOREAN_36_ANSWERS_COMPLETE',len(items),flush=True)
if __name__=='__main__':main()
