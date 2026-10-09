# IEEE8500 V42 출처 및 권위 동결

연구일은 **2025-05-01**, 코드 검토일은 **2026-10-09 (Asia/Seoul)**이다. 독립 worktree의 검토 시작점은 당시 `v42`의 `de6f79cd2cd215f0ed657b99d24b9ac26980ddc1`이다. 종료 시점에는 원격 `87480938c4c3eb9faca9eadef7a87e8e12a44d18`을 관측했다. 추가41파일 외 기존962source의 byte·Git blob은 동일하며 checkout/rebase하지 않았다. [진행분 감사](SOURCE_ADVANCE_SINCE_REVIEW_KO.md)에 V10 수치 정책과 B1/B2 적용 범위, 예산·오류 분류 API를 pin했다. B3/IEEE8500/6대/LV 전체 Native 연결은 미검증이다. 본 작업에서 기존 캠페인의 Worker, Scheduler, 입력, ledger, 예산 및 source version을 전환하지 않았다. 외부 RecoveryV10 task3개·manifest1개의 신규 관측과 기존138파일·44등록의 보존은 별도 기록했다.

`V42_SOURCE_SHA_MANIFEST.json`은 기준 checkout에 존재하는 **962개 V42 Python/HTML 파일의 실제 byte SHA256**을 저장한다. 원본 파일의 줄바꿈도 바꾸지 않았다. `verify_source_identity()`의 BYTE_IDENTITY_ONLY 검사가 PASS했으며, 이것은 모델·Native·OpenDSS PASS를 뜻하지 않는다. Manifest의 `source_content_sha`는 파일별 SHA roster의 결정적 SHA다. Git PR 파일은 checkout하지 않고 고정된 Git object의 원본 byte를 읽어 별도로 pin했다.

