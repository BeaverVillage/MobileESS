# V44 May01~07 실행 직전 준비

최종 상태는 **V44_PRESTART_BLOCKED**다. V44의 Gurobi 최적화·실제 Actual·Fresh 실행은 각각 0회다. Golden003 재최적화도 0회이며 Known 허용창 연구 정책은 **IMPLEMENTED_NOT_EXECUTED** 상태를 유지한다. 414개 실제 START 또는 Known Service Equivalence PASS를 주장하지 않는다.

1. **브랜치·기준:** `codex/v44-may01-07-prestart`, Worktree `D:/v44_may01_07_prepare_20261016`. V43 기준 Commit은 `5fed802db447a1f4b4e7fd556e4f5009b6bcee0d`다. 기준의 B2 복구·캐시·시간 종료 후 FULL 해 인계 수정까지 포함한다. V44 Commit과 Draft PR은 Git 기록 및 이 작업의 최종 보고를 따른다.
2. **변경 범위:** `v44/`, `docs/v44/`, `tests/test_v44*.py`, 해당 파일의 SHA 보존을 위한 `.gitattributes` 규칙이다. 날짜별 IO, Stage/Arm 연결, 900+300초 예산, Scheduler, 모니터, 증거 파일을 추가했다. 원본 V43/V42 수식·목적함수·계통·허용창·Raw를 V44 변경으로 수정하지 않았다.
3. **동결 증거:** `SCIENTIFIC_FREEZE_MANIFEST.json`은 상속 Source의 byte/AST 동일성, 원본 PR189 FULL 검사와 외부 K48/Beam/Joint Source SHA, 16개 지원 입력 SHA, V44 Adapter SHA를 기록한다. M2의 Stage/A2 부모 라벨 연결과 A2의 고정 M1 P/Q 연결만 선택적으로 교체하며 변수·제약·목적함수 생성 호출은 유지한다. 새 일별 대규모 FULL 모델의 행렬·물리 계약은 실행하지 않았으므로 미인증이다.
4. **입력 준비:** May01만 `INPUT_READY`다. May02~07의 초기 Running 사이트 미해결 수는 각각 1/164, 116/297, 7/271, 40/355, 30/360, 19/403이다. 이 6일의 MESS 위치/SOC에도 날짜별 원본 근거가 없다. May01 값을 복사해 준비 완료로 만들지 않는다. 날짜별 Native/WINDOWS/AEMO/PV/기상/교통/전기계수/Runtime/공개 요청 Descriptor는 SHA와 UID·날짜 축으로 검사한다. May01의 초기 상태는 기존 연구 가정을 보존하며 관측 Source 인증으로 승격하지 않는다.
5. **Worker:** Main 1개는 날짜순 B0→B1→B3, B2는 서로 다른 날짜의 2 Worker다. B2가 active/ready이면 Main을 대기시키며 3개 Heavy 동시 실행은 인증하지 않는다. 외부 V42/V43 공유 OS Lock 6개는 Coordinator가 보유하고, 자식은 레인 슬롯·날짜/Arm Lock과 PID 생성시각을 검사한다. 두 실제 Mock 자식 프로세스로 동시성·중복 차단·비정상 종료 후 Lock 해제를 확인했다.
6. **Native 예산:** B2 M1, B3 M1, B3 M2마다 K48 독립 300초와 Joint 독립 900초다. Joint 개별 호출 상한 140초, Threads=1, A1/A2 5400초·Gap≤0.5%를 유지한다. 기존 measured Runtime 원장으로 차감하며 Solver의 실제 초과시간은 기록하고 소진 원장에 추가 호출하지 않는다.
7. **인계·Resume:** 건강한 Original FULL 가능해는 Gap 미인증을 보존하며 M timeout 후 다음 단계로 인계한다. FULL 해 없음·구현 오류·다른 날짜/Arm/Source·변조된 계획은 차단한다. A2는 독립 FULL/0.5% 수락 조건을 유지한다. 정산된 동일 Case Native 원장의 Resume Fixture는 시간 초기화·중복 충전을 막는다. 운영 중 비정상 종료한 Binary Stage는 자동 재계산하지 않고 `RECONCILED_STAGE_CHECKPOINT_REQUIRED_NO_NATIVE_CLOCK_RESET`으로 격리한다. 해당 Stage의 실제 Checkpoint 복원 통합은 아직 미인증이다.
8. **성능:** V43의 sparse batch, 현재 Case 불변 행렬·전기 계수·교통·PCS 캐시, Native0 K16 재사용, 인증 Current AC와 독립 순차 Fresh 경로를 보존한다. Build/Native/Actual/Current AC/Fresh 시간을 분리한다. 새로운 알고리즘·후보 수 정책·MESS 강제 이동은 추가하지 않는다.
9. **경량 검증:** `LIGHTWEIGHT_TEST_RECEIPT.json`과 XML에 결과를 기록한다. V44 56개, 상속 V43 회귀 87개로 총 143개 PASS다. 7일 28 Case 연결은 Mock이며 실제 캠페인이 아니다. 대규모 모델 생성·Gurobi.optimize·Actual·AC 재생을 호출하지 않았다.
10. **기존 B2 보호:** `V43_B2_PROTECTION_START.json`과 `V43_B2_PROTECTION_END.json`에 당시 PID/생성시각·Lock·Native 상태와 Source 1,328건 무변경을 기록했다. B2는 자연 종료했고 기존 1800+300초 예산을 유지했다. 후속 사용자 지시에 따른 별도 V43 FCFS/Fresh 인계는 완료됐다. Actual PASS, Fresh 전압 FAIL 30슬롯, Gap 38.079629% 미인증이다. V44 실행 결과로 전용하지 않는다.
11. **남은 Blocker:** 6일의 초기 Running 및 MESS 관측 근거, 새 일별 FULL 행렬·물리 Driver 인증, Binary Stage Checkpoint 복원 통합, 새 B1/B3 Case에 정확히 결합된 기존 C1 affine/AC 보정 증거가 필요하다. 원래 C1 보정 증거가 없을 때 이전 affine 차단 정책으로 조용히 되돌아가지 않도록 Actual 연결을 차단한다. May01의 보정 증거를 다른 Case의 Source 권한으로 재사용하지 않는다. 이는 새로운 제어 알고리즘을 추가하는 것이 아니다.
12. **최종 상태:** `V44_PRESTART_BLOCKED`. `PREEXECUTION_CERTIFICATION.json`의 Source/날짜/예산·OS Lock Fixture PASS와 실 모델·물리 미인증을 구분한다. 입력이나 인증이 부족하면 READY를 선언하지 않는다. Forecast causal availability와 실제 Source 권한은 미인증 상태를 유지한다.

