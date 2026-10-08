# V42 B1→B2 5월 P1 캠페인 Preflight 검토

2026-10-09 KST 최종 상태: **미기동 / Preflight 실패**. 실행 캠페인 Run ID는 생성하지 않았다. 식별자는 감사용 `b1_b2_p1_preflight_20261009`다. Native optimize 0회, 완료 arm/date 0개다.

Windows에서 로그오프 지속 실행을 위한 S4U 예약 작업 등록을 실제로 2회 시도했으나 `Register-ScheduledTask`, **HRESULT 0x80070005 / 액세스가 거부되었습니다**로 실패했다. 현재 토큰은 관리자 역할이 아니다. Coordinator·Monitor·Watchdog 신규 작업은 등록되지 않았으며, 첫 May01 B1 Worker도 생성되지 않았다. InteractiveToken으로 대체해 전체 PASS를 주장하지 않았다.

## 검증된 내용

- `v42` 로컬·원격 최신 과학적 기준 HEAD: `dc15114d450c25394ff174cc0c65056aae40778f`.
- 기존 공통 Native=0 회귀: **680 PASS / 12 SKIP / 0 FAIL**. SKIP은 PASS가 아니다.
- 기존 infrastructure 회귀: **12 PASS**. 이 검사는 기존 31일/3600초/infra 2회 재시도 정책에 대한 것으로, 요청된 새 62개 축/5400초/실패 무반복 정책 검증은 아니다.
- 과거 May31 입력 31일 전체와 연결된 283개 파일의 SHA·크기를 실측 검증했으며 누락·불일치 0개다. 새 B1/B2 독립 입력이나 새 case 인증으로 간주하지 않는다.
- 기존 소스 1,117개 및 D runtime ledger 5개의 SHA를 회귀 전후 비교해 변경 0개를 확인했다. 추가 A/M·orchestration 감사에도 원본 SHA를 기록했다.
- 기존 알고리즘·과학적 결과·Native ledger를 변경하지 않았다. 기존 Task Scheduler 작업, 옛 read-only monitor PID 41292와 port 8791을 유지했다.

## 아직 완료되지 않은 실행 연결

A-stage는 기존 complete pricing, 원본 정수형 복구, original physical checker, exact LB를 재사용할 수 있다. 다만 May12/3~4일 전용 경로, class count, scientific permit과 날짜당 예산을 최소 adapter로 연결해야 한다. 과거 four-objective runner 및 P2를 호출하면 요청 범위를 벗어난다. 기존 launch 차단은 보존했다.

M-stage의 기존 adaptive primal–dual/role-exchange LNS와 exact LB 구현도 보존했다. 상위 loader·warm start·columns·case SHA·변수 개수·projection rows는 May01에 고정되어 있어 직접 월간 B2에 사용할 수 없다. 원본 FULL→compact→hybrid 조립의 하부 API를 날짜별 원본 입력에 연결하고 P1만 전달하는 adapter와 동치성 검증이 필요하다. 과거 May01 UB/LB/정수해를 다른 날짜 인증으로 사용하지 않았다.

B2는 `v42_capacity.reference.build_reference`의 기존 FCFS/Q50 nominal-release V2 규칙을 자기 원본 입력에서 독립 호출할 경로를 찾았다. 실제 입력 생성은 0일이다. 감사 중 AIDC optimizer 호출 0회를 실제 B2 Worker의 무최적화 실행 증거로 주장하지 않는다.

## 정책과 산출물 상태

사전 정책 초안은 B1 31일 후 B2 31일, Threads=1, P2=0, 날짜당 Wall/Native 각각 5400초, 실패 날짜 무반복 후 다음 날짜 진행, B1 gap 0.5%·B2 gap 3%를 기록한다. 이를 강제하는 신규 wrapper는 구현·검증하지 않았다. `CAMPAIGN_PREREGISTRATION.json`의 62개 항목은 계획 축이며 실행 등록이나 관측 결과가 아니다.

`DATE_ARM_*.csv`와 `FAILURE_LEDGER.csv`에는 열 머리글만 있다. arm/date 실행·실패·시간·gap·Fresh AC 관측 결과가 없기 때문이다. 예약 작업 실패는 `PREFLIGHT_FAILURES.json`에 별도로 기록했다. Monitor URL·Coordinator/Worker PID·heartbeat·OS 부모 관계 증거·checkpoint 재개 명령은 없다. 모니터·Publisher·무인 AI·반복 감시도 시작하지 않았다.

모든 새 파일은 `D:\MobileESS_v42\docs\v42_may_b1_b2_p1_campaign_20261009\`에, 임시 파일과 전체 회귀 로그는 `D:\MobileESS_v42\runtime\v42_may_b1_b2_p1_campaign\scheduler_preflight_20261009\`에 저장했다. live runtime은 Git에 넣지 않는다.

## 다음 확인 명령

상태 확인:

```powershell
Get-Content -Raw 'D:\MobileESS_v42\docs\v42_may_b1_b2_p1_campaign_20261009\CAMPAIGN_STATUS.json'
```

권한을 갖춘 PowerShell에서 S4U **등록 가능성만** 다시 점검할 수 있다. 아래 명령은 solver·캠페인을 시작하거나 재개하지 않으며, 성공해도 나머지 Preflight를 대체하지 않는다.

```powershell
pwsh -NoProfile -File 'D:\MobileESS_v42\docs\v42_may_b1_b2_p1_campaign_20261009\Invoke-SchedulerPreflight.ps1'
```

캠페인 재개 명령은 없다. OS 등록 문제를 해소하고 날짜 adapter·독립 인증·새 wrapper·monitor를 구현한 뒤 전체 Native=0 Preflight를 통과해야 최초 실행이 가능하다. 시스템 절전·최대절전·종료 중 계산 지속을 주장하지 않았고 전원 정책을 변경하지 않았다.

기존 [PR189](https://github.com/BeaverVillage/MobileESS/pull/189)에 감사·차단 증거를 반영한다. 이 문서는 정상 독립 실행 인계 또는 성공한 캠페인 보고가 아니다.
