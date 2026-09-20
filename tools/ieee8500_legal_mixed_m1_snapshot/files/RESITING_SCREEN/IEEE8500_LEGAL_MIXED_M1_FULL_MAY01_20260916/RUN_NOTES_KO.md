# IEEE8500 legal_mixed_M1 — May-1 full validation

사용자가 승인한 2025-05-01 full 96-slot B0/B1/B2/B3 및 Fresh 전용 실행이다. Actual은 실행하지 않는다.

- IEEE8500: 1 day worker, Gurobi Threads=4. IEEE123 3×4 실행은 변경하지 않는다.
- `LAYOUT.json`의 AIDC 12 PCC와 MESS 6 STA PCC, s_DC=s_MESS=1.00 고정.
- 나머지 18개 MESS 서비스 PCC는 사용자 답변에 따라 기존 production mapping 그대로 상속한다. 최종 36개 접속 인터페이스(12 AIDC 부하 + 24 MESS 서비스)는 `PCC_OVERLAY_INVENTORY.json`에 기록했다.
- background alpha=0.574, PV alpha=0.50. 기존 workload/traffic/native feeder authority 보존.
- screening job/dispatch/route/coefficient 또는 결과를 production 결과로 재사용하지 않는다. B0는 새 chronological cold-start 96-slot이며 Fresh는 새 OpenDSS context이다.
- 전기계수는 새 infrastructure의 전체 96 slot × 60 control에서 생성한다. 원래 production linearization과 같이 각 slot의 settled B0 control state에서 signed finite differences를 계산한다. DA/Fresh exact replay에서는 native automatic controls가 동작한다.
- 정책 순서: B1 → B2 route/PQ → B3 M1 route/PQ → B3 A1 AIDC → B3 MF fixed-route PQ → 최종 Fresh 집계. B1과 B3-A1은 기존 14,400초의 연속 search-loop budget과 P1–P5 계층을 보존한다. 준비/route/Fresh 시간은 별도이다.
- `bootstrap.protect()`가 Python 파일 쓰기를 현재 namespace 안으로 제한한다. solver nodefiles, traffic cache, candidate cache, temporary files, logs도 이 namespace를 사용한다. 원본 input/code는 읽기만 한다.

현재 상태의 authority는 `SUPERVISOR_STATUS.json`, 세부 단계는 `STATUS.json`이다. 정책별 `*_production.log` 및 `*_FAILURE.json`을 확인한다. 완료 시 `FULL_RESULT.json`과 `FULL_DA_FRESH_METRICS.csv`가 생성된다.

15분 간격 follow-up `ieee8500-may-1-full-validation`을 이전에 등록했으나, 최근 update 요청에서 app이 automation 미존재를 반환했다. 현재 자동 follow-up은 활성 상태로 보장할 수 없다. 로컬 supervisor의 순차 실행은 이 automation에 의존하지 않는다.

B1 최초 준비 시 기존 authority의 `may_domain.py` 경로가 없어 중단되었다. 원래 SHA-256과 동일한 보존 사본을 현재 namespace의 `authority_sources`에 복사하고 `SOURCE_PATH_ALIASES.json`으로 해당 읽기 경로만 연결했다. 원본 코드/authority 파일은 변경하지 않았으며 동일 infrastructure와 새로 생성한 96-slot coefficients로 재개했다. 최초 실패 log는 보존되어 있다.

승인된 18개 접속점까지 포함한 B0 DA/Fresh 결과는 서로 동일하다:

|rho|Vmin|Vmax|Transformer current/rating|Transformer kVA/rating|Critical slot|Convergence|
|---:|---:|---:|---:|---:|---:|---:|
|0.983428567784|0.951013516811|1.041738003180|0.283185243981|0.287688680426|75|96/96|

Critical line: `Line.tpx21459660c0`, terminal 2, node 1. B1/B2/B3 결과는 완료 전에는 확정하지 않는다.

사용자의 정정에 따라 기존 transport–grid spatial-correlation audit은 `SUPERSEDED_NONBLOCKING_DIAGNOSTIC`이다. Traffic distance/neighborhood와 IEEE8500 electrical/layout distance의 일치는 요구하지 않는다. AIDC/STA identity, original traffic coordinates, travel-time matrix, mobility energy가 보존되면 cross-layer mapping은 valid이며, 이전 P0 FAIL은 production 및 electrical freeze를 차단하지 않는다. 위치/scale은 결과를 보고 조정하지 않는다.

