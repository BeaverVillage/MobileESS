# V22S Melbourne 12-site scale re-audit

RESULT CLASSIFICATION:
V22S_BOUNDARY_OR_IDENTITY_CONFLICT_REMAINS

## 1. Source-discovery corrections

V20의 핵심 수정은 ME4의 7.6 MW installed/12 MW IT-capacity 분리, Fujitsu의 28 MW IT-capacity 회복, CDC BK1의 34 MW operating-build-capacity 회복, IBM MEL01의 Deer Park MEL11 tenant 관계 확정이다. ME5는 발전기 nameplate 외 용량 권한이 없어 null을 유지한다.

## 2. 12-site table

| Site | identity | April status | capacity MW | actual operating-load MW | boundary | low / central / high | confidence |
|---|---|---|---:|---:|---|---|---|
| AIDC01 | Equinix ME4 | operational | 7.6 | null | BUILT_CAPACITY | 7.6 / 7.6 / 18.0 | identity A / capacity B (D) |
| AIDC02 | Micron21 | operational | 2.0 | null | FULLY_BUILT_OUT_POWER | 2.0 / 2.0 / 2.0 | identity A / capacity D (F) |
| AIDC03 | Fujitsu Noble Park | operational | 28.0 | null | IT_CAPACITY | 28.0 / 28.0 / 28.0 | identity A / capacity B (A) |
| AIDC04 | AAPT / TPG Richmond | operational | None | null | MVA_INPUT | None / None / None | identity B / capacity D (F) |
| AIDC05 | NEXTDC M2 | operational | 42.0 | null | BUILT_CAPACITY | 42.0 / 42.0 / 42.0 | identity A / capacity A (B) |
| AIDC06 | NEXTDC M3 | operational | 13.5 | null | BUILT_CAPACITY | 13.5 / 13.5 / 13.5 | identity A / capacity A (B) |
| AIDC07 | Vocus Mitcham | operational | 9.0 | null | FULLY_BUILT_OUT_POWER | 9.0 / 9.0 / 9.0 | identity A / capacity D (F) |
| AIDC08 | NEXTDC M1 | operational | 15.0 | null | IT_CAPACITY | 15.0 / 15.0 / 15.0 | identity A / capacity A (A) |
| AIDC09 | Equinix ME5 | operational | None | null | GENERATOR_NAMEPLATE | None / None / None | identity A / capacity D (A) |
| AIDC10 | CDC Brooklyn BK1 | operational | 34.0 | null | OPERATING_CAPACITY | 34.0 / 34.0 / 34.0 | identity B / capacity A (B) |
| AIDC11 | IBM MEL01 / Digital Realty MEL11 | operational | None | null | CONFLICT_UNRESOLVED | 6.7 / None / 13.4 | identity A / capacity D (F) |
| AIDC12 | STACK MEL01A | operational | 36.0 | null | BUILT_CAPACITY | 36.0 / 36.0 / 36.0 | identity A / capacity A (A) |


12개 시설 모두 2025년 4월 운영 identity를 검토했다. 그러나 site별 실제 April operating load는 0/12개만 확보되었다. capacity와 actual load는 어느 행에서도 동일시하지 않았다.

## 3. Boundary coverage

- SET_A actual load: 0 sites, total null
- SET_B IT capacity: 3 sites, 55.0 MW
- SET_C official operating/built MW: 6 sites, 148.1 MW
- SET_E MVA: 2 sites, MW로 합산하지 않음
- SET_F nameplate only: 2 sites, central capacity에서 제외

## 4. Strict scale

Strict load scale은 null이다. Strict capacity-to-capacity 산술은 동일 site/host coverage를 갖는 SET_B 3-site와 SET_C 3-site 후보만 생성했으며 선택하지 않았다.

| Candidate | Sites | Numerator MW | Denominator MW | rho | IEEE123 equivalent MW @ PF=0.98 |
|---|---|---:|---:|---:|---:|
| STRICT_SET_B_IT_CAPACITY_VS_HOST_FIRM_MW | AIDC01,AIDC03,AIDC08 | 55.000000 | 166.391000 | 0.330546724282 | 1.619678948982 |
| STRICT_SET_B_IT_CAPACITY_VS_HOST_NORMAL_MW | AIDC01,AIDC03,AIDC08 | 55.000000 | 249.556000 | 0.220391415153 | 1.079917934251 |
| STRICT_SET_C_BUILT_CAPACITY_VS_HOST_FIRM_MW | AIDC01,AIDC08,AIDC12 | 58.600000 | 190.981000 | 0.306836805756 | 1.503500348202 |
| STRICT_SET_C_BUILT_CAPACITY_VS_HOST_NORMAL_MW | AIDC01,AIDC08,AIDC12 | 58.600000 | 286.446000 | 0.204576080657 | 1.002422795221 |