| 출처 | 고정 SHA / 역할 | 현재 권위 및 사용 범위 |
|---|---|---|
| [검토 시작점 v42](https://github.com/BeaverVillage/MobileESS/tree/de6f79cd2cd215f0ed657b99d24b9ac26980ddc1) | `de6f79cd2cd215f0ed657b99d24b9ac26980ddc1` | 검토한 A/M core·원본 검증기·정수 공간·Native 예산의 기준; 이후87480938에서도 동일 blob |
| [종료 관측 v42/V10](https://github.com/BeaverVillage/MobileESS/tree/87480938c4c3eb9faca9eadef7a87e8e12a44d18) | `87480938c4c3eb9faca9eadef7a87e8e12a44d18` | 신규41파일 source-only 감사. 직접 numerical API는 May2025 B1/B2. B3·6대·LV 실제 source 연결 미검증 |
| [PR #191](https://github.com/BeaverVillage/MobileESS/pull/191) | `40b6f94dcd80e470f93c73b7479fdd2d9d91c3f2` | OPEN 상태의 B3 A1→M1→A2→M2 source bridge. 현재 v42에 병합된 코드로 취급하지 않음 |
| [PR #192](https://github.com/BeaverVillage/MobileESS/pull/192) | `74908e997112a3148d0e0e7373055fc9f52d3cc7` | 검토 시 OPEN 상태의 B2 builder 개선 출처. 최신 v42에 존재하는 B2 모듈 byte와 PR Git byte는 각각 독립 pin |
| [PR #128](https://github.com/BeaverVillage/MobileESS/pull/128) | `3872dea8130baa25fd3deaabeddeabee5fbd730f` | IEEE123의 독립 Actual RegControl 원칙. IEEE123 장치 수·capacitor 정책을 IEEE8500로 복사하지 않음 |
| [PR #129](https://github.com/BeaverVillage/MobileESS/pull/129) | `97ef9cc9b655d93a42b0b43d593aac01b951c6f3` | IEEE123 May B0 zero-margin holdout. 전압 PASS candidate와 전체 전기적 PASS의 구분을 유지 |
| [PR #45](https://github.com/BeaverVillage/MobileESS/pull/45) | `ca4796ad289cd58d11dc0506539476c4dc96e1d3` | IEEE8500 V41R4 arrival/connection-ready 구분과 과거 회귀 증거. 현재 V42 이동 알고리즘 대체에 사용하지 않음 |
| [PR #52](https://github.com/BeaverVillage/MobileESS/pull/52) | `53b668d62d90c2795932e6fc12a0bbd92d3a8b26` | 과거 May01 BG 경계 0.5775/0.578 및 추천 0.574의 역사적 증거 |
| [PR #55](https://github.com/BeaverVillage/MobileESS/pull/55) | `e465d2648b1cdd8d8a9dc2bb4af1e2ae0f2d4532` | 과거 six-MESS Actual B0/B3 결과·원본 archive 출처. B3 SOC floor 예외를 현재에 이전하지 않음 |
| [PR #62](https://github.com/BeaverVillage/MobileESS/pull/62) | `cf6d0c86c877e73db09e09eec903f176486d2df1` | 과거 paper-PCC scale-only BG 0.552/AIDC 2.40/MESS 2.00. 600초 종료 규칙을 현재 V42에 이전하지 않음 |

현재 원본 알고리즘 API는 다음과 같다. SHA는 동일 이름의 `V42_SOURCE_SHA_MANIFEST.json.files`에서 재확인할 수 있다.

| 영역 | 실제 source API |
|---|---|
| A-stage | `v42_may25_recovery_v9.a_stage.run` → `v42_may_build_v6.a_stage.run`; 기존 Phase I, full pricing, integer recovery, independent replay |
| M-stage | `v42_may25_recovery_v9.m_stage.run` → `v42_may_campaign_native90.m_stage.run`; 기존 FULL→Compact→C3A Hybrid, exact LB/strict UB |
| M 원본 생성기 | `v42_may_campaign.m_model.build_case`, `v42_native.mess.solve`, `v42_native.mess.validate` |
| A 물리 입력 | `v42_pr134_b1.native.bind`, `v42_temporal.native.load_power`, `v42_may01.prepare.native_coefficients` |
| Native 예산 | `v42_may_campaign_native90.budget.DateBudget.native_optimize` 및 최신 V9 admission/precision routing |
| 전력망 | `v42_native.grid.add_grid`, `v42_thermal.authority.current_authority`, `v42_integrated.contract.physical_authority` |
| Actual/Fresh | `v42_native.actual.run_dday_actual`, `v42_may_campaign_native90.operations.actual/fresh`, `v42_regcontrol.authority.compile_verified` |
| B3 검토 API | PR191의 `InjectionAuthority`, `OriginalAStageBridge`, `OriginalMStageBridge`, `SourceStageLedger`, `OriginalOperationsBackend` |

현재 V9는 5월 A PHASE_I/ORIGINAL_P1에 `FeasibilityTol=OptimalityTol=1e-9`, `NumericFocus=3`, `ScaleFlag=2`, Phase I `Presolve=0`을 적용한다. B2 수용 P1 Native 진입에도 동일 네 고정밀도 설정을 적용한다. PR191의 B3 대응 정책은 별도 pin된 `numerical_policy.py`에 있다. 본 통합 인터페이스는 이 설정을 새 IEEE8500 실행으로 적용했다고 주장하지 않는다.

IEEE8500 Feeder의 DSS 원본 byte, 접속 노드/도체/권선 정격, 원본 좌표, v3 AIDC/STA/SCATS ID는 별도의 실제 Feeder·위치 감사에서 확인한다. 옛 IEEE8500 실행 코드는 출처와 구조 확인에만 사용한다. 과거 generator의 절대경로, V41R4 AIDC 모델, 600초 중단 정책, QSAFE repair 또는 SOC 예외는 현재 Production Authority가 아니다.

최종 Production source SHA, 전력망 설정 및 접속·scale 동결은 적격성 검사 후 하나의 `FINAL_SINGLE_SCENARIO.json`에만 부여한다. STOP 또는 미선정 결과는 `SELECTED_AND_FROZEN`으로 표시하지 않는다.
