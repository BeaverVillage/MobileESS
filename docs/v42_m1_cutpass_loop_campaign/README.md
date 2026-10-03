PR135 exact `6795206a09e5f6ce1ad4de5c29a4c729bf79bd43`에서 수행한 단일 M1 시험과 향후 May campaign orchestration 증거다.

M1은 PR135와 동일한 reduced scientific matrix, objective, bounds, vtypes, RHS, senses, names와 accepted A1/NormalAmps/source authority를 사용했다. Solver 설정에는 `CutPasses=1`만 추가했고 exact zero-action candidate를 316,743개 column의 `Start`에 실제 입력했다. Candidate의 numerical/physical PASS와 native Start 수락을 별도로 판정한다. Start의 reference objective는 solver incumbent가 없으면 scientific UB가 아니다.

600초까지 non-root/branch가 관측되지 않아 같은 optimize 호출을 600.29초에 중단했다. P1 호출 1, retry/restart/sweep 0, P2 0이며 추가 시험은 실행하지 않았다. 유효한 새 LB는 0.5687116103498322지만 UB와 gap은 NULL이다. 다음 병목 분류는 `root cut-processing / formulation-strength`다. Root relaxation 완료를 root processing 또는 branch 완료로 해석하지 않는다.

Native log의 `User MIP start did not produce a new incumbent solution`과 `Another try with MIP start`를 보존했다. 수락된 incumbent가 없으며 구체적인 solver-side tolerance 위반 원인은 노출되지 않았다. Rejection의 원인을 1e-8 tolerance로 단정하지 않는다. Solver tolerance 변경, Start repair, clipping, rounding은 0이다.

600초 watch는 callback 밖에서 monotonic wall clock으로 중단 요청을 한다. 그때 마지막 MIP 관측은 475.782초의 root, cuts 0, UB NULL, LB 0.5687116103498299다. **정확한 600.000초 native node/cut/UB/LB는 NULL**이며 stale telemetry를 그 시점 값으로 대체하지 않았다. Terminal native node count 1은 non-root 진입을 증명하지 않는다. First branch는 native API에서 직접 노출되지 않아 NULL로 보존한다.

Campaign 코드는 backend가 등록되지 않은 상태의 orchestration/contract이며 production 실행 entry point는 차단된다. 향후 별도 승인된 task에서 scientific validators와 optimizer/Actual/Fresh-AC backend를 결합해야 한다. 이 task의 31-day plan은 1,458개 NOT_RUN stage다. 동작 증거는 1일의 결정적 synthetic fixture 48개 stage에 한정된다. Fixture certificate는 mock assertion이며 production scientific acceptance가 아니다.

Main은 arm-major B0 전체 May → B1 전체 May → B2 전체 May → B3 L1 전체 May다. 각 day의 Planning → freeze → Actual → Fresh AC → validation freeze를 순차 수행하고, arm의 마지막 validation freeze 전에는 다음 arm을 시작하지 않는다. Main 전체 124개 day/arm validation freeze를 요구하는 별도 gate 뒤에만 B3 L2/L3/L4를 실행한다. Main comparison은 B0/B1/B2/B3 L1로 고정하며 convergence collector는 L1–L4를 별도로 처리한다.

각 B3 loop는 A1 → M1 → A2 → M2다. 최종 AIDC는 A2, 최종 MESS는 M2다. 같은 day의 이전 loop Planning MESS는 다음 A1의 fixed counterpart이고 이전 AIDC는 warm candidate만 된다. M1은 A1 AIDC를 fixed, A2는 M1 MESS를 fixed, M2는 A2 AIDC를 fixed한다. M2의 route/movement/P/Q/SOC는 모두 free이며 M1 MESS는 warm candidate만 된다. Hk는 scientific state만 해시하고 loop label, day metadata, parent SHA, timestamp를 제외한다. Fixed point/2-cycle은 분석 결과만 기록하고 4-loop 진행을 중단하지 않는다.

Planning firewall은 authority에 등록된 D-1/forecast/Runtime CC4의 exact path+SHA와 선언된 accepted Planning freezes만 broker에 전달한다. 미래 정보와 Actual/Fresh/realized provenance를 거부하고, Planning 중 raw Python open/Path read도 exact allowlist로 검사한다. Preopened Actual stream, low-level fd read, subprocess, ctypes/mmap reader, background reader를 거부한다. 금지된 read를 adapter가 catch해도 stage는 FAIL이다. 모든 Planning/final-freeze read의 before/after SHA와 read attempts를 보존했다. Actual 완료 상태는 `predecessor_accepted` 순서 gate로만 전달된다.

이는 신뢰된 broker adapter의 **dependency firewall**이며 임의의 악성 native code에 대한 OS sandbox는 아니다. Opaque native I/O와 미리 로드한 realized 값을 closure로 전달하는 adapter는 허용된 capability가 아니다. Production backend는 이 broker-only contract를 준수해야 한다. 이 구현 범위와 bounded read audit를 함께 보고하며 production leakage 시험을 수행했다고 주장하지 않는다.

Resume은 ACCEPTED prefix, immutable exclusive publication, complete/validated freeze, source/authority/scientific-contract/plan SHA 일치를 요구한다. RUNNING/FAILED partial optimizer state, 불완전 Actual/Fresh AC, mismatched SHA, stale worker lease는 거부한다. Atomic freeze 뒤 ledger를 갱신하며 중간 장애로 남은 orphan freeze를 덮어쓰거나 자동 재최적화하지 않는다.

원본 PR135 tracked 파일과 scientific cache를 보존했다. Tests는 M1 worker와 postsolve audit/P2 gate가 종료된 후 한 pytest process씩 실행한다. 기존 PR135에서도 기록된 OpenDSS native exception trace를 삭제하거나 warning count로 숨기지 않는다. 초기 실패와 수정 후 결과는 별도 로그에 보존한다.

Post-test names 검사에서는 `FULL_DATA.row_names`의 반복 family label `flow`와 native MPS constraint identifier `c0`, `c1`, …를 처음에 혼동한 검사 실패를 보존했다. 올바른 기준인 byte-identical PR135 `REDUCED.mps`의 ROWS 목록과 native names를 전수 비교해 PASS를 확인했다. 이는 검사 namespace 정정이며 model/row/constraint 변경은 0이다.

JSON schemas는 jsonschema 4.26.0으로 bounded states/metrics를 검증했다. 시스템 Python package를 변경하지 않고 `CUTPASS_LOCAL/SCHEMA_DEPS`에 설치한 검증 전용 dependency다. 재현 시 `python -m pip install --target ../CUTPASS_LOCAL/SCHEMA_DEPS jsonschema==4.26.0`을 사용할 수 있으며 설치 로그도 보존했다. Scientific solver의 dependency 또는 parameter 변경은 아니다.

재현 명령은 `python -m v42_campaign.artifacts`(bounded evidence), `python -m v42_cutpass.tests -q`(single-process tests), `python -m v42_campaign.postverify`(읽기 전용 보존 검사), `python -m v42_campaign.finalize`(보고서/manifest)다. **M1 scientific run을 재실행하지 말 것**: `CUTPASS_LOCAL/P1_STARTED.json` marker가 재실행을 차단한다.

Gurobi 공식 문서: [CutPasses](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parametercutpasses), [PoolNX / terminal solution-pool query](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#poolnx). SolutionNumber는 terminal 이후 기존 native pool 조회 selector로만 사용하며 추가 optimize 호출이나 parameter experiment가 아니다.
