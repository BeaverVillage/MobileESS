# 현재V3: 사전 점수 기반 공동 후보 선택

**원본12 AIDC와12 LV STA service ID를 유지하면서 사전 동결된 개발일 controllability surrogate로 공동 후보를 선택했다.** 6 MESS unit과 원본CT/Triplex/정격/자동 제어를 확대하지 않았다. 이 단계는 최종 연구 case의 실제AC·QoS·SOC·배차 적격성을 대체하지 않으며 Production 인증을 주장하지 않는다.

기하 seed 점수 0.01599159385에서 선택 점수 **0.017689066355**로 0.001697472505 증가했다. 허용된 원본606MV/AIDC 및1177LV/STA를 각12서비스에서 모두 읽고 site-specific score를 사용했다. Source/role guard,24 distinct bus,552 strict 방향을 모든 이동에서 유지했고 원본 input과 공통 matrix로 직접 재검증했다. 모든STA는LV upstream-primary coordinate proxy이며 `ASSUMED_PROXY_DIRECTION_PASS`이다.

공통 회전은 geometry-only seed에서 이미 선택한 **-168.244235052°**로 유지했다. 점수나B3 성능으로 회전·공차·개별 좌표를 조정하지 않았다. 알고리즘은 전체 role domain의1site 최선 개선 후2site 공동 개선을 반복했다. 1/2-site local optimum에 도달했다. 전체 combinatorial/global transform-family 최적성은 주장하지 않는다.

점수 의미는 부모의 `selection_scores/PREREGISTRATION.json`을 그대로 따른다. 개발일4시간×20원본 선로의 signed 전류반응에 AIDC known-original-UID activeGPU/C1 swing/PF.95 상한, STA5kW/3kvar 공통 Q vector, 6차량/12STA exposure 및 원본 초기 위치 safeETA+600s를 반영한 heuristic이다. AIDC 상한은 전체QoS/WAN job dispatch를 인증한 실제 flexibility가 아니며, STA exposure는 동시12dock 사용 또는 실제route 보장이 아니다. anonymousCC4/idle credit, B1/B2/B3 성과나 hidden-day claim을 추가하지 않았다.

[저압 연구 포트 설계](../../LV_PORT_SIMULATION_DESIGN.md)의 P±5kW,Q±3kvar,S6kVA,eachhot27A 및 실제|V1−V2|에 따른 current ceiling은 개별/합성 실제AC에서 다시 검사해야 한다. 원본 CT winding·Triplex 모든conductor·전압·reverse power를 유지하고, Q/PCS/DC–DC/BMS·접속 효율/지연 가정을 공개한다. Field 근거 부재는 사용자 허용 연구를 중단시키지 않는다. Study freeze는 최종 모델 적격성 통과 후 부모가 수행하며 현재 선택 파일은 AC PENDING이다.

Witness SHA256: `4a70fd13bf08c8512d30f74e48dfafb46fdddd4e112a3aee92a8191f22cad016`. 선택 방법은 score CSV 값을 보기 전에 `SCORING_PREREGISTRATION.json`으로 동결했고, 입력CSV·root receipt·score policy·hardware model SHA는 `SCORE_INPUT_SHA256.json`에 있다.

| 서비스 | traffic | 선택bus | frozen score |
|---|---|---|---|
| AIDC01 | TN_01 | m1125934 | 0.00177308895 |
| AIDC02 | TN_02 | m1009805 | 0.000891986763 |
| AIDC03 | TN_03 | m1027002 | 0.000366805961 |
| AIDC04 | TN_04 | m1047480 | 0.000359812472 |
| AIDC05 | TN_05 | l3029498 | 0.00119902266 |
| AIDC06 | TN_06 | m1125976 | 0.00181232033 |
| AIDC07 | TN_07 | l3048221 | 0.0010705989 |
| AIDC08 | TN_08 | l2728247 | 0.00186894515 |
| AIDC09 | TN_09 | m1069420 | 0.001048046 |
| AIDC10 | TN_10 | m1125962 | 0.00182069491 |
| AIDC11 | TN_11 | m1026872 | 0.00104002854 |
| AIDC12 | TN_12 | m1142875 | 0.00179468799 |
| STA01 | TN_43 | sx2955055b | 0 |
| STA02 | TN_14 | sx2992657a | 0.00043458653 |
| STA03 | TN_35 | sx2936211c | 5.611364e-06 |
| STA04 | TN_28 | sx3085394c | 5.693075e-06 |
| STA05 | TN_37 | sx2897766c | 5.665299e-06 |
| STA06 | TN_41 | sx2822867b | 8.35807e-07 |
| STA07 | TN_32 | sx3047058a | 0.000509469718 |
| STA08 | TN_47 | sx3729298a | 0.000343781142 |
| STA09 | TN_42 | sx3027133a | 0.000494337021 |
| STA10 | TN_24 | sx2748125c | 1.4305874e-05 |
| STA11 | TN_44 | sx3085401a | 0.000471566849 |
| STA12 | TN_17 | sx2710516a | 0.000357175034 |