## 모니터 및 명령

기존 V43 모니터는 http://127.0.0.1:8795/ 이다. 같은 화면에서 B2 실행 완료 100%와 Fresh 물리 FAIL을 구분한다. 원래 RegControl 7대는 120슬롯 모두 enabled·deadband 충족·미포화였고 제어 큐가 비었으며, 최대 5회 반복으로 정상 종료됐다. 이 판정은 PR189의 snapshot/static 제어 기준이다. MESS PCC 전압 위반을 해결했다고 주장하지 않으며 제어 설정과 MESS P/Q/경로를 바꾸지 않았다. 자세한 증거는 기준 V43의 `docs/v43/B2_COMPLETION_AND_REGCONTROL_AUDIT.md`와 이 폴더의 감사 JSON에 있다.

V44 `MONITOR.html`은 준비 현황 문서다. 빈 숫자는 미실행이며 0 또는 PASS가 아니다. 날짜/Arm/Stage, PID, 별도 K48·Joint 원장, FULL/GAP/timeout, 시간, 오류·Resume을 실제 Worker 저장 경로에서 읽도록 준비했다. V44 모니터 서버와 캠페인 Worker는 시작하지 않았다.

기본 명령은 실행하지 않는 준비 전용이다.

```powershell
Set-Location D:\v44_may01_07_prepare_20261016
python -m v44.prepare --tests docs/v44/LIGHTWEIGHT_TEST_RECEIPT.json
python -m v44.campaign
```

아래 실행/Resume 명령은 **준비만 했으며 호출하지 않았다**. 별도 명시적 사용자 실행 승인, 전체 READY 인증, 현재 Source SHA·정확한 7일 날짜·인증 digest가 결합된 Permit이 있어야 한다. 현재 BLOCKED 상태에서는 실행할 수 없다. Permit은 생성하지 않았다.

```powershell
python -m v44.campaign --execute --permit D:/MobileESS_V44/APPROVED_EXECUTION_PERMIT.json --root D:/MobileESS_V44/runtime/campaign001
python -m v44.campaign --execute --permit D:/MobileESS_V44/APPROVED_EXECUTION_PERMIT.json --root D:/MobileESS_V44/runtime/campaign001 --resume
```

검증 단계는 캠페인 내부에 추가하지 않았다. Stage별 기존 FULL/Source/정산 검사는 유지한다. 기존 결과 덮어쓰기, 다른 날짜 결과 혼용, Native 원장 초기화, May08~31 실행 및 Main Merge는 수행하지 않았다.
