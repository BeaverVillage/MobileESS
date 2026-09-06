"""Reporting and immutable evidence closeout only. No model fitting."""
import re
import sys
import xml.etree.ElementTree as ET
from .common import *
from .receipt import stage_commit

def required():
    request=(OUT/'USER_REQUEST.txt').read_text(encoding='utf-8')
    section=request.split('# 47. REQUIRED ARTIFACTS')[1].split('# 48. MINIMUM TESTS')[0]
    return re.findall(r'^V40S5_[A-Z0-9_]+\.(?:json|parquet|csv|md)$',section,re.M)

def protected():
    initial=read('PROTECTED_SCOPE_START')['entries'];current=tree('HEAD')
    changed=[p for p,v in initial.items() if current.get(p)!=v]
    working=git('diff','--name-only',BASE).splitlines()
    outside=[p for p in working if not allowed(p)]
    assert not changed and not outside
    assert file_sha(SOURCE)==SOURCE_SHA
    reference=read('S4_REFERENCE_FREEZE')
    for p,h in reference['owned_SHA256'].items():assert file_sha(ROOT/p)==file_sha(S4ROOT/p)==h
    assert git('status','--porcelain',cwd=S4ROOT)=='' and git('rev-parse','HEAD',cwd=S4ROOT)==BASE
    for p in read('PROTECTED_SCOPE_START')['S3_preserved_paths']:
        assert (ROOT/p).read_bytes()==git('show',f'{REC3}:{p}',binary=True)
    write('PROTECTED_SCOPE_END',dict(timestamp=now(),base=BASE,inherited_entries_checked=len(initial),unchanged_entries=len(initial),
      S4_owned_bytes_verified=106,S3_bytes_verified=109,S4_worktree_clean=True,source_SHA256=SOURCE_SHA,
      operational_files_unchanged=['dayahead/v37/aidc_materializer.py','dayahead/v40a/initial.py'],
      systems_unchanged=['A0','A1','M1','MF','RUNNING','RUNNING migration','PENDING migration','WAN','Rack','terminal','MESS route','MESS P/Q','Fresh OpenDSS','AC restoration','event trigger','local repair','rolling MPC','second route search'],holds=HOLDS))
    write('PROTECTED_SCOPE_DIFF',dict(status='PASS',inherited_entries_changed=changed,working_paths_outside_allowed=outside,
      all_changes_within_allowed=True,inherited_entries=len(initial),S4_owned=106,S3_preserved=109))

