# AIDC reactive-power forensic 최종

B0/B1의 현재 Planning·Fresh·Actual 경로는 PF=0.95 고정이다. Q=P×0.3286841051788632이므로 Q는 P와 함께 시간에 따라 변한다. Fixed Q가 아니다.

PCC_Q와 Q_PCC 및 OPENDSS_COMPONENT_ELEMENTS의 Q는 고정 PF에서 파생되거나 설정값을 읽은 것이다. readback은 Loads.kvar()를 SolveSnap 전에 읽는다. 독립 측정 Q가 아니며, 별도의 branch/transformer AC Q flow도 해당 load boundary를 조건으로 계산된 계통 반응이다.

Raw 목록 22,981개와 parquet schema 2,486개, 기존 repository schema 후보 3,335개를 선별하고 실제 producer/authority 경로를 추적했다. NLR 원본은 active-power/PUE만 제공한다. 독립 AIDC time-varying Q/PF authority는 확인되지 않았다. 미해독 RADDiT embedding parquet 45개 등 검색 한계를 JSON에 보존했다.

UPS/DRUPS 존재 언급은 있으나 AIDC별 Q range, P-Q capability curve, 응답·제어 주기는 없다. Native feeder capacitor와 MESS Q capability는 AIDC authority로 옮기지 않았다. Q optimization authorization=NO. 실제 PF 분산·leading/lagging 비율은 계산 불가이며 0.95 재산출을 validation으로 사용하지 않았다.

Frozen 방향 민감도에 따른 ΔI=0.148915853403 A, 저장 Actual=0.146241726480 A. 절대 차이=0.002674126923 A, Actual 대비 상대 차이=1.828566%.

이 방향 미분은 ∂I/∂P + tan(acos(.95))∂I/∂Q다. AIDC의 독립 P/Q partial은 현재 frozen cache에서 분리되지 않는다. 같은 상류 bus의 MESS P/Q gradients는 별도 750-kVA transformer/PCC를 거치므로 진단 proxy만 제공했다. 이를 1500-kVA AIDC PCC의 정확한 Q 미분으로 바꾸지 않았다.

Runtime/site가 +2 GPU occupancy 역전을 설명하며, 고정 PF로 연결된 P/Q가 전류 차이를 설명한다. 별도 reactive 원인이 확인된 것은 아니다. 하지만 순수 P만으로 설명됐다고 하거나 PF 변경의 영향이 작다고 확정할 근거는 없다. FIXED_PF_MODEL_FIDELITY_QUESTION=OPEN; FIXED_PF_AUTHORITY_INSUFFICIENT.

Level 0은 현 고정 PF 가정을 명시하고 유지하는 재현 baseline이다. Level 1 exogenous PF는 독립 P/Q 시계열과 pre-May 검증이 필요하다. Level 2 controllable Q는 장비 capability/control authority가 선행해야 한다. 어떤 level도 이번 작업에서 변경·적용하지 않았다.
