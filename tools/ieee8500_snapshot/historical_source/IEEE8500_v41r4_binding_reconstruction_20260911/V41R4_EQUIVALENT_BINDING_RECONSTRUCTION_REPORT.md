# IEEE8500 V41R4-equivalent AIDC binding reconstruction

**IEEE8500_V41R4_AIDC_BINDING_PASS** — non-electrical/AIDC structural binding 범위의 PASS이다. Production 실행 승인이 아니며, numerical electrical preflight PASS 또는 AC feasibility 인증도 아니다. Optimization / Fresh / B0–B3 campaign 실행은 모두 0회이다.

중지된 IEEE8500 production 결과·checkpoint·새 neighborhood 코드·coefficient payload는 재사용하지 않았다. 원본 보존 여부를 확인하기 위한 SHA 계산만 수행했다. 기존 NONAUTHORITATIVE 분류를 유지하며, 이 binding PASS로 과거 결과를 재승인하지 않는다.

## Frozen May21 input binding

| 항목 | 요구값 = 관측값 |
|---|---:|
| reference jobs | 708 |
| temporal-option jobs | 39 |
| spatial-option jobs | 364 |
| migration-option jobs | 364 |
| restored temporal candidates | 16,392 |
| base candidates | 1,325,555 |
| total candidates | 1,341,947 |
| PARTIAL/shared jobs | 361 |

Decompressed candidate stream SHA256: `878116c6e5d9204b8b02cf651ca669c23f1afab1f2cd03920f8620cc5fc82397`

Original compressed artifact를 읽고 모든 UID/option tuple의 원본 순서와 row bytes SHA를 검증했다. 후보 파일을 새로 생성하거나 줄이지 않았고, base 후보가 전부 포함됨을 확인했다. May04 global counts는 적용하지 않았다.

Installed capacity: 780 GPU; AIDC01–AIDC12 = [80, 40, 80, 40, 100, 80, 40, 80, 40, 80, 40, 80]. Frozen power law와 C1을 그대로 호출했다. Frozen operating-point의 V41R4 B0 입력과 비교한 GPU / IT / PCC kW / PCC kvar 최대 절대 차이는 모두 0이다. PARTIAL/shared 361개는 원본 aggregate GPU-slot semantics로 포함된다.

## Structural-equivalence evidence

원본 v40g.optimizer의 AST에서 전기적 평가/행과 optimization 이후 실행만 제외한 compile-only non-electrical projection을 작성했다. 원본 AIDC 선택·migration factorization·UID serial WAN·GPU occupancy recurrence·C1 PWL·reserve 생성 문장을 그대로 실행하여 실제 Gurobi 모델을 만들었다. Gurobi optimize는 호출하지 않았다. Reference, IEEE8500 B1, 원본 make_solver로 변환한 IEEE8500 A1을 비교했다.

- Non-electrical variables: 368,424; linear rows: 5,558; general constraints: 2,607; nonzeros: 1,765,685.
- Original cohorts: 668; 변수 이름/type/bounds, 선형 rows, WAN/migration rows, indicator/MAX/PWL rows 및 P2/P3/P4/P5 coefficient SHA가 세 구성에서 일치.
- 모든 candidate의 eligibility 및 기존 temporal model_boundary 검사를 원본 machinery로 수행했다.
- P5는 original cohort rank를 유지한다. 개별 UID sorted rank를 사용하지 않는다.
- B1과 objective evaluator는 원본 함수 code object와 동일하며 frozen tuple reader만 연결했다.
- A1은 원본 v41r4_b3_equivalent.make_solver / make_seed의 정확한 변환을 사용한다. 동일한 B0 candidate/P4/P5 authority, final B1 assignment 재사용, M1 numeric P/Q 고정 의미를 보존한다.

| Structural field | SHA256 |
|---|---|
| Variable identity | `c3e71eb8f2174d8556349ff6f3c04394715d77f50eced4a80c690de42b47bdef` |
| Linear constraints | `2371f5e7b673094055d015aa0a97f7ff1062307f58d32c03a4e48bf2a28039d6` |
| WAN/migration linear rows | `7ba93f654516b1f34f75db13ad3541fd925aa95b574a9d4811e95aa9412ffef0` |
| General constraints | `f54c2c53cfe9470f3c1e642e1126ec0268fb9771005c32e8a668f10a286aea0e` |
| P5 cohort rank | `5f85bfb2a2cc9eb3c2cc9c18eb46ffa44fd73753e1c23252c4eb9e9a842be4d9` |
| P2 coefficient | `e1c0711b941cc9b1967c5562c98d09db229248d9da61df9f0813980c06234803` |
| P3 coefficient | `67cbcd6a81834cc0594e40a415ac77d94400e7dd9395c44ebdc632b3b92e5b62` |
| P4 coefficient | `271608ac7a7c8df8933dead7fae27df0884e421da0dac1774216499e25fa684a` |
| P5 coefficient | `df145874d375cb08d217018e20e2655da5192d332773baa9bc48dcb1a1df2cfb` |

## Stage, budget, seed

