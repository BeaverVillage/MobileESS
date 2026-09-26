"""Readable presentation of already-frozen decisions; never tunes or selects."""
from pathlib import Path
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
read = lambda name: json.loads((ROOT / name).read_text(encoding='utf-8'))
assert (ROOT / 'EVALUATION_COMPLETE.json').exists()
assert not (ROOT / 'FINAL_REVIEW_KO.md').exists()
freeze, verdict = read('FINAL_SELECTION_FREEZE.json'), read('FINAL_VERDICT.json')
metrics = pd.read_csv(ROOT / 'MODEL_METRICS.csv')
ci = pd.read_csv(ROOT / 'PAIRED_UNCERTAINTY.csv')
horizons = pd.read_csv(ROOT / 'HORIZON_METRICS.csv')
protocol = read('PROTOCOL.json')
lines = ['# CC4-v2.5 최종 검토 — Target-resolution comparison', '',
    f"DEV/CAL에서 동결한 primary resolution은 **{freeze['primary']}**이다. 평가 후 재선택하지 않았다. 지원되는 사전 고정 family는 **{', '.join(verdict['supported_frozen_families']) or '없음'}**이다. May는 exposed historical diagnostic이며 tuning 또는 untouched confirmation에 사용하지 않았다.", '',
    '## 무엇을 고정하고 비교했는가', '',
    'PR70 C0를 만든 PR64 raw refitted H1 LightGBM Q50/Q90을 그대로 사용했다. 동일한 원시 hourly future-arrival GPUh에서 H3/H6는 자정 기준 non-overlapping block, CUM은 다음날 1..24시간 prefix이다. 모든 target은 완료된 총 GPU·h를 submit 시간에 귀속한다. GPU 용량·실행시간 cap이나 신규 exclusion은 없다.', '',
    '기존 71개 feature의 block-end 행을 그대로 쓴다. history/seasonal/calendar/maturity 값의 pooling이나 새로운 feature를 추가하지 않았다. Legacy horizon_hours=1 및 window_start_slot은 원 hourly anchor의 값이고, 실제 target 구간은 별도 start/end/duration metadata다. 이 고정된 anchor 방식에서 direct model의 개선이 없다는 결과를 모든 가능한 aggregated feature 설계의 실패로 일반화하지 않는다.', '',
    'Expanding history, 30일 half-life, daily refit, full-day label_matured_at<issue와 과거 issue/non-PURGE membership을 동일하게 유지했다. 짧은 block도 label을 더 일찍 학습에 넣지 않는다. LightGBM의 15 leaves/400 trees/lr0.03/min_child50/seed20260924 및 log1p target 변환을 고정했다. Target observation별 기존 day weight를 그대로 주므로 H3/H6의 하루 학습 행 수 감소는 target-resolution 변경의 일부다.', '',
    'DIRECT와 AGGREGATED_H1을 비교한다. 후자는 frozen hourly Q50/Q90의 단순 합이며, 합산한 Q90이 aggregate의 실제 Q90임을 보장하지 않는다. H1의 두 method 행은 같은 frozen 예측이다. CUM은 기존 nonnegative/noncrossing quantile support만 적용한 marginal prefix 예측이며, 새로운 monotone projection은 적용하지 않았다.', '',
    '## 단위·정규화·mass conservation', '',
    f"공통 정규화 분모는 eligible TRAIN의 hourly 평균 **{protocol['normalizer']['value']:.9f} GPUh**이다. normalized pinball은 각 target의 pinball을 target duration으로 나눈 후 day/output에 동일 가중 평균을 내고 이 분모로 나눈 값이다. CUM은 각 prefix의 시간당 손실을 동일 가중 평균한다. 모든 resolution과 기간에서 같은 TRAIN scale을 사용한다.", '',
    'H1/H3/H6 requirement ratio는 비중복 block 합의 Q90/actual이다. CUM의 primary ratio는 24h terminal Q90/actual이며 각 prefix ratio를 별도 보고한다. Prefix들의 합을 daily mass 또는 예약량으로 해석하지 않는다. 원시 29 partitions 전체를 다시 읽어 eligible population과 10,632개 hourly label이 원 authority와 정확히 같음을 확인했다. H3/H6 합, CUM terminal 및 first difference의 질량 보존은 RAW_TARGET_AUDIT.json과 DAILY_TARGET_AUDIT.csv에 있다. 부동소수점 오차만 허용했고 label은 변경하지 않았다.', '',
    'High-load는 TRAIN positive target의 Q95 초과로 정의한다. H1/H3/H6는 resolution별 pooled threshold, CUM은 prefix별 threshold를 사용한다. 따라서 resolution 간 high-load strata는 다른 사건이다. Cross-resolution 비교는 target 적합성 비교이며 hourly predictor superiority의 근거가 아니다.', '',
    '## 사전 동결 선택 규칙', '',
    'DEV/CAL 각각 requirement ratio<2, high-load coverage가 H1보다 최소 +5pp, normalized Q90 pinball≤H1을 hard gate로 두었다. Overall88–92%는 선호 기준이다. 이전 task의 positive85%/burst60%를 새 hard gate로 가져오지 않았다. DIRECT와 AGGREGATED_H1 중 각 family의 method를 동결했으며, eligible family 중 primary를 동결했다. 단순 집계만으로 효과가 나도 target-resolution 연구 근거가 될 수 있고, direct 학습 효과는 별도 같은-target 비교로 판단한다.', '',
    '| resolution | frozen method | DEV/CAL eligible |', '|---|---|---|']
