# 선택된24 지점의 PCC·저압 설비·민감도 감사

**현재 선택은12개 원본 source-guarded MV AIDC와12개 원본 고객측 LV STA이다.** 24 service/traffic ID와6 MESS unit을 유지했고, source CT·Triplex·정격·phase·자동 제어를 변경하거나 CT/STA/차량 수를 늘리지 않았다. 후보는 사전 동결한 개발일 response surrogate를 사용한1/2-site local selection이며, global optimum이나 실제 dispatch 성과를 뜻하지 않는다. 현장 근거가 없는 조건의 연구 포트 재설계는 사용자 허용 범위이며 Production/현장 인증은 주장하지 않는다.

한 공통 proper 회전 -168.244235052°, 양의 균일 배율·공통 이동 아래66 AIDC–AIDC, 144 AIDC–STA,66 STA–STA의276쌍/552 strict 축을 원본 traffic/source에서 직접 검사했다. 전부PASS이고 24 PCC가 서로 다르다.1m traffic 공차를 바꾸거나 개별 회전·이동·reflection을 사용하지 않았다. LV 좌표는 원본 상위primary bus의 proxy이므로 판정은 `ASSUMED_PROXY_DIRECTION_PASS`이며 실측 고객 지리방향을 보장하지 않는다. 원본CRS·단위·true east/north는 미인증이다.

AIDC의 원래v3 bus와 현재 bus, source root guard는 다음과 같다. 모두12.47kV/ABC/연속 source path 및 원본 host 제외·root distance≥원본 q05 1.3819547376654384Ω를 유지했다. 원본 v3는 고정 host에서 모든 pair 방향을 통과하지 못했지만, 현재 공동 재선정 결과는 별도 계약의 witness이다.

| 서비스 | traffic | old v3 bus | 선택 MV bus | root Ω |
|---|---|---|---|---|
| AIDC01 | TN_01 | l3234149 | m1125934 | 2.8173663638651747 |
| AIDC02 | TN_02 | e182733 | m1009805 | 12.33581198971096 |
| AIDC03 | TN_03 | m1027055 | m1027002 | 13.328783434465402 |
| AIDC04 | TN_04 | m1069411 | m1047480 | 9.64678519058967 |
| AIDC05 | TN_05 | l2688693 | l3029498 | 5.27111375152571 |
| AIDC06 | TN_06 | m1142814 | m1125976 | 3.268122549815905 |
| AIDC07 | TN_07 | m1026690 | l3048221 | 12.518369359479653 |
| AIDC08 | TN_08 | l3123452 | l2728247 | 5.428287812543354 |
| AIDC09 | TN_09 | l2728247 | m1069420 | 11.131223211150129 |
| AIDC10 | TN_10 | l2973833 | m1125962 | 3.0111416319998816 |
| AIDC11 | TN_11 | m1047763 | m1026872 | 9.608754069704714 |
| AIDC12 | TN_12 | e192258 | m1142875 | 2.5436191458780746 |

12개STA의 원본 서비스 transformer와Triplex rating, 고객bus 및primary proxy는 다음과 같다. Triplex NormalAmps와CT kVA는 원본 값을 그대로 표시했다. 5kW/3kvar/S6kVA/eachhot27A는 연구 PCS ceiling이며 이 원본 rating이나 차량450kW/600kVA로부터 새로운 허용 출력을 만들지 않는다. Split-phase는 하나의240V bus.1.2 포트이고 두120V leg에 전체 P/Q를 각각 복제하지 않는다. 원본 Kron-reduced neutral에 독립 neutral ampacity를 만들어 넣지 않았다.

| 서비스 | LV bus | 원본 CT | CT kVA | Triplex A | primary proxy bus | primary phase | proxy XY |
|---|---|---|---|---|---|---|---|
| STA01 | sx2955055b | transformer.t21249647b | 25.0 | 156.0 | l2955055 | 2 | (1683555.228,12271843.599) |
| STA02 | sx2992657a | transformer.t21475841a | 25.0 | 156.0 | l2992657 | 1 | (1684536.507,12273131.336) |
| STA03 | sx2936211c | transformer.t5260567c | 15.0 | 156.0 | l2936211 | 3 | (1683404.979,12277720.929) |
| STA04 | sx3085394c | transformer.t5274988c | 15.0 | 156.0 | l3085394 | 3 | (1679334.710,12273164.981) |
| STA05 | sx2897766c | transformer.t28128007c | 25.0 | 156.0 | l2897766 | 3 | (1679556.008,12275027.456) |
| STA06 | sx2822867b | transformer.t21386552b | 15.0 | 156.0 | l2822867 | 2 | (1672662.780,12274962.310) |
| STA07 | sx3047058a | transformer.t227902981a | 37.5 | 156.0 | l3047058 | 1 | (1663660.104,12278329.156) |
| STA08 | sx3729298a | transformer.t2224386617a | 37.5 | 156.0 | l3729298 | 1 | (1669980.523,12280472.912) |
| STA09 | sx3027133a | transformer.t226101449a | 25.0 | 156.0 | l3027133 | 1 | (1665589.971,12282579.526) |
| STA10 | sx2748125c | transformer.t5338962c | 25.0 | 156.0 | l2748125 | 3 | (1673854.540,12281160.618) |
| STA11 | sx3085401a | transformer.t28127253a | 37.5 | 156.0 | l3085401 | 1 | (1670835.092,12282505.036) |
| STA12 | sx2710516a | transformer.t5321839a | 25.0 | 156.0 | l2710516 | 1 | (1664363.248,12289282.671) |

