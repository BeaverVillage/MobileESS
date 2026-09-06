"""Package evidence, honest protocol exceptions, and the Korean final review."""
from .common import *
from .backtest import PREREG, registration
import sys

def read(name):
    return json.loads((OUT/name).read_text(encoding='utf-8'))

def protected_scope():
    paths=sorted(set(git('-c','core.quotepath=false','diff','--name-only',START).splitlines()+git('-c','core.quotepath=false','ls-files','--others','--exclude-standard').splitlines()))
    allowed=('dayahead/v40p/','dayahead/artifacts/v40p_lightgbm_forecast_forensic/')
    outside=[p for p in paths if not p.startswith(allowed)]
    assert not outside, outside
    report={'starting_commit':START,'compared_worktree_HEAD':git('rev-parse','HEAD'),'verification':'Entire tracked diff from starting commit plus untracked files is confined to two V40P prefixes; no protected contents opened for this check','allowed_prefixes':allowed,'changed_paths':paths,'outside_scope_changes':outside,'protected_unchanged':{n:True for n in ['V40I','V40J','V40K','V40L','V40M','V40N','K0','T7','runtime model','runtime q','production forecast models','production features','production adapters','optimizer','electrical coefficients']},'V40N_content_accesses':0,'holds':read('V40P_START_STATE.json')['integrity_holds']}
    dump('V40P_PROTECTED_SCOPE_DIFF.json',report)
    return report

def firewall():
    log=[json.loads(s) for s in (OUT/'access_log.jsonl').read_text(encoding='utf-8').splitlines()]
    raw=read('job_identity_and_availability_evidence.json')
    report={
      'strict_zero_scientific_read_gate':'FAIL',
      'MAY_SCIENTIFIC_OUTCOME_READS':2,
      'counter_unit':'Distinct source files with embedded May scientific outcome snippets exposed in an initial broad source search; NOT number of data records',
      'MAY_SCIENTIFIC_OUTCOME_DATA_FILE_READS':0,
      'MAY_SCIENTIFIC_OUTCOME_DATA_ROWS_DECODED':0,
      'MAY_METADATA_CODE_DISCOVERY':'NONZERO',
      'incident':{'id':'INITIAL_SOURCE_SEARCH_EXPOSURE','source_files':['dayahead/v40i/may01_forensic.py','dayahead/v40i/pending_forensic.py'],'search_calls':1,'exact_snippet_count':'not retained; at least two files exposed','description':'A broad rg search returned hard-coded May result summaries embedded in source. This is scientific exposure even though no May result dataset was opened. Disclosed to user immediately; numerical values are deliberately not copied here.','used_for_V40P_model_assessment_or_tuning':False,'remediation':'Restricted later reads to explicit source allowlists, immutable model artifacts, footer-only inspection and physically segregated pre-May row groups; cannot undo prior exposure'},
      'data_firewall':{'method':'Do not decode a mixed May group then filter. Require physical timestamp-max metadata plus 245-minute forecast-window margin for aggregate data. Raw jobs require submit/start/end maxima before May, archive members February 2024 through March 2025 only.','raw_members_opened':len(raw['opened_members']),'cross_May_raw_groups_skipped':len(raw['skipped_cross_May_groups']),'latest_primary_origin':'2025-04-24T14:55:00Z','access_log':'access_log.jsonl','logged_operation_counts':pd.Series([r['kind'] for r in log]).value_counts().to_dict()},
      'derived_label_dependency_limit':'Pre-May aggregate GPU-hour labels contain complete future runtime. Row-window checks alone cannot prove that every contributing job completed before May. This availability flaw is an audit finding, not a claim that the derived dependency firewall is complete.',
      'metadata_examples':['dayahead/v37/context.py','dayahead/v37/aidc_materializer.py','dayahead/v39a/power.py','dayahead/v40a/context.py','historical artifact manifests and parquet footers'],
      'no_May_tuning':True,'FULL_MAY':'NO','V40N_content_reads':0,
      'interpretation':'Do not report this run as fully compliant with MAY_SCIENTIFIC_OUTCOME_READS=0. A clean-room repeat would be required for that protocol claim.'}
    dump('V40P_MAY_READ_FIREWALL.json',report)