for r, value in freeze['choices'].items(): lines.append(f"| {r} | {value['method']} | {value['eligible']} |")
lines += ['', '## 모델/target 결과', '',
    '| role | target | method | Q90 coverage | calibration error | normalized Q90 pinball | primary ratio | high-load coverage | positive coverage |',
    '|---|---|---|---:|---:|---:|---:|---:|---:|']
for _, r in metrics.iterrows():
    lines.append(f'| {r.role} | {r.resolution} | {r.method} | {r.Q90_coverage:.2%} | {r.calibration_error:.4f} | {r.normalized_Q90_pinball:.6f} | {r.requirement_ratio:.3f} | {r.high_load_coverage:.2%} | {r.positive_coverage:.2%} |')
lines += ['', '## Horizon robustness와 CUM coherence', '',
    '| role | target | method | min/max horizon coverage | horizons in88–92% | Q50/Q90 downward prefix pairs | max prefix drop GPUh |',
    '|---|---|---|---|---:|---:|---:|']
for _, r in metrics[metrics.role.isin(['EXPOSED_EVALUATION', 'MAY_HISTORICAL'])].iterrows():
    g = horizons[horizons.role.eq(r.role) & horizons.resolution.eq(r.resolution) & horizons.method.eq(r.method)]
    lines.append(f'| {r.role} | {r.resolution} | {r.method} | {g.Q90_coverage.min():.2%} / {g.Q90_coverage.max():.2%} | {g.Q90_coverage.between(.88,.92).sum()}/{len(g)} | {int(r.prefix_downward_pairs_Q50)}/{int(r.prefix_downward_pairs_Q90)} | {r.max_prefix_drop_GPUh:.3f} |')
lines += ['', '모든 horizon/block, positive/zero/high-load strata와 Q50 결과는 HORIZON_METRICS.csv, STRATIFIED_METRICS.csv에 저장했다. Downward prefix가 있으면 coherent cumulative planning curve라고 주장하지 않는다. Forecast를 evaluation 후 교정하지 않았다.', '',
    '## Paired statistical uncertainty', '',
    '동일한 target-day 전체를 paired unit으로 하여 모든 block/prefix를 함께 resample했다. 1일 및7개 관측일 circular block 각2,000 draws이며 비율과 calibration error를 draw마다 재계산했다. Zero-denominator draw는 세고 해당 CI를 unavailable로 둔다. 제거하거나 재추출하지 않는다. 7-day 결과를 판정에 사용하고 day CI는 sensitivity로만 보고한다.', '',
    '| role | target | method | contrast | metric | delta | 7-day95% CI | invalid draws |',
    '|---|---|---|---|---|---:|---|---:|']
