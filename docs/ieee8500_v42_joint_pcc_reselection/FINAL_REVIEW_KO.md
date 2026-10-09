# IEEE8500 V42 공동 PCC 최종 검토

**단일 선택은 C2/BG0.85/원본780GPU/12MV STA이며 May01의 완전96슬롯 모델-grid·Fresh 적격성은 PASS다. 현장·Native Production 승격은 UNVERIFIED gate로 차단한다.**

| 입력 | B0 전체/Primary/Triplex 최대ρ | MESS=적용 Joint 전체최대ρ | B0 Vmin/Vmax | 전압/선로/변압기 위반 |
|---|---|---:|---|---|
| PLANNING May01 | 0.810230773 / 0.810230773 / 0.730790494 | 0.804653414 | 0.964367216 / 1.041439225 | 0/0/0 |
| ACTUAL May01 | 0.848320702 / 0.848320702 / 0.731301776 | 0.841617405 | 0.957889181 / 1.041593772 | 0/0/0 |

### Q1. 기존 불가능성은 새 공동 문제에도 적용되는가?

아니다. 고정 AIDC12+guardedMV606+공통 proper rotation 조건에서만 STA6개 도메인0이었다. AIDC 고정을 해제한 C1/C2의 실제552축 PASS witness가 새 문제의 feasible 증거다.

### Q2–Q3. AIDC12와 STA12는 어디인가?

다음 원본 버스 표와 JOINT_LOCATION_SELECTION.csv/P0_PCC_MAPPING_COMPARISON.csv를 참조한다.

### Q4. STA MV/LV 수는?

선정 C2는12/0. 비교 C1은 사전 parity6/6, C0는 원래0/12이다. 차량은 모든 경우6대이며 위치24개를 유지한다.

### Q5. 전기·교통 분산성이 충분한가?

동결 연구 제약(AIDC/STA 각≥4권역, 전체≥6권역, 역할별≤4·합계≤6/권역)은 PASS. C2는 각각7권역이고 원본 traffic24 IDs/ETA가 유지된다. 현장 거리·GIS 접근성과 Native6대 이동 인증, 전기적 응답 독립성은 미확인이라 설치·Production 충분성으로 확대하지 않는다.

### Q6. 서로 다른 lateral에는 얼마나 분산됐는가?

MAJOR:l2820531=2, MAJOR:l3081380=9, MAJOR:m1047526=5, TRUNK_OR_MINOR_LATERAL 집계=8개다. 원본3개 named major 라벨+집계 bucket이며 arbitrary8권역을 independent lateral로 세지 않는다.

### Q7. Planningρ는0.75–0.85 범위인가?

B0 0.810230773로 범위 내다. BG=0.85는 Planning-only 사전 규칙에 따라 선택했고 실제 Actual 값으로 조정하지 않았다.

### Q8. Primary/Triplex 병목은?

Planning B0의 Primary/Triplex 최대는0.810230773/0.730790494, MESS는0.804653414/0.732093426. Binding은 B0 Line.ln6504019-5 node2에서 MESS Line.ln6321409-1 node3로 바뀐다. 전체96 binding·상위20·다른 상·Triplex는 별도 CSV로 보존했다.

### Q9. AIDC-only의 실제 제어량은?

비영96슬롯 QoS/WAN/checkpoint 계약을 검증하지 못해 적용한 admissible action0 kW다. 실제 물리적 잠재력0의 증명은 아니다. Planning 원본 mask 감축 상한의 시간최대342.875172 kW, B0 peak slot에서6.572687 kW는 relaxation이지 실제 정책 인증량이 아니다. 시설 전체 Planning P 피크568.257479 kW와 혼동하지 않는다.

### Q10. MESS-only의 실제 제어량은?

6대 stationary proxy schedule에서 충전8슬롯 총1515.789474 kW, 방전8슬롯 총1368 kW, Q0; unit initial/terminal1140·최대1620·기존660–1620 SOC 범위와 current gate를 유지했다. 실제6대 이동 효과는 실행하지 않았고 abstract 원본 access 자료는 별도이다. PLANNING에서 B0 0.810230773→MESS/Joint 0.804653414, 차이는0.557736%p다. 이는 동일 May01 고정 feasible 연구 schedule의 AC 결과이고 B0–B3 정책 개선율이 아니다. ACTUAL에서 B0 0.848320702→MESS/Joint 0.841617405, 차이는0.670330%p다. 이는 동일 May01 고정 feasible 연구 schedule의 AC 결과이고 B0–B3 정책 개선율이 아니다.

