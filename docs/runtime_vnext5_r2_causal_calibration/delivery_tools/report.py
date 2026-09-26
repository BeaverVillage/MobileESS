"""Report frozen causal calibration results; no selection or predictions edited."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def read(n):return json.loads((ROOT/n).read_text(encoding='utf-8'))
def write(n,x):
    with (ROOT/n).open('x',encoding='utf-8') as f:json.dump(x,f,indent=2,ensure_ascii=False,allow_nan=False)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def table(f,cols,labels):
    out=['| '+' | '.join(labels)+' |','|'+'|'.join(['---']*len(cols))+'|']
    for _,r in f.iterrows():
        values=[]
        for c in cols:
            v=r[c]
            if c in ['coverage','GPU_coverage','long_under']:v=f'{v*100:.3f}%'
            elif isinstance(v,(float,np.floating)):v=f'{v:,.4f}'
            values.append(str(v))
        out.append('| '+' | '.join(values)+' |')
    return '\n'.join(out)
def main():
    m=pd.read_csv(ROOT/'MODEL_METRICS.csv');dev=pd.read_csv(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv');ci=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');ledger=pd.read_csv(ROOT/'CALIBRATION_MEMBERSHIP_LEDGER.csv');run=m[m.state.eq('RUNNING')];raw=run[run.arm.eq('R1')].sort_values('role');selected=read('FINAL_SELECTION_FREEZE.json')['selected_running'];diagnostics=[]
    for arm in ['R2','R3']:
        a=run[run.arm.eq(arm)].sort_values('role');safe=bool((a.coverage>=.90).all() and (a.GPU_coverage>=.90).all() and (a.long_under<=.15).all());loss=bool((a.pinball_Q90.to_numpy()<=1.02*raw.pinball_Q90.to_numpy()).all());reserve=bool((a.overreserved_GPUh<=a.requested_overreserved_GPUh).all());proof=[]
        for role,ref in [('EXPOSED_EVALUATION','R1'),('MAY_HISTORICAL','R1'),('MAY_HISTORICAL','R0')]:
            z=ci[ci.role.eq(role)&ci.state.eq('RUNNING')&ci.candidate.eq(arm)&ci.reference.eq(ref)&ci.metric.eq('missed_GPU_slots')&ci.block_days.eq(7)]
            assert len(z)==1
            proof.append(dict(role=role,reference=ref,CI95_high_negative=bool(z.iloc[0].CI95_high<0)))
        robust=all(r['CI95_high_negative'] for r in proof)
        diagnostics.append(dict(arm=arm,preselected=selected==arm,both_evaluation_safety_pass=safe,both_evaluation_pinball_margin_pass=loss,reserve_preferred_pass=reserve,robust_missed_reduction=robust,missed_proof=proof))
    supported=bool(any(r['preselected'] and r['both_evaluation_safety_pass'] and r['both_evaluation_pinball_margin_pass'] and r['robust_missed_reduction'] for r in diagnostics))
    verdict=dict(selected_running=selected,Pending='R0 exact',RUNTIME_CALIBRATION_SUPPORTED=supported,PRODUCTION_REPLACEMENT_SUPPORTED=False,OPTIMIZER_INTEGRATION_READY=False,PRODUCTION_PROMOTED=False,TEMPORAL_POLICY_CHANGED=False,NEW_MODEL_SEARCHED=False,model_training_executions=0,calibrator_diagnostics=diagnostics,reserve_preferred_not_hard_support_gate=True,rule_source_sha256=sha(ROOT/'REGISTRATION.json'),May='already exposed historical diagnostic',proxy='D1_SCHEDULER_REQUEST_STATE_PROXY_V1; UNVERIFIED/UNOBSERVED',production_disposition='unchanged R0; no integration or promotion')
    write('FINAL_VERDICT.json',verdict)
    cols=['role','arm','N','coverage','GPU_coverage','long_under','missed_GPU_slots','overreserve_vs_requested','reserve_vs_requested','pinball_Q90','MAE_bound_seconds'];labels=['구간','모델','N','coverage','GPU coverage','total>4h under','missed GPU-slots','초과예약/요청 초과예약','총예약/요청 총예약','Q90 pinball(s)','bound MAE(s)']
    keyci=ci[ci.state.eq('RUNNING')&ci.reference.eq('R1')&ci.block_days.eq(7)&ci.metric.isin(['coverage','GPU_coverage','missed_slots_reduction','pinball_Q90','overreserve_vs_requested'])]
    fallback=ledger[ledger.support_fallback]
    ranges=ledger.groupby('role').agg(issues=('issue_time','size'),minimum_support=('distinct_mature_Jobs','min'),maximum_support=('distinct_mature_Jobs','max'),fallback_issues=('support_fallback','sum'),global_min=('global_correction_seconds','min'),global_max=('global_correction_seconds','max'),GPU_min=('GPU_correction_seconds','min'),GPU_max=('GPU_correction_seconds','max')).reset_index()
    text=f'''# Runtime-vNext5 최종 검토

DEV/CAL에서 **{selected}, 즉 PR71 R2의 raw Q90 유지**를 동결했다. 두 calibration 후보 모두 eligibility를 통과하지 못했다. **RUNTIME_CALIBRATION_SUPPORTED = {str(supported).upper()}**, **PRODUCTION_REPLACEMENT_SUPPORTED = FALSE**, **OPTIMIZER_INTEGRATION_READY = FALSE**, **PRODUCTION_PROMOTED = FALSE**이다. 연구 비교의 raw R1 유지와 실제 production R0 유지는 서로 다른 의미이며, Pending 및 실제 production은 계속 frozen R0이다.

## 비교와 사전 고정

이번 R0는 frozen production Q90, R1은 **PR71에서 R2였던 GPU/long weighted MULTI_QUANTILE의 raw Running Q90**이다. 이름 매핑에 유의한다. 새 R2는 global residual calibration, 새 R3는 GPU-weighted residual calibration이다. 모델/feature/180-day·14-day temporal policy를 바꾸거나 refit하지 않았다. Q95, AFT, selector, threshold search도 하지 않았다. `TEMPORAL_POLICY_CHANGED = FALSE`, `NEW_MODEL_SEARCHED = FALSE`, model training executions=0.

모든 결정은 `REGISTRATION.json`에서 DEV 전에 고정했다. `FINAL_SELECTION_FREEZE.json` 이후에만 신규 평가를 계산했다. min support=100 distinct mature Jobs, empirical quantile=.90, one-sided additive correction, 2% pinball 허용 한계, reserve preference와 tie-break를 고정했다. 선택 규칙은 두 DEV/CAL 구간 모두 coverage≥90%, GPU coverage≥90%, total>4h under≤15%, pinball≤1.02×raw를 요구한다. eligible 후보 사이에서 요청 초과예약 기준 충족을 선호하고, 두 구간 reserved/requested ratio 평균이 작은 arm, 마지막으로 arm ID 순이다. 없다면 raw R1 유지다.

요청 walltime 대비 reserve는 사용자 지정대로 **preferred**이다. 등록 전에 초기 제안의 추가 reserve hard gate를 수정해 이 우선순위를 반영했다. 이는 DEV/평가 결과를 본 수정이 아니다. 최종 calibration support는 preselected calibration의 두 평가 구간 safety/loss 조건과 block CI로 지지된 missed-slot 감소를 요구하며, reserve 비용은 별도로 명시한다. production/integration 판단은 proxy authority와 노출된 평가 이력을 고려해 계속 fail-closed다.

## Causal residual과 반복 Job

현재 issue t에서 `source_issue<t` 및 `job_end<t`를 먼저 만족시키고, 그 다음 각 Job의 가장 최근 eligible OOS forecast 한 건만 선택한다. residual은 **end−SOURCE_issue−SOURCE_raw_Q90**이며 현재 issue에서의 remaining을 historical residual로 잘못 사용하지 않는다. 반복 Job은 한 pool에 한 번만 기여한다. 현재 Running query Job은 그 pool에 포함될 수 없고 명시적으로 disjoint 검증한다.

unweighted inverse ECDF는 rank ceil(.90×N), GPU-weighted inverse ECDF는 정렬 residual의 누적 양수 GPU weight가 총합의 90%에 처음 도달하는 값이다. interpolation이나 conformal ceil(.90×(N+1)) 보정이 아니다. delta=max(0,해당 quantile), bound=raw Q90+delta이고 scaling/capping은 없다. GPU weight는 source forecast의 requested GPU count이며 이미 허용된 request proxy이다.

100개 Job 미만이면 delta=0을 적용하고 모든 query를 그대로 평가한다. 실제 warmup fallback은 {len(fallback)} issue이며 기존 R2 TRAIN forecast가 없어 새 학습이나 backward replay로 보충하지 않았다. 최소 지원은 dedup 이후의 Job 수로 센다. 정확한 source forecast ID, source issue, mature end, raw bound, GPU weight, residual은 issue별 membership Parquet에 있다.

{table(ranges,list(ranges.columns),list(ranges.columns))}

expanding calibration history는 새 residual pool 정책이며 frozen base model의 학습 temporal policy와 구분한다. latest-per-Job 선택은 elapsed 분포를 바꾸고, mature residual 제한은 완료된 Job을 상대적으로 많이 반영한다. 미완료 장기 Job의 residual은 성숙하기 전 사용할 수 없다. 이러한 편향과 temporal dependence를 제거했다거나 finite-sample/distribution-free coverage 보장을 얻었다고 주장하지 않는다. GPU weight ESS는 concentration 진단이며 튜닝 gate로 사용하지 않았다.

## DEV/CAL 동결 결과

{table(dev,cols,labels)}

R2는 DEVELOPMENT coverage 89.294%, GPU coverage 88.956%로 90%에 못 미쳤다. R3도 safety를 충족하지 못했고 DEVELOPMENT pinball 약 3.265% 악화로 사전 2% 한계를 넘었다. R2의 DEVELOPMENT pinball 악화 약 1.663%는 허용 범위 안이었다. warmup을 빼거나 threshold를 조정하지 않고 raw R1을 동결했다.

## 노출된 historical evaluation

{table(run,cols,labels)}

May에서 global R2는 coverage 87.035%, GPU coverage 85.131%, GPU-weighted R3는 86.851%/85.017%로 둘 다 90%에 못 미쳤다. CALIBRATION 구간에서 보였던 안전성은 다음 historical 구간에서 유지되지 않았다. May 결과로 quantile/window/support/margin이나 선택을 재조정하지 않았다. May는 이미 노출된 diagnostic이며 untouched confirmation이 아니다.

모든 Pending arm은 R0와 동일하다:

{table(m[m.state.eq('PENDING')&m.arm.eq('R0')],cols,labels)}

## Paired uncertainty와 비용

{table(keyci,['role','candidate','metric','estimate','CI95_low','CI95_high'],['구간','후보(vs raw R1)','지표','효과','95% low','95% high'])}

May missed GPU-slot 감소는 raw 대비 R2 0.552% (block CI 0–7.326%), R3 0.187% (0–2.431%)이며 0을 포함한다. May Q90 pinball 차이는 R2 +5.462초 [−9.926,+18.859], R3 −1.968초 [−7.722,+1.224]이다. April에서는 일부 개선이 지지되지만, 두 구간 모두 목표를 충족하는 calibration이라는 결론은 지지되지 않는다.

비음수 additive correction은 **어떤 동일 cohort에서도** raw reserve/overreserve를 줄일 수 없다. 이는 알고리즘의 대수적 성질이다. 실제 May 초과예약/요청 초과예약은 raw 1.35484×, global 1.36027×, GPU-weighted 1.35630×로 선호 조건을 충족하지 못했다. reserve의 선호 실패를 별도 hard support gate로 바꾸지는 않았다. 실제 safety와 안정적 missed-slot 개선이 이미 부족하다.

전체 paired day=1 및 circular block=7 관측 issue bootstrap(2,000 draws)은 `PAIRED_UNCERTAINTY.csv`의 330행에 저장한다. 후보와 기준은 같은 Job-issue/label로 짝지었고 각 draw에서 ratio를 다시 계산했다. denominator=0 등의 nonfinite draw 수를 기록한다. CI는 고정 예측에 조건부이며 calibration 재선택이나 재학습 불확실성, 반복 Job 의존성 전체를 포괄하지 않는다. 관측 issue 사이 calendar gap이 있을 수 있고 April 13/May31 issue로 block 독립 정보량이 작다. 여러 arm/지표를 탐색적으로 보고하며 multiplicity-adjusted confirmation을 주장하지 않는다.

## 정의, strata, authority

Running target은 remaining runtime이고, long-job stratum은 **actual total runtime>4h**다. requested reference는 max(requested−elapsed,0)이다. missed GPU-slots는 부모의 15분/96-slot(24h) runtime-origin occupancy proxy이며 optimizer dispatch가 아니다. 이 metric horizon만 제한되며 prediction을 cap하지 않는다. MAE는 Q90 bound 자체에 대한 절대 오차다. `<1h / 1–2h / 2–4h / 4–8h / >8h`와 GPU `1 / 2–4 / >4` strata를 각각 CSV에 보고한다. invalid outcome은 unscorable로 명시하고 paired scoring에는 같은 valid cohort를 쓴다.

source 59 issues/13,828 Running forecasts는 부모 PR71 R2 raw prediction과 byte hash로 연결된다. 각 원본 모델의 exact training membership에서 end<source_issue, 원본 전처리의 latest end maturity, source Running state/elapsed를 확인했다. 59 calibration pool의 strict maturity·latest-Job dedup·정확한 residual/weight/quantile 및 Pending R0 보존을 재계산했다. 추가 모델 학습은 0회다.

**D1_SCHEDULER_REQUEST_STATE_PROXY_V1 / UNVERIFIED·UNOBSERVED**를 그대로 상속한다. scheduler request의 실제 version/available-time은 관측되지 않아 역사적 정확성, immutability, zero-change를 주장하지 않는다. archive가 실제 historical census 전체이거나 outcome-independent inclusion이라고 주장하지 않는다. 이번 calibration은 이 authority를 개선하는 실험이 아니다. R0의 DEV/CAL/April 출력은 없으며 May-trained baseline을 과거로 역적용하지 않았다.

## 전달 및 판정

6 contract tests, 부모 byte preservation, exact residual membership/maturity audit, 독립 metric·paired CI 재계산, source/selection freeze와 Git blob 검증을 포함한다. `TEST_RESULTS.json`, `VALIDATION.json`, `INDEPENDENT_REVIEW.json`, `DELIVERY_MANIFEST.json`이 검증 결과를 기록한다. 기존 frozen evidence는 overwrite하지 않았다. reproducible scripts, exact split/source/membership, stratified metrics, uncertainty, 최종 selection freeze를 모두 새 scope에 저장했다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS 및 production 실행·수정·promotion은 없다.
'''
    (ROOT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8');print('FINAL_VERDICT',verdict,flush=True)
if __name__=='__main__':main()