`start_validation.py` 및 중단된 `B1_coefficients`는 18개 inherited port 답변 이전의 예비 실행이다. 최종 비교에는 `electrical_engine.py`의 36-interface infrastructure로 재생성한 `B0_REPLAY`, `B0/Fresh`, `coefficients` 및 후속 production 결과만 사용한다.

B1 재개 전 F_AND_O equivalence gate가 원래 경로에 없는 historical test evidence를 읽으려다 실패했다. 16개 frozen evidence record의 SHA-256 및 byte size를 모두 확인했으며, 누락된 파일은 원래 hash와 일치하는 보존 사본을 `authority_sources`에 복사했다. `evidence_path_binding.py`는 누락된 경로만 동일 내용의 사본으로 읽으며 원래 gate의 record 비교와 PASS 요구는 유지한다. 원본 gate/source는 수정하지 않았다. 검증 smoke 결과 `ORIGINAL_EQUIVALENCE_GATE PASS`를 확인했다.

완료된 현재 full-run B1 전기 제약 준비 결과와 입력 487개 record를 `B1_PREPARATION_RESUME.json`에 고정했다. 재개 worker가 hash/size와 원래 PCC bounds를 다시 확인한 후 재사용한다. Screening proxy 재사용이 아니며, 중단 전에 optimization search는 시작되지 않았다. 실패 status와 기존 ranking은 `repair_missing_gate_evidence_*`에 보존했다. Supervisor PID 43404 / worker PID 44392로 1×4 실행을 재개했으며, 현재 PID는 항상 `SUPERVISOR_STATUS.json`을 기준으로 확인한다.

후속 B1 모델 생성 시 Gurobi Error 10013(`Unable to write file`)이 발생했다. 원인은 Unicode 경로의 `B1/SOLVER.log`이며 과학적 모델/AC 실패가 아니다. `D:\ChatGPT\Mobile ESS 2\RESITING_SCREEN\IEEE8500_LEGAL_MIXED_M1_FULL_MAY01_20260916`이 같은 실제 폴더임을 `os.path.samefile`로 확인했다. 새 폴더로 복사하지 않고 이 기존 ASCII alias에서 supervisor/worker를 실행한다. `native_solver_io_preflight.py`로 원래 equivalence gate 및 Gurobi 4-thread license, LogFile, NodefileDir 설정, 작은 모델 solve, MPS/SOL 파일 쓰기를 검증해 PASS했다. Nodefile 실제 spill은 이 작은 검증에서 유발하지 않는다.

Supervisor와 worker는 비-ASCII 실행 경로를 준비 작업 전에 차단한다. 향후 실패 재개에는 `resume_ascii.ps1`이 동일 경로와 native I/O 사전검증을 사용한다. 이번 실패 로그/status는 `repair_gurobi_unicode_path_*`에 보존했다. Native scientific authority, PCC, scale, optimization semantics 및 IEEE123 실행은 변경하지 않았다.

사용자 승인에 따른 B2 seed 성능 수정: 기존 현재-B0 기반 20-state seed가 동일 병목에 집중되어 새 downstream PCC에서 초기 rho≈4e-8로 붕괴했다. 첫 full separation이 line 1,175,692개를 추가하고 모든 후속 후보가 총 1,175,712개를 재구성하여 약 401초/candidate가 됐다. `diagnostics/K200_PERFORMANCE/FORENSIC_REPORT_KO.md`에 비차단 계측 및 cache forensic을 보존했다. 이전 traffic/route table은 SHA 동일하며 이전 cache 2,211개는 삭제되지 않았다.

