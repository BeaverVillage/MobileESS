# V44 May01~07 실행 직전 준비

현재 상태는 **V44_PRESTART_BLOCKED**다. 초기 상태 문제는 해결했으며, 남은 새 계통 FULL 모델·물리 Driver·Case별 C1 보정 인증을 구분한다. V44 Gurobi 최적화 및 Actual96/Fresh96 본 실행은 0회다. Known 연구 정책은 **IMPLEMENTED_NOT_EXECUTED**이며 414개 START 또는 Service Equivalence PASS를 주장하지 않는다.

1. **브랜치·기준:** `codex/v44-may01-07-prestart`, Worktree `D:/v44_may01_07_prepare_20261016`. V43 기준 Commit은 `5fed802db447a1f4b4e7fd556e4f5009b6bcee0d`다. 기준의 B2 복구·캐시·시간 종료 후 FULL 해 인계 수정까지 포함한다. V44 Commit과 Draft PR은 Git 기록 및 이 작업의 최종 보고를 따른다.
2. **변경 범위:** `v44/`, `docs/v44/`, `tests/test_v44*.py`, 해당 파일의 SHA 보존을 위한 `.gitattributes` 규칙이다. 원본 V43/V42 파일·Raw는 보존하고 사용자 승인에 따른 Epoch12 SVR11 계통·전압 모델을 V44 전용 경로에 이식했다. 날짜별 IO, Stage/Arm 연결, 900+300초 예산, Scheduler, 같은 모니터의 부분 수정 및 증거를 추가했다.
3. **동결 증거:** `SCIENTIFIC_FREEZE_MANIFEST.json`은 상속 Source의 byte/AST 동일성, 원본 PR189 FULL 검사와 외부 K48/Beam/Joint Source SHA, 16개 지원 입력 SHA, V44 Adapter SHA를 기록한다. M2의 Stage/A2 부모 라벨 연결과 A2의 고정 M1 P/Q 연결만 선택적으로 교체하며 변수·제약·목적함수 생성 호출은 유지한다. 새 일별 대규모 FULL 모델의 행렬·물리 계약은 실행하지 않았으므로 미인증이다.
4. **입력 준비:** 7일 모두 `MODEL_ASSUMED_VERIFIED`다. May02~07 미지정 Running 213 UID는 기존 V43 issue-only 결정적 초기화로 배치하고 GPU·Rack·호환성과 원래 확정 사이트를 검증했다. PR189 Producer의 공통 Template 연구 가정을 근거로 날짜별 독립 초기 MESS 위치 STA01/STA12/STA08/STA06, 차량별 760 kWh, PCS 400 kVA·P 300 kW를 유지한다. 실제 관측이나 이전 날짜 최적해로 주장하지 않는다. 상세 근거는 `V44_PR189_31DAY_REUSE_AUDIT.json`, `V44_MAY02_07_INITIAL_RUNNING_AUDIT.json`, `V44_MESS_DAILY_INITIAL_STATE_CONTRACT.json`에 기록했다.
5. **Worker:** Main 1개는 날짜순 B0→B1→B3, B2는 서로 다른 날짜의 2 Worker다. B2가 active/ready이면 Main을 대기시키며 3개 Heavy 동시 실행은 인증하지 않는다. 외부 V42/V43 공유 OS Lock 6개는 Coordinator가 보유하고, 자식은 레인 슬롯·날짜/Arm Lock과 PID 생성시각을 검사한다. 두 실제 Mock 자식 프로세스로 동시성·중복 차단·비정상 종료 후 Lock 해제를 확인했다.
6. **Native 예산:** B2 M1, B3 M1, B3 M2마다 K48 독립 300초와 Joint 독립 900초다. Joint 개별 호출 상한 140초, Threads=1, A1/A2 5400초·Gap≤0.5%를 유지한다. 기존 measured Runtime 원장으로 차감하며 Solver의 실제 초과시간은 기록하고 소진 원장에 추가 호출하지 않는다.
7. **인계·Resume:** 완료 Stage는 Source/Case/Hardware/Day/Arm/Attempt 영수증을 검증해 재사용한다. M-stage Binary 행렬·정적 Presolve 역변환 및 K16/K32/K48 Packet 복원, 독립 300/900초 측정 예산 복원을 구현했다. 실제 96슬롯 소규모 Flow 행렬의 원래 Transport 검사까지 통과했다. Gurobi B&B 탐색 상태와 중단된 Actual Tap/Queue 복원은 `NOT_SUPPORTED`다. 미정산 Inflight·중복 Worker·SHA 변조는 해당 Stage를 차단하며 원장을 초기화하지 않는다. FULL 가능해가 있는 정상 timeout은 Gap 미인증을 보존해 인계한다. Full 규모 복원은 아직 실행하지 않았다.
8. **성능:** V43의 sparse batch, 현재 Case 불변 행렬·전기 계수·교통·PCS 캐시, Native0 K16 재사용, 인증 Current AC와 독립 순차 Fresh 경로를 보존한다. Build/Native/Actual/Current AC/Fresh 시간을 분리한다. 새로운 알고리즘·후보 수 정책·MESS 강제 이동은 추가하지 않는다.
9. **경량 검증:** `LIGHTWEIGHT_TEST_RECEIPT.json`과 `svr11_revision01/FINAL_LIGHTWEIGHT_REGRESSION.xml`에 총 175 PASS를 기록했다. 28 Case 연결은 Mock이다. 7일 새 계수는 실제 입력 로더에서 Known/허용창 및 96슬롯·60제어축·153개 변압기 상별 바인딩을 Native0으로 확인했다. 대규모 모델 생성·Gurobi.optimize·Actual96/Fresh96를 호출하지 않았다.
10. **기존 B2 보호:** `V43_B2_PROTECTION_START.json`과 `V43_B2_PROTECTION_END.json`에 당시 PID/생성시각·Lock·Native 상태와 Source 1,328건 무변경을 기록했다. B2는 자연 종료했고 기존 1800+300초 예산을 유지했다. 후속 사용자 지시에 따른 별도 V43 FCFS/Fresh 인계는 완료됐다. Actual PASS, Fresh 전압 FAIL 30슬롯, Gap 38.079629% 미인증이다. V44 실행 결과로 전용하지 않는다.
11. **남은 Blocker:** 새 계통 FULL 행렬/Case 계약 및 새 B1/B3 Anchor에 결합된 C1 affine/AC 보정 증거다. 초기 Running/MESS 관측 부재는 더 이상 연구용 입력 Blocker가 아니다. 원래 C1 보정 증거가 없을 때 이전 affine 차단 정책으로 조용히 되돌아가지 않도록 연결을 차단하며, 다른 Case의 보정 증거를 재사용하지 않는다.
12. **최종 상태:** `V44_PRESTART_BLOCKED`. `PREEXECUTION_CERTIFICATION.json`의 Source/날짜/예산·OS Lock Fixture PASS와 실 모델·물리 미인증을 구분한다. 입력이나 인증이 부족하면 READY를 선언하지 않는다. Forecast causal availability와 실제 Source 권한은 미인증 상태를 유지한다.

