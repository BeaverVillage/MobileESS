# 호주 원자료 연결과 한계

2025-05-01은 이미 사용한 개발일이다. 96개 15분 구간은 고정 AEST(UTC+10), 00:00시작→다음날00:00종료다. grid자료는 interval ending, 날씨·GPU·전력입력은 대응 구간 시작을 사용한다.

* Demand Forecast: VIC1 PREDISPATCHREGIONSUM, 48개30분 MW 평균을 두 번 반복. issue Apr30 17:32:39, cutoff18:00. 지역 에너지 116855.645000 MWh 보존.
* Rooftop Forecast: 48개30분 POWERMEAN, issue18:00. 동일 interval ending repeat2. Rooftop Actual은 MEASUREMENT의 지역 추정 출력이며 모든 고객 실측이라고 주장하지 않는다.
* Demand Actual: DISPATCHREGIONSUM INTERVENTION0의 288개5분 TOTALDEMAND를 세 개씩 평균. piecewise-constant interval power 해석으로 116854.600833 MWh 보존. 기존 V42 15분 말점 선택은 14.319167 MWh 차이가 있어 새 adapter만 수정했다. 원본 producer·raw는 보존했다.
* GFS96슬롯은 Planning C1, NOAA 시간별 관측은 기존 시간 선형 보간으로 Actual C1에 각각 연결했다. GFS init16:00는 cutoff 전이지만 실제 publication 수신시각 증거는 없다.
* Kestrel Planning1649 known UID, Actual2498 UID는 원본731MB archive SHA `3a90f9ac40991712f8718c686fa7b05d7a303a44a87ed1a8f21b403c11efd26f`에서 submit/start/end/duration/requestedGPU를 직접 대조했다. Actual은 private service truth와 causal FCFS queue이며 duration/end를 controller에 미리 전달하지 않는다. GPU780/rack/CC4/backlog와 C1/PF.95를 유지했다.

원본2354 Load 중48Fixed는 `Status=fixed` 그대로다. OpenDSS Fixed는 전역/shape multiplier를 무시한다. 원본 P/Q에 연구BG=.552를 한 번 적용한 뒤 시계열에서는 고정한다. 2306Variable만 동일한 gross factor를 원본P/Q에 직접 적용하며 loadmult=1로 이중 배율을 막았다. 각 고객의 PF·버스·상·model1의 전압 의존성은 유지했다. Fixed/Variable의 시간변동 차이로 집계 상비율은 달라질 수 있으며 고유 상 연결과 각 상 내부 배분은 보존했다.

V42의 frozen constants는 P95=7100.2615MW, annualmax=9490.53MW, alpha=.7481417265421424, PVmax=4021.226MW다.
`solar=alpha*regional_PV/PVmax`, `gross=alpha*regional_demand/P95 + PV_ratio*solar`.
Variable P/Q=`originalP/Q*.552*gross`; Fixed P/Q=`originalP/Q*.552`.
IEEE8500 native10773.17kW에 PR62 원본부하 비율을 적용한2354개 연구Generator의 설치용량은 1276.937105kW/kVA다. 원본에는 PV0개였다. 각 PV는 해당 원본 고객 hot/120V/conn에 접속하며 Q명령0, Planning/Actual 설치용량 동일, 시계열은 Forecast/Actual로 분리한다. BG를 PV에 중복 적용하지 않는다.
원본Generator model1과 원본 Vmin/Vmax를 보존했으므로 임계 밖에서는 실제 P가 전압의 제곱에 따라 변한다. AC 실제 출력·전력보존은 nominalP와 구분해 검산했다.

이는 **Synthetic Load Mapping**이다. 지역MW를 직접 주입하거나 개별 고객 실측을 재구성하지 않았다. IEEE123의 실측 cluster/Q변동을 IEEE8500에 무단 이식하지 않았다.
실제 forecasting 값은 cutoff검사·source분리로 Planning에 Actual0회 전달했지만, inherited annual-normalizer/CC4/Runtime calibration의 D-1 가용성 및 GFS publication은 UNVERIFIED다. 전체 pipeline 미래정보누수0 인증은 하지 않으며 Production 승격을 차단한다.
SCATS/SUMO 교통24ID와 Planning ETA/route자료는 PR193 감사 자료 및 SHA로 보존한다. B0 MESS주입0이며, 6대 Actual/SUMO·Native/SOC/location효율 통합은 UNVERIFIED다.

정확한 경로/SHA/원래 해상도/단위/시간범위는 `PLANNING_INPUT_FREEZE.json`, `ACTUAL_EXOGENOUS_AUDIT.json`, `ACTUAL_Kestrel_QUEUE_AUDIT.json`, `AEMO_PV_96SLOT_ALIGNMENT.csv`에 있다.
Fixed의 공식 의미: [OpenDSS Load properties](https://opendss.epri.com/Properties7.html). 제어 방식은 [DSS-CAPI RegControl](https://github.com/dss-extensions/dss_capi/blob/0.14.5/src/Controls/RegControl.pas), [CapControl](https://github.com/dss-extensions/dss_capi/blob/0.14.5/src/Controls/CapControl.pas) 소스를 대조했다.