def test_report():
    root=ET.parse(OUT/'V40S5_TEST_JUNIT.xml').getroot()
    suites=list(root.iter('testsuite'))
    counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','errors','failures','skipped']}
    assert counts['failures']==0 and counts['errors']==0 and counts['skipped']==0
    names=[v.attrib['name'] for v in root.iter('testcase')]
    request=(OUT/'USER_REQUEST.txt').read_text(encoding='utf-8')
    section=request.split('# 48. MINIMUM TESTS')[1].split('# 49. REPRODUCIBILITY')[0]
    checks=re.findall(r'^(\d+)\. (.+)$',section,re.M)
    assert len(checks)==87
    coverage=[]
    # A single parametrized pytest case may verify several contractual requirements.
    groups=[(1,6,'exact_lineage_and_isolation;original_s4_and_s3_immutable;no_out_of_scope_differences'),
      (7,12,'source_counts_recomputed_independently;proof_mature_unique_exact_runtime;preprocess_future_and_duplicate_jobs_rejected'),
      (13,14,'training_separate_from_exact_s4_panel'),(15,23,'exact_features;excluded_predictors_cannot_change_transform;preprocessing_exact_train_only;unknown_missing_and_medians'),
      (24,25,'historical_split_and_tuning;boundary_timestamp_is_never_split'),(26,28,'all_fits_preregistered_and_historical'),
      (29,32,'saved_predictions_exact_metrics_and_comparators;monotone_repair_and_physical_floor_exact'),
      (33,35,'residual_oof_row_level_evidence;saved_predictions_exact_metrics_and_comparators'),(36,45,'uarp_exact_both_terms_and_no_request_cap;saved_predictions_exact_metrics_and_comparators'),
      (46,52,'metrics_independent_arithmetic;saved_predictions_exact_metrics_and_comparators'),(53,55,'daily_gate_support_boundary;gate_inclusivity_strict_anchor_improvement_and_no_upper_gate;selection_and_exposed_gates_independently'),
      (56,58,'candidate_selection_uses_dev_cal_minimum_and_never_exposed;selection_commit_precedes_exposure_and_no_model_changes'),
      (59,61,'walltime_removal_preserves_every_other_encoded_column;pw_and_unique_job_are_diagnostic_only'),
      (62,84,'firewalls_and_current_holds;scientific_sources_have_no_operational_imports;original_s4_and_s3_immutable;no_out_of_scope_differences'),
      (85,85,'reproducibility_actual_independent_models')]
    for number,description in checks:
        i=int(number)
        if i<=85:
            methods=next(m for lo,hi,m in groups if lo<=i<=hi)
            assert all(any(m in n for n in names) for m in methods.split(';'))
            coverage.append(dict(check=i,description=description,status='PASS',pytest_methods=methods))
        else:coverage.append(dict(check=i,description=description,status='VERIFIED_AT_FINAL_RECEIPT',method='closeout.verify after receipt commit'))
    write('TEST_REPORT',dict(status='PASS',pytest=counts,passed=counts['tests'],runtime_seconds=sum(float(s.attrib.get('time',0)) for s in suites),
      command='python -B -m pytest -q tests/dayahead/test_v40s5_core.py tests/dayahead/test_v40s5_evidence.py -p no:cacheprovider --junitxml=.../V40S5_TEST_JUNIT.xml',
      minimum_requirement_count=87,minimum_check_coverage=coverage,closure_checks_86_87='Final receipt verifier; no self-referential clean claim in a dirty worktree',
      test_names=names,prefit_unit_tests_passed=24,prefit_non_scientific_erratum='V40S5_PREFIT_IMPLEMENTATION_ERRATUM.json'))

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])

def fmt(x):return f'{x:,.3f}'
def pct(x):return f'{x*100:.2f}%'

