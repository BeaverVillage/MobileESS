# V40R4 재현 및 감사

외생 arriving GPU-service demand를 30분별 job count와 positive severity의 random sum으로 예측한다. V40R3의 타깃, 코호트, feature authority, maturity 및 시간 구간은 유지한다. Optimizer와 전기 실험은 범위 밖이다.

- Worktree: `C:/codex_mobileess_workspace/MobileESS_v40r4_compound_gpuwork_arrival`
- Branch: `codex/v40r4-compound-gpuwork-arrival`
- Base receipt: `43710c96c36f7e66257885a56ef6df697b3c53bb`
- Phase-0 규칙 commit: `abfb9a43be0f442a943535a146344fe954703aad`
- Forecast 사전등록 commit: `f10187e0b0cbaadde5b28186e70822f5ff258f76`
- 최종 노출 평가 전 baseline commit: `1a178ceba65a4bf830c6e0955effb4838d922f3f`

실행에는 기존 격리 Python 환경 `C:/codex_mobileess_workspace/v40r3_ml_runtime/Scripts/python.exe`를 읽기 전용으로 사용했다. V40R3 Python 모듈을 import하거나 R2 코드를 복사하지 않았다. 정확한 dependency/device/seed/epoch/timing은 artifact의 `V40R4_PREREGISTRATION.json`, `V40R4_COMPUTE_LEDGER.json`, `V40R4_REPRODUCIBILITY.json`에 있다.

아래는 완료된 실행 순서의 기록이다. 보존된 결과 위에서 재실행하면 산출물을 덮어쓸 수 있으므로 새 연구로 자동 재개하지 않는다.

1. `initialize`, Phase-0 규칙 commit, `phase0`, `prepare`.
2. `preregister`, 사전 테스트, 사전등록 commit과 receipt.
3. `train fit`: 등록 후보 각 1/2개 설정, DEVELOPMENT에서 설정/C0·C1 선택.
4. `train convergence`: TRAIN/CAL에서 고정 10,000 scenarios 수렴 검사와 CCAF 동일 seed 독립 재학습.
5. `train freeze`: DEVELOPMENT 최강 baseline을 저장하고 별도 commit.
6. `evaluate`: 고정 모델로 November CAL score 및 이미 노출된 December/January/February 비교. 안전 실패 시 superiority bootstrap은 미실행.
7. `finalize audit`, `test_contracts --final`, `finalize review`, 연구 결과 commit.
8. `finalize receipt`, receipt commit, 필수 artifact hash 검증.

`authority()`는 사전등록 원문, 모델/평가 소스와 입력 데이터의 고정 hash를 확인한다. `fits/*/selected_params.npz`는 각 인과 문맥의 분포 파라미터이며, 학습된 tree/GLM/neural weight도 함께 보존한다. `exposed_distribution_summary.npz`에는 raw/C1 증분 quantile, 105-point CDF quantile summaries, scenario moments와 시나리오를 먼저 누적한 cumulative quantile이 있다. 조건부 독립 가정을 포함한 분포 law와 seed가 고정 소스에 기록되어 있다.

테스트 통과는 모델 안전성 통과를 뜻하지 않는다. 선택 결과는 artifact의 `V40R4_METHOD_SELECTION.json`과 한국어 `V40R4_FINAL_REVIEW.md`를 따른다. 미노출 확인 자료는 없으며 May scientific reads는 0이다. May 관련 경로/index/provenance metadata 접근은 NONZERO로 별도 공개한다.

초기 자체 R4 index 누락 및 timestamp 정밀도 정정은 각 correction JSON에 보존했다. 두 정정은 모델 진단/학습 전에 이루어졌으며 보호 worktree 파일을 삭제하지 않았다. R2는 `SUPERSEDED_BY_V40R3`, R3는 `V40R3_FUTURE_GPUWORK_SAFETY_FAIL` 상태로 보존한다.
