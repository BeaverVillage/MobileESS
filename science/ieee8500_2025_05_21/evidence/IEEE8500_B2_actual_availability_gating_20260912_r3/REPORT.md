# IEEE8500 B2 Actual — causal availability gating

**PASS** — B2 Actual만 새로 실행했습니다.

DA P/Q clock을 고정하고 unavailable/wrong-PCC command는 버렸습니다. 차량 출발은 실제 도착 이후 가능한 최초 slot 기준으로 판단하고, P/Q 연결에는 별도의 connection-ready 조건을 적용했습니다. QSAFE robust V2는 실제 연결 PCC에서만 작동하며 early arrival을 허용합니다. Executed P는 변경하지 않았습니다.

IEEE123 regression: 124 policy-days / 95 moves, baseline 기록 차이 0, departure shift 0, QSAFE availability mask 차이 0, 기존 final Q 배제 0 — PASS.

기존 collision: MESS04 STA08 → IDC05, planned next departure=41, previous actual ready=42. 기존 FAIL-CLOSE evidence는 보존했습니다.

| 항목 | 결과 |
|---|---:|
| 이동 수 | 23 |
| departure shift 수 / 최대 slot | 0 / 0 |
| 실제 unavailable 차량-slot | 57 |
| nonzero missed P/Q 차량-slot | 0 |
| missed P / missed Q 차량-slot | 0 / 0 |
| availability curtailed active energy (absolute kWh) | 0.000000000 |
| availability curtailed reactive energy (absolute kvarh) | 0.000000000 |
| QSAFE intervention slots | 1 |
| QSAFE unresolved slots | 0 |
| Vmin / Vmax pu | 0.960094590586 / 1.049680441646 |
| max phase-line loading pu | 0.907606550954 |
| max transformer phase-current pu | 0.834664197052 |
| max transformer winding kVA pu | 0.845128382669 |
| convergence / controls settled | 96/96 / 96/96 |
| independent clean AC replay | PASS |

| MESS | final energy kWh | final SoC |
|---|---:|---:|
| MESS01 | 759.766571628 | 63.313880969% |
| MESS02 | 760.339984618 | 63.361665385% |
| MESS03 | 762.864904213 | 63.572075351% |
| MESS04 | 765.566624039 | 63.797218670% |

## MESS04 기존 네 shift 비교

| 다음 이동 | 계획 출발 | 이전 r2 실제 도착 | 이전 r2 ready | 이전 r2 출발 | 수정 후 이전 도착 | 수정 후 이전 ready | 수정 후 출발 |
|---|---:|---:|---:|---:|---:|---:|---:|
| IDC05 → IDC12 | 41 | 40.505915301 | 42 | 42 | 40.505915301 | 42 | 41 |
| IDC12 → STA03 | 43 | 42.991243353 | 44 | 44 | 42.036034190 | 43 | 43 |
| STA03 → STA05 | 45 | 44.437590883 | 46 | 46 | 43.419323256 | 45 | 45 |
| STA05 → STA06 | 47 | 46.766983423 | 48 | 48 | 45.756931446 | 47 | 47 |

전체 연속 이동 쌍 19개 중 실제 도착 지연 때문에 출발을 늦춰야 하는 이동은 0개입니다. 기존 불필요한 connection-ready 기반 shift 4개를 제거했습니다. 이동 출발은 도착 완료 이후 가능하며, 해당 방문에서 출발하면 미완료 connection delay는 전력 공급 권한을 만들지 않습니다.


Battery bounds/conservation audit PASS. Terminal SoC를 맞추기 위한 보상 또는 재최적화는 없습니다. Missed energy는 availability로 버린 원래 DA command의 절대값 적분이며 QSAFE correction과 구분합니다. 순방향/역방향 에너지와 actuator 전체 차이는 B2/MOBILITY_SUMMARY.json에 있습니다.

Move별 계획/실제 departure·arrival·ready는 B2_MOVE_TIMELINE.csv, missed commands는 B2_MISSED_COMMANDS.csv에 있습니다. 기존 frozen 입력 SHA 및 수정시각 전후 동일. rerouting/route search/destination/vehicle/order 변경, DA/MESS optimization, command time shift, catch-up은 모두 0입니다.