민감도 데이터는 선택 이후 새AC를 실행해서 만든 것이 아니다. 기존 완료된 **BG0.552/capacity1/원래v3 AIDC B0 참조 operating point**의4시간 **00:00(slot0),02:15(slot9),12:00(slot48),18:45(slot75)**와 사전에 고정한20 원본 고부하 감시 선로에서 가져왔다. 원본 자동 제어가 정착한 같은base를 고정하고 MV에는±1kW/kvar,LV에는±0.1kW/kvar central difference를 적용한 기존 결과이다. 각 source의 baseline-binding terminal/phase current를 사용했고 MV source가 export하지 않은 terminal/conductor는 추정하지 않고 CSV에 NOT_EXPORTED로 남겼다.

MV/LV reference baselineρ 차이의 최대값은 0, 원본NormalAmps로 dI를 정규화한 dρ 오차의 최대값은 5.41e-16이다. 최종 선택 GPU scale/재배치 B0에서 민감도를 다시 계산했다는 주장은 하지 않는다. 큰 finite action, binding phase 변경, 자동 제어·혼잡 재배치의 비선형 효과는 별도 selected AC96slot 검증이 판단한다.

아래표의 |∂ρ/∂P|,|∂ρ/∂Q|는4시간×20 targets 중 최대 절대 partial이며 units는pu/kW 및pu/kvar이다. P/Q 액션은 후보 score에서 실제 사용한 같은4시간 순서이다. AIDC P는known-original-UID activeGPU·C1 swing footprint의 상한이고 Q/P=tan(acos0.95)로coupled된다. 이는 전체job QoS/WAN dispatch가 인증된 실제flexibility가 아니며 idle/anonymousCC4를 credit하지 않는다. STA는 원본 local CT/Triplex/PCC voltage의 1차 margin으로 제한한 P-only/Q-only/mixed-half finite action을 그대로 가져왔다. 각 PCC/time에서20 선로에 **한 공통P/Q vector**를 적용했다.

| 서비스 | max \|∂ρ/∂P\| pu/kW | max \|∂ρ/∂Q\| pu/kvar | P 액션 kW: 00:00/02:15/12:00/18:45 | Q 액션 kvar: 같은 시간 순서 |
|---|---|---|---|---|
| AIDC01 | 0.000117253 | 1.37168e-05 | 43.82 / 43.82 / 0 / 0 | 14.4 / 14.4 / 0 / 0 |
| AIDC02 | 0.00013432 | 3.03747e-05 | 14.24 / 20.81 / 2.191 / 0 | 4.681 / 6.841 / 0.7201 / 0 |
| AIDC03 | 0.000135322 | 3.04933e-05 | 4.382 / 4.382 / 4.382 / 2.191 | 1.44 / 1.44 / 1.44 / 0.7201 |
| AIDC04 | 0.000132325 | 3.53114e-05 | 2.191 / 4.382 / 4.382 / 4.382 | 0.7201 / 1.44 / 1.44 / 1.44 |
| AIDC05 | 0.000120021 | 1.37209e-05 | 29.03 / 29.03 / 0 / 0 | 9.541 / 9.541 / 0 / 0 |
| AIDC06 | 0.000119992 | 1.73993e-05 | 43.27 / 43.27 / 0 / 0 | 14.22 / 14.22 / 0 / 0 |
| AIDC07 | 0.000135182 | 3.543e-05 | 21.91 / 21.91 / 0 / 0 | 7.201 / 7.201 / 0 / 0 |
| AIDC08 | 0.000121283 | 1.83315e-05 | 43.82 / 43.82 / 0 / 0 | 14.4 / 14.4 / 0 / 0 |
| AIDC09 | 0.000132653 | 3.9338e-05 | 21.91 / 21.91 / 0 / 0 | 7.201 / 7.201 / 0 / 0 |
| AIDC10 | 0.000119323 | 1.66176e-05 | 43.82 / 43.82 / 0 / 0 | 14.4 / 14.4 / 0 / 0 |
| AIDC11 | 0.000133028 | 3.04032e-05 | 21.91 / 21.91 / 0 / 0 | 7.201 / 7.201 / 0 / 0 |
| AIDC12 | 0.00011814 | 1.51907e-05 | 43.82 / 43.82 / 0 / 0 | 14.4 / 14.4 / 0 / 0 |
| STA01 | 2.61054e-05 | 5.88206e-05 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| STA02 | 0.00036603 | 4.50207e-05 | 5 / 5 / 5 / 5 | 0 / 0 / 0 / 0 |
| STA03 | 3.86893e-05 | 8.35331e-05 | 0 / 0 / 0 / 0 | 3 / 3 / 3 / 3 |
| STA04 | 3.21972e-05 | 6.68287e-05 | 0 / 0 / 0 / 0 | 3 / 3 / 3 / 3 |
| STA05 | 3.26628e-05 | 6.69506e-05 | 0 / 0 / 0 / 0 | 3 / 3 / 3 / 3 |
| STA06 | 0.000122393 | 9.20985e-05 | 0.2455 / 0.2455 / 0.2455 / 0.2455 | -1.5 / -1.5 / -1.5 / -1.5 |
| STA07 | 0.000436666 | 8.33404e-05 | 5 / 5 / 5 / 5 | 0 / 0 / 0 / 0 |
| STA08 | 0.000427544 | 7.87105e-05 | 3.254 / 3.254 / 3.255 / 3.255 | 0 / 0 / 0 / 0 |
| STA09 | 0.000429642 | 8.02429e-05 | 4.926 / 4.926 / 4.926 / 4.926 | 0 / 0 / 0 / 0 |
| STA10 | 0.000127549 | 0.000197208 | 0 / 0 / 0 / 0 | 3 / 3 / 3 / 3 |
| STA11 | 0.000420004 | 7.54243e-05 | 4.8 / 4.8 / 4.801 / 4.801 | 0 / 0 / 0 / 0 |
| STA12 | 0.000435707 | 8.31241e-05 | 3.327 / 3.327 / 3.327 / 3.327 | 0 / 0 / 0 / 0 |

