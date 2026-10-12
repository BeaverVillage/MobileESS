IEEE123 B2 May01에서 원본 DAG의 실제 MOVE 경로를 고정하고 전체 384 Charge Mode 및 Pch/Pdis/Q/SOC를 재최적화하는 독립 Canary Adapter를 추가합니다. PR217 정확한 HEAD 114f44330fbd995221c55385c6fde5b5b9e40d95 위에 새 연구 파일만 추가했고, 원본 Scientific Source와 기존 인증/운전계획은 변경하지 않았습니다.

실제 Native Optimize 누적 1795.0209996700287초: 이동 후보 54개 중 53개가 Restricted OPTIMAL 및 Original FULL Replay PASS, 1개가 TIME_LIMIT_NO_FEASIBLE입니다. 최선 이동 계획은 MESS02 STA12→IDC03의 MOVE 1회(2.1267545920520616 kWh)이며 UB 0.5461621302242249로 N1과 동등합니다. Global UB는 기존 N1을 유지하고, 추가 Grid Row16개 강화 K48 MILP에서는 LB 개선이 없었습니다. 최종 인증 LB 0.46498486997548166, Global Gap 14.863216571865975%; 3% 인증과 UB/LB Material Gain은 달성하지 못했습니다.

검증: Native Readback, Route/Node/Flow/Alias 207928좌표 검사, 원본 FULL 재검증, 58 Optimize Runtime 영수증 대조, 메모리/수치/Source/Case 감사 및 최종 독립 검증 PASS. Raw는 수정하지 않았으며 실패·중단·복구 Epoch도 보존했습니다. Actual/B1/B3/IEEE8500/다른 날짜/May 전체 캠페인은 실행하지 않았습니다. 범주는 Bound-Guided Anytime MILP / Certified Matheuristic입니다.

보고서: docs/v42_b2_k32_routefixed1800_canary/K32_ROUTE_FIXED_1800_CANARY_FINAL_KO.md

두 최선 계획의 96슬롯 CSV, UB/LB/Gap 그래프, 모든 Native Raw/로그/인증서 및 정확한 staged-byte 증거 인덱스를 포함합니다.