## 5. Equivalent 12-site case

단일 primary를 만들지 않았다. 사전등록 규칙으로 얻은 capacity interval은 **(196.25000, 206.00000] MW**이며, ME5의 양의 미확정 하한과 MEL11 충돌 때문에 low/primary/high aggregate scale은 null이다. 숫자 high-bound corner weight만 합계 1.0으로 제공한다.

| Site | high-bound corner weight | authority |
|---|---:|---|
| AIDC01 | 0.036893203883 | ENGINEERING_EQUIVALENT |
| AIDC02 | 0.009708737864 | ENGINEERING_EQUIVALENT |
| AIDC03 | 0.135922330097 | ENGINEERING_EQUIVALENT |
| AIDC04 | 0.011893203883 | ENGINEERING_EQUIVALENT |
| AIDC05 | 0.203883495146 | ENGINEERING_EQUIVALENT |
| AIDC06 | 0.065533980583 | ENGINEERING_EQUIVALENT |
| AIDC07 | 0.043689320388 | ENGINEERING_EQUIVALENT |
| AIDC08 | 0.072815533981 | ENGINEERING_EQUIVALENT |
| AIDC09 | 0.014805825243 | ENGINEERING_EQUIVALENT |
| AIDC10 | 0.165048543689 | ENGINEERING_EQUIVALENT |
| AIDC11 | 0.065048543689 | ENGINEERING_EQUIVALENT |
| AIDC12 | 0.174757281553 | ENGINEERING_EQUIVALENT |


## 6. Capacity vs actual load

모든 MW/MVA는 source wording에 따른 boundary를 유지했다. 34 MW CDC와 NEXTDC built MW는 실제 소비가 아니다. Fujitsu 28 MW는 facility specification의 IT capacity이며 actual load가 아니다.

## 7. IEEE123 denominator

수요 분모는 frozen background peak 2.315469136076 MW, 용량 분모는 IEEE PES 5.0 MVA substation transformer다. 두 분모는 혼용하지 않았다.

## 8. PCC interface

PF 0.95/0.98/1.00 및 loading 0.80/0.90 민감도를 산출했다. 모든 결과는 `IEEE123_EQUIVALENT_CASE_STUDY_INTERFACE`이며 실제 Melbourne DNSP transformer가 아니다.

| Strict case | Site | P_peak MW @ capacity PF=0.98 | Main S_required MVA @ PF=.98/loading=.80 | Rounded MVA |
|---|---|---:|---:|---:|
| STRICT_SET_C_BUILT_CAPACITY_VS_HOST_FIRM_MW | AIDC01 | 0.194993219221 | 0.248715840843 | 0.3 |
| STRICT_SET_C_BUILT_CAPACITY_VS_HOST_FIRM_MW | AIDC08 | 0.384855037936 | 0.490886527979 | 0.5 |
| STRICT_SET_C_BUILT_CAPACITY_VS_HOST_FIRM_MW | AIDC12 | 0.923652091046 | 1.178127667150 | 1.5 |
| STRICT_SET_C_BUILT_CAPACITY_VS_HOST_NORMAL_MW | AIDC01 | 0.130007051940 | 0.165825321352 | 0.3 |
| STRICT_SET_C_BUILT_CAPACITY_VS_HOST_NORMAL_MW | AIDC08 | 0.256592865671 | 0.327286818458 | 0.5 |
| STRICT_SET_C_BUILT_CAPACITY_VS_HOST_NORMAL_MW | AIDC12 | 0.615822877610 | 0.785488364299 | 1.0 |


## 9. Remaining unresolved items

ME5 capacity, MEL11 capacity conflict/exact host, Jemena firm/normal capacity, 실제 site별 DNSP connection rating, April actual load가 미해결이다.

## 10. Ready flags

Strict capacity와 PCC engineering만 ready이다. Strict load, 단일 12-site equivalent scale/weight, GPU weight, final grid science는 ready가 아니다.

## 11. Science firewall

ML retraining/forecast edit/GPU-h scaling/B0-B3/OpenDSS/grid science 호출은 모두 0이다.

## 12. Generated artifacts + SHA256

모든 생성 artifact의 SHA256은 `V22S_ARTIFACT_SHA256.json`에 기록한다. 자기 자신의 재귀 해시는 정의할 수 없으므로 해당 manifest 자체만 목록에서 제외한다.
