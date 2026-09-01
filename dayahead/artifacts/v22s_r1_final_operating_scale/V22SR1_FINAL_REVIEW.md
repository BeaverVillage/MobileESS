# V22S-R1 최종 운영부하 스케일 검토

RESULT CLASSIFICATION:
V22SR1_FINAL_OPERATING_LOAD_SCALE_COMPLETE

## 1. 최종 case 정의

정식 명칭은 `MELBOURNE_INFORMED_EQUIVALENT_12SITE_OPERATING_LOAD_CASE`이다. 과학적 표현은 **Melbourne-informed equivalent AIDC operating-load scale**이며, 실제 2025년 4월 Melbourne 계량부하 전수조사가 아니다.

## 2. 출처 재검증 수정

Fujitsu 28 MW IT Load, NEXTDC M2 42 MW/M3 13.5 MW built, CDC Melbourne 34 MW operating build, STACK 첫 36 MW 시설은 원문에서 재확인했다. ME5 현행 페이지는 N+1만 노출하므로 이전 공식 사양의 발전기 명판값을 보존했다. MEL11은 현행 공식 주소·중복도와 2020년 Digital Realty 브랜드 포트폴리오 보관본의 LIVE 7.02 MW를 결합하되 실제 부하로 해석하지 않았다.

## 3. 12-site primary IT-equivalent capacity

| Site | Facility | IT-equivalent MW | 원래 boundary | 방법/등급 |
|---|---|---:|---|---|
| AIDC01 | Equinix ME4 | 12.000000000000 | IT_CAPACITY | SOURCE_BACKED_IT_CAPACITY; DIRECT_SOURCE_VALUE / E |
| AIDC02 | Micron21 | 2.000000000000 | FULLY_BUILT_OUT_POWER | SECONDARY_CRITICAL_POWER_EQUIVALENT; ENGINEERING_IT_EQUIVALENT_PROXY / F |
| AIDC03 | Fujitsu Noble Park | 28.000000000000 | IT_CAPACITY | SOURCE_BACKED_IT_CAPACITY; DIRECT_SOURCE_VALUE / A |
| AIDC04 | AAPT / TPG Richmond | 1.884615384615 | MVA_INPUT | ENGINEERING_IT_EQUIVALENT_FROM_MVA; ENGINEERING_PF_AND_PUE_CONVERSION / F |
| AIDC05 | NEXTDC M2 | 42.000000000000 | BUILT_CAPACITY | SOURCE_BACKED_DATA_HALL_DESIGN_POWER_CAPACITY; ENGINEERING_IT_EQUIVALENT_PROXY / B |
| AIDC06 | NEXTDC M3 | 13.500000000000 | BUILT_CAPACITY | SOURCE_BACKED_DATA_HALL_DESIGN_POWER_CAPACITY; ENGINEERING_IT_EQUIVALENT_PROXY / B |
| AIDC07 | Vocus Mitcham | 9.000000000000 | FULLY_BUILT_OUT_POWER | SECONDARY_CRITICAL_POWER_EQUIVALENT; ENGINEERING_IT_EQUIVALENT_PROXY / F |
| AIDC08 | NEXTDC M1 | 15.000000000000 | IT_CAPACITY | SOURCE_BACKED_IT_CAPACITY; DIRECT_SOURCE_VALUE / A |
| AIDC09 | Equinix ME5 | 2.346153846154 | GENERATOR_NAMEPLATE | ENGINEERING_EQUIVALENT_IT_CAPACITY_PROXY_FROM_N_PLUS_1_BACKUP; N_PLUS_1_ENGINEERING_IT_EQUIVALENT_PROXY / A |
| AIDC10 | CDC Brooklyn BK1 | 34.000000000000 | OPERATING_CAPACITY | SOURCE_BACKED_OPERATING_BUILD_CAPACITY_EQUIVALENT; ENGINEERING_IT_EQUIVALENT_PROXY / B |
| AIDC11 | IBM MEL01 / Digital Realty MEL11 | 7.020000000000 | HISTORICAL_LIVE_FACILITY_CAPACITY | HISTORICAL_DIGITAL_REALTY_FACILITY_CAPACITY_PRIMARY; HISTORICAL_ENGINEERING_IT_EQUIVALENT_PROXY / B |
| AIDC12 | STACK MEL01A | 36.000000000000 | BUILT_CAPACITY | SOURCE_BACKED_BUILT_CRITICAL_CAPACITY; ENGINEERING_IT_EQUIVALENT_PROXY / A |