### Q11. Joint의 추가 상호보완 효과는?

비영 AIDC 계약 미검증으로 이번 action을0으로 두어 조건부 연구 기록의 Joint=MESS-only, 관측 추가 효과0이다. 실제 잠재력0을 증명한 것은 아니다. known-mask relaxation+instant sixSTA AC는 미인증 endpoint로만 표시하고 STA응답66쌍 중복을 보존한다.

### Q12. 무엇이 제한하는가?

AIDC QoS/WAN/checkpoint·작은 source mask, 공통 Primary/Triplex 병목 전환, 실제 포트 상전류·S600·전용TX750, SOC·연결·이동, Native/grid six-vehicle 호환성, 보호·접지·역송전·GIS/현장 데이터 부재다. 정격·전압을 완화하지 않았다.

### Q13. 모든 V42 비교군에 공통 적용 가능한가?

동일 physical configuration/P5/원본Job/전체minρ 목적을 비교군에 사용하는 연구 설계는 저장했다. 새 MV/grid/Native 및6대 API와 비영 AIDC 계약을 추가 검증해야 한다. B1/B2/B3를 실행하지 않았고 Production 준비 PASS라고 선언하지 않는다.


| ID | 원본 IEEE8500 PCC | 역할/접속 | 권역 |
|---|---|---|---|
| AIDC01 | l2692655 | AIDC / MV_3PH | R07 |
| AIDC02 | l2729414 | AIDC / MV_3PH | R03 |
| AIDC03 | m1009805 | AIDC / MV_3PH | R04 |
| AIDC04 | m1047486 | AIDC / MV_3PH | R06 |
| AIDC05 | m1142815 | AIDC / MV_3PH | R07 |
| AIDC06 | 221-312488 | AIDC / MV_3PH | R02 |
| AIDC07 | m1108295 | AIDC / MV_3PH | R01 |
| AIDC08 | m1047534 | AIDC / MV_3PH | R03 |
| AIDC09 | l2955081 | AIDC / MV_3PH | R01 |
| AIDC10 | m1069498 | AIDC / MV_3PH | R02 |
| AIDC11 | l3197646 | AIDC / MV_3PH | R05 |
| AIDC12 | l3179650 | AIDC / MV_3PH | R02 |
| STA01 | m1142839 | STA / MV_3PH | R07 |
| STA02 | l3160872 | STA / MV_3PH | R07 |
| STA03 | m1069497 | STA / MV_3PH | R02 |
| STA04 | l2730163 | STA / MV_3PH | R07 |
| STA05 | m1125902 | STA / MV_3PH | R01 |
| STA06 | m1108298 | STA / MV_3PH | R01 |
| STA07 | l2804249 | STA / MV_3PH | R01 |
| STA08 | m1069438 | STA / MV_3PH | R06 |
| STA09 | m1047513 | STA / MV_3PH | R03 |
| STA10 | m1026830 | STA / MV_3PH | R05 |
| STA11 | l3216345 | STA / MV_3PH | R05 |
| STA12 | e182733 | STA / MV_3PH | R04 |

### 실행·제어 및 자료 범위

Source1.04 pu, 전체12 RegControl Vreg123.5 V, 기존 CAPBank3 off의 P5 overlay를 모든 비교군에 공통 적용했다. 원본 deadband/tap 한계·CapControl 지연과 임계값·설비 정격은 유지했다. 모든96슬롯 자동 settle, 실제tap 궤적·커패시터 states 및 phase/node 전압을 기록하고 SOURCE/P5 SHA를 보존했다. 원본 source SHA31개는 변하지 않았다. 배경부하 배율0.85와 설치GPU780·실제 workload·PCC power·적용가능 action은 서로 다른 항목이다. GPU780은12site 합계이며 logical rack pool을 실물 rack/냉각/PSU 정격으로 인증하지 않는다. Actual 시설 P 피크는568.257491 kW, Actual mask 피크는미산출(Actual causal queue archive에 source-mask 필드 없음; Planning mask를 대입하지 않음), 비영 계약 미검증에 따른 적용action은0.000000 kW다. 실제 물리 잠재력0이라는 증명이 아니다. PV actual injection은 제거하지 않고 원본 Rooftop 데이터와 weather/AEMO/Kestrel 권위를 유지했다.

