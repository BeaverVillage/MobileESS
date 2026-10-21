# IEEE8500 source audit — 2026-09-10

**IEEE8500_SOURCE_FOUND_IN_LOCAL_ARCHIVE**. 지정 ZIP의 top-level canonical distribution에서 IEEE8500 unbalanced case를 확인하고, 이 별도 workspace에 31개 파일을 byte-identical하게 추출했다. MobileESS V41R4 코드와 결과에는 쓰기 작업을 하지 않았다. IEEE123 복제/변형, AIDC host 선정, B0/B1/B2/B3 실행은 하지 않았다.

## 원본과 재귀 검색

입력 ZIP: `C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\EPRI IEEE 123-bus canonical OpenDSS case\electricdss-code-r4173-trunk.zip`

ZIP SHA256 (조사 전/추출 후/전체 감사 종료 후 동일):

`eb8a91ded9904ffe6f87dd461688339b665ce05217d344e823941a3c765493bd`

ZIP 자체의 8,907 entries와 모든 nested ZIP을 재귀 순회했다. 총 41개 ZIP container를 읽었고 오류는 0개다. 내부 경로의 8500 표기 및 Master-unbal/UnbalancedLoads 이름 기준으로 503개 파일을 발견하고 정확한 내부 경로·bytes·SHA256을 `audit/archive_ieee8500_matches.csv`에 기록했다. Nested ZIP 경로는 `outer.zip!/inner/path` 표기다. 17개 embedded non-ZIP(.7z) container는 목록만 기록했고 내부를 열지는 않았다. IEEE8500 존재 확인은 이들과 무관하게 top-level canonical case에서 직접 성립한다.

채택한 내부 directory:

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/`

Version7/Version8 및 Training의 사본을 혼합하지 않았다. canonical이라는 판단은 이 로컬 EPRI 배포 archive의 `Distrib/IEEETestCases` 위치와 master/구성 파일에 근거한다. 최신 외부 IEEE 배포본과의 동일성 인증이나 r4173 native executable 재현을 주장하지 않는다. 전체 채택본 31개 파일의 정확한 경로와 hash는 `audit/source_manifest.csv` 및 JSON에 있다.

## 요청 파일과 SHA256

아래 hash는 원본 ZIP entry의 **압축 해제된 원시 bytes** 기준이다. 줄바꿈이나 파일명 대소문자를 정규화하지 않았다. `UnbalancedLoads.DSS`는 실제 대문자 확장자이다.

| 파일 | SHA256 |
|---|---|
| `Master-unbal.dss` | `59bdb5e9da4bf3c063d7efdfa6b9b1e537d7786533fefa0f2c470cfb2e12622b` |
| `Buscoords.dss` | `aa3d71873e595578f8c952dffd16b8cf74d5d811da40e16db8a4f0c72abe8c32` |
| `Lines.dss` | `460eb5e8179bda1926d0d70cf4fc9d8bdd29ab4dd9a101941730749f8a4a663a` |
| `Transformers.dss` | `cab397f65f5de08c4d82cf794c03c432b404cd5db7db37ff827869db8344b708` |
| `UnbalancedLoads.DSS` | `72705438556764981d430a9148c84b783f76b977911a2284ffe9295740bddaba` |
| `Regulators.dss` | `041f353f55076feaaf751bbb20551226f8727ddfbdfc5101cf1b1f222da38617` |
| `Capacitors.dss` | `cc05836176a6715b121619079eb6cef96e77468a3368c8ed44815f2e9d684dcf` |
| `CapControls.DSS` | `562818b4d905f391e88ed58efcd54150d4296d6cfb355f8abac32c969a290348` |
| `LoadXfmrCodes.dss` | `213a3c0478b33a4cb95d82d40e076d1c1ec19b22033e4aa03e6dcdd8b92fa8f9` |
| `Triplex_Lines.DSS` | `abf45521bc05a7f9d5c3fa4c94c4f24f7ea9bc984e7086b303ae4a143d77971d` |

정확한 내부 경로:

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/Master-unbal.dss`

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/Buscoords.dss`

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/Lines.dss`

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/Transformers.dss`

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/UnbalancedLoads.DSS`

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/Regulators.dss`

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/Capacitors.dss`

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/CapControls.DSS`

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/LoadXfmrCodes.dss`

