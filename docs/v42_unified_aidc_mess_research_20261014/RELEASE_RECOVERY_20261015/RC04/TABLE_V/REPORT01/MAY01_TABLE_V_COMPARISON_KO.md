# May01 Table V 비교

| Arm | Computing | MESS | 실행 결과 | Raw Fresh96 재검산 |
|---|---|---|---|---|
| B0 | Reference | OFF | FULL_PASS | PASS |
| B1 | Full E1/FLEX30/R1 | OFF | NOT_RUN | NOT_RUN |
| B2 | Reference | ON | NOT_RUN | NOT_RUN |
| B3 | Full E1/FLEX30/R1 | ON | NOT_RUN | NOT_RUN |

실제 Arm 결과와 raw settled Fresh96가 모두 PASS인 비교군은 1/4개입니다.
미실행·미기록 수치는 0으로 대체하지 않았습니다. Planning action은 Actual 실행 횟수로 전이하지 않았습니다.

A1/A2는 Arm·Stage마다 누적 Gurobi Native 5400초, M1/M2는 1800초이며 합산 총량 제한은 없습니다. K48은 별도 단계 원장입니다. Build·HiGHS·Actual·AC wall은 Native timeout에서 제외됩니다.
표의 Arm wall은 중첩 시간을 포함한 실제 전체 wall입니다. Native/Presolve/Root/Build와 다시 더하지 않습니다.
공식 물리 판정은 15분×96의 원래 settle_slot→measure_full_network입니다. Substep 진단은 별도로 보존하며 공식 판정을 대신하지 않습니다. 연속시간 안전 인증은 주장하지 않습니다.
과거 Basic A1의 0.64211779208034와 과거 MESS UB/LB는 현재 Full E1 케이스에 전이하지 않았습니다. R2는 HOLD입니다.

효과 비교는 최대 선로부하율과 실제 Compute GPUh를 함께 읽어야 합니다. 처리량 감소만으로 선로부하율이 낮아진 결과를 제어 개선으로 단정하지 않습니다.

- B0→B1 (MESS OFF AIDC flexibility): 최대 선로부하율 차이 NOT_CERTIFIED, 실제 Compute GPUh 차이 NOT_RECORDED.
- B0→B2 (Reference MESS): 최대 선로부하율 차이 NOT_CERTIFIED, 실제 Compute GPUh 차이 NOT_RECORDED.
- B1→B3 (Flexible MESS): 최대 선로부하율 차이 NOT_CERTIFIED, 실제 Compute GPUh 차이 NOT_RECORDED.
- B2→B3 (MESS ON AIDC flexibility): 최대 선로부하율 차이 NOT_CERTIFIED, 실제 Compute GPUh 차이 NOT_RECORDED.
