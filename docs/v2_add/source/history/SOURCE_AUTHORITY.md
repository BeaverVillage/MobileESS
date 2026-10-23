# IEEE8500 Balanced / Unbalanced Source Authority

부모 Unbalanced P5는 commit `5cf5986a981428a4544a3a82d44b8e55d635fb70`, [Draft PR #196](https://github.com/BeaverVillage/MobileESS/pull/196)으로 보존했다. 그 이전 [PR #193](https://github.com/BeaverVillage/MobileESS/pull/193)의 feeder·교통·접속 자료 및 [PR #62](https://github.com/BeaverVillage/MobileESS/pull/62)의 과거 Vreg 출처를 유지한다. V42 입력/전력 Authority는 `625bbcb8b9a54a00c1660c26d96f7737c2f75457`의 기존 P5 byte를 그대로 사용한다. 새 브랜치는 부모 P5 commit에서 별도로 만들었으며 이전 코드·결과 파일을 수정하지 않았다.

공식 모델의 권위는 로컬 EPRI OpenDSS r4173 배포 ZIP의 `Distrib/IEEETestCases/8500-Node/`다. ZIP SHA256은 `eb8a91ded9904ffe6f87dd461688339b665ce05217d344e823941a3c765493bd`, 채택본 31개 파일의 추출 이력은 [기존 원본 감사](../../ieee8500_v42/data/IEEE8500_SOURCE_AUDIT.md)에 있다. 최신 외부 배포본 또는 r4173 실행 엔진과 동일하다는 인증은 하지 않는다. 실행 엔진은 `DSS C-API Library version 0.14.5 revision 87d85c2622c8281b92255335bc7c09b11191b21d based on OpenDSS SVN 3723 [FPC 3.2.2] (64-bit build) MVMULT INCREMENTAL_Y CONTEXT_API PM 20240329033747; License Status: Open DSS-Python version: 0.15.7 OpenDSSDirect.py version: 0.9.4`다.

Balanced는 원본 `Master.dss`가 `Loads.dss`를 Redirect하고, Unbalanced는 `Master-unbal.dss`가 `UnbalancedLoads.DSS`를 Redirect한다. 두 Master를 실제 별도 context로 compile했다. source 31개는 부모 P5 Git blob 및 기존 sealed source와 SHA256 일치한다. 장치·bus·line/CT axes·모든 CapControl/RegControl 원본 속성이 같고, 고객 Load 객체 구성만 다르다. kvar/kV 정의의 Capacitor에서 사용되지 않는 CMatrix getter가 미초기화 숫자 문자열을 노출하므로 그 getter 비교만 제외했다. 실제 정의 파일, kvar/kV/Cuf/연결/전류정격 등 모든 유효 속성은 동일하다.

원본 `Loads.dss` 주석은 2상 wye 모델이 3상 LN 전압 기준을 사용하여 `.208/sqrt(3)=.120088856 kV`가 되고 총 kW를 두 레그에 균등하게 나눈다고 명시한다. 서비스 변압기는 두 hot의 반대 극성을 만든다. 실제 208 V 3상 고객이나 계통 전체의 ABC 완전 평형을 뜻하지 않는다. [EPRI Load 속성](https://opendss.epri.com/Properties7.html)은 kW가 모든 상의 합계임을, [EPRI 부하 배분 설명](https://opendss.epri.com/OpenDSSLoadAlocation.html)은 복수 상 Load의 균등 배분을 설명한다.

두 모델의 명목 총 입력은 10773.17000000 kW / 2700.010911176041 kvar다. 고객 P 최대 차이 5.15e-14 kW, Q 최대 차이 1.33e-14 kvar는 원본 decimal 저장 및 float 오차다. 1,177 ID 전수 일대일 대조와 Fixed24/Variable1,153 분류 보존을 검증했다.

기존 2,354개 120 V hot별 연구 PV Generator의 위치·설치 용량·Model1·역률·전압 특성은 전부 보존한다. Balanced 고객마다 기존 두 PV를 정확히 묶어 설치 용량을 보존하며 PV를 새로 균등 배분하지 않는다. 고객 부하 균형과 PV 균형을 혼동하지 않는다. 실제 PV 출력은 전압에 따라 달라질 수 있다. 설치 총량은 1,276.937105381 kW/kVA, 명령 Q=0이다.

동일한 P5 overlay는 Source1.04, 전체12 Vreg123.5, CAPBank3의 state0, 원본9 CapControl 속성과 지연·deadband·tap한계다. overlay SHA256 `aea60229da9599906204a9c83a397aff88c5b69bc02eca965621497c9507c925`는 부모 P5와 동일하다. 제어 상태 궤적 자체는 서로 다른 조류에 따라 달라질 수 있다.

`SOURCE_AUTHORITY.json`은 재사용 AEMO/GFS/NOAA/Kestrel/C1/Runtime/CC4 입력의 전체 SHA roster를 저장한다. `.npz` 입력을 직접 재사용해 Forecast/Actual 인과 경계·96축·정규화·BG.552 및 Fixed static 규칙을 바꾸지 않았다. 기존 연간 normalization reference의 D-1 가용성, Runtime/CC4 calibration ingestion as-of 및 GFS 실제 publication receipt는 UNVERIFIED다. 과거 노출된 2025-05-01의 Fresh 재실행은 독립 미노출 검증일이 아니다.