`electricdss-code-r4173-trunk/electricdss-code-r4173-trunk/Distrib/IEEETestCases/8500-Node/Triplex_Lines.DSS`

## Compile와 감사 범위

명령은 별도 workspace의 `source/Master-unbal.dss`에 대한 Compile이다. 원본 master의 redirect closure와 Buscoords를 그대로 읽었다. 별도 source 편집이나 runtime용 modified master를 만들지 않았다. 현재 dependency 파일은 12개이며 명령/파일 ledger는 `audit/compile_dependency_audit.json`에 있다.

엔진: `DSS C-API Library version 0.14.5 revision 87d85c2622c8281b92255335bc7c09b11191b21d based on OpenDSS SVN 3723 [FPC 3.2.2] (64-bit build) MVMULT INCREMENTAL_Y CONTEXT_API PM 20240329033747; License Status: Open  / DSS-Python version: 0.15.7 / OpenDSSDirect.py version: 0.9.4`

OpenDSSDirect.py 0.9.4 / DSS-Python 0.15.7 / DSS C-API 0.14.5 (OpenDSS SVN 3723 기반)에서 **compile error=0**, circuit=`ieee8500u`이다. 소스 archive r4173과 엔진 기반 revision은 다르므로 이를 명시적으로 구분한다.

Master의 `CalcVoltageBases`는 bus list와 nominal bases를 만드는 엔진 내부 무부하 계산을 포함한다. 별도의 `Solve`, time-series, control-scenario 또는 B0–B3 명령은 실행하지 않았다. `Run_8500Node_Unbal.dss`는 실행하지 않았다. 따라서 이번 PASS는 source/compile/topology 감사이며, 비대칭 부하 운전점의 수렴·전압 한계·열용량 통과 판정은 아니다.

## Bus, phase, nominal voltage

| 항목 | 확인값 |
|---|---:|
| OpenDSS buses | 4,876 |
| Electrical nodes (bus-phase nodes) | 8,531 |
| Circuit elements | 7,280 |
| Loads | 2,354 |
| 좌표가 정의된 buses | 4,876 |
| 115-kV ABC source/substation buses | 2 |
| 12.47-kV primary buses | 2,520 |
| Primary ABC / A / B / C / AC buses | 647 / 685 / 621 / 564 / 3 |
| Secondary split-phase buses | 2,354 |

‘8500-node’는 case 이름이며 8,500개의 bus를 의미하지 않는다. 여기서는 엔진이 4,876 buses / 8,531 nodes를 보고한다. 단상 regulator 및 capacitor sensing link 등 모델의 내부 bus도 포함한다.

Source는 115 kV, substation transformer는 115/12.47 kV이다. Primary의 LN base는 7.1995578568 kV이다. Master에는 `[115, 12.47, 0.48, 0.208]` voltagebases가 선언되어 있으나 0.48-kV base의 bus는 없다. Secondary는 transformer winding이 **0.12/0.12 kV의 center-tapped 120/240-V** 모델이며, 2개의 반대 극성 node `.1.2`를 쓴다. 엔진이 secondary에 할당하는 LN base는 약 0.120089 kV이고 그 sqrt(3) 값이 0.208 kV이다. 이 숫자를 실제 208-V 3상 secondary라고 해석하면 안 된다.

## Regulators, capacitors, transformers

- Transformers: **1,190개** = 115/12.47-kV 3상 substation transformer 1개 + 단상 regulator transformer 12개 + 3-winding center-tapped 단상 service transformer 1,177개.
- Substation: delta/grounded-wye, 27,500 kVA, XHL=15.51%. 원본 Reactor.HVMV_Sub_HSB가 source impedance를 별도 표현한다.
- Regulator: FEEDER_REG, VREG2, VREG3, VREG4의 **4 banks**, bank당 3상 독립 제어로 **12 RegControls**. 모델 winding voltage는 7.2/7.2 kV. feeder Vreg=126.5 V, 다른 bank는 125 V, PTRatio=60, band=2 V이다. 모든 input/output 단자를 host 후보에서 제외했다.
- Capacitors: **4 banks, 10 objects, 3,900 kvar**. CAPBank0은 3×400 kvar, CAPBank1/2는 각각 3×300 kvar, CAPBank3는 3상 900 kvar이다. 앞선 3개 bank에는 단상 CapControls 총 9개가 있고, CAPBank3용 control은 이 master에 없다.
- 이 값은 원본 모델의 정격/구성이다. regulator tap 동작이나 capacitor switching의 부하 운전 성능은 평가하지 않았다.

