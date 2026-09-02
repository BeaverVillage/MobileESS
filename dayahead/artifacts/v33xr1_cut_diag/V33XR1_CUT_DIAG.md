# V33XR1-DIAG — E1 전압 컷 결함 대 제어 가능 범위 감사

## 판정

**V33XR1_DIAG_CUT_CORRECT_CONTROL_AUTHORITY_INSUFFICIENT**

컷 구현, 부호, 단위, site/slot 축, 계획 기울기는 모두 정상이다. 서비스 목적을 완전히 제거하고 frozen E1 Stage-2 feasible set 안에서 전압 컷 affine LHS만 최소화해도 slot 85와 95 모두 1.05 pu에 도달하지 못한다. 따라서 V33XR1 실패 원인은 컷 결함이 아니라 frozen E1의 전압 보정 제어권 부족이다.

실행 범위는 B1 E1 궤적 재구성, slot 85의 독립 단일-slot OpenDSS 7회(기준점 1회와 AIDC10/11/12 각각 ±1 kW), slot 85·95 보조 LP로 제한했다. 96-slot Fresh, B3, E2, MESS, Stage-1, 회귀 전체 실행은 하지 않았다. HiGHS와 BLAS 스레드는 4로 고정했다.

## 1. 컷 anchor identity

컷 식은 `V_fresh_k + a_k^T(p-p_k) <= 1.05`이다. `p=p_k`에서 네 컷 모두 LHS가 저장된 Fresh 전압과 정확히 같았다.

| cut | slot | node | Fresh V (pu) | anchor LHS (pu) | 절대오차 (pu) | 결과 |
|---|---:|---|---:|---:|---:|---|
| I01_B1_T85_N238_01 | 85 | 83.1 | 1.050210480163198 | 1.050210480163198 | 0 | PASS |
| I01_B1_T85_N383_02 | 85 | mess_sta12_pcc.1 | 1.050210449969648 | 1.050210449969648 | 0 | PASS |
| I01_B1_T95_N238_03 | 95 | 83.1 | 1.050068868600175 | 1.050068868600175 | 0 | PASS |
| I01_B1_T95_N383_04 | 95 | mess_sta12_pcc.1 | 1.050068838410696 | 1.050068838410696 | 0 | PASS |

현재 frozen coefficient에서 네 sensitivity를 다시 유도한 결과, ledger 벡터와의 최대 절대오차도 `0 pu/kW`였다.

## 2. 부호

- 최적화 P 규약: **LOAD_POSITIVE**. `voltage_cut_recourse.py:127-131`에서 workload가 늘면 site PCC P가 증가한다.
- 계획 전력망 규약: `full_ieee123_g11_v16_1.py:306-313`에서 양의 AIDC load control은 P 주입과 Q 주입에 음수 계수로 들어간다.
- Fresh 규약: `opendss_mapping.py:56-59,144-146`에서 양의 P/Q를 전용 PCC `Load` 객체의 kW/kvar로 적용한다.
- sensitivity 규약: `dV_pu/d(AIDC_load_kW)`. 과전압 지점의 주요 sensitivity가 음수이므로 AIDC 부하를 늘리면 전압이 내려간다.

**SIGN_CONSISTENT = YES (PASS)**

## 3. 단위

- `p`: kW
- `a`: pu/kW
- `a^T delta_p`: pu
- 변환: `runner.py:176-181`의 `dV/dP = d(V^2)/dP / (2 V_plan)`

수치 예: slot 85, 83.1, AIDC10에서 `a_i = -3.097963330982653e-05 pu/kW`, `delta_P_i = +1 kW`, 따라서 `a_i delta_P_i = -3.097963330982653e-05 pu`이다. ×1000 또는 ÷1000 불일치는 없다.

**UNIT_CONSISTENCY = PASS**

## 4. site 및 slot 축

| index | site | 최적화 control | cut anchor | sensitivity 열 | Fresh load |
|---:|---|---|---|---|---|
| 0 | AIDC01 | aidc_load_kw[AIDC01] | pcc_p_kw[slot,0] | voltage_matrix[0,node] | IDC_IDC01 |
| 1 | AIDC02 | aidc_load_kw[AIDC02] | pcc_p_kw[slot,1] | voltage_matrix[1,node] | IDC_IDC02 |
| 2 | AIDC03 | aidc_load_kw[AIDC03] | pcc_p_kw[slot,2] | voltage_matrix[2,node] | IDC_IDC03 |
| 3 | AIDC04 | aidc_load_kw[AIDC04] | pcc_p_kw[slot,3] | voltage_matrix[3,node] | IDC_IDC04 |
| 4 | AIDC05 | aidc_load_kw[AIDC05] | pcc_p_kw[slot,4] | voltage_matrix[4,node] | IDC_IDC05 |
| 5 | AIDC06 | aidc_load_kw[AIDC06] | pcc_p_kw[slot,5] | voltage_matrix[5,node] | IDC_IDC06 |
| 6 | AIDC07 | aidc_load_kw[AIDC07] | pcc_p_kw[slot,6] | voltage_matrix[6,node] | IDC_IDC07 |
| 7 | AIDC08 | aidc_load_kw[AIDC08] | pcc_p_kw[slot,7] | voltage_matrix[7,node] | IDC_IDC08 |
| 8 | AIDC09 | aidc_load_kw[AIDC09] | pcc_p_kw[slot,8] | voltage_matrix[8,node] | IDC_IDC09 |
| 9 | AIDC10 | aidc_load_kw[AIDC10] | pcc_p_kw[slot,9] | voltage_matrix[9,node] | IDC_IDC10 |
| 10 | AIDC11 | aidc_load_kw[AIDC11] | pcc_p_kw[slot,10] | voltage_matrix[10,node] | IDC_IDC11 |
| 11 | AIDC12 | aidc_load_kw[AIDC12] | pcc_p_kw[slot,11] | voltage_matrix[11,node] | IDC_IDC12 |

