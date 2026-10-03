# V42 autonomous grid controls — source authority STOP

PR125 exact head `043298363fe51edde0bddaa073a553e526ffef2c`에서 시작해,
현재 implementation과 exact OpenDSS source를 audit했다. Planning과 Actual
compiler 모두 **regulator 7 / RegControl 7 / capacitor 4 / CapControl 0**이다.
Capacitor switching law·threshold·delay가 없어 사용자 요청 §25 STOP 조건에
해당한다. 새로운 control 설정을 추가하거나 regulator-only 결과를 대신
생성하지 않았다. 이번 산출물은 audit와 중단 evidence이며 구현 완료가 아니다.

| 요청 항목 | 확인 결과 |
|---|---|
| 1. Git 상태 | 새 branch `codex/v42-autonomous-grid-controls-april-b0`; audit만 추가. 최종 PR/commit은 제출 메시지에서 보고 |
| 2. tests | TEST_RECEIPT.json / PYTEST_FULL.log 참조. Audit regression은 scientific autonomous-control regression과 구분 |
| 3. equipment | regulator/RegControl 7, capacitor 4, CapControl 0 |
| 4. Planning semantics | forecast RegControl autonomous; capacitor fixed ON; 하루 내 sequential tap carryover; sensitivity 동안만 anchor state 고정 |
| 5. PR125 Actual | 매 slot Planning tap/cap 주입; RegControl disabled, controlmode off |
| 6. 수정 후 Actual | activation 없음; source-authority STOP |
| 7–8. tap/cap replay 제거 | 미구현. PR125 코드 byte-preserve; 제거 완료를 주장하지 않음 |
| 9. April 15/16/30 | old frozen violation cells 3/17/2; new diagnostic NOT_RUN; tap/cap changes 미측정 |
| 10. April 30-day convergence | new run NOT_RUN. Old PR125 2880 converged slots는 historical evidence로만 보존 |
| 11–12. physical violations | new run 미측정. Old frozen voltage 22 cells / 3 days, line / transformer current / transformer kVA 모두 0 |
| 13–15. residual, ±0.005, Q95/Q99 | new statistics/coverage/candidate bands 미생성. Old candidate를 current contract로 승격하지 않음 |
| 16. PR125 supersession | false; replacement execution 없음. Old voltage-calibration condition을 기록하고 최종 candidate로 수용하지 않음 |
| 17. workload/capacity | BASE 전체 3560 files exact-byte PASS; Runtime/CC4/queue/C1/PF/780 GPU/physical P/Q/V_PLAN/old results 변경 없음 |
| 18. May/common contract | all arms/months 동일 authority 요구와 동일 STOP을 문서화. Reusable production code 미활성/미구현; May NOT_RUN |
| 19. FINAL_MARGIN_ACCEPTED | false |
| 20. PROBLEM13_FINAL_VALIDATED | false |
| 21. blocker | exact banks에 적용할 source-backed CapControl 정의/settings 부재 |

재개에는 exact source CapControl 및 switching settings authority가 필요하다.
다른 가능한 방향은 사용자가 source의 fixed-ON capacitor를 허용하는 contract로
명시적으로 수정하는 것이다. 이 task에서 그 변경을 임의 채택하지 않았다.
Actual P/Q repair, optimizer, MESS, tuning 모두 0이며 May outcomes는 control
설정에 사용하지 않았다. B1/B2/B3/May/M1/A2/M2 scientific execution은 NOT_RUN.

BASE_BYTE_PRESERVATION.json은 exact base의 모든 raw Git blob bytes를 검증한다.
전체 pytest는 tests와 contract_tests를 함께 포함한다. 이전 legacy manifest가
Windows CRLF checkout SHA를 기록했으므로 8개 파일에 대해 테스트 동안만 그
exact historical SHA와 일치하는 EOL variant를 사용한다. Assertion/manifest는
변경하지 않고 finally에서 원래 bytes를 복원한다. 최초 EOL 실패 로그와
TEST_CHECKOUT_COMPATIBILITY.json을 보존하며, 최종 verification은 복원 후
BASE 전체를 다시 검증한다.
UNPRODUCED_SCIENTIFIC_ARTIFACTS.json은 STOP 때문에 생성하지 않은 출력들을
나열한다. 누락 scientific output을 빈 CSV나 0 violation 값으로 대체하지 않았다.