`current_layout_seed.py`는 현재 96-slot B0에서 다양한 native line 32개와 slot별 최대 loading을 초기 seed 438개로 선택한다. 기존 full-separation 함수, tolerance, K domain, objective 및 final exact/Fresh를 변경하지 않는다. 최종 active-set cap이나 hardcoded rho floor는 없다. `PROPAGATED_SEED_PROOF.json`의 5개 후보에서 원래 목적값 차이 0, 최대 rho 차이 5.2941e-9, 중앙값 6.6639초가 확인됐다. 사용자 즉시 중지 지시로 당시 supervisor 49136 / worker 43892를 중지한 뒤, 조건부 proof PASS 재개 승인에 따라 B2만 새로 시작했다. B0/B1은 완료 checkpoint로 건너뛴다. 기존 B2 16개 파일은 `B2_BEFORE_SEED_CORRECTION_1789572235`로 이동하고 모든 SHA를 재검증했다. `B2_ARCHIVE_RELOCATION.json`과 `PRESERVE_COMPLETED_AUTHORITY.json`을 참조한다. 새 최초 PID는 supervisor 53924 / worker 47600이며 live authority는 여전히 SUPERVISOR_STATUS.json이다.

사용자가 Actual까지 연속 실행을 명시적으로 승인했다. ACTUAL_AUTHORIZATION.json이 이전 Actual 보류 지시를 대체한다. 현재 DA worker는 중단하지 않았으며 actual_followthrough.py가 DA/Fresh 완료와 physical PASS를 기다려 actual_campaign.py를 실행한다. 기존 arrival-gated 6-MESS Actual, physical workload power law, causal robust QSAFE V2 및 independent continuous replay를 현재 PCC engine과 연결했다. Actual 시작 전에 RULE_FREEZE.json으로 최종 DA/인프라/코드/교통·관측 입력을 해시 고정하며, ordering 및 .90 목표는 Actual 차단 조건으로 쓰지 않는다. 사전검증 diagnostics/ACTUAL_ADAPTER_PREFLIGHT/PREFLIGHT.json PASS. 시간별 점검도 Actual 완료까지 유지한다.

B2 beam completed; primary exact AC failed (rho 1.1086519428, Vmin .9492725093). Existing post-selection physical closure then encountered missing historical selective_actual_revision_v1.py evidence. SHA-identical 5133-byte snapshot (870abf7a...05face) was copied into authority_sources, with explicit read alias CLOSURE_EVIDENCE_ALIASES.json. All eight original code/margin hashes and sizes verified; no gate bypass, limit or decision change. Empty unstarted closure directory and failure evidence preserved in repair_closure_evidence_1789618918. B0/B1 and completed B2 selection hashes preserved; resumed using existing search checkpoints. Actual followthrough remains enabled.

User requested pause B3 and prioritize B0/B1/B2 Actual. B3 supervisor 60020 / worker39224 and followthrough7788 stopped after identity verification; checkpoints preserved in diagnostics/ACTUAL_B012_PRIORITY_1789629598. Actual_B012 namespace freezes completed B0/B1/B2 DA/Fresh and fixed infrastructure before realized data execution. B0 Actual rho=.9815501233047021; B1=.9800703763390655, both physical PASS. B2 baseline rho=1.014294076389173 before QSAFE. The lower-Q extreme at slot29 failed native convergence and the legacy adapter assertion aborted the run. actual_b012_resume.py preserves the QSAFE search and solver settings, returns native nonconverged trial arrays to inherited feasible(r), which rejects converged=False. A supplementary runtime freeze records this error handling change. Same failed trial rejection smoke passed. B0/B1 completions reused. B3 remains PAUSED_USER. Existing monitor reused at port63426 with Actual columns. Hourly automation ieee8500 is absent from the app; update returned automation-does-not-exist, so no claim of active hourly monitoring.

User explicitly resumed Actual on 2026-09-18. B2 prior process51960 exited without Python traceback at slot32 after 32 accepted slots. original Q_ACCEPTED_CHECKPOINT and Q_CONTROL_EVENTS archived under resume_slot32_1789689754. actual_b012_checkpoint_resume.py verifies all original hashes, preserves accepted slot0..31 Q/events, reconstructs their exact chronological prefix without reoptimizing, and continues original QSAFE at slot32. In-flight slot32 cache was memory-only: the same deterministic capped search is replayed for that slot, not a larger domain or budget. Full final independent96 AC and battery audit remain unchanged. B0/B1 reused; B3 remains PAUSED_USER. New process recorded in ACTUAL_B012_PROCESS.json.