원본 P1→P2→P3→P4→P5 stage ordering과 upper-priority locks의 AST가 B1/A1에서 동일하다. Original BoundedLex 및 V41R4 continuous LoopBoundedLex를 연결했다. 허용된 시간 변경은 총 14,400초뿐이다. 원본 GUARDS 비율 [900,480,180,120,120]은 그대로이므로 배분은 [7200,3840,1440,960,960]초이다. Fake monotonic clock으로 30min/1h/2h/deadline 의미를 검사했으며 실제 대기나 search loop 실행은 하지 않았다.

B1 reference seed는 원본 choice/placement Start와 original feasible_seed의 non-electrical fill 의미를 사용했다. 원본 job_audit 및 row_audit로 non-electrical seed의 모든 행을 대입 검증했다. 전기 port rho는 projection에서만 제외되므로 이를 물리적 seed PASS로 해석하면 안 된다.

A1은 원본 make_seed대로 final B1 assignment를 읽고 WAN/migration 값을 0으로 초기화하지 않는다. 새 production root의 SHA-verified seed만 허용하며 stopped production 경로는 차단한다. 실제 final B1은 아직 생성되지 않았으므로 실제 B1 결과와의 hash binding 검증은 추후 승인된 실행 시 수행해야 한다. 이번에는 원본 seed adapter 의미와 non-electrical 구조를 검사했다. 24-location M1 P/Q binding은 algebra-only synthetic fixture로 검사했고 OpenDSS나 모델 부하에 주입하지 않았다.

## AUTHORIZED_ELECTRICAL_DIFFERENCE

유지된 authority: 2025-05-21; source 1.0400; Vreg 123.5 V; alpha8500 0.50; CAPBank3 OFF; 기존 12 AIDC / 24 MESS PCC. 60-dimensional original control interface를 보존한다: 12 aidc_load_kw + 24 mess_p_kw + 24 mess_q_kvar. AIDC Q는 기존 PF를 따르며 새로운 독립 AIDC Q 결정변수를 추가하지 않는다. Road IDCxx→electrical AIDCxx 변환은 PCC boundary에서만 적용한다.

P1 voltage/current/flow matrices, branch axes, grid rows 및 그 numerical payload는 이 단계에서 만들거나 시뮬레이션하지 않았다. 이들만 structural differential에서 분리했으며 numerical preflight는 미실행 상태로 남긴다. 기존 stopped coefficient를 복사해 생산 authority로 승인하지 않았다. 별도의 전기적 coefficient/API 검증 및 full grid seed validation 없이는 생산 실행할 수 없다.

## Source hashes

| Source | SHA256 |
|---|---|
| [dayahead/v40g/optimizer.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v40g/optimizer.py>) | `f2a64cbd0c28215f8eeaac48235f1d2b3d58d6c07cd5ce321a6535ae050ba3cc` |
| [dayahead/v41/objectives.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41/objectives.py>) | `a5f385a0893796e67b3995dd13ce9aef7f02c4f965944b95c7746bc276a2fd85` |
| [dayahead/v41r1/bounded_solver.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/bounded_solver.py>) | `db57efc8da824fb6777bdf5ca7a7181030d6d4104a084c0cf107cea738b79d13` |
| [dayahead/v41r1/feasible_seed.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/feasible_seed.py>) | `a69f8b043da3d9c7b20ecb16008a1313a744dbfc5ff35c3eade6f4c94151fd70` |
| [v41r4_b3_equivalent.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/v41r4_b3_equivalent.py>) | `284b1557590bd492d3baa988bbff3b3fcb8590eb2f39f276de0e1f12752b7ecb` |
| [v41r4_loop_budget.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/v41r4_loop_budget.py>) | `68ae5b101db061979f04024bf5a33b2bcea819f14b56400dd8ff3a7194e9e28c` |
| [dayahead/v39a/power.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v39a/power.py>) | `ff264b087b2f7c1549121034ee4606a90af55b666ccd4f47314f18d9cc3e010e` |
| [dayahead/v28r2/c1_affine.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v28r2/c1_affine.py>) | `912c870a2c062431cac60f2157f3b4399ad824119facdafbd7ac3f1788c40c13` |
| [dayahead/v41/reserve.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41/reserve.py>) | `f0b6fd207321599f8903ac842025907a0f12b10b9aa41cf7aca79344c8e090ba` |
| [dayahead/v41r1/migration.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/migration.py>) | `c8908d56662dcb3820d90412dc1fa4a1094b73c95638938ff5096a4bdad37aff` |
| [dayahead/v41r1/terminal.py](<C:/codex_mobileess_workspace/MobileESS_v41r3_scale_rebalance/dayahead/v41r1/terminal.py>) | `593721d7cc85512bf34b900255468473607550af4011c00de1c5fecafef44c41` |

전체 input/source/code SHA는 EXACT_INPUT_SHA256.json, ORIGINAL_V41R4_SOURCE_SHA256.json, RECONSTRUCTION_CODE_SHA256.json에 기록했다.

기존 stopped evidence 4,638개, 기존 topology/PCC/electrical/operating authority 3,997개, 이전 audit의 source/input 59개를 hash-only 재검증했고 변경은 0개였다. New workspace의 initial import/temporary-directory 보호 설정 오류는 development failure artifact로 보존했다. 당시에도 optimization이나 외부 authority 수정은 없었으며 최종 structural 비교는 완료되었다.

GATE: non-electrical structural binding PASS; production execution remains disabled. B0/B1/B2/B3/Fresh는 시작하지 않았다.