def review():
    a=read('HISTORICAL_TRAINING_LIBRARY_AUDIT');h=read('HYPERPARAMETER_FREEZE');s=read('SELECTION_FREEZE');e=read('EXPOSED_RESULTS');c=read('COMPUTE_LEDGER')
    text=[f"FINAL CLASSIFICATION: {e['classification']}\nSELECTED MODEL: NONE\nSELECTED LIGHTGBM CONFIG: {h['selected']}\nHISTORICAL TRAINING JOBS: {a['D_exact_unique_training_jobs']}\nQ50 MODEL: LightGBM quantile 0.50 / L2\nQ90 MODEL: LightGBM quantile 0.90 / L2\nQ95 MODEL: LightGBM quantile 0.95 / L2\nQ99 MODEL: LightGBM quantile 0.99 / L2\nUNCERTAINTY MODEL: LightGBM regression / historical OOF squared residuals\nUARP-STYLE CANDIDATE: Q99 + max(0.20*Q99, 0.50*sigma)\nDEV SAFETY: FAIL\nCAL SAFETY: FAIL\nEXPOSED SAFETY: FAIL (no selected candidate; all fixed candidates fail)\nEFFICIENCY VS REQUESTED WALLTIME: PASS alone, safety FAIL\nCURRENT RSP REPLACED: NO\nOPTIMIZER INTEGRATION: NO\nPRODUCTION READY: NO\n"]
    text += [f"지정된 S4 scientific {SCI4}, receipt {BASE}, S3 scientific {SCI3}, receipt {REC3}를 Git에서 해석하고 순차 조상 관계를 검증했다. S4 분류와 모든 선택 NONE, optimizer integration NO를 보존했다. 상속 Git 항목은 실제 5,459개이며, S4가 보존했던 5,352개에 S4의 107개 경로(과학 파일 106개와 최종 receipt)가 더해진 수다. S4 106개 과학 파일과 S3 109개 파일의 바이트를 확인했다.",
      f"원본 {a['source_rows']:,}행 / {a['source_unique_jobs']:,}개 고유 작업, 양의 runtime {a['positive_runtime_jobs']:,}, 0초 {a['zero_runtime_jobs']:,}, 음수 0개. end < cutoff 작업은 {a['A_jobs_end_before_cutoff']}개, end >= cutoff는 {a['B_jobs_end_at_or_after_cutoff']:,}개다. cutoff 이전 0초 4개를 제외한 feature 구성 가능 학습 작업은 정확히 421개다. cutoff는 2025-03-14T08:00:00Z이며, 421개 모두 엄격한 end < cutoff를 만족한다.",
      f"학습 자료의 earliest/latest submit은 {a['earliest_submit']} / {a['latest_submit']}, earliest start는 {a['earliest_start']}, latest end는 {a['latest_end']}다. 월별 학습 수는 2025-03: 421이다. 원본 노출 자료가 시작되는 첫날의 약 8시간에 한정된 mature 표본이며, 장시간 실행 중 작업이 이 cutoff까지 완료되지 못하는 선택 효과가 있다. 이는 관측 범위에서 추론되는 한계이며 완전한 과거 scheduler history가 아니다.",
      "TRAINING_LIBRARY_FULL_BACKLOG_AUTHORITY=NO; TRAINING_LIBRARY_COMPLETE_CASE_SELECTION_LIMITATION=YES. 기존 exposed terminal-service complete-case 원본의 한계와 검증되지 않은 backlog/censoring을 유지한다. 미래 완료 라벨을 끌어오거나 과거 원본을 새로 추정하지 않았다.",
      '가정은 D1_SCHEDULER_REQUEST_STATE_PROXY_V1이다. HISTORICAL_D1_SNAPSHOT_PROVENANCE=UNVERIFIED, ORIGINAL_SUBMISSION_VALUE_PROVENANCE=UNVERIFIED, REQUEST_MODIFICATION_HISTORY=UNOBSERVED. 논문용 명칭은 ASSUMPTION-BASED TRACE-DRIVEN RUNTIME MODEL이다.',
      'Track P feature: '+', '.join(FEATURES)+'. 5개 request 양은 log1p, partition/qos는 historical-only vocabulary 및 UNKNOWN one-hot, numeric missing은 과거 median+indicator다. 실제 학습 자료 결측/invalid는 모든 feature에서 0이다. user/account/job/application identity, 실제 start/end/runtime/status, K0/reference_safe, 미래 상태·migration·전기 결과는 predictor에서 제외했다. RSP와 GPU 평가 가중치는 별도 읽기 전용 비교 값이다.',
      table(['학습 분포','median','P90','P95','P99'],[[key,*[fmt(a['distributions'][key][k]) for k in ['median','P90','P95','P99']]] for key in ['runtime_seconds','requested_seconds','num_gpus_req','actual_request_ratio']]),
      '학습 partition/QoS 빈도: '+json.dumps(a['categorical_frequencies'],ensure_ascii=False)+'.',
      '시간순 HIST_FIT/HIST_TUNE는 332/89개다. 80% 경계의 동일 end timestamp 블록 전체를 HIST_TUNE에 넣었다. 전처리는 tuning용 HIST_FIT, 각 OOF의 이전 fold, 최종 전체 historical library에 각각 별도로 fit했다. PENDING TRAIN 1,190행은 모델 학습에 사용하지 않았으며 DEV 4,346 / CAL 2,634 / EXPOSED 2,713 job-issue의 S4 파일 바이트와 ID는 동일하다. 학습 작업과 PENDING 평가 작업의 중복은 0이다.',
      table(['설정','normalized pinball mean','Q50 pinball','Q90','Q95','Q99'],[[r['config'],*[fmt(r[k]) for k in ['mean_normalized_pinball','Q50_pinball','Q90_pinball','Q95_pinball','Q99_pinball']]] for r in h['results']]),
      '선택 L2: num_leaves=31, learning_rate=.02, n_estimators=800, min_child_samples=100. L1 regularization=0, L2 regularization=1, subsample=1, feature_fraction=1, CPU, n_jobs=1, seed=4005. HIST_TUNE의 mean raw pinball을 mean actual runtime으로 나눈 점수로 공유 설정을 고정했다.',
      f"사전등록 원본 커밋은 8477fda59945815dc70e7896b42feff981d2936c다. 최초 fit 진입에서 출력 디렉터리 생성 누락으로 모델 fit 이전에 중단했고, 디렉터리 생성 및 receipt self-hash 제외를 수정한 최종 pre-fit 커밋은 {read('PREREGISTRATION_COMMIT_RECEIPT')['commit']}다. 그 사이 모델 fit=0, tuning prediction=0이며 과학 규칙·설정은 동일하다. 원본 receipt와 erratum을 보존했다.",
      '잔차용 Q50은 HIST_TUNE 선택을 통한 간접 정보 유입을 막기 위해 사전에 L0로 고정한 보조 OOF 모델이다. 최종 4개 분위수와 잔차 회귀는 L2를 공유한다. 시간순 OOF fold의 fit/validation 수는 70/69, 139/70, 209/71, 280/60, 340/81이다. 동일 timestamp는 분리하지 않았다. warmup 70개는 잔차 학습에서 제외하고 351개 OOF 오차만 사용했다. 첫 fold는 min_child_samples=50 조건상 분할이 없는 상수 LightGBM이며 이를 그대로 감사 기록했다. OOF Q50 MAE는 760.241초, 모든 fold에서 train/validation job 중복은 0이다.',
      'UARP 식과 고정 계수는 [Choi & Oh (2026), §4.3–4.4](https://link.springer.com/article/10.1007/s11227-026-08422-8)에서 확인했다. 원문의 데이터·스케줄러 결과 재현이 아닌 식의 적용이며, 경험적 Q99가 99% coverage를 보장한다고 주장하지 않는다. 요청 walltime 상한은 적용하지 않았다.']
    for role in ROLES[1:]:
        d=read('P_'+role+'_REPORT')
        text += [role+' 후보 결과 (coverage는 %, GPU_under는 GPU·초, GPU_over는 GPU·시간):',
          table(['후보','coverage','GPU coverage','GPU_under_sec','GPU_over_h','안전성 / 효율성'],
            [[name,pct(m['coverage']),pct(m['GPU_coverage']),fmt(m['GPU_under_sec']),fmt(m['GPU_over_h']),
              '비교 기준' if name in CANDIDATES[:2] else ('PASS' if d['gates'][name]['safety'] else 'FAIL')+' / '+('PASS' if d['gates'][name]['efficiency'] else 'FAIL')]
             for name,m in d['results'].items()]),
          role+' 분위수 정확도 (초, WAPE는 %; pinball은 raw prediction, 나머지는 고정 하한·단조 보정 후):',
          table(['모델','MAE','WAPE','bias','pinball'],[[q,fmt(v['metrics']['MAE']),pct(v['metrics']['WAPE']),fmt(v['metrics']['bias']),fmt(v['raw_pinball'])] for q,v in d['quantiles'].items()])]
    text += ['안전성은 DEV와 CAL에서 각각 coverage≥90%, GPU coverage≥90%, N≥100인 모든 issue-day에서 두 coverage≥88%, GPU_under<RSP를 모두 요구했다. 효율성은 각 split에서 GPU_over<requested walltime를 별도로 요구했다. 4개 후보 모두 효율성만 만족하고 안전성은 실패했다. 따라서 selected=NONE이며 EXPOSED 후보 결과는 고정 비교의 설명 자료다.',
      f"선택 동결 커밋 {read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit']} 후 정확히 1회 P-W sensitivity와 1회 독립 P 재학습을 마쳤다. EXPOSED 이전 전체 모델 동결 커밋은 {read('PREEXPOSED_COMMIT_RECEIPT')['commit']}다. 이후 모델 재학습·계수 수정·후보 승격은 0이다.",
      table(['EXPOSED 후보','RSP 대비 GPU_under 감소율','request 대비 GPU_over 감소율'],[[name,pct(v['GPU_under_reduction_vs_RSP']),pct(v['GPU_over_reduction_vs_request'])] for name,v in e['reductions'].items()]),
      '감소율 음수는 악화를 뜻한다. UARP는 RSP보다 GPU 과소예측량이 76.92% 늘었다. 91.78%의 과잉예약 감소를 안전한 효율 개선으로 해석할 수 없다. 현재 RSP도 EXPOSED에서 충분히 안전하다고 볼 수 없지만 이번 실험으로 대체 권한이 생기지 않았다.']
    text += ['15분 완료 슬롯: actual과 candidate 각각 ceil(sec/900)를 한 번 적용했다. 96슬롯 상한을 덧씌우지 않았다.',
      table(['EXPOSED 후보','슬롯 MAE','signed error','≥1슬롯 조기','≥4슬롯 조기','≥8슬롯 조기','GPU ≥1슬롯 조기'],
        [[name,fmt(m['completion_slot_MAE']),fmt(m['completion_slot_signed_error']),pct(m['ending_at_least_1_slots_early']),pct(m['ending_at_least_4_slots_early']),pct(m['ending_at_least_8_slots_early']),pct(m['GPU_ending_at_least_1_slots_early'])] for name,m in e['results'].items()])]
    cross=read('QUANTILE_CROSSING_AUDIT')['P'];margin=read('UARP_MARGIN_ABLATION')['P']
    text += [table(['split','raw crossing N / %','보정 후 crossing','raw 음수 값 수','평균 보정량(초)','A≥B','B>A','sigma median / P99'],
      [[r,f"{cross[r]['raw_crossing_N']} / {pct(cross[r]['raw_crossing_fraction'])}",0,cross[r]['raw_negative_value_N'],fmt(cross[r]['correction_magnitude_sec']['mean']),
        pct(margin[r]['fraction_A_ge_B']),pct(margin[r]['fraction_B_gt_A']),fmt(margin[r]['sigma_sec']['median'])+' / '+fmt(margin[r]['sigma_sec']['P99'])] for r in ROLES]),
      '모든 raw 예측을 보존했다. 비음수 runtime 요구를 위해 학습 전 등록한 max(raw,0) 물리적 하한 후 누적 max 단조 보정을 적용했다. 후보는 모두 finite/nonnegative다. sigma는 요청한 sqrt(max(predicted_r2,0))를 그대로 사용했다. EXPOSED residual r2 음수 예측은 1,145/2,713개(42.20%)로 sigma가 0이 된다. 잔차 회귀의 불안정성을 보여주는 진단이며 조정하지 않았다.',
      'actual>requested 행은 historical 0개, TRAIN 1개, DEV 85개, CAL 34개, EXPOSED 189개로 모두 유지했다. actual/request median은 historical .002448, TRAIN .080171, DEV .051678, CAL .044722, EXPOSED .290208이다. request를 hard upper bound로 사용하지 않았다.',
      'Unique-job sensitivity는 split별 earliest issue만 사용했다: TRAIN 1,160 / DEV 2,893 / CAL 1,738 / EXPOSED 1,812개. 선택에는 사용하지 않았다. 모든 후보 결과는 UNIQUE_JOB_SENSITIVITY.json에 있다.']
    unique=read('UNIQUE_JOB_SENSITIVITY')['results']['P']
    text += [table(['unique-job split','UARP coverage','GPU coverage','GPU_under_sec','GPU_over_h'],[[r,pct(unique[r]['results']['R5_UARP_STYLE']['coverage']),pct(unique[r]['results']['R5_UARP_STYLE']['GPU_coverage']),fmt(unique[r]['results']['R5_UARP_STYLE']['GPU_under_sec']),fmt(unique[r]['results']['R5_UARP_STYLE']['GPU_over_h'])] for r in ROLES])]
    shift=read('TEMPORAL_SHIFT_AUDIT')['splits']
    text += ['시간 분포 이동은 historical reference decile bins와 1e-6 probability floor를 사용하는 사전등록 PSI로 확인했다. runtime/actual-request/request/GPU/submit hour/weekday 분포와 partition/QoS 빈도도 전 split에 저장했다. 진단 후 적응 학습은 하지 않았다.',
      table(['split','runtime median','request median','actual/request median','request PSI','GPU PSI'],[[r,fmt(v['distributions']['runtime_seconds']['median']),fmt(v['distributions']['requested_seconds']['median']),fmt(v['distributions']['actual_request_ratio']['median']),fmt(v['PSI']['requested_seconds']['value']),fmt(v['PSI']['num_gpus_req']['value'])] for r,v in shift.items()])]
    wt=read('WALLTIME_DEPENDENCE_ANALYSIS')['deltas'];importance=read('FEATURE_IMPORTANCE_DIAGNOSTIC')
    text += ['P-W는 requested_seconds와 그 missing indicator만 제거했다. 모델 family·설정·분위수·잔차 OOF 절차·수식은 동일하고 별도 winner search는 없다. selected=NONE이므로 모든 등록 수식의 변화는 진단으로만 보고했다.',
      table(['split','Q50 MAE Δ(P-W − P)','Q90 pinball Δ','Q95 Δ','Q99 Δ','UARP coverage Δ(pp)','GPU Δ(pp)'],
        [[r,fmt(v['Q50_MAE_delta_PW_minus_P']),*[fmt(v['pinball_delta_PW_minus_P'][q]) for q in ['Q90','Q95','Q99']],fmt(v['candidate_delta_PW_minus_P']['R5_UARP_STYLE']['coverage']*100),fmt(v['candidate_delta_PW_minus_P']['R5_UARP_STYLE']['GPU_coverage']*100)] for r,v in wt.items()]),
      table(['모델','walltime gain 비중','HIST_TUNE permutation loss Δ'],[[q,pct(v['grouped_gain_fraction']['requested_seconds']),fmt(v['permutation_HIST_TUNE']['requested_seconds']['mean_loss_increase'])] for q,v in importance.items()]),
      'Gain은 최종 모델, permutation은 HIST_FIT 전용 보조 모델에서 HIST_TUNE만 사용했다. quantile은 pinball, 잔차는 OOF squared-error target의 MSE를 사용하므로 잔차 permutation의 단위는 초⁴이다. Q50/Q90에서는 walltime 순열이 오차를 늘리지만 Q95/Q99와 residual에서는 반대다. 이 작은 단일 오전 자료로 walltime의 일반적 무용성을 결론낼 수 없다. feature 제거 또는 계수 조정 근거로 사용하지 않았다.',
      'May runtime/outcome/training/calibration/selection/sensitivity scientific row reads=0, Apr24–30 shadow=SEALED, scientific reads=0. Git 경로·index·blob identity 메타데이터 discovery는 nonzero로 공개했다. Phase 0에서는 SHA로 검증된 pre-Apr24 source의 전체 완료 시각/라벨을 집계·정합성 검사했고, 학습은 cutoff 이전 421개로 제한했다. EXPOSED는 이미 노출된 역사 자료다.',
      'Optimizer/Gurobi/OpenDSS/Fresh calls=0. A0/A1/M1/MF, RUNNING/PENDING migration, WAN, Rack, terminal, MESS route/P/Q, AC restoration, event trigger, local repair, rolling MPC는 모두 변경 0이다. normative sequence와 production q=5576.44921875s, PF=.95, Q control=NO, electrical=HOLD, B0–B3=NO, FULL_MAY=NO를 유지했다.',
      f"검증은 pytest {read('TEST_REPORT')['passed']}개 통과(실패·오류·skip=0). 사용자 최소 87항목을 테스트/최종 receipt 검증에 연결했다. 독립 재학습은 1회이며 Q50/Q90/Q95/Q99/sigma 및 모든 새 safe candidate의 max/mean 차이가 모두 0이고 최종 모델 파일 SHA도 일치한다. 반복 결과로 선택을 바꾸지 않았다.",
      f"실행환경: Python {c['Python']}; libraries {json.dumps(c['libraries'])}; CPU {c['CPU']}, threads=1, seed=4005. 전체 fit 인스턴스 {len(c['fits'])}개(설정 비교 12, primary 및 진단 11, P-W 10, 독립 repeat 10), 합계 학습 시간 {sum(v['seconds'] for v in c['fits']):.3f}s. 추론 기록 합계 {sum(v['seconds'] for v in c['inference']):.3f}s. 파일별 학습 대상·시각·전처리·SHA와 실행 시간은 COMPUTE_LEDGER.json에 있다.",
      '실패 해석: 이용 가능한 complete-case Kestrel trace, 명시적 request-state proxy 가정, cutoff 이전 mature historical library, 사전등록된 direct quantile/UARP-style 모델군에서는 요구 신뢰성–효율성 절충을 만족하는 대체 모델이 없었다. runtime prediction이 불가능하다는 의미는 아니다. 학습 가능 이력이 421개/약 8시간이라는 제약을 포함한 이 계약의 실패다.',
      'RECOMMENDED_OPERATIONAL_RUNTIME=CURRENT_RSP. CURRENT_RSP_REMAINS_OPERATIONAL. FURTHER_RUNTIME_MODEL_PROLIFERATION=NO. FURTHER_RUNTIME_MODEL_WORK=DEFER_UNTIL_RICHER_AUTHORITY_OR_DATA. 추가 quantile, 계수 조정, 새 모델군, BODY/tail 복원, 게이트 완화는 하지 않았다. 향후 재검토에는 검증된 snapshot, 더 긴 과거 이력·full backlog/censoring 권한, 승인된 application/job context 또는 progress/checkpoint 정보 같은 새로운 권한·자료가 필요하다.',
      'Adapter: proposal_only=true, optimizer_use_allowed=false, recommended_rows=[]. 과학 커밋과 최종 receipt 커밋은 자기참조를 피하기 위해 V40S5_FINAL_COMMIT_RECEIPT.json과 git log -1 --format=%H -- 해당 파일로 확인한다.']
    (OUT/'V40S5_FINAL_REVIEW.md').write_text('\n\n'.join(text)+'\n',encoding='utf-8')