keep = ci.block_observed_days.eq(7) & ci.metric.isin(['normalized_Q90_pinball', 'high_load_coverage', 'requirement_ratio'])
for _, r in ci[keep].iterrows():
    if r.contrast == 'RESOLUTION_EFFECT' and freeze['choices'][r.resolution]['method'] != r.method: continue
    lines.append(f'| {r.role} | {r.resolution} | {r.method} | {r.contrast} | {r.metric} | {r.delta:.6f} | [{r.CI95_low:.6f}, {r.CI95_high:.6f}] | {int(r.nonfinite_draws)} |')
lines += ['', 'SAME_TARGET_DIRECT_EFFECT는 DIRECT−동일 target의 H1 합산이며 학습 방법 효과다. RESOLUTION_EFFECT는 해당 target−H1이며 target 자체와 high-load 사건이 달라진 비교다. 고정 예측에 조건부인 CI로 refit/selection uncertainty를 포함하지 않는다. 여러 family와 지표의 unadjusted95% CI이므로 simultaneous familywise95% confirmation이나 새로운 untouched 검증으로 주장하지 않는다.', '',
    '## 최종 판정과 한계', '',
    '지원 판정은 DEV/CAL에서 eligible로 동결한 family에만 가능하다. Dec–Feb와 May 각각 point gate를 통과하고 7-day CI의 high-load 차이 lower>0 및 normalized pinball 차이 upper≤0이어야 한다. +5pp는 point의 실질적 개선 기준이며 CI lower≥5pp인 더 강한 증거는 GATES.csv의 robust_five_pp_gain으로 구분했다. 평가로 method나 primary를 다시 선택하지 않았다.', '']
for key in ['AGGREGATED_CC4_TARGET_SUPPORTED', 'PRODUCTION_REPLACEMENT_SUPPORTED', 'OPTIMIZER_INTEGRATION_READY', 'PRODUCTION_PROMOTED', 'CC4_ML_DEVELOPMENT_STOPPED']:
    lines.append(f'- {key} = **{str(verdict[key]).upper()}**')
if verdict['CC4_ML_DEVELOPMENT_STOPPED']:
    lines += ['', 'H3/H6/CUM의 사전 고정 후보 모두 지원 기준에 실패했다. CC4 추가 ML 개발을 종료하고 현재 frozen interface를 유지한다. 이번 task에서는 optimizer coupling이나 production promotion을 구현하지 않았다.']
else:
    lines += ['', '지원은 위 사전 고정 family의 historical target-resolution 연구 근거에 한정된다. Frozen primary를 평가로 바꾸지 않았으며 현재 interface와 production은 그대로 유지했다.']
lines += ['', '요청 상태와 실제 ingestion version/effective-time은 기존 V40S4 D1_SCHEDULER_REQUEST_STATE_PROXY_V1의 UNVERIFIED/UNOBSERVED 경계를 계승한다. Historical exactness, request immutability 또는 변경 빈도0을 주장하지 않는다. Raw actual completion은 label 재구성에만 사용하며 issue 이후 label은 학습에 들어가지 않는다. 이 한계와 untouched confirmation 부재 때문에 production replacement와 integration readiness는 fail-closed다.', '',
    '19개 contract/preparation tests, raw Job membership, exact day membership/weights, feature time, checkpoint/prediction replay와 독립 paired CI 감사의 결과는 TEST_RESULTS.json, RAW_TARGET_AUDIT.json, VALIDATION.json, INDEPENDENT_AUDIT.json, UNCERTAINTY_AUDIT.json에 저장했다. 과거 frozen evidence는 overwrite하지 않았다. Optimizer/MESS/IEEE123/8500/Actual/OpenDSS/production은 수정하거나 실행하지 않았다.', '']
with (ROOT / 'FINAL_REVIEW_KO.md').open('x', encoding='utf-8', newline='\n') as stream: stream.write('\n'.join(lines))
