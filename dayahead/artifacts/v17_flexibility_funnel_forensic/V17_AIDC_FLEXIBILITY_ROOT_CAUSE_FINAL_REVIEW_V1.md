# V17 AIDC Flexibility Funnel Root-Cause Final Review V1

RESULT CLASSIFICATION: D. MULTI_FACTOR_ATTRITION

## 핵심 결론

92.0945%는 학습기간 semantic-flexible GPU-hour 중 V1+V4R1 U2_CLEAN 전력 지원범위의 비율이며 시설 전체 IT 전력 비율이 아니다. 7개 평가일의 source-backed flexible IT는 604.164768 kWh로 전체 IT 131984.076435 kWh의 0.457756%이다. 이 성분만 D-1 스케줄러의 전기적 가동범위가 되고, 실제 최대 개별 AIDC PCC 이동은 4.111208 kW였다. B1 목적함수 개선은 AIDC-only 상한의 평균 99.901050%에 도달하므로 주된 설명은 optimizer 결함이 아니라 작은 authority-backed actuator와 그리드 민감도/제약이다.

## Reviewer-safe 경계

- Dataset312: NVML GPU-board incremental power만 유연 전력으로 인정한다.
- Kestrel: workload/resource telemetry이며 usable positive U2 host-energy가 없다.
- Eagle: node total-power는 있으나 V100→H100 절대 전력 전이와 shared marginal response가 승인되지 않았다.
- ESIF: whole-facility IT magnitude를 제공하지만 workload schedulability attribution은 없다.
- CPU/host/memory/storage/network의 workload-dependent 유연 전력은 현재 authority에서 식별할 수 없다.

## 핵심 수치

- 전체 IT 평균/피크: 785.619503 / 929.541600 kW
- 전체 PCC 평균/피크: 1021.305353 / 1208.404080 kW
- 유연 IT 평균/피크: 3.596219 / 5.039557 kW
- 유연 PCC 평균/피크: 4.675085 / 6.551424 kW
- B1/B3 실제 이동 PCC 에너지(L1/2): 75.917696 / 76.438841 kWh
- 최대 개별 AIDC PCC 이동: 4.111208 kW
- B3 MESS 실제 aggregate active-power peak / AIDC peak shift: 220.000000 kW / 4.111208 kW = 53.512250배

Counterfactual C0~C5는 모두 `NON_AUTHORITY_DIAGNOSTIC`이며 새 과학 권위나 scale 선택이 아니다.