상세 목록은 `audit/transformers.csv`, `regulators.csv`, `capacitors.csv`, `capacitor_controls.csv`에 있다.

## Line topology

| 항목 | 확인값 |
|---|---:|
| Lines | 3,703 |
| Primary-model lines / triplex lines | 2,526 / 1,177 |
| 3-phase / 1-phase / 2-conductor-or-phase line objects | 639 / 1,884 / 1,180 |
| Open line objects | 0 |
| 전체 graph bus vertices | 4,876 |
| 물리적 series element edges | 4,889 |
| phase bank를 합친 unique bus-pair corridors | 4,875 |
| 연결 성분 / cycle rank | 1 / 0 |
| ABC primary graph vertices / corridors | 647 / 646 |

2-conductor/phase line 1,180개 중 1,177개는 triplex이며 3개는 primary 2상이다. 3개 capacitor sensing corridor와 4개 regulator bank가 각각 세 단상 요소로 표현되므로 bus-pair 중복을 그대로 cycle로 세면 잘못된 mesh 판정이 나온다. 이를 상별 bank로 집계하면 전체 feeder는 연결된 radial tree이다. 3,703개 line의 원본 terminal, phase, impedance matrix, 길이 및 단위는 `audit/lines.csv`; transformer/reactor를 포함한 edge inventory는 `audit/topology_edges.csv`에 있다.

Line units는 km=2,473, ft=1,177, none=53이다. units=none인 link를 임의로 km나 ft로 변경하지 않았다. `source/Lines.dss`와 다른 원본 파일도 변경하지 않았다.

## 12-site 후보 선정 방법론

전기적 자격 조건을 만족하는 **638개 무순위 후보**를 확인했다. 총 647개 primary ABC bus에서 source/substation/regulator 관련 9개를 추가 제외한 결과이며 모두 root와 ABC로 연결되고 서로 다른 원본 좌표가 있다. 후보 pool 확인은 12개의 host를 선정하는 행위와 다르다.

`12_SITE_CANDIDATE_SELECTION_METHODOLOGY.md`에서 다음을 동결했다: 고정 Melbourne 12-anchor 상대 구조의 허용 distortion, 최소 전기적·지리적 거리, major lateral 분류, 공통 upstream-path ratio의 분모/분자, 그리고 lexicographic 목적 순서. 상대 구조 보존을 hard constraint로 두고 major lateral diversity → upstream 공유 최소화 → electrical distance → geographic dispersion 순으로 평가한다. 고정 major-lateral 규칙은 3개 major lateral을 만들며, 12개로 맞추기 위해 회로 또는 분류 threshold를 바꾸지 않는다.

방법론의 joint feasibility/전역 최적성은 아직 평가하지 않았다. **선정된 host 목록은 빈 배열**, AIDC는 예정 수 12개, added AIDC loads=0이다. 최종 12-site 선정과 모든 B0/B1/B2/B3 시뮬레이션은 이번 범위 밖이다.

## 무결성과 재현

`archive_audit.py` → `compile_audit.py` → `methodology_inputs.py` → `finalize_audit.py` 순서로 이 workspace 안에서만 감사 산출물을 만든다. V41R4 모듈을 import하거나 scenario runner를 호출하지 않는다. source 31개는 추출 전 entry hash와 compile/감사 종료 후 file hash가 전부 일치했고 source directory의 추가 생성 파일도 없다. ZIP SHA256도 작업 전후 일치했다. V41R4에 쓰지 않았지만 기존 전체 대규모 V41R4 tree의 사전/사후 전수 hash를 수행했다는 주장은 하지 않는다.

검증 기록: `audit/final_verification.json`. 동결 입력과 산출물 SHA256: `FREEZE_MANIFEST.json`. 경로/해시 전체 목록: `audit/archive_ieee8500_matches.csv`, `audit/source_manifest.csv`.
