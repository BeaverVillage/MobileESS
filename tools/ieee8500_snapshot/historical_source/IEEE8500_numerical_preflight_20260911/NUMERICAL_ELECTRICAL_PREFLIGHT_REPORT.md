IEEE8500 numerical electrical preflight: **IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS**

검증 범위는 수치 전기 preflight입니다. B0/B1/B2/B3 optimization 및 B1 4-hour search는 실행하지 않았습니다. Gurobi는 원래 모델의 build-only와 모든 제약의 seed 대입 검증에만 사용했으며 optimize 호출 수는 0입니다.

2025-05-21, source 1.0400 pu, 전체 regulator Vreg 123.5 V, alpha8500 0.50, CAPBank3 OFF를 유지했습니다. 기존 topology/PCC/mapping/resource/rating 및 binding authority와 중단 결과의 SHA가 모두 보존됐습니다. 중단 production의 전기 계수는 재사용하지 않았습니다.

| 검증 | 결과 |
|---|---|
| 신규 계수 | 96 slots × 60 controls; signed derivative solves 11,520; 268.851 s |
| Control interface | 12 AIDC P + 24 MESS P + 24 MESS Q; AIDC Q는 기존 fixed PF, 독립 Q 변수 0 |
| Exact signed perturbation | 5 slots × 60 controls × 양/음 부호 = 600건 PASS; ±10 kW/kvar |
| 최대 voltage 예측 오차 | 2.30644938175e-05 pu (기준 0.001) |
| 최대 phase-line loading 예측 오차 | 0.000678402298051 pu (기준 0.005) |
| 최대 transformer phase-current 예측 오차 | 2.08824840353e-05 pu (기준 0.005) |
| 최대 winding-kVA loading 예측 오차 | 1.75212720094e-05 pu (기준 0.005) |
| B0 exact replay | 96/96 converged, controls settled; frozen extrema 차이 최대 2.78e-17 |
| Original B1 seed | 708 jobs; 전체 non-electrical/linear/general/electrical 제약 PASS |
| Non-electrical identity | 368,424개 변수 정의 및 P2–P5, seed SHA 동일 |
| 전체 전기 제약 | 31,945,536 rows, 누락 없이 대입 검증 |
| 전 서비스 binding | 24 MESS service → PCC → P/Q column 및 12 AIDC P/fixed-PF 연결 PASS |

B0 exact extrema: Vmin 0.972287548319, Vmax 1.041167261977, max phase-line 0.848769140370, max transformer phase-current 0.224564029228, max transformer winding-kVA 0.229467627192 pu.

P1과 exact AC의 critical witness는 동일합니다: `Line.tpx21459660c0`, `t2/node1`, bus `sx3101194c.1.2`, native primary phase **C**, slot 32 (0-based 31), 07:45. 두 값 모두 0.848769140369619 pu이며 차이는 0입니다.

전체 joint model은 원래 AIDC core (5,558 linear + 2,607 general rows)와 96개 full electrical CSR block의 합으로 보존했습니다. 각 block은 같은 원래 global PCC 변수와 단일 rho_max에 정확히 연결됩니다. 메모리 관리를 위해 affine electrical auxiliary를 대수적으로 제거하고 block별 실제 Gurobi 모델에 동일 seed를 대입했습니다. 96개를 별도로 최적화하지 않았고, 하나의 거대한 resident Gurobi 모델을 구성했다는 주장은 하지 않습니다. 총 logical linear rows는 31,951,094개입니다. 모든 residual의 최댓값은 1.11022302463e-16 (기준 1e-9)입니다. 전체 matrix/RHS/공유 변수명/seed/row audit는 `full_model/electrical_blocks/`에 저장했습니다.

전기 계수의 단위를 명시합니다. Voltage는 squared pu의 affine 계수입니다. Line 및 transformer phase current는 원래 ampere rating으로 나눈 **복소 전류 실수/허수 성분**을 flow_p/flow_q API에 담습니다(이 두 current 계열의 API 이름은 kW/kvar를 뜻하지 않습니다). Winding은 실제 복소 P+jQ kVA와 원래 winding rating을 사용합니다. Line P1에는 기존 anchored 16-face polygon을 적용하고, transformer phase current와 winding kVA에는 각각 16-face thermal bounds를 적용합니다. 0-injection MESS에서도 signed 전류 방향을 보존했습니다.

계수는 각 B0 slot의 accepted regulator/capacitor 상태 주변 local 모델입니다. Signed 검증은 동일 상태를 유지한 별도 clean OpenDSS context에서 수행했습니다. Chronological B0 replay는 native controlled logic을 활성화했습니다. 이 gate는 향후 임의의 최적화 trajectory까지 AC feasible하다는 주장이 아니며, 향후 각 policy의 final 96-slot exact AC 검증은 여전히 필요합니다.

최종 candidate stream SHA256: `878116c6e5d9204b8b02cf651ca669c23f1afab1f2cd03920f8620cc5fc82397`. Candidate universe는 1,341,947개이며 재생성/축소하지 않았습니다. 원래 P5 cohort rank, BoundedLex와 AIDC power/WAN/migration semantics는 기존 binding과 동일하게 유지했습니다.

기계 판독 gate: `IEEE8500_V41R4_ELECTRICAL_PREFLIGHT_PASS.json`. 전체 산출물 SHA: `ELECTRICAL_PREFLIGHT_FREEZE_MANIFEST.json` 및 `.sha256`. 초기 Python 구문 오류는 실행 전 개발 이력으로 별도 보존했고, 물리 rule이나 오차 기준은 변경하지 않았습니다.

Gurobi가 내부 materialization에서 일부 극소 계수를 생략하므로, 별도 `FULL_PRECISION_ELECTRICAL_ROW_AUDIT.json`에서 저장된 CSR의 모든 nonzero를 직접 사용해 전체 31,945,536개 전기 row를 다시 대입 검증했습니다. Full-precision CSR nonzero 수는 402,054,621개이며, 직접 대입의 최대 residual은 1.1102230246251565e-16입니다. 원본 CSR 계수는 삭제하거나 반올림하지 않았습니다.

첫 모델 export는 Gurobi의 한글 resolved-path 처리 오류로 중단됐습니다. 그 전에 완료된 전체 seed audit는 그대로 보존했습니다. 같은 원래 모델을 build-only로 복원하고 전역 seed 값, 96개 coefficient SHA, PCC/rho binding 및 P2–P5 identity를 재확인한 뒤, 같은 디렉터리의 ASCII junction 경로로 MPS를 저장했습니다. `export_recovery/core/MODEL_PERSISTENCE.json`에서 gzip 해제 바이트/SHA 일치까지 확인했습니다. 이 복구에서도 optimize 호출은 0입니다.