합계는 **202.750769230769 MW**이다.

## 4. 이용률 권한

Low 0.435, primary 0.46, high 0.491803278689이다. Primary 0.46은 IEEE Electrification Magazine의 EU Code of Conduct 참여 데이터센터 평균이며, high는 NEXTDC billing/built deployment proxy라 실제 전기 이용률이 아니다.

## 5. 동결 형상

V4R1 7개 참조일의 672 슬롯을 연결해 형상만 사용했다. `mean/max = 0.845168739654049`이고 기존 절대 kW는 폐기했다.

## 6. 등가 운영 IT 및 PCC

- 평균 IT: 93.265353846154 MW
- 피크 IT: 110.351163584600 MW
- 평균 PCC (PUE 1.30): 121.244960000000 MW
- 피크 PCC (PUE 1.30): 143.456512659980 MW

## 7. 중복 없는 host 분모

DPTS는 AIDC01/11/12에 대해 한 번만 계산하고 LVN/TNA를 추가하지 않았다. DPTS 276.752 MW와 나머지 9개 host 351.394 MW의 합은 **628.146000000000 MW**이다.

## 8. 실세계 등가 penetration

동일 load boundary의 산술 결과는 `rho = 0.228380842447424`이다. 이는 실제 계량 penetration 주장이 아니다.

## 9. IEEE123 분모

동결된 AIDC-free background peak active power는 **2.315469136075646 MW**이다. 5 MVA transformer capacity authority와 혼용하지 않았다.

## 10. 최종 IEEE123 AIDC scale

최종 aggregate AIDC PCC peak는 **0.528808791957965 MW**이다. 목표값이나 grid 결과에 맞춘 수치가 아니다.

## 11. Site power weights

| Site | weight |
|---|---:|
| AIDC01 | 0.059185965338271 |
| AIDC02 | 0.009864327556378 |
| AIDC03 | 0.138100585789298 |
| AIDC04 | 0.009295231735818 |
| AIDC05 | 0.207150878683947 |
| AIDC06 | 0.066584211005554 |
| AIDC07 | 0.044389474003703 |
| AIDC08 | 0.073982456672838 |
| AIDC09 | 0.011571615018059 |
| AIDC10 | 0.167693568458433 |
| AIDC11 | 0.034623789722888 |
| AIDC12 | 0.177557896014812 |

가중치 합은 machine precision에서 1.0이다. GPU weight authority는 unavailable이다.


## 12. 이용률 민감도

- low: 0.500069183699 MW
- primary: 0.528808791958 MW
- high deployment proxy: 0.565369342792 MW

## 13. Capacity evidence envelope

ME4 7.6/12/18, AAPT PF 0.95/0.98/1.00, MEL11 5.76·6.7/7.02/10.0·13.4를 유지했다. ME5 lower는 양의 open bound이며 임의 양수 하한을 만들지 않았다. 결합 engineering envelope는 **(0.480180327154, 0.602411270663] MW**이다.

## 14. PCC interface sizing

PF 0.98, loading 0.80을 사전 동결하고 각 site의 IEEE123 등가 PCC peak에서 표준 transformer size로 올림했다. 결과는 실제 Melbourne transformer가 아니라 `IEEE123_EQUIVALENT_CASE_STUDY_INTERFACE`이다.

## 15. Lineage / deprecation

V4R1 약 1.208 MW는 legacy stress scale, V20/V22S 부분 결과는 primary operating-load scaling에서 superseded, V22S 1.0–1.62 MW는 capacity-to-capacity diagnostic이다. V22S-R1 값만 현재 primary Melbourne-informed equivalent operating-load scale이다.

## 16. 미해결 항목과 firewall

실제 4월 계량부하, 정확한 개별 전기사업자 서비스점, 실제 transformer rating, GPU weight는 여전히 미확정이다. ML 재학습, forecast 수정, GPU-h scaling, B0–B3, OpenDSS, grid science, 결과기반 튜닝은 모두 0이다.

## 17. Ready flags 및 Git

등가 operating-load scale, site power weight, PCC engineering interface는 ready이다. GPU weight authority는 ready가 아니며 `FINAL_GRID_SCIENCE_READY = false`, `FINAL_GRID_SCIENCE_AUTHORIZED = false`이다. 시작 HEAD는 `a842d301febc523dfca5d4803aebdf70b048586e`; 종료 커밋과 clean 상태는 최종 응답에 기록한다.