def summary_rows(phase):
    parts=[]
    for track,name in [('A','FUTURE_ARRIVAL'),('B','FIXED_LOAD')]:
        f=pd.read_csv(OUT/f'V40P_{name}_METRICS.csv')
        parts.append(f.loc[f.phase.eq(phase)&f.fold.eq('POOLED')&f.method.eq('prediction')])
    return pd.concat(parts).sort_values(['track','horizon_minutes'])

def table(phase):
    lines=['| Track | Horizon | Model | Baseline | MAE | WAPE | Bias | Underprediction | GPUh shortfall | Baseline skill | Verdict |','|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|']
    for r in summary_rows(phase).itertuples():
        model='Tweedie ×0.5' if r.track=='A' else 'Persistence' if r.horizon_minutes==15 else 'Persistence + residual'
        short=f'{r.shortfall:,.1f}' if r.track=='A' else 'N/A'
        lines.append(f'| {r.track} | {r.horizon_minutes}분 | {model} | {"A0 zero" if r.track=="A" else "B0 persistence"} | {r.MAE:.4f} | {100*r.WAPE:.4f}% | {r.bias:.4f} | {100*r.underprediction_rate:.2f}% | {short} | {100*r.skill_MAE:+.6f}% | 누출 / {"우월성 없음" if r.track=="A" else "동일" if r.horizon_minutes==15 else "조건부 개선"} |')
    return '\n'.join(lines)

