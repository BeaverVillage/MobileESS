# 단일 운영 시나리오 결정 상태

**최종 논문/Production 주 계통은 아직 선정·동결하지 않았다.** 이번 실행은 이미 노출된2025-05-01에서 공식 Balanced P5를 기존 Unbalanced P5와 비교한 단일 연구 후보다. 고객 총 P/Q 및 네트워크를 보존한 synthetic 고객 hot 균형 구성은 AC에서 유효하나, 결과가 유리하다는 이유만으로 주 검증 계통으로 자동 채택하지 않는다.

| 항목 | Unbalanced Planning | Balanced Planning | Unbalanced Actual | Balanced Actual |
|---|---:|---:|---:|---:|
| 전체 최대 rho | 0.939955961 | 0.528279075 | 0.939831403 | 0.570974936 |
| Primary 최대 rho | 0.529585849 | 0.528279075 | 0.572277146 | 0.570974936 |
| Triplex 최대 rho | 0.939955961 | 0.468376642 | 0.939831403 | 0.467035775 |
| Vmin | 0.962436203 | 0.979170031 | 0.966540541 | 0.980022141 |
| Vmax | 1.041741567 | 1.041752129 | 1.040245991 | 1.040247149 |
| Primary 최대 슬롯 수 | 0 | 32 | 0 | 43 |
| Triplex 최대 슬롯 수 | 96 | 64 | 96 | 53 |
| 옛 tpx21459660c0 최대 슬롯 수 | 96 | 26 | 96 | 29 |
| 병목 전환 횟수 | 0 | 9 | 0 | 5 |


이후 판단은 B1/B2/B3 성과를 보기 전에 연구 질문(실제 레그 불평형에 대한 강건성인지, 공식 균형 baseline에서 중압 유연성/계산 확장성을 검증할지), 같은 입력·제약, 양 case 병목 구조와 미검증 항목을 공개하고 수행해야 한다. 불리한 Unbalanced P5는 commit `5cf5986a981428a4544a3a82d44b8e55d635fb70` 및 PR196에 보존하며 비교·한계로 유지한다.

현재 study candidate: Source1.04, all12 Vreg123.5, CAPBank3OFF, 원본9CapControl, BG.552, installedGPU780, 12AIDC/12LVSTA/6MESS와 기존 mapping·ETA·연결600초. 차량450kW/600kVA/1800kWh, port5kW/3kvar/6kVA/27A. B0P/Q_MESS=0. Source/Scale/PV/접속점 및 원본 정격을 결과에 맞추어 변경하지 않았다.

B0 physical gate=PASS; Production=BLOCKED. 실제 지리/접근/보호/LV 보조장치, 데이터 publication/as-of, six-unit Native/Actual 및 위치별 효율/SOC/fullC3A 등 기존 UNVERIFIED gate를 유지한다. 본 반사실은 순간 upper endpoint이며 운영 가능한 workload/route 스케줄 인증이 아니다. 최종 사용자 연구 구성 판단 전 동결하지 않는다.
