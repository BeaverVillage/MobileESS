"""Post-freeze reporting only: no model, feature, selection, or prediction edits."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
def read(n):return json.loads((ROOT/n).read_text(encoding='utf-8'))
def write(n,x):
    with (ROOT/n).open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def table(f,cols,labels):
    lines=['| '+' | '.join(labels)+' |','|'+'|'.join(['---']*len(cols))+'|']
    for _,r in f.iterrows():
        vals=[]
        for c in cols:
            v=r[c]
            if c in ['coverage','GPU_coverage','long_under']:v=f'{v*100:.2f}%'
            elif isinstance(v,(float,np.floating)):v=f'{v:,.3f}'
            vals.append(str(v))
        lines.append('| '+' | '.join(vals)+' |')
    return '\n'.join(lines)
def main():
    metrics=pd.read_csv(ROOT/'MODEL_METRICS.csv');ci=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');dev=pd.read_csv(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv')
    selected=read('FINAL_SELECTION_FREEZE.json')['selected'];running=metrics[metrics.state.eq('RUNNING')].copy()
    s=running[running.arm.eq(selected)]
    safety=bool(len(s)==2 and (s.coverage>=.90).all() and (s.GPU_coverage>=.90).all() and (s.long_under<=.15).all())
    reserve=bool(len(s)==2 and (s.overreserved_GPUh<=s.requested_overreserved_GPUh).all())
    comparisons=[('EXPOSED_EVALUATION','R1'),('MAY_HISTORICAL','R1'),('MAY_HISTORICAL','R0')]
    proof=[]
    for role,ref in comparisons:
        z=ci[ci.role.eq(role)&ci.state.eq('RUNNING')&ci.candidate.eq(selected)&ci.reference.eq(ref)&ci.block_days.eq(7)&ci.metric.eq('missed_GPU_slots')]
        proof.append({'role':role,'reference':ref,'CI95_high_negative':bool(len(z)==1 and z.iloc[0].CI95_high<0)})
    superior=bool(selected in ['R2','R3'] and safety and reserve and all(v['CI95_high_negative'] for v in proof))
    verdict={'selected_research_candidate':selected,'operational_quantile':.9,'Pending':'frozen R0 exact','TEMPORAL_POLICY_CHANGED':False,'NEW_MODEL_SUPERIOR':superior,'PRODUCTION_REPLACEMENT_SUPPORTED':False,'OPTIMIZER_INTEGRATION_READY':False,'PRODUCTION_PROMOTED':False,'both_evaluation_safety_pass':safety,'both_evaluation_reserve_pass':reserve,'paired_block_missed_slot_proof':proof,'rule_sha256':sha(ROOT/'VERDICT_RULE_FREEZE.json'),'May':'previously exposed historical diagnostic','proxy':'D1_SCHEDULER_REQUEST_STATE_PROXY_V1; provenance UNVERIFIED/UNOBSERVED','production_disposition':'retain R0; no promotion or integration'}
    write('FINAL_VERDICT.json',verdict)
    cols=['role','arm','N','coverage','GPU_coverage','long_under','missed_GPU_slots','overreserve_vs_requested','reserve_vs_requested','pinball_Q90','MAE_bound_seconds']
    labels=['구간','모델','N','coverage','GPU coverage','총 길이>4h under','missed GPU-slots','초과예약/요청 초과예약','총예약/요청 총예약','Q90 pinball (s)','bound MAE (s)']
    keyci=ci[ci.state.eq('RUNNING')&ci.block_days.eq(7)&ci.metric.isin(['missed_slots_reduction','overreserve_vs_requested','coverage','GPU_coverage','long_under','pinball_Q90'])]
    reports=[]
    for role in ['EXPOSED_EVALUATION','MAY_HISTORICAL']:
        z=keyci[keyci.role.eq(role)&((keyci.candidate.eq('R2')&keyci.reference.eq('R1'))|(keyci.candidate.eq('R3')&keyci.reference.isin(['R1','R0'])))]
        reports.append(table(z,['role','candidate','reference','metric','estimate','CI95_low','CI95_high'],['구간','후보','기준','지표','효과','95% low','95% high']))
    ledger=pd.read_csv(ROOT/'TRAINING_MEMBERSHIP_LEDGER.csv');r3=ledger[ledger.arm.eq('R3')]
    pending=metrics[(metrics.state.eq('PENDING'))&metrics.arm.eq('R0')]
    text=f'''# Runtime-vNext4 최종 검토

DEV/CAL에서 동결한 연구 후보는 **{selected}의 실제 Q90**이다. 이는 안전성 조건을 만족한 연구 후보 선택이며 운영 채택을 뜻하지 않는다. 최종 판정은 **NEW_MODEL_SUPERIOR = {str(superior).upper()}**, **PRODUCTION_REPLACEMENT_SUPPORTED = FALSE**, **OPTIMIZER_INTEGRATION_READY = FALSE**, **PRODUCTION_PROMOTED = FALSE**이다. Pending은 모든 arm에서 frozen R0와 정확히 동일하며 운영 변경은 없다.

## 사전 결정과 비교 범위

- R0: 최신 frozen production Q90. May에만 권위 있는 출력이 존재한다. Running은 total−elapsed naive transport이다. DEV/CAL/April로 역적용하지 않았다.
- R1: PR65의 고정된 elapsed-conditioned remaining MULTI_QUANTILE. 180-day/14-day recency와 기존 issue refit을 그대로 사용한다.
- R2: R1과 같은 완료 Job landmark, 전처리, LightGBM 구조와 hyperparameter. 학습 가중치만 recency×GPU×(관측 total>4h이면 2, 아니면 1)로 바꾸고 총 recency weight를 보존하도록 정규화했다. GPU/long multiplier는 DEV 전에 고정했다.
- R3: 동일 완료 landmark에 해당 issue까지 관측된 archive-conditional right-censored landmark를 추가한 고정 log-normal XGBoost AFT. 800 rounds, scale=1.0과 모든 hyperparameter를 DEV 전에 고정했다. R3−R2에는 모델 구조와 censored 학습 모집단의 효과가 함께 있으므로 순수 구조 효과로 해석하지 않는다.
- Q90만 운영 bound 후보이다. Q50/Q95는 각 명목 수준을 유지한 진단이며 Q95를 Q90으로 이름 바꾸거나 threshold/selector를 탐색하지 않았다. scaling/capping은 없다. R2의 고정 monotone quantile 정렬은 부모와 동일하다.

`REGISTRATION.json` → DEV/CAL metric → `FINAL_SELECTION_FREEZE.json` 및 `FREEZE_BUNDLE.json` → 평가의 순서를 지켰다. 별도 `VERDICT_RULE_FREEZE.json`은 신규 평가 전 판정 규칙을 고정했다. May는 이미 노출된 historical diagnostic이며 untouched confirmation이 아니다. May/April 결과로 학습 weight, feature, model, quantile, 선택 rule을 변경하지 않았다.

**TEMPORAL_POLICY_CHANGED = FALSE**: 180-day window와 14-day half-life, issue cadence를 유지한다. R3의 censored row는 마지막 관측 시각이 현재 issue이므로 recency age=0이다. 완료 row의 age는 완료 시각 기준이다. 이 관측 시각 확장은 censored population 처리의 일부이며 별도 temporal search가 아니다.

## DEV/CAL 선택

{table(dev,cols,labels)}

R3만 두 구간 모두 coverage≥90%, GPU coverage≥90%, total>4h under≤15%를 충족했다. 요청 대비 초과예약은 selection의 선호 조건이었고 hard safety gate가 아니었다. R3의 DEV/CAL 초과예약 비율은 각각 5.84×/16.79×이고 총예약 비율은 3.24×/5.74×이다. 따라서 `selected=R3`은 안전성 우선 규칙에 따른 연구 후보이며 예약 효율이나 채택 근거가 아니다. R0의 pre-evaluation missed-slot 성능은 알 수 없어 선택에 넣지 않았다.

## 동결 이후 평가

{table(running,cols,labels)}

최종 superiority는 두 평가 구간 모두 안전성 조건과 `overreserved GPUh <= requested-walltime overreserved GPUh`를 충족하고, 7-issue block CI에서 missed-slot 감소가 R1 대비 두 구간 및 R0 대비 May에서 지지되는지를 함께 요구했다. 안전성 통과={safety}, 요청 초과예약 기준 통과={reserve}. coverage만 높이는 과예약 모델은 운영 우수성으로 채택하지 않는다.

Pending R0(모든 후보 동일):

{table(pending,cols,labels)}

`QUANTILE_DIAGNOSTICS.csv`는 R1/R2/R3 Q50/Q90/Q95의 명목 pinball, coverage와 예약량을 각각 보고한다. R0에는 authoritative Q90만 존재하므로 median MAE나 Q95 자체 예측을 만들어 넣지 않았다. 각 bound에서 tau=.90/.95 loss를 계산한 항목은 그 bound를 해당 loss로 평가한 값이며 quantile 이름 변경을 뜻하지 않는다.

## 통계적 불확실성

{reports[0]}

{reports[1]}

위 표는 7-observed-issue circular-block 결과다. 전체 paired day=1/block=7 2,000 draws와 모든 지표는 `PAIRED_UNCERTAINTY.csv`에 있다. 후보−기준 차이에서 coverage는 양수가, under/missed/reserve/loss는 음수가 개선이다. `missed_slots_reduction`은 1−후보/기준으로 양수가 개선이다. 총량과 비율은 각 bootstrap sample에서 다시 계산했으며 denominator=0인 draw 수를 저장한다. `N_days`는 실제 달력 간격이 아닌 관측 issue 수다. April 13, May 31 issue이며 block=7의 유효 정보량이 작다. 고정 예측의 조건부 CI이고 재학습/모델 선택 불확실성이나 반복 Job 의존성 전체를 제거하지 않는다. 여러 arm/지표를 보고하며 다중비교 보정이나 untouched confirmatory 유의성 주장은 하지 않는다.

## Causal / maturity / provenance

사용자는 V40S4 **D1_SCHEDULER_REQUEST_STATE_PROXY_V1**에 따라 archive request field를 scheduler-visible proxy로 명시적으로 허용했다. provenance는 **UNVERIFIED/UNOBSERVED**다. 요청값의 역사적 정확성·불변성·zero-change, 실제 historical census의 완전성, outcome-independent archive inclusion을 주장하지 않는다. `07_hpc-oda-commons`는 code/model authority일 뿐 snapshot authority가 아니다. 초기 엄격 authority assessment와 이후 사용자 허용은 각각 `CENSORING_AUTHORITY.json`, `PROXY_AUTHORIZATION.json`으로 보존했다. 후자의 'no outcome-based population exclusion'은 **이미 관측된 archive 내부 cache filter**에 한정되며 upstream archive completeness의 주장이 아니다.

원시 전체 GPU {read('PROXY_AUTHORIZATION.json')['raw_GPU_all_dates']:,}행을 읽었고 null-end GPU는 0행이었다. 관련 pre-June {read('PROXY_AUTHORIZATION.json')['relevant_GPU_jobs']:,}행은 end/state/label_valid로 제외하지 않고 부모 cache와 정확히 일치한다. 관측되지 않은 never-completed Job을 만들어 보충하거나 실제 위험집단 전체를 안다고 주장하지 않았다. raw rebuild는 부모 normalized input과 byte SHA-256까지 같다.

R2 완료 학습은 end<issue만 허용한다. R3에서 end<issue일 때만 exact remaining label을 사용하고, 그 외 future/end==issue/null은 observed_end를 제거하고 lower=issue−start−이미 도달한 landmark, upper=∞로 만든다. final state/runtime/label_valid는 censored 학습 입력·label·weight에 들어가지 않는다. censored long weight는 그때 이미 관측된 total elapsed>4h 여부만 쓴다. R3의 issue별 censored 수 범위는 {int(r3.N_censored.min())}–{int(r3.N_censored.max())}이며 작은 archive-conditional 보강이다. 실제 모집단 censor bias 해소는 입증하지 않는다.

feature는 기존 9개 scheduler proxy와 log1p(elapsed)이다. request version의 실제 availability timestamp는 UNOBSERVED이며 임의 시각을 발명하지 않았다. submit/start와 issue의 event-time eligibility, 완료 target encoding의 maturity, query matrix의 기존 전처리와 bit-exact 동등성은 검증했다. feature의 운영 causality 인증과 event-time proxy 검증을 구분한다.

`>4h long-job underprediction`은 **actual TOTAL runtime>4h**인 Job에서 Running remaining prediction이 실제 remaining보다 작은 비율이다. 요청 기준 remaining은 max(requested−elapsed,0)이다. GPU-slots는 부모의 15분/24시간 runtime-origin occupancy proxy이며 optimizer dispatch 결과가 아니다. 이 지표의 96-slot horizon 때문에 24시간 이후의 차이는 측정하지 않는다. prediction 자체에는 이 cap을 적용하지 않는다. 평가 query 전체를 유지하고 invalid label만 unscorable로 표시한다. `RUNNING_ELAPSED_METRICS.csv`에 <1h, 1–2h, 2–4h, 4–8h, >8h를 보고한다. GPU bucket 추가 진단은 `RUNNING_GPU_METRICS.csv`에 있다.

## 재현·검증·보존

118개 신규 fit의 exact ordered membership, safe label/time/weight digests, 학습 receipt와 prediction을 저장했다. 거대한 원본 fit-time MEMBERSHIP Parquet와 model weights는 local에서 변경 없이 보존하고 SHA manifest를 제공한다. Git에는 같은 ordered row_id NPZ와 parent JOB_MEMBERSHIP + 동결 censor_proxy로 모든 safe column을 lossless 재구성·검증한 증거를 전달한다. `PORTABLE_MEMBERSHIP_AUDIT.json` 및 독립 review가 원본과의 동등성을 확인한다. 모델 입력 전체는 pinned raw archive로 재구성한다. portable sklearn preprocessors와 query-transform bit-exact bridge를 포함한다.

검증은 synthetic censor/future-end invariance/weight/AFT/selection/CI contract test 6개, 118 memberships 및 model/prediction digests, Pending R0 exact preservation, 모든 parent delivery hash, 독립 paired uncertainty 재계산을 포함한다. 정확한 결과는 `TEST_RESULTS.json`, `VALIDATION.json`, `INDEPENDENT_REVIEW.json`, `PORTABLE_MEMBERSHIP_AUDIT.json`을 참조한다. 기존 frozen evidence는 overwrite하지 않았다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS 실행·수정 및 production promotion은 없다.
'''
    (ROOT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    # Additional diagnostic strata; these are never consulted for selection.
    import sys
    sys.path.insert(0,str(ROOT));import study
    f=pd.read_parquet(ROOT/'PREDICTIONS.parquet');f=f[f.state.eq('RUNNING')].copy()
    f['GPU_bucket']=np.select([f.num_gpus_req.eq(1),f.num_gpus_req.le(4)],['1 GPU','2-4 GPU'],default='>4 GPU')
    rows=[dict(role=r,arm=a,GPU_bucket=b,**study.stats(g)) for (r,a,b),g in f.groupby(['role','arm','GPU_bucket'])]
    pd.DataFrame(rows).to_csv(ROOT/'RUNNING_GPU_METRICS.csv',index=False)
    print('REPORT_COMPLETE',verdict,flush=True)
if __name__=='__main__':main()