May01-only 지시가 과거 May02 paired-check 계획을 덮어썼다. May02 source/input/결과는 보존했고 이번 공동 케이스의 선정·효과·미노출 검증으로 사용하지 않았다. 완료 matching AC는 metadata/SHA를 확인해 재사용했으며 interrupted output은 별도 보존했다. 날짜/시간대는 source 운전 모델의 AEST(+10)이고 host KST와 혼동하지 않는다. Source publication/as-of·CC4/calibration의 미인증 한계는 SOURCE_AUTHORITY.md와 계승 SOURCE_AUDIT.json에 남았다.

최종 May01 실행 효율 원장은 완료96슬롯11개 재사용, 신규8개(운영점768개) 및 finite/base193개를 구분한다. 완료 운영점의 명시 API Solve961회와 초기화18회를 합쳐979회다. 기록된 신규 AC runtime은146.972903초이며 finite 구간은 filesystem timestamp 근사다. DSS 내부 network iterations/CalcVoltageBases solve 및 중단된 미완료 May01 M2의0..95 운영점은 이 완료 수치에 들어있지 않다. 이미 완료된 민감도·기존46검증·QoS/geometry를 다시 실행하지 않았고 새 경량 date/resume 테스트6개만 수행했다. Native/장시간 policy Solver0, 보고서 생성의 AC solve0이다.

외부 캠페인 보존 감사에서 이번 작업의 외부campaign 쓰기·중단은0, input/manifest와 scheduler registration 변경도0이다. 다만 다른 활성 작업 중 live 외부source9개(B2 monitor1·seed recovery8)가 변경되고 stationary_dispatch.py1개가 추가되어 `original_authorities_equal=False`로 기록됐다. 모든 live 캠페인 소스가 byte-identical하다고 주장하지 않는다. 이것은 원본 DSS 및 과거PR193/196/197의 sealed 권위 보존과 구분하며, 이번 작업 자체의 진단 runner중단2건을 외부campaign중단으로 혼동하지 않는다. 상세는 별도 CAMPAIGN_PRESERVATION_REFERENCE.json이다.

선정 후 순간 AC 사전검사는 `COMPLETED_WITH_ENDPOINT_DETAIL_UNAVAILABLE`이다. 숫자 CSV 6,270행·33target의 모든 실패를 보존했다. 실패 target행은660이며 target별 중복행이므로 이를 독립 실패 dispatch 수로 세지 않는다. 상세 개별 endpoint port readback은 `UNAVAILABLE: NumPy bool JSON serialization raised after complete CSV persisted`이다. 실제 port-limit boolean 요약과 전압·선로 수치는 CSV에 남았고 복구 AC solve0이었다. 완전96슬롯 PORT_96.json의 실제 P/Q·상전류는 모두 보존됐다.

190개 finite endpoint 중20개는 P=-450/Q=-300 injection의 새480V 포트 노드 과전압으로 FAIL이며 최고1.068246498422 pu다. line·TX·port-limit 위반0도 전압 FAIL을 해소하지 않는다. `PHYSICAL_ENDPOINT_CONSTRAINT_SUMMARY.csv/json`은 개별endpoint와 corner를 구분 기록했다. full P450/Q300 rectangle은 NOT_CERTIFIED이며 현재의 Q0 96슬롯 schedule PASS를 무효전력 정책 전체의 안전성 인증으로 확대하지 않는다. 장치 정격·입지·P5를 사후 조정하지 않았다.

