# Exact M1 acceleration 개발 최종 검토

Draft PR: https://github.com/BeaverVillage/MobileESS/pull/154 (base: frozen PR152 branch). 최종 delivery SHA와 remote 일치는 Git/PR head로 확인한다.

과학적 기준: PR152 `63e81dc3b6d236549f566e65e07dcd05ac0a160c`, pool 1,604, LB 0.5687115725336208, UB 0.5741861223241257. authoritative checkpoint는 변경하지 않았다.

Full pytest: 1900 passed / 1 failed / 0 errors. failure는 PR152 exact 원본에서도 재현된 historical branch-scope assertion이며 assertion을 바꾸거나 숨기지 않았다. 전체 원본 파일 12919개 byte 보존 및 saved-point original matrix 독립 audit PASS.

최종 M1_ACCELERATION_SELECTED=false, 상태=NONCOMPARABLE.

| Variant | Pricing wall | RMP wall | New cols | UB decrease | UB decrease/s | Root/LB effect | Peak RSS | Selected |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| PR152 baseline | N/A | N/A | 15 | 7.03537e-05 | N/A | frozen LB 0.5687115725336208 | 14511706112 | False |
| Persistent RMP | N/A | 213.683 | 10 | 6.9796e-05 | 3.26634e-07 | no new certificate | 12829007872 | False |
| Stabilized CG | N/A | N/A | 0 | N/A | N/A | no new certificate | 14303662080 | False |
| Specialized pricing | N/A | N/A | 0 | N/A | N/A | no new certificate | 628715520 | False |
| Pricing dominance | N/A | N/A | 0 | N/A | N/A | no new certificate | N/A | False |
| Root cuts | N/A | N/A | 0 | N/A | N/A | 0 (redundant full-DW cuts) | N/A | False |
| Final exact combination | N/A | N/A | N/A | N/A | N/A | frozen independent LB unchanged | 14511706112 | False |

N/A는 미측정/미완료 또는 NONCOMPARABLE이다. partial incumbent와 timing을 성능 선택이나 lower bound에 사용하지 않았다.

Stage 1: matrix/objective identity PASS, persistent+basis 총 시간은 cold보다 느려 REJECTED.

Stage 2: box guidance LP가 90초 cap 안에 optimal이 되지 않아 미채택. alpha sweep이나 자동 연장은 없었다.

Stage 3: HYBRID_DP_LP_POSSIBLE, continuous SOC/P/Q 유지한 toy 3개 PASS. B1 실제 PID+optimize overlap 때문에 timing 제외; full-scale hybrid 비교 미완료, 미채택.

Stage 4: 실제 block의 exact parallel-arc 제거 대상 0개. 동일 formulation의 추가 native solve 없이 구조적으로 REJECTED.

Stage 5: INCONCLUSIVE_CONTROLLER_INTERRUPTION. mode-linking cut은 정수 해에 유효하고 toy arc LP를 강화하지만 full D-W에는 redundant라 이론적 root-bound 효과는 0이다. own runner의 상태를 대기로 잘못 판단해 제어 중단한 원본 RMP/첫 root receipt는 보존했고 재실행하지 않았다. 두 번째 root는 terminal receipt가 없어 인증에서 제외했다. cuts full-scale 비교는 미완료라 미채택했다.

최종 조합은 개별 retained stage만 포함했다. 빈 집합이면 PR152 identity 비교이며 개선 알고리즘으로 채택하지 않는다.

Root-CG 10–15분 도달 가능성은 한 round로 외삽할 근거가 없어 추정하지 않았다. 다음 단일 blocker는 >=20% exact end-to-end 효율 개선에 대한 재현 가능한 증거의 부재다.

마지막 사용자 지시에 따라 최종 비교는 B1 worker의 존재 또는 actual overlap을 이유로 중단하지 않았다. actual overlap이 관측된 시간은 NONCOMPARABLE로 기록하고 selection evidence에서 제외했다. RAM/commit/deadline 보호는 유지했다.

최종 비교는 125.071초에 종료됐다. PR152 leg는 validated 15 columns, audited UB 0.574115768594322, UB decrease 0.00007035372980368493을 얻었다. 다음 candidate leg의 pricing build 중 available RAM 최소 0.129009 GiB로 1 GiB floor가 발동했고 own children만 종료했다. foreign native PID 37092의 actual optimize overlap도 확인됐다. candidate 비교는 미완료이며 raw time은 채택 근거에서 제외했다. 추가 run/예산 연장은 없었다.

Stage 1의 UB decrease/s는 controlled RMP-only 반복 기준이며 end-to-end Discovery+RMP 효율과 직접 비교하지 않는다. Table의 Peak RSS는 bytes이며 NONCOMPARABLE timing은 N/A다.

Lane A의 May production calls=0/0/0. B1의 자체 대기/중단/재시작은 read-only 관측만 했으며 제어 호출은 0이다.

본 작업은 휴리스틱 또는 convergence tolerance 완화 없이 exact M1 알고리즘의 계산 효율만 개선했다.

B1 May production은 독립적으로 실행되었으며, Lane-A 작업은 B1 process/worktree/artifacts를 변경하거나 종료하지 않았다.

실행시간 비교에 사용된 full-scale microbenchmark는 다른 heavy native solve와 겹치지 않은 구간만 selection evidence로 사용했다.

장시간 authoritative root-CG continuation과 Branch-and-Price는 별도 승인 전까지 실행하지 않았다.
