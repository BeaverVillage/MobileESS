# May-04 B1 flexibility diagnostic

**주원인: COMPUTATIONAL_LOCAL_BASIN.** 기존 F&O가 원래 B1 모델에서 가능한 개선을 놓쳤습니다.
원래 변수 경계를 복구하지 않은 결함이나 AIDC/전력망 연결 결함은 발견되지 않았습니다. 과학적 feasible set 변경은 필요하지 않습니다.

| 결과 | P1 | P2 GPUh | P3 | P4 | P5 |
|---|---:|---:|---:|---:|---:|
| B0 / 기존 production B1 | 0.5383475197373216 | 1604.7619377781873 | 0 | 0 | 957282143 |
| 최선 단일 작업 | 0.5383475197373216 | 1604.6631723460885 | 1 | 8 | 957282660 |
| 검증된 pair | 0.536990903169153 | 1572.8823081485577 | 2 | 2538 | 957924550 |
| 검증된 triple | 0.536990903169153 | 1572.783542716459 | 3 | 2546 | 957925067 |
| 검증된 coupled witness | 0.5363128252782274 | 1557.2341600004095 | 5 | 3426 | 958450215 |

명목 후보 3,847,255개 중 단일 작업 변경으로 가능한 대안 658개를 모두 전체 MPS 행·일반 제약·정수성·GPU·rack·WAN·전력으로 검증했습니다. 단일 변경 P1 개선은 0개, 동일 P1은 658개입니다.
PENDING 초기 사이트 대안이 있는 작업은 단일 변경 범위에서 26개, checkpoint migration 대안이 있는 PENDING 작업은 99개입니다. D00 RUNNING의 단일 이동은 0개지만 공동 이동에서는 가능합니다.
전체 원래 모델에서 두 admissible 값을 증명한 결정 변수는 최소 1,058개입니다. 모든 공동 조합의 실제 자유도를 전수 인증한 숫자는 아닙니다. 열린 LB/UB 수와 구분했습니다.
과거 157개 부분문제에서 열린 변수의 LB/UB 복구 누락은 0개입니다. P5의 P3=0/P4=0 잠금에 따른 암묵적 고정은 정상적인 lexicographic 제약입니다. 나머지 미인증 조합은 UNKNOWN으로 기록했습니다.

기존 production 선택: prestart 0개, checkpoint migration 0개. 명목 migration 옵션 3,839,503개와 선택 건수는 다릅니다.
D00 상태별 eligible migration 작업: {'RUNNING': 413, 'PENDING': 611}. 검증된 최선 diagnostic 선택: {'prestart_relocations': 0, 'running_migrations': 5, 'D00_RUNNING_migrations': 2, 'PENDING_becomes_RUNNING_migrations': 3, 'initial_IDC_different_jobs': [], 'checkpoint_migrated_jobs': ['8725925', '8750047', '8665900', '8665917', '8667226']}.
강제 변경 테스트에서 execution site, rack/GPU, IT, PCC P/Q, injection, line loading 및 voltage가 모두 반응했습니다.
세 non-B0 존재성 검사(순수 feasibility / P1 유지 / P1·P2 유지)는 모두 원래 모델에서 검증됐습니다.

최대 부하: line.sw2::A, A상, D18:00(issue slot 96), rho=0.5383475197373216. 이때 12 IDC가 전부 GPU-full입니다.
| IDC | P 방향 / kW | Q 방향 / kvar | 실제 AIDC 고정 PF 방향 / kW |
|---|---:|---:|---:|
| AIDC01 | 8.58882699e-08 | -2.66467436e-07 | -1.52990849e-08 |
| AIDC02 | 7.13609213e-07 | 9.80635675e-07 | 1.02838424e-06 |
| AIDC03 | 5.87827544e-07 | 8.18470975e-07 | 8.42766895e-07 |
| AIDC04 | 5.82166014e-07 | 7.98532975e-07 | 8.36221585e-07 |
| AIDC05 | 0.000330237794 | -6.26750724e-05 | 0.000309603179 |
| AIDC06 | 4.67960356e-07 | 6.10610975e-07 | 6.53889617e-07 |
| AIDC07 | 6.07647047e-07 | 8.3581592e-07 | 8.76321246e-07 |
| AIDC08 | 6.12937746e-07 | 8.53120864e-07 | 8.84811006e-07 |
| AIDC09 | 0.000328825349 | -5.61688978e-05 | 0.000310340434 |
| AIDC10 | 0.000329938078 | -6.56794951e-05 | 0.000308328153 |
| AIDC11 | 0.00032997262 | -6.54225474e-05 | 0.00030845575 |
| AIDC12 | 0.000330458005 | -6.45643598e-05 | 0.000309217232 |

P/Q 열은 co-located certified MESS P/Q 제어 열을 사용한 별도의 진단 perturbation입니다. AIDC 고정 PF 열의 정확한 분해라고 주장하지 않습니다. 검색 우선순위는 직접 AIDC 열을 사용하며 후보를 제거하지 않습니다.
발견된 pair는 먼저 P1 유지·P2 개선 단계를 거쳐 더 낮은 P1로 갈 수 있습니다. 비개선 중간 해를 반드시 수락해야 하는 trap은 입증되지 않았습니다. 공동 해를 하나의 제안으로 탐색할 이유는 충분합니다.
Cross-region 추가 강제 검사는 coupled 검사에서 이미 B0를 벗어났으므로 조건이 발동하지 않았습니다(ΔP1: N/A).
Placement-only 25개 작업 검사에서는 B0 그대로였습니다. Migration-only 검사는 더 낮은 P1을 찾았습니다. 전체 placement 전역 최적성/전체 B1 전역 최적성을 solver gap으로 주장하지 않습니다.
**해석상 중요한 점:** pair의 RUNNING job 8725925는 checkpoint 이후 92슬롯(23시간) 대기합니다. UID 순서의 WAN 직렬화가 늦은 PENDING 이동을 먼저 처리하며, 일부 작업량이 day horizon 밖으로 이동합니다. 원래 제약과 전체 safe compute service를 만족하지만 순수한 공간적 부하 분산 효과로 해석하면 안 됩니다.
**인증 불일치:** 앞선 coupled solve의 zero-gap bound 0.5366498148764607은 동일한 25개 작업에서 원래 전체 행을 통과한 0.5363128252782274 해와 모순됩니다. 해당 최적성 주장은 철회했습니다. Fresh model 재검사는 더 좋은 해를 확인했지만 전역 최적성 근거로 사용하지 않습니다. Migration-only raw proposal은 PWL residual 1.0455e-9로 원래 1e-9 기준을 초과했으며, 독립 재구성한 전체 assignment만 PASS로 인정했습니다.
과거 3% gap 재현 및 후속 첫 개선 탐색 수정 결과는 별도 FIRST_IMPROVEMENT 보고서에 연결합니다. 5월 전체 실행은 보류 상태입니다.

세부 경로와 SHA-256: [machine-readable report](V41R1_MAY04_B1_FLEXIBILITY_DIAGNOSTIC.json).
