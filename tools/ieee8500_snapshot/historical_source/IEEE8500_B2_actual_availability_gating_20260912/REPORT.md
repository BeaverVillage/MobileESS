# REALIZED_MOBILITY_CAUSAL_AVAILABILITY_GATING — gate result

**FAIL-CLOSE: IEEE123 final QSAFE behavioral-equivalence gate 실패. IEEE8500 B2 replay는 시작하지 않았습니다.**

요청한 PCC gating을 최종 Actual Q에도 적용하는 엄격한 해석으로 rule/code/input SHA를 먼저 동결했습니다. 실제 연결되었어도 frozen service_id=None인 계획상 이동/connection-delay slot에서는 QSAFE가 이 zero gate를 덮어쓰지 못하도록 했습니다. 이는 명시한 해석이며, 기존 QSAFE 예외를 임의로 새로 허용하지 않았습니다.

| 검증 항목 | 결과 |
|---|---:|
| policy-days / moves | 124 / 95 |
| baseline command/P/Q/energy/SoC 기록 차이 | 0 |
| actual departure shift (IEEE123) | 0 |
| QSAFE availability mask 변경 vehicle-slot | 5 |
| 기존 final Q와 충돌하는 vehicle-slot | 1 |

## 반례

2025-05-11 / B3 / MESS01 / slot 43 (운영일 10:45). STA01 → STA03 이동의 계획 출발은 slot 41, 계획 ready는 slot 44지만 actual arrival=42.13833158836331, actual ready=43입니다. 따라서 이 slot은 frozen PCC=None / 실제 연결 PCC=STA03입니다. Frozen P=Q=0이지만 기존 QSAFE final Q=-20.39341192385541 kvar입니다. 새 strict gating의 Q=0과 20.39341192385541 kvar (15분 절대 에너지 차이 5.098352980963853 kvarh) 다릅니다.

이 반례는 late-arrival collision이 아니라 early-arrival QSAFE입니다. 이전 collision audit의 0건 결론과 모순되지 않습니다. 순수 mobility/command baseline은 124건 모두 동일하지만, 최종 QSAFE 동작까지 포함한 zero-change gate는 통과하지 못했습니다. 이미 저장된 final injection이 새 eligibility를 위반하므로 이를 증명하기 위해 QSAFE/AC를 재실행할 필요가 없습니다.

## IEEE8500 B2 상태

기존 MESS04 STA08 → IDC05의 actual ready 42가 다음 계획 출발 41보다 늦은 collision evidence를 참조로 보존했습니다. B2 clean mobility/전기 replay는 gate 이전이라 수행하지 않았습니다. 따라서 departure shifts, missed P/Q, energy, SoC, QSAFE intervention, Vmin/Vmax, thermal maxima 및 independent replay 결과는 모두 NOT_RUN이며 0/PASS로 보고하지 않습니다.

동결한 이동식은 `max(planned departure_k, previous move actual ready)`이며 P/Q clock은 이동하지 않습니다. 이번 실행에서는 source text/JSON 조회 및 메모리상의 IEEE123 mobility regression만 수행했습니다. SUMO/AC/DA/MESS optimization 및 기존 결과 생성은 수행하지 않았습니다.

읽은 입력 1226개 SHA256 및 수정시각 전후 동일. 모든 생성 파일은 이 새 폴더에만 있습니다.

진행하려면 계획상 PCC가 없는 early-arrival slot에서도 기존 QSAFE의 실제 연결 PCC 제어를 예외로 유지할지 명확한 rule이 필요합니다. 현재 gate를 임의로 완화하거나 PASS로 바꾸지 않았습니다.