def review():
    registration()
    tests=read('V40P_TEST_REPORT.json')
    frozen=summary_rows('FROZEN_2025_PREMAY')
    clone=summary_rows('DIAGNOSTIC_CLONE')
    skills=read('V40P_BASELINE_SKILL_REPORT.json')['primary_comparisons']
    lines=[
      '# V40P LightGBM forecast forensic — 최종 검토',
      '',
      '**최종 판정: `V40P_FORECAST_CAUSALITY_FAIL`.**',
      '',
      '1. **Future-arrival 예측은 충분하지 않다.** 고정 모델 5개 모두 WAPE가 약 100%이고 zero baseline 대비 MAE skill이 0 이하이다. 240분에서 겹치는 예측 창의 실제 GPUh 합 6,695,270에 대해 예측 합은 82.75에 그친다.',
      '2. **Fixed-load는 제한적인 오차 개선만 확인된다.** 30–240분에서 persistence 대비 MAE가 1.80%, 3.07%, 5.11%, 9.62% 줄었지만, 240분 WAPE 46.53%와 입력 누출 때문에 causal predictor로 검증되지 않았다. 15분은 persistence 그 자체이다.',
      '3. **미래누설이 있다.** 177개 feature 중 70개 FUTURE_LEAKAGE, 20개 TIMESTAMP_AMBIGUOUS. 60개 rolling 입력은 원점 이후 5분 bin을 포함하고, 10개 도착 GPUh lag는 아직 완료되지 않은 job의 실제 전체 runtime을 사용한다.',
      '4. **Baseline 우월성은 A에서 입증되지 않는다.** B의 조건부 MAE skill 95% CI는 30분 [1.14, 2.52]%, 60분 [1.97, 4.21]%, 120분 [3.22, 6.96]%, 240분 [6.41, 12.66]%. 입력과 comparator가 같은 retrospective state를 쓰므로 이 CI는 실제 운영 우월성 증명이 아니다.',
      '5. **절대 오차가 가장 큰 horizon은 양쪽 모두 240분이다.** A MAE 204.5986 GPUh, B MAE 22.0773 average GPU. 절대 MAE 최소는 15분(A 12.7460, B 5.2417)이다. A는 target mass가 horizon에 따라 커져 단순 MAE만으로 모델 질을 비교할 수 없다. 정규화 skill 기준 A의 덜 나쁜 값은 120분, 가장 나쁜 값은 30분이지만 모두 사실상 zero 수준이다. B 상대 skill 최고는 240분이다.',
      '6. **Underprediction 위험이 크다.** A는 모든 양수 target 창에서 실제보다 작게 예측하며 normalized shortfall은 99.9995–100.0000%다. B 240분 bias는 −8.3236 GPU, normalized shortfall은 32.04%다. 전체 행의 A underprediction rate가 7.61–43.14%로 낮아 보이는 이유는 zero actual이 56.86–92.39%이기 때문이다.',
      '7. **Burst를 놓친다.** frozen 60/120/240분의 train-q95 burst recall은 0%; positive-only train-q95 기준 5개 horizon 모두 recall 0%다. 15/30분 전체 q95=0에서는 아주 작은 양수 예측 때문에 recall 100%로 집계되지만 precision은 7.61%/12.70%이고 실제 burst mass를 거의 포착하지 못한다.',
      '8. **분포 변화가 있다.** 안전하게 읽은 원시 job 부분집합에서 GPU/job 중앙값 4→1, 요청 walltime 중앙값 3,600→7,200초, partition TV 0.05959, QoS TV 0.01257. GPU/job Wasserstein 2.6694, walltime Wasserstein 21,197.4초. 제외된 row group이 있어 전체 모집단의 불편 추정이나 변화의 인과효과로 해석하지 않는다.',
      '9. **현재 모델을 검증된 논문·Day-Ahead 입력으로 그대로 승인할 근거가 없다.** 원본은 재현 목적의 frozen artifact로 유지하되 검증 완료라고 주장할 수 없다. 실제 현재 V40A planning context는 V37 known-job ledger + V39A power 구성이며 이 15–240분 K5B2 predictor를 호출하지 않는다.',
      '10. **다음 revision이 필요하다.** 예측 발행 시각, 관측 가용 시각, 완료 runtime label 지연, fixed/flexible 계약부터 수정 설계하고 새 untouched temporal holdout을 사전 확보해야 한다. 이번 V40P에서는 production 변경을 수행하지 않았다.',
      '',
      '## 평가 범위와 요약',
      '',
      'Frozen 평가: 2025-01-01 00:00–2025-04-24 14:55 UTC, 각 head N=32,724. 개발 구간 2024-02-29 23:00–2024-12-31 19:55 UTC, N=88,044. 2025 block은 과거 frozen/monthly 평가 이력이 있어 untouchedness를 증명할 수 없으므로 A/B 모두 `TRUE_FROZEN_HOLDOUT_AVAILABLE=NO`이다. 과거 평가가 있었다는 사실만으로 test-driven tuning이 있었다고 단정하지 않는다.',
      '',table('FROZEN_2025_PREMAY'),'',
      'A의 MAE/Bias는 GPUh, B는 5분 bin 평균 active GPU이다. WAPE/underprediction/skill은 %. A shortfall 합은 겹치는 forecast window를 합친 수치로 실제 소비 에너지 총량이 아니다. B shortfall은 GPU 단위 오차 합이므로 GPUh 칸은 N/A로 둔다. 모든 행은 누출 게이트를 실패한다.',
      '',
      '## 복원된 구현과 시간 계약',
      '',
      'Primary A와 B는 모두 Kestrel H100 COMPLETED/non-standby cohort이다. Eagle fixed + Kestrel flexible 구성이라는 설명은 이 구현과 다르다. F30은 실제 runtime≥30분 및 실제 queue wait≥15분; fixed는 그 여집합이다. A의 GPUh는 요청 GPU 수 × 실제 전체 실행시간이며 requested-walltime GPUh, 실행창 내부 에너지, 실제 power가 아니다.',
      '',
      '행 timestamp를 t0로 쓰는 코드에서 A target은 submission-bin index 1..h의 누적량, 즉 [t0+5분, t0+H+5분)이다. B는 [t0+H, t0+H+5분)의 평균 fixed active GPU다. H=15/30/60/120/240분. 보통의 [t0,t0+H)나 순간 부하로 표기하면 틀린다. 모든 10개 target을 시계열에서 직접 재구성해 일치를 확인했다. t0를 5분 늦추면 current-bin peeking은 줄지만 실제 runtime 완료 지연 누출은 남는다.',
      '',
      'UTC 저장, Australia/Melbourne AEST/AEDT calendar, 원본 America/Denver 표시/수치 UTC offset을 구분했다. 현재 Day-Ahead D-1 18:00은 fixed AEST(UTC+10)로 별도 계약이다. 12개 IDC 배분, 별도 power/inference trace를 결합한 synthetic 구성이고 하나의 실측 Melbourne 시설 ground truth로 주장할 수 없다.',
      '',
      'A는 5개의 Tweedie p=1.7, frozen scale=0.5, 788/826/846/997/978 trees. B15는 persistence; B30/60/120/240은 residual L1 34/47/62/42 trees를 현재 fixed bin에 더하고 0으로 하한 clipping한다. 별도의 event classifier 5개는 point forecast에 곱하지 않는다. 177개 numeric float32 feature, scaler/encoder 없음. 모델·feature 순서·objective·출력 scale은 변경하지 않았다.',
      '',
      '기존 V28 daily LGBM과 V28R2 P/G/W quantile 24개도 별도 inventory/SHA 검증했다. V28 D-1 full-day GPUh 및 7/14일 통계 4개 feature는 D-1 18:00 이후를 포함한다. V28R2 P_REF는 ESIF IT kW, G_REF는 Kestrel GPU, W는 strict full-node node-hours여서 15–240분 A/B와 target·unit이 다르다. P_REF를 fixed GPU load 또는 PUE target이라고 부르면 안 된다. V28R2 reference residual subtraction과 현재 V40A known-job/power 경로도 분리해 기록했다.',
      '',
      '## 가용성·중복·일관성',
      '',
      '안전한 raw 405,777 jobs 중 F30 18,031개 모두 submission-bin+5분 시점에는 전체 actual GPUh를 알 수 없었다. 이 가용 시각 이후 지연의 중앙값 11.879시간, P95 67.299시간이다. fixed 387,746/flexible 18,031의 retrospective job-ID 중복은 0이고 모든 aggregate 행에서 fixed+flex=total을 확인했다. 이것이 causal partition을 의미하지는 않는다.',
      '',
      'Known submit≤t0와 future target submission window를 독립 raw job ID로 212개 원점에서 검사해 중복 0을 확인했다. 단 (t0,t0+5분) target gap이 있고, legacy aggregate와 현재 ledger 사이 공통 job-ID 인터페이스가 없어 전체 downstream 결합의 완전한 무중복을 보증할 수 없다. 현재 V40A closed cohort에는 아직 submit하지 않은 arrival component가 없다.',
      '',
      '누적 target의 실제 horizon crossing은 0. Frozen 예측 crossing 행은 30,682/32,724=93.760%, clone은 19,317/26,061=74.122%. 허용오차 1e-9로 계산하고 출력을 보정하지 않았다. Frozen 값이 거의 0이므로 crossing 비율만으로 큰 물리적 오차 크기를 뜻하지는 않는다.',
      '',
      '## 사전등록 진단 backtest',
      '',
      f'진짜 사전등록 commit은 `{PREREG}`. 앞선 `2aa8b0d`는 scaffold commit이고 prereg artifact가 포함되지 않았으므로 사전등록으로 세지 않았다. Phase A frozen inference를 먼저 수행한 뒤 prereg JSON/MD를 commit했으며 그 이후에만 fit을 시작했다.',
      '',
      'F1=2024-09, F2=2024-11, F3=2025-03의 서로 겹치지 않는 3개 fold, 총 27개 clone fit. 각 fold train max timestamp+245분 < evaluation start, evaluation origin+245분 < fold end를 강제했다. Clone N=26,061/head. 원본에서 선택된 tree 수·objective·features·scale 고정, early stopping/tuning 없음. F1/F2 spec은 이후 2024 validation에서 선택된 것이므로 nested prospective CV가 아니다. 실제 runtime label availability는 여전히 실패하므로 timestamp purge만으로 미래 학습 정보 배제를 입증하지 못한다.',
      '',
      '| Horizon | Clone A MAE / skill | Clone B MAE / skill |',
      '|---:|---:|---:|']
    for h in [15,30,60,120,240]:
        a=clone.loc[clone.track.eq('A')&clone.horizon_minutes.eq(h)].iloc[0];b=clone.loc[clone.track.eq('B')&clone.horizon_minutes.eq(h)].iloc[0]
        lines.append(f'| {h}분 | {a.MAE:.4f} / {100*a.skill_MAE:+.4f}% | {b.MAE:.4f} / {100*b.skill_MAE:+.4f}% |')
    lines += ['', 'Clone A240 skill 0.659%의 CI는 [−0.150%, 1.775%]여서 우월성을 입증하지 못한다. Clone B30–240 CI는 모두 양수이나 동일한 causal 한계가 있다. UTC 일별 block, fold별 stratification, 2,000회 bootstrap, seed 20260906 사용. A1 recent rate 및 daily/weekly seasonal은 realized mark 가용성이 입증되지 않아 보조적 retrospective comparator이며 A0 zero만 확실한 causal baseline이다.','',
      'Burst cutoffs는 원본 development 또는 각 clone training target에서만 계산했다. 2025 test/May로 threshold를 고르지 않았다. 모든 MAE/RMSE/WAPE/bias/shortfall CI, fold별/보조 baseline 지표, burst precision/recall·최악 10개 창, underprediction streak는 개별 JSON/CSV에 있다.','',
      '기존 K5C2 adapter와 저장된 GPU–kW 쌍으로 coefficient 0.4525064517 kW/GPU를 확인해 B incremental IT error만 환산했다. 이 coefficient의 upstream 대표 utilization은 전체 site data 평균을 사용하므로 train-only power preprocessing이 아니다. 새로운 mapping은 만들지 않았으며 현재 V40 electrical 식에 옮기지 않았다. A 누적 도착 GPUh는 실행 profile 없이 순간 kW로 바꿀 수 없다.','',
      '## 무결성·검사·제한', '',
      'May protocol에는 명백한 예외가 있다. 초반 광범위 소스 검색이 V40I 두 파일의 코드에 박힌 May 결과 문구를 노출했다. `MAY_SCIENTIFIC_OUTCOME_READS=2`는 노출 파일 수이며, May 결과 data-file read 및 decoded data-row는 각각 0이다. May code/metadata discovery는 NONZERO. 해당 결과값을 V40P 평가·튜닝에 사용하지 않았지만 엄격한 zero-read gate는 FAIL로 기록한다. 원점이 pre-May인 derived label도 전체 runtime이 May 전에 완료되었는지는 전부 입증하지 못한다. 따라서 이 run을 May firewall 완전 준수로 표현하지 않는다.', '',
      f'자동검사 {tests["tests_run"]}개: {tests["passed"]} 통과, {tests["expected_scientific_failures"]}개 과학적 게이트 실패, 예기치 않은 실행 실패 {tests["unexpected_failures"]}개. 실패 gate는 #11 no future feature timestamps, #12 rolling right edge, #27 May zero-read이다. 소프트웨어가 예상한 누출을 검출했다는 것과 과학적 타당성이 통과했다는 것을 구분한다.', '',
      'Phase A는 10개 output head에서 feature order 일치, deterministic 차이 0, 저장 prediction과 최대 차이 1.1368683772161603e-13. Primary 14+historical 24=38개 model SHA 일치. 두 V40P prefix 외 변경이 없다는 전체 Git diff allowlist 검사로 V40I/J/K/L/M/N, K0/T7/runtime/q/production model·feature·adapter/optimizer/electrical 불변을 확인했다. V40N source/worktree/artifact 내용은 읽지 않았다.', '',
      '진단 실행 중 Decimal/UTF-8 및 mixed datetime 직렬화 오류를 수정했다. 최초 27 fit 이후 예측 직렬화를 재개할 때 모델 SHA를 검증하고 저장 clone을 재사용했으며 spec·fold·baseline·parameter를 바꾸거나 결과에 맞춰 재학습하지 않았다. Resume receipt elapsed_seconds는 재개 inference 시간을 나타낼 수 있어 순수 fit 시간으로 해석하지 않는다.', '',
      'Integrity holds: `31_DAY_ELECTRICAL_REGENERATION=HOLD`, `B0/B1/B2/B3=NO`, `FULL_MAY=NO`, `PF=0.95`, `Q control=NO`. Runtime-tail 및 72-case replay semantics 변경 없음.', '',
      '## NEXT_REVISION_RECOMMENDATION — 구현하지 않음', '',
      '1. Submit/start/completion별 available_at 계약과 원점의 좌·우경계를 명시하고 causal snapshot builder를 설계한다. 실제 완료 runtime을 과거에 즉시 알았던 것처럼 쓰지 않는다.',
      '2. COMPLETED-only 생존/완료 cohort와 F30 사후 분류가 목표 deployment population과 맞는지 재정의한다.',
      '3. 모델 선택·calibration·최종 검증을 분리하고 아직 사용하지 않은 temporal block 및 facility boundary를 사전등록한다. May zero-read 주장은 별도 clean-room 검토가 필요하다.',
      '4. A의 zero-dominated loss, magnitude shortfall, 실제 burst capture와 horizon consistency를 다음 revision의 평가 계약으로 삼는다. 이번에는 objective·family·scale·output repair를 바꾸지 않았다.',
      '5. 현 Day-Ahead closed-cohort와 future-unsubmitted forecast 연결 여부, known/future job identity interface 및 power residual decomposition을 별도 설계 검토한다.', '',
      '## Commit와 model SHA', '',
      f'- Branch: `{git("branch","--show-current")}`',
      f'- Worktree: `{ROOT}`',
      f'- Starting commit: `{START}`',
      f'- Preregistration commit: `{PREREG}`',
      '- Final research commit: `V40P_FINAL_COMMIT_RECEIPT.json`의 final_research_commit. 자신의 SHA를 포함할 수 없으므로 receipt는 별도의 후속 commit으로 저장한다.', '',
      '| Track/head | SHA256 |', '|---|---|']
    census=read('V40P_MODEL_SOURCE_CENSUS.json')
    for r in census['models']:
        lines.append(f'| {r["model_id"]} | `{r["model_SHA256"]}` |')
    lines += ['', 'B15 persistence에는 serialized model/SHA가 없다. V28/V28R2의 나머지 24개 SHA와 full ledger는 V40P_MODEL_SHA_VERIFICATION.json 및 V40P_MODEL_SOURCE_CENSUS.json에 있다. 모든 요구 artifact는 같은 V40P artifact 디렉터리에 있다.', '']
    (OUT/'V40P_FINAL_REVIEW.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    dump('V40P_SCIENTIFIC_CLASSIFICATION.json',{'track_A':'FUTURE_ARRIVAL_FORECAST_LEAKAGE_FOUND','track_B':'FIXED_LOAD_FORECAST_LEAKAGE_FOUND','final':'V40P_FORECAST_CAUSALITY_FAIL','secondary_A':['BASELINE_NOT_BETTER','UNDERPREDICTION_RISK'],'secondary_B':['CONDITIONAL_BASELINE_IMPROVEMENT','UNDERPREDICTION_RISK_240MIN'],'true_frozen_holdout_A':'NO','true_frozen_holdout_B':'NO','May_protocol':'FAIL_SOURCE_EXPOSURE','production_changes':False})

def main():
    protected_scope();firewall()
    if '--review' in sys.argv:review()
    print('V40P packaging updated; strict May gate remains FAIL.')

if __name__=='__main__':main()
