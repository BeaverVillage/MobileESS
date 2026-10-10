# 기존 캠페인 및 원본 증거 감사

2026-10-10 Asia/Seoul의 읽기 전용 조사이다. 기존 Source Epoch, 결과, Ledger, 프로세스, 예약 Task는 변경하지 않았다.

`D:\v42_may_restart_20261010_02`의 Supervisor는 `USER_STOPPED_FOR_LB_RESEARCH`이며 workers는 비어 있다. 실행 중인 Worker/Native Solver는 관찰되지 않았다. Monitor PID 41292(B1), 99224(이전 B2), 91376(Autonomous)가 남아 있다. 별도 cleanup 프로세스 PID 77204는 관계없는 작업으로 보존했다. 중단된 Supervisor를 재시작하지 않는다.

기존 Restart 상태는 B2 PASS 0일, FAIL 3일(May01~03), 오래된 RUNNING 표기 6일(May04~07, May11~12), RETRY_PENDING 3일(May08~10), PENDING 19일(May13~31)이다. B3 31일은 모두 PENDING이다. 실제 프로세스가 없는 RUNNING 표기는 현재 실행 완료 증거가 아니다. Recovery Queue 82개는 RECOVERY_FAILED 24개, SUPERSEDED_UNSTARTED_READY 48개, QUARANTINE_DISPATCH_INTERRUPTED 5개, WORKER_ENTERED 2개, READY_VERIFIED_REPAIR 3개다.

원본 실패 원인은 feasible gap 미인증, RMP budget/scope closure drift, Infinity 정수비 변환 오류, projection cache zero-start request 불일치, 메모리/리소스 고갈, 독립 bound certificate 불일치다. B2 RESULT Attempt 34개는 전부 non-PASS이다(IMPLEMENTATION_FAILURE 3, INPUT_OR_CERTIFICATION_FAILURE 21, TIME_LIMIT_FEASIBLE_NOT_CERTIFIED 9, INPUT_FAILURE 1). 이 과거 5,400초 예산과 결과를 새 1,800초 U4 캠페인의 성공 결과로 옮기지 않는다.

기존 B2 Source는 `D:\v42run37`, commit `300acbeb7a53da184d996bc352a8527cfb3549f5`, source SHA `ba88d19a1e0d0abbbf343ee55deec49753b8e68d6a31c37c1ee9a8cf288c4a82`다. B3는 `D:\v42b3run4`, commit `c9b22a0db342168beb954c2725e99cf44a2aac16`, source SHA `f80ec9062ed7c9cef3ed136f7c0ac79e5faefd1208de41ecc8d0db8f29f995a7`이다. Autonomous manifest가 지시한 `autonomous\B3_PRODUCTION_QUALIFICATION.json`은 존재하지 않는다. 따라서 새 B3의 실제 Canary/정식 qualification이 필요하다.

B1의 기준은 `D:\MobileESS_V42\runtime\v42_may_campaign\native90_build_reuse_20261009_01`이다. Restart AUTONOMOUS_MANIFEST의 31개 결과 SHA는 모두 원본 파일과 일치한다. 31일 모두 Planning/Actual/Fresh 실행 PASS, Fresh 96슬롯 수렴을 기록했다. 하지만 May28은 전압 위반 2개, Vmax 1.050228286007951 pu를 기록했다. B1의 무위반 날짜는 30/31이며 기존 PASS의 의미를 물리 무위반으로 바꾸지 않는다. May01 Actual 최대선로부하율은 raw phase_current_a/원본 Line NormAmps를 다시 계산하여 67.6826162707868%로 확인했다(263 line phases, 슬롯 78, line.sw2::A). 변압기를 선로 최댓값에 혼합하지 않았다.

B0의 원본 증거는 `D:\MobileESS_V42\docs\v42_transformer_normalamps_contract\MAY_B0_CURRENT_RECLASSIFICATION.json`이며, 명시된 원본 NPZ 31개 SHA가 모두 일치한다. 31일/2,976슬롯 수렴, voltage/line-current/transformer-current/transformer-kVA 위반 0이며 31/31 물리 PASS다. 원본 NPZ 경로는 증거의 source_files를 따른다(OneDrive workspace의 v42_transformer_normalamps_pr 아래 DAY_202505DD). 무단 복사나 원본 재작성은 하지 않는다.

예약 Task `MobileESS_V42_May_B2_B3_Autonomous_Supervisor`는 Disabled다. 이전 DirectLPV18/SeedV17 Coordinator는 Ready지만 Trigger/NextRunTime이 없다. 모든 기존 Coordinator/Watchdog를 새 캠페인 실행에 재활용하지 않고 새 Source Epoch/Lock/Attempt를 발행한다. 기존 Monitor만 실행 중인 Task가 있다.

기존 launch interface는 `python -B -X utf8 -m v42_autonomous.supervisor <campaign_root>`이며, 요청 발행과 소스 검증 후 `v42_autonomous_b2.worker <request>` 또는 `v42_autonomous_b3.worker <request>`를 호출한다. Recovery CLI는 `v42_autonomous.recovery begin/end/guard/status/enqueue --root ...`이다. 기존 fresh.prepare는 목적지가 비어 있어야 하고 B1 31개 SHA 및 불변 Source를 검증하지만 5,400초와 기존 Gap 계약을 쓰므로 이번 새 계약의 실행 경로로 그대로 쓰지 않는다.

새 보고 코드는 `v42_common_reporting.summarize(campaign_root, manifest_path=None, output_root=None)`이다. 62개의 B2/B3 날짜 상태를 항상 출력하며 공란/UNKNOWN을 0으로 바꾸지 않는다. 원본 Actual phase current와 동일 B1 선로 집합 및 NormAmps authority를 사용하고, 원본 SHA가 불일치한 데이터는 수치 비교에 넣지 않는다. Snapshot 생성은 원본 결과/입력/Ledger를 변경하지 않는다.
