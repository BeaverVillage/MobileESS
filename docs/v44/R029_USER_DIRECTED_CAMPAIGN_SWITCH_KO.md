# r029 사용자 지시 캠페인 재개 (2026-10-18)

사용자 지시: 진행 중인 May07 B1을 즉시 중단하고, 개선한 r 버전으로 May02 B3 A2를 처음부터 실행한다. May07 B1의 순서가 돌아오면 체크포인트를 재사용한다.

- May07 B1 attempt001 worker 61092를 명시적 사용자 요청으로 중단했다. 기존 A1 결과, Native ledger, Raw, Actual 진행 기록은 보존했다. 기존 coordinator가 기록한 `WORKER_EXIT_WITHOUT_RESULT`도 수정하지 않고 `USER_INTERRUPTION.json`으로 사용자 중단 사실을 별도 기록했다.
- May07의 완료 A1 체크포인트를 실제로 재검증했다. FULL feasible, 독립 LB, 정확한 유리수 UB/LB Gap, AIDC 원본 및 source bytes 검증이 모두 통과했다. Gap은 약 2.7568e-10이며 새 Planning 최적화 호출은 없다.
- Actual 진행 기록 78/120은 실행 가능한 중간 상태 체크포인트가 아니다. 원래 driver는 제어 queue와 simulator 상태를 중간에 저장하지 않는다. 따라서 May07은 A1을 재사용하고 새 Actual/Fresh context에서 시작한다. Actual 78번 틱에서 이어진다고 표시하지 않는다.
- r029 알고리즘과 execution permit은 그대로 유지한다. 별도 `v44_recovery_r029_switch`는 명시적 사용자 중단의 재개 허용, May07 A1 재사용 경로, 자식 프로세스 실행 경로만 연결한다. 다른 실패의 재시도 정책과 과학적 검증은 그대로 적용한다.
- May02 B3 attempt013은 기존 완료 M1을 재검증하여 재사용하며, 이전 A2 support, point, Native 시간을 가져오지 않는다. A2는 Native 0부터 시작한다. 조건부 전압 완화 ±0.005 pu, Phase I 1500초, 전체 A 5400초 정책을 유지한다.
- Windows task `MobileESS_V44_Campaign004_Recovery_R029_UserSwitch`가 supervisor를 실행한다. 원래 r029 대기 task는 비활성화했다. 단일 coordinator lease와 worker lock을 그대로 사용한다.

검증: 사용자 재개 경로 및 기존 r029 수정·병목 회귀 테스트 41개 통과. 실제 May07 A1 재검증 통과. 운영 증거는 campaign004/AUTONOMOUS_RECOVERY/R029_USER_SWITCH_20261018_100310에 보존했다.

운영 엔트리:

```
python -m v44_recovery_r029_switch.operations --watchdog --algorithm v44_recovery_r029.operations
```

May07 A1 이외의 중단/실패는 이 예외로 자동 재시도하지 않는다. May07 새 attempt가 실패하면 기존 실패 격리 정책을 따른다.
