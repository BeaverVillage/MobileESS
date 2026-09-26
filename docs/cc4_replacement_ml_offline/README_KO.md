# CC4 forecast-only offline 실험

진입점은 FINAL_REVIEW_KO.md다. 이 폴더 밖의 production/predictor/snapshot을 수정하지 않는다. Gurobi/OpenDSS/캠페인을 실행하는 모듈을 import하지 않는다.

실행 환경: `D:/codex_mobileess_workspace/v40r3_ml_runtime/Scripts/python.exe`, UTF-8 mode, CPU/BLAS/PyTorch threads=1, GPU job=1. 구체적 버전은 ENVIRONMENT.json. 추가 도표 패키지는 이 폴더의 plot_dependencies에만 설치했다.

재현 순서:

1. setup.py: 네 GitHub commit/PR metadata 확인 후 필요한 Git objects를 history/{A,B,C,D}로 추출.
2. prepare_data.py: 사전 protocol 저장, 보호 lineage, raw archive 및 원본 target/feature/maturity 검증, DATA.npz 생성.
3. run_experiment.py: 원본 F0 재현, 실제 학습, development 선택·설정 동결, 역사 비교. fits/* checkpoint와 영수증에 seed별 기록. 완료된 영수증은 재사용하므로 새 독립 학습에는 새 namespace를 사용한다.
4. verify_and_enrich.py: 수치 dtype 보정, repair 이전 raw quantile 추가, authority/causality/membership/protected hash 검증. EXECUTION_CORRECTION.json을 확인한다.
5. finalize_report.py: 모든 metrics, uncertainty, 한국어 보고서, 정적 비교 도표 및 delivery manifest.
6. final_checks.py: calibration membership, zero/positive coverage identity, LightGBM retraining 재현, 최종 산출물 SHA 확인.

과거 자료와 exposed/May는 미사용 holdout이 아니다. 모델·설정·refit·horizon 선택에 May 결과를 사용하지 않았다. source freeze 이후 학습 코드는 변경하지 않았고, 별도의 검증 단계에서 상수 기준모델의 integer calibration 배열 절삭만 보정했다. F0의 85%와 F1의 90%를 신경망 구조 개선으로 혼동하지 않는다.

PREDICTIONS.parquet에는 seed별 raw/보정/cap 이후 예측과 target이 있고, secured_reserve는 optimizer 미실행을 뜻하는 결측이다. 평균 quantile ensemble을 만들지 않았다. MODEL_METRICS는 모든 seed 결과, SEED_MEAN_METRICS는 지표의 seed 평균이다. development 진단은 전체 58일, selection score는 성숙 residual 20일 warmup 이후 34일로 범위가 다르다.

KNOWN_NUMERICAL_ISSUES: 초기 준비 단계의 dtype/Unicode/empty-bin 수정을 학습 전에 완료했다. 검증 과정의 NPZ 반복 압축 해제 메모리 오류는 단일 읽기+vector indexing으로 해결했다. 표본 축소는 없다. 상수 calibration dtype correction은 run_experiment만 재실행하면 다시 필요하므로 4단계를 생략하지 않는다.