상세3840개 partial은 `SELECTED_PCC_PQ_SENSITIVITY.csv`,1920개 action prediction은 `SELECTED_CONTROL_POTENTIAL.csv`,96개 PCC/time 요약은 `SELECTED_PCC_PQ_SUMMARY.csv`, 48개LV local interval/PCC voltage partial은 `SELECTED_LV_LOCAL_LINEAR_BOUNDS.csv`에 있다. 대상20 line의 번호·원본NormalAmps는 `SELECTED_SENSITIVITY_TARGET_LEGEND.csv`에서 확인한다.

Prediction은 `ΔI≈(∂I/∂P)P+(∂I/∂Q)Q`, `Δρ≈(∂ρ/∂P)P+(∂ρ/∂Q)Q`로 계산했다. 음의Δρ는해당참조 binding axis의 predicted relief이고 양수는adverse response이다. 동시24 PCC의 실제 system maxρ 변화나B1/B2/B3 성과가 아니다. Root score의 negative-benefit/positive-adverse penalty2,초기6차량 safeETA+600s reachability와0.5 exposure를 같은 방식으로 재계산하여24개 선택 root score가 모두 일치했다. 이 mobility factor는 SOC·동시12dock·실제 route를 인증하지 않는다. Surrogate 증가율을 실제ρ 개선율로 해석하지 않는다.

[저압 연구 포트 설계](../../LV_PORT_SIMULATION_DESIGN.md)의 DC/DC·BMS·보호·접근/지연·효율 가정과 원본 전압/선로/CT/반전력/PQ 제약은 별도 actual selected-case audit에 남는다. 이 보고서는 새AC/Native를 실행하지 않고 현재 mapping·scores·선택 prereg 및 root main report/copies를 변경하지 않았다.

현재 mapping SHA256: `4a70fd13bf08c8512d30f74e48dfafb46fdddd4e112a3aee92a8191f22cad016`. 재현 명령은 `.runtime/Scripts/python.exe -m ieee8500_v42.selected_location_audit --root .`이며 입력·CSV SHA/coverage는 `SELECTED_LOCATION_AUDIT_RECEIPT.json`에 있다.

<!-- selected-reference-sensitivity-figures -->

모든24 PCC×4시간×20 target의 P/Q partial과 동일 bounded P/Q 액션의 예측은 다음 그림에서 확인한다. 공통 대칭 signed-log 색상 척도를 사용하고 값 보간·누락0 대체를 하지 않았다. 음수 blue는 참조 axis의 전류/ρ 감소이고 red는 증가이다. 이 색상은 실제 정책 성과나 동시 dispatch를 나타내지 않는다.

- [P/Q loading partial: PNG](figures/SELECTED_PQ_RHO_SENSITIVITY_HEATMAP.png), [SVG](figures/SELECTED_PQ_RHO_SENSITIVITY_HEATMAP.svg)
- [P/Q current partial: PNG](figures/SELECTED_PQ_CURRENT_SENSITIVITY_HEATMAP.png), [SVG](figures/SELECTED_PQ_CURRENT_SENSITIVITY_HEATMAP.svg)
- [Bounded common P/Q control potential: PNG](figures/SELECTED_CONTROL_POTENTIAL_HEATMAP.png), [SVG](figures/SELECTED_CONTROL_POTENTIAL_HEATMAP.svg)

그림 포함 재현 명령: `.runtime/Scripts/python.exe -m ieee8500_v42.selected_location_audit --root . --plots`.
