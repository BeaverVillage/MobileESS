"""Post-freeze reporting and portable evidence packaging; no model selection."""
import argparse, subprocess
from study import *

def formatted_table(f, columns):
    output=['| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|']
    for _,r in f.iterrows():
        cells=[]
        for c in columns:
            v=r[c]
            cells.append('—' if pd.isna(v) else f'{v:,.4f}' if isinstance(v,(float,np.floating)) else str(v))
        output.append('| '+' | '.join(cells)+' |')
    return '\n'.join(output)+'\n'

def report():
    need(read(ROOT/'VALIDATION.json')['PASS'],'AUDIT_NOT_PASS')
    need(read(ROOT/'REVIEW_ADDENDUM_VALIDATION.json')['PASS'],'INDEPENDENT_REVIEW_GUARD_FAIL')
    m=pd.read_csv(ROOT/'MODEL_METRICS.csv');d=pd.read_csv(ROOT/'DEVELOPMENT_CALIBRATION_METRICS.csv')
    ci=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');pairs=pd.read_csv(ROOT/'MATCHED_COMPARISONS.csv')
    freeze=read(ROOT/'FINAL_SELECTION_FREEZE.json')
    gates=[]
    for r in m[m.role.eq('MAY_HISTORICAL')&m.arm.ne('R0')].itertuples():
        pair=pairs[pairs.role.eq(r.role)&pairs.state.eq(r.state)&pairs.candidate.eq(r.arm)&pairs.reference.eq('R0')].iloc[0]
        gates.append(dict(role=r.role,state=r.state,arm=r.arm,coverage=bool(r.coverage>=.9),
            GPU_coverage_preferred=bool(r.GPU_coverage>=.9),long_under_preferred=bool(r.long_under<=.15),
            missed_slots_decreased=bool(pair.missed_slots_reduction>0),
            overreserve_below_walltime=bool(r.overreserved_GPUh<r.requested_overreserved_GPUh)))
    verdict=dict(time=now(),TEMPORAL_POLICY_CHANGED=False,NEW_ARCHITECTURE_SEARCHED=False,
        PRODUCTION_REPLACEMENT_SUPPORTED=False,OPTIMIZER_INTEGRATION_READY=False,PRODUCTION_PROMOTED=False,
        selected_by_state=freeze['selected_by_state'],historical_May_gates=gates,
        reason='Neither quantile eligible in both DEVELOPMENT and CALIBRATION; retain R0. May is exposed diagnostic, request-version and ingestion authority UNVERIFIED.',
        target_interface_valid='offline event-time proxy only',optimizer_executions=0,grid_executions=0)
    save('VERDICT.json',verdict)
    text='''# Runtime-vNext2 최종 검토 — Q90 vs Q95 operational bound

**Pending과 Running 모두 R0 유지로 freeze했다. Q95를 채택하지 않는다.** Q90과 Q95 어느 후보도 DEVELOPMENT와 CALIBRATION 양쪽의 필수 coverage·과예약 조건을 통과하지 못했다. May 결과로 선택을 바꾸지 않았다.

이번 작업은 May exposure 이후의 후속 model-development 실험이다. May 및 기존 April evaluation은 historical diagnostic이며 untouched confirmation이 아니다. PR65의 고정 `MULTI_QUANTILE` 예측을 그대로 재사용했다. temporal policy는 180일 history, 14일 recency half-life, 기존 issue마다 refit인 채로 보존됐고, 이번 실행에서 새 학습은 0회이다. 새로운 architecture·feature·hyperparameter·quantile 탐색이나 residual calibration은 없었다.

## 비교와 selection freeze

- R0: 최신 frozen production `ROLLING_Q90_TRACK_P_L2` Q90. Pending은 total runtime이며 Running은 `max(total-elapsed,0)`의 naive remaining reference이다. Running R0를 학습된 remaining 모델이라고 주장하지 않는다.
- R1: PR65 MULTI_QUANTILE **Q90**. Pending total / Running elapsed-conditioned remaining.
- R2: 같은 구조와 같은 fit의 **Q95**. Q95를 Q90으로 재명명하지 않았다.

상태별로 DEV와 CAL **각각** coverage ≥90%, overreserved GPU·h < requested-walltime reference를 만족해야 후보가 된다. 후보 중 GPU coverage ≥90% 및 long-job underprediction ≤15%를 양쪽에서 만족하는 경우를 우선하고, 그다음 낮은 quantile을 택한다. 후보가 없으면 R0 유지다. 최신 R0는 DEV/CAL에서 검증 가능한 artifact가 없어 해당 시기로 역적용하지 않았다. R0 대비 missed-slot 개선은 May diagnostic에서만 보고하며 selection에 사용하지 않았다. R0 유지 판정은 R0가 모든 gate를 충족한다는 뜻이 아니다.

'''
    text+=f"등록 시각: `{read(ROOT/'REGISTRATION.json')['time']}`. 선택 freeze: `{freeze['time']}`. 평가 완료: `{read(ROOT/'EVALUATION_COMPLETE.json')['time']}`.\n\n"
    text+=formatted_table(d,['role','state','arm','coverage','GPU_coverage','long_under','overreserve_vs_requested'])
    text+='''
Q95 Pending은 DEV coverage 96.22%지만 CAL 79.21%로 탈락했다. Q95 Running은 DEV coverage 87.03%이며 DEV/CAL 과예약이 walltime reference의 1.17/2.50배로 탈락했다. Q90도 필수 조건을 충족하지 못했다.

## May historical diagnostic

coverage 및 long_under는 비율, GPU-slots는 15분 GPU-slot 누적 수, reserve는 GPU·h, pinball은 초 단위 평균이다. 아래 표는 각각의 동일 Job-issue 모집단으로 직접 비교한다.

'''
    may=m[m.role.eq('MAY_HISTORICAL')]
    text+=formatted_table(may,['state','arm','nominal_quantile','N','coverage','GPU_coverage','long_under','missed_GPU_slots'])
    text+='\n'+formatted_table(may,['state','arm','overreserved_GPUh','requested_overreserved_GPUh','reserved_GPUh','requested_reserved_GPUh','reserve_vs_requested','pinball_Q90','pinball_Q95'])
    text+='''
Q95 Pending은 coverage 92.80%, GPU coverage 93.83%로 올라가지만 long-job underprediction 16.21%는 선호 기준을 넘고, missed GPU-slots 141,342는 R0의 17,373보다 많다(713.57% 증가). Q95 Running은 coverage 91.22%, long-job underprediction 9.36%이고 R0 대비 missed slots가 87.97% 감소한다. 하지만 GPU coverage 89.49%는 90%에 못 미치며, 과예약 333,653.85 GPU·h는 walltime reference 200,667.57의 **1.66배**다. 안전성 증가만으로 과예약 실패를 무시하지 않는다.

## Paired day/block bootstrap

동일 Job-issue를 pair로 유지하고 관측 issue-day 단위 bootstrap 및 chronological circular 7-issue block bootstrap을 각각 2,000회 수행했다(seed 20260927). coverage, GPU coverage, long under, missed slots, 과예약, 총 reserve, requested 대비 reserve 비율, 두 pinball을 각 resample의 집계값에서 다시 계산했다. 아래 delta는 **candidate − reference**다. 양수 coverage는 개선, 양수 loss/underprediction/slots/reserve는 증가다. 원본 전체 CI는 `PAIRED_UNCERTAINTY.csv`에 있다.

'''
    short=ci[ci.role.eq('MAY_HISTORICAL')&ci.candidate.eq('R2')&ci.block_days.eq(7)&ci.metric.isin(['coverage','GPU_coverage','long_under','missed_GPU_slots','overreserved_GPUh','pinball_Q90','pinball_Q95'])]
    text+=formatted_table(short,['state','candidate','reference','metric','delta','CI95_low','CI95_high'])
    text+='''
CI는 이미 노출된 과거 기간에 대한 조건부 불확실성이다. 오래 지속되는 Job이 여러 issue에 반복되어 7개 issue를 넘는 dependence가 남을 수 있다. April에는 관측하지 않은 날짜가 있으므로 block_days=7은 달력 7일이 아니라 관측 issue 7개다. 통계적으로 안전성 개선이 보여도 DEV/CAL 탈락이나 과예약 실패를 뒤집지 않는다.

## Pending/Running 및 label/maturity audit

Pending target은 실행 대기시간을 제외한 total runtime이며, Running target은 issue부터 종료까지의 remaining runtime이다. Running에는 이미 검증된 log1p(elapsed) feature와 고정 landmark 학습 membership을 사용했다. long-job은 **actual total runtime >4h**로 정의하고 해당 상태의 target에 대한 underprediction을 계산한다. elapsed strata `<1h / 1–2h / 2–4h / 4–8h / >8h`는 `RUNNING_ELAPSED_METRICS.csv`에 모두 보고한다.

67개 inherited issue의 전체 positive-GPU query membership과 training membership을 다시 구성해 NPZ row IDs와 정확히 일치하는지 검증했다. 학습은 `job_end_time < issue_time` 및 180일 lower bound를 지키며 Running landmark Job-ID hash와 support도 재검증했다. 부모의 raw prediction hash와 동일한 Q90/Q95만 읽었고 fit weight를 변경하지 않았다. 67개 issue의 prediction receipt는 새 label join 전에 생성된 부모 증거이다. exact ID 목록은 부모 `JOB_MEMBERSHIP.parquet`, `ISSUE_MEMBERSHIP.parquet`, `fits/LGBM_180_14/*/train_membership.npz`에 그대로 있으며 신규 `CAUSAL_MEMBERSHIP_LEDGER.csv`가 상대경로와 hash를 고정한다.

원본 DEV Pending의 invalid-label 2개는 query membership에서 보존하고 unscorable_N=2로 명시한다. 나머지 DEV/CAL 및 모든 평가 label은 scorable이며, 임의 exclusion은 없다. feature availability는 submit/start event-time proxy에서 검증했으나 historical request 수정 이력과 ingestion/version provenance는 여전히 미확인이다. 따라서 운영 인과성 인증이나 production 승격 근거가 될 수 없다. 완료된 Job만의 학습에 따른 completion selection bias도 부모와 동일하다.

GPU-slots는 runtime-origin 24시간의 predicted-finished/actually-active **proxy**이며 실제 dispatch나 optimizer 출력이 아니다. Pending은 queue wait를 포함하지 않는다. reserve reference는 Pending requested walltime, Running `max(requested-elapsed,0)`이다. 음수 bound repair와 monotone quantile ordering은 부모의 고정 생성 방식이며 이번 실험은 scaling/capping을 추가하지 않았다.

## 최종 판정

```text
TEMPORAL_POLICY_CHANGED = FALSE
NEW_ARCHITECTURE_SEARCHED = FALSE
PRODUCTION_REPLACEMENT_SUPPORTED = FALSE
OPTIMIZER_INTEGRATION_READY = FALSE
PRODUCTION_PROMOTED = FALSE
```

target/interface는 명시된 offline proxy 범위에서 유효하다. 이번에 temporal 효과나 새 architecture 우월성을 시험하지 않았다. 선택 후보가 없어 운영 교체를 지지하지 않으며, May의 일부 안전성 개선도 requested-walltime 대비 과예약과 Pending missed slots 실패를 해결하지 못한다. PR64/65 기존 frozen evidence를 덮어쓰지 않았다. optimizer/MESS/IEEE123/8500/Actual/OpenDSS를 수정하거나 실행하지 않았다.

## 재현·검증 산출물

- `REGISTRATION.json`, `FINAL_SELECTION_FREEZE.json`: 선택 규칙, split/metric 정의와 결정 시각, source hash.
- `DEVELOPMENT_CALIBRATION_METRICS.csv`, `MODEL_METRICS.csv`, `RUNNING_ELAPSED_METRICS.csv`: 상태별 전체 지표.
- `BOUND_PREDICTIONS.parquet`: 이름과 nominal quantile이 보존된 모든 평가 bound·label.
- `PAIRED_UNCERTAINTY.csv`, `MATCHED_COMPARISONS.csv`: paired CI 및 R0/후보 비교.
- `CAUSAL_MEMBERSHIP_LEDGER.csv`, `VALIDATION.json`, `PARENT_PRESERVATION_START/END.json`: 정확한 inherited membership과 부모 무결성.
- `TEST_RECEIPT.json`, `SCIENTIFIC_REVIEW.json`, `DELIVERY_MANIFEST.json`: 단위 검증, 독립 검토, byte-level 배포 seal.

![Q90/Q95 coverage와 과예약 비교](COMPARISON.png)
'''
    text+='\n독립 검토의 missing preference 지표 처리 한계와 보완 검증은 [검토 addendum](REVIEW_ADDENDUM_KO.md)에 공개했다. 실제 선택 지표는 모두 finite이며 frozen 선택에 영향이 없다. 별도 guard가 이를 fail-closed로 확인한다. 감소율 CI는 `MISSED_SLOT_REDUCTION_UNCERTAINTY.csv`에서 확인한다. May Q95 대비 R0의 7-issue block 감소율 CI는 Pending −20.2771~−1.5382, Running 0.8016~0.9736이다(비율 단위, 음수는 증가).\n'
    (ROOT/'FINAL_REVIEW_KO.md').write_text(text,encoding='utf-8')
    print('REVIEW_WRITTEN',flush=True)

