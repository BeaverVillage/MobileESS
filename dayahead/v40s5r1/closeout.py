"""Read-only verification, reports, and final scientific/receipt commits."""
import re
import sys
import xml.etree.ElementTree as ET
from .common import *
from .receipt import commit

def required():
    txt=(OUT/'USER_REQUEST.txt').read_text(encoding='utf-8')
    part=txt.split('# 55. REQUIRED ARTIFACTS')[1].split('# 56. MINIMUM TESTS')[0]
    return re.findall(r'^V40S5R1_[A-Z0-9_]+\.(?:json|parquet|csv|md)$',part,re.M)

def protect():
    start=read('PROTECTED_SCOPE_START');before=start['entries'];after=tree('HEAD')
    changed=[p for p,v in before.items() if after.get(p)!=v]
    outside=[p for p in git('diff','--name-only',BASE).splitlines() if not allowed(p)]
    assert not changed and not outside
    for p,h in start['parent_owned_SHA256'].items():assert file_sha(ROOT/p)==file_sha(S5ROOT/p)==h
    assert file_sha(SOURCE)==SOURCE_SHA and file_sha(PANEL)==PANEL_SHA
    assert git('status','--porcelain',cwd=S5ROOT)==''
    preserved={}
    for part in ['v40s3','v40s4','v40s5']:
        paths=[p for p in before if p.startswith(f'dayahead/{part}/') or p.startswith(f'dayahead/artifacts/{part}_') or p.startswith(f'tests/dayahead/test_{part}_')]
        for p in paths:assert (ROOT/p).read_bytes()==(S5ROOT/p).read_bytes(),p
        preserved[part]=len(paths)
    write('PROTECTED_SCOPE_END',dict(timestamp=now(),base=BASE,inherited_entries=len(before),unchanged_entries=len(before),preserved_scopes=preserved,
      parent_scientific_files_verified=len(start['parent_owned_SHA256']),S5_worktree_clean=True,source_SHA256=SOURCE_SHA,panel_SHA256=PANEL_SHA,
      systems_unchanged=['A0','A1','M1','MF','RUNNING','PENDING migration','RUNNING migration','WAN','Rack','terminal','MESS route','MESS P/Q','Fresh','AC restoration','event trigger','local repair','rolling MPC','second route search'],
      protected_operational_files=['dayahead/v37/aidc_materializer.py','dayahead/v40a/initial.py'],holds=HOLDS))
    write('PROTECTED_SCOPE_DIFF',dict(status='PASS',inherited_changed=changed,outside_allowed=outside,all_inherited_entries_unchanged=len(before),allowed_only=True))

