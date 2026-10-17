# r022 개선의 이후 미실행 B1·B3 무조건 적용

최신 사용자 지시에 따라 May02 B3 A2의 PASS를 기다려 개선 적용 여부를 결정하던 조건을 제거했다. 이후 미실행 **B1 A1·B3 A2**는 현재 A2 결과가 없거나 RUNNING·FAILED·PASS인 것과 관계없이 같은 개선을 사용한다. 공통 B1 A2 어댑터도 지원한다.

기존 r022는 현재 worker가 사용하는 봉인 소스이므로 수정하지 않았다. **r022u는 r022 알고리즘을 그대로 사용하는 배정 리비전**이다. `phase_rebuild.stage_scope()`의 기존 `pilot_result.exists()`와 `read(...).get('PASS')` 분기를 제거하고 `row_generation=stable`로 바꿨다. 행 생성·Full Φ·원본 Primal/Dual·Inclusion·Pricing·예산·허용오차 계산은 동일하다.

현재 May02 B3 `attempt005`의 worker PID32296과 coordinator PID34976은 그대로 실행한다. A2를 재시작하거나 Native 원장을 초기화하지 않는다. 후속 배정은 현재 worker와 coordinator가 자연 종료하는 안전한 경계에서 전환한다. 이 경계는 Case의 COMPLETE·FAILED·BLOCKED_DEPENDENCY를 모두 허용하며 A2 PASS 조건이 아니다. 기존 Source/OS lock/사용자 중단 및 오류 처리 정책은 유지한다.

검증은 **234개 PASS**다. B1 A1·B3 A2·공통 B1 A2 각각에 대해 이전 A2 결과가 MISSING·RUNNING·FAILED·PASS인 경우에도 해당 결과 파일을 조회하지 않고 새 경로에 연결되는지 검증했다. 실패한 Case의 자연 종료도 전환 경계로 인정하고, worker가 살아 있으면 보호하는 것을 검증했다. 추가 Native 최적화는 0회다.

대상은 아직 시작하지 않은 May03~May07의 B1·B3 총 **10개 Case**다. 완료된 PASS, 같은 날 B1 A1 재사용, 현재 May02 B3의 M1 및 현재 실행은 보존한다. Windows `MobileESS_V44_Campaign004_Recovery_R022U`와 독립 handover waiter가 등록되어 Codex 턴 종료와 관계없이 다음 배정을 준비한다. 이전 R022 Windows task는 Disabled이며 현재 worker는 중단하지 않았다.

운영 근거는 다음 영수증에 있다.

- `AUTONOMOUS_RECOVERY/R022U_USER_AUTHORIZATION.json`
- `R022U_CHANGE_AND_VALIDATION.json` / `R022U_SEALED.json`
- `RECOVERY_R022U_EXECUTION_PERMIT.json`
- `R022U_HANDOVER_GUARD.json` / `R022U_HANDOVER_HEARTBEAT.json`
- `R022U_UNCONDITIONAL_ROLLOUT_READY.json`

이 문서와 최신 사용자 지시가 이전 May02 개선 보고서의 “A2 pilot PASS 후 적용” 설명보다 우선한다. PR: https://github.com/BeaverVillage/MobileESS/pull/233
