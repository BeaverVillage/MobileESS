원본 Kestrel 제출 정보를 동일 코드로 historical replay와 미래 V42 입력에서 변환하는 독립적인 semantic 경로를 추가했다. 비공개 RADDiT exporter/vector 복구와의 의존성을 제거하며 원래 RADDiT embedding을 사용했다고 주장하지 않는다.

원본 6,326,884행 감사 후 최초 제출 값의 의미가 확인되는 user/submit_line identity만 historical whitelist에 포함했다. Mutable account/name/partition/qos snapshot과 custom script/job_type의 시점 미확인 필드는 제외했다. 10개 optional payload 개념, 기본 OFF flag, 숫자 전용 policy 경계 및 제출 vector 보존 cache를 구현했다.

- Runtime R0는 정확한 V13 S4 예측을 재사용하고 R1/R2만 5개 fold에서 평가했다. pooled Q90 91.77%, min-fold 66.11%, >4h 67.11%, >12h 60.12%, >24h 51.65%, Q90 pinball 4852.5745, reservation/actual 3.5360, W0 대비 0.6878. R2: pooled Q90 91.50%, min-fold 66.75%, >4h 66.87%, >12h 58.98%, >24h 45.81%, Q90 pinball 4720.1813, reservation/actual 3.4665, W0 대비 0.6743. 선택은 `NONE`다.
- CC4는 사용자 지정 T0/B0 hourly 제출 GPUh LightGBM을 유지하고 C1/C2 특징만 추가했다. 선택/유지는 `C0`이며 nominal coverage와 pinball·requirement·burst 기준을 함께 적용했다.
- TRAIN-only SVD/recurrence/KMeans, parity, future/past perturbation, 새 입력 호출성, legacy 호환성과 기존 증거 보존을 검증했다. April selection·May payload·optimizer/전력 모델 변경·OpenDSS 실행은 없다.

연구 interface 준비와 모델 승격은 별도다. 기본 실행은 legacy이고 운영 V42에 semantic 모델을 자동 활성화하지 않았다. 큰 모델/예측/logs는 .local에 보존하며 source/local/delivery manifests 및 한국어 50문항 최종 검토를 제공한다.