12개 site 모두 정확히 정렬되어 **SITE_AXIS = PASS**이다.

모든 배열은 zero-based slot을 사용한다. slot 85는 one-based interval 86, `2025-04-04 21:30:00+10:00` 종료 구간이고, slot 95는 one-based interval 96, `2025-04-05 00:00:00+10:00` 종료 구간이다. 같은 인덱스가 최적화, coefficient, anchor, Fresh 적용에 사용되어 **SLOT_AXIS = PASS**이다.

## 5. 계획 기울기 대 Fresh 유한차분

slot 85, node 83.1에서 절대 sensitivity가 가장 큰 AIDC10/11/12를 검사했다. 각 perturbation은 동일 PCC의 P에 ±1 kW, Q에 ±0.3286841051788632 kvar를 함께 적용해 PF=0.95를 보존했다.

| site | 계획 (pu/kW) | Fresh 중앙 FD (pu/kW) | 부호 | 상대 크기 오차 |
|---|---:|---:|---|---:|
| AIDC10 | -3.097963330983e-05 | -3.101988680509e-05 | 일치 | 0.1299% |
| AIDC11 | -2.808909749604e-05 | -2.815483163621e-05 | 일치 | 0.2340% |
| AIDC12 | -2.343024820049e-05 | -2.350580486576e-05 | 일치 | 0.3225% |

부호는 전부 일치하고 최대 상대 크기 오차는 0.3225%이다. 이는 계획 sensitivity와 Fresh 물리 응답이 근사 크기까지 일치한다는 강한 증거다.

허용된 독립 단일-slot clean-engine 기준 전압은 1.050207750106921 pu로, 저장된 순차 실행의 1.050210480163198 pu보다 2.730056277e-06 pu 낮다. 중앙차분의 +/− perturbation과 기준점은 모두 동일한 독립 single-slot context를 사용했으므로 derivative 비교에는 영향을 주지 않는다.

## 6. 서비스 목적 없는 최대 보정 보조 LP

기존 shortfall는 이미 요청된 보조 LP에서 생성된 값이다. `voltage_cut_recourse.py:188-205`는 컷을 실제 constraint로 추가하기 전에 frozen base grid/resource feasible set에 대해 `min a^T p`를 풀고 `minimum_site_lhs - required_rhs`를 기록한다. 서비스 최대화 목적은 이 단계에 들어가지 않는다.

동일 보조 LP를 각 컷에 대해 독립 재실행했고 기존 값과의 오차는 모두 정확히 0이었다.

| slot | node | 최소 affine V (pu) | 1.05 대비 shortfall (pu) | 컷 가능 |
|---:|---|---:|---:|---|
| 85 | 83.1 | 1.050059276788608 | 5.927678860782e-05 | NO |
| 85 | mess_sta12_pcc.1 | 1.050059246599405 | 5.924659940514e-05 | NO |
| 95 | 83.1 | 1.050068931595770 | 6.893159577018e-05 | NO |
| 95 | mess_sta12_pcc.1 | 1.050068901406289 | 6.890140628901e-05 | NO |

unique slot의 binding 결과는 다음과 같다.

- slot 85: 최소 1.050059276788608 pu, shortfall 5.927678860782e-05 pu
- slot 95: 최소 1.050068931595770 pu, shortfall 6.893159577018e-05 pu

따라서 모든 서비스 가치를 희생해도 frozen E1은 두 slot 모두 컷을 만족할 수 없다.

## 7. 같은 슬롯의 전기적 중복성

| slot | sensitivity cosine | 최대 성분 차이 (pu/kW) | feasible set 내 V(83.1)-V(PCC) 범위 (pu) | 판정 |
|---:|---:|---:|---:|---|
| 85 | 0.9999999999999999 | 8.9086e-13 | [3.018920267e-08, 3.019518849e-08] | 동일 모드, 83.1 컷이 항상 지배 |
| 95 | 1.0000000000000000 | 8.8016e-13 | [3.018948117e-08, 3.018948117e-08] | 동일 모드, 83.1 컷이 항상 지배 |

벡터는 bitwise 동일하지 않지만 frozen E1 feasible set 전체에서 83.1 affine 전압이 PCC affine 전압보다 항상 약 3.019e-08 pu 높다. 따라서 각 slot에서 83.1 컷이 `mess_sta12_pcc.1` 컷을 실질적으로 지배하며, 네 위반은 두 개의 unique electrical mode다.

## 결론과 다음 조치

- 컷 구현 결함: **NO**
- sensitivity-model 결함: **NO**
- frozen E1 제어권 부족: **YES**

가장 작은 다음 조치는 **Stage-1 전압 보정 recourse capability를 설계하는 것**이다. E2와 MESS는 건드리지 않는다.