def package():
    need(read(ROOT/'VALIDATION.json')['PASS'],'VALIDATION_FAIL')
    need(read(ROOT/'REVIEW_ADDENDUM_VALIDATION.json')['PASS'],'REVIEW_ADDENDUM_FAIL')
    need(read(ROOT/'SCIENTIFIC_REVIEW.json')['PASS'],'REVIEW_NOT_PASS')
    files=[]
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts or p.name=='DELIVERY_MANIFEST.json':continue
        files.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size))
    save('DELIVERY_MANIFEST.json',dict(time=now(),files=files,parents=dict(PR=65,commit='d3ec564854f65f62b3587f49c857d2f86575ad2c',
        delivery_sha256=sha(BASE/'DELIVERY_MANIFEST.json'))))

def verify():
    manifest=read(ROOT/'DELIVERY_MANIFEST.json')
    for r in manifest['files']:need(sha(ROOT/r['path'])==r['sha256'],'DELIVERY_DRIFT '+r['path'])
    parent=read(BASE/'DELIVERY_MANIFEST.json')
    need(sha(BASE/'DELIVERY_MANIFEST.json')==manifest['parents']['delivery_sha256'],'PARENT_MANIFEST_DRIFT')
    for r in parent['files']:need(sha(BASE/r['path'])==r['sha256'],'PARENT_DRIFT '+r['path'])
    print('PORTABLE_DELIVERY_PASS',len(manifest['files']),'parent_files',len(parent['files']),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['report','package','verify']);args=parser.parse_args();globals()[args.stage]()
