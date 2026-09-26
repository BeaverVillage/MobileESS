"""Render completed frozen metrics into Korean tables; no fitting or selection."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import *


def main():
    require(read('VALIDATION.json')['PASS'], 'VALIDATION_REQUIRED')
    selected = read('FINAL_SELECTION_FREEZE.json')['model']
    metrics = pd.read_csv(ROOT/'MODEL_METRICS.csv')
    strata = pd.read_csv(ROOT/'STRATIFIED_METRICS.csv')
    paired = pd.read_csv(ROOT/'MATCHED_REFERENCE_METRICS.csv')
    uncertainty = pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv')
    point = pd.read_csv(ROOT/'POINT_ARCHITECTURE_DIAGNOSTICS.csv')
    quantiles = pd.read_csv(ROOT/'QUANTILE_DIAGNOSTICS.csv')
    label = lambda r: 'Exposed Apr' if r == 'EXPOSED_EVALUATION' else 'May'
    lines = ['# Runtime-vNext 정량 검토 보충', '',
             f'평가 전 고정 후보는 **{selected}**, 시간 정책은 **180일·14일 반감기**다. 평가 결과로 선택을 바꾸지 않았다.', '',
             '## 전체 모델 비교', '',
             'PR31 frozen reference는 Pending 교집합만 포함하므로 N이 다르다. 직접 paired 비교는 아래 matched 표와 CI를 사용한다. May frozen LightGBM의 Running 값은 total-minus-elapsed proxy다.', '',
             '| 구간 | 모델 | N | Q90 coverage | GPU coverage | >4h under | overreserved GPUh | requested reference GPUh |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for _, r in metrics[metrics.state.eq('ALL')].iterrows():
        lines.append(f'| {label(r.role)} | {r.model} | {r.N:d} | {r.Q90_coverage:.2%} | {r.GPU_coverage:.2%} | {r.long_under:.2%} | {r.overreserved_GPUh:,.1f} | {r.requested_overreserved_GPUh:,.1f} |')
    lines += ['', '## 고정 후보: Pending / Running', '',
              '| 구간 | state | N | Q90 coverage | GPU coverage | >4h under | missed GPU-slots |',
              '|---|---|---:|---:|---:|---:|---:|']
    for _, r in metrics[metrics.model.eq(selected)&metrics.state.ne('ALL')].iterrows():
        lines.append(f'| {label(r.role)} | {r.state} | {r.N:d} | {r.Q90_coverage:.2%} | {r.GPU_coverage:.2%} | {r.long_under:.2%} | {r.missed_GPU_slots:,.0f} |')
    lines += ['', '## Running elapsed regime', '',
              '| 구간 | elapsed | N | Q90 coverage | GPU coverage | >4h under |',
              '|---|---|---:|---:|---:|---:|']
    for _, r in strata[strata.model.eq(selected)&strata.stratum.eq('elapsed')].iterrows():
        lines.append(f'| {label(r.role)} | {r.value} | {r.N:d} | {r.Q90_coverage:.2%} | {r.GPU_coverage:.2%} | {r.long_under:.2%} |')
    lines += ['', '## 고정 후보의 주요 subgroup gate 미달', '',
              '사전 정의한 100개 이상 Job-issue 및 총 GPU weight 1% 이상인 hardware/state/walltime/GPU 그룹 중 coverage 88% 미만만 표시한다. 전체 strata는 원본 CSV에 보존했다.', '',
              '| 구간 | stratum | value | N | Q90 coverage |', '|---|---|---|---:|---:|']
    failing = strata[strata.model.eq(selected)&strata.major&strata.stratum.ne('elapsed')&strata.Q90_coverage.lt(.88)]
    for _, r in failing.iterrows():
        lines.append(f'| {label(r.role)} | {r.stratum} | {r.value} | {r.N:d} | {r.Q90_coverage:.2%} |')
    if failing.empty:
        lines.append('| 전체 | 미달 없음 | — | — | — |')
    lines += ['', '## 고정 후보와 frozen reference의 paired 비교', '',
              'Exposed Apr의 frozen comparison은 Pending 교집합이다. Running의 기존 production remaining 모델 재현이라고 해석하지 않는다. GPU-slot은 24시간 runtime-origin occupancy proxy다.', '',
              '| 구간 | state | paired N | missed GPU-slot 감소 | 후보 pinball | reference pinball |',
              '|---|---|---:|---:|---:|---:|']
    for _, r in paired[paired.model.eq(selected)&paired.effect.eq('vs_frozen_production')].iterrows():
        lines.append(f'| {label(r.role)} | {r.state} | {r.N:d} | {r.missed_slots_reduction:.2%} | {r.pinball:.2f} | {r.reference_pinball:.2f} |')
    lines += ['', '## 효과별 paired 95% CI', '',
              '7개의 관측 issue-day circular block, 2,000회 bootstrap이다. Delta는 candidate minus reference이며 음수이면 pinball 개선이다. 1일 결과도 원본 CSV에 있다. architecture 항목의 Running/ALL은 remaining-target 전략 변화도 포함한다.', '',
              '| 구간 | effect | state | Delta pinball | 95% CI | unmatched candidate / reference |',
              '|---|---|---|---:|---|---:|']
    subset = uncertainty[uncertainty.block_days.eq(7)&uncertainty.metric.eq('Q90_pinball')&(
        (uncertainty.effect.eq('vs_frozen_production')&uncertainty.model.eq(selected))|
        (uncertainty.effect.ne('vs_frozen_production')&uncertainty.state.isin(['ALL','PENDING'])))]
    for _, r in subset.iterrows():
        lines.append(f'| {label(r.role)} | {r.effect} | {r.state} | {r.delta:.2f} | [{r.CI95_low:.2f}, {r.CI95_high:.2f}] | {r.candidate_unmatched:d} / {r.reference_unmatched:d} |')
    lines += ['', '## Calibration 이전 Pending point architecture 비교', '',
              '같은 시간 정책·cohort·입력·OHE/SVD·total-runtime target에서 raw MoE point와 raw LightGBM Q50을 비교한다. Q90 pooled correction의 영향은 들어가지 않는다.', '',
              '| 구간 | LGBM Q50 MAE(s) | MoE point MAE(s) | Delta | 7-issue 95% CI |',
              '|---|---:|---:|---:|---|']
    for _, r in point[point.block_issue_days.eq(7)].iterrows():
        lines.append(f'| {label(r.role)} | {r.candidate_MAE_seconds:.2f} | {r.reference_MAE_seconds:.2f} | {r.delta_MAE_seconds:.2f} | [{r.CI95_low:.2f}, {r.CI95_high:.2f}] |')
    lines += ['', '## Q95/Q99 진단', '',
              '선택과 gate는 Q90 기준이다. 아래 상위 quantile의 coverage를 Q90 성과로 대체하지 않는다. 모든 모델·quantile의 결과는 QUANTILE_DIAGNOSTICS.csv에 있다.', '',
              '| 구간 | state | quantile | coverage | GPU coverage | overreserved GPUh |',
              '|---|---|---:|---:|---:|---:|']
    for _, r in quantiles[quantiles.model.eq(selected)&quantiles['quantile'].ge(.9)].iterrows():
        lines.append(f'| {label(r.role)} | {r.state} | {r["quantile"]:.2f} | {r.coverage:.2%} | {r.GPU_coverage:.2%} | {r.overreserved_GPUh:,.1f} |')
    lines += ['', '## 기준선·인과성·적용 범위', '',
              '과거 MoE 재학습의 245개 예측, 최신 LightGBM 31일분 frozen 예측 및 대표 issue 재학습을 검증했다. 최신 대표 issue는 완료 Job 667,375개, Pending 1,395개이며 model text SHA-256까지 완전히 같다. May 31일 training membership도 frozen authority와 모두 일치한다.', '',
              'Temporal 효과는 공통 positive-GPU cohort에서만 식별한다. 과거 전체 Job MoE의 production refit 우월성으로 확대하지 않는다. request 수정 이력과 실제 ingestion 시각은 미인증이며, target/interface 유효성은 offline event-time proxy 범위다. 완료 Job만 학습하는 remaining 모델의 completion selection bias 및 장기 반복 Job의 dependence는 남는다.', '',
              '## 최종 해석', '',
              '고정 후보는 전체 success gate를 통과하지 못했다. May의 frozen baseline 대비 전체 Q90 pinball 차이는 7-issue CI가 0을 포함한다. Running의 naive total-minus-elapsed 기준선 대비 개선은 있지만, Pending에서 missed GPU-slot이 증가해 전체 50% 감소 조건을 충족하지 못한다. Running-only 개선을 전체 운영 우월성으로 해석하지 않는다.', '',
              'Hierarchical calibration challenger는 May 전체 coverage와 GPU coverage를 목표 범위로 올렸지만 long-job underprediction 조건은 통과하지 못했다. evaluation 결과를 보고 이 challenger로 재선택하지 않았다. 공통 시간 정책의 Q90 비교는 quantile 추정 방식과 pooled correction 차이를 함께 포함하며, calibration 이전 Pending point MAE의 architecture 차이는 두 평가 구간 모두 CI가 0을 포함한다.', '',
              '통계적으로 견고한 production 대체 개선, production replacement 및 optimizer integration readiness는 지지하지 않는다. 모든 비교의 N과 N_days는 실제 paired 관측으로 계산한다. May Pending은 31개 issue 중 Pending 관측이 있는 29개 issue이며, 빈 issue를 결과에 따라 제외한 것이 아니다.', '',
              '상세 비교의 해석은 [INTERPRETATION_CONTRACT.md](INTERPRETATION_CONTRACT.md)를 따른다. 기존 frozen evidence와 optimizer/MESS/IEEE123/8500/Actual/OpenDSS는 변경하거나 실행하지 않았다. production promotion과 optimizer integration은 수행하지 않았다.', '',
              '![공통 cohort 비교](COMPARISON.png)', '']
    (ROOT/'REVIEW_SUPPLEMENT_KO.md').write_text('\n'.join(lines), encoding='utf-8')
    names = ['MODEL_METRICS.csv','STRATIFIED_METRICS.csv','MATCHED_REFERENCE_METRICS.csv',
             'PAIRED_UNCERTAINTY.csv','POINT_ARCHITECTURE_DIAGNOSTICS.csv','QUANTILE_DIAGNOSTICS.csv']
    dump('REVIEW_SUPPLEMENT_RECEIPT.json', dict(time=now(), input_hashes={n:sha(ROOT/n) for n in names},
         editorial_only=True, selection_changed=False))


if __name__ == '__main__':
    main()
