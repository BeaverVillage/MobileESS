from common import *
from study import guard
from finish import table
import sys
REQUIRED='COMPUTE_BACKEND_BENCHMARK.csv COMPUTE_BACKEND_SELECTION.json NEXT_STAGE_PROTOCOL.json LEAD_GROUP_DEFINITION.json MODEL_STAGE_A_METRICS.csv MODEL_STAGE_B_CALIBRATION_METRICS.csv FINALIST_FREEZE.json FULL_OOS_METRICS.csv LEAD_TIME_METRICS.csv BURST_METRICS.csv PAIRED_UNCERTAINTY.csv NEXT_STAGE_FINAL_REVIEW_KO.md FINAL_COMPUTE_FLAGS.json NEXT_STAGE_VALIDATION.json'.split()
def review():
    guard();verify_previous();v=read(ROOT/'NEXT_STAGE_VALIDATION.json');assert v['PASS']
    backend=read(ROOT/'COMPUTE_BACKEND_SELECTION.json');f=read(ROOT/'FINALIST_FREEZE.json');a=pd.read_csv(ROOT/'MODEL_STAGE_A_METRICS.csv');b=pd.read_csv(ROOT/'MODEL_STAGE_B_CALIBRATION_METRICS.csv');m=pd.read_csv(ROOT/'FULL_OOS_METRICS.csv');u=pd.read_csv(ROOT/'PAIRED_UNCERTAINTY.csv');bench=pd.read_csv(ROOT/'COMPUTE_BACKEND_BENCHMARK.csv');lead=pd.read_csv(ROOT/'LEAD_TIME_METRICS.csv')
    decisions=[]
    for arm,s in f['finalists'].items():
        checks=[]
        for role in ['EXPOSED_EVALUATION','OOS_EXTENSION']:
            final=m[m.arm.eq(arm)&m.role.eq(role)&m.variant.eq('FINALIST')].iloc[0];legacy=m[m.arm.eq(arm)&m.role.eq(role)&m.variant.eq('LEGACY_SLOT_REFERENCE')].iloc[0]
            ci=u[u.arm.eq(arm)&u.role.eq(role)&u.contrast.eq('FINALIST minus LEGACY_SLOT_REFERENCE')&u.metric.eq('Q90_pinball')&u.block_days.eq(7)].iloc[0]
            passed=bool(final.Q90_coverage>=.88 and final.Q90_coverage<=.92 and final.requirement_ratio<=legacy.requirement_ratio and ci.CI_high<0)
            checks.append(dict(role=role,coverage=final.Q90_coverage,ratio=final.requirement_ratio,pinball_delta_CI_high=ci.CI_high,PASS=passed))
        decisions.append(dict(arm=arm,model=s['model'],method=s['method'],multi_period_supported=all(r['PASS'] for r in checks),checks=checks))
    flags=dict(CURRENT_V27_RUN_COMPLETED_UNCHANGED=True,CURRENT_V27_DEVICE_CHANGED_MIDRUN=False,CPU_MULTIPROCESS_BENCHMARKED=backend['CPU_MULTIPROCESS_BENCHMARKED'],GPU_LIGHTGBM_BENCHMARKED=backend['GPU_LIGHTGBM_BENCHMARKED'],SELECTED_BACKEND=backend['SELECTED_BACKEND'],PREDICTION_EQUIVALENCE_VERIFIED=backend['PREDICTION_EQUIVALENCE_VERIFIED'],NEXT_STAGE_SEARCH_SPACE_REDUCED=True,FULL_DAILY_REFIT_LIMITED_TO_FINALISTS=True)
    write('FINAL_COMPUTE_FLAGS.json',dict(**flags,new_full_period_fit_count=0,reused_finalist_daily_fit_records=546,full_refit_scope_semantics='Exactly two finalists reuse matching frozen causal daily-refit evidence; no redundant refit or speculative full-period model training.',benchmark_quantile_fits=120,additional_untimed_GPU_identification_fits=1))
    write('NEXT_STAGE_VERDICT.json',dict(time=pd.Timestamp.now(tz='UTC'),decisions=decisions,NEW_CALIBRATION_PROMOTED=any(s['method'].startswith('HORIZON') for s in f['finalists'].values()),MULTI_PERIOD_CALIBRATION_SHARPNESS_SUPPORTED=any(d['multi_period_supported'] for d in decisions),REPLACEMENT_SUPPORTED=False,OPTIMIZER_INTEGRATION_READY=False,NO_UNTOUCHED_CONFIRMATION=True,May_used_for_selection=False))
    write('SOURCE_MANIFEST.json',dict(current_v27_delivery=dict(path=PREV.relative_to(ROOT.parent).as_posix()+'/DELIVERY_MANIFEST.json',sha256=sha(PREV/'DELIVERY_MANIFEST.json'),all_nested_files_verified=True),current_completion_sha256=sha(PREV/'CURRENT_RUN_COMPLETION.json'),current_review_sha256=sha(PREV/'FINAL_REVIEW_KO.md'),daily_refit_reuse_audit_sha256=sha(ROOT/'DAILY_REFIT_REUSE_AUDIT.csv'),source_scope='Read-only frozen v2.7; no raw-target/feature reconstruction or older evidence changes.'))
    fields=['arm','method','Q90_coverage','Q90_pinball','requirement_ratio','excess_reserve_proxy','positive_coverage','burst_coverage']
    selected=m[m.variant.eq('FINALIST')]
    s=lead[lead.variant.eq('FINALIST')].groupby(['arm','role']).Q90_coverage.agg(['min','max']).reset_index()
    rawci=u[u.contrast.eq('FINALIST minus RAW_REFERENCE')&u.metric.eq('Q90_pinball')&u.block_days.eq(7)]
    parts=['# CC4-v2.7 후속 축소 연구 최종 검토',
        f"선택한 계산 백엔드 {backend['SELECTED_BACKEND']}는 대표 배치에서 단일 실행 대비 {backend['speedup_vs_CPU_SINGLE']:.2f}배의 속도를 보였고 동등성 기준을 통과했다. 이번 CPU4 예측과 지표는 비트 단위로 같았다. GPU는 실제 NVIDIA 장치에서 실행됐으나 더 느리고 수치 차이가 커서 선택하지 않았다. 과학적 결과는 음성이다. 새 리드 그룹 보정과 국소 스케일 보정이 CAL 단계에서 기존 슬롯 보정을 이기지 못했고, 최종 두 후보는 기존 방법을 유지했다. 교체·optimizer 통합 준비는 FALSE다.",
        '## 현재 실험 보존과 분리',
        '원 CC4-v2.7의 24개 조합 및 등록된 M0/M1 비교를 중단·가속·가지치기 없이 완료했다. CPU/GPU, n_jobs, 정의, 날짜, 후보, 보정, May 규칙을 실행 중 변경하지 않았다. 5,733개 신규 일별 학습 기록과 275,184개 예측 행을 검증하고 최종 검토와 5,859개 파일 명세를 동결한 다음에만 이 후속 연구를 시작했다. 이전 결과는 [원 최종 검토](../cc4_v27_target_feature_sharpness/FINAL_REVIEW_KO.md)에 보존했다.',
        'T0의 수명량을 제출 시간에 집중하는 방식은 TRAIN CV 3.89, 상위1% 질량 32.12%였고 T2는 1.12, 4.90%였다. 발행 후 자정 전 제출은 D일 미지 실행량의 6.383%를 차지했다. 같은 D일 제출 모집단 수명량의 54.33%는 D일 뒤에 실행됐다. 이 운영상 매핑 문제와 확률적 Q90 보정 문제는 별개다. 원 DEV의 raw 24개 조합 모두 명목 88~92% 밴드에 실패했다.',
        '## 백엔드 벤치마크',
        '2024-09-15/10-15의 T2F0·T3F2 × M0/M1을 같은 데이터·성숙 규칙·가중치로 실행했다. 백엔드별 8개 작업, 40개 Q50/Q90 booster다. CPU는 각각 n_jobs=1을 유지했다. LightGBM 4.6.0, Python3.11.7, CPU 10코어/16스레드, RAM 약32GB, NVIDIA RTX4060 Laptop 8GB 환경이다. GPU는 설치된 device_type=gpu, double precision 요청을 사용했고 라이브러리를 재빌드하지 않았다. 별도 verbose 확인 로그가 NVIDIA 장치 사용과 GPU 비결정성 경고를 보여준다.',
        table(bench,['backend','total_wall_seconds','mean_fit_seconds','P95_fit_seconds','mean_CPU_utilization_percent','mean_GPU_utilization_percent','peak_RAM_MiB','peak_VRAM_MiB','max_prediction_abs_diff','max_metric_abs_diff','prediction_equivalence']),
        '선택은 CPU_MULTIPROCESS, workers=4, fit별 n_jobs=1이다. 동등성 한계는 prediction atol/rtol 1e-8, 지표 절대 차이1e-6으로 측정 전에 고정했다. GPU 최대 예측 차이는 63.75여서 탈락했다. CPU/GPU 사용률과 VRAM은 시스템·장치 전체 관측치이며, VRAM 약789MiB의 기존 점유도 포함한다. RAM은 프로세스 트리 RSS 합으로 공유 페이지 중복 가능성이 있다. 0.5초 간격 표본이며 단일 순서 측정이라 열 상태·캐시·실행간 분산을 분리한 일반적 성능 주장은 아니다. 그래도 이 동일 배치에서 CPU4가 더 빠르고 정확히 재현됐다는 관측은 유효하다.',
        '## Stage A: 구조 축소',
        'T0F0는 역사적 도착량 기준으로만 남겼다. 운영 정합 후보 T2F0와 T3F2의 M0/M1을 DEV/CAL에서 비교하고 DEV로 구조를 선택했다. 두 후보 모두 M0를 유지했으며 M1은 pinball·Q50 MAE·보정 오차가 모두 더 나빴다. 96개 개별 모델이나 TFT/DeepAR 검색을 수행하지 않았다.',
        table(a[a.role.eq('DEVELOPMENT')],[x for x in ['arm','model','Q90_coverage','Q90_pinball','Q50_MAE','requirement_ratio']]),
        '## Stage B: 보정 축소',
        'RAW, 원 슬롯별 보정, 6시간 리드 그룹 가산 잔차 보정, 그룹별 국소 스케일 잔차 보정만 비교했다. 국소 스케일은 max(Q90−Q50, 0.05×TRAIN 평균)으로 정의하고 미래 관측을 사용하지 않았다. 새 방법의 DEV/CAL 잔차는 가장 최근의 성숙한 26일을 사용하며 20일 미만 warmup은 raw로 남겼다. CAL에서 먼저 88~92% 밴드, 그다음 pinball과 요구량 비율을 적용했다.',
        table(b[b.role.eq('CALIBRATION')],fields),
        'T2F0는 기존 슬롯 보정 coverage90.54%, pinball26.04, 비율2.45가 선택됐다. 그룹 가산은91.19%지만 손실28.21·비율2.70으로 더 나빴고, 국소 스케일은95.35%·비율3.48로 과도했다. T3F2는 기존88.70%·손실27.40·비율2.38이 선택됐다. 국소 스케일은89.94%로 명목에 가깝지만 손실55.36·비율4.21로 악화됐다. coverage만 최적화하지 않은 결과다.',
        '이 비교에서 원 슬롯 방법의 DEV/CAL 잔차 은행은 기존 expanding 방식이고 새 방법은 최근26일이다. 따라서 그룹화만의 순수 인과 효과를 분리한 실험은 아니다. 등록된 전체 보정 전략의 성능 비교이며, 모든 horizon-aware 또는 conformal 방식이 불가능하다는 결론은 내리지 않는다. 그룹 내 상관된 슬롯을 풀링했으므로 분포 독립적인 conformal coverage 보장을 주장하지 않는다. 국소 스케일은 예측 폭에 적응하지만 평가 잔차를 온라인 갱신하는 방식은 아니다.',
        '## Stage C: 동결한 최종 후보만 평가',
        '두 후보 모두 M0+LEGACY_SLOT로 동결됐다. 타깃·피처·모델·파라미터·날짜·가중치가 원 실험과 같으므로 546개 일별 모델 기록을 재사용했다. 그중 평가 날짜의 기록은364개이며, 새 전체 기간 학습은0회다. 캐시 해시, 학습 날짜, 가중치, 성숙 시각과 Q50/Q90을 검증했다. 이는 일별 refit을 생략한 정적 모델 평가가 아니라 이미 수행된 동일한 인과적 일별 refit의 정확한 재사용이다. 탈락한 새 보정 전략은 전체 OOS에 확장하지 않았다.',
        table(selected,['arm','role']+[x for x in fields if x!='arm']),
        '기존 평가/확장의 최종 coverage는 T2F0 94.22%/95.17%, T3F2 96.65%/94.69%로 모두 상한92%를 넘었다. 요구량 비율도 각각2.51/2.01, 2.69/2.03이다. CAL의 명목 근접이 다음 기간까지 유지되지 않았다. 최종 예측은 기존 슬롯 보정과 같아 그 대비 차이·CI는 정확히0이다. 따라서 새 방법의 개선으로 보고하지 않는다.',
        '리드 그룹별 최종 coverage 범위:',table(s),
        'raw 대비 Q90 손실 차이의 7일 블록95% CI:',table(rawci,['arm','role','delta','CI_low','CI_high']),
        '이 raw 대비 보정 효과는 이미 원 연구의 효과이며 후속 신기술의 성과가 아니다. 원 슬롯 대비 개선 CI는0이다. 전체 paired1일/7일 2,000회 CI, 양수·0·버스트·리드 그룹 지표는 개별 CSV에 보존했다. 0 라벨·어려운 날짜를 유지했고 NaN CI는 일부 resample에서 조건부 분모가0이 되는 경우 미정의로 남겼다.',
        '## 결론과 제한',
        '계산 가속은 확인됐지만, 이번에 시험한 보정 전략으로 명목 Q90와 낮은 예비량을 동시에 개선했다는 다기간 근거는 없다. 운영 점유량에 맞는 T2F0·T3F2는 연구 후보로 유지한다. 운영 교체를 승인하거나 V42·optimizer·MESS·IEEE/OpenDSS를 수정·실행하지 않았다. May는 역사적 진단으로만 사용했다. 모든 평가 기간은 이미 노출돼 있어 독립 확인시험이 아니며, 잔존 오차의 본질적 불가약성을 증명한 것도 아니다.',
        '## 최종 계산 플래그',table(pd.DataFrame([dict(flag=k,value=v) for k,v in flags.items()])),
        '재현과 캐시 범위는 README.md, backend 선택은 COMPUTE_BACKEND_SELECTION.json, 동결 후보는 FINALIST_FREEZE.json, 현재 증거 보존은 SOURCE_MANIFEST.json과 NEXT_STAGE_VALIDATION.json에서 확인할 수 있다.']
    (ROOT/'NEXT_STAGE_FINAL_REVIEW_KO.md').write_text('\n\n'.join(parts)+'\n',encoding='utf-8')
    print('NEXT_REVIEW_COMPLETE')
def seal():
    guard();verify_previous();assert all((ROOT/f).exists() for f in REQUIRED)
    rows=[dict(path=p.relative_to(ROOT).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(ROOT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json']
    write('DELIVERY_MANIFEST.json',dict(time=pd.Timestamp.now(tz='UTC'),files=rows,required_complete=True,original_v27_manifest_sha256=sha(PREV/'DELIVERY_MANIFEST.json'),scope=ROOT.name))
def verify():
    for r in read(ROOT/'DELIVERY_MANIFEST.json')['files']:assert sha(ROOT/r['path'])==r['sha256'],r['path']
    verify_previous();print('BOTH_DELIVERIES_VERIFIED')
if __name__=='__main__':{'review':review,'seal':seal,'verify':verify}[sys.argv[1]]()