def tests():
    x=ET.parse(OUT/f'{PREFIX}TEST_JUNIT.xml').getroot();suites=list(x.iter('testsuite'))
    counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','errors','failures','skipped']}
    assert counts['errors']==counts['failures']==counts['skipped']==0
    names=[v.attrib['name'] for v in x.iter('testcase')]
    txt=(OUT/'USER_REQUEST.txt').read_text(encoding='utf-8').split('# 56. MINIMUM TESTS')[1].split('# 57. FINAL RESPONSE FORMAT')[0]
    rows=re.findall(r'^(\d+)\. (.+)$',txt,re.M);assert len(rows)==88
    groups=[(1,6,'parent_closed_before_new_worktree;parent_and_entire_inherited_tree_unchanged'),(7,8,'exact_panel_identity_metadata_and_timezone'),
      (9,13,'one_expanding_membership_and_one_package_per_issue;every_origin_exact_mature_membership_and_ooftime;strict_cutoff_rejects_equal_end_and_future'),
      (14,15,'every_origin_prediction_hash_precedes_label_and_score;label_reader_cannot_open_before_both_hashes'),
      (16,22,'forbidden_fields_do_not_affect_predictor_matrix;every_origin_exact_mature_membership_and_ooftime;unknown_and_numeric_missing_are_issue_local'),
      (23,28,'exact_parent_frozen_contract_and_pure_functions;every_origin_exact_mature_membership_and_ooftime;repeat_dates_predetermined_before_fit'),
      (29,29,'exact_formula_and_no_requested_cap;exact_predictions_metrics_daily_support_and_candidates'),
      (30,31,'every_origin_exact_mature_membership_and_ooftime;fold_timestamp_blocks_and_expanding_history'),
      (32,43,'exact_predictions_metrics_daily_support_and_candidates;exact_formula_and_no_requested_cap;metric_arithmetic_and_rounding_once'),
      (44,50,'exact_predictions_metrics_daily_support_and_candidates;one_expanding_membership_and_one_package_per_issue;daily_support_rule'),
      (51,53,'static_comparison_and_pw_do_not_select;pw_exact_single_feature_removal'),
      (54,57,'safety_efficiency_selection_independent_recomputation;prereg_and_selection_commits_precede_their_stages'),
      (58,62,'prior_exposed_labels_enter_only_after_maturity;every_origin_exact_mature_membership_and_ooftime;every_origin_prediction_hash_precedes_label_and_score;safety_efficiency_selection_independent_recomputation'),
      (63,85,'firewalls_holds_adapter_and_no_operational_imports;parent_and_entire_inherited_tree_unchanged'),
      (86,86,'independent_repeats_all_five_full_packages')]
    mapping=[]
    for no,desc in rows:
        i=int(no)
        if i<=86:
            methods=next(g for lo,hi,g in groups if lo<=i<=hi)
            assert all(any(m in n for n in names) for m in methods.split(';'))
            mapping.append(dict(check=i,description=desc,status='PASS',methods=methods))
        else:mapping.append(dict(check=i,description=desc,status='FINAL_RECEIPT_VERIFIER',method='closeout.verify after receipt commit'))
    write('TEST_REPORT',dict(status='PASS',pytest=counts,passed=counts['tests'],seconds=sum(float(s.attrib.get('time',0)) for s in suites),
      prefit_unit_tests_passed=34,first_origin_static_equivalence_test_passed=True,minimum_requirements=88,coverage=mapping,
      command='python -B -m pytest -q tests/dayahead/test_v40s5r1_core.py tests/dayahead/test_v40s5r1_evidence.py -p no:cacheprovider --junitxml=.../V40S5R1_TEST_JUNIT.xml',
      names=names))

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def num(x):return f'{x:,.3f}'
def pct(x):return f'{100*x:.2f}%'

