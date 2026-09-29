from common import *

def main():
    c=pd.read_csv(ROOT/'FINAL_RUNTIME_MODEL_COMPARISON.csv').set_index('Model');sel=read(ROOT/'FINAL_SELECTION_FREEZE.json')
    # This finalizer deliberately refuses to invent a deployment alpha for a positive result.
    assert sel['SELECTED_RUNTIME_MODEL']=='NONE'
    flags=dict(NO_NEW_RUNTIME_TRAINING=True,RUNTIME_RATIO_UNIT='seconds',GPU_WEIGHTED_RATIO_USED_FOR_SELECTION=False,GPUH_RATIO_USED_FOR_SELECTION=False,
        QUANTILE_ONLY_INTERFACE=True,V9_FULL_DISTRIBUTION_PROMOTED=False,SELECTED_RUNTIME_MODEL='NONE',SELECTED_RUNTIME_INTERFACE='NONE',SELECTED_ALPHA=None,
        SELECTED_Q50_MAE_HOURS=None,SELECTED_RAW_Q90_COVERAGE=None,SELECTED_GT12H_RAW_Q90_COVERAGE=None,SELECTED_Q50_TIME_RATIO=None,SELECTED_Q90_TIME_RATIO=None,
        SELECTED_OPERATIONAL_COVERAGE=None,SELECTED_MIN_FOLD_OPERATIONAL_COVERAGE=None,SELECTED_OPERATIONAL_TIME_RATIO=None,
        OPERATIONAL_RATIO_BELOW_1P2=False,OPERATIONAL_RATIO_BELOW_1P5=False,OPERATIONAL_RATIO_BELOW_2P0=False,
        MAY_RUNTIME_LABELS_OPENED=False,APRIL_USED_FOR_SELECTION=False,RADDIT_RETRAINED=False,CC4_CHANGED=False,V42_CHANGED=False,V42_EXECUTED=False,OPENDSS_RUN=False,
        COMMON_POPULATION_VERIFIED=True,ALPHA_SELECTED_FROM_CAL_ONLY=True,RUNTIME_SELECTION_FROZEN=True)
    write('FINAL_FLAGS.json',flags)
    write('FINAL_VERDICT.json',dict(time=now(),status='COMPLETED_NEGATIVE_SELECTION',selected='NONE',
        conclusion='사전 고정한 CAL-only Q50–Q90 보정은 6개 후보에서 1.x 시간 비율과 fold별 명목 90% 신뢰도를 함께 확립하지 못했다. 새로운 Runtime 모델/운영 duration은 승격하지 않는다.',
        scope='30 candidate-folds, 21 alpha values each on CAL; one frozen alpha per VALID fold; 230237 common exact-matured jobs. No scheduler/resource campaign.',
        ratio_range=[float(c.TIME_RATIO_OP.min()),float(c.TIME_RATIO_OP.max())],best_pooled_coverage=float(c.OP_coverage.max()),
        does_not_prove=['Runtime intrinsically random','Runtime forecasting impossible','semantic/current-state features useless','all calibration architectures impossible'],
        distinction='Q50 MAE assesses median accuracy; raw Q90 assesses upper-bound reliability; alpha duration is not Q90 when alpha<1. Time ratio is not GPU reservation ratio.',
        historical_results='All V6–V16 negative gates and source evidence preserved; no full-distribution defect repaired.',flags=flags))
    def values(col,percent=False):return '; '.join(f'{a}: {100*r[col]:.2f}%' if percent else f'{a}: {r[col]:.4f}' for a,r in c.iterrows())
    def pct(v):return f'{100*v:.2f}%'
    table='| Model | Q50 MAE [h] | Raw Q90 [%] | >12h Raw Q90 [%] | Q50 time [x] | Q90 time [x] | α (fold 1→5) | OP coverage [%] | OP time [x] |\n|---|---:|---:|---:|---:|---:|---|---:|---:|\n'
    for a,r in c.iterrows():table+=f'| {a} | {r.Q50_MAE_hours:.3f} | {100*r.Q90_coverage:.2f} | {100*r.GT12H_Q90_coverage:.2f} | {r.TIME_RATIO_Q50:.3f} | {r.TIME_RATIO_Q90:.3f} | {r.Selected_Alpha_by_fold} | {100*r.OP_coverage:.2f} | {r.TIME_RATIO_OP:.3f} |\n'
    med=pd.read_csv(ROOT/'PER_JOB_RATIO_DISTRIBUTION.csv');med=med[med.fold.eq('POOLED')]
    median=lambda q:'; '.join(f'{r.Model}: {r["median"]:.4f}' for _,r in med[med['quantile']==q].iterrows())
    d1=c.loc['V9_D1_ROLLING14'];v13=c.loc['V13_EXPANDING_S4'];normal=c.loc['V9_D2_NORMAL_1P5_NONE'];extreme=c.loc['V9_D2_EXTREME_1P0_NONE'];low=c.loc['V9_D2_NORMAL_1P0_NONE']
    answers=[
      ('Runtime 출력 단위는?', '초(seconds)다. MAE는 초와 시간으로 함께 보고한다.'),
      ('주 비율을 초로 측정한 이유는?', '예측 대상과 같은 단위로 합산한 sum(predicted seconds)/sum(actual seconds)로 모델의 시간상 보수성을 측정한다. 개별 작업 비율의 평균·중앙값과 다르다.'),
      ('GPUh를 선택에 사용했는가?', '아니다. 주 계산 입력에서 GPU/node 열을 제거했고, 임의 GPU 가중치 변경에도 선택이 불변인지 테스트했다.'),
      ('후보별 aggregate Q50 time ratio는?',values('TIME_RATIO_Q50')),
      ('후보별 aggregate Q90 time ratio는?',values('TIME_RATIO_Q90')),
      ('작업별 Q50/actual 중앙값은?',median('q50')),
      ('작업별 Q90/actual 중앙값은?',median('q90')+'; T=0인 1,290행은 개별 비율에서 제외했다. 나머지 228,947행의 Q25/Q75/Q90/진단용 평균도 CSV에 있다. 0행은 aggregate 합·MAE·coverage에서는 유지했다.'),
      ('Q50 MAE [h]는?',values('Q50_MAE_hours')),
      ('Raw Q90 coverage는?',values('Q90_coverage',True)),
      ('>12h raw Q90 coverage는?',values('GT12H_Q90_coverage',True)),
      ('운영 duration 공식은?', 'T_op = Q50 + α(Q90−Q50), 0≤α≤1. α<1일 때 Q90라고 부르지 않으며 CALIBRATED_OPERATIONAL_RUNTIME이다. 15분 반올림도 하지 않는다.'),
      ('새 ML을 학습했는가?', '아니다. V9 CAL 저장 quantile과 V13 동결 모델의 CAL 추론만 사용했다. V13은 저장된 VALID 32행/fold의 추론을 비트 단위 재현했다. fit 호출 금지 guard를 적용했다.'),
      ('α grid는?', '0.00, 0.05, …, 1.00의 21개 값이다. 6×5×21=630개 CAL 조합을 사전 고정했다.'),
      ('α를 VALID에서 골랐는가?', '아니다. CAL에서 coverage≥90% 중 최소 시간 비율을 택했다. 불가능하면 최대 coverage, 동일하면 최소 시간 비율·최소 α를 택했다. 30개 α를 SHA로 동결한 후 VALID 운영 지표를 계산했다. 기존 raw VALID 결과가 이미 알려진 연구라는 점은 공개한다.'),
      ('May를 사용했는가?', '아니다. April/May labels를 새로 디코딩하거나 선택에 사용하지 않았다. 기존 evidence 보존은 byte hash 검사다.'),
      ('90% 목표를 85%로 바꿨는가?', '아니다. α 보정과 최종 판정 모두 90% 명목 기준을 유지했다. 최종 선택은 pooled 및 모든 fold≥90%라는 보수적 규칙을 CAL/운영 VALID 실행 전에 고정했다.'),
      ('후보별 α는?', '; '.join(a+': '+r.Selected_Alpha_by_fold for a,r in c.iterrows())+'. 순서는 fold 1→5이며 단일 평균 α를 만든 적 없다.'),
      ('VALID 운영 coverage는?',values('OP_coverage',True)),
      ('최저 fold 운영 coverage는?',values('min_fold_OP_coverage',True)),
      ('>12h 운영 coverage는?',values('GT12H_OP_coverage',True)),
      ('운영 시간 비율은?',values('TIME_RATIO_OP')),
      ('<1.2x가 나왔는가?', '아니다. 모든 후보가 2배보다 컸다. 낮은 Q50 하한만으로 1.2배를 달성했다고 주장하지 않는다.'),
      ('<1.5x가 나왔는가?', '아니다. 이 CAL-only grid에서 실측되지 않았다. 모든 보정법의 불가능성을 증명한 것은 아니다.'),
      ('<2.0x가 나왔는가?',f'아니다. 최소는 진단 대조군 D2 normal1.0의 {low.TIME_RATIO_OP:.4f}배이며 coverage {pct(low.OP_coverage)}로 심각한 undercoverage도 남는다.'),
      ('Q50 floor에서 exact1.0x는 가능한가?', 'D1 2.0465, extreme1.0 1.3473, D3 1.7567, V13 2.1580은 하한만으로 불가능하다. normal1.5 0.5474, normal1.0 0.6513은 하한이 배제하지 않을 뿐, 90% 신뢰도·grid에서 실현 가능하다는 뜻이 아니다. 특히 D1/V13은 α≥0이면 2배 미만도 구조적으로 불가능하다.'),
      ('Q50 MAE 최선은?', f'D2 normal1.5: {normal.Q50_MAE_hours:.4f}시간이다.'),
      ('>12h coverage 최선은?', f'Raw Q90는 D2 extreme1.0 {pct(extreme.GT12H_Q90_coverage)}, 보정 후는 D1 {pct(d1.GT12H_OP_coverage)}다. 서로 다른 질문이다.'),
      ('운영 비율 최저는?', f'전체 진단 포함 normal1.0 {low.TIME_RATIO_OP:.4f}; primary만 보면 normal1.5 {normal.TIME_RATIO_OP:.4f}다. 신뢰도 통과를 뜻하지 않는다.'),
      ('정확도·tail·최저 비율의 최선이 같은가?', '아니다. 위 26–28번처럼 서로 다른 후보와 평가 역할이다.'),
      ('D1이 Pareto에 남는가?', '그렇다. 5개 primary 모두 5축 Pareto에 남는다. D1은 높은 최저 fold·운영 tail coverage와 큰 시간 비율의 trade-off다. Pareto membership은 안전성 통과가 아니다.'),
      ('normal1.5가 D1을 이겼는가?', f'MAE {normal.Q50_MAE_hours:.3f} vs {d1.Q50_MAE_hours:.3f}h, 시간 비율 {normal.TIME_RATIO_OP:.3f} vs {d1.TIME_RATIO_OP:.3f}로 낮지만 최저 fold {pct(normal.min_fold_OP_coverage)} vs {pct(d1.min_fold_OP_coverage)}, >12h {pct(normal.GT12H_OP_coverage)} vs {pct(d1.GT12H_OP_coverage)}로 낮다. 단일 우승으로 볼 수 없다.'),
      ('extreme1.0이 D1을 이겼는가?', f'Pooled {pct(extreme.OP_coverage)}와 시간 비율 {extreme.TIME_RATIO_OP:.3f}는 유리하지만 최저 fold {pct(extreme.min_fold_OP_coverage)}와 >12h {pct(extreme.GT12H_OP_coverage)}는 D1보다 낮다. 공동 지배하지 않는다.'),
      ('D3는 경쟁력이 있는가?', 'Pareto에는 남지만 운영 3.6421배, pooled89.84%, min-fold72.81%, >12h65.80%다. D1보다 저렴한 시간 합과 약한 tail/temporal reliability의 trade-off이며 선택되지 않았다.'),
      ('V13의 장점은?', f'D1보다 운영 시간 비율이 {v13.TIME_RATIO_OP:.3f} vs {d1.TIME_RATIO_OP:.3f}로 작다. 그러나 MAE {v13.Q50_MAE_hours:.3f}h, >12h {pct(v13.GT12H_OP_coverage)}, min-fold {pct(v13.min_fold_OP_coverage)}로 악화된다. D1보다 일괄 우월하지 않다.'),
      ('normal1.0은 단순 underprediction인가?', f'낮은 비율에 raw {pct(low.Q90_coverage)}, 운영 {pct(low.OP_coverage)}, >12h 운영 {pct(low.GT12H_OP_coverage)}가 동반된다. 안전한 sharpness로 해석할 수 없다. 모든 오차의 원인을 단일 메커니즘으로 단정하지는 않는다.'),
      ('V9 zero-support를 고쳤는가?', '아니다. 기존 full-distribution 결함은 남는다.'),
      ('그런데 V9 quantile은 왜 비교할 수 있는가?', '저장된 유한·비음수·순서 일치 Q50/Q90 값의 경험적 정확도와 coverage는 별도로 검증할 수 있다. full-density 적합성을 인정한다는 뜻은 아니다.'),
      ('scheduler가 full distribution을 사용하는가?', '아니다. 이번에는 scheduler 자체도 실행하지 않았다. 후보 인터페이스는 초 단위 Q50/Q90와 duration scalar뿐이다.'),
      ('submission metadata를 observable로 간주했는가?', '그렇다. 사용자가 승인한 historical proxy 가정이다. immutable initial-submit byte receipt가 있다는 주장은 하지 않는다.'),
      ('그 가정은 RADDiT 때문인가?', '아니다. RADDiT 이전부터 존재한 역사적 archive/version 문제다. 그 provenance 부족만으로 후보를 기각하지 않았다.'),
      ('RADDiT를 재학습했는가?', '아니다. 신규 의미 특징·embedding·external telemetry 탐색도 하지 않았다.'),
      ('CC4를 변경했는가?', '아니다. T0/B0와 다른 CC4 연구 후보도 그대로 보존했다.'),
      ('V42를 실행했는가?', '아니다. PR93 canary/A1/M1/A2/M2/OpenDSS/IEEE123/IEEE8500도 실행하지 않았다.'),
      ('주 선택 어디에도 GPU weighting이 있었는가?', '없다. sum T, sum Q50, sum Q90, sum T_op 및 작업별 동일 가중 coverage만 사용했다.'),
      ('GPUh는 downstream 진단으로만 남는가?', '그렇다. 수정 지시 이전의 GPU 기반 예비 감사는 .local/superseded_shared_reserve에 보존했으며 선택·논문 주 표에 들어가지 않는다. 공유 reserve fitting/queue replay는 시작하지 않았다.'),
      ('정확한 선택 모델은?', 'NONE. 이전 과학적 negative result를 바꾸지 않았고, 새 duration-interface 판정에서도 선택 후보가 없다.'),
      ('정확한 최종 α는?', 'null. 모든 candidate-fold α는 표에 있지만 운영 승격용 단일 α는 없다.'),
      ('V42가 사용할 정확한 공식은?', '연구 후보 공식은 Q50+α(Q90−Q50)지만 이번에 승인된 모델/α는 없다. V42에 적용하거나 현재 provider를 바꾸지 않는다.'),
      ('논문에 공개할 한계는?', '이미 노출된 pre-April 5-fold의 exact-matured 작업 조건부 표본이다. Censored/pending을 0으로 만들지 않았고 평가에서 동일하게 제외했다. CAL→VALID temporal shift, CAL rolling warm-up(min200/부족시0), coarse α grid, 가정된 제출 metadata provenance, 모델별 CAL 추론 재생성 범위, 기존 full-distribution 결함을 공개해야 한다. 기준을 만족하지 못했다는 결과는 모든 미래 예측법의 불가능성 증명이 아니다.'),
      ('선택은 동결됐는가?', '그렇다. FINAL_SELECTION_FREEZE.json과 alpha/evidence SHA로 NONE 판정을 동결했다. 기존 증거 보존·검증 결과는 VERIFICATION.json에 있다.')]
    text='# Runtime 최종 duration calibration 검토\n\n결론: **SELECTED_RUNTIME_MODEL=NONE, SELECTED_ALPHA=null**. 단위는 초이며 GPUh로 모델을 선택하지 않았다.\n\n'+table
    text+='\nRaw Q90→보정 duration의 시간 합 감소율: '+values('raw_Q90_time_reduction_fraction',True)+'. 감소율은 동일 신뢰도에서의 무손실 이득이 아니다.\n\n'
    text+='\n\n'.join(f'## {i}. {q}\n\n{a}' for i,(q,a) in enumerate(answers,1))+'\n'
    (ROOT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    (ROOT/'README.md').write_text('# Frozen Runtime duration calibration\n\n선택은 **NONE**입니다. 230,237개 동일 작업, 6개 동결 후보, 5개 temporal fold를 비교했습니다. GPU 가중치 없는 초 단위 비율을 사용합니다.\n\n'+table+'\nα는 각 fold CAL의 21개 고정 grid에서 선택했고 VALID 적용 전에 동결했습니다. 모든 후보의 OP time ratio는 2배 이상이며 모든 primary가 fold별 90% 기준을 실패했습니다. 기존 provider gate와 V9 full-distribution 결함을 변경하지 않았습니다.\n\n[한국어 50항목 검토](FINAL_REVIEW_KO.md), [사전등록](PREREGISTRATION.json), [공통 population](COMMON_RUNTIME_POPULATION_AUDIT.json), [CAL 감사](CAL_CAUSALITY_AUDIT.json), [선택 동결](FINAL_SELECTION_FREEZE.json), [검증](VERIFICATION.json)을 참조하세요.\n\n재현: 동결 로컬 입력과 exact environment가 필요합니다. `prepare.py`는 원 요청 수정 직전의 보존된 population 감사에서 입력을 준비하고, `calibrate.py`는 CAL quantile/alpha를 생성합니다. 두 단계는 이미 동결된 파일이 있으면 덮어쓰지 않고 중단합니다. `evaluate.py`, `finalize.py`, `test_duration.py`, `verify.py`가 결과·보고·검증을 수행합니다. 모델 학습 엔트리포인트는 호출하지 않습니다. 큰 행별 CAL/VALID/OP 예측과 폐기된 shared-reserve 초안은 로컬 SHA manifest로 보존됩니다.\n',encoding='utf-8')
if __name__=='__main__':main()