def science():
    guard_receipt('PREREGISTRATION_COMMIT_RECEIPT');guard_receipt('SELECTION_FREEZE_COMMIT_RECEIPT');guard_receipt('PREEXPOSED_COMMIT_RECEIPT')
    protected();test_report();review()
    req=required();missing=[p for p in req if not (OUT/p).exists() and p!='V40S5_FINAL_COMMIT_RECEIPT.json']
    assert not missing,missing
    write('ARTIFACT_MANIFEST',dict(required=req,required_count=len(req),present_before_receipt=len(req)-1,only_pending='V40S5_FINAL_COMMIT_RECEIPT.json'))
    commit=stage_commit('Close V40S5 direct runtime validation: safety failure; retain current RSP')
    print(json.dumps(dict(scientific_commit=commit,required_artifact_count=len(req),pytest_passed=read('TEST_REPORT')['passed'])),flush=True)

def receipt():
    science_commit=git('rev-parse','HEAD');assert git('status','--porcelain')==''
    assert ancestor(read('PREEXPOSED_COMMIT_RECEIPT')['commit'],science_commit)
    owned=[p for p in git('ls-tree','-r','--name-only','HEAD').splitlines() if allowed(p)]
    hashes={p:file_sha(ROOT/p) for p in owned}
    for p,h in hashes.items():assert sha(git('show',f'{science_commit}:{p}',binary=True))==h,p
    req=required()
    write('FINAL_COMMIT_RECEIPT',dict(timestamp=now(),status='PASS',scientific_commit=science_commit,S4_base=BASE,S4_scientific=SCI4,S3_scientific=SCI3,S3_receipt=REC3,
      branch=git('branch','--show-current'),worktree=str(ROOT),classification=read('FINAL_DECISION')['classification'],selected_model=read('SELECTION_FREEZE')['selected_model'],
      selected_lightgbm_config=read('HYPERPARAMETER_FREEZE')['selected'],historical_training_jobs=421,
      preregistration_commit=read('PREREGISTRATION_COMMIT_RECEIPT')['commit'],selection_commit=read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit'],
      preexposed_commit=read('PREEXPOSED_COMMIT_RECEIPT')['commit'],owned_SHA256=hashes,owned_file_count=len(hashes),required_artifacts=req,
      required_artifact_count=len(req),git_after_scientific_commit='CLEAN',pytest_passed=read('TEST_REPORT')['passed'],
      protected_scope=read('PROTECTED_SCOPE_DIFF'),reproducibility=read('REPRODUCIBILITY_AUDIT')['status'],May_firewall=read('MAY_FIREWALL'),
      optimizer_calls=0,Gurobi_calls=0,OpenDSS_calls=0,Fresh_calls=0,holds=HOLDS,operational_recommendation='CURRENT_RSP_REMAINS_OPERATIONAL',
      future_work='DEFER_UNTIL_RICHER_AUTHORITY_OR_DATA',optimizer_integration='NO',production_ready='NO',recommended_rows=[],
      receipt_commit_identity='git log -1 --format=%H -- dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime/V40S5_FINAL_COMMIT_RECEIPT.json',
      final_verification='python -B -m dayahead.v40s5.closeout verify; read-only output outside self-referential receipt'))
    assert all((OUT/p).exists() for p in req)
    print(json.dumps(dict(receipt_commit=stage_commit('Record V40S5 final scientific receipt and immutable evidence manifest'))),flush=True)