def review():
    final=read('FINAL_DECISION');selected=final['selected_candidate'];ex=read('EXPOSED_RESULTS');allr=read('ALL_SPLIT_RESULTS');r=allr['P']
    ledger=pd.read_parquet(OUT/f'{PREFIX}DAILY_TRAINING_LEDGER.parquet');daily=pd.read_parquet(OUT/f'{PREFIX}DAILY_RUNTIME_RESULTS.parquet')
    static=read('STATIC_S5_COMPARISON');maturity=read('DATA_MATURITY_PERFORMANCE_AUDIT');decision=static['primary_interpretation']
    name=selected or 'NONE';success=final['prevalidated']
    def role_safety(role):
        if selected:return 'PASS' if r['gates'][role][selected]['safety'] else 'FAIL'
        return 'NONE selected; no candidate passed all DEV+CAL gates'
    lines=[f"FINAL CLASSIFICATION: {final['classification']}\nSELECTED MODEL: {name}\nSELECTED CANDIDATE: {name}\nS5 STATIC RESULT: V40S5_DIRECT_RUNTIME_SAFETY_FAIL\nS5R1 ROLLING RESULT: {final['classification']}\nINITIAL HISTORICAL TRAINING JOBS: {ledger.iloc[0].training_job_count}\nFINAL HISTORICAL TRAINING JOBS: {ledger.iloc[-1].training_job_count}\nROLLING UPDATE MATERIAL IMPROVEMENT: {decision}\nDEV SAFETY: {role_safety('DEVELOPMENT')}\nCAL SAFETY: {role_safety('CALIBRATION')}\nEXPOSED SAFETY: {role_safety('EXPOSED_EVALUATION')}\nEFFICIENCY VS REQUESTED WALLTIME: see frozen gate table\nCURRENT RSP REPLACED: NO\nOPTIMIZER INTEGRATION: NO\nPRODUCTION READY: NO\n"]
    lines += [f"S5 scientific {S5SCIENCE}, 최종 receipt {BASE}와 clean Git·필수 artifact·receipt 검증을 먼저 확인한 후 독립 branch codex/v40s5r1-rolling-origin-runtime을 만들었다. S5 source/models/predictions/classification은 변경하지 않았다. S5는 고정된 static 실험으로 보존한다.",
      'S5에서 초기 mature 이력은 421개, HIST_FIT/HIST_TUNE는 332/89개였다. 고정 direct-runtime 후보가 안전성에 실패했다는 결과와, 과거 이력이 약 8시간에 집중됐다는 자료 한계를 구분했다. 이번 실험은 모델군 추가 없이 학습 갱신 정책만 expanding-origin으로 바꿨다.',
      'S4/S5 PENDING 파일 SHA256 '+PANEL_SHA+'의 동일 바이트를 사용했다. TRAIN/DEV/CAL/EXPOSED job-issue 수는 1,190/4,346/2,634/2,713, 합계 10,883, 고유 작업 7,603이다. 순서도 동일하다. 실제 패널에 있는 36개 08:00 UTC issue만 사용했고 빈 날짜를 새로 생성하지 않았다. 고정 AEST D-1 18:00 계약이다.',
      f"처음/마지막 학습 작업 수는 {ledger.iloc[0].training_job_count:,}/{ledger.iloc[-1].training_job_count:,}개다. 모든 issue에서 source/cohort가 같은 unique 작업 중 end_time < issue_time, runtime=end-start>0 finite, S5 feature 구성 가능 조건을 적용했다. end==issue는 제외했다. 과거 작업은 버리지 않았고 새로운 작업의 end는 이전 issue 이상, 현재 issue 미만임을 전수 검증했다.",
      'Arrow scanner는 end_time predicate를 내부에서 평가하지만 Python에 전달되는 scientific training row는 해당 시각 이전 완료 작업뿐이다. 현재 평가의 start/end/runtime은 P와 P-W 예측 파일을 저장·해시·검증한 뒤에만 열었다. 이벤트 로그는 FIT→PREDICT→HASH→LABEL READ→SCORE 순서를 기록한다. S5와 이전 대화의 역사 결과가 이미 노출됐으므로 이 검사는 R1 실행의 데이터 흐름 인과성에 대한 검증이며 untouched holdout이라는 뜻은 아니다.',
      '최종 분위수 4개와 residual regression은 S5의 L2를 그대로 사용했다: num_leaves=31, learning_rate=.02, n_estimators=800, min_child_samples=100, reg_alpha=0, reg_lambda=1, subsample=1, colsample_bytree=1, CPU, n_jobs=1, seed=4005. 하이퍼파라미터 선택은 0회다. 잔차 OOF Q50은 S5에 동결된 L0 보조 모델을 그대로 사용했다.',
      'Track P features: '+', '.join(FEATURES)+'. user/account/job/application identity, actual start/end/runtime/status, K0/reference-safe, migration/전기 결과는 predictor에서 제외했다. D1_SCHEDULER_REQUEST_STATE_PROXY_V1, 과거 D1 및 최초 submission provenance UNVERIFIED, request modification history UNOBSERVED를 유지한다.',
      '전처리는 매 issue의 D_train에서만 fit했다. request 수량 5개는 log1p, continuous missing은 해당 이력 median+indicator, partition/qos는 이력 vocabulary와 UNKNOWN one-hot이다. 각 OOF fold도 해당 validation보다 일찍 끝난 부분집합으로만 전처리한다. 전역 미래 전처리·target encoding은 없다.',
      'S5와 동일하게 raw runtime seconds를 예측하고 사전등록된 max(raw,0) 하한 후 Q50→Q90→Q95→Q99 누적 max를 적용했다. raw 값과 crossing/보정량은 모두 저장했다. 요청 walltime이나 기간 상한은 적용하지 않았다.',
      '잔차 crossfit은 N≥250이면 5개 expanding fold, 100≤N<250이면 3개, N<100이면 중단하도록 사전등록했다. 실제 모든 issue는 5-fold 경로다. 각 residual row를 예측한 Q50은 그 작업 및 이후 완료 작업을 학습하지 않았다. warmup block은 residual target에서 제외한다. sigma=sqrt(max(predicted_r2,0)), UARP=Q99+max(.20×Q99,.50×sigma)이며 계수 변화는 없다.',
      'UARP 식의 문헌 연결은 S5에서 검증한 [Choi & Oh (2026), §4.3–4.4](https://link.springer.com/article/10.1007/s11227-026-08422-8)를 유지한다. 이번 결과는 해당 논문의 데이터나 scheduler 결과 재현이 아니다.']
    grow=[]
    for _,v in ledger.iterrows():
        d=daily[(daily.issue_time==v.issue_time)&(daily.track=='P')&(daily.candidate=='R5_UARP_STYLE')].iloc[0]
        grow.append([v.issue_time.strftime('%Y-%m-%d'),d.role,int(v.training_job_count),int(v.new_jobs_added_since_previous_issue),int(d.N_eval_jobs),pct(d.coverage),pct(d.GPU_coverage),num(d.MAE)])
    lines += ['일별 학습 증가와 사전 지정 UARP 진단 결과:',table(['UTC issue 날짜','split','N_train','추가 작업','N_eval','coverage','GPU coverage','MAE 초'],grow)]
    for role in ROLES[1:]:
        lines += [role+' 후보 결과. GPU under 단위는 GPU·초, GPU over는 GPU·시간이다.',
          table(['후보','coverage','GPU coverage','GPU under','GPU over','안전성','효율성'],
            [[c,pct(m['coverage']),pct(m['GPU_coverage']),num(m['GPU_under_sec']),num(m['GPU_over_h']),
              'anchor' if c in CANDIDATES[:2] else str(r['gates'][role][c]['safety']),
              'anchor' if c in CANDIDATES[:2] else str(r['gates'][role][c]['efficiency'])] for c,m in r['results'][role].items()]),
          role+' 분위수 정확도: pinball은 raw, MAE/WAPE/bias는 고정 보정 후.',
          table(['Q','MAE 초','WAPE','bias 초','raw pinball'],[[q,num(v['metrics']['MAE']),pct(v['metrics']['WAPE']),num(v['metrics']['bias']),num(v['raw_pinball'])] for q,v in r['quantiles'][role].items()])]
    lines += ['안전성은 각 DEV와 CAL에서 coverage≥90%, GPU coverage≥90%, N≥100 issue-day의 두 coverage≥88%, GPU under<RSP를 모두 요구한다. 효율성은 각 split에서 GPU over<recorded requested walltime이다. coverage 상한 게이트는 없고 >99.5%는 보수성 경고다. CAL GPU over 최소→CAL GPU under→DEV+CAL GPU over→단순성 순으로만 선택했다.',
      f"선택 결과는 {name}이다. 사전등록 커밋 {read('PREREGISTRATION_COMMIT_RECEIPT')['commit']}, 선택 동결 커밋 {read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit']}를 각각 첫 rolling fit 및 첫 rolling EXPOSED issue 이전에 완료했다. EXPOSED 중에는 후보·설정·feature·계수·전처리 정책·학습 window를 바꾸지 않았다.",
      '이전 EXPOSED issue의 작업도 현재 issue 전에 완료됐으면 현재 학습에 포함했다. 이 성숙 규칙은 원본 전체 같은 cohort에 동일하게 적용했다. 이후 issue의 결과가 이전 예측에 영향을 주는 경로는 없다. EXPOSED PREQUENTIAL HISTORICAL EVIDENCE이며 TRUE_CONFIRMATORY_AVAILABLE=NO다.',
      '동일 후보에서 rolling−static S5 변화:',
      table(['split','후보','coverage Δpp','GPU coverage Δpp','GPU under Δ','GPU over Δ','material 진단'],
        [[role,c,num(v['rolling_minus_static']['coverage']*100),num(v['rolling_minus_static']['GPU_coverage']*100),num(v['rolling_minus_static']['GPU_under_sec']),num(v['rolling_minus_static']['GPU_over_h']),str(v['MATERIAL_IMPROVEMENT_DIAGNOSTIC'])]
          for role,rows in static['splits'].items() for c,v in rows.items() if c in CANDIDATES[2:]]),
      'material은 coverage 또는 GPU coverage가 동일 static 후보보다 10%p 이상 좋아지는 사전등록 진단이다. 안전성 게이트를 대체하지 않는다. 주 진단 대상은 결과를 보기 전에 R5_UARP_STYLE로 고정했다. 주 해석은 '+decision+'.']
    lines += ['학습량–성능의 일별 Spearman 상관은 인과관계가 아니다. 마지막 EXPOSED issue는 N_eval=1이므로 마지막 하루만으로 성능을 판단하지 않는다.',
      table(['후보','최소 N','중앙 N','최대 N','N vs coverage','N vs GPU coverage','N vs MAE'],
        [[c,v['min_N_train'],v['median_N_train'],v['max_N_train'],*[num(v['Spearman'][x]) if v['Spearman'][x] is not None else 'undefined' for x in ['coverage','GPU_coverage','MAE']]] for c,v in maturity['candidates'].items()])]
    drift=read('TEMPORAL_DRIFT_AUDIT')
    lines += ['훈련 composition과 평가 runtime/request/actual-request/GPU 분포 및 partition/QoS 빈도를 issue 또는 split별로 저장했다. EXPOSED 월·ISO 주별 결과도 분리했다. 표본 수와 분포 이동의 영향을 단독 원인으로 분리해 입증한 실험은 아니다.',
      table(['EXPOSED 구간','N_eval','학습 N 시작/끝','후보','coverage','GPU coverage','GPU under','GPU over'],
        [[label,v['N'],f"{v['N_train_start']}/{v['N_train_end']}",c,pct(m['coverage']),pct(m['GPU_coverage']),num(m['GPU_under_sec']),num(m['GPU_over_h'])]
          for group in drift['exposed_time_blocks'].values() for label,v in group.items() for c,m in v['results'].items() if c in CANDIDATES[2:]])]
    wt=read('WALLTIME_DEPENDENCE_ANALYSIS')
    lines += ['P-W는 동일 일별 membership·모델 설정·residual 방법·수식에서 requested_seconds와 그 indicator만 제거한 1회 고정 민감도다. 운영 후보가 될 수 없고 별도 tuning/selection은 없다.',
      table(['split','Q50 MAE Δ(PW−P)','Q90 pinball Δ','Q95 Δ','Q99 Δ','UARP coverage Δpp','GPU coverage Δpp'],
        [[role,num(v['Q50_MAE_delta_PW_minus_P']),*[num(v['pinball_delta_PW_minus_P'][q]) for q in ['Q90','Q95','Q99']],
          num(v['candidates']['R5_UARP_STYLE']['coverage']*100),num(v['candidates']['R5_UARP_STYLE']['GPU_coverage']*100)] for role,v in wt['deltas'].items()]),
      'requested_seconds grouped gain은 모든 일별 quantile/residual 모델에서 기록했다. permutation은 사전 지정 5일에 해당 issue 이전 historical 80/20 slice만 사용해 3회 순열을 적용했다. feature 선택·변경에는 사용하지 않았다. 전체 시계열은 WALLTIME_DEPENDENCE_ANALYSIS.json에 있다.']
    gain_rows=[]
    for t in read('PREREGISTRATION')['repeat_issue_times']:
        k=key(t);gain=wt['grouped_gain_over_time'][k+'_P'];perm=wt['historical_permutation'][k]['reports']
        for q in ['Q50','Q90','Q95','Q99','RESIDUAL']:gain_rows.append([t[:10],q,pct(gain[q]['grouped_gain_fraction']['requested_seconds']),num(perm[q]['walltime_mean_loss_increase'])])
    lines += [table(['날짜','모델','walltime gain 비중','historical permutation loss Δ'],gain_rows)]
    lines += ['15분 완료 슬롯은 actual/candidate 각각 ceil(seconds/900)를 한 번 적용했다. EXPOSED의 signed/weighted 지표도 모두 저장했다.',
      table(['후보','slot MAE','signed error','≥1 slot early','≥4','≥8','GPU ≥1 early'],
        [[c,num(m['completion_slot_MAE']),num(m['completion_slot_signed_error']),pct(m['ending_at_least_1_slots_early']),pct(m['ending_at_least_4_slots_early']),pct(m['ending_at_least_8_slots_early']),pct(m['GPU_ending_at_least_1_slots_early'])] for c,m in r['results']['EXPOSED_EVALUATION'].items()])]
    unique=read('UNIQUE_JOB_SENSITIVITY')['splits']
    lines += ['Unique-job는 split별 earliest issue만 사용한 보조 진단이며 재선택하지 않았다.',
      table(['split','고유 작업 N','UARP coverage','GPU coverage','GPU under','GPU over'],
        [[role,v['P']['N'],pct(v['P']['results']['R5_UARP_STYLE']['coverage']),pct(v['P']['results']['R5_UARP_STYLE']['GPU_coverage']),num(v['P']['results']['R5_UARP_STYLE']['GPU_under_sec']),num(v['P']['results']['R5_UARP_STYLE']['GPU_over_h'])] for role,v in unique.items()])]
    margin=read('UARP_MARGIN_AUDIT');cross=read('QUANTILE_CROSSING_AUDIT');rows=[]
    for v in read('PENDING_PANEL_IDENTITY_AUDIT')['issues']:
        k=key(v['issue_time'])+'_P';m=margin[k];cr=cross[k]
        rows.append([v['issue_time'][:10],num(m['sigma']['median']),num(m['sigma']['P99']),m['negative_r2_N'],pct(m['margin']['A_ge_B_fraction']),pct(m['margin']['B_gt_A_fraction']),cr['raw_N'],cr['corrected_N']])
    lines += ['일별 sigma·UARP margin·quantile crossing은 다음과 같다. 음수 predicted_r2는 고정 식대로 0으로 내려 sigma를 계산했으며 raw 결과를 숨기거나 재조정하지 않았다.',
      table(['날짜','sigma median','sigma P99','음수 r2 N','A≥B','B>A','raw crossing N','보정후 N'],rows)]
    comp=read('COMPUTE_LEDGER');test=read('TEST_REPORT')
    lines += ['May runtime/outcome/feature fitting/training/selection/calibration/sensitivity scientific reads=0. Apr24–30 shadow=SEALED, scientific reads=0. Git 경로/index/blob identity 및 schema 메타데이터 discovery는 nonzero로 별도 공개했다.',
      'Optimizer/Gurobi/OpenDSS/Fresh calls=0. A0/A1/M1/MF·RUNNING·migration·WAN·Rack·terminal·MESS route/PQ·AC restoration·event trigger·local repair·rolling MPC·second route search 변경=0. rolling-origin ML은 rolling MPC와 연결하지 않았다.',
      'production q=5576.44921875s, PF=.95, Q control=NO, electrical=HOLD, B0–B3=NO, FULL_MAY=NO, optimizer integration=NO를 유지한다. Adapter는 proposal_only=true, optimizer_use_allowed=false이며 '+('성공 조건에 한한 제안 row만 저장했다.' if success else 'recommended_rows=[]다.'),
      f"pytest {test['passed']}개 통과, 실패/오류/skip=0. 실행 전 단위 테스트 34개와 첫 issue의 static S5 예측 완전 일치도 검증했다. 최소 88개 요청 항목을 테스트 및 최종 receipt 검증에 연결했다. 사전 지정 5개 issue에서 전체 P 모델 패키지를 각각 1회 독립 재학습했고 Q50/Q90/Q95/Q99/sigma/UARP 최대·평균 차이는 모두 0, 모델 및 OOF 파일 SHA도 동일하다. 더 나은 repeat 선택은 하지 않았다.",
      f"CPU 1 thread, seed 4005. 환경 {json.dumps(comp['environment'],ensure_ascii=False)}. 일별 P/PW 모델 패키지는 각 {comp['primary_packages']}개, 독립 repeat는 {comp['independent_repeat_packages']}개, historical permutation 진단 패키지는 {comp['historical_diagnostic_packages']}개다. 총 fit {len(comp['fits'])}회, 학습 {comp['total_fit_seconds']:.3f}s, 추론(모델 읽기 포함) {comp['total_inference_seconds']:.3f}s. Cache 재사용은 0이다.",
      f"기존 Git 항목 {read('PROTECTED_SCOPE_END')['inherited_entries']:,}개 전체를 보존했고 변경 경로는 지정 S5R1 source/artifacts/tests 내부뿐이다. scientific 및 receipt 커밋은 FINAL_COMMIT_RECEIPT.json과 해당 파일의 git log에서 독립 확인한다."]
    if success:
        lines.append('명시적 scheduler-visible request-state proxy 가정 아래, 인과적 expanding-window 모델 갱신이 PENDING-job duration 추정의 사전 검증에 필요한 reliability와 efficiency를 회복했다. 최대 주장은 PREVALIDATED이며 production-ready·실제 deployment 검증·runtime 문제 해결을 주장하지 않는다. 현재 RSP의 실제 교체는 하지 않았다.')
    elif decision=='ROLLING_UPDATE_MATERIALLY_IMPROVES_RUNTIME':
        lines.append('일별 인과적 모델 갱신은 static S5 대비 runtime 예측을 사전등록된 기준에서 실질적으로 개선했지만, 미리 정한 reliability–efficiency 요건은 충족하지 못했다. 초기 historical maturity 부족은 S5 실패와 관련된 중요한 요인이었지만 표본 수가 유일한 원인이었다고 입증하지 않았다.')
    else:lines.append('인과적으로 성숙한 historical library를 확장했어도, 이용 가능한 request-state proxy features와 고정 모델 계약에서 충분한 runtime reliability를 회복하지 못했다.')
    lines += ['원본은 기존 exposed terminal-service complete-case extract이며 full cluster backlog 또는 검증된 scheduler snapshot이 아니다. 이 결과를 runtime prediction의 일반적 불가능성이나 보편적 성공으로 확대하지 않는다.',
      'CURRENT_RSP_REMAINS_OPERATIONAL. FURTHER_RUNTIME_MODEL_PROLIFERATION=NO. FURTHER_RUNTIME_MODEL_WORK='+final['FURTHER_RUNTIME_MODEL_WORK']+'. '+
      ('실패에 따라 S5R2/S6·추가 quantile·계수 조정·새 모델군·BODY/tail·user별 모델을 만들지 않는다. 향후 재검토에는 검증된 snapshot, 더 긴 pre-study history, 승인된 application/job context, full backlog/censoring/status 또는 progress/checkpoint 자료가 필요하다.' if not success else '후속 통합과 shadow 검증을 별도로 거쳐야 한다.')]
    (OUT/f'{PREFIX}FINAL_REVIEW.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')