## 모니터 및 명령

기존 [모니터 화면](http://127.0.0.1:8795/)에 7개 날짜별 완료 슬롯·PID·생존·RAM 및 재개 상태를 표시한다. 화면이나 URL을 새로 만들지 않았다. V43 과거 B2의 Actual PASS/Fresh 전압 30슬롯 FAIL은 과거 결과로 보존한다.

SVR11은 Epoch12 실행 Commit `637f3754ad443910b90be9d2898e14943e54b855`의 23개 원본 파일을 실행 Manifest SHA와 대조해 이식했다. 기존 7 + 추가 33 = RegControl 40개, SVR 11뱅크, Capacitor 4개 Fixed ON을 B0/B1/B2/B3에 동일 적용한다. BUS82는 최종 Line.l82 입력측 구성이다. 기존 7-Reg 계수·Golden003·과거 B2 해를 새 계통의 계획 인증으로 재사용하지 않는다.

May01~07 Forecast는 모두 96/96 완료했다. May02~07은 사용자 지시에 따른 6개 날짜별 독립 Worker로 생성했다. Windows 상태 파일 교체의 일시적인 접근 충돌은 재시도하고 UI telemetry 오류가 공유 잠금을 해제하지 않도록 수정했다. 완료 슬롯은 원래 SHA를 검증해 별도 출력 폴더에서 재개한다.

날짜별 24슬롯 Prefix + 첫 평가슬롯의 최소 실제 물리 검사 10건을 통과했다. 측정 전압 범위는 0.981178~1.046559 pu다. Current AC 캐시/독립 Fresh 동일성과 4대 MESS의 장치 P/Q 부호 및 사이트 연결도 소규모 진단에서 확인했다. Issue GPU를 고정한 명시적 진단 부하이며, 실제 Job 이벤트 캠페인 또는 Fresh96 대체 인증이 아니다. 전압·정격 위반은 그대로 기록하며 Tap·전압 범위·MESS P/Q를 튜닝하지 않는다.

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

최신 사용자 지시로 May01 B2 한 건의 실행을 승인받았다. 별도 v44.pilot 경로가 날짜/Arm/Stage/Source/예산을 한정한다. K48 300초와 Joint 900초, Threads=1이며 기존 Native0/FULL 검사를 통과한 정상 가능해는 Gap 미달이어도 Actual/Fresh로 인계한다. 다른 날짜, A1, B1/B3 또는 전체 캠페인을 자동 실행하지 않는다. 이 문서의 미실행 수치는 Pilot 시작 전 준비 기준이다. 실제 실행 상태는 D:/MobileESS_V44/runtime/ACTIVE_MAY01_B2_PILOT.json 및 그 RESULT 원장에서 확인한다.