전용 포트 hardware는 ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED이다. 상용750kVA 12.47Δ/480Y topology/5.75% impedance 근거는 [Eaton](https://www.eaton.com/content/dam/eaton/products/utility-and-grid-solutions/transformer/pad-mounted-transformer/Eaton-Pad-mounted-Transformer-Brochure-EN-US.pdf), [ELSCO](https://elscotransformers.com/transformers/dry-type-transformers/750-kva-12470-delta-to-480y-277/)이며 모듈 병렬 규모 근거는 [Dynapower MPS125](https://dynapower.com/products/energy-storage/mps-125-energy-storage-inverter/)다. 정확한 mobile600kVA 제품, DC interface·온도·보호·현장 as-built가 인증됐다는 뜻이 아니다. %R1·XHL5.662375826·no-load0.2·imag0.5·ideal grounded node0는 문헌 topology를 따른 모델 가정이다. IEEE1547·short-circuit·인입선/GIS/역송전 승인/접지·anti-islanding commissioning은 미확인이다. 새 primary conductor0, 기존 original Triplex 삭제0·정격확대0다.

8권역과24개 교통서비스의 방향을 통과했어도 실제 접근성·거리 또는 영향 독립성 PASS는 아니다. C2 STA–STA66쌍의 median cosine0.998440은 대부분 같은 주요 선로 응답을 공유한다는 제한이다. 형상 변환은 하나의135° proper similarity이며 0.001 km 축 공차는 탐색 전에 동결했다. 새로운 source/position 좌표를 만들거나 위치별 반사·회전을 하지 않았다. 그림의 label offset은 가독성용이고 PCC 좌표는 source 원본이다.

### 재현·감사 파일

- `python -B -X utf8 -m ieee8500_v42_joint.report`는 완료된 AC/score/geometry/traffic 기록만 읽는다. 이 보고 작업의 AC·Native 호출은0이다.
- JOINT_LOCATION_SELECTION.csv SHA `900dec7fd8f16da4356bb109f2b629fa781c34de3ec94932d00264622fa5dd5a`; 같은 mapping은 C2_SCORED에 보존됐다.
- BG085_B0_PLANNING_AC_96.csv, FINAL_B0_PLANNING_ACTUAL_FRESH.csv, FINAL_MESS_PLANNING_ACTUAL_FRESH.csv, FINAL_AC_SUMMARY.csv
- MV_PORT_RATING_AUDIT.csv, PHYSICAL_CONSTRAINT_AUDIT.csv, FINAL_REGCONTROL_CAPCONTROL_TRAJECTORIES.csv
- CRITICAL_CORRIDOR_CONTROL_AUDIT.csv, FINAL_TOP20_ORIGINAL_LINE_BOTTLENECKS.csv, AIDC_MESS_JOINT_PRECHECK.csv
- P0_PCC_MAPPING_COMPARISON.csv, ORIGINAL_PRIMARY_CONNECTION_PATH_AUDIT.csv, JOINT_CONTROL_OVERLAP_AUDIT.csv의 상세는 C1_SCORED/C2_SCORED 하위에 있다.
- Python 생성 SVG/PNG는 figures/에 저장했다. 원본 topology와 named bus/proxy 좌표를 사용했으며 이미지 생성 AI를 사용하지 않았다.

로컬 dense AC archive 65개·2.379 GB는 `LOCAL_DENSE_AC_RETENTION.json`에 exact SHA/크기로 seal하여 원본 그대로 보존했다. 대용량 AC_96.npz만 Git 전송에서 제외되며 CSV·고객/PV/PCC·phasor·control·port·receipt·code는 별도 전달된다. 큰 JSON 축/parameter snapshot은 lossless gzip으로 전달하고 원본 JSON은 로컬 보존했으며 transport SHA와 decoded SHA를 각각 감사했다. 이 report는 raw JSON이 없을 때 동일 내용의 .json.gz를 읽는다. **remote_clone_dense_AC_available=False**이므로 원격 clone만으로 dense 전체 엄격 검증이나 이 report의 all-line 분석을 실행할 수 없다. 동일 SHA archive를 복원해야 하며 원격 완전 재현 PASS를 주장하지 않는다. 이 보존 조치는 source/data 변경이나 추가 AC 실행이 아니다.

최적해·글로벌 최적성·미노출 독립검증·B0–B3 개선율·실증 설치 가능성을 주장하지 않는다. 실제 정책·Native/grid 결합·현장 gate를 충족하기 전까지 최종 Production 동결을 하지 않는다.