def science():
    guard('PREREGISTRATION_COMMIT_RECEIPT');guard('SELECTION_FREEZE_COMMIT_RECEIPT')
    protect();tests();review();req=required()
    missing=[p for p in req if not (OUT/p).exists() and p!=PREFIX+'FINAL_COMMIT_RECEIPT.json'];assert not missing,missing
    write('ARTIFACT_MANIFEST',dict(required=req,required_count=len(req),only_pending=PREFIX+'FINAL_COMMIT_RECEIPT.json'))
    c=commit('Close V40S5R1 causal rolling runtime validation and preserve operational holds')
    print(json.dumps(dict(scientific_commit=c,required_artifacts=len(req),pytest_passed=read('TEST_REPORT')['passed'])),flush=True)

def final_receipt():
    c=git('rev-parse','HEAD');assert git('status','--porcelain')==''
    paths=[p for p in git('ls-tree','-r','--name-only',c).splitlines() if allowed(p)]
    hashes={p:file_sha(ROOT/p) for p in paths}
    for p,h in hashes.items():assert sha(git('show',f'{c}:{p}',binary=True))==h,p
    write('FINAL_COMMIT_RECEIPT',dict(timestamp=now(),status='PASS',scientific_commit=c,base_S5_receipt=BASE,base_S5_scientific=S5SCIENCE,
      branch=git('branch','--show-current'),worktree=str(ROOT),preregistration_commit=read('PREREGISTRATION_COMMIT_RECEIPT')['commit'],
      selection_commit=read('SELECTION_FREEZE_COMMIT_RECEIPT')['commit'],classification=read('FINAL_DECISION')['classification'],
      selected_candidate=read('SELECTION_FREEZE')['selected_candidate'],selected_config=model_config()[0],
      initial_training_jobs=read('DAILY_TRAINING_MEMBERSHIP_AUDIT')['first_N'],final_training_jobs=read('DAILY_TRAINING_MEMBERSHIP_AUDIT')['last_N'],
      owned_SHA256=hashes,owned_scientific_file_count=len(paths),required_artifacts=required(),required_artifact_count=len(required()),
      git_after_scientific_commit='CLEAN',pytest_passed=read('TEST_REPORT')['passed'],protected_scope=read('PROTECTED_SCOPE_DIFF'),
      reproducibility='PASS',May_firewall=read('MAY_FIREWALL'),optimizer_calls=0,Gurobi_calls=0,OpenDSS_calls=0,Fresh_calls=0,holds=HOLDS,
      current_RSP_replaced='NO',production_ready='NO',optimizer_integration='NO',future_work=read('FINAL_DECISION')['FURTHER_RUNTIME_MODEL_WORK'],
      receipt_commit_identity='git log -1 --format=%H -- dayahead/artifacts/v40s5r1_rolling_origin_runtime/V40S5R1_FINAL_COMMIT_RECEIPT.json',
      read_only_final_verification='python -B -m dayahead.v40s5r1.closeout verify'))
    assert all((OUT/p).exists() for p in required())
    print(json.dumps(dict(receipt_commit=commit('Record V40S5R1 final scientific receipt and evidence hashes'))),flush=True)