def verify():
    r=read('FINAL_COMMIT_RECEIPT');head=git('rev-parse','HEAD')
    assert git('status','--porcelain')==''
    assert ancestor(r['scientific_commit'],head)
    assert git('diff','--name-only',r['scientific_commit'],head).splitlines()==['dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime/V40S5_FINAL_COMMIT_RECEIPT.json']
    for p,h in r['owned_SHA256'].items():
        assert file_sha(ROOT/p)==h and sha(git('show',f"{r['scientific_commit']}:{p}",binary=True))==h,p
    initial=tree(BASE);final=tree(head)
    assert all(final[p]==v for p,v in initial.items())
    assert all(allowed(p) for p in git('diff','--name-only',BASE,head).splitlines())
    for p in r['required_artifacts']:assert (OUT/p).exists(),p
    assert (OUT/'V40S5_FINAL_COMMIT_RECEIPT.json').read_bytes()==git('show',f'{head}:dayahead/artifacts/v40s5_uncertainty_aware_direct_runtime/V40S5_FINAL_COMMIT_RECEIPT.json',binary=True)
    guard_receipt('PREREGISTRATION_COMMIT_RECEIPT');guard_receipt('SELECTION_FREEZE_COMMIT_RECEIPT');guard_receipt('PREEXPOSED_COMMIT_RECEIPT')
    assert file_sha(SOURCE)==SOURCE_SHA and file_sha(S4/'V40S4_PENDING_ISSUE_PANEL.parquet')==PANEL_SHA
    assert git('status','--porcelain',cwd=S4ROOT)==''
    print(json.dumps(dict(status='PASS',scientific_commit=r['scientific_commit'],receipt_commit=head,git_clean=True,
      inherited_entries_unchanged=len(initial),owned_scientific_files_verified=len(r['owned_SHA256']),required_artifacts_verified=len(r['required_artifacts']),
      minimum_checks_86_87='PASS',pytest_passed=r['pytest_passed'],classification=r['classification'],selected=r['selected_model']),indent=2),flush=True)

if __name__=='__main__':{'science':science,'receipt':receipt,'verify':verify}[sys.argv[1]]()
