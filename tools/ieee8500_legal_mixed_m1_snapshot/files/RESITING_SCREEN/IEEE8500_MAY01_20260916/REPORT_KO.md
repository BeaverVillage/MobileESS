# IEEE8500 RESITING_SCREEN — May-1

선정 후보: **legal_mixed_M1**, s_DC=s_MESS=1.00. Screening 한정, Full 96-slot / Fresh pipeline / Actual 미실행. 최종 infrastructure freeze는 아직 하지 않았다.

## 범위와 판정
Native bus inventory에서 service/phase/연결성을 검사했고, 111개 진단 접속점의 10-slot P/Q finite differences 중 source/capacitor internal 진단점 3개를 제외한 108개를 후보로 사용했다. 3개 AIDC 배치 × 3개 MESS 배치의 B0 gate를 검사했다. 최종 비교는 고부하 68–85번 18 slots와 낮 시간 충전 34–53번 20 slots, 합계 38 slots exact AC이다. 시간 인덱스는 기존 자료와 동일한 0-based이다.
기존 ρ≥0.931437 local obstruction은 직접 downstream 단상 접속으로 제거됐다. 현재 scale에서 exact-AC feasible B3 witness는 **0.884728081**이다. 실제 최적값을 증명한 수치는 아니다. 해당 6-station infrastructure에 대한 별도 native-leaf 필요 하한은 **0.848071657**이며, 현재 알려진 critical-slot 최적값 범위는 [0.848071657, 0.884728081]이다. 이 결과는 full-day production 보증이 아니다.

## 동일 infrastructure / 동일 physical authority의 proxy
| Policy | rho | Vmin | Vmax | transformer I pu | transformer kVA pu | AC |
|---|---:|---:|---:|---:|---:|---|
| B0 | 0.983591141 | 0.9510075 | 1.0417381 | 0.2831766 | 0.2876701 | PASS |
| B1 | 0.980908418 | 0.9525559 | 1.0417748 | 0.2824675 | 0.2871721 | PASS |
| B2 | 0.887179311 | 0.9546758 | 1.0417197 | 0.3696520 | 0.3778425 | PASS |
| B3 | 0.884728081 | 0.9561357 | 1.0416245 | 0.3710017 | 0.3778425 | PASS |

Strict ordering (tie tolerance 1e-6): **True**. B0−B3=0.098863060; 최소 adjacent separation=0.002451230. 순서 제약은 추가하지 않았다.

원래 job/WAN/resource/PWL 제약과 P1–P5 hierarchy를 가진 24-cohort 제한 MILP를 실행했다. MILP의 일부 electrical 근사는 exact AC에서 실패하여 탈락시켰다. 최종 표는 원래 audit를 통과한 3개 workload schedule과 exact AC 보정한 2개 MESS schedule의 동일 후보 집합을 각 배치에 적용하여 얻은 실행 가능한 최선의 proxy이다. 전체 job/route domain의 전역 최적화 결과가 아니다. B3는 B0 workload를 유지하는 선택도 허용한다. 모든 선택은 exact rho를 우선 비교했으며 ordering을 강제하지 않았다.

## AIDC 12개 — 모두 3상 .1.2.3, 12.47/0.48 kV, 1500 kVA
| AIDC | native host bus |
|---|---|
| AIDC01 | m1026834 |
| AIDC02 | e184626 |
| AIDC03 | l3234149 |
| AIDC04 | m4113347 |
| AIDC05 | m1047763 |
| AIDC06 | m1026780 |
| AIDC07 | n1142100 |
| AIDC08 | l3122821 |
| AIDC09 | m1047566 |
| AIDC10 | l2814529 |
| AIDC11 | l2992624 |
| AIDC12 | e182733 |

## MESS 6개 — 기존 P=300 kW, S=400 kVA, E=1200 kWh 유지
| MESS | station | host connection | phase | max P kW | max abs Q kvar | max S kVA |
|---|---|---|---:|---:|---:|---:|
| MESS01 | STA01 | sx3101194c.1 | 1 | 6.7249 | 3.6025 | 7.6288 |
| MESS02 | STA12 | sx2767340c.2 | 1 | 6.1051 | 3.7037 | 7.1399 |
| MESS03 | STA08 | sx3027670b.1 | 1 | 5.7617 | 5.5000 | 7.9654 |
| MESS04 | STA06 | sx3141411c.1 | 1 | 5.5000 | 5.2417 | 7.5977 |
| MESS05 | STA03 | m1009763.1.2.3 | 3 | 261.1614 | 110.0000 | 283.3819 |
| MESS06 | STA10 | n1144668.1.2.3 | 3 | 110.0000 | 110.0000 | 155.5635 |

사용자 승인에 따라 네 저압 단상 PCC의 전압/상 인터페이스를 해당 native bus에 맞췄다. Native 선로/변압기 임피던스와 정격은 바꾸지 않았다. Additive PCC transformer는 기존 750 kVA, XHL=5.75%, %Rs=[0.8,0.2]를 유지한다. 여섯 station은 중복 없이 서로 다른 native bus이다. 모든 MESS는 재배치한 각 initial station ID에 계속 연결되므로 이동/소비 에너지는 0이다. 이것은 합법적인 stationary route witness이며 전체 route-search optimum은 아니다.

선택 B3의 migration: 21 jobs, 84 GPUs, WAN payload 6,720,000,000,000 bytes. 전체 96-slot workload/WAN/resource 및 per-GPU 전력 재구성 audit는 PASS. SOC 440–1080 kWh, initial=terminal=760 kWh, ηc=ηd=.95를 모두 검사했다.

## 남은 제약 및 한계
현재 objective bottleneck: `Line.tpx21459660c0|t2|sx3101194c.1.2|node1`, slot 77. 미접속 말단 `sx3645811c`의 native current/voltage ceiling은 별도 필요 하한 0.848071657을 만든다. 채택 해의 모든 hard physical constraints는 여유를 갖고 통과했으므로, 이 해만으로 전역 optimum의 binding constraint를 특정하지 않는다. Native regulator/capacitor의 이산 동작 때문에 근사 목적값과 exact rho의 차이가 있으며, 더 공격적인 근사 해는 채택하지 않았다.

실행 경과(코드 준비/수치 검증 포함): 약 39.6분. 최종 공통 제어 후보 비교: 142.2초. 원본 authority hash 48개 및 native physical element audit PASS. 결과 파일은 RESITING_SCREEN 내부에만 작성했다.

## 핵심 파일
- FINAL_PROXY_RESULTS.csv/json: 상위 3개 배치 비교
- SELECTED_AIDC.csv / SELECTED_MESS.csv: 최종 screening 후보 bus·phase·출력
- SENSITIVITY_MAP.csv / SELECTED_SENSITIVITY.json: exact finite-difference 근거
- SELECTION_EVIDENCE.json: 기존 하한 제거, 새 필요 하한, exact witness
- SELECTED_MIGRATION.json: 실제 workload migration
- INDEPENDENT_WORKLOAD_AUDIT.json / NATIVE_PHYSICAL_AUTHORITY_AUDIT.json / SOURCE_CONSERVATION.json
- PROXY_METHOD.json: 범위·제약·검색 제한
- RESTRICTED_REPLAY_VERIFICATION.json: 선정 4정책 38-slot 재현 검증