def verify():
    r=read('FINAL_COMMIT_RECEIPT');head=git('rev-parse','HEAD');assert git('status','--porcelain')==''
    assert ancestor(r['scientific_commit'],head)
    assert git('diff','--name-only',r['scientific_commit'],head).splitlines()==['dayahead/artifacts/v40s5r1_rolling_origin_runtime/V40S5R1_FINAL_COMMIT_RECEIPT.json']
    for p,h in r['owned_SHA256'].items():assert file_sha(ROOT/p)==h and sha(git('show',f"{r['scientific_commit']}:{p}",binary=True))==h,p
    before=tree(BASE);after=tree(head);assert all(after[p]==v for p,v in before.items())
    assert all(allowed(p) for p in git('diff','--name-only',BASE,head).splitlines())
    assert all((OUT/p).exists() for p in r['required_artifacts'])
    assert (OUT/f'{PREFIX}FINAL_COMMIT_RECEIPT.json').read_bytes()==git('show',f'{head}:dayahead/artifacts/v40s5r1_rolling_origin_runtime/V40S5R1_FINAL_COMMIT_RECEIPT.json',binary=True)
    guard('PREREGISTRATION_COMMIT_RECEIPT');guard('SELECTION_FREEZE_COMMIT_RECEIPT')
    assert git('status','--porcelain',cwd=S5ROOT)=='' and file_sha(SOURCE)==SOURCE_SHA and file_sha(PANEL)==PANEL_SHA
    print(json.dumps(dict(status='PASS',scientific_commit=r['scientific_commit'],receipt_commit=head,git_clean=True,
      inherited_entries_unchanged=len(before),owned_scientific_files_verified=len(r['owned_SHA256']),required_artifacts_verified=len(r['required_artifacts']),
      minimum_checks_87_88='PASS',pytest_passed=r['pytest_passed'],classification=r['classification'],selected=r['selected_candidate']),indent=2),flush=True)

if __name__=='__main__':{'science':science,'receipt':final_receipt,'verify':verify}[sys.argv[1]]()
