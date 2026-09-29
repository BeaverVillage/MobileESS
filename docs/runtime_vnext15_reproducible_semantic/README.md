# V42 reproducible submission-semantic integration

Base: Runtime-vNext14R2 PR #88, `ce72e7f890f2bb1f330aa8c66910fc43a74ea06f`. 결과: `SEMANTIC_INTERFACE_READY_MODELS_NOT_PROMOTED`.

원본 Kestrel 6,326,884행을 감사하고 V13 GPU 621,583행의 source identity를 확인했다. 새 historical semantic whitelist는 user/submit_line 두 개다. Mutable 최종 snapshot과 시점이 미확인인 derived/custom field는 제외했다. 인터페이스는 10개 optional 개념을 지원하되 현 모델은 고정 whitelist만 쓴다.

공통 `v42/semantic_adapter.py`가 namespace-separated categorical token, FeatureHasher262144, TRAIN-only SVD32(seed1401), TRAIN recurrence를 제공한다. 과거·재생·새 입력의 코드는 동일하다. CC4는 사용자가 지정한 기존 T0/B0의 target·hourly resolution·LightGBM family를 유지하고 과거 1/6/24/72h semantic state와 KMeans8 composition만 추가했다.

Runtime 선택은 `NONE`, CC4는 `C0`다. 안전 조건·sharpness 기준을 낮추지 않았고 legacy feature flag 기본값은 FALSE다. 큰 모델/행별 예측은 `.local`에 유지하고 local manifest로 결속한다. 50개 답변은 FINAL_REVIEW_KO.md, 정확한 수치와 gate는 비교 CSV 및 selection freeze에 있다.

원본 RADDiT vector·private exporter·원본 암호화 좌표·대형 LLM은 필요하지 않다. April 선택·May payload 해석·optimizer physics 변경·OpenDSS selection은 없다. 본 결과는 제한된 제출 identity/co-occurrence 표현의 predictive contribution 실험이다.

재현은 prior namespace를 읽기 전용으로 보존하고 별도 출력 위치에서 수행한다. prepare15 → audit_fields15 → test_semantics15/test_integration15 → register15 → runtime15 순서다. 그 후 prepare_cc415와 cc415 register/prepare/run을 실행한다. Runtime 및 CC4 semantic prepare/replay는 V13 exact environment를, CC4 LightGBM run은 CC4_EXECUTION_ENVIRONMENT.json의 원래 NumPy1.26.4 환경을 쓴다. 환경 분리 이유와 실패 시도는 CC4_SEMANTIC_ENVIRONMENT_REPAIR.json에 있다. 중간에 code hash가 바뀌면 guard가 거부한다. 이미 끝난 모델을 재학습할 필요 없이 stored artifacts와 verify15로 재검증할 수 있다.

이 commit의 결과를 바꾸지 않는 전달 검증은 `python -B docs/runtime_vnext15_reproducible_semantic/verify15.py --check-delivery`다. 인자 없는 verify15는 과학적 지표를 다시 확인한 후 현재 파일의 manifest와 검증 receipt를 새로 쓴다. 전체 재학습에는 원본 archive와 선행 local evidence가 필요하며, `prepare15`는 정확한 base commit에서만 허용한다. 완료된 이 폴더에서 등록 파일을 덮어쓰거나 모델을 재학습하지 않는다.
